"""MACA Harness 现场管理页（Agnes + Harness 深度绑定版）。

定位：
    - 五段流水线 Intake / Agent / Engine / Tool / Report 可视化；
    - 一键运行 Harness Runner，出审计 JSON；
    - 10 分钟预算 + MIDAS 真值状态 + 收敛结果。

启动：
    cd D:\AIToolboxConsole\新建文件夹\maca
    streamlit run ui/harness_demo_app.py
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
from harness_runner import run_harness
from harness_audit import load_audit, audit_summary
from core.solver import all_names

st.set_page_config(page_title="MACA Harness Demo", page_icon="⚙️", layout="wide")
st.title("⚙️ MACA Harness Runner：Agnes + Harness 五段流水线")
st.caption("Intake → Agent → Engine → Tool → Report；可审计、可复用、可被 Graph/Loop 调度。")

left, mid, right = st.columns([1.0, 1.2, 0.95])

with left:
    st.subheader("1⃣ 输入")
    source = st.text_input("来源（DXF / 参数 JSON / 计算书 txt）", value=str(ROOT.parent / "勒勒车2-2.dxf"))
    engine = st.selectbox("引擎", all_names(), index=all_names().index("MIDAS(NX)") if "MIDAS(NX)" in all_names() else 0)
    max_iters = st.slider("最大迭代", 1, 8, 6)
    use_override = st.checkbox("使用 demo_params.json 覆盖参数", value=True)
    run = st.button("▶ 运行 Harness 五段流水线", type="primary")

with mid:
    st.subheader("2⃣ 五段流水线")
    if run:
        t0 = time.time()
        override = None
        if use_override:
            pj = ROOT / "demo_params.json"
            if pj.exists():
                override = json.loads(pj.read_text(encoding="utf-8")).get("param_overrides", {})
        hrun = run_harness(source, engine=engine, max_iters=max_iters, override=override, out_dir=ROOT / "logs")
        st.session_state["hrun"] = hrun
        st.session_state["wall_s"] = time.time() - t0

    hrun = st.session_state.get("hrun")
    if not hrun:
        st.info("点击左侧「运行 Harness 五段流水线」。")
    else:
        for s in hrun.stages:
            icon = "✅" if s.ok else "❌"
            st.markdown(f"{icon} **{s.stage}** — {s.duration_s}s")
        st.write(f"engine_used={hrun.engine_used} | midas_used={hrun.midas_used} | converged={hrun.converged}")
        st.json(hrun.final)
        with st.expander("审计 JSON"):
            st.json(hrun.to_json())

with right:
    st.subheader("3⃣ 审计 & 预算")
    audit = load_audit(ROOT / "logs")
    summ = audit_summary(audit)
    if summ.get("exists"):
        st.write(f"run_id={summ['run_id']} total={summ['total_s']}s")
        for s in summ["stages"]:
            st.markdown(f"- {s['stage']}: {s['duration_s']}s ok={s['ok']}")
    else:
        st.info("尚无审计记录。")

    budget = 600.0
    used = st.session_state.get("wall_s", 0.0)
    st.metric("10 分钟预算", f"{used:.2f}s / 600s")
    st.success("在预算内" if used <= budget else "超预算")
