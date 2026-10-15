"""MACA Agent 编排层（迭代反馈闭环）。

这是整个范式的"灵魂"：
    AI 解析 → 选引擎求解 → AI 评估 → 建议 → 新参数 → 再求解 …… 直到满足或到上限。

不依赖任何具体 LLM/求解器，完全可插拔。
"""

from dataclasses import dataclass, field

from core.models import DesignParams, SolverResult, Suggestion
from core.solver import get as get_solver
from ai.decider import AIDecider


@dataclass
class StepLog:
    step: int
    engine: str
    section_label: str
    stress_ratio: float
    deflection_mm: float
    ok: bool
    suggestion: str
    log: str


@dataclass
class AgentReport:
    design_params: DesignParams
    final_result: SolverResult
    steps: list = field(default_factory=list)
    converged: bool = False
    reason: str = ""

    def to_rows(self) -> list:
        """给 UI 折线图用：每步 (应力比, 挠度)。"""
        return [(s.stress_ratio, s.deflection_mm) for s in self.steps]


class Agent:
    def __init__(self, decider: AIDecider, engine: str = "PyNite", max_iters: int = 6):
        self.decider = decider
        self.engine = engine
        self.max_iters = max_iters

    def run(self, book_text: str) -> AgentReport:
        solver = get_solver(self.engine)
        params = self.decider.parse_design_book(book_text)
        steps: list[StepLog] = []
        converged = False
        reason = ""
        result = solver.solve(params)

        for i in range(self.max_iters):
            s: Suggestion = self.decider.decide(params, result)
            steps.append(StepLog(
                step=i + 1,
                engine=result.engine,
                section_label=params.section_label(),
                stress_ratio=result.stress_ratio,
                deflection_mm=result.deflection_mm,
                ok=result.ok,
                suggestion=s.reason or s.kind,
                log=result.log,
            ))
            if s.kind == "accept" and result.ok:
                converged = True
                reason = "满足承载力与服务性"
                break
            # 应用建议 -> 新参数
            if s.target_b:
                params.section_b = float(s.target_b)
            if s.target_h:
                params.section_h = float(s.target_h)
            if s.target_as_area:
                params.as_area = float(s.target_as_area)
            result = solver.solve(params)
            if result.ok:
                converged = True
                reason = "调整后再验证通过"
                break
        else:
            reason = f"达到最大迭代 {self.max_iters} 次仍未收敛"

        return AgentReport(design_params=params, final_result=result, steps=steps, converged=converged, reason=reason)
