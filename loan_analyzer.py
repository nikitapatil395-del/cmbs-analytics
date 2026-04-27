"""Loan tape & property-level analytics.

Reads a loan tape (CSV or DataFrame) with standard CMBS columns and produces
pool-level summary statistics, concentration metrics, and risk flags.

Can be called directly::

    from cmbs.loan_analyzer import LoanAnalyzer
    la = LoanAnalyzer.from_csv("sample_data/loan_tape.csv")
    la.pool_summary()
    la.concentrations()
    la.risk_flags()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import MOCK_LOAN_TAPE
from .llm import EXPERT, LLMResponse


REQUIRED_COLS = [
    "loan_id", "property_type", "state", "current_balance", "dscr_ncf",
    "ltv_pct", "note_rate_pct", "maturity_date",
]


@dataclass
class LoanAnalyzer:
    df: pd.DataFrame
    name: str = "MSCG 2024-CMBS1"

    # Cached computed properties
    _summary: dict | None = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------

    @classmethod
    def from_csv(cls, path: str | Path = MOCK_LOAN_TAPE, **kw) -> "LoanAnalyzer":
        df = pd.read_csv(path)
        cls._validate(df)
        return cls(df=df, **kw)

    @classmethod
    def from_df(cls, df: pd.DataFrame, **kw) -> "LoanAnalyzer":
        cls._validate(df)
        return cls(df=df.copy(), **kw)

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"Loan tape missing required columns: {missing}")

    # ------------------------------------------------------------
    # Pool-level stats
    # ------------------------------------------------------------

    def pool_summary(self) -> dict[str, Any]:
        if self._summary is None:
            df = self.df
            pool = float(df["current_balance"].sum())
            wa_rate = float((df["note_rate_pct"] * df["current_balance"]).sum() / pool)
            wa_dscr = float((df["dscr_ncf"] * df["current_balance"]).sum() / pool)
            wa_ltv = float((df["ltv_pct"] * df["current_balance"]).sum() / pool)
            self._summary = {
                "deal_name": self.name,
                "loan_count": int(len(df)),
                "total_balance": pool,
                "avg_balance": float(df["current_balance"].mean()),
                "largest_loan": float(df["current_balance"].max()),
                "wa_note_rate_pct": round(wa_rate, 4),
                "wa_dscr": round(wa_dscr, 2),
                "wa_ltv_pct": round(wa_ltv, 2),
                "sub_1x_dscr_count": int((df["dscr_ncf"] < 1.0).sum()),
                "watchlist_count": int(df.get("on_watchlist", pd.Series([False]*len(df))).sum()),
                "delinquent_balance": float(
                    df.loc[df.get("status", "").str.contains("Delinquent|Special", na=False), "current_balance"].sum()
                    if "status" in df.columns else 0
                ),
            }
        return self._summary

    # ------------------------------------------------------------
    # Concentrations
    # ------------------------------------------------------------

    def concentrations(self) -> dict[str, pd.DataFrame]:
        pool = float(self.df["current_balance"].sum())
        by_type = self._mix("property_type", pool)
        by_state = self._mix("state", pool)
        top10 = self.df.nlargest(10, "current_balance")[
            ["loan_id", "property_name", "property_type", "state",
             "current_balance", "dscr_ncf", "ltv_pct", "maturity_date"]
        ].copy()
        top10["pct_of_pool"] = (top10["current_balance"] / pool * 100).round(2)
        return {"by_property_type": by_type, "by_state": by_state, "top10": top10}

    def _mix(self, col: str, pool: float) -> pd.DataFrame:
        g = self.df.groupby(col)["current_balance"].agg(["sum", "count"]).rename(
            columns={"sum": "balance", "count": "loan_count"}
        )
        g["pct_of_pool"] = (g["balance"] / pool * 100).round(2)
        return g.sort_values("balance", ascending=False).reset_index()

    # ------------------------------------------------------------
    # Risk flags
    # ------------------------------------------------------------

    def risk_flags(self) -> pd.DataFrame:
        """Apply a bank of heuristic risk screens and return a per-loan flag table."""
        df = self.df.copy()
        flags = pd.DataFrame({"loan_id": df["loan_id"]})
        flags["low_dscr"] = df["dscr_ncf"] < 1.10
        flags["sub_1x_dscr"] = df["dscr_ncf"] < 1.00
        flags["high_ltv"] = df["ltv_pct"] > 70.0
        flags["hot_rate"] = df["note_rate_pct"] > 7.0
        if "occupancy" in df.columns:
            flags["low_occupancy"] = df["occupancy"] < 0.80
        if "status" in df.columns:
            flags["non_performing"] = df["status"].str.contains("Delinquent|Special", na=False)
        if "on_watchlist" in df.columns:
            flags["watchlist"] = df["on_watchlist"].astype(bool)

        # near-term maturity (< 18 months from cutoff)
        mat = pd.to_datetime(df["maturity_date"], errors="coerce")
        flags["near_term_maturity"] = (mat - pd.Timestamp.today()).dt.days.between(-30, 18 * 30, inclusive="both")

        flag_cols = [c for c in flags.columns if c != "loan_id"]
        flags["flag_count"] = flags[flag_cols].sum(axis=1)
        flags = flags.merge(df[["loan_id", "current_balance", "property_type", "state"]], on="loan_id")
        return flags.sort_values(["flag_count", "current_balance"], ascending=[False, False])

    def maturity_ladder(self, bucket_years: int = 1) -> pd.DataFrame:
        df = self.df.copy()
        df["maturity_year"] = pd.to_datetime(df["maturity_date"], errors="coerce").dt.year
        g = df.groupby("maturity_year")["current_balance"].sum().reset_index()
        g["pct_of_pool"] = (g["current_balance"] / df["current_balance"].sum() * 100).round(2)
        return g.sort_values("maturity_year")

    # ------------------------------------------------------------
    # LLM narrative
    # ------------------------------------------------------------

    def expert_commentary(self) -> LLMResponse:
        """Ask Claude to write a one-paragraph credit memo on the pool."""
        summary = self.pool_summary()
        conc = self.concentrations()
        top_type = conc["by_property_type"].iloc[0]
        top_state = conc["by_state"].iloc[0]
        top3 = conc["top10"].head(3)[["loan_id", "property_name", "current_balance", "pct_of_pool"]]
        flags = self.risk_flags()
        flagged_bal = float(flags[flags["flag_count"] >= 2]["current_balance"].sum())

        prompt = f"""Please write a 3-paragraph CMBS credit memo summary for {self.name} based on the data below.
Paragraph 1: pool composition (size, WA metrics, top property type / geography).
Paragraph 2: concentration and top-3 loans.
Paragraph 3: risk flags and what to watch. Be crisp, quantitative, and use CMBS jargon.

POOL SUMMARY:
{summary}

TOP PROPERTY TYPE: {top_type['property_type']} = {top_type['pct_of_pool']:.2f}% of pool
TOP STATE: {top_state['state']} = {top_state['pct_of_pool']:.2f}% of pool

TOP 3 LOANS:
{top3.to_string(index=False)}

RISK: ${flagged_bal:,.0f} of pool balance has 2+ risk flags out of {len(flags)} loans scanned.
"""
        return EXPERT.ask(prompt)
