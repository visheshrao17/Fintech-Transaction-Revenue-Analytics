"""
clean_data.py
=============
Reusable, modular data-cleaning pipeline for the PaySim dataset.

Cleaning rules (documented):
  1.  RENAME  — standardise column names (strip whitespace).
  2.  DEDUP   — identify and remove exact duplicate rows; keep first occurrence.
  3.  MISSING — flag rows with nulls in critical fields; do not drop them silently.
  4.  NEGAMT  — flag rows where amount < 0 (invalid for PaySim).
  5.  ZERO_AMT— flag zero-amount rows (unusual but preserved).
  6.  STEP    — validate step is a positive integer (1–744 for 30-day simulation).
  7.  TYPE    — validate transaction type is one of the five known PaySim types.
  8.  BALANCE — flag originator and destination balance inconsistencies.
  9.  DERIVED — add helper columns: transaction_month, hour_of_day, amount_band,
                is_large_transaction, orig_balance_delta, dest_balance_delta.
  10. FRAUD   — retain isFraud label; add readable fraud_label column.

Records are NEVER silently deleted.  Flagged rows go into a separate
rejected/flagged file; the main cleaned file retains all original rows.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}
STEP_MIN, STEP_MAX = 1, 744          # PaySim simulates 30 days × 24 steps/day
AMOUNT_BAND_BINS = [0, 1_000, 10_000, 100_000, 500_000, np.inf]
AMOUNT_BAND_LABELS = ["<1K", "1K-10K", "10K-100K", "100K-500K", ">500K"]
LARGE_TX_THRESHOLD = 200_000         # USD equivalent in PaySim units
BALANCE_TOLERANCE = 1.0              # floating-point tolerance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clean_paysim(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Run the full cleaning pipeline on a raw PaySim DataFrame.

    Returns
    -------
    cleaned : pd.DataFrame
        All original rows, with flag columns added.
    flagged : pd.DataFrame
        Subset of rows that triggered at least one quality flag.
    report  : dict
        Counts and percentages for each cleaning rule.
    """
    log.info("Starting cleaning pipeline (%d rows)…", len(df))
    df = df.copy()

    report: dict[str, Any] = {"input_rows": len(df)}
    flag_cols: list[str] = []

    # -- 1. Duplicates --------------------------------------------------------
    df, report = _flag_duplicates(df, report)
    flag_cols.append("flag_duplicate")

    # -- 2. Missing critical values -------------------------------------------
    df, report = _flag_missing(df, report)
    flag_cols.append("flag_missing_critical")

    # -- 3. Negative amounts --------------------------------------------------
    df, report = _flag_negative_amount(df, report)
    flag_cols.append("flag_negative_amount")

    # -- 4. Zero amounts ------------------------------------------------------
    df, report = _flag_zero_amount(df, report)
    flag_cols.append("flag_zero_amount")

    # -- 5. Invalid step values -----------------------------------------------
    df, report = _flag_invalid_step(df, report)
    flag_cols.append("flag_invalid_step")

    # -- 6. Invalid transaction types -----------------------------------------
    df, report = _flag_invalid_type(df, report)
    flag_cols.append("flag_invalid_type")

    # -- 7. Balance inconsistencies -------------------------------------------
    df, report = _flag_balance_issues(df, report)
    flag_cols.extend(["flag_orig_balance_mismatch", "flag_dest_balance_mismatch",
                       "flag_negative_balance"])

    # -- 8. Derived columns ---------------------------------------------------
    df = _add_derived_columns(df)

    # -- 9. Composite quality flag --------------------------------------------
    df["any_quality_flag"] = df[flag_cols].any(axis=1)

    total = len(df)
    n_flagged = int(df["any_quality_flag"].sum())
    report["flagged_rows"] = n_flagged
    report["flagged_pct"] = round(n_flagged / total * 100, 4) if total else 0.0
    report["clean_rows"] = total - n_flagged
    report["output_rows"] = total  # ALL rows retained

    flagged = df[df["any_quality_flag"]].copy()

    log.info(
        "Pipeline complete. Total: %d | Flagged: %d (%.2f%%) | Clean: %d",
        total, n_flagged, report["flagged_pct"], report["clean_rows"],
    )
    return df, flagged, report


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _flag_duplicates(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    subset_cols = [c for c in ["step", "type", "amount", "nameOrig", "nameDest"] if c in df.columns]
    dup_mask = df.duplicated(subset=subset_cols, keep="first")
    df["flag_duplicate"] = dup_mask
    n = int(dup_mask.sum())
    report["duplicate_rows"] = n
    report["duplicate_pct"] = round(n / len(df) * 100, 4) if len(df) else 0.0
    if n:
        log.warning("Duplicates found: %d rows (%.2f%%)", n, report["duplicate_pct"])
    return df, report


def _flag_missing(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    critical = [c for c in ["step", "type", "amount", "nameOrig", "nameDest"] if c in df.columns]
    missing_mask = df[critical].isna().any(axis=1)
    df["flag_missing_critical"] = missing_mask
    n = int(missing_mask.sum())
    report["missing_critical_rows"] = n
    if n:
        log.warning("Rows with missing critical fields: %d", n)
    return df, report


def _flag_negative_amount(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    if "amount" not in df.columns:
        df["flag_negative_amount"] = False
        report["negative_amount_rows"] = 0
        return df, report
    mask = df["amount"] < 0
    df["flag_negative_amount"] = mask
    n = int(mask.sum())
    report["negative_amount_rows"] = n
    if n:
        log.warning("Negative amounts: %d rows", n)
    return df, report


def _flag_zero_amount(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    if "amount" not in df.columns:
        df["flag_zero_amount"] = False
        report["zero_amount_rows"] = 0
        return df, report
    mask = df["amount"] == 0
    df["flag_zero_amount"] = mask
    n = int(mask.sum())
    report["zero_amount_rows"] = n
    if n:
        log.info("Zero-amount transactions: %d rows (preserved).", n)
    return df, report


def _flag_invalid_step(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    if "step" not in df.columns:
        df["flag_invalid_step"] = False
        report["invalid_step_rows"] = 0
        return df, report
    mask = ~df["step"].between(STEP_MIN, STEP_MAX)
    df["flag_invalid_step"] = mask
    n = int(mask.sum())
    report["invalid_step_rows"] = n
    if n:
        log.warning("Invalid step values (outside 1–744): %d rows", n)
    return df, report


def _flag_invalid_type(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    if "type" not in df.columns:
        df["flag_invalid_type"] = False
        report["invalid_type_rows"] = 0
        return df, report
    type_str = df["type"].astype(str).str.strip().str.upper()
    mask = ~type_str.isin(VALID_TYPES)
    df["flag_invalid_type"] = mask
    n = int(mask.sum())
    report["invalid_type_rows"] = n
    if n:
        log.warning("Invalid transaction types: %d rows", n)
    return df, report


def _flag_balance_issues(df: pd.DataFrame, report: dict) -> tuple[pd.DataFrame, dict]:
    """Flag rows where balance changes don't match transaction amounts."""
    has_all = all(c in df.columns for c in
                  ["amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"])

    if not has_all:
        for col in ["flag_orig_balance_mismatch", "flag_dest_balance_mismatch", "flag_negative_balance"]:
            df[col] = False
        return df, report

    # Originator: oldbalanceOrg - amount should ≈ newbalanceOrig
    # (only meaningful for debit-type transactions; check directional mismatch)
    orig_delta = df["oldbalanceOrg"] - df["amount"]
    orig_mismatch = (orig_delta - df["newbalanceOrig"]).abs() > BALANCE_TOLERANCE
    # Exclude rows where both old and new balances are 0 (merchant accounts)
    both_zero_orig = (df["oldbalanceOrg"] == 0) & (df["newbalanceOrig"] == 0)
    orig_mismatch = orig_mismatch & ~both_zero_orig
    df["flag_orig_balance_mismatch"] = orig_mismatch

    # Destination: oldbalanceDest + amount should ≈ newbalanceDest
    dest_delta = df["oldbalanceDest"] + df["amount"]
    dest_mismatch = (dest_delta - df["newbalanceDest"]).abs() > BALANCE_TOLERANCE
    both_zero_dest = (df["oldbalanceDest"] == 0) & (df["newbalanceDest"] == 0)
    dest_mismatch = dest_mismatch & ~both_zero_dest
    df["flag_dest_balance_mismatch"] = dest_mismatch

    # Negative balance check
    neg_cols = ["oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]
    neg_balance = (df[neg_cols] < 0).any(axis=1)
    df["flag_negative_balance"] = neg_balance

    n_orig = int(orig_mismatch.sum())
    n_dest = int(dest_mismatch.sum())
    n_neg = int(neg_balance.sum())
    report.update({
        "orig_balance_mismatch_rows": n_orig,
        "dest_balance_mismatch_rows": n_dest,
        "negative_balance_rows": n_neg,
        "orig_balance_mismatch_pct": round(n_orig / len(df) * 100, 4),
        "dest_balance_mismatch_pct": round(n_dest / len(df) * 100, 4),
    })
    log.info(
        "Balance mismatches — orig: %d | dest: %d | negative: %d",
        n_orig, n_dest, n_neg,
    )
    return df, report


def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add business-useful derived columns."""
    # Transaction month (PaySim step maps to hours; 24 steps = 1 day)
    if "step" in df.columns:
        df["day_of_sim"] = ((df["step"] - 1) // 24) + 1         # 1-indexed day
        df["transaction_month"] = ((df["step"] - 1) // (24 * 30)) + 1  # rough month
        df["hour_of_day"] = (df["step"] - 1) % 24

    # Amount band
    if "amount" in df.columns:
        df["amount_band"] = pd.cut(
            df["amount"],
            bins=AMOUNT_BAND_BINS,
            labels=AMOUNT_BAND_LABELS,
            right=True,
        )
        df["is_large_transaction"] = df["amount"] >= LARGE_TX_THRESHOLD

    # Balance deltas
    if all(c in df.columns for c in ["oldbalanceOrg", "newbalanceOrig"]):
        df["orig_balance_delta"] = df["newbalanceOrig"] - df["oldbalanceOrg"]
    if all(c in df.columns for c in ["oldbalanceDest", "newbalanceDest"]):
        df["dest_balance_delta"] = df["newbalanceDest"] - df["oldbalanceDest"]

    # Readable fraud label
    if "isFraud" in df.columns:
        df["fraud_label"] = df["isFraud"].map({0: "Legitimate", 1: "Fraudulent"})

    return df
