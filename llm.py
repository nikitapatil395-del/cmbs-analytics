"""Thin Claude wrapper with CMBS-flavored system prompt + optional web search.

Everything that calls an LLM in this project routes through :class:`CMBSExpertClient`.

Key design choices:
* API key is optional. Without one, we return a clearly-marked stub response so
  the rest of the app still works for smoke-testing.
* We enable Anthropic's built-in ``web_search`` tool so the model can look up
  live deal information (remittance updates, rating actions, news).
* PDF inputs are passed as document content blocks — Claude reads the PDF
  natively without needing us to pre-extract text.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import SETTINGS


SYSTEM_PROMPT = """You are a senior CMBS (Commercial Mortgage-Backed Securities) \
analyst with 15+ years of experience covering conduit, SASB, and CRE CLO deals. \
You are assisting an analyst with diagnostics on a specific deal.

Ground rules:
- Be precise and quantitative. Always cite numbers when discussing loan tape, \
  cashflows, or capital structure.
- Use correct CMBS terminology: PSA, pooling and servicing agreement, \
  appraisal reduction amount (ARA), appraisal subordinate entitlement \
  reduction (ASER), realized loss, control event, collateral deficiency \
  event, interest shortfall, controlling class, operating advisor, special \
  servicing transfer, yield maintenance, defeasance, DSCR, LTV, NCF, NOI, \
  in-trust vs. whole loan, A-notes, pari passu companion loans, lockbox, \
  cash management, CSA (cash sweep).
- When explaining a waterfall event, map it to a specific PSA section if \
  possible (e.g., Section 4.01 for priority of distributions).
- When looking up a deal on the web, prefer issuer remittance reports, \
  SEC EDGAR (10-D filings), rating agency surveillance notes, and \
  established CRE news outlets (Commercial Observer, Trepp blog, Bisnow, \
  GlobeSt). Link sources.
- If you aren't sure, say so and suggest what document would resolve the \
  question (e.g., "check the PSA s.4.03 for control-shift mechanics").
- Format numbers with thousand separators, percentages to two decimals, \
  and DSCR to two decimals (e.g., 1.72x).
"""


@dataclass
class LLMResponse:
    text: str
    citations: list[str]
    stub: bool = False


class CMBSExpertClient:
    """Lightweight Claude client. Lazily imports the SDK so the rest of the
    library works without anthropic installed.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or SETTINGS.anthropic_api_key
        self.model = model or SETTINGS.model
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                return None
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------
    # Core call
    # ------------------------------------------------------------------

    def ask(
        self,
        user_message: str,
        *,
        use_web_search: bool = False,
        pdf_path: str | Path | None = None,
        extra_system: str | None = None,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        """Send a message and return the combined text + any web citations."""
        client = self._get_client()
        if client is None:
            return LLMResponse(
                text=(
                    "⚠️ **LLM disabled** — no ANTHROPIC_API_KEY set. "
                    "Set one in your `.env` to enable expert commentary, "
                    "web research, and prospectus Q&A.\n\n"
                    f"(Your question: {user_message[:300]}{'...' if len(user_message) > 300 else ''})"
                ),
                citations=[],
                stub=True,
            )

        system = SYSTEM_PROMPT
        if extra_system:
            system = SYSTEM_PROMPT + "\n\n" + extra_system

        content: list[dict] = []
        if pdf_path:
            pdf_bytes = Path(pdf_path).read_bytes()
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf_bytes).decode("utf-8"),
                },
            })
        content.append({"type": "text", "text": user_message})

        tools: list[dict] = []
        if use_web_search:
            tools.append({
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5,
            })

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:  # pragma: no cover - network
            return LLMResponse(
                text=f"⚠️ LLM call failed: {exc}",
                citations=[],
                stub=True,
            )

        text_parts: list[str] = []
        citations: list[str] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
                for c in getattr(block, "citations", None) or []:
                    url = getattr(c, "url", None) or getattr(c, "source_url", None)
                    title = getattr(c, "title", None) or ""
                    if url:
                        citations.append(f"{title} — {url}" if title else url)
            elif btype == "web_search_tool_result":
                for item in getattr(block, "content", []) or []:
                    url = getattr(item, "url", None)
                    if url and url not in citations:
                        title = getattr(item, "title", "") or ""
                        citations.append(f"{title} — {url}" if title else url)

        return LLMResponse(
            text="\n".join(text_parts).strip() or "(empty response)",
            citations=citations,
            stub=False,
        )

    def stream_batch(self, prompts: Iterable[str]) -> list[LLMResponse]:
        """Convenience — sequentially ask multiple prompts."""
        return [self.ask(p) for p in prompts]


# Singleton for easy import throughout the app
EXPERT = CMBSExpertClient()
