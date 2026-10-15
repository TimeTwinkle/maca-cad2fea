"""MACA Harness 审计模块：生成 / 读取 / 校验 Harness 执行审计 JSON。

字段（每段流水线）：
    stage         intake | agent | engine | tool | report
    started_s     相对 run 起点的秒
    finished_s
    ok            bool
    duration_s    自动算
    detail        各段自定义结构

顶层：
    run_id / source / source_type / engine_requested / engine_used
    midas_configured / midas_used / converged / final / total_s
    audit_path
"""

from __future__ import annotations

import json
from pathlib import Path


def save_audit(run_json: dict, out_dir: str | Path = "logs") -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "harness_audit.json"
    p.write_text(json.dumps(run_json, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def load_audit(out_dir: str | Path = "logs") -> dict | None:
    p = Path(out_dir) / "harness_audit.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def audit_summary(a: dict | None) -> dict:
    """给现场管理页用的精简摘要。"""
    if not a:
        return {"exists": False}
    stages = []
    for s in a.get("stages", []):
        stages.append({
            "stage": s.get("stage"),
            "ok": s.get("ok"),
            "duration_s": round(s.get("finished_s", 0) - s.get("started_s", 0), 3),
        })
    return {
        "exists": True,
        "run_id": a.get("run_id"),
        "total_s": a.get("total_s"),
        "converged": a.get("converged"),
        "midas_used": a.get("midas_used"),
        "engine_used": a.get("engine_used"),
        "stages": stages,
    }
