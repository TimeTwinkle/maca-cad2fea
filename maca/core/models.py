"""MACA 核心数据模型。

三层解耦范式：
    输入层  -> 计算书文本 -> 结构化工程参数 (DesignParams)
    调度层  -> 统一求解器接口 (solve) -> 求解结果 (SolverResult)
    迭代层  -> AI 评估 (SolverResult) -> 调整建议 (Suggestion) -> 新 DesignParams

DesignParams 是"模型无关"的中间表示：
    任何格式的计算书（MIDAS/手算/规范表格/自然语言）都能被 AI 解析成它，
    任何求解器（MIDAS/PyNite/理论公式）都从它出发计算。
"""

from dataclasses import dataclass, field, asdict


@dataclass
class DesignParams:
    """一组结构计算参数（简支梁示例，可扩展为多跨/多荷载）。"""
    material: str = "C30"          # 混凝土等级
    fc: float = 14.3               # 抗压强度 N/mm^2（C30 设计值）
    fy: float = 300.0              # 纵向钢筋屈服强度 N/mm^2（HRB300 设计值）
    span: float = 6000.0          # 跨度 mm（6m）
    wll: float = 20.0             # 均布荷载 kN/m（可变）
    self_weight: bool = True       # 是否计入自重
    section_b: float = 250.0      # 截面宽 mm
    section_h: float = 500.0      # 截面高 mm
    as_area: float = 1256.0      # 受拉钢筋面积 mm^2（默认 4C18）
    max_serviceability_span_mm: float = 20.0  # 容许挠度限值（示例）
    notes: str = ""

    def section_label(self) -> str:
        return f"{int(round(self.section_b))}x{int(round(self.section_h))}"

    def to_json(self) -> dict:
        d = asdict(self)
        d["section_label"] = self.section_label()
        return d

    @classmethod
    def from_json(cls, d: dict) -> "DesignParams":
        keys = {f for f in cls.__dataclass_fields__}
        d2 = {k: v for k, v in d.items() if k in keys}
        return cls(**d2)


@dataclass
class SolverResult:
    """一次求解的结果。"""
    stress_ratio: float          # 最大截面利用率（1.0 = 恰好达到承载能力）
    utilization_detail: dict = field(default_factory=dict)  # 弯矩/剪力/挠度 分项
    deflection_mm: float = 0.0
    max_moment_knm: float = 0.0
    ok: bool = False
    engine: str = ""
    log: str = ""

    def summary(self) -> str:
        flag = "满足" if self.ok else "超限"
        return f"[{self.engine}] 应力比={self.stress_ratio:.3f} {flag}，挠度={self.deflection_mm:.2f}mm"


@dataclass
class Suggestion:
    """AI 给出的一条调整建议。"""
    kind: str                    # "section" | "rebar" | "span" | "accept" | "reject"
    target_b: float | None = None
    target_h: float | None = None
    target_as_area: float | None = None
    reason: str = ""

    def to_json(self) -> dict:
        return asdict(self)
