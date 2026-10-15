"""MACA -> MCP 桥：把求解层暴露成 MCP 工具，供 AGH / Claude / 任意 MCP 客户端调用。

设计意义（答辩用）：
    MACA 的核心是"统一求解接口 + 注册表"，
    这一层证明了同一套求解层既可以被 Streamlit UI 直接调，
    也可以被 MCP 客户端（AGH、Claude Desktop 等）当成工具调——
    "一个框架，两种入口"。

零依赖实现（不装 mcp 库也能跑）：
    用 JSON-RPC 2.0 实现 MCP 的核心 method（tools/list、tools/call），
    通过 stdio 与客户端通信。要装完整 MCP SDK 时替换为 fastmcp 即可，
    求解逻辑不变。

用法：
    python mcp_bridge.py
    （stdio 模式：客户端经 stdin/stdout 发 JSON-RPC）
"""

import json
import sys

import adapters  # noqa: F401  注册引擎
from core import Agent
from ai.decider import AIDecider
from core.solver import all_names, get

TOOLS = [
    {
        "name": "list_engines",
        "description": "列出 MACA 已注册的可插拔计算引擎及其可用状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "solve_once",
        "description": "用指定引擎对一组结构参数求解一次，返回应力比/挠度/是否满足",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "description": "引擎名，如 FormulaEngine/PyNite/MIDAS(NX)"},
                "span_mm": {"type": "number"},
                "wll_kn_m": {"type": "number"},
                "section_b_mm": {"type": "number"},
                "section_h_mm": {"type": "number"},
                "as_area_mm2": {"type": "number"},
            },
        },
    },
    {
        "name": "run_maca_agent",
        "description": "跑完整 MACA 闭环：解析计算书→AI 决策→多引擎迭代→返回收敛结果",
        "inputSchema": {
            "type": "object",
            "properties": {
                "book_text": {"type": "string", "description": "计算书自然语言文本"},
                "engine": {"type": "string"},
                "max_iters": {"type": "integer"},
            },
        },
    },
]


def _tool_result(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}]}


def handle_rpc(msg: dict) -> dict | None:
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params", {})

    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "list_engines":
            from core.models import DesignParams
            rows = []
            for n in all_names():
                s = get(n)
                rows.append({"engine": n, "available": s.is_available(), "note": s.note})
            return _ok(id_, _tool_result({"engines": rows}))

        if name == "solve_once":
            from core.models import DesignParams
            p = DesignParams(
                span=args.get("span_mm", 6000.0),
                wll=args.get("wll_kn_m", 20.0),
                section_b=args.get("section_b_mm", 250.0),
                section_h=args.get("section_h_mm", 500.0),
                as_area=args.get("as_area_mm2", 1256.0),
            )
            r = get(args.get("engine", "FormulaEngine")).solve(p)
            return _ok(id_, _tool_result({
                "engine": r.engine, "stress_ratio": r.stress_ratio,
                "deflection_mm": r.deflection_mm, "ok": r.ok, "log": r.log,
            }))

        if name == "run_maca_agent":
            agent = Agent(AIDecider(), engine=args.get("engine", "FormulaEngine"), max_iters=int(args.get("max_iters", 6)))
            rep = agent.run(args.get("book_text", ""))
            return _ok(id_, _tool_result({
                "converged": rep.converged, "reason": rep.reason,
                "final_section": rep.design_params.section_label(),
                "final_stress_ratio": rep.final_result.stress_ratio,
                "final_deflection_mm": rep.final_result.deflection_mm,
                "steps": [{"step": s.step, "section": s.section_label, "ratio": s.stress_ratio, "defl": s.deflection_mm, "ok": s.ok} for s in rep.steps],
            }))

        return _err(id_, -32602, f"未知工具 {name}")

    if method == "initialize":
        return _ok(id_, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "maca-mcp", "version": "0.1.0"}})

    return None


def _ok(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_rpc(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
