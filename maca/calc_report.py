"""计算书生成器（真实值 + 策略蒸馏口径 + 矛盾自动检出）。

与 mock 版区别：
    - FEA 数值优先用 MIDAS 真 FEA（fea_results，来自 red_run），无 key 时用
      计算书 表格3 的真实 165 节点位移作为比对基准（real_fea_table.py，非占位）；
    - 限值/材料/组合口径来自 strategy.json（人关于 MidasGen 判断的机器蒸馏）；
    - 自动把 strategy.open_discrepancies 检出的 red flag（M1 位移口径矛盾等）
      写进计算书，诚信红线：只摆矛盾，不替用户下"合格"结论。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load_strategy(path: str | Path = "strategy.json") -> dict:
    p = Path(path)
    if not p.exists():
        p = ROOT / "strategy.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def generate_report(strategy: dict, fea_results: dict) -> str:
    """生成 Markdown 计算书。

    fea_results 来自 red_run：
       {available, max_disp_mm, max_moment_knm, converged, analyze_s, error,
        picked_nodes, picked_members, longest_mm}
    """
    from discrepancy import check as disp_check

    geo = strategy.get("geometry_rules", {})
    matl = strategy.get("material_rules", {})
    loads = strategy.get("load_cases", {})
    limits = strategy.get("check_limits", {})
    real_tbl = strategy.get("real_fea_table", {})

    md = ["# 结构计算书（MACA 自动生成 · 真实数据版）\n"]

    # 一、几何与材料（策略蒸馏，全真实）
    md.append("## 一、几何与材料口径")
    md.append(f"- 结构类型：{geo.get('structure_type')}")
    md.append(f"- 材料：{geo.get('material')}，E={geo.get('elastic_modulus_gpa')}GPa"
              f"（{geo.get('elastic_modulus_note', '')}）")
    md.append(f"- 节点数：{geo.get('node_count_report')}"
              f"（{geo.get('node_count_source', 'PPT')}）")
    md.append(f"- 截面号：{geo.get('main_beam_section_no')}={geo.get('section_role_1', '梁')}"
              f" / {geo.get('axial_member_section_no')}={geo.get('section_role_2', '轴')}"
              f"（计算书 表格2）")
    md.append(f"- 约束：{geo.get('support_condition')}"
              f"（{geo.get('support_note', '')}）")
    md.append("")

    # 二、荷载组合（PPT 真实口径）
    md.append("## 二、荷载与工况组合")
    rc = loads.get("report_combos", {})
    if rc:
        md.append(f"- 强度验算：{rc.get('strength')}")
        md.append(f"- 变形验算：{rc.get('deflection')}")
    md.append(f"- 活载类型：{', '.join(loads.get('live_load_types', []))}")
    md.append(f"- 恒载：{loads.get('dead_load')}")
    md.append(f"- 汇报工况：{loads.get('report_case')}")
    md.append("")

    # 三、FEA 结果（真值优先，无 key 用表格3基准）
    md.append("## 三、MIDAS FEA 结果")
    if fea_results.get("available"):
        src = fea_results.get("red_source", "MIDAS实时")
        if src == "表格3快照":
            md.append(f"- 取数：**{src}**（MIDAS 会话未建/材料未定义，诚实降级，非伪造实时值）")
            md.append(f"- 最大竖向位移：**{fea_results.get('max_disp_mm', 0):.4f} mm**（表格3 快照基准）")
            md.append(f"- 最大弯矩：**n/a**（快照仅位移表，无弯矩表）")
            md.append(f"- 逐行可追溯：{fea_results.get('snapshot_ref', '')}")
        else:
            mk = fea_results.get('max_moment_knm')
            md.append(f"- 取数：MIDAS 官方 MAPI 实时 FEA（{fea_results.get('analyze_s', 0)}s）")
            md.append(f"- 最大竖向位移：**{fea_results.get('max_disp_mm', 0):.4f} mm**")
            md.append(f"- 最大弯矩：**{('n/a' if mk is None else str(mk) + ' kNm')}**")
        md.append(f"- 收敛：{'✅' if fea_results.get('converged') else '⚠ 发散'}")
    else:
        md.append(f"- ⚪ 实时 MIDAS 未取真值：{fea_results.get('error', 'MIDAS 未配')}")
        if real_tbl:
            md.append(f"- **比对基准（计算书 表格3 真实值）**：|DZ|max="
                     f"{real_tbl.get('max_abs_dz_mm')}mm@node{real_tbl.get('max_abs_dz_node')}，"
                     f"合成 {real_tbl.get('max_combined_disp_mm')}mm，{real_tbl.get('rows')} 节点")
            md.append("- （诚信：MIDAS 会话未建/MAPI-Key 失效时，用计算书自带表格3 快照做基准，不伪造实时值）")
    md.append("")

    # 四、验算 + 矛盾自动检出（核心）
    md.append("## 四、验算与矛盾自动检出")
    dlim = limits.get("deflection", {})
    for k, v in dlim.items():
        if k == "source":
            continue
        md.append(f"- 挠度限值 {k}：{v}")
    md.append(f"- 应力比限值：{limits.get('stress_ratio_limit')}")
    md.append("")

    disc = disp_check(strategy)
    flags = disc.get("flags", [])
    g = disc.get("m1_gauge", {})
    if g.get("gap"):
        md.append(f"### 红蓝对抗 · 自动检出矛盾")
        md.append(f"- **M1 位移口径**：正文声称 {g.get('claim')}mm，"
                  f"计算书表格3 实测 {g.get('real')}mm，缺口 **{g.get('gap')} 倍** → "
                  f"{'⚠ RED FLAG' if g['gap'] > 1.2 else '✅ 一致'}")
    for f in flags:
        md.append(f"- [{f['severity'].upper()}] **{f['id']} {f['kind']}**：{f['detail']}")
        if f.get("adjudication"):
            md.append(f"    → **MACA 判定**：{f['adjudication']}")
        elif f.get("note"):
            md.append(f"    → {f['note']}")
    md.append("")

    # 五、审查结论（诚信：有矛盾不下合格）
    md.append("## 五、审查结论（MACA 红蓝对抗）")
    if not fea_results.get("available") and not real_tbl:
        md.append("- MACA 判定：**未取真值，不予结论**。")
    else:
        critical = [f for f in flags if f["severity"] == "critical"]
        if critical:
            md.append("- MACA 判定：**存在 critical 矛盾，不予合格结论**。"
                      "（诚信红线：正文数值与实测表格矛盾，需先核实再验收。）")
            for f in critical:
                md.append(f"  - {f['id']}：{f['detail']}")
        else:
            md.append("- MACA 判定：各口径一致，结构结果成立。")
    md.append(f"\n_数据源：strategy.json（真实蒸馏）+ 计算书表格3 + PPT。"
              f"MACA 只摆矛盾，不替用户下'合格'结论。_")
    return "\n".join(md)


if __name__ == "__main__":
    import glob
    strat = load_strategy()
    # 从最新一版 duel_report_v*.json 取 red（快照态或实时态），不硬编码 demo
    f = sorted(glob.glob(str(ROOT / "logs" / "duel_report_v*.json")),
               key=lambda p: Path(p).stat().st_mtime)
    if f:
        rep = json.loads(open(f[-1], encoding="utf-8").read())
        fea = {"available": rep["red"]["available"],
               "red_source": rep["red"]["red_source"],
               "max_disp_mm": rep["red"]["max_disp_mm"],
               "max_moment_knm": rep["red"]["max_moment_knm"],
               "converged": rep["red"]["converged"],
               "analyze_s": rep["red"].get("analyze_s", 0),
               "snapshot_ref": rep["red"].get("snapshot_ref", ""),
               "error": rep["red"].get("error", "")}
        print(f"red source from: {Path(f[-1]).name}")
    else:
        fea = {"available": False, "error": "无 duel_report_v*.json，未跑 run_duel"}
    out = generate_report(strat, fea)
    # 落盘带版本+时刻（不裸名反复覆盖）
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    prev = sorted((ROOT / "logs").glob("calc_report_v*.md"))
    n = (len(prev) + 1) if prev else 1
    p = ROOT / "logs" / f"calc_report_v{n}_{ts}.md"
    p.write_text(out, encoding="utf-8")
    print(out)
    print(f"\n-> {p}")
