import json


def generate_report(strategy, fea_results, duel_rules):
    """
    生成 Markdown 格式的计算书
    """
    md = []
    md.append("# 结构计算书（AI自动生成-Mock版）\n")

    # 一、几何与材料信息
    md.append("## 一、几何与材料信息")
    geo = strategy.get("geometry_rules", {})
    md.append(f"- 结构类型：{geo.get('structure_type')}")
    md.append(f"- 主承重梁截面：{geo.get('main_beam_section')} ({geo.get('material_main_beam')})")
    md.append(f"- 轴向杆件：{geo.get('axial_member_section')} ({geo.get('material_axial_member')})")
    md.append(f"- 约束条件：{geo.get('support_condition')}\n")

    # 二、荷载与工况组合
    md.append("## 二、荷载与工况组合")
    loads = strategy.get("load_cases", {})
    md.append(f"- 组合公式：{loads.get('combination')}")
    md.append(f"- 恒载系数：{loads.get('dead_load')}")
    md.append(f"- 沙袋荷载系数：{loads.get('sandbag_load')}\n")

    # 三、FEA结果汇总
    md.append("## 三、FEA结果汇总")
    md.append(f"- 最大位移：{fea_results.get('max_deflection_mm'):.2f} mm")
    md.append(f"- 最大弯矩：{fea_results.get('max_moment_kNm'):.2f} kNm")
    md.append(f"- 最大应力比：{fea_results.get('max_stress_ratio'):.3f}\n")

    # 四、验算与红蓝对抗逻辑
    md.append("## 四、验算与红蓝对抗")
    limits = strategy.get("check_limits", {})
    max_deflect = fea_results.get('max_deflection_mm', 0)
    limit_deflect = limits.get("member_length_mm", 1000) / limits.get("deflection_limit_ratio", 400)
    stress_ratio = fea_results.get('max_stress_ratio', 0)
    deflect_pass = max_deflect <= limit_deflect
    stress_pass = stress_ratio <= limits.get("stress_ratio_limit", 1.0)
    md.append(f"- 挠度验算：{max_deflect:.2f} mm <= {limit_deflect:.2f} mm | 结果：{'✅ 蓝色合格' if deflect_pass else '❌ 红色警告'}")
    md.append(f"- 应力验算：{stress_ratio:.3f} <= {limits.get('stress_ratio_limit', 1.0)} | 结果：{'✅ 蓝色合格' if stress_pass else '❌ 红色警告'}\n")

    # 五、AI审查结论与调整建议
    md.append("## 五、AI审查结论与调整建议")
    if not stress_pass:
        md.append("- **审查员（Agnes）判定**：最大应力比超限，结构承载力不足。")
        md.append("- **调整建议**：建议将主承重梁截面由 20x20mm 增大至 30x30mm，或材料由 Q235 升级为 Q355。")
    elif not deflect_pass:
        md.append("- **审查员（Agnes）判定**：挠度超限，刚度不足。")
        md.append("- **调整建议**：建议增大轴向杆件截面或增设支撑。")
    else:
        md.append("- **审查员（Agnes）判定**：结构各项指标均满足限值要求，计算书合理。无需调整。")
    return "\n".join(md)
