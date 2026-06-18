"""
profile_data.py
===============
Data profiling utilities for the PaySim dataset.

Generates a rich profile report covering:
  - Shape and dtypes
  - Missing-value counts and rates
  - Numeric summary statistics
  - Cardinality / unique-value analysis
  - Sample values per column
  - Skewness, kurtosis, and outlier flags
  - Balance-field relationship checks

Usage
-----
  from src.profile_data import profile_dataset
  profile = profile_dataset(df)
  profile.to_csv("outputs/data_profile.csv", index=False)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def profile_dataset(df: pd.DataFrame) -> dict[str, Any]:
    """Return a comprehensive profile of *df*.

    Returns
    -------
    dict with keys:
      shape, dtypes, missing, numeric_stats, cardinality,
      sample_values, balance_checks, skewness, kurtosis
    """
    log.info("Profiling dataset (%d rows × %d cols)…", *df.shape)

    profile: dict[str, Any] = {
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "dtypes": df.dtypes.astype(str).to_dict(),
        "missing": _missing_summary(df),
        "numeric_stats": _numeric_stats(df),
        "cardinality": _cardinality(df),
        "sample_values": _sample_values(df),
        "balance_checks": _balance_checks(df),
        "skewness": _skewness(df),
        "kurtosis": _kurtosis(df),
    }

    _log_profile_summary(profile)
    return profile


def profile_to_dataframe(profile: dict[str, Any]) -> pd.DataFrame:
    """Flatten the profile dict into a single summary DataFrame for export."""
    rows = []
    missing = profile["missing"]
    cardinality = profile["cardinality"]
    numeric = profile["numeric_stats"]
    skewness = profile.get("skewness", {})
    kurtosis = profile.get("kurtosis", {})

    for col in missing.keys():
        row = {
            "column": col,
            "dtype": profile["dtypes"].get(col, ""),
            "missing_count": missing[col]["count"],
            "missing_pct": round(missing[col]["pct"], 4),
            "unique_values": cardinality.get(col, {}).get("unique", ""),
            "top_value": cardinality.get(col, {}).get("top", ""),
        }
        if col in numeric:
            ns = numeric[col]
            row.update(
                {
                    "mean": ns.get("mean"),
                    "median": ns.get("median"),
                    "std": ns.get("std"),
                    "min": ns.get("min"),
                    "max": ns.get("max"),
                    "q25": ns.get("q25"),
                    "q75": ns.get("q75"),
                    "skewness": skewness.get(col),
                    "kurtosis": kurtosis.get(col),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _missing_summary(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    total = len(df)
    result = {}
    for col in df.columns:
        n = int(df[col].isna().sum())
        result[col] = {"count": n, "pct": round(n / total * 100, 4) if total else 0.0}
    return result


def _numeric_stats(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    result = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        result[col] = {
            "mean": round(float(s.mean()), 4),
            "median": round(float(s.median()), 4),
            "std": round(float(s.std()), 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
            "q25": round(float(s.quantile(0.25)), 4),
            "q75": round(float(s.quantile(0.75)), 4),
        }
    return result


def _cardinality(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result = {}
    for col in df.columns:
        vc = df[col].value_counts(dropna=False)
        result[col] = {
            "unique": int(df[col].nunique(dropna=False)),
            "top": str(vc.index[0]) if not vc.empty else "",
            "top_freq": int(vc.iloc[0]) if not vc.empty else 0,
        }
    return result


def _sample_values(df: pd.DataFrame, n: int = 5) -> dict[str, list]:
    return {col: df[col].dropna().head(n).tolist() for col in df.columns}


def _balance_checks(df: pd.DataFrame) -> dict[str, Any]:
    """Check whether balance changes are consistent with transaction amounts."""
    checks: dict[str, Any] = {}

    # Originator balance change should equal amount for non-fraud CASH_OUT / TRANSFER
    for field_pair in [
        ("oldbalanceOrg", "newbalanceOrig", "orig"),
        ("oldbalanceDest", "newbalanceDest", "dest"),
    ]:
        old_col, new_col, label = field_pair
        if old_col in df.columns and new_col in df.columns and "amount" in df.columns:
            delta = (df[old_col] - df[new_col]).abs()
            amount_col = df["amount"]
            # Allow small floating-point tolerance
            mismatch = ((delta - amount_col).abs() > 1.0).sum()
            checks[f"{label}_balance_mismatch_count"] = int(mismatch)
            checks[f"{label}_balance_mismatch_pct"] = round(
                mismatch / len(df) * 100, 4
            ) if len(df) else 0.0

    # Negative balance detection
    for col in ["oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]:
        if col in df.columns:
            neg = (df[col] < 0).sum()
            checks[f"{col}_negative_count"] = int(neg)

    return checks


def _skewness(df: pd.DataFrame) -> dict[str, float]:
    return {
        col: round(float(df[col].dropna().skew()), 4)
        for col in df.select_dtypes(include=[np.number]).columns
    }


def _kurtosis(df: pd.DataFrame) -> dict[str, float]:
    return {
        col: round(float(df[col].dropna().kurtosis()), 4)
        for col in df.select_dtypes(include=[np.number]).columns
    }


def _log_profile_summary(profile: dict[str, Any]) -> None:
    shape = profile["shape"]
    log.info("Rows: %d | Columns: %d", shape["rows"], shape["columns"])
    missing = profile["missing"]
    cols_with_missing = {c: v for c, v in missing.items() if v["count"] > 0}
    if cols_with_missing:
        log.warning("Columns with missing values: %s", list(cols_with_missing.keys()))
    else:
        log.info("No missing values detected.")
    checks = profile.get("balance_checks", {})
    for k, v in checks.items():
        if "mismatch_count" in k and v > 0:
            log.warning("Balance check '%s': %d records", k, v)
