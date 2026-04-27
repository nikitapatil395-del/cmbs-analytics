"""Prospectus PDF parsing + Q&A.

Works in two layers:

1. **Local parsing** (no LLM needed) — extract text with ``pdfplumber`` and
   pull out structured key/value pairs (parties, dates, pool summary) using
   regexes. Good for fast table-of-contents style summaries.

2. **Q&A over the full PDF** — the PDF is streamed to Claude as a document
   content block, so Claude reads it natively. This powers free-form
   questions like "explain the appraisal reduction mechanics" or "what
   happens on a control event".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import MOCK_PROSPECTUS
from .llm import EXPERT, LLMResponse


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


@dataclass
class ProspectusSummary:
    deal_name: str | None
    parties: dict[str, str]
    key_dates: dict[str, str]
    pool_summary: dict[str, str]
    psa_sections: list[str]
    raw_text: str


class Prospectus:
    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        self._text: str | None = None

    # ------------------------------------------------------------
    # Text
    # ------------------------------------------------------------

    def text(self) -> str:
        if self._text is None:
            try:
                import pdfplumber
            except ImportError as e:
                raise RuntimeError("pdfplumber required to parse PDFs") from e
            pages = []
            with pdfplumber.open(self.pdf_path) as pdf:
                for p in pdf.pages:
                    pages.append(p.extract_text() or "")
            self._text = "\n".join(pages)
        return self._text

    # ------------------------------------------------------------
    # Structured summary
    # ------------------------------------------------------------

    def summarize(self) -> ProspectusSummary:
        text = self.text()

        parties = self._kv_block(text, [
            "Depositor", "Sponsors", "Sponsor",
            "Master Servicer", "Special Servicer", "Trustee",
            "Certificate Administrator", "Operating Advisor",
        ])
        key_dates = self._kv_block(text, [
            "Cut-off Date", "Closing Date", "First Distribution Date",
            "Distribution Date", "Expected Final Distribution",
            "Rated Final Distribution",
        ])
        pool = self._kv_block(text, [
            "Initial Pool Balance", "Number of Mortgage Loans",
            "Number of Mortgaged Props", "WA Mortgage Rate",
            "WA U/W NCF DSCR", "WA Cut-off Date LTV",
            "Top 10 Loan Concentration", "Largest Property Type",
            "Largest State",
        ])

        deal_name = None
        m = re.search(r"^(.*Trust.*\d{4}-[A-Z0-9]+)", text, re.MULTILINE)
        if m:
            deal_name = m.group(1).strip()

        psa_secs = sorted(set(re.findall(r"Section\s+\d+\.\d+", text)))

        return ProspectusSummary(
            deal_name=deal_name,
            parties=parties,
            key_dates=key_dates,
            pool_summary=pool,
            psa_sections=psa_secs,
            raw_text=text,
        )

    @staticmethod
    def _kv_block(text: str, keys: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in keys:
            # Match "Key: value" or "Key      value" (padded with spaces/colons)
            pattern = rf"{re.escape(key)}\s*[:\s]\s+(.+?)(?:\n|$)"
            m = re.search(pattern, text)
            if m:
                out[key] = m.group(1).strip()
        return out

    # ------------------------------------------------------------
    # Q&A
    # ------------------------------------------------------------

    def ask(self, question: str, *, include_pdf: bool = True) -> LLMResponse:
        """Ask Claude a question about the prospectus.

        When ``include_pdf`` is True (default) we send the raw PDF as a
        document block so Claude can cite specific sections. When False, we
        send only the extracted text — cheaper but with less fidelity.
        """
        if include_pdf:
            prompt = (
                f"You have been given the full prospectus supplement for a CMBS deal. "
                f"Answer the analyst's question precisely, citing section numbers "
                f"and page references where possible.\n\nQuestion: {question}"
            )
            return EXPERT.ask(prompt, pdf_path=str(self.pdf_path))
        else:
            snippet = self.text()[:40_000]  # keep prompts bounded
            prompt = (
                f"Below is the extracted text of a CMBS prospectus supplement. "
                f"Answer the question using only this text.\n\n"
                f"--- PROSPECTUS ---\n{snippet}\n--- END ---\n\nQuestion: {question}"
            )
            return EXPERT.ask(prompt)

    def deal_abstract(self) -> LLMResponse:
        """One-paragraph expert abstract of the deal."""
        snippet = self.text()[:20_000]
        prompt = (
            "Read the CMBS prospectus supplement excerpt below and produce a "
            "tight 6-8 sentence abstract covering: (a) deal name and issuer, "
            "(b) pool size and composition, (c) key parties, "
            "(d) most important structural features for subordinate holders, "
            "(e) the one or two risks that most stand out.\n\n"
            f"{snippet}"
        )
        return EXPERT.ask(prompt)


def load_default() -> Prospectus:
    """Convenience loader for the synthetic prospectus."""
    return Prospectus(MOCK_PROSPECTUS)
