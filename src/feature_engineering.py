"""
feature_engineering.py
=======================
Creates supplementary synthetic tables for analyses not supported
by the base PaySim dataset (merchant names, refunds, processing fees).

All synthetic data is:
  - Clearly labelled as SYNTHETIC in column names and documentation.
  - Never described as actual business revenue.
  - Deterministically generated (seeded) for reproducibility.
  - Related to the cleaned PaySim data via transaction_id surrogate key.
"""

from __future__ import annotations

import logging
import random
import string
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

RANDOM_SEED = 42
rng = np.random.default_rng(RANDOM_SEED)
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Merchant name pool (fictional fintech merchants)
# ---------------------------------------------------------------------------

MERCHANT_NAMES = [
    "QuickPay Ltd",        "NovaCash Corp",       "FlexMoney Inc",
    "TrustTx Partners",    "SwiftSettle Co",       "BridgePay Group",
    "ClearFunds SA",       "MoneyBridge GmbH",     "PayNow Technologies",
    "EasyTransfer LLC",    "ZeroBorder Finance",   "GlobalPay Hub",
    "OpenWallet Systems",  "PrimePay Services",    "VaultX Solutions",
    "TrustedMove SA",      "SafeRemit Ltd",        "CoinRoute Corp",
    "TransactPro Inc",     "NetPay Partners",
]

MERCHANT_CATEGORIES = [
    "Retail", "Utilities", "Entertainment", "Food & Beverage", "Healthcare",
    "Education", "Travel", "Insurance", "E-commerce", "Telco",
]

# Fee rate assumption (configurable — explicitly labelled as ESTIMATED)
DEFAULT_FEE_RATE = 0.0025   # 0.25% of transaction amount — MODELED, NOT ACTUAL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_merchant_table(df_cleaned: pd.DataFrame) -> pd.DataFrame:
    """
    Create a synthetic merchant lookup table for PAYMENT and CASH_OUT rows
    that have a 'merchant' destination account (nameDest starts with 'M').

    ⚠️  This is SYNTHETIC data, not from the PaySim source.
        It is generated for analytical demonstration purposes only.

    Parameters
    ----------
    df_cleaned : pd.DataFrame
        Cleaned PaySim dataset (output of clean_paysim).

    Returns
    -------
    pd.DataFrame with columns:
        merchant_id, merchant_name (SYNTHETIC), merchant_category (SYNTHETIC),
        city (SYNTHETIC), country (SYNTHETIC), registration_year (SYNTHETIC)
    """
    log.info("Building SYNTHETIC merchant lookup table…")

    # Extract unique merchant account IDs
    mask_merchant = df_cleaned["nameDest"].str.startswith("M", na=False)
    merchant_ids = df_cleaned.loc[mask_merchant, "nameDest"].unique()

    n = len(merchant_ids)
    log.info("Unique merchant accounts: %d", n)

    merchant_df = pd.DataFrame({"merchant_id": merchant_ids})
    merchant_df["merchant_name_SYNTHETIC"] = [
        MERCHANT_NAMES[i % len(MERCHANT_NAMES)] + f" #{i + 1:04d}"
        for i in range(n)
    ]
    merchant_df["merchant_category_SYNTHETIC"] = rng.choice(MERCHANT_CATEGORIES, size=n)
    merchant_df["city_SYNTHETIC"] = rng.choice(
        ["Lagos", "Nairobi", "Dar es Salaam", "Accra", "Lusaka", "Harare"], size=n
    )
    merchant_df["country_SYNTHETIC"] = rng.choice(
        ["Nigeria", "Kenya", "Tanzania", "Ghana", "Zambia", "Zimbabwe"], size=n
    )
    merchant_df["registration_year_SYNTHETIC"] = rng.integers(2010, 2020, size=n)
    merchant_df["data_origin"] = "SYNTHETIC — generated for analytical demonstration"

    return merchant_df


def build_refund_table(
    df_cleaned: pd.DataFrame,
    refund_rate: float = 0.01,
    random_state: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Create a synthetic refund table by randomly sampling ~1% of PAYMENT
    and CASH_OUT transactions.

    ⚠️  SYNTHETIC data. Refund amounts and reasons are simulated.

    Returns
    -------
    pd.DataFrame with columns:
        refund_id, original_step, refund_amount_SYNTHETIC,
        refund_reason_SYNTHETIC, refund_status_SYNTHETIC, data_origin
    """
    log.info("Building SYNTHETIC refund table (rate=%.2f%%)…", refund_rate * 100)

    refundable = df_cleaned[
        df_cleaned["type"].isin(["PAYMENT", "CASH_OUT"]) & ~df_cleaned["any_quality_flag"]
    ].copy()

    n_refunds = max(1, int(len(refundable) * refund_rate))
    sampled = refundable.sample(n=min(n_refunds, len(refundable)), random_state=random_state)

    rng2 = np.random.default_rng(random_state)
    refund_df = pd.DataFrame({
        "refund_id": [f"REF-{i:06d}" for i in range(len(sampled))],
        "original_step": sampled["step"].values,
        "original_nameOrig": sampled["nameOrig"].values,
        "original_amount": sampled["amount"].values,
        "refund_amount_SYNTHETIC": sampled["amount"].values * rng2.uniform(0.5, 1.0, size=len(sampled)),
        "refund_reason_SYNTHETIC": rng2.choice(
            ["Customer dispute", "Merchant error", "Duplicate charge",
             "Service not rendered", "Technical error"],
            size=len(sampled),
        ),
        "refund_status_SYNTHETIC": rng2.choice(
            ["Approved", "Pending", "Rejected"], size=len(sampled), p=[0.75, 0.15, 0.10]
        ),
        "data_origin": "SYNTHETIC — generated for analytical demonstration",
    })

    log.info("Synthetic refund records created: %d", len(refund_df))
    return refund_df


def compute_estimated_revenue(
    df_cleaned: pd.DataFrame,
    fee_rate: float = DEFAULT_FEE_RATE,
) -> pd.DataFrame:
    """
    Add an ESTIMATED revenue column using a configurable fee assumption.

    ⚠️  This is MODELED/ESTIMATED revenue, not actual business data.
        Default fee_rate = 0.25% (industry typical for mobile money).
        Adjust fee_rate to see sensitivity.

    Returns
    -------
    pd.DataFrame with additional column: estimated_revenue_MODELED
    """
    log.info(
        "Computing ESTIMATED revenue (fee_rate=%.4f%% — MODELED, NOT ACTUAL)…",
        fee_rate * 100,
    )
    df = df_cleaned.copy()
    # Revenue is only modeled for successful-looking (non-fraud-flagged) transactions
    eligible = ~df["any_quality_flag"] & (df["amount"] > 0)
    df["estimated_revenue_MODELED"] = 0.0
    df.loc[eligible, "estimated_revenue_MODELED"] = df.loc[eligible, "amount"] * fee_rate
    total_est = df["estimated_revenue_MODELED"].sum()
    log.info(
        "ESTIMATED total revenue at %.4f%% rate: %.2f (MODELED — see assumptions).",
        fee_rate * 100, total_est,
    )
    return df


def build_kpi_summary(
    df_cleaned: pd.DataFrame,
    refund_df: pd.DataFrame | None = None,
    fee_rate: float = DEFAULT_FEE_RATE,
) -> dict[str, Any]:
    """
    Calculate all supported business KPIs from the cleaned dataset.

    KPI Definitions
    ---------------
    total_transactions       : Row count in cleaned dataset (all rows)
    total_amount             : Sum of 'amount' column
    avg_amount               : Mean of 'amount' column
    median_amount            : Median of 'amount' column
    fraud_count              : Rows where isFraud == 1
    fraud_rate               : fraud_count / total_transactions (%)
    data_quality_exceptions  : Rows where any_quality_flag == True
    data_quality_rate        : exceptions / total_transactions (%)
    estimated_revenue_MODELED: Sum of amount * fee_rate for non-flagged rows
    refund_count_SYNTHETIC   : Row count of synthetic refund table (if provided)
    refund_total_SYNTHETIC   : Sum of refund_amount_SYNTHETIC (if provided)
    refund_rate_SYNTHETIC     : refund_count / total_transactions (%)
    """
    n = len(df_cleaned)
    total_amount = float(df_cleaned["amount"].sum()) if "amount" in df_cleaned.columns else 0.0
    avg_amount = float(df_cleaned["amount"].mean()) if "amount" in df_cleaned.columns else 0.0
    median_amount = float(df_cleaned["amount"].median()) if "amount" in df_cleaned.columns else 0.0

    fraud_count = int(df_cleaned["isFraud"].sum()) if "isFraud" in df_cleaned.columns else 0
    fraud_rate = round(fraud_count / n * 100, 4) if n else 0.0

    exceptions = int(df_cleaned["any_quality_flag"].sum()) if "any_quality_flag" in df_cleaned.columns else 0
    dq_rate = round(exceptions / n * 100, 4) if n else 0.0

    # Estimated revenue (MODELED)
    eligible = (
        ~df_cleaned.get("any_quality_flag", pd.Series(False, index=df_cleaned.index))
        & (df_cleaned.get("amount", pd.Series(0.0, index=df_cleaned.index)) > 0)
    )
    est_revenue = float(df_cleaned.loc[eligible, "amount"].sum() * fee_rate)

    kpis: dict[str, Any] = {
        # --- Source metrics ---
        "total_transactions": n,
        "total_amount": round(total_amount, 2),
        "avg_amount": round(avg_amount, 2),
        "median_amount": round(median_amount, 2),
        "fraud_count": fraud_count,
        "fraud_rate_pct": fraud_rate,
        "data_quality_exceptions": exceptions,
        "data_quality_rate_pct": dq_rate,
        # --- Modeled metric (explicitly labelled) ---
        "estimated_revenue_MODELED": round(est_revenue, 2),
        "fee_rate_assumption_pct": round(fee_rate * 100, 4),
        "estimated_revenue_note": (
            "MODELED value. Assumes a flat fee of "
            f"{fee_rate*100:.4f}% per transaction. "
            "NOT actual business revenue."
        ),
    }

    # --- Synthetic refund metrics ---
    if refund_df is not None:
        approved = refund_df[refund_df.get("refund_status_SYNTHETIC", pd.Series()) == "Approved"]
        kpis.update({
            "refund_count_SYNTHETIC": len(refund_df),
            "refund_total_SYNTHETIC": round(float(refund_df["refund_amount_SYNTHETIC"].sum()), 2),
            "refund_approved_count_SYNTHETIC": len(approved),
            "refund_rate_pct_SYNTHETIC": round(len(refund_df) / n * 100, 4) if n else 0.0,
            "refund_note": "SYNTHETIC — generated for analytical demonstration only.",
        })

    return kpis
