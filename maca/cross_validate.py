"""红方交叉验证：3 工况各建-析-取，独立保存结果（内存），只最终存一份。

修正：每工况 = /DOC/NEW + 建模 + /doc/ANAL + 立刻 /post/TABLE 取数。
不跨工况复用模型（避免被下一次 /DOC/NEW 清掉）。
"""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cad_model import extract_structure
from duel_run import largest_connected_component, pick_anchors


API = os.environ.get("MIDAS_API_URL", "https://moa-engineers.midasit.cn:443/gen").rstrip("/")
KEY = os.environ.get("MIDAS_MAPI_KEY", "")


def call(method, path, body=None, timeout=180):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "MAPI-Key": KEY, "Authorization": "Bearer " + KEY}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


MATL = {"1": {"TYPE": "USER", "NAME": "Q355", "bMASS_DENS": True, "DAMP_RAT": 0.05,
    "PARAM": [{"P_TYPE": 2, "ELAST": 206000000.0, "POISN": 0.3, "THERMAL": 1e-5,
               "DEN": 78.5, "MASS": 8.0047}]}}


def sect_body(h_mm, b_mm=20.0):
    return {"1": {"SECTTYPE": "DBUSER", "SECT_NAME": "Rect",
        "SECT_BEFORE": {"USE_SHEAR_DEFORM": True, "SHAPE": "SB", "DATATYPE": 2,
        "SECT_I": {"vSIZE": [round(h_mm/1000, 6), round(b_mm/1000, 6)]}}}}


def cons_body(nodes):
    a = pick_anchors(nodes)
    return {"1": {"ITEMS": [
        {"ID": a[0], "CONSTRAINT": "1111100"},
        {"ID": a[1], "CONSTRAINT": "1100000"},
        {"ID": a[2], "CONSTRAINT": "1100000"}]}}


def one_case(nodes, members, h_mm, udl, with_self, tag):
    st, r = call("POST", "/DOC/NEW", {})
    if st not in (200, 201):
        return None, None, f"NEW {st} {r[:80]}"
    call("POST", "/OPE/APISTART", {})
    st, r = call("PUT", "/db/NODE", {"Assign": {str(n.id): {"X": n.x/1000, "Y": n.y/1000, "Z": 0.0}
              for n in nodes}})
    if st not in (200, 201):
        return None, None, f"NODE {st} {r[:80]}"
    call("PUT", "/db/SECT", {"Assign": sect_body(h_mm)})
    call("PUT", "/db/MATL", {"Assign": MATL})
    elem = {str(i): {"TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [mb.n1, mb.n2], "ANGLE": 0}
            for i, mb in enumerate(members, 1)}
    call("POST", "/db/ELEM", {"Assign": elem})
    call("POST", "/db/CONS", {"Assign": cons_body(nodes)})

    if with_self:
        call("POST", "/db/STLD", {"Assign": {"1": {"NAME": "DL", "TYPE": "USER"},
                                             "2": {"NAME": "LL", "TYPE": "USER"}}})
        call("POST", "/db/LCOM-GEN", {"Assign": {"1": {"iTYPE": 0, "NAME": "Comb1",
            "vCOMB": [{"ANAL": "ST", "LCNAME": "DL", "FACTOR": 1.0},
                       {"ANAL": "ST", "LCNAME": "LL", "FACTOR": 1.0}]}}})
        call("POST", "/db/BODF", {"Assign": {"1": {"LCNAME": "DL", "FV": [0, 0, -1]}}})
        call("POST", "/db/BMLD", {"Assign": {"1": {"ITEMS": [{"ID": 1, "LCNAME": "LL",
            "GROUP_NAME": "", "CMD": "BEAM", "TYPE": "UNILOAD", "DIRECTION": "GZ",
            "USE_PROJECTION": False, "USE_ECCEN": False, "D": [0, 1, 0, 0],
            "P": [udl, udl, 0, 0]}]}}})
        lc = "Comb1(CB)"
    else:
        call("POST", "/db/STLD", {"Assign": {"1": {"NAME": "LL", "TYPE": "USER"}}})
        call("POST", "/db/LCOM-GEN", {"Assign": {"1": {"iTYPE": 0, "NAME": "CombLL",
            "vCOMB": [{"ANAL": "ST", "LCNAME": "LL", "FACTOR": 1.0}]}}})
        call("POST", "/db/BMLD", {"Assign": {"1": {"ITEMS": [{"ID": 1, "LCNAME": "LL",
            "GROUP_NAME": "", "CMD": "BEAM", "TYPE": "UNILOAD", "DIRECTION": "GZ",
            "USE_PROJECTION": False, "USE_ECCEN": False, "D": [0, 1, 0, 0],
            "P": [udl, udl, 0, 0]}]}}})
        lc = "CombLL(CB)"

    t0 = time.time()
    st, r = call("POST", "/doc/ANAL", {})
    if st not in (200, 201):
        return None, None, f"ANAL {st} {r[:80]}"

    def colmax(tt, keys, load):
        st, r = call("POST", "/post/TABLE", {"Argument": {"TABLE_TYPE": tt, "TABLE_NAME": tt,
            "LOAD_CASE_NAMES": [load]}}, timeout=90)
        if st != 200:
            return None
        for v in json.loads(r).values():
            if isinstance(v, dict) and "HEAD" in v:
                head = v["HEAD"]
                idx = [i for i, hh in enumerate(head) if hh in keys]
                best = None
                for row in v["DATA"]:
                    for i in idx:
                        if i < len(row):
                            try:
                                x = float(row[i])
                                if best is None or abs(x) > abs(best):
                                    best = x
                            except (TypeError, ValueError):
                                pass
                return best
        return None

    disp = colmax("DISPLACEMENTG", {"DX", "DY", "DZ"}, lc)
    mom = colmax("BEAMFORCE", {"Moment-y"}, lc)
    dt = time.time() - t0
    return (disp*1000 if disp is not None else None), mom, f"ok({dt:.1f}s)"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", nargs="?", default=str(ROOT.parent / "勒勒车2-2.dxf"))
    ap.add_argument("--udl", type=float, default=-1.0)
    args = ap.parse_args()

    m = extract_structure(args.dxf)
    nodes, members, _ = largest_connected_component(m)
    print(f"CAD {Path(args.dxf).name}: 最大分量 节点={len(nodes)} 杆={len(members)}")

    st, r = call("POST", "/OPE/APISTART", {})
    if st != 200:
        print(f"APISTART 失败 {st}: {r[:150]}"); return 3

    t0 = time.time()
    p1d, p1m, p1msg = one_case(nodes, members, 20.0, args.udl, True, "P1")
    p2d, p2m, p2msg = one_case(nodes, members, 20.0, args.udl, False, "P2")
    p3d, p3m, p3msg = one_case(nodes, members, 40.0, args.udl, True, "P3")
    wall = time.time() - t0

    print("\n================ 红方交叉验证 ================")
    print(f"P1 自重+一级 20x20  位移={p1d} mm 弯矩={p1m} kNm  {p1msg}")
    print(f"P2 纯一级    20x20  位移={p2d} mm 弯矩={p2m} kNm  {p2msg}")
    print(f"P3 自重+一级 20x40  位移={p3d} mm 弯矩={p3m} kNm  {p3msg}")
    print(f"3 工况 {wall:.1f}s")

    checks = [
        ("P1位移>P2位移", None if not (p1d and p2d) else p1d > p2d),
        ("P1位移>P3位移(截面Ix4)", None if not (p1d and p3d) else p1d > p3d),
        ("P1弯矩=P3弯矩(截面不变内力)", None if not (p1m and p3m) else abs(p3m-p1m) < 1e-6),
    ]
    real = [s for _, s in checks if s is not None]
    allpass = bool(real) and all(s for s in real)
    for name, s in checks:
        tag = "PASS" if s else ("FAIL" if s is False else "N/A")
        print(f"  [{tag:4s}] {name}")

    if not real:
        verdict = "undetermined"
    else:
        verdict = "consistent" if allpass else "divergent"
    print(f"\nverdict = {verdict}  总耗时 {wall:.1f}s")

    out = ROOT / "logs" / "cross_validate.json"
    out.write_text(json.dumps({
        "P1": {"disp_mm": p1d, "moment_knm": p1m},
        "P2": {"disp_mm": p2d, "moment_knm": p2m},
        "P3": {"disp_mm": p3d, "moment_knm": p3m},
        "checks": [[n, s] for n, s in checks], "verdict": verdict, "wall_s": round(wall, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"存一份 -> {out}")
    return 0 if allpass else 2


if __name__ == "__main__":
    raise SystemExit(main())
