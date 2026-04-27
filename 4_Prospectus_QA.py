"""Prospectus PDF parser + Q&A chat."""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from cmbs import config
from cmbs.prospectus import Prospectus

st.set_page_config(page_title="Prospectus Q&A", page_icon="📄", layout="wide")
st.title("📄 Prospectus Q&A")

with st.sidebar:
    st.subheader("Prospectus source")
    uploaded = st.file_uploader("Upload a prospectus PDF", type=["pdf"])
    if uploaded is not None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(uploaded.read())
        tmp.close()
        pdf_path = Path(tmp.name)
        st.success(f"Loaded: {uploaded.name}")
    elif config.SETTINGS.prospectus_path and config.SETTINGS.prospectus_path.exists():
        pdf_path = config.SETTINGS.prospectus_path
        st.info(f"Using path from CMBS_PROSPECTUS_PATH:\n`{pdf_path.name}`")
    else:
        pdf_path = config.MOCK_PROSPECTUS
        st.info(f"Using synthetic prospectus: `{Path(pdf_path).name}`")

pros = Prospectus(pdf_path)

# ---- Structured summary ----
with st.spinner("Extracting prospectus text…"):
    summary = pros.summarize()

st.subheader(summary.deal_name or "Prospectus Summary")

col1, col2, col3 = st.columns(3)

def _render_kv(col, title: str, items: dict[str, str]):
    with col:
        st.markdown(f"#### {title}")
        if not items:
            st.caption("_(nothing parsed)_")
        for k, v in items.items():
            st.markdown(f"**{k}:** {v}")

_render_kv(col1, "Parties", summary.parties)
_render_kv(col2, "Key Dates", summary.key_dates)
_render_kv(col3, "Pool Summary", summary.pool_summary)

st.divider()
if summary.psa_sections:
    st.markdown(f"**PSA sections referenced:** `{'`, `'.join(summary.psa_sections)}`")

# ---- Deal abstract ----
st.subheader("🧠 Deal abstract")
if st.button("Generate abstract", type="primary"):
    with st.spinner("Claude reading PDF…"):
        resp = pros.deal_abstract()
    if resp.stub:
        st.info(resp.text)
    else:
        st.markdown(resp.text)

st.divider()

# ---- Chat ----
st.subheader("💬 Ask the prospectus")

if "pros_chat" not in st.session_state:
    st.session_state.pros_chat = []

for role, msg in st.session_state.pros_chat:
    with st.chat_message(role):
        st.markdown(msg)

q = st.chat_input("Ask any question about this prospectus…")
include_pdf = st.checkbox("Send full PDF to Claude (more accurate, slower)", value=True)

if q:
    st.session_state.pros_chat.append(("user", q))
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            resp = pros.ask(q, include_pdf=include_pdf)
        if resp.stub:
            st.info(resp.text)
        else:
            st.markdown(resp.text)
        if resp.citations:
            st.caption("Sources: " + ", ".join(resp.citations))
    st.session_state.pros_chat.append(("assistant", resp.text))

# ---- Raw text viewer ----
with st.expander("Extracted prospectus text"):
    st.code(summary.raw_text[:8000] + ("\n…(truncated)" if len(summary.raw_text) > 8000 else ""))
