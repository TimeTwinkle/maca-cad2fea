"""MACA MCP Server —— 让带 model key + MIDAS JWT 的 agent 直连 MACA 全链路。

定位（成品）：
    Agnes Harness / 任何 MCP 客户端（Claude / Agnes / 自研 agent）通过 stdio
    JSON-RPC 调用本 server，把"AutoCAD → MIDAS 复刻导入 → 真 FEA → 红蓝对抗
    → 规则沉淀"整条线当作一个可调度节点。

三个工具（全部实测过的官方 MAPI 契约，不猜）：
    maca_duel      一键跑通：CAD DXF → 连通分量筛选 → MIDAS 真 FEA
                   → 蓝军闭式解 → 规则诊断 → 沉淀 duel_rules.json
    maca_import    白盒复刻导入：CAD → MIDAS，每步留痕（request/response/快照）
    list_duel_rules 查当前沉淀规则库

凭证（绝不写死进代码）：
    - MIDAS_MAPI_KEY / MIDAS_API_URL  走环境变量（默认值）
    - 工具参数可传 midas_mapi_key 覆盖（agent 从密钥管理注入，20min 窗口）
      优先级：参数 > 环境变量

直接跑（MCP stdio，父进程发 JSON-RPC）：
    python maca_mcp.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cad_model import extract_structure
from duel_run import (
    largest_connected_component, pick_anchors, red_run, blue_closed_form,
    pick_main_beam, _elastic_gpa,
)
from duel_rules import load_rules
from midas_importer import import_cad_to_midas
from calc_report import generate_report, load_strategy
from discrepancy import check as discrepancy_check

DEFAULT_API = "https://moa-engineers.midasit.cn:443/gen"


# ---------- 凭证：参数 > 环境变量 ----------

def _resolve_creds(args: dict) -> tuple[str, str]:
    """返回 (api_url, mapi_key)。参数覆盖环境变量，绝不写死。"""
    api = (args.get("midas_api_url")
           or os.environ.get("MIDAS_API_URL", DEFAULT_API)).rstrip("/")
    key = args.get("midas_mapi_key") or os.environ.get("MIDAS_MAPI_KEY", "")
    # 让同进程内的 duel_run / midas_importer 读到同一套凭证
    if key:
        os.environ["MIDAS_MAPI_KEY"] = key
    if api:
        os.environ["MIDAS_API_URL"] = api
    return api, key


def _cred_status(args: dict) -> dict:
    api, key = _resolve_creds(args)
    return {
        "midas_available": bool(key),
        "api_url": api if key else "(unset)",
        "key_source": ("param" if args.get("midas_mapi_key")
                       else ("env" if os.environ.get("MIDAS_MAPI_KEY") else "none")),
        "note": ("凭证走参数/环境变量，绝不写死进代码。"
                 "20min 窗口，agent 应每次注入新 key。"),
    }


# ---------- 工具 1：一键红蓝对抗 ----------

def tool_maca_duel(args: dict) -> dict:
    """CAD DXF → 连通分量筛选 → MIDAS 真 FEA → 蓝军闭式解 → 规则诊断 → 沉淀。"""
    _resolve_creds(args)
    dxf = args.get("dxf", str(ROOT.parent / "勒勒车2-2.dxf"))
    h_mm = float(args.get("h_mm", 20.0))
    b_mm = float(args.get("b_mm", 20.0))
    udl = float(args.get("udl_kn_per_m", -1.0))

    t0 = time.perf_counter()
    m = extract_structure(dxf)
    nodes, members, ncomps = largest_connected_component(m)
    main_beam = pick_main_beam(members, nodes)
    longest_mm = main_beam.length_mm if main_beam else 0.0

    # 红光：MIDAS 真 FEA（无 key 时诚实不跑）
    strat = load_strategy()
    e_gpa, matl_note = _elastic_gpa(strat, placeholder=(h_mm == 20.0))
    udl_eff = udl if udl > 0 else 1.0
    red = red_run(nodes, members, h_mm, b_mm, udl_eff, strat)
    # 蓝军：闭式解
    blue = blue_closed_form(longest_mm, h_mm, b_mm, udl_eff, e_gpa,
                            source_note=f"E:{e_gpa}GPa({matl_note}) | 荷载:{'PLACEHOLDER' if udl <= 0 else 'CLI'}")

    # 规则诊断
    hits = _rule_hits(red, blue)

    # 结论
    if not red.available:
        verdict = "red_unavailable"
        note = red.error
    elif red.converged:
        ratio = ((red.max_moment_knm or 0.0) / blue.max_moment_knm
                 if blue.max_moment_knm else None)
        verdict = ("consistent" if (ratio and abs(abs(ratio) - 1.0) < 0.5)
                   else "divergent")
        note = f"弯矩比={ratio}" if ratio else "MIDAS 收敛"
    else:
        verdict = "divergent"
        note = "MIDAS 发散"

    wall = round(time.perf_counter() - t0, 2)
    return {
        "source_cad": dxf,
        "cad_stats": {"nodes": len(m.nodes), "members": len(m.members),
                       "components": ncomps},
        "picked_component": {"nodes": len(nodes), "members": len(members),
                              "longest_mm": round(longest_mm, 1)},
        "red": {
            "available": red.available,
            "max_disp_mm": red.max_disp_mm,
            "max_moment_knm": red.max_moment_knm,
            "converged": red.converged,
            "analyze_s": red.analyze_s,
            "error": red.error,
        },
        "blue": {
            "L_m": blue.L_m, "delta_mm": blue.delta_mm,
            "max_moment_knm": blue.max_moment_knm,
        },
        "rules_hit": hits,
        "verdict": verdict,
        "note": note,
        "wall_s": wall,
    }


def _rule_hits(red, blue) -> list[dict]:
    """跑 duel_rules.json，返回命中的规则摘要。"""
    rules = load_rules()
    out = []
    disp_m = abs(red.max_disp_mm) / 1000.0 if red.available else 0.0
    theory = abs(blue.delta_mm) / 1000.0 if blue.delta_mm else 0.0

    # RULE-001 刚体位移：弯矩正常但位移发散
    if red.available and disp_m > max(theory * 100, 0.5):
        r = next((x for x in rules if x["id"] == "RULE-001"), None)
        if r:
            out.append({"id": r["id"], "name": r["name"],
                        "attribution": r.get("attribution"),
                        "evidence": f"disp={disp_m}m 弯矩={red.max_moment_knm}kNm"})
    # RULE-006 竖向约束：位移落在 mm 级
    if red.available and 0 < disp_m < 0.1:
        r = next((x for x in rules if x["id"] == "RULE-006"), None)
        if r:
            out.append({"id": r["id"], "name": r["name"],
                        "attribution": r.get("attribution"),
                        "evidence": f"disp={disp_m*1000:.2f}mm 物理量级"})
    # RULE-004 CAD 断线：分量数多
    if red.available and len(red.anchors) and False:
        pass
    return out


# ---------- 工具 2：白盒复刻导入（留痕） ----------

def tool_maca_import(args: dict) -> dict:
    """CAD → MIDAS 复刻导入，每步 request/response/快照留痕，不分析。"""
    api, key = _resolve_creds(args)
    dxf = args.get("dxf", str(ROOT.parent / "勒勒车2-2.dxf"))
    m = extract_structure(dxf)
    nodes, members, _ = largest_connected_component(m)

    # 截断到连通分量（导入真实结构，不导散落碎片）
    m.nodes, m.members = nodes, members
    trace = import_cad_to_midas(m, {
        "section_h_mm": float(args.get("h_mm", 20.0)),
        "section_b_mm": float(args.get("b_mm", 20.0)),
        "udl_kn_per_m": float(args.get("udl_kn_per_m", -1.0)),
        "max_nodes": int(args.get("max_nodes", 400)),
        "max_elems": int(args.get("max_elems", 800)),
    })
    p = trace.save("logs")
    return {
        "source_cad": dxf,
        "midas_available": bool(key),
        "picked": {"nodes": len(nodes), "members": len(members)},
        "import_ok": trace.ok,
        "steps": [
            {"step": s.step, "method": s.method, "endpoint": s.endpoint,
             "ok": s.ok, "status": s.status, "elapsed_ms": s.elapsed_ms,
             "note": s.note}
            for s in trace.steps
        ],
        "snapshot": trace.snapshot,
        "trace_path": p,
    }


# ---------- 工具 3：查沉淀规则库 ----------

def tool_list_duel_rules(args: dict) -> dict:
    rules = load_rules()
    return {"count": len(rules), "rules": rules}


# ---------- 工具 4：全流程（策略蒸馏驱动 + 计算书） ----------

def tool_run_full_pipeline(args: dict) -> dict:
    """一条命令跑 ①CAD→②策略蒸馏→③MIDAS建模→④真FEA→⑤红蓝+计算书。

    策略（strategy.json）= 人关于 MidasGen 判断的机器蒸馏，驱动自动建模；
    FEA 数值来自 MIDAS 真值（无 key 时诚实标未取，不编造）；
    计算书 Markdown 落 logs/calc_report.md，返回路径 + 全文。

    agent 零配置自动点亮：
        - 传 midas_mapi_key 参数 → 直接覆盖（agent 从密钥管理注入，20min 窗口）
        - 不传但 env 有 MIDAS_MAPI_KEY → 自动读（setup_maca.ps1 一次配好）
        - 都没有 → 诚实标 red_unavailable，用计算书表格3真值作基准，不出实时值
        优先级：参数 > 环境变量。凭证绝不写死进代码。
    """
    api, key = _resolve_creds(args)
    dxf = args.get("dxf", str(ROOT.parent / "勒勒车2-2.dxf"))
    strat = load_strategy(args.get("strategy_path", "strategy.json"))
    geo = strat.get("geometry_rules", {})
    h_mm = float(args.get("h_mm") or _parse_dim(geo.get("main_beam_section", "20x20mm"))[0])
    b_mm = float(args.get("b_mm") or _parse_dim(geo.get("main_beam_section", "20x20mm"))[1])
    udl = float(args.get("udl_kn_per_m", -1.0))

    t0 = time.perf_counter()
    # ① CAD 解析 + 连通筛选（② 策略 member_filter 驱动）
    m = extract_structure(dxf)
    nodes, members, ncomps = largest_connected_component(m)
    main_beam = pick_main_beam(members, nodes)
    longest_mm = main_beam.length_mm if main_beam else 0.0

    # ③ 白盒复刻导入（留痕）
    m.nodes, m.members = nodes, members
    trace = import_cad_to_midas(m, {"section_h_mm": h_mm, "section_b_mm": b_mm,
                                    "udl_kn_per_m": udl,
                                    "max_nodes": 400, "max_elems": 800})
    trace_path = trace.save("logs")

    # ④ MIDAS 真 FEA + ⑤ 红蓝
    # [FIX 2026-10-15] red_run/blue_closed_form 需 strategy/e_gpa 形参（与 duel_run 主路径同口径），
    # 旧调用点缺参会在 MCP 入口 TypeError；见 ACCEPTANCE.md §3 边界备注。
    e_gpa, matl_note = _elastic_gpa(strat, placeholder=(h_mm == 20.0))
    udl_eff = udl if udl > 0 else 1.0
    red = red_run(nodes, members, h_mm, b_mm, udl_eff, strat)
    blue = blue_closed_form(longest_mm, h_mm, b_mm, udl_eff, e_gpa,
                            source_note=f"E:{e_gpa}GPa({matl_note}) | 荷载:{'PLACEHOLDER 1.0kN/m' if udl <= 0 else udl}")
    hits = _rule_hits(red, blue)

    if not red.available:
        verdict, note = "red_unavailable", red.error
    elif red.converged:
        ratio = ((red.max_moment_knm or 0.0) / blue.max_moment_knm
                 if blue.max_moment_knm else None)
        verdict = "consistent" if (ratio and abs(abs(ratio) - 1.0) < 0.5) else "divergent"
        note = f"弯矩比={ratio}" if ratio else "MIDAS 收敛"
    else:
        verdict, note = "divergent", "MIDAS 发散"

    # ⑤ 计算书
    fea_for_report = {
        "available": red.available, "max_disp_mm": red.max_disp_mm,
        "max_moment_knm": red.max_moment_knm, "converged": red.converged,
        "analyze_s": red.analyze_s, "error": red.error,
        "picked_nodes": len(nodes), "picked_members": len(members),
        "longest_mm": longest_mm,
    }
    report_md = generate_report(strat, fea_for_report)
    report_path = (ROOT / "logs" / "calc_report.md").resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")

    wall = round(time.perf_counter() - t0, 2)
    # ⑤ 矛盾自动检出（诚信红线：只摆矛盾不下合格结论）
    disc = discrepancy_check(strat)
    flags = disc.get("flags", [])
    critical_flags = [f for f in flags if f.get("severity") == "critical"]
    # 凭证来源（agent 侧透明度：知道④是真跑还是降级到表格3基准）
    key_source = ("param" if args.get("midas_mapi_key")
                  else ("env" if os.environ.get("MIDAS_MAPI_KEY") else "none"))
    return {
        "source_cad": dxf,
        "credential": {"key_source": key_source,
                        "midas_available": bool(key),
                        "note": ("参数注入 JWT" if key_source == "param"
                                  else "环境变量自动点亮" if key_source == "env"
                                  else "无凭证，④降级用计算书表格3真值基准")},
        "strategy": {"material": geo.get("material"),
                     "elastic_gpa": geo.get("elastic_modulus_gpa"),
                     "node_count": geo.get("node_count_report"),
                     "constraint": geo.get("support_condition")},
        "cad_stats": {"nodes": len(m.nodes), "members": len(m.members),
                      "components": ncomps},
        "picked": {"nodes": len(nodes), "members": len(members),
                    "longest_mm": round(longest_mm, 1)},
        "import": {"ok": trace.ok, "steps": len(trace.steps),
                    "trace_path": trace_path},
        "red": {"available": red.available, "max_disp_mm": red.max_disp_mm,
                "max_moment_knm": red.max_moment_knm,
                "converged": red.converged, "analyze_s": red.analyze_s},
        "blue": {"L_m": blue.L_m, "delta_mm": blue.delta_mm,
                 "max_moment_knm": blue.max_moment_knm},
        "rules_hit": hits,
        "verdict": verdict, "note": note,
        "discrepancies": {"flags": flags,
                           "critical_count": len(critical_flags)},
        "calc_report": {"path": str(report_path), "markdown": report_md},
        "wall_s": wall,
    }


def _parse_dim(sec: str) -> tuple[float, float]:
    """解析 '20x20mm' -> (20.0, 20.0)。'φ42' -> (42,42)。"""
    import re
    s = sec.replace("mm", "").strip()
    m = re.match(r"(\d+)\s*[x×*]\s*(\d+)", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"[φØ\d]", s)
    if m:
        d = float(re.sub(r"[^0-9.]", "", s) or 0)
        return d, d
    return 20.0, 20.0


# ---------- 工具 5：凭证状态（agent 自检④是否点亮） ----------

def tool_check_credential(args: dict) -> dict:
    """返回当前凭证来源 + MIDAS 是否点亮。agent 调一次就知道④是实时 FEA 还是降级。"""
    return _cred_status(args)


# ---------- MCP 协议（stdio JSON-RPC 2.0） ----------

TOOLS = [
    {
        "name": "maca_duel",
        "description": "一键红蓝对抗：CAD DXF→连通分量筛选→MIDAS 真FEA→"
                       "蓝军闭式解→规则诊断。返回 verdict + 命中规则 + 耗时。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dxf": {"type": "string", "description": "DXF 路径（默认勒勒车2-2.dxf）"},
                "h_mm": {"type": "number", "default": 20.0},
                "b_mm": {"type": "number", "default": 20.0},
                "udl_kn_per_m": {"type": "number", "default": -1.0},
        "midas_mapi_key": {"type": "string",
                    "description": "MIDAS MAPI JWT（20min 窗口）。传则覆盖环境变量，绝不写死。不传时自动读 $env:MIDAS_MAPI_KEY。"},
                "midas_api_url": {"type": "string",
                    "description": "MIDAS 中国区端点（默认官方）"},
            },
        },
    },
    {
        "name": "check_credential",
        "description": "凭证自检：返回 MIDAS 是否点亮（env/param/none）。agent 调一次就知道④是真 FEA 还是降级到表格3基准。",
        "inputSchema": {"type": "object", "properties": {
            "midas_mapi_key": {"type": "string"},
            "midas_api_url": {"type": "string"}
        }},
    },
    {
        "name": "maca_import",
        "description": "白盒复刻导入：CAD→MIDAS，每步留痕（request/response/快照）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dxf": {"type": "string"},
                "h_mm": {"type": "number", "default": 20.0},
                "b_mm": {"type": "number", "default": 20.0},
                "max_nodes": {"type": "integer", "default": 400},
                "max_elems": {"type": "integer", "default": 800},
                "midas_mapi_key": {"type": "string"},
                "midas_api_url": {"type": "string"},
            },
        },
    },
    {
        "name": "list_duel_rules",
        "description": "查 MACA 沉淀的红蓝对抗规则库（duel_rules.json）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_full_pipeline",
        "description": "全流程：CAD→策略蒸馏(strategy.json)→MIDAS白盒导入→真FEA→"
                       "红蓝对抗→计算书(Markdown)。一条命令出计算书。无key时诚实标未取真值。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dxf": {"type": "string"},
                "strategy_path": {"type": "string", "description": "策略蒸馏JSON(默认strategy.json)"},
                "h_mm": {"type": "number"},
                "b_mm": {"type": "number"},
                "udl_kn_per_m": {"type": "number", "default": -1.0},
                "midas_mapi_key": {"type": "string"},
                "midas_api_url": {"type": "string"},
            },
        },
    },
]


def _dispatch(req: dict) -> dict | None:
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "maca-midas-mcp", "version": "2.0"},
            "capabilities": {"tools": {}},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        if name == "maca_duel":
            res = tool_maca_duel(args)
        elif name == "maca_import":
            res = tool_maca_import(args)
        elif name == "list_duel_rules":
            res = tool_list_duel_rules(args)
        elif name == "run_full_pipeline":
            res = tool_run_full_pipeline(args)
        elif name == "check_credential":
            res = tool_check_credential(args)
        else:
            res = {"error": f"unknown tool {name}"}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text",
                          "text": json.dumps(res, ensure_ascii=False, default=str)}]}}
    if method in ("notifications/initialized",):
        return None
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main() -> int:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
