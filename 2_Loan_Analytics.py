"""Loan tape drill-down — filter, risk-flag, chart."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cmbs import config, visualizations as viz
from cmbs.loan_analyzer import LoanAnalyzer

st.set_page_config(page_title="Loan Analytics", page_icon="🏘️", layout="wide")
st.title("🏘️ Loan Analytics")

# ---- data source ----
with st.sidebar:
    st.subheader("Data source")
    uploaded = st.file_uploader("Upload a loan tape (CSV)", type=["csv"])
    if uploaded is not None:
        loans = pd.read_csv(uploaded)
        st.success(f"Loaded {len(loans)} loans from upload")
    else:
        loans = pd.read_csv(config.MOCK_LOAN_TAPE)
        st.info(f"Using synthetic tape ({len(loans)} loans)")

# ---- filters ----
st.sidebar.subheader("Filters")
types = st.sidebar.multiselect("Property type", sorted(loans["property_type"].unique()),
                                default=sorted(loans["property_type"].unique()))
states = st.sidebar.multiselect("State", sorted(loans["state"].unique()),
                                 default=sorted(loans["state"].unique()))
dscr_range = st.sidebar.slider("DSCR", 0.5, 3.5, (0.5, 3.5), 0.05)
ltv_range = st.sidebar.slider("LTV %", 0, 100, (0, 100), 1)

f = loans[
    loans["property_type"].isin(types)
    & loans["state"].isin(states)
    & loans["dscr_ncf"].between(*dscr_range)
    & loans["ltv_pct"].between(*ltv_range)
]

# ---- KPIs ----
la = LoanAnalyzer.from_df(f)
s = la.pool_summary()
k = st.columns(5)
k[0].metric("Loans (filtered)", s["loan_count"])
k[1].metric("Balance", f"${s['total_balance']/1e6:,.1f}M")
k[2].metric("WA DSCR", f"{s['wa_dscr']:.2f}x")
k[3].metric("WA LTV", f"{s['wa_ltv_pct']:.1f}%")
k[4].metric("Sub-1x DSCR", s["sub_1x_dscr_count"])

st.divider()

# ---- Charts ----
c1, c2 = st.columns(2)
c1.plotly_chart(viz.property_type_mix(f), use_container_width=True)
c2.plotly_chart(viz.state_mix(f), use_container_width=True)

st.plotly_chart(viz.top_loans_bar(f, n=10), use_container_width=True)
st.plotly_chart(viz.maturity_ladder(f), use_container_width=True)

st.divider()

# ---- Risk flags ----
st.subheader("🚩 Risk flags")
flags = la.risk_flags()
st.dataframe(
    flags.style.format({"current_balance": "${:,.0f}"})
    .background_gradient(subset=["flag_count"], cmap="Reds"),
    use_container_width=True, hide_index=True,
)

# ---- Commentary ----
st.subheader("🧠 Claude's take")
if st.button("Generate commentary on filtered pool"):
    with st.spinner("Writing credit memo…"):
        resp = la.expert_commentary()
    if resp.stub:
        st.info(resp.text)
    else:
        st.markdown(resp.text)

# ---- Raw tape ----
with st.expander(f"Full loan tape ({len(f)} loans)"):
    st.dataframe(f, use_container_width=True, hide_index=True)
