"""MACA Harness Runner —— Agnes + Harness 深度绑定执行壳。

五段流水线（Graph 可调度 / Loop 可反复触发）：
    1. Intake   DXF / JSON / 计算书文本 -> 参数候选
    2. Agent    AIDecider 解析 + 截面迭代决策（默认规则，可外接 Agnes）
    3. Engine   Formula / PyNite / MIDAS(NX) 求解
    4. Tool     MCP 工具桥（可被 Agnes 客户端调用，非必经）
    5. Report   HTML + JSON + Harness 审计 JSON

设计原则：
    - 不降级：MIDAS 已配环境变量时走官方 MAPI 真值；未配时明确标注 midas_used=False，
      用 FormulaEngine 保闭环可演示（这是可复现性卖点，不是静默降级）；
    - 可审计：每段流水线产出结构化的 stage 记录，写入 logs/harness_audit.json；
    - 可复用：新模型只需换 DXF 或改 demo_params.json，Runner 零改动。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import adapters  # noqa: F401  注册所有引擎
from core.agent import Agent
from core.solver import get, all_names
from ai.decider import AIDecider
from demo_pipeline import build_report, PipelineReport, save_html, save_json


@dataclass
class StageRecord:
    stage: str
    started_s: float
    finished_s: float
    ok: bool
    detail: dict = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return round(self.finished_s - self.started_s, 4)


@dataclass
class HarnessRun:
    run_id: str
    source: str
    source_type: str
    engine_requested: str
    engine_used: str
    stages: list = field(default_factory=list)
    total_s: float = 0.0
    midas_configured: bool = False
    midas_used: bool = False
    converged: bool = False
    final: dict = field(default_factory=dict)
    audit_path: str = ""

    def to_json(self) -> dict:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "source_type": self.source_type,
            "engine_requested": self.engine_requested,
            "engine_used": self.engine_used,
            "midas_configured": self.midas_configured,
            "midas_used": self.midas_used,
            "converged": self.converged,
            "final": self.final,
            "total_s": self.total_s,
            "stages": [asdict(s) for s in self.stages],
            "audit_path": self.audit_path,
        }


def run_harness(
    source: str | Path,
    engine: str = "MIDAS(NX)",
    max_iters: int = 6,
    override: dict | None = None,
    out_dir: str | Path = "logs",
) -> HarnessRun:
    """执行五段流水线，返回 HarnessRun（含每段耗时与审计数据）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    stages: list[StageRecord] = []

    # ---- Stage 1: Intake ----
    s1_t = time.perf_counter()
    rep: PipelineReport = build_report(source, engine=engine, max_iters=max_iters, override=override)
    s1 = StageRecord("intake", s1_t, time.perf_counter(), True, {
        "source_type": rep.source_type,
        "dxf_keys": sorted((rep.dxf or {}).keys()) if rep.dxf else [],
        "param_keys": sorted(rep.design_params.keys()),
    })
    stages.append(s1)

    # ---- Stage 2: Agent（已在 build_report 内完成，这里只记录）----
    s2_t = time.perf_counter()
    ag = rep.agent_report or {}
    s2 = StageRecord("agent", s2_t, time.perf_counter(), ag.get("converged", False), {
        "converged": ag.get("converged"),
        "reason": ag.get("reason"),
        "steps_count": len(ag.get("steps", [])),
        "engine_used": ag.get("engine_used"),
    })
    stages.append(s2)

    # ---- Stage 3: Engine ----
    s3_t = time.perf_counter()
    s3 = StageRecord("engine", s3_t, time.perf_counter(), True, {
        "midas_configured": rep.midas_configured,
        "midas_used": rep.midas_used,
        "dual_check_present": bool(rep.dual_check),
    })
    stages.append(s3)

    # ---- Stage 4: Tool（MCP 桥可用性探测，不实际调用）----
    s4_t = time.perf_counter()
    tool_ok = Path(__file__).parent.joinpath("mcp_server.py").exists()
    s4 = StageRecord("tool", s4_t, time.perf_counter(), tool_ok, {
        "mcp_bridge_exists": tool_ok,
        "note": "MCP 工具桥为扩展口；Graph/Loop 可通过它调度 MACA，非必经路径。",
    })
    stages.append(s4)

    # ---- Stage 5: Report ----
    s5_t = time.perf_counter()
    rep.html_path = save_html(rep, out / "harness_demo.html")
    save_json(rep, out / "harness_demo_result.json")
    s5 = StageRecord("report", s5_t, time.perf_counter(), True, {
        "html_path": rep.html_path,
        "json_path": str(out / "harness_demo_result.json"),
    })
    stages.append(s5)

    total = time.perf_counter() - t0
    run = HarnessRun(
        run_id=f"hr-{int(t0)}",
        source=str(source),
        source_type=rep.source_type,
        engine_requested=engine,
        engine_used=ag.get("engine_used", engine),
        stages=stages,
        total_s=round(total, 3),
        midas_configured=rep.midas_configured,
        midas_used=rep.midas_used,
        converged=bool(ag.get("converged")),
        final=ag.get("final", {}),
    )

    # 审计 JSON
    audit_path = out / "harness_audit.json"
    audit_path.write_text(json.dumps(run.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    run.audit_path = str(audit_path)
    return run


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="DXF / 参数 JSON / 计算书 txt")
    ap.add_argument("--engine", default="MIDAS(NX)", choices=all_names())
    ap.add_argument("--max-iters", type=int, default=6)
    ap.add_argument("--override", default="", help="参数覆盖 JSON")
    ap.add_argument("--out-dir", default="logs")
    args = ap.parse_args()

    override = None
    if args.override:
        override = json.loads(Path(args.override).read_text(encoding="utf-8")).get("param_overrides", {})

    run = run_harness(args.source, engine=args.engine, max_iters=args.max_iters,
                      override=override, out_dir=args.out_dir)
    print("=" * 62)
    print("MACA Harness Runner（Agnes + Harness 深度绑定）")
    print("=" * 62)
    print(f"run_id={run.run_id}  source={run.source}")
    print(f"engine_requested={run.engine_requested}  engine_used={run.engine_used}")
    print(f"midas_configured={run.midas_configured}  midas_used={run.midas_used}")
    print(f"converged={run.converged}  total={run.total_s}s")
    for s in run.stages:
        print(f"  [{s.stage:6s}] ok={s.ok}  {s.duration_s}s  {s.detail}")
    print(f"audit={run.audit_path}")
    return 0 if run.converged else 1


if __name__ == "__main__":
    raise SystemExit(main())
