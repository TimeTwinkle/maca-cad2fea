"""MACA 适配器包：导入即注册。

引擎注册表（调度层灵魂）：
    FormulaEngine   纯 math 理论解（零依赖，永远可用）
    PyNite          开源 FEA（PyniteFEA；未装自动回退理论解）
    MIDAS(NX)       商业软件（官方 MAPI RESTful 直连，缺 Key 时占位）
"""

from adapters.formula_adapter import FormulaAdapter
from adapters.pynite_adapter import PyniteAdapter
from adapters.midas_sdk_adapter import MidasSdkAdapter

__all__ = ["FormulaAdapter", "PyniteAdapter", "MidasSdkAdapter"]
