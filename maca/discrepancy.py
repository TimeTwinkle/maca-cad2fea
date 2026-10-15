"""矛盾自动检出器：MACA 把"人关于 MIDAS 的判断"做成可机器复核的规则。

定位（核心卖点）：
    计算书正文说"最大15mm 合格"，但它自己的表格3实测 32.22mm。
    人汇报时把数写小了 / 限值口径没对齐 —— 这种"自相矛盾"人工易漏。
    本模块把 strategy.json 的 open_discrepancies 变成自动检出的 red flag，
    不替用户下结论，只把矛盾摆出来（诚信红线）。

触发条件（来自真实数据，不猜）：
    M1 位移口径 : |DZ|max(表格3) > 正文声称 * 1.2 → red flag
    M2 材料缺E   : strategy 无 E 且 PPT 有 → 标注待确认
    M3 系数未填   : 组合无系数 → 标注待确认
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_strategy(path: str | Path = "strategy.json") -> dict:
    p = Path(path)
    if not p.exists():
        p = ROOT / "strategy.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def check(strategy: dict, tol: float = 1.2) -> dict:
    """返回 {flags: [...], m1_gauge: ...}。M1 用 tol 倍数判缺口。

    若 strategy 里 M1 已 adjudicated（MACA_decision 存在），则 flag 带上判定结论，
    不再只摆矛盾——这是"人关于 MIDAS 的判断"被机器复核后的定稿。"""
    real = strategy.get("real_fea_table", {})
    claims = strategy.get("check_limits", {}).get("report_claims", {})
    flags = []

    # M1 位移口径矛盾
    max_real = real.get("max_abs_dz_mm")
    claim = claims.get("max_vertical_disp_mm")
    if max_real and claim and max_real > claim * tol:
        gap = max_real / claim
        need_L_250 = max_real * 250
        need_L_600 = max_real * 600
        # 读 M1 是否已 adjudicated
        m1 = next((d for d in strategy.get("open_discrepancies", [])
                   if d.get("id") == "M1"), {})
        m1_flag = {
            "id": "M1", "severity": "critical", "kind": "位移口径矛盾",
            "claim_mm": claim, "real_mm": max_real, "gap": round(gap, 3),
            "detail": (f"计算书正文声称 max={claim}mm，"
                       f"但其表格3实测 {max_real}mm@node{real.get('max_abs_dz_node')}，"
                       f"差 {gap:.2f} 倍。"),
            "note": (f"若 {max_real}mm 按 1/250 需 L≥{need_L_250:.0f}mm；"
                     f"按 1/600 需 L≥{need_L_600:.0f}mm，均非车架尺度。"),
        }
        if m1.get("MACA_decision"):
            m1_flag["adjudication"] = m1["MACA_decision"]
            m1_flag["status"] = "adjudicated"
            m1_flag["note"] += " MACA 判定：" + m1["MACA_decision"]
        else:
            m1_flag["status"] = "open"
            m1_flag["note"] += " 未核实 L 前 MACA 不予合格结论。"
        flags.append(m1_flag)

    # M2 材料 E
    mat = strategy.get("geometry_rules", {}).get("elastic_modulus_gpa")
    if not mat:
        flags.append({"id": "M2", "severity": "medium", "kind": "材料缺E",
                       "detail": "strategy 无弹性模量，需确认材料口径。"})

    # M3 荷载系数
    lc = strategy.get("load_cases", {})
    if not lc.get("strength_combo_factor"):
        flags.append({"id": "M3", "severity": "low", "kind": "荷载系数未定",
                       "detail": "组合系数未定，验算口径不确定。"})

    return {"m1_gauge": {"claim": claim, "real": max_real,
                          "gap": (max_real / claim) if (max_real and claim) else None,
                          "tolerance": tol},
            "flags": flags}


def main() -> int:
    strat = load_strategy()
    r = check(strat)
    print("=" * 58)
    print("MACA 矛盾自动检出（诚信红线：只摆矛盾，不下合格结论）")
    print("=" * 58)
    g = r["m1_gauge"]
    print(f"M1 位移口径: 正文={g['claim']}mm  表格3实测={g['real']}mm  "
          f"缺口={g['gap']}  (tol={g['tolerance']})")
    for f in r["flags"]:
        print(f"  [{f['severity']:8s}] {f['id']} {f['kind']}")
        print(f"      {f['detail']}")
        if f.get("note"):
            print(f"      -> {f['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
