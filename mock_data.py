"""Generate a synthetic but realistic CMBS dataset.

Produces (under ``sample_data/``):
    loan_tape.csv        - 50 underlying mortgage loans
    bonds.csv            - capital structure (tranches)
    waterfall.log        - 36 monthly payment waterfalls with trigger events
    remittance.csv       - monthly remittance summary
    prospectus.pdf       - a realistic-looking pros-supplement excerpt
    deal.json            - deal metadata (name, issuer, dates, pool summary)

Run directly::

    python -m cmbs.mock_data
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from . import config

# Deterministic output
SEED = 42
random.seed(SEED)
np.random.seed(SEED)


DEAL = {
    "deal_name": "MSCG 2024-CMBS1",
    "full_name": "Morgan Stanley Capital Group Trust 2024-CMBS1",
    "issuer": "Morgan Stanley Capital Group",
    "trustee": "Wilmington Trust, N.A.",
    "master_servicer": "KeyBank National Association",
    "special_servicer": "Rialto Capital Advisors, LLC",
    "certificate_administrator": "Computershare Trust Company, N.A.",
    "closing_date": "2024-06-27",
    "cutoff_date": "2024-06-01",
    "first_payment_date": "2024-07-17",
    "distribution_date": "17th of each month",
    "expected_final_distribution": "2034-06-17",
    "rated_final_distribution": "2057-06-17",
    "total_pool_balance": None,  # filled after loan generation
    "loan_count": 50,
    "property_count": 57,
    "deal_type": "Conduit / Fusion",
    "prospectus_date": "2024-06-18",
    "sec_cik": "0001985724",
    "rating_agencies": ["Moody's", "Fitch", "KBRA"],
}


PROPERTY_TYPES = [
    ("Office", 0.28),
    ("Retail", 0.22),
    ("Multifamily", 0.20),
    ("Industrial", 0.12),
    ("Hospitality", 0.10),
    ("Mixed Use", 0.05),
    ("Self Storage", 0.03),
]

STATES = [
    ("CA", 0.18), ("NY", 0.14), ("TX", 0.12), ("FL", 0.10), ("IL", 0.07),
    ("GA", 0.05), ("PA", 0.05), ("NJ", 0.04), ("MA", 0.04), ("WA", 0.04),
    ("CO", 0.03), ("NC", 0.03), ("AZ", 0.03), ("OH", 0.02), ("VA", 0.02),
    ("MI", 0.02), ("MO", 0.02),
]

CITIES = {
    "CA": ["Los Angeles", "San Francisco", "San Diego", "San Jose", "Oakland", "Sacramento"],
    "NY": ["New York", "Brooklyn", "Queens", "Buffalo", "Rochester"],
    "TX": ["Houston", "Dallas", "Austin", "San Antonio", "Fort Worth"],
    "FL": ["Miami", "Tampa", "Orlando", "Jacksonville", "Fort Lauderdale"],
    "IL": ["Chicago", "Naperville", "Schaumburg"],
    "GA": ["Atlanta", "Savannah", "Augusta"],
    "PA": ["Philadelphia", "Pittsburgh", "King of Prussia"],
    "NJ": ["Newark", "Jersey City", "Edison"],
    "MA": ["Boston", "Cambridge", "Waltham"],
    "WA": ["Seattle", "Bellevue", "Tacoma"],
    "CO": ["Denver", "Aurora", "Boulder"],
    "NC": ["Charlotte", "Raleigh", "Durham"],
    "AZ": ["Phoenix", "Tucson", "Scottsdale"],
    "OH": ["Columbus", "Cleveland", "Cincinnati"],
    "VA": ["Arlington", "Richmond", "Norfolk"],
    "MI": ["Detroit", "Ann Arbor", "Grand Rapids"],
    "MO": ["St. Louis", "Kansas City"],
}

NAME_ROOTS = [
    "Pinnacle", "Metropolitan", "Harbor", "Riverfront", "Central", "Summit",
    "Gateway", "Crescent", "Liberty", "Heritage", "Monarch", "Beacon",
    "Hudson", "Lakeview", "Parkside", "Union", "Commerce", "Oakwood",
    "Westfield", "Skyline",
]

NAME_SUFFIX = {
    "Office": ["Tower", "Plaza", "Center", "Corporate Park"],
    "Retail": ["Mall", "Shopping Center", "Marketplace", "Promenade"],
    "Multifamily": ["Apartments", "Residences", "Village", "Court"],
    "Industrial": ["Logistics Park", "Distribution Center", "Industrial Park"],
    "Hospitality": ["Hotel", "Resort", "Suites", "Inn"],
    "Mixed Use": ["Commons", "Quarter", "District"],
    "Self Storage": ["Storage", "Self-Storage Facility"],
}


def _weighted(items):
    values, weights = zip(*items)
    return random.choices(values, weights=weights, k=1)[0]


def _property_name(ptype: str) -> str:
    return f"{random.choice(NAME_ROOTS)} {random.choice(NAME_SUFFIX[ptype])}"


# ---------------------------------------------------------------------------
# LOAN TAPE
# ---------------------------------------------------------------------------


def generate_loan_tape(n: int = 50) -> pd.DataFrame:
    rows = []
    cutoff = date.fromisoformat(DEAL["cutoff_date"])

    # First three loans are "large" to create meaningful concentration
    for i in range(n):
        if i < 3:
            orig_balance = random.uniform(75_000_000, 145_000_000)
        elif i < 10:
            orig_balance = random.uniform(35_000_000, 70_000_000)
        else:
            orig_balance = random.uniform(4_000_000, 28_000_000)

        ptype = _weighted(PROPERTY_TYPES)
        state = _weighted(STATES)
        city = random.choice(CITIES[state])

        loan_term_months = random.choice([60, 84, 120, 120, 120])
        io_period = random.choice([0, 0, 12, 24, 36, 60, loan_term_months])  # fully IO possible
        amort_term = random.choice([300, 360, 360, 360, 0])  # 0 = IO

        rate = round(random.uniform(5.10, 7.65), 4)
        # Current balance = original minus some amortization
        months_elapsed = random.randint(0, 8)
        if amort_term and io_period < months_elapsed:
            remaining = orig_balance * (1 - 0.0008 * (months_elapsed - io_period))
        else:
            remaining = orig_balance
        remaining = round(remaining, 2)

        dscr = round(np.clip(np.random.normal(1.72, 0.38), 0.85, 3.2), 2)
        ltv = round(np.clip(np.random.normal(58, 8), 30, 82), 1)

        occupancy = round(np.clip(np.random.normal(0.92, 0.08), 0.45, 1.0), 3)
        noi = round(remaining * rate / 100 * dscr, 0)  # NOI implied by DSCR
        appraised_value = round(remaining / (ltv / 100), 0)

        origination = cutoff - relativedelta(months=months_elapsed)
        maturity = origination + relativedelta(months=loan_term_months)

        status_roll = random.random()
        if status_roll < 0.04:
            status, watchlist = "Specially Serviced", True
        elif status_roll < 0.12:
            status, watchlist = "Watchlist", True
        elif status_roll < 0.15:
            status, watchlist = "30+ Days Delinquent", True
        else:
            status, watchlist = "Current", False

        rows.append({
            "loan_id": f"MSCG24-{i+1:03d}",
            "property_name": _property_name(ptype),
            "property_type": ptype,
            "city": city,
            "state": state,
            "year_built": random.randint(1965, 2022),
            "net_rentable_sf": int(round(appraised_value / random.uniform(180, 720), -3)),
            "units": int(round(remaining / random.uniform(120_000, 320_000), 0)) if ptype == "Multifamily" else None,
            "origination_date": origination.isoformat(),
            "maturity_date": maturity.isoformat(),
            "loan_term_months": loan_term_months,
            "io_period_months": io_period,
            "amort_term_months": amort_term if amort_term else None,
            "original_balance": round(orig_balance, 2),
            "current_balance": remaining,
            "note_rate_pct": rate,
            "dscr_ncf": dscr,
            "ltv_pct": ltv,
            "occupancy": occupancy,
            "noi_annual": noi,
            "appraised_value": appraised_value,
            "appraisal_date": origination.isoformat(),
            "status": status,
            "on_watchlist": watchlist,
            "sponsor": f"{random.choice(NAME_ROOTS)} Capital Partners",
            "lockbox": random.choice(["Hard", "Springing", "None"]),
            "prepay_provision": random.choice(["Defeasance", "YM then Open", "Lockout then Open"]),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("current_balance", ascending=False).reset_index(drop=True)
    df["pct_of_pool"] = (df["current_balance"] / df["current_balance"].sum() * 100).round(3)
    return df


# ---------------------------------------------------------------------------
# BOND STRUCTURE
# ---------------------------------------------------------------------------


@dataclass
class Tranche:
    class_name: str
    balance: float
    coupon_pct: float
    rating_moodys: str
    rating_fitch: str
    rating_kbra: str
    credit_support_pct: float
    wal_years: float
    tranche_type: str  # Senior / Mezz / Sub / IO / X
    payment_order: int


def generate_bond_structure(pool_balance: float) -> pd.DataFrame:
    # Classic super-senior conduit stack
    structure = [
        Tranche("A-1",  pool_balance * 0.075, 4.85, "Aaa(sf)", "AAAsf", "AAA(sf)", 30.0, 2.7,  "Senior", 1),
        Tranche("A-2",  pool_balance * 0.135, 5.30, "Aaa(sf)", "AAAsf", "AAA(sf)", 30.0, 6.8,  "Senior", 2),
        Tranche("A-3",  pool_balance * 0.175, 5.55, "Aaa(sf)", "AAAsf", "AAA(sf)", 30.0, 9.4,  "Senior", 3),
        Tranche("A-SB", pool_balance * 0.045, 5.15, "Aaa(sf)", "AAAsf", "AAA(sf)", 30.0, 7.1,  "Senior", 4),
        Tranche("A-S",  pool_balance * 0.090, 5.80, "Aaa(sf)", "AAAsf", "AAA(sf)", 22.5, 9.7,  "Senior", 5),
        Tranche("B",    pool_balance * 0.075, 6.05, "Aa3(sf)", "AA-sf", "AA-(sf)", 16.0, 9.8,  "Mezz",   6),
        Tranche("C",    pool_balance * 0.060, 6.35, "A3(sf)",  "A-sf",  "A-(sf)",  10.5, 9.9,  "Mezz",   7),
        Tranche("D",    pool_balance * 0.050, 6.75, "Baa3(sf)","BBB-sf","BBB-(sf)", 5.5, 9.9,  "Mezz",   8),
        Tranche("E",    pool_balance * 0.030, 7.25, "Ba3(sf)", "BB-sf", "BB-(sf)",  2.5, 9.9,  "Sub",    9),
        Tranche("F",    pool_balance * 0.025, 7.75, "B3(sf)",  "B-sf",  "B-(sf)",   0.0, 9.9,  "Sub",   10),
        Tranche("NR",   pool_balance * 0.025, 0.00, "NR",      "NR",    "NR",       0.0, 9.9,  "Sub",   11),
        Tranche("X-A",  pool_balance * 0.520, 1.25, "Aaa(sf)", "AAAsf", "AAA(sf)", 30.0, 8.4,  "IO",    12),
        Tranche("X-B",  pool_balance * 0.185, 0.85, "Aa3(sf)", "BBB-sf","BBB-(sf)", 5.5, 9.8,  "IO",    13),
    ]
    df = pd.DataFrame([asdict(t) for t in structure])
    df["balance"] = df["balance"].round(0)
    # Exclude IO notionals from par total
    par_rows = df["tranche_type"] != "IO"
    par_total = df.loc[par_rows, "balance"].sum()
    # Rescale par tranches so they sum exactly to pool_balance
    df.loc[par_rows, "balance"] = (df.loc[par_rows, "balance"] / par_total * pool_balance).round(0)
    return df


# ---------------------------------------------------------------------------
# WATERFALL LOG + REMITTANCE
# ---------------------------------------------------------------------------


def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def generate_waterfall_log(loan_tape: pd.DataFrame, bonds: pd.DataFrame, months: int = 36) -> tuple[str, pd.DataFrame]:
    """Simulate a realistic waterfall log with trigger events and one specially-serviced loan loss.

    Returns (log_text, remittance_df).
    """
    first_pay = date.fromisoformat(DEAL["first_payment_date"])
    pool_balance = float(loan_tape["current_balance"].sum())
    wa_coupon = float((loan_tape["note_rate_pct"] * loan_tape["current_balance"]).sum() / pool_balance)

    par_bonds = bonds[bonds["tranche_type"] != "IO"].copy().reset_index(drop=True)
    io_bonds = bonds[bonds["tranche_type"] == "IO"].copy().reset_index(drop=True)

    # Tracking state
    balances = par_bonds["balance"].to_dict()  # keyed by index
    coupons = par_bonds["coupon_pct"].to_dict()
    names = par_bonds["class_name"].to_dict()
    cumulative_losses = 0.0

    log_lines = []
    remit_rows = []

    # Schedule: prepayment in month 9, specially serviced in month 14, loss in month 22, rate modification in month 27
    EVENT_MONTHS = {9, 14, 18, 22, 27, 31}

    for m in range(months):
        pay_date = first_pay + relativedelta(months=m)
        period_balance = pool_balance  # simplified - we'll decrement below with principal
        # ------------- COLLECTIONS ----------------
        scheduled_int = pool_balance * wa_coupon / 100 / 12
        scheduled_prin = pool_balance * 0.0009  # very light amortization (most loans IO)
        prepayments = 0.0
        recoveries = 0.0
        loss_this_period = 0.0
        trigger_events = []

        if m == 9:
            prepayments = 14_250_000.0
            trigger_events.append(
                "PREPAYMENT: Loan MSCG24-011 paid off in full ($14.25M). Yield maintenance premium of "
                "$1,124,000 collected and distributed to Class X-A per s.8.02(f)."
            )
        if m == 14:
            trigger_events.append(
                "TRANSFER TO SPECIAL SERVICING: Loan MSCG24-006 (retail, $28.4M, Midwest) transferred to "
                "Rialto Capital Advisors on 2025-09-08 due to payment default (missed Aug-25 P&I). "
                "Appraisal Reduction Event expected within 60 days."
            )
        if m == 18:
            trigger_events.append(
                "APPRAISAL REDUCTION: Loan MSCG24-006 — updated appraisal of $19.2M vs. $34.8M at origination. "
                "Appraisal Reduction Amount = $9,840,000. ARA applied to reduce P&I advancing and "
                "adjusts interest entitlement for Class F, Class NR per PSA Section 3.18."
            )
        if m == 22:
            loss_this_period = 6_750_000.0
            recoveries = 18_110_000.0  # from liquidation of MSCG24-006
            trigger_events.append(
                "REALIZED LOSS: Loan MSCG24-006 liquidated at $18.11M net of $1.2M special servicing fees. "
                "Realized loss of $6.75M applied in reverse sequential order. Class NR absorbs first; "
                "residual $1.025M writes down Class F principal balance."
            )
        if m == 27:
            trigger_events.append(
                "LOAN MODIFICATION: Loan MSCG24-019 (office, $11.2M) — interest rate reduced from 6.85% to 4.95% "
                "through 2028-03 per modification approved by Special Servicer. Shortfall vs. original rate "
                "allocated to Class NR interest per s.4.07(b)(ii)."
            )
        if m == 31:
            trigger_events.append(
                "CUMULATIVE LOSS TRIGGER: Deal cumulative realized loss = $6.75M (0.71% of original pool). "
                "Below 2.00% threshold — triggers NOT in effect. Principal continues sequential-pay."
            )

        available_int = scheduled_int
        available_prin = scheduled_prin + prepayments + recoveries

        log_lines.append(f"================================================================")
        log_lines.append(f"DISTRIBUTION DATE: {pay_date.isoformat()}  (Period {m+1:02d})")
        log_lines.append(f"================================================================")
        log_lines.append(f"POOL BALANCE (BOP):          {_fmt_money(period_balance)}")
        log_lines.append(f"WA COUPON:                   {wa_coupon:.4f}%")
        log_lines.append(f"SCHEDULED INTEREST:          {_fmt_money(scheduled_int)}")
        log_lines.append(f"SCHEDULED PRINCIPAL:         {_fmt_money(scheduled_prin)}")
        log_lines.append(f"UNSCHEDULED PRINCIPAL:       {_fmt_money(prepayments)}")
        log_lines.append(f"LIQUIDATION PROCEEDS:        {_fmt_money(recoveries)}")
        log_lines.append(f"TOTAL AVAILABLE DISTRIBUTION:{_fmt_money(available_int + available_prin)}")
        log_lines.append("")

        for evt in trigger_events:
            log_lines.append(f"  [EVENT] {evt}")
        if trigger_events:
            log_lines.append("")

        # INTEREST WATERFALL (sequential)
        log_lines.append("  -- INTEREST DISTRIBUTION (PSA s.4.01(a)) --")
        int_remaining = available_int
        # IO strip first
        for _, row in io_bonds.iterrows():
            strip = row["balance"] * row["coupon_pct"] / 100 / 12
            strip = min(strip, int_remaining * 0.10)
            int_remaining -= strip
            log_lines.append(f"    Class {row['class_name']:<4}  Interest Paid: {_fmt_money(strip)}")
        for idx, row in par_bonds.iterrows():
            accrued = balances[idx] * coupons[idx] / 100 / 12
            paid = min(accrued, int_remaining)
            shortfall = accrued - paid
            int_remaining -= paid
            tag = "" if shortfall == 0 else f"  [SHORTFALL {_fmt_money(shortfall)}]"
            log_lines.append(f"    Class {names[idx]:<4}  Accrued: {_fmt_money(accrued)}  Paid: {_fmt_money(paid)}{tag}")
        log_lines.append("")

        # PRINCIPAL WATERFALL - sequential
        log_lines.append("  -- PRINCIPAL DISTRIBUTION (PSA s.4.01(b), sequential) --")
        prin_remaining = available_prin
        paid_per_tranche = {}
        for idx, row in par_bonds.iterrows():
            if prin_remaining <= 0:
                paid_per_tranche[idx] = 0.0
                continue
            pay = min(balances[idx], prin_remaining)
            balances[idx] -= pay
            prin_remaining -= pay
            paid_per_tranche[idx] = pay
            log_lines.append(
                f"    Class {names[idx]:<4}  Principal Paid: {_fmt_money(pay):>18}  "
                f"New Balance: {_fmt_money(balances[idx])}"
            )
        log_lines.append("")

        # LOSSES (reverse sequential)
        if loss_this_period > 0:
            log_lines.append("  -- REALIZED LOSS ALLOCATION (reverse sequential) --")
            loss_remaining = loss_this_period
            for idx in reversed(list(par_bonds.index)):
                if loss_remaining <= 0:
                    break
                absorb = min(balances[idx], loss_remaining)
                balances[idx] -= absorb
                loss_remaining -= absorb
                log_lines.append(
                    f"    Class {names[idx]:<4}  Loss Allocated: {_fmt_money(absorb):>18}  "
                    f"New Balance: {_fmt_money(balances[idx])}"
                )
            cumulative_losses += loss_this_period
            log_lines.append("")

        log_lines.append(f"  Cumulative Realized Losses: {_fmt_money(cumulative_losses)}")
        log_lines.append("")

        # update pool balance
        pool_balance = max(0.0, pool_balance - scheduled_prin - prepayments - recoveries)
        # (recoveries reduce the pool even though they partially become loss)

        remit_rows.append({
            "period": m + 1,
            "distribution_date": pay_date.isoformat(),
            "pool_balance_bop": round(period_balance, 2),
            "scheduled_interest": round(scheduled_int, 2),
            "scheduled_principal": round(scheduled_prin, 2),
            "prepayments": round(prepayments, 2),
            "liquidation_proceeds": round(recoveries, 2),
            "realized_loss": round(loss_this_period, 2),
            "cumulative_loss": round(cumulative_losses, 2),
            "trigger_events": " | ".join(trigger_events) or "",
        })

    return "\n".join(log_lines), pd.DataFrame(remit_rows)


# ---------------------------------------------------------------------------
# PROSPECTUS PDF
# ---------------------------------------------------------------------------


PROSPECTUS_BODY = """\
PROSPECTUS SUPPLEMENT (To Prospectus Dated June 12, 2024)

{full_name}
Commercial Mortgage Pass-Through Certificates, Series 2024-CMBS1

The certificates offered by this prospectus supplement and the accompanying
prospectus (the "Offered Certificates") are part of a series designated as
Commercial Mortgage Pass-Through Certificates, Series 2024-CMBS1. The
Offered Certificates represent beneficial ownership interests in the Issuing
Entity, which is a New York common law trust.

---------------------------------------------------------------
TRANSACTION PARTIES
---------------------------------------------------------------
Depositor:                    Morgan Stanley Capital I Inc.
Sponsors:                     Morgan Stanley Mortgage Capital Holdings LLC
                              Bank of America, National Association
                              Citi Real Estate Funding Inc.
Master Servicer:              {master_servicer}
Special Servicer:             {special_servicer}
Trustee:                      {trustee}
Certificate Administrator:    {certificate_administrator}
Operating Advisor:            Park Bridge Lender Services LLC

---------------------------------------------------------------
KEY DATES
---------------------------------------------------------------
Cut-off Date:                 {cutoff_date}
Closing Date:                 {closing_date}
First Distribution Date:      {first_payment_date}
Distribution Date:            {distribution_date}
Expected Final Distribution:  {expected_final_distribution}
Rated Final Distribution:     {rated_final_distribution}

---------------------------------------------------------------
POOL SUMMARY
---------------------------------------------------------------
Initial Pool Balance:         {pool_balance}
Number of Mortgage Loans:     {loan_count}
Number of Mortgaged Props:    {property_count}
WA Mortgage Rate:             {wa_rate:.4f}%
WA U/W NCF DSCR:              {wa_dscr:.2f}x
WA Cut-off Date LTV:          {wa_ltv:.1f}%
WA Remaining Term to Mat:     ~117 months
Top 10 Loan Concentration:    {top10_conc:.1f}%
Largest Property Type:        {top_type} ({top_type_pct:.1f}%)
Largest State:                {top_state} ({top_state_pct:.1f}%)

---------------------------------------------------------------
PRIORITY OF DISTRIBUTIONS
---------------------------------------------------------------
On each Distribution Date, amounts available in the Distribution Account
after payment of Trust Fund Expenses will be distributed in the following
order of priority (summarized):

  (1) to the Class A-1, A-2, A-3, A-SB, A-S and X-A Certificates,
      current Interest Distribution Amounts, pro rata, based on entitlement;
  (2) to the Class A-1, A-2, A-3, A-SB Certificates sequentially, then
      to the Class A-S Certificates, Principal Distribution Amounts until
      reduced to zero;
  (3) to reimburse the Class A Certificates for previously unreimbursed
      Realized Losses;
  (4) to the Class B, C, D, E, F, and NR Certificates, in that order,
      current and unpaid Interest Distribution Amounts;
  (5) sequentially to the Class B through NR Certificates, Principal
      Distribution Amounts until each is reduced to zero;
  (6) to reimburse subordinate classes for unreimbursed Realized Losses
      in reverse order of subordination;
  (7) any remaining amounts to the Class R Certificates.

Realized Losses are allocated in reverse order of seniority beginning with
the Class NR Certificates, then to the Class F, E, D, C, B, A-S, A-SB, A-3,
A-2 and A-1 Certificates, in that order, and will reduce the Notional
Amount of the Class X-B Certificates to the extent such losses are
allocated to the related Classes.

---------------------------------------------------------------
TRIGGER EVENTS
---------------------------------------------------------------
A "Collateral Deficiency Event" exists if, on any Determination Date, the
Collateral Deficiency Amount (the aggregate outstanding principal balance
of all Specially Serviced Loans and the aggregate Appraisal Reduction
Amount) equals or exceeds 25% of the aggregate Stated Principal Balance of
the mortgage pool.

A "Control Event" occurs when the aggregate principal balance of the Class
E, F and NR Certificates, net of cumulative Appraisal Reduction Amounts
and Realized Losses allocated thereto, is less than 25% of their initial
certificate balance. Upon a Control Event, the Controlling Class shifts
from the Class NR to the most senior remaining subordinate class.

---------------------------------------------------------------
RISK FACTORS (selected)
---------------------------------------------------------------
* Concentration risk: the three largest loans represent approximately
  {top3_conc:.1f}% of the pool.
* Property type risk: {top_type} properties (the largest concentration at
  {top_type_pct:.1f}%) are particularly sensitive to remote-work trends
  and rising operating expenses.
* Geographic risk: {top_state} represents {top_state_pct:.1f}% of the pool
  by balance.
* Interest shortfall risk: the Special Servicer may reduce P&I Advances
  following an Appraisal Reduction Event, which could cause interest
  shortfalls on subordinate certificates.
* Extension risk: many loans are structured with interest-only periods and
  balloon maturities. Adverse capital markets conditions could delay
  refinancing and extend the weighted average life of the certificates.

---------------------------------------------------------------
CERTAIN PSA SECTIONS REFERENCED IN THIS OFFERING
---------------------------------------------------------------
Section 3.18 - Appraisal Reductions and Implementation
Section 4.01 - Priority of Distributions
Section 4.07 - Interest and Principal Advances
Section 8.02 - Realized Loss Allocation
Section 9.11 - Controlling Class Rights and Notices

This is a summary only. Investors should rely on the definitive PSA and
full Offering Circular, which are available on EDGAR under CIK {cik}.
"""


def generate_prospectus_pdf(loan_tape: pd.DataFrame, out_path: Path) -> None:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Preformatted, PageBreak, Table, TableStyle
    )
    from reportlab.lib import colors

    pool_balance = float(loan_tape["current_balance"].sum())
    wa_rate = float((loan_tape["note_rate_pct"] * loan_tape["current_balance"]).sum() / pool_balance)
    wa_dscr = float((loan_tape["dscr_ncf"] * loan_tape["current_balance"]).sum() / pool_balance)
    wa_ltv = float((loan_tape["ltv_pct"] * loan_tape["current_balance"]).sum() / pool_balance)
    top10 = float(loan_tape.head(10)["current_balance"].sum() / pool_balance * 100)
    top3 = float(loan_tape.head(3)["current_balance"].sum() / pool_balance * 100)
    ptype_mix = (loan_tape.groupby("property_type")["current_balance"].sum() / pool_balance * 100).sort_values(ascending=False)
    state_mix = (loan_tape.groupby("state")["current_balance"].sum() / pool_balance * 100).sort_values(ascending=False)

    body = PROSPECTUS_BODY.format(
        full_name=DEAL["full_name"],
        master_servicer=DEAL["master_servicer"],
        special_servicer=DEAL["special_servicer"],
        trustee=DEAL["trustee"],
        certificate_administrator=DEAL["certificate_administrator"],
        cutoff_date=DEAL["cutoff_date"],
        closing_date=DEAL["closing_date"],
        first_payment_date=DEAL["first_payment_date"],
        distribution_date=DEAL["distribution_date"],
        expected_final_distribution=DEAL["expected_final_distribution"],
        rated_final_distribution=DEAL["rated_final_distribution"],
        pool_balance=f"${pool_balance:,.0f}",
        loan_count=DEAL["loan_count"],
        property_count=DEAL["property_count"],
        wa_rate=wa_rate, wa_dscr=wa_dscr, wa_ltv=wa_ltv,
        top10_conc=top10, top3_conc=top3,
        top_type=ptype_mix.index[0], top_type_pct=ptype_mix.iloc[0],
        top_state=state_mix.index[0], top_state_pct=state_mix.iloc[0],
        cik=DEAL["sec_cik"],
    )

    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50,
        title=f"{DEAL['deal_name']} Prospectus Supplement",
        author=DEAL["issuer"],
    )
    styles = getSampleStyleSheet()
    mono = ParagraphStyle(
        "mono", parent=styles["Code"], fontName="Courier",
        fontSize=8.5, leading=11,
    )
    title = ParagraphStyle(
        "deal_title", parent=styles["Title"], fontSize=16, alignment=1, spaceAfter=12,
    )

    elements = [
        Paragraph(DEAL["full_name"], title),
        Paragraph(
            "Commercial Mortgage Pass-Through Certificates, Series 2024-CMBS1 "
            "— Prospectus Supplement dated " + DEAL["prospectus_date"],
            styles["Italic"],
        ),
        Spacer(1, 10),
        Preformatted(body, mono),
        PageBreak(),
        Paragraph("Top 10 Loans by Cut-Off Date Balance", styles["Heading2"]),
    ]

    top10_df = loan_tape.head(10)[[
        "loan_id", "property_name", "property_type", "city", "state",
        "current_balance", "dscr_ncf", "ltv_pct", "note_rate_pct", "maturity_date",
    ]].copy()
    top10_df["current_balance"] = top10_df["current_balance"].map(lambda x: f"${x/1e6:.1f}M")
    top10_df["note_rate_pct"] = top10_df["note_rate_pct"].map(lambda x: f"{x:.3f}%")
    top10_df["ltv_pct"] = top10_df["ltv_pct"].map(lambda x: f"{x:.1f}%")
    data = [list(top10_df.columns)] + top10_df.values.tolist()
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
    ]))
    elements.append(tbl)

    elements.append(Spacer(1, 18))
    elements.append(Paragraph("Property Type Composition (% of pool)", styles["Heading2"]))
    ptype_rows = [["Property Type", "% of Pool"]] + [[k, f"{v:.2f}%"] for k, v in ptype_mix.items()]
    tbl2 = Table(ptype_rows, hAlign="LEFT")
    tbl2.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(tbl2)

    doc.build(elements)


# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------


def generate_all(force: bool = False) -> dict:
    """Produce all mock artifacts. Returns paths of generated files."""
    if not force and all(
        p.exists() for p in [
            config.MOCK_LOAN_TAPE, config.MOCK_BOND_STRUCTURE,
            config.MOCK_CASHFLOW_LOG, config.MOCK_REMITTANCE,
            config.MOCK_PROSPECTUS, config.MOCK_DEAL_META,
        ]
    ):
        return {"status": "already_generated", "dir": str(config.SAMPLE_DATA_DIR)}

    loan_tape = generate_loan_tape(n=DEAL["loan_count"])
    pool_balance = float(loan_tape["current_balance"].sum())
    DEAL["total_pool_balance"] = round(pool_balance, 2)

    bonds = generate_bond_structure(pool_balance)
    log_text, remit = generate_waterfall_log(loan_tape, bonds, months=36)

    loan_tape.to_csv(config.MOCK_LOAN_TAPE, index=False)
    bonds.to_csv(config.MOCK_BOND_STRUCTURE, index=False)
    config.MOCK_CASHFLOW_LOG.write_text(log_text, encoding="utf-8")
    remit.to_csv(config.MOCK_REMITTANCE, index=False)

    generate_prospectus_pdf(loan_tape, config.MOCK_PROSPECTUS)
    config.MOCK_DEAL_META.write_text(json.dumps(DEAL, indent=2))

    return {
        "status": "ok",
        "loan_tape": str(config.MOCK_LOAN_TAPE),
        "bonds": str(config.MOCK_BOND_STRUCTURE),
        "waterfall_log": str(config.MOCK_CASHFLOW_LOG),
        "remittance": str(config.MOCK_REMITTANCE),
        "prospectus": str(config.MOCK_PROSPECTUS),
        "deal_meta": str(config.MOCK_DEAL_META),
        "pool_balance": pool_balance,
    }


if __name__ == "__main__":
    info = generate_all(force=True)
    print(json.dumps(info, indent=2))
