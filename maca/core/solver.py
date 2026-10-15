"""统一求解器接口 + 注册表（MACA 调度层核心）。

设计要点：
    - SolverBase.solve(params) -> SolverResult  是唯一的对外契约；
    - 每个适配器是一个可插拔后端，注册表负责名字->实例；
    - 新增引擎（如 OpenSees/CalculiX）只需写一个类并 register，
      上层 AI 编排与 UI 零改动。
"""

from abc import ABC, abstractmethod
from typing import Dict

from core.models import DesignParams, SolverResult


class SolverBase(ABC):
    name: str = "base"
    mode: str = "?"            # "theory" | "open-source" | "commercial" | "mock"
    available: bool = True
    note: str = ""

    @abstractmethod
    def solve(self, params: DesignParams) -> SolverResult:
        ...

    def is_available(self) -> bool:
        return self.available


_REGISTRY: Dict[str, SolverBase] = {}


def register(solver: SolverBase):
    _REGISTRY[solver.name] = solver()
    return solver


def get(name: str) -> SolverBase:
    if name not in _REGISTRY:
        raise KeyError(f"未注册的求解器: {name}；可用: {list(_REGISTRY)}")
    return _REGISTRY[name]


def available_names() -> list:
    return [n for n, s in _REGISTRY.items() if s.is_available()]


def all_names() -> list:
    return list(_REGISTRY)
