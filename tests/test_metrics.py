"""
test_metrics.py
===============
Tests for KPI calculations and metric reconciliation (src/feature_engineering.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.clean_data import clean_paysim
from src.feature_engineering import build_kpi_summary, build_refund_table, DEFAULT_FEE_RATE
from tests.generate_test_data import generate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cleaned_df():
    raw = generate()
    cleaned, _, _ = clean_paysim(raw)
    return cleaned


@pytest.fixture(scope="module")
def kpis(cleaned_df):
    return build_kpi_summary(cleaned_df)


# ---------------------------------------------------------------------------
# KPI structure
# ---------------------------------------------------------------------------


class TestKPIStructure:
    def test_required_kpi_keys(self, kpis):
        required = [
            "total_transactions", "total_amount", "avg_amount", "median_amount",
            "fraud_count", "fraud_rate_pct", "data_quality_exceptions",
            "data_quality_rate_pct", "estimated_revenue_MODELED",
            "fee_rate_assumption_pct", "estimated_revenue_note",
        ]
        for key in required:
            assert key in kpis, f"KPI key '{key}' missing"

    def test_all_values_not_none(self, kpis):
        for k, v in kpis.items():
            assert v is not None, f"KPI '{k}' is None"


# ---------------------------------------------------------------------------
# KPI value correctness
# ---------------------------------------------------------------------------


class TestKPIValues:
    def test_total_transactions_matches_row_count(self, cleaned_df, kpis):
        assert kpis["total_transactions"] == len(cleaned_df)

    def test_total_amount_non_negative(self, kpis):
        # Even with injected negative rows they should net to near-zero or positive
        # given 9995 genuine rows
        assert kpis["total_amount"] > 0

    def test_avg_amount_between_min_and_max(self, cleaned_df, kpis):
        assert cleaned_df["amount"].min() <= kpis["avg_amount"] <= cleaned_df["amount"].max()

    def test_median_amount_is_numeric(self, kpis):
        assert isinstance(kpis["median_amount"], float)

    def test_fraud_count_non_negative(self, kpis):
        assert kpis["fraud_count"] >= 0

    def test_fraud_rate_in_range(self, kpis):
        assert 0.0 <= kpis["fraud_rate_pct"] <= 100.0

    def test_dq_exception_count_matches_any_flag(self, cleaned_df, kpis):
        expected = int(cleaned_df["any_quality_flag"].sum())
        assert kpis["data_quality_exceptions"] == expected

    def test_dq_rate_formula(self, cleaned_df, kpis):
        expected_rate = round(
            int(cleaned_df["any_quality_flag"].sum()) / len(cleaned_df) * 100, 4
        )
        assert abs(kpis["data_quality_rate_pct"] - expected_rate) < 0.001

    def test_estimated_revenue_is_modeled_not_zero(self, kpis):
        """Revenue should be > 0 since there are valid (non-flagged) transactions."""
        assert kpis["estimated_revenue_MODELED"] > 0

    def test_estimated_revenue_note_contains_modeled(self, kpis):
        assert "MODELED" in kpis["estimated_revenue_note"]


# ---------------------------------------------------------------------------
# Denominator correctness
# ---------------------------------------------------------------------------


class TestDenominators:
    def test_fraud_rate_denominator(self, cleaned_df, kpis):
        """Fraud rate denominator is total transactions, not just legitimate ones."""
        expected = round(
            kpis["fraud_count"] / len(cleaned_df) * 100, 4
        )
        assert abs(kpis["fraud_rate_pct"] - expected) < 0.001

    def test_dq_rate_denominator(self, cleaned_df, kpis):
        expected = round(
            kpis["data_quality_exceptions"] / len(cleaned_df) * 100, 4
        )
        assert abs(kpis["data_quality_rate_pct"] - expected) < 0.001


# ---------------------------------------------------------------------------
# Fee rate sensitivity
# ---------------------------------------------------------------------------


class TestFeeRateSensitivity:
    def test_higher_fee_rate_yields_more_revenue(self, cleaned_df):
        kpi_low = build_kpi_summary(cleaned_df, fee_rate=0.001)
        kpi_high = build_kpi_summary(cleaned_df, fee_rate=0.005)
        assert kpi_high["estimated_revenue_MODELED"] > kpi_low["estimated_revenue_MODELED"]

    def test_zero_fee_rate_yields_zero_revenue(self, cleaned_df):
        kpi = build_kpi_summary(cleaned_df, fee_rate=0.0)
        assert kpi["estimated_revenue_MODELED"] == 0.0


# ---------------------------------------------------------------------------
# Refund KPIs
# ---------------------------------------------------------------------------


class TestRefundKPIs:
    def test_refund_kpis_present_when_table_provided(self, cleaned_df):
        refund_df = build_refund_table(cleaned_df)
        kpis = build_kpi_summary(cleaned_df, refund_df=refund_df)
        assert "refund_count_SYNTHETIC" in kpis
        assert "refund_total_SYNTHETIC" in kpis
        assert "refund_rate_pct_SYNTHETIC" in kpis

    def test_refund_note_contains_synthetic(self, cleaned_df):
        refund_df = build_refund_table(cleaned_df)
        kpis = build_kpi_summary(cleaned_df, refund_df=refund_df)
        assert "SYNTHETIC" in kpis.get("refund_note", "")

    def test_refund_count_positive(self, cleaned_df):
        refund_df = build_refund_table(cleaned_df)
        kpis = build_kpi_summary(cleaned_df, refund_df=refund_df)
        assert kpis["refund_count_SYNTHETIC"] > 0


# ---------------------------------------------------------------------------
# Export correctness
# ---------------------------------------------------------------------------


class TestExportedFiles:
    def test_csv_has_expected_columns(self, cleaned_df, tmp_path):
        """Verify that when written to CSV and read back, required columns are intact."""
        csv_path = tmp_path / "cleaned.csv"
        cleaned_df.to_csv(csv_path, index=False)
        reloaded = pd.read_csv(csv_path)
        for col in ["step", "type", "amount", "nameOrig", "nameDest",
                    "isFraud", "any_quality_flag", "fraud_label"]:
            assert col in reloaded.columns, f"Column '{col}' missing from exported CSV"

    def test_kpi_csv_has_kpi_and_value_columns(self, kpis, tmp_path):
        kpi_df = pd.DataFrame([{"kpi": k, "value": v} for k, v in kpis.items()])
        csv_path = tmp_path / "kpi_summary.csv"
        kpi_df.to_csv(csv_path, index=False)
        reloaded = pd.read_csv(csv_path)
        assert "kpi" in reloaded.columns
        assert "value" in reloaded.columns
