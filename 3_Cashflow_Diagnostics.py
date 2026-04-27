"""Cashflow log diagnostics — parse a waterfall log and explain cashflows."""
from __future__ import annotations

import streamlit as st

from cmbs import config, visualizations as viz
from cmbs.cashflow_analyzer import CashflowAnalyzer

st.set_page_config(page_title="Cashflow Diagnostics", page_icon="💧", layout="wide")
st.title("💧 Cashflow Diagnostics")
st.caption("Parse a waterfall log, spot anomalies, and get Claude's explanation of why each period paid the way it did.")

# ---- source ----
with st.sidebar:
    st.subheader("Waterfall log")
    upload = st.file_uploader("Upload a log file (.txt / .log)", type=["txt", "log"])
    if upload is not None:
        text = upload.read().decode("utf-8", errors="ignore")
        ca = CashflowAnalyzer.from_text(text)
        st.success(f"Parsed {len(ca.snapshots)} periods from upload")
    else:
        ca = CashflowAnalyzer.from_file(config.MOCK_CASHFLOW_LOG)
        st.info(f"Using synthetic log ({len(ca.snapshots)} periods)")

summary = ca.summary()

# ---- KPIs ----
k = st.columns(5)
k[0].metric("Periods", summary["periods_parsed"])
k[1].metric("Total Interest", f"${summary['total_interest_distributed']/1e6:,.2f}M")
k[2].metric("Total Principal", f"${summary['total_principal_distributed']/1e6:,.2f}M")
k[3].metric("Cum. Loss", f"${summary['final_cumulative_loss']/1e6:,.2f}M")
k[4].metric("Event Periods", summary["event_periods"])

st.divider()

rem = ca.remittance_frame()
tranches = ca.tranche_frame()
events = ca.events_frame()

# ---- Charts ----
st.plotly_chart(viz.cashflow_over_time(rem), use_container_width=True)

c1, c2 = st.columns(2)
c1.plotly_chart(viz.prepayment_timeline(rem), use_container_width=True)
c2.plotly_chart(viz.losses_bar(rem), use_container_width=True)

st.plotly_chart(viz.tranche_balance_over_time(tranches), use_container_width=True)
st.plotly_chart(viz.tranche_interest_paid(tranches), use_container_width=True)
st.plotly_chart(viz.event_timeline(events), use_container_width=True)

st.divider()

# ---- Anomalies ----
st.subheader("⚠️ Anomalies")
anoms = ca.anomalies()
st.dataframe(
    anoms[["period", "distribution_date", "reason", "events"]]
    if not anoms.empty else anoms,
    use_container_width=True, hide_index=True,
)

st.divider()

# ---- Explain period ----
st.subheader("🧠 Why did this period pay the way it did?")
period_ids = [s.period for s in ca.snapshots]
col_a, col_b = st.columns([1, 3])
with col_a:
    chosen = st.selectbox("Period", period_ids, index=min(13, len(period_ids) - 1))
    explain = st.button("Ask Claude", type="primary")

with col_b:
    if explain:
        with st.spinner("Claude reviewing the log…"):
            resp = ca.explain_period(chosen)
        if resp.stub:
            st.info(resp.text)
        else:
            st.markdown(resp.text)
    else:
        snap = next(s for s in ca.snapshots if s.period == chosen)
        st.markdown(f"**Period {snap.period} — {snap.distribution_date}**")
        st.markdown(f"- Pool balance BOP: `${snap.pool_balance_bop:,.2f}`")
        st.markdown(f"- Interest: `${snap.scheduled_interest:,.2f}`  "
                    f"· Principal: `${snap.scheduled_principal:,.2f}`  "
                    f"· Prepay: `${snap.prepayments:,.2f}`  "
                    f"· Liquidation: `${snap.liquidation_proceeds:,.2f}`  "
                    f"· Loss: `${snap.realized_loss:,.2f}`")
        if snap.events:
            st.markdown("**Events:**")
            for e in snap.events:
                st.markdown(f"- {e}")
        else:
            st.markdown("_(no trigger events)_")

# ---- Metric narrative ----
st.subheader("🧠 Narrative across the full history")
metric = st.selectbox("Metric to narrate",
                       ["cumulative losses", "prepayments", "interest distribution",
                        "tranche interest shortfalls", "principal amortization pattern"])
if st.button("Generate narrative"):
    with st.spinner("…"):
        resp = ca.explain_metric(metric)
    if resp.stub:
        st.info(resp.text)
    else:
        st.markdown(resp.text)

with st.expander("Raw log"):
    st.code(ca.raw[:6000] + ("\n…(truncated)" if len(ca.raw) > 6000 else ""))
