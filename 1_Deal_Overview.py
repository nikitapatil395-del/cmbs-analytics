"""Deal overview — capital structure, pool metrics, expert commentary."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from cmbs import config, visualizations as viz
from cmbs.loan_analyzer import LoanAnalyzer

st.set_page_config(page_title="Deal Overview", page_icon="📊", layout="wide")

st.title("📊 Deal Overview")

loans = pd.read_csv(config.MOCK_LOAN_TAPE)
bonds = pd.read_csv(config.MOCK_BOND_STRUCTURE)
deal = json.loads(Path(config.MOCK_DEAL_META).read_text())
la = LoanAnalyzer.from_df(loans, name=deal["deal_name"])
summary = la.pool_summary()

# --- KPIs ---
k = st.columns(6)
k[0].metric("Pool Balance", f"${summary['total_balance']/1e6:,.1f}M")
k[1].metric("Loans", f"{summary['loan_count']}")
k[2].metric("WA Rate", f"{summary['wa_note_rate_pct']:.3f}%")
k[3].metric("WA DSCR", f"{summary['wa_dscr']:.2f}x")
k[4].metric("WA LTV", f"{summary['wa_ltv_pct']:.1f}%")
k[5].metric("Watchlist", f"{summary['watchlist_count']}")

st.divider()

# --- Parties & Dates ---
col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("Transaction Parties")
    for k_ in ["issuer", "trustee", "master_servicer", "special_servicer", "certificate_administrator"]:
        st.markdown(f"**{k_.replace('_', ' ').title()}:** {deal[k_]}")
    st.markdown(f"**Rating Agencies:** {', '.join(deal['rating_agencies'])}")

    st.subheader("Key Dates")
    for k_ in ["cutoff_date", "closing_date", "first_payment_date",
               "expected_final_distribution", "rated_final_distribution"]:
        st.markdown(f"**{k_.replace('_', ' ').title()}:** {deal[k_]}")

with col2:
    st.plotly_chart(viz.capital_stack(bonds), use_container_width=True)
    st.dataframe(
        bonds[["class_name", "balance", "coupon_pct", "rating_moodys",
               "rating_fitch", "rating_kbra", "credit_support_pct", "wal_years"]]
        .style.format({
            "balance": "${:,.0f}",
            "coupon_pct": "{:.3f}%",
            "credit_support_pct": "{:.2f}%",
            "wal_years": "{:.1f}",
        }),
        use_container_width=True, hide_index=True,
    )

st.divider()

# --- Charts ---
c1, c2 = st.columns(2)
c1.plotly_chart(viz.property_type_mix(loans), use_container_width=True)
c2.plotly_chart(viz.geo_choropleth(loans), use_container_width=True)

c3, c4 = st.columns(2)
c3.plotly_chart(viz.dscr_histogram(loans), use_container_width=True)
c4.plotly_chart(viz.ltv_histogram(loans), use_container_width=True)

st.plotly_chart(viz.dscr_vs_ltv(loans), use_container_width=True)

st.divider()

# --- Expert commentary ---
st.subheader("🧠 Claude's Credit Memo")
if st.button("Generate expert commentary", type="primary"):
    with st.spinner("Drafting credit memo…"):
        resp = la.expert_commentary()
    if resp.stub:
        st.info(resp.text)
    else:
        st.markdown(resp.text)
        if resp.citations:
            st.caption("Sources: " + ", ".join(resp.citations))
