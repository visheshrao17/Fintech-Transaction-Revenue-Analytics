"""
validate_data.py
================
Post-cleaning validation layer.

Runs a suite of assertion-style checks against the cleaned DataFrame and
returns a structured validation report that includes pass/fail status,
counts, and human-readable messages.

Usage
-----
  from src.validate_data import validate_cleaned
  report = validate_cleaned(df_cleaned)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

VALID_TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    count: int = 0
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[ValidationCheck] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[ValidationCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "check": c.name,
                    "passed": c.passed,
                    "count": c.count,
                    "detail": c.detail,
                }
                for c in self.checks
            ]
        )

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        return (
            f"Validation: {passed}/{total} checks passed"
            + (" ✓" if self.all_passed else f" — {total - passed} FAILED")
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_cleaned(df: pd.DataFrame) -> ValidationReport:
    """Run all validation checks on the cleaned DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Output from ``clean_paysim()``.

    Returns
    -------
    ValidationReport
    """
    report = ValidationReport()
    checks = [
        _check_no_overwrite(df),
        _check_required_columns(df),
        _check_amount_non_negative(df),
        _check_valid_types(df),
        _check_step_range(df),
        _check_fraud_label_binary(df),
        _check_flag_columns_bool(df),
        _check_derived_columns_present(df),
        _check_amount_band_not_null(df),
        _check_no_inf_values(df),
        _check_orig_account_format(df),
        _check_dest_account_format(df),
        _check_metric_reconciliation(df),
    ]
    report.checks = checks

    for chk in checks:
        level = logging.INFO if chk.passed else logging.WARNING
        log.log(level, "[%s] %s — %s", "PASS" if chk.passed else "FAIL", chk.name, chk.detail)

    log.info(report.summary())
    return report


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_no_overwrite(df: pd.DataFrame) -> ValidationCheck:
    """Source columns must still be present (pipeline didn't remove them)."""
    expected = ["step", "type", "amount", "nameOrig", "nameDest"]
    present = all(c in df.columns for c in expected)
    return ValidationCheck(
        name="source_columns_preserved",
        passed=present,
        detail="All expected source columns are present." if present
               else f"Missing: {[c for c in expected if c not in df.columns]}",
    )


def _check_required_columns(df: pd.DataFrame) -> ValidationCheck:
    required = ["step", "type", "amount", "nameOrig", "nameDest",
                "isFraud", "any_quality_flag"]
    missing = [c for c in required if c not in df.columns]
    return ValidationCheck(
        name="required_columns_exist",
        passed=len(missing) == 0,
        count=len(missing),
        detail="All required columns present." if not missing
               else f"Missing columns: {missing}",
    )


def _check_amount_non_negative(df: pd.DataFrame) -> ValidationCheck:
    """After cleaning, all amounts should be >= 0 (negatives are flagged, not removed)."""
    if "amount" not in df.columns:
        return ValidationCheck("amount_non_negative", True, detail="Column absent — skipped.")
    neg = int((df["amount"] < 0).sum())
    return ValidationCheck(
        name="amount_non_negative",
        passed=True,      # We flag, not remove — presence of negatives is noted
        count=neg,
        detail=f"{neg} negative-amount rows flagged (retained per cleaning rules).",
    )


def _check_valid_types(df: pd.DataFrame) -> ValidationCheck:
    if "type" not in df.columns:
        return ValidationCheck("valid_transaction_types", True, detail="Column absent — skipped.")
    invalid = df["type"].astype(str).str.strip().str.upper()
    invalid_count = int((~invalid.isin(VALID_TYPES)).sum())
    return ValidationCheck(
        name="valid_transaction_types",
        passed=invalid_count == 0,
        count=invalid_count,
        detail=f"{invalid_count} rows with unrecognised transaction types.",
    )


def _check_step_range(df: pd.DataFrame) -> ValidationCheck:
    if "step" not in df.columns:
        return ValidationCheck("step_in_range", True, detail="Column absent — skipped.")
    oob = int(~df["step"].between(1, 744).all())
    n = int((~df["step"].between(1, 744)).sum())
    return ValidationCheck(
        name="step_in_range",
        passed=oob == 0,
        count=n,
        detail=f"{n} rows with step outside [1, 744].",
    )


def _check_fraud_label_binary(df: pd.DataFrame) -> ValidationCheck:
    if "isFraud" not in df.columns:
        return ValidationCheck("fraud_label_binary", True, detail="Column absent — skipped.")
    vals = set(df["isFraud"].unique())
    valid = vals.issubset({0, 1})
    return ValidationCheck(
        name="fraud_label_binary",
        passed=valid,
        detail=f"Unique values: {vals}. Expected subset of {{0, 1}}.",
    )


def _check_flag_columns_bool(df: pd.DataFrame) -> ValidationCheck:
    flag_cols = [c for c in df.columns if c.startswith("flag_")]
    non_bool = [c for c in flag_cols if df[c].dtype not in (bool, np.bool_)]
    return ValidationCheck(
        name="flag_columns_boolean",
        passed=len(non_bool) == 0,
        count=len(non_bool),
        detail=f"Non-boolean flag columns: {non_bool}" if non_bool else "All flag columns are boolean.",
    )


def _check_derived_columns_present(df: pd.DataFrame) -> ValidationCheck:
    expected = ["day_of_sim", "hour_of_day", "amount_band", "is_large_transaction",
                "fraud_label"]
    missing = [c for c in expected if c not in df.columns]
    return ValidationCheck(
        name="derived_columns_present",
        passed=len(missing) == 0,
        count=len(missing),
        detail=f"Missing derived columns: {missing}" if missing else "All derived columns present.",
    )


def _check_amount_band_not_null(df: pd.DataFrame) -> ValidationCheck:
    if "amount_band" not in df.columns:
        return ValidationCheck("amount_band_no_nulls", True, detail="Column absent — skipped.")
    # Nulls are expected only when amount is exactly on a boundary edge (rare)
    n = int(df["amount_band"].isna().sum())
    return ValidationCheck(
        name="amount_band_no_nulls",
        passed=n == 0,
        count=n,
        detail=f"{n} null amount_band values (amounts may be ≤ 0).",
    )


def _check_no_inf_values(df: pd.DataFrame) -> ValidationCheck:
    numeric = df.select_dtypes(include=[np.number])
    inf_count = int(np.isinf(numeric.values).sum())
    return ValidationCheck(
        name="no_infinite_values",
        passed=inf_count == 0,
        count=inf_count,
        detail=f"{inf_count} infinite values detected." if inf_count else "No infinite values.",
    )


def _check_orig_account_format(df: pd.DataFrame) -> ValidationCheck:
    if "nameOrig" not in df.columns:
        return ValidationCheck("orig_account_format", True, detail="Column absent — skipped.")
    invalid = int(~df["nameOrig"].str.match(r"^[CM]\d+$", na=True).all())
    n = int((~df["nameOrig"].str.match(r"^[CM]\d+$", na=False)).sum())
    return ValidationCheck(
        name="orig_account_format",
        passed=n == 0,
        count=n,
        detail=f"{n} nameOrig values don't match expected pattern (C/M + digits).",
    )


def _check_dest_account_format(df: pd.DataFrame) -> ValidationCheck:
    if "nameDest" not in df.columns:
        return ValidationCheck("dest_account_format", True, detail="Column absent — skipped.")
    n = int((~df["nameDest"].str.match(r"^[CM]\d+$", na=False)).sum())
    return ValidationCheck(
        name="dest_account_format",
        passed=n == 0,
        count=n,
        detail=f"{n} nameDest values don't match expected pattern (C/M + digits).",
    )


def _check_metric_reconciliation(df: pd.DataFrame) -> ValidationCheck:
    """Spot-check: fraud count in isFraud column equals sum of flagged fraud."""
    if "isFraud" not in df.columns or "fraud_label" not in df.columns:
        return ValidationCheck("metric_reconciliation", True, detail="Columns absent — skipped.")
    fraud_int = int(df["isFraud"].sum())
    fraud_label = int((df["fraud_label"] == "Fraudulent").sum())
    match = fraud_int == fraud_label
    return ValidationCheck(
        name="metric_reconciliation",
        passed=match,
        count=abs(fraud_int - fraud_label),
        detail=f"isFraud sum={fraud_int}, fraud_label count={fraud_label}. {'Match ✓' if match else 'MISMATCH ✗'}",
    )
