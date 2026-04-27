"""Live web research on a named CMBS deal via Claude's web_search tool."""
from __future__ import annotations

import streamlit as st

from cmbs import deal_lookup
from cmbs.config import SETTINGS

st.set_page_config(page_title="Web Research", page_icon="🌐", layout="wide")
st.title("🌐 CMBS Deal Web Research")
st.caption("Claude searches the web for the latest on any CMBS deal by name. "
           "Good inputs: `BANK 2023-BNK45`, `WFCM 2022-C58`, `BX Trust 2021-XL2`.")

if not SETTINGS.has_llm:
    st.warning("Web research needs `ANTHROPIC_API_KEY` set in your `.env`.", icon="🔑")

deal_id = st.text_input("Deal name / shelf / series", value="BANK 2023-BNK45")

col1, col2, col3, col4 = st.columns(4)
run_overview = col1.button("📋 Overview brief", type="primary")
run_news     = col2.button("📰 Recent news (90d)")
run_loans    = col3.button("🏘️ Top loans")
run_pros     = col4.button("📄 Find prospectus")

free_q = st.text_input("Or ask a free-form research question", placeholder="e.g. has the largest loan been modified?")
run_free = st.button("Ask") if free_q else False

def _render(resp):
    if resp.stub:
        st.info(resp.text)
        return
    st.markdown(resp.text)
    if resp.citations:
        st.markdown("**Sources:**")
        for c in resp.citations:
            st.markdown(f"- {c}")

if run_overview:
    with st.spinner(f"Researching {deal_id}…"):
        brief = deal_lookup.deal_brief(deal_id, include_news=False)
    _render(brief.overview)

if run_news:
    with st.spinner("Pulling recent news…"):
        resp = deal_lookup.deal_brief(deal_id, include_news=True).news
    _render(resp)

if run_loans:
    with st.spinner("Pulling top loans…"):
        resp = deal_lookup.top_loans(deal_id)
    _render(resp)

if run_pros:
    with st.spinner("Searching EDGAR…"):
        resp = deal_lookup.find_prospectus(deal_id)
    _render(resp)

if run_free:
    with st.spinner("Searching the web…"):
        resp = deal_lookup.research(deal_id, free_q)
    _render(resp)

st.divider()
st.caption(
    "Claude uses its built-in `web_search` tool (up to 5 searches per brief). "
    "Sources are listed below each response."
)
