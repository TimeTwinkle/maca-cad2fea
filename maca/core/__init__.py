"""MACA 核心包：数据模型 + 求解器接口 + 注册表 + Agent 编排。"""

from core.models import DesignParams, SolverResult, Suggestion
from core.solver import SolverBase, register, get, available_names, all_names
from core.agent import Agent, AgentReport, StepLog

__all__ = [
    "DesignParams",
    "SolverResult",
    "Suggestion",
    "SolverBase",
    "register",
    "get",
    "available_names",
    "all_names",
    "Agent",
    "AgentReport",
    "StepLog",
]
