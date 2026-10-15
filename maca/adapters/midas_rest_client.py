"""MIDAS Gen NX —— 官方 Open API（REST）直连层。

定位（重要，勿改）：
    本模块是「AutoCAD → MIDAS 复刻导入」的**写入端**。
    它不是要替代 MIDAS 的一键导入，而是把导入过程**程序化 + 白盒化**：
    每一步写什么、写成了什么，都有独立记录，从而能与独立路径做红蓝对抗。

真实调用契约（按实测 2025 官方 MAPI，非猜测）：
    鉴权头  MAPI-Key: <JWT>
    中国区  https://moa-engineers.midasit.cn:443/gen
    流程    /OPE/APISTART → /db/* 建模 → /doc/ANAL → /post/TABLE → /OPE/APIEND

关键实测修正（覆盖早期误写）：
    - 没有 /db/RESULT；结果统一走 POST /post/TABLE（Argument.TABLE_TYPE 区分）
    - 梁单元用 TYPE + NODE:[n1,n2]，不是 Node1/Node2
    - 截面用 SECTTYPE/SECT_BEFORE/SECT_I.vSIZE=[H_m, B_m]，不是平铺 b/h
    - 约束用 7 位 CONSTRAINT 码
    - BMLD 依赖其 LCNAME 指向的工况必须已在 /db/STLD 建好

凭证只走环境变量（绝不写死进代码）：
    MIDAS_API_URL    https://moa-engineers.midasit.cn:443/gen
    MIDAS_MAPI_KEY   <MAPI-Key>
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_E = float("nan")


def _api_url() -> str:
    return os.environ.get("MIDAS_API_URL", "").rstrip("/")


def _mapi_key() -> str:
    return os.environ.get("MIDAS_MAPI_KEY", "")


def is_available() -> bool:
    return bool(_api_url() and _mapi_key())


def _auth_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "MAPI-Key": _mapi_key(),
        "Authorization": f"Bearer {_mapi_key()}",
    }


def MidasAPI(method: str, command: str, body: dict | None = None, timeout: int = 30) -> dict:
    """官方调用契约的 REST 实现：MidasAPI("PUT", "/db/NODE", {...})。"""
    url = f"{_api_url()}{command}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode(errors="replace") or "{}"
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw, "http": resp.status}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace") or ""
        try:
            return {"http": e.code, "error": json.loads(raw)}
        except Exception:
            return {"http": e.code, "error": {"raw": raw[:500]}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


def is_error(resp: dict) -> bool:
    return isinstance(resp, dict) and ("error" in resp or "http" in resp)


def describe() -> str:
    if is_available():
        return f"✅ 已配置 MAPI 直连 {_api_url()}（无第三方中转）"
    return "⚪ 未配置 MIDAS_API_URL / MIDAS_MAPI_KEY → 此引擎为占位"


# ---------------- 会话 ----------------

def api_start() -> dict:
    return MidasAPI("POST", "/OPE/APISTART", {})


def api_end() -> dict:
    return MidasAPI("POST", "/OPE/APIEND", {})


def set_units(force: str = "KN", dist: str = "M") -> dict:
    return MidasAPI("PUT", "/db/UNIT",
                    {"Assign": {"1": {"FORCE": force, "DIST": dist}}})


# ---------------- 建模（复刻导入的写入端） ----------------

def put_nodes(nodes: list[tuple[float, float, float]]) -> tuple[dict, dict]:
    """写入节点。nodes = [(x_m, y_m, z_m), ...]（1-based 编号）。

    返回 (resp, assign) —— assign 是实际发出的 Assign 体，用于审计比对。
    """
    assign = {str(i + 1): {"X": float(x), "Y": float(y), "Z": float(z)}
              for i, (x, y, z) in enumerate(nodes)}
    body = {"Assign": assign}
    return MidasAPI("PUT", "/db/NODE", body), body


def put_rect_section(sid: int, h_mm: float, b_mm: float, name: str = "Rectangular") -> tuple[dict, dict]:
    """矩形截面（实测 schema：vSIZE=[H_m, B_m]，单位米）。"""
    body = {"Assign": {str(sid): {
        "SECTTYPE": "DBUSER", "SECT_NAME": name,
        "SECT_BEFORE": {
            "USE_SHEAR_DEFORM": True, "SHAPE": "SB", "DATATYPE": 2,
            "SECT_I": {"vSIZE": [round(h_mm / 1000.0, 6), round(b_mm / 1000.0, 6)]}}}}}
    return MidasAPI("PUT", "/db/SECT", body), body


def put_user_material(mid: int, name: str, elast: float, poissn: float,
                      den: float, thermal: float = 1e-5) -> tuple[dict, dict]:
    """USER 材料（kN-m 制：ELAST 用 kPa）。"""
    body = {"Assign": {str(mid): {
        "TYPE": "USER", "NAME": name, "bMASS_DENS": True, "DAMP_RAT": 0.05,
        "PARAM": [{"P_TYPE": 2, "ELAST": elast, "POISN": poissn,
                   "THERMAL": thermal, "DEN": den, "MASS": den / 9.80665}]}}}
    return MidasAPI("POST", "/db/MATL", body), body


def put_beam_elements(elems: list[tuple[int, int]], sect: int = 1, matl: int = 1) -> tuple[dict, dict]:
    """梁单元（实测 schema：TYPE + NODE:[n1,n2]）。"""
    assign = {}
    for i, (n1, n2) in enumerate(elems, start=1):
        assign[str(i)] = {"TYPE": "BEAM", "MATL": matl, "SECT": sect,
                          "NODE": [int(n1), int(n2)], "ANGLE": 0}
    body = {"Assign": assign}
    return MidasAPI("POST", "/db/ELEM", body), body


def put_constraints(items: list[dict]) -> tuple[dict, dict]:
    """约束。items = [{"ID": node, "CONSTRAINT": "1111000"}, ...]（7 位码）。"""
    body = {"Assign": {str(i + 1): {"ITEMS": [it]} for i, it in enumerate(items)}}
    return MidasAPI("POST", "/db/CONS", body), body


def put_static_load_cases(cases: list[tuple[str, str]]) -> tuple[dict, dict]:
    """工况。cases = [("DL","dead"), ("LL","live")]。

    重要：BMLD 等荷载依赖工况先存在，否则服务器回 Wrong Field。
    """
    assign = {str(i + 1): {"NAME": nm, "TYPE": "USER", "DESC": desc}
              for i, (nm, desc) in enumerate(cases)}
    body = {"Assign": assign}
    return MidasAPI("POST", "/db/STLD", body), body


def put_self_weight(lcname: str = "DL", fv=(0, 0, -1)) -> tuple[dict, dict]:
    body = {"Assign": {"1": {"LCNAME": lcname, "FV": list(fv)}}}
    return MidasAPI("POST", "/db/BODF", body), body


def put_beam_udl(lcname: str, p_kn_per_m: float) -> tuple[dict, dict]:
    """梁均布荷载（实测 4 元素 D/P 数组）。"""
    body = {"Assign": {"1": {"ITEMS": [{
        "ID": 1, "LCNAME": lcname, "GROUP_NAME": "",
        "CMD": "BEAM", "TYPE": "UNILOAD", "DIRECTION": "GZ",
        "USE_PROJECTION": False, "USE_ECCEN": False,
        "D": [0, 1, 0, 0], "P": [p_kn_per_m, p_kn_per_m, 0, 0]}]}}}
    return MidasAPI("POST", "/db/BMLD", body), body


def put_combination(name: str, items: list[tuple[str, str, float]]) -> tuple[dict, dict]:
    """荷载组合。items = [("ST","DL",1.0), ("ST","LL",1.0)]。"""
    body = {"Assign": {"1": {"iTYPE": 0, "NAME": name,
        "vCOMB": [{"ANAL": a, "LCNAME": lc, "FACTOR": f} for a, lc, f in items]}}}
    return MidasAPI("POST", "/db/LCOM-GEN", body), body


# ---------------- 分析与取结果 ----------------

def analyze() -> dict:
    """触发分析（实测：POST /doc/ANAL，空体）。"""
    return MidasAPI("POST", "/doc/ANAL", {})


def post_table(table_type: str, load_case_names: list[str], table_name: str = "") -> dict:
    """结果表（实测：POST /post/TABLE）。"""
    return MidasAPI("POST", "/post/TABLE", {"Argument": {
        "TABLE_TYPE": table_type,
        "TABLE_NAME": table_name or table_type,
        "LOAD_CASE_NAMES": load_case_names,
    }})


def extract_table(resp: dict) -> dict | None:
    """从 /post/TABLE 响应里挑出 {HEAD, DATA} 表。"""
    if not isinstance(resp, dict):
        return None
    for v in resp.values():
        if isinstance(v, dict) and "HEAD" in v and "DATA" in v:
            return v
    return None


def max_of(resp: dict, keys: list[str]) -> float | None:
    """取指定列的最大绝对值（官方值都是字符串）。"""
    tbl = extract_table(resp)
    if not tbl:
        return None
    head = tbl["HEAD"]
    idx = {k: i for i, k in enumerate(head) if k in keys}
    if not idx:
        return None
    best = None
    for row in tbl["DATA"]:
        for k, i in idx.items():
            if i >= len(row):
                continue
            try:
                v = float(row[i])
            except (TypeError, ValueError):
                continue
            if best is None or abs(v) > abs(best):
                best = v
    return best
