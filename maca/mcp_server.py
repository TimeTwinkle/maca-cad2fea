"""Agnes Harness MCP Tool 接入层（stdio，JSON-RPC 2.0）。

定位：
    这是 MACA 接入 Agnes + Harness 体系的**工具化扩展口**（B 方案）。
    Graph / Loop 可通过本桥把 MACA 当作一个可调度节点；
    底层求解仍走官方 MAPI REST 直连（adapters/midas_rest_client.py），无任何第三方中转。

暴露工具：
  list_engines     列出可用求解引擎（含 MIDAS 接入状态）
  solve_once       单次求解：DesignParams -> SolverResult（指定引擎，含 MIDAS(NX)）
  run_maca_agent   完整闭环：计算书 -> AI 决策 -> 迭代 -> 收敛
  run_harness      五段 Harness 流水线（Intake->Agent->Engine->Tool->Report），出审计 JSON

凭证走环境变量（绝不写死进代码）：
  MIDAS_API_URL / MIDAS_MAPI_KEY   （MIDAS）
  AGNES_API_KEY                    （可选，启用 LLM 决策；否则规则 fallback）

直接 stdio 运行：
  python mcp_server.py
（父进程 / Agnes 客户端按 MCP 协议发 JSON-RPC）
"""

import json
import os
import sys

# 让 core/ adapters/ ai/ 可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adapters  # noqa: F401  注册所有引擎（Formula / PyNite / MIDAS(NX)）
from core.solver import get, all_names, available_names
from core.models import DesignParams
from ai.decider import AIDecider
from core.agent import Agent
from adapters import midas_rest_client as midas


TOOLS = [
    {
        "name": "list_engines",
        "description": "列出 MACA 可用的求解引擎及接入状态（MIDAS 是否已配 MAPI）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "solve_once",
        "description": "用指定引擎对一组设计参数做单次求解，返回应力比/挠度/ok。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "description": "FormulaEngine / PyNite / MIDAS(NX)"},
                "span_m": {"type": "number"},
                "wll_knm": {"type": "number", "description": "均布荷载 kN/m"},
                "fc_mpa": {"type": "number", "description": "混凝土抗压强度 MPa"},
                "fy_mpa": {"type": "number", "description": "钢筋抗拉强度 MPa"},
                "section_b": {"type": "number", "description": "截面宽 mm"},
                "section_h": {"type": "number", "description": "截面高 mm"},
                "as_area": {"type": "number", "description": "配筋面积 mm^2"},
            },
            "required": ["engine"],
        },
    },
    {
        "name": "run_maca_agent",
        "description": "跑完整 MACA 闭环：读计算书 -> AI 出建议 -> 迭代截面 -> 收敛。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "book_text": {"type": "string", "description": "计算书原文"},
                "engine": {"type": "string", "description": "默认 FormulaEngine"},
                "max_iters": {"type": "integer"},
            },
            "required": ["book_text"],
        },
    },
    {
        "name": "run_harness",
        "description": "五段 Harness 流水线（Intake->Agent->Engine->Tool->Report），出审计 JSON。Agnes Harness 深度绑定入口。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "DXF / 参数 JSON / 计算书 txt 路径"},
                "engine": {"type": "string", "description": "默认 MIDAS(NX)"},
                "max_iters": {"type": "integer"},
                "override_json": {"type": "string", "description": "参数覆盖 JSON 字符串（可选）"},
            },
            "required": ["source"],
        },
    },
]


def _handle_tool(name: str, args: dict):
    if name == "list_engines":
        return {
            "engines": all_names(),
            "available_now": available_names(),
            "midas_status": midas.describe(),
        }

    if name == "solve_once":
        p = DesignParams(
            span=float(args.get("span_m", 6.0)),
            wll=float(args.get("wll_knm", 20.0)),
            fc=float(args.get("fc_mpa", 30.0)),
            fy=float(args.get("fy_mpa", 300.0)),
            section_b=float(args.get("section_b", 200.0)),
            section_h=float(args.get("section_h", 300.0)),
            as_area=float(args.get("as_area", 1256.0)),
        )
        r = get(args.get("engine", "FormulaEngine")).solve(p)
        return {
            "engine": r.engine,
            "stress_ratio": r.stress_ratio,
            "deflection_mm": r.deflection_mm,
            "ok": r.ok,
            "log": r.log,
        }

    if name == "run_maca_agent":
        engine = args.get("engine", "FormulaEngine")
        max_iters = int(args.get("max_iters", 6))
        report = Agent(AIDecider(), engine=engine, max_iters=max_iters).run(args.get("book_text", ""))
        return {
            "converged": report.converged,
            "reason": report.reason,
            "final_section": report.final_result,
            "final_stress_ratio": report.final_stress_ratio,
            "final_deflection_mm": report.final_deflection_mm,
            "steps": [
                {
                    "step": s.step,
                    "section_label": s.section_label,
                    "stress_ratio": s.stress_ratio,
                    "deflection_mm": s.deflection_mm,
                    "ok": s.ok,
                    "engine": s.engine,
                    "suggestion": s.suggestion,
                }
                for s in report.steps
            ],
        }

    if name == "run_harness":
        from harness_runner import run_harness
        override = None
        oj = args.get("override_json")
        if oj:
            override = json.loads(oj).get("param_overrides", {})
        run = run_harness(
            source=args.get("source", ""),
            engine=args.get("engine", "MIDAS(NX)"),
            max_iters=int(args.get("max_iters", 6)),
            override=override,
        )
        return run.to_json()

    return {"error": f"unknown tool {name}"}


def _dispatch(request: dict) -> dict | None:
    method = request.get("method")
    rid = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "maca-midas-mcp", "version": "1.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        result = _handle_tool(name, args)
        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]}}
    if method in ("notifications/initialized", "notifications/initialized"):
        return None
    # 未知方法：仅带 id 的才回错误
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _dispatch(req)
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
