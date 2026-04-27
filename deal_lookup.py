"""Web-powered CMBS deal lookup.

Uses Claude's native web search tool to pull the latest surveillance info,
remittance highlights, and rating actions on a specific deal.

Composable — other modules can call :func:`deal_brief` to attach the latest
web context to their own analysis.
"""
from __future__ import annotations

from dataclasses import dataclass

from .llm import EXPERT, LLMResponse


TEMPLATES = {
    "overview": (
        "Please research the CMBS deal `{deal_id}` on the public web. Include:\n"
        "1) Issuer, sponsor(s), and trustee.\n"
        "2) Pool size at issuance and current factor (if reported).\n"
        "3) Current delinquency / special servicing rate.\n"
        "4) Any rating actions in the last 12 months.\n"
        "5) Any loans in headline news (foreclosure, modification, transfer to SS).\n"
        "6) A link to the latest 10-D / remittance report on EDGAR if findable.\n\n"
        "If you cannot find the deal, say so and suggest similar recent deals."
    ),
    "news": (
        "What has happened with CMBS deal `{deal_id}` in the last 90 days? "
        "Look for specially-serviced loan updates, rating watch/downgrade actions, "
        "remittance commentary, and any property-level news (appraisal, "
        "foreclosure, sale) on loans in this deal. Format as a dated bullet "
        "list, newest first, with source links."
    ),
    "loans": (
        "For CMBS deal `{deal_id}`, list the top 10 underlying loans if publicly "
        "disclosed (in the offering circular or recent remittance). For each, "
        "give the loan name, property name(s), property type, city/state, "
        "original balance, DSCR and LTV at origination, and current status "
        "(current / watchlist / special servicing). Cite sources."
    ),
    "prospectus": (
        "Find the prospectus / offering circular (424B filing) for CMBS deal "
        "`{deal_id}` on SEC EDGAR. Return the direct URL, the date it was filed, "
        "and a one-paragraph description of what's inside. If the exact deal "
        "cannot be found, suggest the most likely CIK and filings page."
    ),
}


@dataclass
class DealBrief:
    deal_id: str
    overview: LLMResponse
    news: LLMResponse
    all_citations: list[str]


def deal_brief(deal_id: str, *, include_news: bool = True) -> DealBrief:
    """Compose an overview + news brief for a deal using web search."""
    overview = EXPERT.ask(
        TEMPLATES["overview"].format(deal_id=deal_id),
        use_web_search=True,
        max_tokens=2000,
    )
    news = (
        EXPERT.ask(
            TEMPLATES["news"].format(deal_id=deal_id),
            use_web_search=True,
            max_tokens=2000,
        )
        if include_news
        else LLMResponse(text="(skipped)", citations=[], stub=True)
    )
    cites = list(dict.fromkeys(overview.citations + news.citations))
    return DealBrief(deal_id=deal_id, overview=overview, news=news, all_citations=cites)


def research(deal_id: str, question: str) -> LLMResponse:
    """Free-form web research question scoped to a deal."""
    prompt = (
        f"Research question about CMBS deal `{deal_id}`:\n\n"
        f"{question}\n\n"
        f"Use the web. Cite sources with URLs."
    )
    return EXPERT.ask(prompt, use_web_search=True, max_tokens=2000)


def find_prospectus(deal_id: str) -> LLMResponse:
    return EXPERT.ask(
        TEMPLATES["prospectus"].format(deal_id=deal_id),
        use_web_search=True,
        max_tokens=1200,
    )


def top_loans(deal_id: str) -> LLMResponse:
    return EXPERT.ask(
        TEMPLATES["loans"].format(deal_id=deal_id),
        use_web_search=True,
        max_tokens=2000,
    )
