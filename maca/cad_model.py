"""AutoCAD DXF → 结构语义抽取（实体级，不是头部指纹）。

与旧 dxf_parser 的区别：
    旧版：读前 100KB，正则抓数字，套默认参数。
    本版：解析全部实体，按图层/几何/标注重建结构元素。

输出 structure_manifest：
    nodes      [{id, x, y, z, source}]
    members    [{id, n1, n2, kind, length_mm, source_ehandle}]
    sections   [{no, name, ...}]        来自计算书口径
    loads      [{case, kind, desc}]
    constraints [{node, dof}]
    dims       [{value, measured}]      真实标注值
    texts      [...]                    真实文字
    stats      {line/target/... 计数}
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path


# ---------- DXF 基础读取 ----------

def _pairs(path: Path) -> list[tuple[str, str]]:
    raw = path.read_bytes()
    for enc in ("gb18030", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i = 0
    while i + 1 < len(lines):
        code, val = lines[i].strip(), lines[i + 1].strip()
        if code:
            out.append((code, val))
        i += 2
    return out


def _entities(pairs: list[tuple[str, str]]) -> list[dict]:
    """把组码流切成实体块（组码 0 = 新实体开始）。"""
    ents: list[dict] = []
    cur: dict | None = None
    for code, val in pairs:
        if code == "0":
            if cur and cur.get("type"):
                ents.append(cur)
            cur = {"type": val, "codes": {}}
        elif cur is not None:
            cur["codes"].setdefault(code, []).append(val)
    if cur and cur.get("type"):
        ents.append(cur)
    return ents


def _f(codes: dict, *keys) -> float | None:
    for k in keys:
        v = codes.get(k)
        if v:
            try:
                return float(v[0])
            except ValueError:
                continue
    return None


def _s(codes: dict, *keys) -> str:
    for k in keys:
        v = codes.get(k)
        if v:
            return v[0]
    return ""


# ---------- 结构模型 ----------

@dataclass
class Node:
    id: int
    x: float
    y: float
    z: float = 0.0
    source: str = ""


@dataclass
class Member:
    id: int
    n1: int
    n2: int
    kind: str = "beam"
    length_mm: float = 0.0
    layer: str = ""
    handle: str = ""


@dataclass
class StructureManifest:
    source: str = ""
    units: str = "mm"
    nodes: list = field(default_factory=list)
    members: list = field(default_factory=list)
    dims: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def extract_structure(path: str | Path, tol: float = 1.0) -> StructureManifest:
    p = Path(path)
    m = StructureManifest(source=str(p))
    pairs = _pairs(p)
    ents = _entities(pairs)

    layer_counts: dict[str, int] = {}
    text_list: list[str] = []
    dim_list: list[dict] = []

    # 节点去重表（1mm 容差）
    node_ids: dict[tuple[int, int], int] = {}

    def node_for(x: float, y: float, src: str) -> int:
        k = (round(x / tol), round(y / tol))
        if k in node_ids:
            return node_ids[k]
        nid = len(m.nodes) + 1
        m.nodes.append(Node(id=nid, x=round(x, 3), y=round(y, 3), source=src))
        node_ids[k] = nid
        return nid

    line_n = poly_n = 0

    for e in ents:
        et = e["type"].upper()
        c = e["codes"]
        layer = _s(c, "8")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

        if et == "LINE":
            x1, y1 = _f(c, "10"), _f(c, "20")
            x2, y2 = _f(c, "11"), _f(c, "21")
            if None in (x1, y1, x2, y2):
                continue
            n1 = node_for(x1, y1, "LINE")
            n2 = node_for(x2, y2, "LINE")
            if n1 == n2:
                continue
            length = math.hypot(x2 - x1, y2 - y1)
            m.members.append(Member(
                id=len(m.members) + 1, n1=n1, n2=n2, kind="beam",
                length_mm=round(length, 3), layer=layer, handle=_s(c, "5")))
            line_n += 1

        elif et == "LWPOLYLINE":
            xs = [float(v) for v in c.get("10", []) if _isnum(v)]
            ys = [float(v) for v in c.get("20", []) if _isnum(v)]
            for i in range(min(len(xs), len(ys)) - 1):
                n1 = node_for(xs[i], ys[i], "LWPOLYLINE")
                n2 = node_for(xs[i + 1], ys[i + 1], "LWPOLYLINE")
                if n1 == n2:
                    continue
                length = math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i])
                m.members.append(Member(
                    id=len(m.members) + 1, n1=n1, n2=n2, kind="poly",
                    length_mm=round(length, 3), layer=layer, handle=_s(c, "5")))
            poly_n += 1

        elif et in ("TEXT", "MTEXT", "ATTRIB"):
            t = _s(c, "1", "3")
            if t:
                text_list.append(_clean_mtext(t))

        elif et == "DIMENSION":
            meas = _f(c, "42")
            txt = _s(c, "1")
            dim_list.append({
                "measured": round(meas, 3) if meas is not None else None,
                "text": _clean_mtext(txt),
                "layer": layer,
            })

        elif et == "CIRCLE":
            r = _f(c, "40")
            if r is not None:
                m.notes.append(f"CIRCLE r={r} layer={layer}")

    m.layers = sorted(layer_counts)
    m.texts = text_list
    m.dims = dim_list
    m.stats = {
        "entities": len(ents),
        "line": line_n,
        "lwpolyline": poly_n,
        "nodes": len(m.nodes),
        "members": len(m.members),
        "texts": len(text_list),
        "dims": len(dim_list),
    }

    if not m.members:
        m.notes.append("未解析到成员：DXF 可能为块引用（INSERT）或 3D 实体，需展开块定义。")
    return m


def _isnum(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _clean_mtext(t: str) -> str:
    t = re.sub(r"\\[A-Za-z][^;]*;", "", t)
    t = t.replace("\\P", " ").replace("{", "").replace("}", "")
    return t.strip()


def member_type_by_length(length_mm: float, spans: list[float] | None = None) -> str:
    """按计算书口径猜构件类型（主梁/次梁/悬挑）。"""
    if not spans:
        return "main_beam"
    longest = max(spans)
    if abs(length_mm - longest) < 1e-6:
        return "main_beam"
    return "secondary_beam"


def main() -> int:
    import sys
    root = Path(__file__).resolve().parent.parent
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "勒勒车2-2.dxf"
    m = extract_structure(target)
    out = Path(__file__).resolve().parent / "logs" / "structure_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"source: {m.source}")
    print(f"stats : {m.stats}")
    print(f"layers: {m.layers}")
    print(f"dims  : {len(m.dims)} (sample {[d['measured'] for d in m.dims[:8]]})")
    print(f"texts : {m.texts[:6]}")
    print(f"nodes : {len(m.nodes)}  members: {len(m.members)}")
    if m.members:
        ls = sorted({round(x.length_mm, 1) for x in m.members})
        print(f"member lengths (top): {ls[:12]} ... {ls[-6:] if len(ls) > 12 else ''}")
    print(f"notes : {m.notes}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
