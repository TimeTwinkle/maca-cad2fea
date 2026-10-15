"""理论公式适配器（模式 C）：纯 math 实现，零依赖、永远可用。

用作"对照基准"：它给出简支梁的理论解，
用来验证 PyNite / MIDAS 适配器算得对不对。
"""

import math

from core.models import DesignParams, SolverResult
from core.solver import SolverBase, register


@register
class FormulaAdapter(SolverBase):
    name = "FormulaEngine"
    mode = "theory"
    note = "理论公式解（纯 math），作为其它引擎的对照基准"

    def solve(self, p: DesignParams) -> SolverResult:
        # 简支梁：设计弯矩 M = q * L^2 / 8
        q = p.wll + (p.self_weight * 0.25 * 25 * p.section_h / 1000.0)  # 自重 kN/m（b=250 简化）
        L_m = p.span / 1000.0  # mm -> m
        M_design = q * L_m ** 2 / 8.0  # kN·m

        # 受拉钢筋承载力 Mu = fy * As * d
        # fy [N/mm²] * As [mm²] * d [mm] = N·mm；换算到 kN·m 除以 1e6
        d = p.section_h - 0.02 * p.section_h  # 有效高度 d（保护层 2%h 简化）
        Mu_kNm = p.fy * p.as_area * d / 1e6  # kN·m

        stress_ratio = M_design / Mu_kNm if Mu_kNm else float("inf")

        # 弹性挠度 δ = 5 q L^4 / (384 E I)（全用 mm 系：q N/mm，L mm，E MPa，I mm⁴ → δ mm）
        E = 3.0e4  # MPa (C30)
        I = p.section_b * p.section_h ** 3 / 12.0  # mm⁴
        q_N_mm = q * 1000.0 / 1000.0  # kN/m -> N/mm（数值等同 kN/m/1000*1000，即 q/1）
        # 严格单位换算：q [kN/m] = q * 1000 N / 1000 mm = q N/mm
        q_Nmm = q  # 数值上 1 kN/m = 1 N/mm
        L_mm = p.span
        delta_mm = 5.0 * q_Nmm * L_mm ** 4 / (384.0 * E * I)

        ok = stress_ratio <= 1.0 and delta_mm <= p.max_serviceability_span_mm
        return SolverResult(
            stress_ratio=round(stress_ratio, 4),
            utilization_detail={
                "M_design_kNm": round(M_design, 3),
                "Mu_capacity_kNm": round(Mu_kNm, 3),
                "q_total_kNm": round(q, 3),
            },
            deflection_mm=round(delta_mm, 3),
            max_moment_knm=round(M_design, 3),
            ok=ok,
            engine=self.name,
            log=f"理论解：M={M_design:.1f}kNm, Mu={Mu_kNm:.1f}kNm, 应力比={stress_ratio:.3f}, δ={delta_mm:.2f}mm",
        )
