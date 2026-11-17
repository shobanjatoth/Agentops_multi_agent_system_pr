"""
Streamlit observability dashboard.

Run with: streamlit run dashboard/dashboard_app.py

Reads the same SQLite DB the FastAPI app writes to, so it shows live
data with no extra wiring — this is the piece that turns "an agent that
runs" into "a system someone can operate," which is exactly the gap the
2026 hiring market is short on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from app.eval_tracker import dashboard_query, dashboard_tasks

st.set_page_config(page_title="AgentOps Dashboard", layout="wide")
st.title("AgentOps — Live Observability Dashboard")

traces = pd.DataFrame(dashboard_query())
tasks = pd.DataFrame(dashboard_tasks())

if traces.empty:
    st.info("No traces yet. Send a task to the API (`POST /tasks`) to see data here.")
    st.stop()

# ---- top-line metrics ----
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total tasks", len(tasks))
col2.metric("Total cost (USD)", f"${traces['cost_usd'].sum():.4f}")
col3.metric("Avg latency / step (ms)", f"{traces['latency_ms'].mean():.0f}")
pass_rate = traces["passed"].mean() * 100 if len(traces) else 0
col4.metric("Step pass rate", f"{pass_rate:.1f}%")
if not tasks.empty and "status" in tasks.columns:
    approval_pending = len(tasks[tasks["status"] == "awaiting_approval"])
    col5.metric("⏳ Pending approvals", approval_pending)
else:
    col5.metric("⏳ Pending approvals", 0)

st.divider()

# ---- latency & cost by node ----
c1, c2 = st.columns(2)
with c1:
    st.subheader("Avg latency by node")
    st.bar_chart(traces.groupby("node")["latency_ms"].mean())
with c2:
    st.subheader("Total cost by node")
    st.bar_chart(traces.groupby("node")["cost_usd"].sum())

st.divider()

# ---- injection flagged tasks ----
st.subheader("🛡️ Security events — prompt injection flagged")
injection_traces = traces[traces["node"] == "research.security"] if not traces.empty else pd.DataFrame()
if injection_traces.empty:
    st.caption("✅ No injection attempts detected.")
else:
    st.warning(f"⚠️ {len(injection_traces)} potential prompt injection attempt(s) detected!")
    st.dataframe(
        injection_traces[["task_id", "input_summary", "output_summary", "created_at"]],
        use_container_width=True
    )

st.divider()

# ---- tasks awaiting human approval ----
st.subheader("Tasks awaiting human approval")
pending = tasks[tasks["status"] == "awaiting_approval"] if not tasks.empty else pd.DataFrame()
if pending.empty:
    st.caption("None right now.")
else:
    st.dataframe(pending[["id", "description", "created_at"]], use_container_width=True)

st.divider()

# ---- raw trace table ----
st.subheader("Recent agent steps")
st.dataframe(
    traces[
        ["task_id", "node", "latency_ms", "input_tokens", "output_tokens", "cost_usd", "passed", "created_at"]
    ],
    use_container_width=True,
)
