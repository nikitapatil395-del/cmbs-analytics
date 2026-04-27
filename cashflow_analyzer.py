"""Parse a CMBS waterfall log file and explain the cashflows it produced.

Input format: the plain-text waterfall log written by ``cmbs.mock_data``
(or any similarly structured log). The parser is intentionally forgiving —
section headers are detected by label prefixes, and event markers are picked
up from lines starting with ``[EVENT]``.

Public API::

    CashflowAnalyzer.from_file("sample_data/waterfall.log")
        .periods()                  # list[PeriodSnapshot]
        .remittance_frame()         # pandas DataFrame
        .events_frame()             # one row per trigger event
        .explain_period(14)         # LLMResponse: why did this period look the way it did?
        .explain_metric("losses")   # LLMResponse: narrative on loss allocation over time
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MOCK_CASHFLOW_LOG
from .llm import EXPERT, LLMResponse


MONEY_RE = re.compile(r"\$[\d,]+\.\d{2}")
PERIOD_HEADER_RE = re.compile(
    r"DISTRIBUTION DATE:\s+(\d{4}-\d{2}-\d{2})\s+\(Period\s+(\d+)\)"
)


def _parse_money(s: str) -> float:
    return float(s.replace("$", "").replace(",", ""))


@dataclass
class TrancheFlow:
    class_name: str
    interest_accrued: float = 0.0
    interest_paid: float = 0.0
    shortfall: float = 0.0
    principal_paid: float = 0.0
    loss_allocated: float = 0.0
    ending_balance: float | None = None


@dataclass
class PeriodSnapshot:
    period: int
    distribution_date: str
    pool_balance_bop: float
    wa_coupon: float
    scheduled_interest: float
    scheduled_principal: float
    prepayments: float
    liquidation_proceeds: float
    total_available: float
    events: list[str] = field(default_factory=list)
    tranches: dict[str, TrancheFlow] = field(default_factory=dict)
    realized_loss: float = 0.0
    cumulative_loss: float = 0.0


class CashflowAnalyzer:
    """Parses the waterfall log and exposes period-level analytics."""

    def __init__(self, text: str):
        self.raw = text
        self.snapshots: list[PeriodSnapshot] = []
        self._parse()

    # ------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path = MOCK_CASHFLOW_LOG) -> "CashflowAnalyzer":
        return cls(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_text(cls, text: str) -> "CashflowAnalyzer":
        return cls(text)

    # ------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------

    def _parse(self) -> None:
        # Split into period blocks
        blocks = re.split(r"={10,}\s*\n", self.raw)
        current: PeriodSnapshot | None = None
        section: str | None = None

        for line in self.raw.splitlines():
            m = PERIOD_HEADER_RE.search(line)
            if m:
                if current is not None:
                    self.snapshots.append(current)
                current = PeriodSnapshot(
                    period=int(m.group(2)),
                    distribution_date=m.group(1),
                    pool_balance_bop=0.0,
                    wa_coupon=0.0,
                    scheduled_interest=0.0,
                    scheduled_principal=0.0,
                    prepayments=0.0,
                    liquidation_proceeds=0.0,
                    total_available=0.0,
                )
                section = None
                continue
            if current is None:
                continue

            stripped = line.strip()

            if stripped.startswith("POOL BALANCE (BOP):"):
                current.pool_balance_bop = _parse_money(MONEY_RE.search(stripped).group())
            elif stripped.startswith("WA COUPON:"):
                current.wa_coupon = float(stripped.split()[-1].rstrip("%"))
            elif stripped.startswith("SCHEDULED INTEREST:"):
                current.scheduled_interest = _parse_money(MONEY_RE.search(stripped).group())
            elif stripped.startswith("SCHEDULED PRINCIPAL:"):
                current.scheduled_principal = _parse_money(MONEY_RE.search(stripped).group())
            elif stripped.startswith("UNSCHEDULED PRINCIPAL:"):
                current.prepayments = _parse_money(MONEY_RE.search(stripped).group())
            elif stripped.startswith("LIQUIDATION PROCEEDS:"):
                current.liquidation_proceeds = _parse_money(MONEY_RE.search(stripped).group())
            elif stripped.startswith("TOTAL AVAILABLE DISTRIBUTION:"):
                current.total_available = _parse_money(MONEY_RE.search(stripped).group())
            elif stripped.startswith("[EVENT]"):
                current.events.append(stripped.replace("[EVENT]", "").strip())
            elif stripped.startswith("-- INTEREST DISTRIBUTION"):
                section = "interest"
            elif stripped.startswith("-- PRINCIPAL DISTRIBUTION"):
                section = "principal"
            elif stripped.startswith("-- REALIZED LOSS"):
                section = "loss"
            elif stripped.startswith("Cumulative Realized Losses:"):
                current.cumulative_loss = _parse_money(MONEY_RE.search(stripped).group())
                section = None
            elif stripped.startswith("Class ") and section is not None:
                parts = stripped.split()
                # e.g. "Class A-1  Accrued: $100.00  Paid: $100.00"
                class_name = parts[1]
                tranche = current.tranches.setdefault(class_name, TrancheFlow(class_name))
                monies = MONEY_RE.findall(stripped)
                if section == "interest":
                    if "Accrued:" in stripped and len(monies) >= 2:
                        tranche.interest_accrued = _parse_money(monies[0])
                        tranche.interest_paid = _parse_money(monies[1])
                    elif "Interest Paid:" in stripped and monies:
                        tranche.interest_paid += _parse_money(monies[0])
                    if "SHORTFALL" in stripped and monies:
                        tranche.shortfall = _parse_money(monies[-1])
                elif section == "principal":
                    if len(monies) >= 1:
                        tranche.principal_paid = _parse_money(monies[0])
                    if len(monies) >= 2:
                        tranche.ending_balance = _parse_money(monies[1])
                elif section == "loss":
                    if len(monies) >= 1:
                        tranche.loss_allocated = _parse_money(monies[0])
                    if len(monies) >= 2:
                        tranche.ending_balance = _parse_money(monies[1])
                    current.realized_loss += tranche.loss_allocated

        if current is not None:
            self.snapshots.append(current)

    # ------------------------------------------------------------
    # DataFrame views
    # ------------------------------------------------------------

    def periods(self) -> list[PeriodSnapshot]:
        return self.snapshots

    def remittance_frame(self) -> pd.DataFrame:
        rows = []
        for s in self.snapshots:
            rows.append({
                "period": s.period,
                "distribution_date": s.distribution_date,
                "pool_balance_bop": s.pool_balance_bop,
                "scheduled_interest": s.scheduled_interest,
                "scheduled_principal": s.scheduled_principal,
                "prepayments": s.prepayments,
                "liquidation_proceeds": s.liquidation_proceeds,
                "total_available": s.total_available,
                "realized_loss": s.realized_loss,
                "cumulative_loss": s.cumulative_loss,
                "event_count": len(s.events),
                "events": " | ".join(s.events),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["distribution_date"] = pd.to_datetime(df["distribution_date"])
        return df

    def events_frame(self) -> pd.DataFrame:
        rows = []
        for s in self.snapshots:
            for evt in s.events:
                etype = evt.split(":", 1)[0] if ":" in evt else "EVENT"
                rows.append({
                    "period": s.period,
                    "distribution_date": s.distribution_date,
                    "event_type": etype.strip(),
                    "description": evt,
                })
        return pd.DataFrame(rows)

    def tranche_frame(self) -> pd.DataFrame:
        """Long DataFrame: one row per (period, tranche)."""
        rows = []
        for s in self.snapshots:
            for name, t in s.tranches.items():
                rows.append({
                    "period": s.period,
                    "distribution_date": s.distribution_date,
                    "class_name": name,
                    "interest_paid": t.interest_paid,
                    "interest_accrued": t.interest_accrued,
                    "shortfall": t.shortfall,
                    "principal_paid": t.principal_paid,
                    "loss_allocated": t.loss_allocated,
                    "ending_balance": t.ending_balance,
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["distribution_date"] = pd.to_datetime(df["distribution_date"])
        return df

    # ------------------------------------------------------------
    # Anomaly detection & summaries
    # ------------------------------------------------------------

    def anomalies(self) -> pd.DataFrame:
        """Periods where something non-trivial happened."""
        rem = self.remittance_frame()
        if rem.empty:
            return rem
        anomalies = rem[
            (rem["realized_loss"] > 0)
            | (rem["prepayments"] > 0)
            | (rem["liquidation_proceeds"] > 0)
            | (rem["event_count"] > 0)
        ].copy()
        anomalies["reason"] = anomalies.apply(self._classify_anomaly, axis=1)
        return anomalies.reset_index(drop=True)

    @staticmethod
    def _classify_anomaly(row) -> str:
        reasons = []
        if row["realized_loss"] > 0:
            reasons.append(f"Realized loss ${row['realized_loss']:,.0f}")
        if row["prepayments"] > 0:
            reasons.append(f"Prepayment ${row['prepayments']:,.0f}")
        if row["liquidation_proceeds"] > 0:
            reasons.append(f"Liquidation ${row['liquidation_proceeds']:,.0f}")
        if row["event_count"] > 0 and not reasons:
            reasons.append("Servicing event")
        return "; ".join(reasons)

    def summary(self) -> dict:
        rem = self.remittance_frame()
        return {
            "periods_parsed": len(self.snapshots),
            "total_interest_distributed": float(rem["scheduled_interest"].sum()) if not rem.empty else 0.0,
            "total_principal_distributed": float(
                (rem["scheduled_principal"] + rem["prepayments"] + rem["liquidation_proceeds"]).sum()
            ) if not rem.empty else 0.0,
            "total_prepayments": float(rem["prepayments"].sum()) if not rem.empty else 0.0,
            "total_realized_loss": float(rem["realized_loss"].sum()) if not rem.empty else 0.0,
            "final_cumulative_loss": float(rem["cumulative_loss"].iloc[-1]) if not rem.empty else 0.0,
            "event_periods": int((rem["event_count"] > 0).sum()) if not rem.empty else 0,
        }

    # ------------------------------------------------------------
    # LLM diagnostics
    # ------------------------------------------------------------

    def explain_period(self, period: int) -> LLMResponse:
        snap = next((s for s in self.snapshots if s.period == period), None)
        if snap is None:
            return LLMResponse(text=f"No period {period} in log.", citations=[], stub=True)

        tranche_table = "\n".join(
            f"  {t.class_name:<5}  int_paid={t.interest_paid:>15,.2f}  "
            f"prin_paid={t.principal_paid:>15,.2f}  loss={t.loss_allocated:>15,.2f}  "
            f"end_bal={(t.ending_balance or 0):>18,.2f}"
            for t in snap.tranches.values()
        )
        events = "\n".join(f"  - {e}" for e in snap.events) or "  (no trigger events)"
        prompt = f"""Explain, as a CMBS analyst, exactly why the cashflows in Period {snap.period} \
({snap.distribution_date}) flowed the way they did. Be specific about which bonds got paid, \
why shortfalls occurred (if any), and what the trigger events mean for subordinate holders.

PERIOD SNAPSHOT
  Pool balance (BOP): ${snap.pool_balance_bop:,.2f}
  Scheduled interest: ${snap.scheduled_interest:,.2f}
  Scheduled principal: ${snap.scheduled_principal:,.2f}
  Prepayments: ${snap.prepayments:,.2f}
  Liquidation proceeds: ${snap.liquidation_proceeds:,.2f}
  Realized loss: ${snap.realized_loss:,.2f}
  Cumulative loss: ${snap.cumulative_loss:,.2f}

TRIGGER EVENTS
{events}

TRANCHE-LEVEL FLOWS
{tranche_table}

Answer in 4-6 sentences. Reference PSA sections when relevant.
"""
        return EXPERT.ask(prompt)

    def explain_metric(self, metric: str) -> LLMResponse:
        rem = self.remittance_frame()
        prompt = f"""You are reviewing the waterfall history of a CMBS deal.
The user wants to understand the pattern of `{metric}` over the 36 periods.

Here is the remittance summary:
{rem.to_string(index=False)}

In one tight paragraph, describe the trajectory of {metric}, call out the \
inflection periods, explain the servicing events that drove those \
inflections, and note implications for subordinate holders.
"""
        return EXPERT.ask(prompt)
