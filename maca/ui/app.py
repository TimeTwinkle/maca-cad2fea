"""MACA Streamlit 前端（杀手锏级 Demo 界面）。

三栏布局（对应答辩演示脚本）：
    左：原始计算书（乱糟糟的文本）
    中：AI 实时思考日志（逐条滚动，含每步应力比/建议）
    右：应力比随迭代的折线图 + 引擎对比（PyNite 绿·MIDAS 灰待接入）

启动：
    cd maca
    streamlit run ui/app.py
"""

import sys
from pathlib import Path

import streamlit as st

# 让 maca 包路径可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adapters  # noqa: F401  注册引擎
import examples_lib
from core import Agent
from core.solver import get, all_names
from ai.decider import AIDecider, llm_enabled


def _engine_badge(name: str) -> str:
    """引擎状态色标。"""
    s = get(name)
    if not s.is_available():
        return f"⚪ {name}（未接入/回退）"
    return f"🟢 {name}"


st.set_page_config(page_title="MACA · 多模式 AI 计算自动化引擎", page_icon="🏗", layout="wide")

st.title("🏗 MACA — 多模式 AI 计算自动化引擎")
st.caption("大模型作中枢 + 标准化接口对接一切计算引擎（MIDAS / PyNite / 理论公式）")

# ── 侧栏：引擎选择 + 计算书输入 ───────────────────────────────
with st.sidebar:
    st.subheader("⚙️ 配置")
    engines = [n for n in all_names()]
    default_engine = "FormulaEngine" if "FormulaEngine" in engines else engines[0]
    engine = st.selectbox(
        "求解引擎（可插拔）",
        options=engines,
        index=engines.index(default_engine),
        help="切换引擎上层逻辑零改动 —— 这正是'多模式范式'的核心",
    )
    max_iters = st.slider("最大迭代次数", 1, 10, 6)

    st.subheader("📄 计算书输入")
    book_text = st.text_area(
        "粘贴计算书（或留空用示例）",
        value=examples_lib.SAMPLE,
        height=200,
    )

    if st.button("▶️ AI 解析与迭代", type="primary"):
        text = book_text.strip() or examples_lib.SAMPLE
        agent = Agent(AIDecider(), engine=engine, max_iters=max_iters)
        report = agent.run(text)
        st.session_state["report"] = report

report = st.session_state.get("report")

# ── 主区：三栏 ─────────────────────────────────────────────────
col_l, col_m, col_r = st.columns([1, 1.2, 1.2])

# 左：原始计算书
with col_l:
    st.subheader("📄 原始计算书")
    text = st.session_state.get("book_text", "")
    st.code(text or "(未提供)", language="text")
    if report:
        p = report.design_params
        st.markdown("**AI 解析出的结构化参数**")
        st.json(p.to_json())

# 中：AI 思考日志
with col_m:
    st.subheader("🧠 AI 思考日志")
    decider = AIDecider()
    st.caption(f"决策器：{decider.name}（{'大模型 Agnes' if llm_enabled() else '规则 fallback（离线可跑）'}）")
    if not report:
        st.info("点击左上「▶️ AI 解析与迭代」开始")
    else:
        for s in report.steps:
            flag = "✅" if s.ok else "⚠️"
            st.markdown(
                f"**[step {s.step}]** {s.section_label} · 应力比={s.stress_ratio} · δ={s.deflection_mm}mm {flag}\n"
                f"> 建议：{s.suggestion}"
            )
        st.success(
            f"**收敛**：{report.reason}，最终截面 {report.design_params.section_label()}，"
            f"{report.final_result.summary()}"
        )

# 右：折线图 + 引擎对比
with col_r:
    st.subheader("📈 迭代曲线 & 引擎对比")
    if report and report.steps:
        import plotly.graph_objects as go

        xs = [s.step for s in report.steps]
        sr = [s.stress_ratio for s in report.steps]
        df = [s.deflection_mm for s in report.steps]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=sr, name="应力比", mode="lines+markers",
            line=dict(color="#e15759"),
        ))
        fig.add_trace(go.Scatter(
            x=xs, y=df, name="挠度(mm)", mode="lines+markers",
            line=dict(color="#4e79a7"),
        ))
        # 应力比限值线
        fig.add_hline(y=1.0, line_dash="dot", line_color="red", annotation_text="利用率限值=1.0")
        fig.update_layout(height=320, title="每步应力比 & 挠度", xaxis_title="迭代步", yaxis_title="值")
        st.plotly_chart(fig, use_container_width=True)

    # 引擎对比卡
    st.markdown("**引擎可插拔对比**")
    for n in all_names():
        st.write(_engine_badge(n))

    # 引擎切换说明
    st.caption("🟢 PyNite=真实开源 FEA · ⚪ MIDAS(NX)=填 MAPI-Key 即接入商业软件（架构不变）")

# ── 底部：答辩话术 ────────────────────────────────────────────
with st.expander("💡 评委提问应答（内置话术）"):
    st.markdown(
        "**问：为什么不用 MIDAS 做 Demo？**\n"
        "> 我们在探索一种**不依赖单一商业软件授权的通用范式**。MIDAS 只是适配器之一，"
        "今天用开源 PyNite/理论公式跑通逻辑，填入 MAPI-Key 即可无缝迁移到商业软件。"
    )
    st.markdown(
        "**问：核心创新点？**\n"
        "> **解耦与泛化**。大模型作中枢，标准化接口对接一切计算引擎，"
        "把'算得准'从单一软件抽离成 AI 可调度的服务。"
    )
