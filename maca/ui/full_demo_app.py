"""MACA 全闭环管理页（Streamlit）。

现场定位：
    - 左侧选择来源：DXF / 参数 JSON / 计算书文本；
    - 中间一键运行全闭环；
    - 右侧展示 10 分钟时间预算、MIDAS 状态、迭代曲线与最终报告。

启动：
    cd D:\AIToolboxConsole\新建文件夹\maca
    streamlit run ui/full_demo_app.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import adapters  # noqa: F401
import demo_pipeline
from ai.decider import AIDecider
from core.solver import get, all_names

st.set_page_config(page_title="MACA 全闭环 Demo", page_icon="🏗", layout="wide")
st.title("🏗 MACA 全闭环 Demo：AutoCAD DXF → MIDAS MAPI → AI 审查迭代")
st.caption("目标：把 3 小时人工 MIDAS 建模/计算/审查流程压缩到 10 分钟内自动跑通。")

left, mid, right = st.columns([1.05, 1.15, 0.95])

with left:
    st.subheader("1️⃣ 输入来源")
    source_mode = st.radio("来源类型", ["DXF 文件", "参数覆盖 JSON", "计算书文本"], horizontal=True)

    if source_mode == "DXF 文件":
        dxf_path = st.text_input("DXF 路径", value=str(ROOT.parent / "勒勒车2-2.dxf"))
        source = dxf_path
    elif source_mode == "参数覆盖 JSON":
        json_path = st.text_input("参数 JSON 路径", value=str(ROOT / "demo_params.json"))
        source = json_path
    else:
        book_text = st.text_area("计算书文本", value="某钢筋混凝土简支梁，C30，跨度 6000mm，均布荷载 20kN/m，初始截面 250x500，要求利用率≤1.0，挠度≤20mm。", height=160)
        tmp = ROOT / "tmp_book_input.txt"
        tmp.write_text(book_text, encoding="utf-8")
        source = str(tmp)

    st.subheader("2️⃣ 参数覆盖（可选）")
    o_span = st.number_input("跨度 span_mm", value=5577.0, step=1.0, format="%.0f")
    o_b = st.number_input("截面宽 b_mm", value=250.0, step=1.0, format="%.0f")
    o_h = st.number_input("截面高 h_mm", value=500.0, step=1.0, format="%.0f")
    o_wll = st.number_input("均布荷载 kN/m", value=20.0, step=0.5, format="%.1f")
    o_mat = st.text_input("材料", value="C30")
    override = {"span_mm": o_span, "section_b": o_b, "section_h": o_h, "wll_knm": o_wll, "material": o_mat}

    engine = st.selectbox("引擎", [n for n in all_names()], index=all_names().index("MIDAS(NX)") if "MIDAS(NX)" in all_names() else 0)
    max_iters = st.slider("最大迭代次数", 1, 8, 6)

    run = st.button("▶ 运行全闭环 Demo", type="primary")

with mid:
    st.subheader("3️⃣ 运行结果")
    if run:
        t0 = time.time()
        rep = demo_pipeline.build_report(source, engine=engine, max_iters=max_iters, override=override)
        rep.html_path = demo_pipeline.save_html(rep, ROOT / "logs" / "full_demo.html")
        demo_pipeline.save_json(rep, ROOT / "logs" / "full_demo_result.json")
        st.session_state["rep"] = rep
        st.session_state["wall_s"] = time.time() - t0

    rep = st.session_state.get("rep")
    if not rep:
        st.info("点击左侧「运行全闭环 Demo」。输出会保存到 logs/full_demo_result.json 与 logs/full_demo.html。")
    else:
        ag = rep.agent_report or {}
        st.success(f"内部链路耗时 {rep.duration_s}s；页面整体响应 {round(st.session_state.get('wall_s', 0), 3)}s")
        st.write(f"来源：{rep.source} | 引擎：{rep.engine} | MIDAS configured={rep.midas_configured} | MIDAS used={rep.midas_used}")
        st.write(f"实际执行：{ag.get('engine_used')} | 收敛：{ag.get('converged')} | 原因：{ag.get('reason')}")

        st.markdown("#### 迭代日志")
        for s in ag.get("steps", []):
            st.markdown(f"- 步{s['step']}：{s['section_label']}，应力比={s['stress_ratio']}，挠度={s['deflection_mm']}mm，ok={s['ok']}，建议={s['suggestion']}")
        st.json(ag.get("final", {}))

with right:
    st.subheader("4️⃣ 10 分钟预算")
    budget = 600.0
    used = st.session_state.get("wall_s", 0.0)
    st.metric("时间预算", "10 min")
    st.metric("本次实际", f"{used:.2f} s")
    if used <= budget:
        st.success("在 10 分钟预算内完成。")
    else:
        st.warning("超过 10 分钟预算。")

    st.markdown("#### 现场说明")
    st.markdown(
        "- 有 `MIDAS_API_URL` / `MIDAS_MAPI_KEY` 时：实际走 MIDAS(NX) 官方 MAPI 真值。\n"
        "- 无凭证时：自动用 FormulaEngine 保证闭环可演示，并在报告中明确标注 `midas_used=False`。\n"
        "- 复用新模型：改 `demo_params.json` 或上传新 DXF，即可复用同一套自动迭代链路。"
    )
