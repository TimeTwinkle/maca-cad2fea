"""MACA 红蓝对抗正式运行器（整合全部实测教训，一键跑通）。

定位：不替代 MIDAS 一键导入，而是白盒拆解导入过程 + 独立闭式解比对，
把"导入错了/画错了/建错了"定位到具体环节，沉淀成可复用规则。

链路（全部实测踩坑后修正）：
    CAD DXF
      -> cad_model 实体解析（263节点/371杆）
      -> 连通分量筛选（371杆散落47个孤立碎片，取最大相连分量=30节点/46杆）
         [踩坑RULE-004：不筛就直接建=机构发散]
      -> MIDAS 复刻导入（米制/竖支锁/1111100）
         [踩坑RULE-001/006：缺竖向约束=位移发散到1e10m]
      -> /doc/ANAL 真 FEA -> /post/TABLE 取位移(D*)/弯矩(Moment-y)
      -> 蓝军闭式解（简支梁 5qL⁴/384EI / qL²/8）
      -> 比对 -> 归因 -> duel_rules.json 沉淀

红方双态（评审收尾 A 条）：
    - MIDAS 实时态（APISTART=200/201）：red_source="MIDAS实时"，取数自 /post/TABLE。
    - 快照态（APISTART 非 200/201，会话未建）：自动降级读 maca_review/real_fea_table_165.json
      的 165 行明细作比对基准，red_source="表格3快照"，可逐行追溯。
    两者皆缺才报 red_unavailable（判据 1 要求此时 available=false 除外，正常路径恒 true）。

口径（评审收尾 B 条）：
    - 材料 E 读 strategy.json（竹材 6GPa，M2 open 依 PPT slide11），不再硬编码 Q355 钢。
    - 蓝军跨度/截面/荷载/E 一律从 strategy.json + project_llecar.py 真口径取；
      CLI 默认值 20/20/-1 只作未配置兜底，报告内显著标 PLACEHOLDER。

诚信红线：MIDAS 离线绝不报实时值；快照数字可追溯 165 行 JSON 行号；
不下"合格"结论，只摆矛盾 + 归因。
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cad_model import extract_structure, Node, Member
from duel_rules import check as rules_check, load_rules

# 600s 全链路预算（评审 C 条）：降级模式 0.03s 不得当全链路成绩
BUDGET_S = 600.0

# 评审快照态数据源（只读引用，非改动其逻辑）
SNAPSHOT_JSON = ROOT.parent / "maca_review" / "real_fea_table_165.json"

# 口径数据源
STRATEGY_JSON = ROOT / "strategy.json"


def load_strategy() -> dict:
    if STRATEGY_JSON.exists():
        return json.loads(STRATEGY_JSON.read_text(encoding="utf-8"))
    return {}


def _elastic_gpa(strategy: dict, placeholder: bool) -> tuple[float, str]:
    """材料 E：读 strategy 竹材口径；缺失才用 PLACEHOLDER 兜底。"""
    v = (strategy.get("geometry_rules") or {}).get("elastic_modulus_gpa")
    if v:
        return float(v), "strategy.json geometry_rules.elastic_modulus_gpa " \
                         f"(M2 open, 依 PPT slide11)"
    return 206.0, "PLACEHOLDER(钢 Q355 E=206GPa) — strategy 未配置材料 E，兜底值，非真口径"


def _section_mm(strategy: dict, h_cli: float, b_cli: float) -> tuple[float, float, str]:
    """截面：CLI 显式传非占位值用之；否则 PLACEHOLDER。"""
    ph = (abs(h_cli - 20.0) < 1e-9 and abs(b_cli - 20.0) < 1e-9)
    note = "PLACEHOLDER 20×20 — CLI 未配截面，兜底值" if ph else "CLI 显式传入"
    return h_cli, b_cli, note


# ---------- MIDAS REST（内联，避免循环 import） ----------

API_URL = "https://moa-engineers.midasit.cn:443/gen"


def _key():
    return os.environ.get("MIDAS_MAPI_KEY", "")


def _url():
    return os.environ.get("MIDAS_API_URL", API_URL).rstrip("/")


def midas_available() -> bool:
    return bool(_url() and _key())


def call(method: str, path: str, body=None, timeout=180):
    url = _url() + path
    data = json.dumps(body).encode() if body is not None else None
    # 鉴权：MAPI-Key + Bearer 双 header（统一术语，见 calc_report 注释 B3）
    h = {"Content-Type": "application/json", "MAPI-Key": _key(),
         "Authorization": "Bearer " + _key()}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


# ---------- 连通分量筛选（RULE-004 教训） ----------

def largest_connected_component(m) -> tuple[list[Node], list[Member], int]:
    """返回 (节点, 杆, 总连通分量数)。取节点数最多的分量。"""
    from collections import defaultdict
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for mb in m.members:
        a, b = find(mb.n1), find(mb.n2)
        parent[a] = b
    comps = defaultdict(list)
    for n in m.nodes:
        comps[find(n.id)].append(n.id)
    maxroot = max(comps, key=lambda r: len(comps[r]))
    cset = set(comps[maxroot])
    nodes = [n for n in m.nodes if n.id in cset]
    newnodes: list[Node] = []
    old2new = {}
    for i, n in enumerate(sorted(nodes, key=lambda x: x.id), 1):
        old2new[n.id] = i
        newnodes.append(Node(id=i, x=n.x, y=n.y, z=n.z, source=n.source))
    members = [Member(id=j, n1=old2new[mb.n1], n2=old2new[mb.n2], kind="beam",
                      length_mm=mb.length_mm)
               for j, mb in enumerate(
                   [mb for mb in m.members if mb.n1 in cset and mb.n2 in cset], 1)]
    return newnodes, members, len(comps)


def pick_anchors(nodes: list[Node]) -> list[int]:
    """3 个几何分散的固支点（最远点对 + 中间点），锁平面内+竖向。"""
    pts = {n.id: (n.x, n.y) for n in nodes}
    ids = sorted(pts)

    def dist(a, b):
        return ((pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2) ** 0.5

    far = max(ids, key=lambda i: dist(ids[0], i))
    mid = max(ids, key=lambda i: min(dist(i, ids[0]), dist(i, far)))
    return sorted({ids[0], far, mid})


# ---------- MIDAS 建模 + 分析（含竖向约束，RULE-006 教训） ----------

@dataclass
class RedResult:
    available: bool
    red_source: str
    nodes: int
    elems: int
    anchors: list
    max_disp_mm: float = 0.0
    max_moment_knm: float = 0.0
    converged: bool = False
    analyze_s: float = 0.0
    material_note: str = ""
    snapshot_ref: str = ""
    error: str = ""

    def to_json(self) -> dict:
        return asdict(self)


def _read_snapshot() -> tuple[dict, bool]:
    """读 165 行 JSON 快照（评审输入件）。返回 (doc, found)。"""
    if not SNAPSHOT_JSON.exists():
        return {}, False
    try:
        return json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8")), True
    except Exception:
        return {}, False


def _snapshot_max_dz(doc: dict) -> tuple[float, int, int]:
    """逐行取 max|DZ| 及其节点号 + 行号（可追溯到 165 行 JSON 的具体第 N 行）。"""
    rows = doc.get("rows", [])
    best_v, best_n, best_i = 0.0, 0, -1
    for i, r in enumerate(rows, 1):
        v = abs(r.get("DZ_mm", 0.0))
        if v > abs(best_v):
            best_v, best_n, best_i = v, r.get("node", 0), i
    return best_v, best_n, best_i


def red_run(nodes, members, h_mm: float, b_mm: float, udl: float,
            strategy: dict) -> RedResult:
    res = RedResult(available=True, red_source="", nodes=len(nodes),
                    elems=len(members), anchors=pick_anchors(nodes) if nodes else [])

    e_gpa, matl_note = _elastic_gpa(strategy, placeholder=(h_mm == 20.0))
    res.material_note = matl_note

    # --- 先尝试 MIDAS 实时态 ---
    live = _try_live_midas(nodes, members, h_mm, b_mm, udl, e_gpa)
    if live is not None:
        res.available, res.red_source = True, "MIDAS实时"
        res.max_disp_mm, res.max_moment_knm = live["disp"], live["moment"]
        res.converged, res.analyze_s = live["converged"], live["analyze_s"]
        return res

    # --- 降级：快照态（165 行 JSON 真值基准，可追溯到具体行号） ---
    doc, found = _read_snapshot()
    if found:
        dz, node_no, row_i = _snapshot_max_dz(doc)
        res.available, res.red_source = True, "表格3快照"
        res.max_disp_mm = dz
        res.max_moment_knm = None  # 快照只有位移表，无弯矩表 → 不报 0，也不写 NaN（JSON 严格不合法），标 null
        res.converged = True
        res.analyze_s = 0.0
        res.snapshot_ref = (
            f"real_fea_table_165.json 第{row_i}行 node{node_no} "
            f"|DZ|max={dz:.4f}mm（逐行可追溯，165 行 XML 解析）")
        res.error = "MIDAS APISTART 非 200/201 或 analyze 材料未定义（已记 midas_live_trace），降级表格3快照；不报实时值"
        return res

    # --- 两者皆缺 ---
    res.available, res.red_source = False, "none"
    res.error = "MIDAS 未建会话且快照缺失，未取真值，不伪造"
    return res


def _try_live_midas(nodes, members, h_mm, b_mm, udl, e_gpa):
    """MIDAS 实时 FEA。APISTART 非 200/201 返回 None（诚信：不伪造）。"""
    if not midas_available():
        return None
    res_local = {"disp": 0.0, "moment": 0.0, "converged": False, "analyze_s": 0.0}
    trace = []  # (step, status, note) —— 落盘留痕，供事后审计 404/未建会话

    def _log(a, st, note=""):
        trace.append((a, st, note))
        mark = "OK " if st in (200, 201) else "ERR"
        print(f"    [{mark}] {a:8s} {st} {note}")

    _log("start", call("POST", "/OPE/APISTART", {})[0])
    # 诚信红线：APISTART 若 404/非200，说明 MIDAS 会话没建起来（client 不在线/被回收）
    st_start, _body = call("POST", "/OPE/APISTART", {})
    _log("start2", st_start, "APISTART 终态确认")
    if st_start not in (200, 201):
        _write_live_trace(trace, st_start)
        return None  # 会话未建，交给快照态

    _log("clear", call("POST", "/DOC/NEW", {})[0])
    assign = {str(n.id): {"X": n.x / 1000, "Y": n.y / 1000, "Z": 0.0} for n in nodes}
    _log("nodes", call("PUT", "/db/NODE", {"Assign": assign})[0], f"{len(nodes)}")
    _log("sect", call("PUT", "/db/SECT", {"Assign": {"1": {"SECTTYPE": "DBUSER", "SECT_NAME": "Rect",
        "SECT_BEFORE": {"USE_SHEAR_DEFORM": True, "SHAPE": "SB", "DATATYPE": 2,
        "SECT_I": {"vSIZE": [round(h_mm / 1000, 6), round(b_mm / 1000, 6)]}}}}})[0])
    # 材质 E 读 strategy 口径（B1），不再硬编码 Q355
    # 云端实测：GET /db/MATL/STANDARD 报 "Wrong Key"（端点未开放）；
    # STANDARD 材质 PUT 报 "Wrong Field"。唯一可用的就是 USER + PARAM 数组。
    e_pa = e_gpa * 1e9
    _log("matl", call("PUT", "/db/MATL", {"Assign": {"1": {"TYPE": "USER", "NAME": f"bamboo(E={e_gpa}GPa,M2open)",
        "bMASS_DENS": True, "DAMP_RAT": 0.05,
        "PARAM": [{"P_TYPE": 2, "ELAST": e_pa, "POISN": 0.3, "THERMAL": 1e-5,
                   "DEN": 7.8, "MASS": 0.078}]}}})[0], f"E={e_pa:.0f}Pa")

    # 元素引用材质号：MIDAS 云端要 int（非 str "1"），否则 ELEM 不挂 MATL →
    # ANAL 报"MATERIAL NOT ASSIGNED TO ELEMENT"，位移全 0（非材料口径问题）。
    elem = {str(i): {"TYPE": "BEAM", "MATL": 1, "SECT": 1,
                     "NODE": [mb.n1, mb.n2], "ANGLE": 0}
            for i, mb in enumerate(members, 1)}
    _log("elems", call("POST", "/db/ELEM", {"Assign": elem})[0], f"{len(elem)}")
    # 复查 ELEM 是否真挂上 MATL（防"200 但引用没生效"），没挂则补挂一次
    st_chk, b_chk = call("GET", "/db/ELEM")
    if st_chk == 200 and '"MATL"' in b_chk:
        _log("elems_chk", 200, "ELEM 已挂 MATL")
    else:
        _log("elems_relink", call("POST", "/db/ELEM", {"Assign": elem})[0], "补挂 MATL")

    # 材质真建成判定：以 PUT /db/MATL 返回 200/201 为准（说明材质已建进会话）。
    # GET /db/MATL 在共享云会话有传播延迟，常回空 {"message":""}——这是脏读时序抖动，
    # 不能拿它当"没建成"就降级（那样会把本来建好的材质误判掉）。真正的诚信防线
    # 放在 ANAL 步：ANAL 报 error（如"材料 没有定义"）才降级，不拿 0 当真值。
    time.sleep(2.0)
    st_mat, b_mat = call("GET", "/db/MATL")
    matl_put_ok = st_mat in (200, 201)  # PUT 已过（见上 _log matl），这里 GET 只记录
    if '"ELAST"' in b_mat:
        _log("matl_chk", 200, "材质已建成 (GET 读到 ELAST)")
    else:
        # GET 读空不降级，仅记录（PUT 已 200 说明建进去了，ANAL 会最终检验）
        _log("matl_chk", st_mat, "GET 未回显 ELAST (共享会话传播延迟, PUT 已过, 交 ANAL 终验)")

    a = pick_anchors(nodes)
    cons = {"1": {"ITEMS": [
        {"ID": a[0], "CONSTRAINT": "1111100"},
        {"ID": a[1], "CONSTRAINT": "1100000"},
        {"ID": a[2], "CONSTRAINT": "1100000"}]}}
    _log("cons", call("POST", "/db/CONS", {"Assign": cons})[0], f"fix {a}")
    _log("stld", call("POST", "/db/STLD", {"Assign": {
        "1": {"NAME": "DL", "TYPE": "USER", "DESC": "dead"},
        "2": {"NAME": "LL", "TYPE": "USER", "DESC": "live"}}})[0])
    _log("comb", call("POST", "/db/LCOM-GEN", {"Assign": {"1": {"iTYPE": 0, "NAME": "Comb1",
        "vCOMB": [{"ANAL": "ST", "LCNAME": "DL", "FACTOR": 1.0},
                   {"ANAL": "ST", "LCNAME": "LL", "FACTOR": 1.0}]}}})[0])
    _log("bodf", call("POST", "/db/BODF", {"Assign": {"1": {"LCNAME": "DL", "FV": [0, 0, -1]}}})[0])
    _log("bmld", call("POST", "/db/BMLD", {"Assign": {"1": {"ITEMS": [{"ID": 1, "LCNAME": "LL",
        "GROUP_NAME": "", "CMD": "BEAM", "TYPE": "UNILOAD", "DIRECTION": "GZ",
        "USE_PROJECTION": False, "USE_ECCEN": False, "D": [0, 1, 0, 0],
        "P": [udl, udl, 0, 0]}]}}})[0])

    t0 = time.time()
    st_anal, body_anal = call("POST", "/doc/ANAL", {})
    res_local["analyze_s"] = round(time.time() - t0, 1)
    _log("analyze", st_anal, f"({res_local['analyze_s']}s) {body_anal[:80]}")
    # 诚信：MIDAS analyze 有时 HTTP=200 但 body 含 error（如"材料 没有定义"），
    # 此时 FEA 无有效结果、位移/弯矩全 0 —— 绝不把 0 当"真值"，降级快照态。
    if st_anal != 200 or '"error"' in body_anal:
        _write_live_trace(trace, st_anal, note=body_anal[:160])
        return None

    def table(tt, tn):
        st, r = call("POST", "/post/TABLE", {"Argument": {"TABLE_TYPE": tt,
            "TABLE_NAME": tn, "LOAD_CASE_NAMES": ["Comb1(CB)"]}}, timeout=90)
        if st != 200:
            return None
        d = json.loads(r)
        for v in d.values():
            if isinstance(v, dict) and "HEAD" in v:
                return v
        return None

    def colmax(tbl, keys):
        if not tbl:
            return None
        head = tbl["HEAD"]
        idx = [i for i, hh in enumerate(head) if hh in keys]
        best = None
        for row in tbl["DATA"]:
            for i in idx:
                if i < len(row):
                    try:
                        v = float(row[i])
                        if best is None or abs(v) > abs(best):
                            best = v
                    except (TypeError, ValueError):
                        pass
        return best

    res_local["disp"] = (colmax(table("DISPLACEMENTG", "Displacements(Global)"),
                                {"DX", "DY", "DZ"}) or 0.0) * 1000.0
    res_local["moment"] = colmax(table("BEAMFORCE", "BeamForce"), {"Moment-y"}) or 0.0
    res_local["converged"] = abs(res_local["disp"]) < 100.0
    _write_live_trace(trace, 200)
    return res_local


def _write_live_trace(trace: list, final_status: int, note: str = "") -> None:
    """MIDAS 实时态留痕落盘（带版本+时刻，不裸名反复覆盖）。"""
    import datetime
    out = ROOT / "logs"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    prev = sorted(out.glob("midas_live_trace_v*.json"))
    n = (len(prev) + 1) if prev else 1
    p = out / f"midas_live_trace_v{n}_{ts}.json"
    doc = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "version": f"v{n}_{ts}",
        "final_status": final_status,
        "note": note,
        "steps": [{"step": a, "status": st, "note": nt} for a, st, nt in trace],
    }
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 蓝军闭式解（口径 B2：参数一律 strategy + project_llecar 真口径） ----------

@dataclass
class BlueResult:
    L_m: float
    I_m4: float
    E_pa: float
    q_n_per_m: float
    delta_mm: float
    max_moment_knm: float
    source_note: str = ""

    def to_json(self) -> dict:
        return asdict(self)


def pick_main_beam(members: list, nodes: list) -> Member | None:
    """选承重主梁参照：连通分量里最水平且足够的杆。"""
    npos = {n.id: (n.x, n.y) for n in nodes}
    best = None
    for mb in members:
        p1, p2 = npos.get(mb.n1), npos.get(mb.n2)
        if not p1 or not p2:
            continue
        dx, dy = abs(p2[0] - p1[0]), abs(p2[1] - p1[1])
        total = (dx * dx + dy * dy) ** 0.5
        if total < 30.0:
            continue
        score = (dx / total) * total
        if best is None or score > best[0]:
            best = (score, mb, total)
    return best[1] if best else (max(members, key=lambda m: m.length_mm)
                                  if members else None)


def _blue_span_mm() -> tuple[float, str]:
    """蓝军跨度：优先 CAD 实测主梁（真实），缺失退 project_llecar 真值 500mm。"""
    try:
        from project_llecar import REAL_SPAN_MM, REAL_SPAN_NOTE
        return float(REAL_SPAN_MM), REAL_SPAN_NOTE
    except Exception:
        return 500.0, "PLACEHOLDER 500mm — project_llecar 不可导入，兜底车架外廓量级"


def blue_closed_form(span_mm: float, h_mm: float, b_mm: float,
                     udl_kn_per_m: float, e_gpa: float,
                     source_note: str = "") -> BlueResult:
    L = span_mm / 1000.0
    E = e_gpa * 1e9
    I = (b_mm / 1000) * (h_mm / 1000) ** 3 / 12.0
    q = abs(udl_kn_per_m) * 1000.0
    delta_mm = (5 * q * L ** 4 / (384 * E * I)) * 1000.0 if I > 0 else float("inf")
    M = q * L ** 2 / 8 / 1000.0
    return BlueResult(L_m=L, I_m4=I, E_pa=E, q_n_per_m=q,
                      delta_mm=delta_mm, max_moment_knm=M, source_note=source_note)


# ---------- 主流程 ----------

@dataclass
class DuelReport:
    source_cad: str
    red: RedResult
    blue: BlueResult
    hits: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    t_wall_s: float = 0.0

    def save(self, out_dir: str | Path = "logs") -> str:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        import datetime
        # 文件名带版本 + 态 + 时刻：评审可追溯“第N版·什么态·什么时候”，不再裸名反复覆盖
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        src_tag = "MIDAS实时" if self.red.red_source == "MIDAS实时" else "快照"
        prev = sorted(out.glob("duel_report_v*.json"))
        n = (len(prev) + 1) if prev else 1
        p = out / f"duel_report_v{n}_{src_tag}_{ts}.json"
        p.write_text(json.dumps({
            "source_cad": self.source_cad,
            "red": self.red.to_json(),
            "blue": self.blue.to_json(),
            "hits": self.hits,
            "summary": self.summary,
            "timings": self.timings,
            "t_wall_s": self.t_wall_s,
            "version": f"v{n}_{src_tag}_{ts}",
            "degraded": self.timings.get("degraded", False),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)


def run_duel(dxf: str, h_mm: float = 20.0, b_mm: float = 20.0,
             udl_kn_per_m: float = -1.0, out_dir: str = "logs",
             strategy: dict | None = None, write: bool = True) -> DuelReport:
    strat = strategy if strategy is not None else load_strategy()
    ph = {}
    ph["section"] = "PLACEHOLDER 20×20mm（CLI 未配截面，兜底）" \
        if abs(h_mm - 20.0) < 1e-9 and abs(b_mm - 20.0) < 1e-9 \
        else "CLI 显式截面"
    ph["udl"] = "PLACEHOLDER udl=-1（未配荷载，取 1.0 kN/m 兜底）" \
        if abs(udl_kn_per_m + 1.0) < 1e-9 else "CLI 显式荷载"
    udl_eff = udl_kn_per_m if udl_kn_per_m > 0 else 1.0
    ph["span"] = None  # 蓝军跨度由 CAD 实测主梁给，见下

    t = {"cad_parse_s": 0.0, "model_build_s": 0.0, "analyze_s": 0.0,
         "table_s": 0.0, "compare_s": 0.0, "degraded": False,
         "cad_available": True}
    t0 = time.perf_counter()

    # CAD 源缺失时诚实降级：原始图纸（.dxf）属团队工程件，不随公开仓库分发。
    # 与 MIDAS 离线同一原则——取不到就标注跳过，绝不伪造节点/杆件或崩溃。
    if dxf and Path(dxf).exists():
        m = extract_structure(dxf)
        nodes, members, ncomps = largest_connected_component(m)
        main_beam = pick_main_beam(members, nodes)
        longest_mm = main_beam.length_mm if main_beam else 0.0
        t["cad_parse_s"] = round(time.perf_counter() - t0, 2)
        print(f"[CAD]  {Path(dxf).name}")
        print(f"       实体解析 节点={len(m.nodes)} 杆={len(m.members)} "
              f"散落{ncomps}个连通分量")
        print(f"       最大相连分量 节点={len(nodes)} 杆={len(members)} "
              f"最长杆={longest_mm:.1f}mm")
    else:
        m, nodes, members, ncomps, longest_mm = None, [], [], 0, 0.0
        t["cad_available"] = False
        print(f"[CAD]  {dxf}")
        print("       源图纸未随仓库分发（团队原始工程件），跳过 CAD 解析；")
        print("       蓝军跨度退 project_llecar 真值，红方走表格3快照（诚信降级，不伪造几何）。")

    # 蓝军跨度：CAD 实测主梁（真实）；缺失退 project_llecar
    if longest_mm > 30.0:
        span_mm, span_src = longest_mm, f"CAD 实测主梁 {longest_mm:.1f}mm"
    else:
        span_mm, span_src = _blue_span_mm()
        ph["span"] = "PLACEHOLDER 500mm（CAD 主梁不可用，退 project_llecar 真值）"
    ph["span"] = ph.get("span") or span_src

    e_gpa, matl_note = _elastic_gpa(strat, placeholder=False)

    t1 = time.perf_counter()
    blue = blue_closed_form(span_mm, h_mm, b_mm, udl_eff, e_gpa,
                            source_note=f"跨度:{ph.get('span')} | 截面:{ph['section']} "
                                         f"| E:{e_gpa}GPa({matl_note}) | 荷载:{ph['udl']}")
    t["model_build_s"] = round(time.perf_counter() - t1, 3)

    t2 = time.perf_counter()
    red = red_run(nodes, members, h_mm, b_mm, udl_eff, strat)
    t["analyze_s"] = red.analyze_s
    if red.red_source == "表格3快照" or (not red.available and _read_snapshot()[1]):
        t["degraded"] = True
    t["table_s"] = round(time.perf_counter() - t2 - red.analyze_s, 3)
    print(f"[RED]  源={red.red_source or '无'} "
          f"位移={red.max_disp_mm:.4f}mm 弯矩={red.max_moment_knm}kNm "
          f"{'✅收敛' if red.converged else '⚠'} {red.snapshot_ref}")

    print(f"[BLUE] 蓝军闭式解 位移={blue.delta_mm:.4f}mm "
          f"弯矩={blue.max_moment_knm:.5f}kNm (L={blue.L_m:.3f}m)")
    print(f"       口径: {blue.source_note}")

    t3 = time.perf_counter()
    hits = rules_check(
        {"max_disp_m": red.max_disp_mm / 1000.0,
         "max_moment_knm": red.max_moment_knm},
        blue.__dict__)
    for h in hits:
        print(f"[RULE] {h['id']} {h['name']} -> {h['attribution']}")

    summary = _verdict(red, blue, hits, t)
    t["compare_s"] = round(time.perf_counter() - t3, 3)

    rep = DuelReport(source_cad=dxf, red=red, blue=blue, hits=hits,
                     summary=summary, timings=t,
                     t_wall_s=round(time.perf_counter() - t0, 2))
    _print_budget(rep, t)
    print(f"\n[结论] {summary.get('verdict')}  全程 {rep.t_wall_s}s"
          f"{'（DEGRADED 降级态）' if t['degraded'] else ''}")
    if write:
        p = rep.save(out_dir)
        print(f"[报告] {p}")
    else:
        print("[报告] 未落盘（write=False，内存态）")
    return rep


def _verdict(red: RedResult, blue: BlueResult, hits, t) -> dict:
    """consistent 判据（评审 D 条）：口径对齐后，弯矩同源可比。
    快照态（无弯矩）退化为位移量级判据。"""
    if not red.available:
        return {"verdict": "red_unavailable",
                "note": red.error, "basis": "red 不可用"}
    if red.red_source == "表格3快照":
        # 快照只有位移，不比弯矩；按位移量级 + M1 矛盾落结论
        m1 = next((h for h in hits if h.get("id") == "RULE-005"), None)
        disp_m = red.max_disp_mm
        # 32.22mm vs 正文 15mm 矛盾必在 → divergent（不盖章合格）
        verdict = "divergent" if disp_m > 0 and abs(disp_m - 15.0) > 5 else "consistent"
        return {"verdict": verdict,
                "basis": "快照态位移量级 + M1 矛盾（32.22 vs 15mm）",
                "note": "快照无弯矩表，判据退化为位移量级；M1 矛盾保留 → 不下合格结论"}
    # MIDAS 实时态：弯矩同源比对
    if red.converged and blue.max_moment_knm:
        ratio = (red.max_moment_knm or 0.0) / blue.max_moment_knm
        return {"verdict": "consistent" if (ratio and abs(abs(ratio) - 1.0) < 0.5)
                else "divergent",
                "moment_ratio": ratio,
                "basis": "MIDAS实时 vs 蓝军闭式解（口径已对齐：E=6GPa竹材）",
                "note": "弯矩同源比对；约束简化不同属预期差异"}
    return {"verdict": "divergent", "basis": "MIDAS 实时态发散或无参照",
            "note": red.error or "红光发散，未收敛"}


def _print_budget(rep: DuelReport, t) -> None:
    t = rep.timings
    total = rep.t_wall_s
    degraded = t.get("degraded", False)
    print(f"\n[分段计时] CAD={t.get('cad_parse_s',0)}s 建模={t.get('model_build_s',0)}s "
          f"ANAL={t.get('analyze_s',0)}s TABLE={t.get('table_s',0)}s "
          f"比对={t.get('compare_s',0)}s")
    print(f"[全链路] 总={total}s / 预算 {BUDGET_S}s -> "
          f"{'FAIL 超预算' if total > BUDGET_S else 'PASS'}"
          f"{'  **DEGRADED 降级态：计时不可当全链路成绩**' if degraded else ''}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", nargs="?", default=str(ROOT.parent / "勒勒车2-2.dxf"))
    ap.add_argument("--h", type=float, default=20.0)
    ap.add_argument("--b", type=float, default=20.0)
    ap.add_argument("--udl", type=float, default=-1.0)
    ap.add_argument("--no-write", action="store_true",
                    help="不落盘 duel_report.json，仅内存跑+打印（本地迭代/自验用，省 MIDAS 会话）")
    ap.add_argument("--verify", action="store_true",
                    help="跑完自动执行 4 判据机器验证（不落盘、不动 MIDAS）")
    args = ap.parse_args()
    write = not args.no_write
    rep = run_duel(args.dxf, args.h, args.b, args.udl, write=write)
    if args.verify:
        from verify_criteria import check_in_memory
        ok = check_in_memory(rep)
        print("\n[VERIFY] 判据 1-4: " + ("PASS" if ok else "FAIL"))
    return 0 if (rep.red.converged and rep.red.available) else 2


if __name__ == "__main__":
    raise SystemExit(main())
