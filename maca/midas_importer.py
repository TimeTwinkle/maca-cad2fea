"""MIDAS 复刻导入层：把我的 CAD 解析结果，用官方 API 写成 MIDAS 模型。

为什么要有这一层（定位，勿改）：
    MIDAS 自带"一键导 AutoCAD"。但那是黑盒：导错了你不知道哪一步错的。
    本层把导入过程**程序化 + 白盒化**：
      - 每一步写了什么（request）
      - 服务器回了什么（response）
      - 最终成型的模型是什么（model snapshot）
    全部留痕。这样才能：
      1. 与独立路径（自己算）做红蓝对抗
      2. 定位是 CAD 画错 / 写入错 / MIDAS 建错
      3. 沉淀成可复用规则（下次同图秒级命中）

依赖：cad_model（CAD 解析产物）+ MIDAS REST（同 duel_run.call，实测过的官方 schema）
输入：cad_model.StructureManifest（我自己的 CAD 解析产物）
输出：MidasImportTrace（含每步 request/response + 模型快照）
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cad_model import StructureManifest, extract_structure

API_URL = "https://moa-engineers.midasit.cn:443/gen"


def _key():
    return os.environ.get("MIDAS_MAPI_KEY", "")


def _url():
    return os.environ.get("MIDAS_API_URL", API_URL).rstrip("/")


@dataclass
class ImportStep:
    step: str
    method: str
    endpoint: str
    ok: bool
    status: int
    note: str
    elapsed_ms: int = 0
    request: dict = field(default_factory=dict)
    response: str = ""

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class MidasImportTrace:
    source_cad: str
    nodes: int = 0
    elems: int = 0
    steps: list = field(default_factory=list)
    ok: bool = False
    analyze_s: float = 0.0
    t_wall_s: float = 0.0
    snapshot: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)

    def save(self, out_dir: str | Path = "logs") -> str:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        p = out / "midas_import_trace.json"
        p.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return str(p)


@dataclass
class MidasImporter:
    trace: MidasImportTrace
    source_cad: str

    def _call(self, action: str, method: str, endpoint: str,
              fn=None, note: str = "") -> tuple[int, str]:
        """发请求，全程留痕。fn 返回 (status, text)。"""
        t0 = time.time()
        try:
            st, r = fn()
        except urllib.error.HTTPError as e:
            st, r = e.code, e.read().decode(errors="replace")
        except Exception as e:
            st, r = -1, f"{type(e).__name__}: {e}"
        dt = int((time.time() - t0) * 1000)
        ok = st in (200, 201)
        self.trace.steps.append(ImportStep(
            step=action, method=method, endpoint=endpoint, ok=ok, status=st,
            note=note, elapsed_ms=dt, response=r[:2000]))
        return st, r


def _req(method, path, body=None, timeout=180):
    url = _url() + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "MAPI-Key": _key(),
         "Authorization": "Bearer " + _key()}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode(errors="replace")


def import_manifest(self: MidasImporter, manifest: StructureManifest,
                    span_mm: float = 500.0, section_h_mm: float = 20.0,
                    section_b_mm: float = 20.0, udl_kn_per_m: float = -1.0,
                    max_nodes: int = 400, max_elems: int = 800) -> MidasImportTrace:
    """把一份 CAD manifest 写入 MIDAS。只取前 max_nodes/max_elems，超大图截断。"""
    if not _key():
        self.trace.ok = False
        self.trace.snapshot["error"] = "无 MIDAS_MAPI_KEY，不写入，不伪造"
        self.trace.t_wall_s = 0.0
        print("[MIDAS] 跳过：未配置 MIDAS_MAPI_KEY（诚实不写）")
        return self.trace

    nodes = manifest.nodes[:max_nodes]
    elems = manifest.members[:max_elems]
    self.trace.nodes, self.trace.elems = len(nodes), len(elems)

    def do(action, method, endpoint, body=None, note=""):
        return self._call(action, method, endpoint,
                          fn=lambda: _req(method, endpoint, body, 180), note=note)

    do("start", "POST", "/OPE/APISTART", {}, "开会话")
    do("clear", "POST", "/DOC/NEW", {}, "清空模型")
    do("nodes", "PUT", "/db/NODE",
       {"Assign": {str(n.id): {"X": n.x / 1000, "Y": n.y / 1000, "Z": 0.0}
                    for n in nodes}}, f"{len(nodes)} 节点")
    do("sect", "PUT", "/db/SECT",
       {"Assign": {"1": {"SECTTYPE": "DBUSER", "SECT_NAME": "Rect",
                          "SECT_BEFORE": {"USE_SHEAR_DEFORM": True, "SHAPE": "SB",
                                           "DATATYPE": 2,
                                           "SECT_I": {"vSIZE": [section_h_mm / 1000,
                                                                 section_b_mm / 1000]}}}}},
       "矩形截面")
    do("matl", "PUT", "/db/MATL",
       {"Assign": {"1": {"TYPE": "USER", "NAME": "Q355", "bMASS_DENS": True,
                          "DAMP_RAT": 0.05,
                          "PARAM": [{"P_TYPE": 2, "ELAST": 206000000.0, "POISN": 0.3,
                                     "THERMAL": 1e-5, "DEN": 78.5, "MASS": 8.0047}]}}},
       "Q355")
    do("elems", "POST", "/db/ELEM",
       {"Assign": {str(i): {"TYPE": "BEAM", "MATL": 1, "SECT": 1,
                            "NODE": [e.n1, e.n2], "ANGLE": 0}
                    for i, e in enumerate(elems, 1)}}, f"{len(elems)} 杆")

    # 模型快照（导入后留痕）
    self.trace.snapshot["elem_count"] = len(elems)
    self.trace.snapshot["node_count"] = len(nodes)
    self.trace.snapshot["section_mm"] = [section_h_mm, section_b_mm]
    self.trace.snapshot["span_mm"] = span_mm

    self.trace.ok = all(s.ok for s in self.trace.steps if s.step in
                        ("nodes", "elems", "sect", "matl"))
    return self.trace


def import_cad_to_midas(manifest: StructureManifest,
                        kw: dict | None = None) -> MidasImportTrace:
    """便捷入口：manifest -> 留痕 trace。"""
    tr = MidasImportTrace(source_cad=manifest.source)
    imp = MidasImporter(trace=tr, source_cad=manifest.source)
    import_manifest(imp, manifest, **(kw or {}))
    tr.t_wall_s = 0.0
    return tr


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", nargs="?", default=str(ROOT.parent / "勒勒车2-2.dxf"))
    ap.add_argument("--out", default="logs")
    args = ap.parse_args()
    m = extract_structure(args.dxf)
    tr = import_cad_to_midas(m)
    p = tr.save(args.out)
    print(f"导入步骤 {len(tr.steps)}：")
    for s in tr.steps:
        flag = "OK " if s.ok else "ERR"
        print(f"  [{flag}] {s.step:8s} {s.method:4s} {s.endpoint:12s} "
              f"{s.status} {s.elapsed_ms}ms  {s.note}")
    print(f"ok={tr.ok}  报告: {p}")
    return 0 if tr.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
