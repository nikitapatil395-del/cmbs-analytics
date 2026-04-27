"""Plotly chart factories for CMBS analytics.

Every function returns a ``plotly.graph_objects.Figure`` so callers (Streamlit,
notebooks, scripts) can render or export as they wish. Styling is shared via
:func:`_style` so charts feel like they belong to one toolkit.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ----- shared style -----
COLORWAY = [
    "#1F3A93", "#26A65B", "#D35400", "#8E44AD", "#16A085",
    "#C0392B", "#2C3E50", "#F39C12", "#7F8C8D", "#2980B9",
]

def _style(fig: go.Figure, *, title: str | None = None) -> go.Figure:
    fig.update_layout(
        title=title,
        margin=dict(l=20, r=20, t=60 if title else 20, b=30),
        colorway=COLORWAY,
        template="plotly_white",
        legend=dict(orientation="h", y=-0.18, x=0),
        font=dict(family="Inter, -apple-system, Helvetica, sans-serif", size=12),
    )
    return fig


# ---------------------------------------------------------------------------
# Loan-tape charts
# ---------------------------------------------------------------------------


def property_type_mix(df: pd.DataFrame) -> go.Figure:
    g = df.groupby("property_type")["current_balance"].sum().reset_index()
    g["balance_m"] = g["current_balance"] / 1e6
    fig = px.pie(
        g, values="balance_m", names="property_type", hole=0.55,
        labels={"balance_m": "Balance ($M)"},
    )
    fig.update_traces(textposition="outside", textinfo="label+percent")
    return _style(fig, title="Pool Composition by Property Type")


def state_mix(df: pd.DataFrame, top_n: int = 12) -> go.Figure:
    g = (df.groupby("state")["current_balance"].sum() / 1e6).reset_index()
    g = g.sort_values("current_balance", ascending=True).tail(top_n)
    fig = px.bar(
        g, x="current_balance", y="state", orientation="h",
        labels={"current_balance": "Balance ($M)", "state": ""},
    )
    return _style(fig, title=f"Top {top_n} States by Balance")


def geo_choropleth(df: pd.DataFrame) -> go.Figure:
    g = (df.groupby("state")["current_balance"].sum() / 1e6).reset_index()
    fig = px.choropleth(
        g, locations="state", locationmode="USA-states", color="current_balance",
        scope="usa", color_continuous_scale="Blues",
        labels={"current_balance": "Balance ($M)"},
    )
    fig.update_layout(geo=dict(bgcolor="rgba(0,0,0,0)"))
    return _style(fig, title="Geographic Concentration")


def dscr_histogram(df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        df, x="dscr_ncf", nbins=20,
        labels={"dscr_ncf": "DSCR (NCF)"},
    )
    fig.add_vline(x=1.0, line_dash="dash", line_color="#C0392B",
                  annotation_text="1.00x breakeven", annotation_position="top left")
    fig.add_vline(x=1.25, line_dash="dot", line_color="#F39C12",
                  annotation_text="1.25x common covenant", annotation_position="top right")
    return _style(fig, title="DSCR Distribution")


def ltv_histogram(df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        df, x="ltv_pct", nbins=20,
        labels={"ltv_pct": "LTV (%)"},
    )
    fig.add_vline(x=65, line_dash="dash", line_color="#F39C12",
                  annotation_text="65% typical conduit", annotation_position="top left")
    return _style(fig, title="LTV Distribution")


def dscr_vs_ltv(df: pd.DataFrame) -> go.Figure:
    d = df.copy()
    d["balance_m"] = d["current_balance"] / 1e6
    fig = px.scatter(
        d, x="ltv_pct", y="dscr_ncf", size="balance_m",
        color="property_type", hover_data=["loan_id", "property_name", "state"],
        labels={"ltv_pct": "LTV (%)", "dscr_ncf": "DSCR (NCF)", "balance_m": "Balance ($M)"},
        size_max=45,
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color="#C0392B")
    fig.add_vline(x=65, line_dash="dash", line_color="#F39C12")
    return _style(fig, title="DSCR × LTV (bubble = balance)")


def maturity_ladder(df: pd.DataFrame) -> go.Figure:
    d = df.copy()
    d["maturity_year"] = pd.to_datetime(d["maturity_date"], errors="coerce").dt.year
    g = d.groupby("maturity_year")["current_balance"].sum().reset_index()
    g["balance_m"] = g["current_balance"] / 1e6
    fig = px.bar(g, x="maturity_year", y="balance_m",
                 labels={"maturity_year": "Maturity Year", "balance_m": "Balance ($M)"})
    return _style(fig, title="Maturity Ladder")


def top_loans_bar(df: pd.DataFrame, n: int = 10) -> go.Figure:
    top = df.nlargest(n, "current_balance").copy()
    top["balance_m"] = top["current_balance"] / 1e6
    top = top.sort_values("balance_m")
    fig = px.bar(
        top, x="balance_m", y="property_name", orientation="h",
        color="property_type",
        hover_data=["loan_id", "state", "dscr_ncf", "ltv_pct"],
        labels={"balance_m": "Balance ($M)", "property_name": ""},
    )
    return _style(fig, title=f"Top {n} Loans by Balance")


# ---------------------------------------------------------------------------
# Capital structure
# ---------------------------------------------------------------------------


def capital_stack(bonds: pd.DataFrame) -> go.Figure:
    par = bonds[bonds["tranche_type"] != "IO"].copy()
    par = par.sort_values("payment_order")
    par["balance_m"] = par["balance"] / 1e6
    fig = px.bar(
        par, y="class_name", x="balance_m", color="tranche_type",
        orientation="h",
        hover_data=["coupon_pct", "rating_moodys", "credit_support_pct", "wal_years"],
        labels={"balance_m": "Balance ($M)", "class_name": "Class"},
    )
    fig.update_yaxes(categoryorder="array", categoryarray=par["class_name"].tolist()[::-1])
    return _style(fig, title="Capital Structure (par tranches)")


# ---------------------------------------------------------------------------
# Cashflow / waterfall
# ---------------------------------------------------------------------------


def cashflow_over_time(rem: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("Monthly Distributions ($M)", "Cumulative Realized Loss ($M)"),
        vertical_spacing=0.12, row_heights=[0.65, 0.35],
    )
    fig.add_trace(go.Bar(
        x=rem["distribution_date"], y=rem["scheduled_interest"] / 1e6,
        name="Interest", marker_color=COLORWAY[0],
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=rem["distribution_date"],
        y=(rem["scheduled_principal"] + rem["prepayments"] + rem["liquidation_proceeds"]) / 1e6,
        name="Principal", marker_color=COLORWAY[1],
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=rem["distribution_date"], y=rem["cumulative_loss"] / 1e6,
        name="Cum. Loss", mode="lines+markers",
        line=dict(color=COLORWAY[5], width=3),
    ), row=2, col=1)
    fig.update_layout(barmode="stack")
    return _style(fig, title="Cashflow & Loss Trajectory")


def losses_bar(rem: pd.DataFrame) -> go.Figure:
    d = rem.copy()
    d["loss_m"] = d["realized_loss"] / 1e6
    fig = px.bar(d, x="distribution_date", y="loss_m",
                 labels={"distribution_date": "", "loss_m": "Realized Loss ($M)"})
    fig.update_traces(marker_color=COLORWAY[5])
    return _style(fig, title="Realized Loss by Period")


def prepayment_timeline(rem: pd.DataFrame) -> go.Figure:
    d = rem.copy()
    d["prepay_m"] = d["prepayments"] / 1e6
    d["liq_m"] = d["liquidation_proceeds"] / 1e6
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["distribution_date"], y=d["prepay_m"], name="Prepayments", marker_color=COLORWAY[2]))
    fig.add_trace(go.Bar(x=d["distribution_date"], y=d["liq_m"], name="Liquidations", marker_color=COLORWAY[5]))
    fig.update_layout(barmode="stack", yaxis_title="$M")
    return _style(fig, title="Unscheduled Principal Activity")


def tranche_balance_over_time(tranche_df: pd.DataFrame) -> go.Figure:
    d = tranche_df.sort_values(["class_name", "period"]).copy()
    # Forward-fill ending balance *within each tranche* so we draw a full line
    # even for periods where the tranche didn't receive principal.
    d["ending_balance"] = d.groupby("class_name")["ending_balance"].ffill()
    d["ending_balance_m"] = d["ending_balance"] / 1e6
    # Show only par tranches (IO strips never get principal so ending_balance is all-NaN).
    d = d.dropna(subset=["ending_balance_m"])
    fig = px.line(
        d, x="distribution_date", y="ending_balance_m",
        color="class_name", markers=True,
        labels={"distribution_date": "", "ending_balance_m": "Ending Balance ($M)", "class_name": "Class"},
    )
    return _style(fig, title="Tranche Balances Over Time")


def tranche_interest_paid(tranche_df: pd.DataFrame) -> go.Figure:
    d = tranche_df.copy()
    agg = d.groupby("class_name", as_index=False)["interest_paid"].sum()
    agg["interest_paid_m"] = agg["interest_paid"] / 1e6
    agg = agg.sort_values("interest_paid_m", ascending=True)
    fig = px.bar(
        agg, x="interest_paid_m", y="class_name", orientation="h",
        labels={"interest_paid_m": "Total Interest Paid ($M)", "class_name": "Class"},
    )
    return _style(fig, title="Total Interest Paid by Tranche (36 mo)")


def event_timeline(events_df: pd.DataFrame) -> go.Figure:
    if events_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No trigger events parsed.", showarrow=False)
        return _style(fig, title="Trigger Events")
    d = events_df.copy()
    d["distribution_date"] = pd.to_datetime(d["distribution_date"])
    fig = px.scatter(
        d, x="distribution_date", y="event_type", color="event_type",
        hover_data=["description"], size_max=20,
    )
    fig.update_traces(marker=dict(size=16, line=dict(width=1, color="white")))
    fig.update_yaxes(categoryorder="total ascending")
    return _style(fig, title="Servicing / Trigger Events Timeline")
