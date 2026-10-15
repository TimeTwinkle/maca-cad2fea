"""Harness 工程调度层：6 组 / 130 任务台账 + 10 分钟预算 + 审计。

把 "10 分钟 = 6 个大人 130 个小任务" 从口号变成可执行台账。

6 组（并行工作流）
    CAD     AutoCAD 解析与清洗
    MODEL   结构语义映射
    MIDAS   建模与有限元分析
    AUDIT   结果审查与超限识别
    OPT     截面/配筋/荷载迭代
    REPORT  汇总输出与审计

130 任务：以下为正式任务定义（编号 CAD-01..REPORT-26）。
每张任务卡：id / group / title / budget_s / depends_on / status / evidence
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

TOTAL_BUDGET_S = 600.0     # 10 分钟硬预算


@dataclass
class TaskCard:
    id: str
    group: str
    title: str
    budget_s: float
    depends_on: list = field(default_factory=list)
    status: str = "pending"      # pending | running | done | skipped | failed
    elapsed_s: float = 0.0
    evidence: dict = field(default_factory=dict)
    note: str = ""


def _t(id_, group, title, budget, deps=None, note=""):
    return TaskCard(id=id_, group=group, title=title, budget_s=budget,
                    depends_on=deps or [], note=note)


def build_task_ledger() -> list[TaskCard]:
    """正式 130 任务台账。"""
    tasks: list[TaskCard] = []

    # ---- CAD 组：30 ----
    cad_titles = [
        "校验 DXF 文件可读性与编码", "解析 HEADER 段（单位/范围）", "解析 TABLES 段（图层表）",
        "解析 BLOCKS 段（块定义）", "展开 INSERT 块引用", "解析 ENTITIES 段",
        "提取全部 LINE 实体", "提取全部 LWPOLYLINE 实体", "提取全部 CIRCLE 实体",
        "提取全部 ARC 实体", "提取全部 TEXT 实体", "提取全部 MTEXT 实体",
        "提取全部 DIMENSION 实体", "提取全部 HATCH 实体", "提取全部 SOLID 实体",
        "提取全部 POINT 实体", "统计各实体类型数量", "按图层分类实体统计",
        "识别 Defpoints 图层（标注辅助）", "过滤构造线/辅助线", "清洗 MTEXT 转义符",
        "还原中文编码（GB18030）", "提取尺寸标注测量值", "提取尺寸标注文字覆盖值",
        "几何去重（1mm 容差）", "端点吸附合并节点", "剔除零长度构件",
        "剔除孤立点实体", "生成围合边界盒", "输出 CAD 解析中间结果",
    ]
    for i, t in enumerate(cad_titles, 1):
        tasks.append(_t(f"CAD-{i:02d}", "CAD", t, 600.0 / 130))

    # ---- MODEL 组：20 ----
    model_titles = [
        "建立节点编号体系", "节点坐标归一化", "构件端点关联节点",
        "识别梁构件", "识别轴/柱构件", "识别支撑构件",
        "构件长度计算", "构件方向向量", "共线构件合并",
        "按长度分级（主/次/悬挑）", "生成构件清单", "套用截面号 1（梁）",
        "套用截面号 2（轴）", "读取钢结构材料等级", "识别重复截面",
        "生成截面汇总表", "生成结构拓扑图数据", "交叉节点识别",
        "悬挑构件识别", "输出 structure_manifest",
    ]
    for i, t in enumerate(model_titles, 1):
        tasks.append(_t(f"MODEL-{i:02d}", "MODEL", t, 600.0 / 130, deps=["CAD-30"]))

    # ---- MIDAS 组：30 ----
    midas_titles = [
        "初始化 MIDAS MAPI 会话", "设置单位制（kN/m）", "写入节点坐标",
        "写入截面 1（梁）", "写入截面 2（轴）", "写入钢材材料定义",
        "写入梁单元", "写入轴单元", "写入单元角度",
        "施加边界条件（一般支承）", "定义恒载工况", "定义一级加载工况",
        "写入结构自重", "写入沙袋荷载（11 个）", "写入温度荷载",
        "写入风荷载", "写入雪荷载", "定义荷载组合 1（空载）",
        "定义荷载组合 2（一级加载）", "设置分析控制参数", "触发静力分析",
        "轮询分析状态", "读取位移表", "读取梁内力表",
        "读取梁应力表", "读取反力表", "提取最大相对位移",
        "提取跨中弯矩", "提取构件应力比", "结束 MAPI 会话",
    ]
    for i, t in enumerate(midas_titles, 1):
        tasks.append(_t(f"MIDAS-{i:02d}", "MIDAS", t, 600.0 / 130, deps=["MODEL-20"]))

    # ---- AUDIT 组：15 ----
    audit_titles = [
        "校核位移比（1/600 vs 1/250）", "校核主梁挠度 L/400", "校核次梁挠度 L/250",
        "校核悬挑挠度 L/200", "校核构件应力比 ≤1.0", "校核稳定系数",
        "提取超限构件清单", "超限构件定位", "超限原因分类",
        "对比计算书参照值（15mm）", "偏差分析", "生成审查结论",
        "标注不合格项", "生成审查日志", "输出 audit_report",
    ]
    for i, t in enumerate(audit_titles, 1):
        tasks.append(_t(f"AUDIT-{i:02d}", "AUDIT", t, 600.0 / 130, deps=["MIDAS-30"]))

    # ---- OPT 组：20 ----
    opt_titles = [
        "接收超限构件清单", "判定控制因素（强度/挠度）", "生成截面放大建议",
        "生成材料升级建议", "生成荷载重分布建议", "生成支撑增设建议",
        "更新截面参数", "重建 MIDAS 模型", "重跑静力分析",
        "读取新结果", "收敛判据检查", "迭代计数",
        "迭代上限保护（≤6 轮）", "预算保护（10 分钟）", "最优方案筛选",
        "方案对比表", "选择最终方案", "记录迭代轨迹",
        "生成迭代收敛曲线", "输出 optimization_report",
    ]
    for i, t in enumerate(opt_titles, 1):
        tasks.append(_t(f"OPT-{i:02d}", "OPT", t, 600.0 / 130, deps=["AUDIT-15"]))

    # ---- REPORT 组：15 ----
    report_titles = [
        "汇总 CAD 解析结果", "汇总结构模型", "汇总 MIDAS 建模记录",
        "汇总分析结果", "汇总审查结论", "汇总迭代轨迹",
        "生成结构计算书章节", "生成截面汇总表", "生成荷载组合表",
        "生成位移结果图", "生成内力图", "生成应力比条形图",
        "生成 HTML 报告", "生成 JSON 数据包", "生成 Harness 审计日志",
    ]
    for i, t in enumerate(report_titles, 1):
        tasks.append(_t(f"REPORT-{i:02d}", "REPORT", t, 600.0 / 130, deps=["OPT-20"]))

    return tasks


class HarnessLedger:
    """任务台账运行时：状态推进、预算监控、审计落盘。"""

    def __init__(self, tasks: list[TaskCard] | None = None, budget_s: float = TOTAL_BUDGET_S):
        self.tasks = tasks or build_task_ledger()
        self.budget_s = budget_s
        self.t0 = time.perf_counter()

    @property
    def elapsed_s(self) -> float:
        return round(time.perf_counter() - self.t0, 4)

    def remaining_s(self) -> float:
        return round(self.budget_s - self.elapsed_s, 4)

    def find(self, task_id: str) -> TaskCard:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(f"未知任务: {task_id}")

    def mark(self, task_id: str, status: str, evidence: dict | None = None,
             elapsed_s: float | None = None, note: str = "") -> TaskCard:
        t = self.find(task_id)
        t.status = status
        t.elapsed_s = round(elapsed_s if elapsed_s is not None else (self.elapsed_s / len(self.tasks)), 4)
        if evidence:
            t.evidence.update(evidence)
        if note:
            t.note = note
        return t

    def group_summary(self) -> dict:
        out: dict[str, dict] = {}
        for t in self.tasks:
            g = out.setdefault(t.group, {"total": 0, "done": 0, "failed": 0, "skipped": 0})
            g["total"] += 1
            if t.status == "done":
                g["done"] += 1
            elif t.status == "failed":
                g["failed"] += 1
            elif t.status == "skipped":
                g["skipped"] += 1
        return out

    def budget_ok(self) -> bool:
        return self.elapsed_s <= self.budget_s

    def to_json(self) -> dict:
        return {
            "budget_s": self.budget_s,
            "elapsed_s": self.elapsed_s,
            "remaining_s": self.remaining_s(),
            "budget_ok": self.budget_ok(),
            "task_total": len(self.tasks),
            "groups": self.group_summary(),
            "tasks": [asdict(t) for t in self.tasks],
        }

    def save(self, out_dir: str | Path = "logs") -> str:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        p = out / "harness_ledger.json"
        p.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)


def main() -> int:
    led = HarnessLedger()
    j = led.to_json()
    print(f"任务总数: {j['task_total']}")
    print(f"预算: {j['budget_s']}s")
    for g, s in j["groups"].items():
        print(f"  {g:7s} {s['total']:3d} 项")
    path = led.save()
    print(f"台账已写入: {path}")
    assert j["task_total"] == 130, f"任务数应为 130，实际 {j['task_total']}"
    print("任务数校验通过 = 130")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
