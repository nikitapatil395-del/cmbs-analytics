# CMBS Analytics Diagnostic Toolkit

A Claude-powered diagnostic tool for Commercial Mortgage-Backed Securities.
It acts like a senior CMBS analyst you can put on your desk: it reads the
prospectus, parses waterfall logs, visualizes the loan tape, and researches
deals on the live web.

## Features

| Feature | What it does |
|---|---|
| **Deal Overview** | Capital structure, pool metrics, party directory, expert credit-memo narrative. |
| **Loan Analytics** | Interactive loan-tape filters, DSCR × LTV bubble chart, maturity ladder, 7-screen risk flag grid. |
| **Cashflow Diagnostics** | Parses a waterfall log into period/tranche/event frames, spots anomalies, and lets Claude explain *why* a period flowed the way it did (with PSA-section references). |
| **Prospectus Q&A** | Extracts parties, dates, pool summary, and PSA sections from a prospectus PDF; free-form chat sends the full PDF to Claude for Q&A. |
| **Web Research** | Uses Claude's built-in web search tool to pull the latest overview, 90-day news, top loans, or EDGAR prospectus for any deal. |

Every feature can be used on its own or composed (e.g. the Loan Analytics
page uses `LoanAnalyzer.expert_commentary()` which internally calls the LLM
wrapper used by Prospectus Q&A and Web Research).

## Quick start

```bash
# 1. clone / unzip this folder, then:
cd cmbs_analytics
cp .env.example .env         # add your ANTHROPIC_API_KEY
./run.sh                     # creates venv, installs deps, launches Streamlit
```

Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m cmbs.mock_data     # generate sample_data/
streamlit run app.py
```

The app will open at `http://localhost:8501`. The first run generates a
synthetic deal (50 loans, 3-tranche capital structure with IO strips,
36-month waterfall simulation, and a realistic prospectus supplement PDF).
No API key is required to browse the UI, parse logs, or see charts — the
key is only needed for Claude-generated commentary, web research, and
prospectus Q&A.

## Use as a library

```python
from cmbs.loan_analyzer import LoanAnalyzer
from cmbs.cashflow_analyzer import CashflowAnalyzer
from cmbs.prospectus import Prospectus
from cmbs import deal_lookup

# 1) Loan tape analytics
la = LoanAnalyzer.from_csv("sample_data/loan_tape.csv")
la.pool_summary()
la.risk_flags()
print(la.expert_commentary().text)

# 2) Waterfall log diagnosis
ca = CashflowAnalyzer.from_file("sample_data/waterfall.log")
ca.anomalies()
print(ca.explain_period(14).text)

# 3) Prospectus Q&A
pros = Prospectus("sample_data/prospectus.pdf")
print(pros.summarize().parties)
print(pros.ask("Explain the appraisal reduction mechanics.").text)

# 4) Live web research
brief = deal_lookup.deal_brief("BANK 2023-BNK45")
print(brief.overview.text)
for c in brief.all_citations:
    print(" - ", c)
```

## Project layout

```
cmbs_analytics/
├── app.py                       # Streamlit home
├── pages/
│   ├── 1_Deal_Overview.py
│   ├── 2_Loan_Analytics.py
│   ├── 3_Cashflow_Diagnostics.py
│   ├── 4_Prospectus_QA.py
│   └── 5_Web_Research.py
├── cmbs/
│   ├── config.py                # env / paths
│   ├── llm.py                   # Claude client (web_search, PDF input)
│   ├── mock_data.py             # synthetic deal generator
│   ├── deal_lookup.py           # web-powered research
│   ├── loan_analyzer.py         # pool / loan analytics
│   ├── cashflow_analyzer.py     # waterfall log parser + "why" explanations
│   ├── prospectus.py            # PDF parsing + Q&A
│   └── visualizations.py        # Plotly chart factory
├── sample_data/                 # generated on first run
├── requirements.txt
├── .env.example
├── run.sh
└── README.md
```

## Bringing your own data

- **Loan tape:** drop a CSV with columns `loan_id, property_type, state,
  current_balance, dscr_ncf, ltv_pct, note_rate_pct, maturity_date`
  (extras like `property_name`, `city`, `status`, `on_watchlist`,
  `occupancy` are used when present). Upload it from the Loan Analytics
  sidebar.
- **Waterfall log:** the parser uses generic anchors (`DISTRIBUTION DATE`,
  `POOL BALANCE (BOP)`, `[EVENT]`, `-- INTEREST DISTRIBUTION --`, etc.).
  You can adapt your servicer's log with a small preprocessor, or feed the
  synthetic format via `CashflowAnalyzer.from_text(...)`.
- **Prospectus:** upload any 424B / prospectus supplement PDF in the
  Prospectus Q&A sidebar. Claude reads the PDF natively — no manual
  extraction needed.

## Notes on costs

Web research uses Claude's `web_search_20250305` server tool (billed
per search). A "deal brief" uses up to 5 searches. Prospectus Q&A sends
the full PDF as a document content block on each question; if this is
too expensive for your workflow, uncheck *Send full PDF to Claude* in the
chat sidebar to fall back to extracted text.

## Safety / disclaimers

All data shipped with the tool is **synthetic**. The deal name
`MSCG 2024-CMBS1` is fictional and any resemblance to a real issuance is
coincidental. The output is diagnostic, not investment advice.
# cmbs-analytics 
