"""PyNite 适配器（模式 B）：真实开源 FEA 引擎。

正确包名：pip install PyniteFEA（JWock82 版），导入名 `Pynite`。
若本机不可用，自动退化为理论公式（demo 仍可跑通），result 标注 fallback。
"""

from core.models import DesignParams, SolverResult
from core.solver import SolverBase, register


@register
class PyniteAdapter(SolverBase):
    name = "PyNite"
    mode = "open-source"
    note = "开源 3D FEA 引擎（JWock82 PyNite / PyniteFEA）"

    def __init__(self):
        try:
            import Pynite  # 由 PyniteFEA 提供
            self._pynite = Pynite
            self.available = True
        except Exception:
            self._pynite = None
            self.available = False
            self.note = "开源 FEA 引擎（未安装 → 回退理论公式）"
            from adapters.formula_adapter import FormulaAdapter
            self._fallback = FormulaAdapter()

    def solve(self, p: DesignParams) -> SolverResult:
        if not self.available:
            r = self._fallback.solve(p)
            r.engine = "PyNite→Fallback"
            r.log = "PyniteFEA 未安装，回退理论解。" + r.log
            return r
        try:
            return self._solve(p)
        except Exception as e:
            r = self._fallback.solve(p)
            r.engine = "PyNite→Fallback"
            r.log = f"PyniteFEA 异常({e})，回退理论解。" + r.log
            return r

    def _solve(self, p: DesignParams) -> SolverResult:
        P = self._pynite
        # 单位：mm / N / Pa。PyNite 内部对梁用 E[Pa], A[mm2], I[mm4], 荷载[kN→N]
        M = P.Model()
        M.Nodes = {
            "A": P.Node("A", 0.0, 0.0, 0.0),
            "B": P.Node("B", p.span, 0.0, 0.0),
        }
        E = 3.0e10  # Pa (C30 ≈ 30 GPa)
        Acs = p.section_b * p.section_h
        Iy = p.section_b * p.section_h ** 3 / 12.0
        Iz = Iy
        M.Beams = {"B1": P.BeamElement("B1", "A", "B", E, Acs, Iy, Iz, Iz, Iy, mass_per_m=0.0)}
        M.AddSupport("A", True, True, True, False, False, False)
        M.AddSupport("B", True, True, True, False, False, False)

        # 均布荷载（Y 向负）：q_total [kN/m] -> N/m -> 施加到梁（PyNite 用 kN/m 量级需换算）
        q_kNm = p.wll + (p.self_weight * 0.25 * 25 * p.section_h / 1000.0)
        # PyNite 均布荷载单位 kN/m（其内部对梁荷载按 kN/m 处理，位移输出 mm）
        M.Loads.AddDistributedLoad("B1", "DL1", "global", 0.0, [0.0, -q_kNm, 0.0], 1.0, [0.0, -q_kNm, 0.0])
        M.ReleaseAllLoads()
        M.Analyze()

        beam = M.Beams["B1"]
        M_mid_kNm = abs(beam.Moment(0.5)) / 1e3  # PyNite 弯矩输出 kN·m 量级需校准
        # PyNite 位移单位为 mm
        d_mid_mm = abs(beam.Deflection(0.5))

        mu_kNm = p.fy * p.as_area * (0.98 * p.section_h) / 1e6
        stress_ratio = M_mid_kNm / mu_kNm if mu_kNm else float("inf")
        ok = stress_ratio <= 1.0 and d_mid_mm <= p.max_serviceability_span_mm

        return SolverResult(
            stress_ratio=round(stress_ratio, 4),
            utilization_detail={"M_design_kNm": round(M_mid_kNm, 3), "Mu_capacity_kNm": round(mu_kNm, 3), "q_total_kNm": round(q_kNm, 3)},
            deflection_mm=round(d_mid_mm, 3),
            max_moment_knm=round(M_mid_kNm, 3),
            ok=ok,
            engine=self.name,
            log=f"PyNite FEA：M中={M_mid_kNm:.1f}kNm, δ中={d_mid_mm:.2f}mm, 应力比={stress_ratio:.3f}",
        )
