"""CMBS Analytics Diagnostic Tool — Streamlit entry point.

Launch with::

    streamlit run app.py

This home page gives the user an orientation; individual feature pages live
under ``pages/`` and are auto-discovered by Streamlit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from cmbs import config
from cmbs.mock_data import generate_all


st.set_page_config(
    page_title="CMBS Analytics Diagnostic",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---- ensure sample data exists on first run ----
@st.cache_data(show_spinner="Generating synthetic deal data (first run only)…")
def _bootstrap_data():
    return generate_all(force=False)

info = _bootstrap_data()


# ---- header ----
st.title("🏢 CMBS Analytics Diagnostic Toolkit")
st.caption(
    "A Claude-powered, expert-in-the-box diagnostic tool for Commercial Mortgage-Backed "
    "Securities. Navigate to a feature in the sidebar, or start with the overview below."
)

col1, col2, col3 = st.columns(3)
deal_meta = json.loads(Path(config.MOCK_DEAL_META).read_text())
with col1:
    st.metric("Active Deal", deal_meta["deal_name"])
    st.caption(deal_meta["full_name"])
with col2:
    st.metric("Pool Balance", f"${deal_meta['total_pool_balance']/1e6:.1f}M")
    st.caption(f"{deal_meta['loan_count']} loans / {deal_meta['property_count']} properties")
with col3:
    st.metric("Deal Type", deal_meta["deal_type"])
    st.caption(f"Closing: {deal_meta['closing_date']}")


# ---- API key check ----
if not config.SETTINGS.has_llm:
    st.warning(
        "**No `ANTHROPIC_API_KEY` detected.** The tool will still render all "
        "data, parse logs, and show charts — but expert commentary, web "
        "research, and prospectus Q&A need a Claude API key.\n\n"
        "Copy `.env.example` → `.env` and fill in your key, then restart.",
        icon="🔑",
    )
else:
    st.success(f"Claude model in use: **{config.SETTINGS.model}**", icon="🧠")


# ---- feature tour ----
st.markdown("## What's inside")

feat_cols = st.columns(2)
with feat_cols[0]:
    st.markdown("""
### 📊 Deal Overview
Capital structure, pool metrics, property-type mix, geographic concentration — all
at a glance. Includes a Claude-generated credit-memo style narrative.

### 🏘️ Loan Analytics
Drill into the loan tape: top loans, DSCR/LTV distributions, maturity ladder,
interactive risk flags across 7 screens.
""")
with feat_cols[1]:
    st.markdown("""
### 💧 Cashflow Diagnostics
Upload a waterfall log (or use the built-in 36-month simulation). The parser
extracts period-by-period flows, tranche-level interest/principal/losses, and
trigger events — then Claude explains *why* a specific period flowed the way
it did.

### 📄 Prospectus Q&A
Loads the prospectus PDF, extracts parties, key dates, and pool summary, then
lets you ask free-form questions. Claude reads the PDF natively, so answers
cite actual sections.

### 🌐 Web Research
Uses Claude's web-search tool to pull live news, rating actions, and
remittance updates on any CMBS deal by name.
""")


# ---- sample data paths ----
with st.expander("Sample data files on disk"):
    for label, path in [
        ("Loan tape (CSV)", config.MOCK_LOAN_TAPE),
        ("Capital structure (CSV)", config.MOCK_BOND_STRUCTURE),
        ("Remittance summary (CSV)", config.MOCK_REMITTANCE),
        ("Waterfall log (text)", config.MOCK_CASHFLOW_LOG),
        ("Prospectus PDF", config.MOCK_PROSPECTUS),
        ("Deal metadata (JSON)", config.MOCK_DEAL_META),
    ]:
        p = Path(path)
        st.text(f"{label:<25}  {p}  ({p.stat().st_size:,} bytes)")

st.divider()
st.caption(
    "Built with Streamlit, Plotly, pdfplumber, and the Anthropic Python SDK. "
    "All loan / cashflow / prospectus data shown by default is synthetic."
)
