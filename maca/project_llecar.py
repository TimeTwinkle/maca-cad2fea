"""勒勒车结构 —— 真实工程定义（来自《勒勒车计算书》+ 汇报 PPT，不是占位）。

来源：
  - 勒勒车计算书.docx（设计：王子豪、柯希鑫、邓广新）
  - 勒勒车模型结构设计与计算汇报.pptx（slide 11 / 15 / 17 / 18 / 19）

关键事实（原文摘录，勿改）：
  - 对象：竞赛用勒勒车（小型载货车），非建筑结构
  - 材料：竹材/钢结构设计，软件 Midas-Gen
  - 外廓尺寸：500 × 280 mm（PPT slide 11 原文）
  - 内部净空：480 × 270 mm
  - 局部卡槽：150 宽 × 20 深（动力小车连接件限位）
  - 构件分类：核心受力构件两类 —— 承重梁、受力轴（slide 17）
  - 截面号列表：1 = 梁，2 = 轴（计算书 3.2）
  - 荷载：结构自重（自动）+ 空载 + 一级加载（沙袋）；温度/风荷载
  - 荷载组合：1 空载 / 2 一级加载；验算用自重 + 使用荷载标准组合
  - 边界：一般支承约束（slide 18）
  - 挠度控制：主梁 L/400，次梁 L/250，悬挑 L/200（计算书表格 1）
  - 已算结果：最大相对位移 15mm，位移比 1/600 < 1/250（slide 19）
  - 装载：布袋 20~40 个，单个 10~20kg（slide 4）
  - 赛车要素：坡道/弯道/减速带/单边桥，动力小车牵引

重要：跨度 L 就是车架尺寸级别（500mm 量级），不是建筑意义的米级跨度。
      任何几何解释都必须先对齐这个量级。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


# ---------- 截面定义（计算书：1=梁，2=轴）----------

@dataclass
class SteelSection:
    no: int
    name: str
    shape: str = ""          # "SB"(实腹矩形) / "B"(钢管) / "H"(工字) 等，待从模型确认
    height_mm: float = 0.0
    width_mm: float = 0.0
    thk_web_mm: float = 0.0
    thk_flange_mm: float = 0.0
    steel_grade: str = ""    # Q235 / Q355
    note: str = ""


# ---------- 挠度控制（计算书表格 1，原文）----------

DEFLECTION_LIMITS = {
    "cantilever": 200.0,   # 悬挑构件：L/200
    "main_beam": 400.0,    # 主梁：L/400
    "secondary_beam": 250.0,  # 次梁：L/250
}


# ---------- 荷载工况（计算书 3.3）----------

@dataclass
class LoadCase:
    no: int
    name: str
    kind: str                # "dead" / "live" / "sandbag_stage"
    desc: str = ""
    multiplier: float = 1.0


@dataclass
class LoadCombination:
    no: int
    name: str
    kind: str                # "add"
    items: list = field(default_factory=list)   # [("D", 1.0), ("L", 1.0)]
    desc: str = ""


# ---------- 工程口径总表 ----------

DESIGN_BASIS = {
    "structure_type": "steel_bamboo_frame",
    "object": "竞赛用勒勒车（小型载货车）车架",
    "analysis_software": "Midas-Gen",
    "codes": [
        "GB 50068-2017", "GB 50153-2008", "GB 50009-2012", "GB 50223-2008",
        "GB 50011-2010(2016)", "JGJ99-2015", "JGJ7-2010", "GB 50017-2017",
        "GB/T 19879-2015", "GB/T 1591-2018", "JGJ/T 395-2017",
        "GB 50016-2017(2019)", "GB 51249-2017",
    ],
    "design_life_years": 100,
    "safety_level": "一级",
    "gamma0": 1.10,
    "seismic_intensity": 6,
    "seismic_accel_g": 0.05,
    "seismic_group": 1,
    "site_class": "I0",
    "seismic_category": "丙类",
    "basic_wind_kpa": 0.30,
    "terrain_roughness": "A",
    "basic_snow_kpa": 0.70,
    "governing_combo": "自重+使用荷载标准组合",
    # 车架真实尺寸（PPT slide 11 原文，mm）
    "outline_length_mm": 500.0,
    "outline_width_mm": 280.0,
    "inner_length_mm": 480.0,
    "inner_width_mm": 270.0,
    "slot_width_mm": 150.0,
    "slot_depth_mm": 20.0,
    "min_clearance_mm": 20.0,
    # 装载能力（slide 4）
    "bag_count_min": 20,
    "bag_count_max": 40,
    "bag_weight_kg_min": 10.0,
    "bag_weight_kg_max": 20.0,
}

# 截面分类（计算书 3.2：1 = 梁，2 = 轴）
SECTION_ROLES = {1: "承重梁", 2: "受力轴"}


DEFAULT_SECTIONS = [
    SteelSection(no=1, name="承重梁", note="计算书 3.2 + PPT slide 17：截面号 1 = 梁"),
    SteelSection(no=2, name="受力轴", note="计算书 3.2 + PPT slide 17：截面号 2 = 轴"),
]


REAL_SPAN_MM = 500.0      # 车架外廓长度（PPT slide 11）
REAL_SPAN_NOTE = "车架外廓 500mm（PPT slide 11），内部净空 480mm"


DEFAULT_LOAD_CASES = [
    LoadCase(no=1, name="空载", kind="dead", desc="PPT slide 18：使用阶段荷载 —— 空载工况"),
    LoadCase(no=2, name="一级加载", kind="sandbag_stage", desc="PPT slide 18：使用阶段荷载 —— 一级加载（布袋）"),
]


DEFAULT_COMBINATIONS = [
    LoadCombination(no=1, name="空载", kind="add", items=[("D", 1.0), ("L", 0.0)]),
    LoadCombination(no=2, name="一级加载", kind="add", items=[("D", 1.0), ("L", 1.0)]),
]


REFERENCE_RESULT = {
    "max_relative_displacement_mm": 15.0,   # PPT slide 19 原文
    "displacement_ratio": "1/600",
    "limit_ratio": "1/250",
    "verdict": "满足要求",
    "combo": "自重+使用荷载标准组合",
    "note": "PPT slide 19：结构最大相对位移仅 15mm，位移比 1/600，远优于 1/250 要求",
}

# 量级矛盾（待澄清，不自行编造）：
#   车架外廓 500mm，若按 1/250 算限值 = 2.0mm，与 15mm 实测矛盾；
#   若 15mm 对应 1/600，则 L = 9000mm；若对应 1/250，则 L = 3750mm。
#   两种结果都与车架外廓 500mm 差一个数量级。
#   推测：计算书中的 L 指车轮跨距 / 整车尺度，而非车架外廓；
#   或位移限值按整车而非单构件。须向设计人核实后才可用于验收。
OPEN_QUESTIONS = [
    {
        "id": "Q-SPAN-01",
        "topic": "挠度限值所属跨度 L 的尺度",
        "problem": "计算书/PPT 的 15mm 位移与 1/600 位移比，无法用车架外廓 500mm 解释（500/250=2.0mm）",
        "candidates": [
            "L = 车轮跨距或整车长度（非车架外廓）",
            "位移限值按整车/整机尺度控制，非单个车架构件",
            "PPT 的 1/600 是展示口径，与表格 L/250 非同一条款",
        ],
        "impact": "未经核实前，AUDIT 不得用 L/250 对 500mm 直接判定，应用 verdict=undetermined",
        "status": "open",
    },
]


@dataclass
class LelLecarProject:
    """勒勒车结构工程口径（真实来源，非占位）。"""
    name: str = "勒勒车结构"
    design_basis: dict = field(default_factory=lambda: dict(DESIGN_BASIS))
    sections: list = field(default_factory=lambda: [asdict(s) for s in DEFAULT_SECTIONS])
    load_cases: list = field(default_factory=lambda: [asdict(l) for l in DEFAULT_LOAD_CASES])
    combinations: list = field(default_factory=lambda: [asdict(c) for c in DEFAULT_COMBINATIONS])
    deflection_limits: dict = field(default_factory=lambda: dict(DEFLECTION_LIMITS))
    reference_result: dict = field(default_factory=lambda: dict(REFERENCE_RESULT))
    open_questions: list = field(default_factory=lambda: [dict(q) for q in OPEN_QUESTIONS])
    sandbag_count: int = 11
    real_span_mm: float = REAL_SPAN_MM
    real_span_note: str = REAL_SPAN_NOTE

    def to_json(self) -> dict:
        return asdict(self)


def deflection_limit_mm(member_type: str, span_mm: float) -> float:
    """按计算书表格 1 算挠度限值（mm）。"""
    div = DEFLECTION_LIMITS.get(member_type)
    if not div:
        raise KeyError(f"未知构件类型: {member_type}；可用: {list(DEFLECTION_LIMITS)}")
    return span_mm / div


if __name__ == "__main__":
    import json
    p = LelLecarProject()
    print(json.dumps(p.to_json(), ensure_ascii=False, indent=2))
    print("主梁 6000mm 限值 =", deflection_limit_mm("main_beam", 6000.0), "mm")
