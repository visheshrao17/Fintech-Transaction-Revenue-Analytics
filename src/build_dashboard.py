"""
build_dashboard.py
==================
Generates a professional matplotlib/seaborn dashboard saved as PNG.

Output: outputs/dashboard.png

All metrics are derived from real calculated data — no placeholders.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for server/pipeline use

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Colour palette
PALETTE = {
    "dark_blue":   "#1a3a5c",
    "medium_blue": "#2e6da4",
    "light_blue":  "#6baed6",
    "accent":      "#e67e22",
    "green":       "#27ae60",
    "red":         "#c0392b",
    "light_grey":  "#f4f6f9",
    "dark_grey":   "#2c3e50",
    "gold":        "#f39c12",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_dashboard(
    kpi_summary: dict[str, Any],
    query_results: dict[str, pd.DataFrame],
    output_path: Path | str | None = None,
) -> Path:
    """Render the analytics dashboard and save to PNG.

    Parameters
    ----------
    kpi_summary : dict
        Output from ``build_kpi_summary()``.
    query_results : dict
        Output from ``run_all_queries()``.
    output_path : Path or str, optional
        Override the default output path.

    Returns
    -------
    Path to the saved PNG.
    """
    path = Path(output_path) if output_path else OUTPUTS_DIR / "dashboard.png"
    log.info("Building dashboard → %s", path)

    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": PALETTE["light_grey"],
    })

    fig = plt.figure(figsize=(22, 26), facecolor=PALETTE["light_grey"])
    gs = gridspec.GridSpec(
        5, 4,
        figure=fig,
        hspace=0.55,
        wspace=0.35,
        top=0.94, bottom=0.04,
        left=0.05, right=0.97,
    )

    # -- Header ---------------------------------------------------------------
    _draw_header(fig)

    # -- Row 0: KPI Cards (4 cards across full width) -------------------------
    kpi_data = _extract_kpis(kpi_summary)
    for i, (label, value, unit, color) in enumerate(kpi_data):
        ax = fig.add_subplot(gs[0, i])
        _kpi_card(ax, label, value, unit, color)

    # -- Row 1: Monthly Trends (volume + amount) ------------------------------
    mt = query_results.get("monthly_trends", pd.DataFrame())
    ax_vol = fig.add_subplot(gs[1, :2])
    _monthly_volume_chart(ax_vol, mt)

    ax_amt = fig.add_subplot(gs[1, 2:])
    _monthly_amount_chart(ax_amt, mt)

    # -- Row 2: Transaction Type + Fraud by Type ------------------------------
    ta = query_results.get("type_analysis", pd.DataFrame())
    ax_type = fig.add_subplot(gs[2, :2])
    _type_volume_chart(ax_type, ta)

    ax_fraud_type = fig.add_subplot(gs[2, 2:])
    _fraud_by_type_chart(ax_fraud_type, ta)

    # -- Row 3: Amount Distribution + Hourly Fraud ----------------------------
    ad = query_results.get("amount_distribution", pd.DataFrame())
    ax_amt_dist = fig.add_subplot(gs[3, :2])
    _amount_distribution_chart(ax_amt_dist, ad)

    hf = query_results.get("hourly_fraud", pd.DataFrame())
    ax_hourly = fig.add_subplot(gs[3, 2:])
    _hourly_fraud_chart(ax_hourly, hf)

    # -- Row 4: Balance Reconciliation + Data Quality -------------------------
    br = query_results.get("balance_reconciliation", pd.DataFrame())
    ax_balance = fig.add_subplot(gs[4, :2])
    _balance_reconciliation_chart(ax_balance, br)

    dq = query_results.get("data_quality", pd.DataFrame())
    ax_dq = fig.add_subplot(gs[4, 2:])
    _data_quality_chart(ax_dq, dq)

    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=PALETTE["light_grey"])
    plt.close(fig)
    log.info("Dashboard saved: %s", path)
    return path


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _draw_header(fig: plt.Figure) -> None:
    fig.text(
        0.5, 0.965,
        "Fintech Transaction & Revenue Analytics Dashboard",
        ha="center", va="top",
        fontsize=22, fontweight="bold", color=PALETTE["dark_blue"],
    )
    fig.text(
        0.5, 0.952,
        "Source: PaySim (simulated mobile-money transactions)  |  "
        "MODELED/SYNTHETIC values explicitly labelled",
        ha="center", va="top",
        fontsize=11, color=PALETTE["dark_grey"], style="italic",
    )


def _extract_kpis(kpi: dict) -> list[tuple]:
    """Return list of (label, formatted_value, unit, color) tuples."""
    total_tx = kpi.get("total_transactions", 0)
    total_amt = kpi.get("total_amount", 0)
    fraud_rate = kpi.get("fraud_rate_pct", 0.0)
    dq_rate = kpi.get("data_quality_rate_pct", 0.0)

    return [
        ("Total Transactions",    f"{total_tx:,}",            "",   PALETTE["dark_blue"]),
        ("Total Amount",          f"{total_amt / 1e9:.2f}B",  "USD", PALETTE["medium_blue"]),
        ("Fraud Rate",            f"{fraud_rate:.2f}",         "%",  PALETTE["red"]),
        ("DQ Exception Rate",     f"{dq_rate:.2f}",            "%",  PALETTE["gold"]),
    ]


def _kpi_card(ax: plt.Axes, label: str, value: str, unit: str, color: str) -> None:
    ax.set_facecolor(color)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(0.5, 0.65, value + " " + unit, transform=ax.transAxes,
            ha="center", va="center", fontsize=22, fontweight="bold",
            color="white")
    ax.text(0.5, 0.25, label, transform=ax.transAxes,
            ha="center", va="center", fontsize=11, color="white", alpha=0.9)


def _monthly_volume_chart(ax: plt.Axes, mt: pd.DataFrame) -> None:
    ax.set_title("Monthly Transaction Volume", fontweight="bold", color=PALETTE["dark_blue"])
    if mt.empty or "transaction_count" not in mt.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    x_col = mt.columns[0]
    ax.bar(mt[x_col].astype(str), mt["transaction_count"],
           color=PALETTE["medium_blue"], edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Simulation Month")
    ax.set_ylabel("Transaction Count")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_facecolor(PALETTE["light_grey"])


def _monthly_amount_chart(ax: plt.Axes, mt: pd.DataFrame) -> None:
    ax.set_title("Monthly Total Transaction Amount", fontweight="bold", color=PALETTE["dark_blue"])
    if mt.empty or "total_amount" not in mt.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    x_col = mt.columns[0]
    ax.plot(mt[x_col].astype(str), mt["total_amount"] / 1e6,
            color=PALETTE["accent"], marker="o", linewidth=2, markersize=6)
    ax.fill_between(range(len(mt)), mt["total_amount"] / 1e6,
                    alpha=0.15, color=PALETTE["accent"])
    ax.set_xlabel("Simulation Month")
    ax.set_ylabel("Amount (Millions)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.1f}M"))
    ax.set_facecolor(PALETTE["light_grey"])


def _type_volume_chart(ax: plt.Axes, ta: pd.DataFrame) -> None:
    ax.set_title("Transaction Count by Type", fontweight="bold", color=PALETTE["dark_blue"])
    if ta.empty or "type" not in ta.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    colors = [PALETTE["dark_blue"], PALETTE["medium_blue"], PALETTE["light_blue"],
              PALETTE["accent"], PALETTE["green"]]
    bars = ax.barh(ta["type"], ta["transaction_count"],
                   color=colors[:len(ta)], edgecolor="white")
    ax.set_xlabel("Transaction Count")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}K"))
    for bar, val in zip(bars, ta["transaction_count"]):
        ax.text(bar.get_width() + 0.01 * ta["transaction_count"].max(),
                bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=9)
    ax.set_facecolor(PALETTE["light_grey"])


def _fraud_by_type_chart(ax: plt.Axes, ta: pd.DataFrame) -> None:
    ax.set_title("Fraud Rate by Transaction Type (%)", fontweight="bold", color=PALETTE["dark_blue"])
    if ta.empty or "fraud_rate_pct" not in ta.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    fraud_types = ta[ta["fraud_rate_pct"] > 0]
    if fraud_types.empty:
        fraud_types = ta
    ax.barh(fraud_types["type"], fraud_types["fraud_rate_pct"],
            color=PALETTE["red"], edgecolor="white", alpha=0.85)
    ax.set_xlabel("Fraud Rate (%)")
    ax.set_facecolor(PALETTE["light_grey"])


def _amount_distribution_chart(ax: plt.Axes, ad: pd.DataFrame) -> None:
    ax.set_title("Transaction Count by Amount Band", fontweight="bold", color=PALETTE["dark_blue"])
    if ad.empty or "amount_band" not in ad.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    ax.bar(ad["amount_band"], ad["transaction_count"],
           color=PALETTE["medium_blue"], edgecolor="white")
    ax.set_xlabel("Amount Band")
    ax.set_ylabel("Count")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}K"))
    ax.set_facecolor(PALETTE["light_grey"])


def _hourly_fraud_chart(ax: plt.Axes, hf: pd.DataFrame) -> None:
    ax.set_title("Fraud Count by Hour of Day (Simulation)", fontweight="bold",
                 color=PALETTE["dark_blue"])
    if hf.empty or "hour_of_day" not in hf.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    ax.bar(hf["hour_of_day"], hf["fraud_count"], color=PALETTE["red"], alpha=0.75)
    ax.set_xlabel("Hour of Day (Simulation Step % 24)")
    ax.set_ylabel("Fraud Count")
    ax.set_facecolor(PALETTE["light_grey"])


def _balance_reconciliation_chart(ax: plt.Axes, br: pd.DataFrame) -> None:
    ax.set_title("Balance Mismatch by Transaction Type", fontweight="bold",
                 color=PALETTE["dark_blue"])
    if br.empty or "type" not in br.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    x = np.arange(len(br))
    width = 0.35
    ax.bar(x - width / 2, br.get("orig_mismatch_pct", [0] * len(br)),
           width, label="Orig Balance Mismatch %", color=PALETTE["gold"])
    ax.bar(x + width / 2, br.get("dest_mismatch_pct", [0] * len(br)),
           width, label="Dest Balance Mismatch %", color=PALETTE["accent"])
    ax.set_xticks(x)
    ax.set_xticklabels(br["type"], rotation=15, ha="right")
    ax.set_ylabel("Mismatch %")
    ax.legend(fontsize=8)
    ax.set_facecolor(PALETTE["light_grey"])


def _data_quality_chart(ax: plt.Axes, dq: pd.DataFrame) -> None:
    ax.set_title("Data Quality Exception Counts", fontweight="bold", color=PALETTE["dark_blue"])
    if dq.empty or "flag" not in dq.columns:
        ax.text(0.5, 0.5, "No data", ha="center"); return
    dq_plot = dq[dq["flag"] != "any_quality_flag"].sort_values("count", ascending=True)
    colors = [PALETTE["red"] if c > 0 else PALETTE["green"] for c in dq_plot["count"]]
    ax.barh(dq_plot["flag"].str.replace("flag_", "", regex=False),
            dq_plot["count"], color=colors)
    ax.set_xlabel("Exception Count")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_facecolor(PALETTE["light_grey"])
