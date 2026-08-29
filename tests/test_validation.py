"""
test_validation.py
==================
Tests for the post-cleaning validation layer (src/validate_data.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.clean_data import clean_paysim
from src.validate_data import validate_cleaned, ValidationReport
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
def val_report(cleaned_df):
    return validate_cleaned(cleaned_df)


# ---------------------------------------------------------------------------
# Report structure tests
# ---------------------------------------------------------------------------


class TestReportStructure:
    def test_returns_validation_report(self, val_report):
        assert isinstance(val_report, ValidationReport)

    def test_checks_list_non_empty(self, val_report):
        assert len(val_report.checks) > 0

    def test_all_passed_is_bool(self, val_report):
        assert isinstance(val_report.all_passed, bool)

    def test_to_dataframe_has_required_cols(self, val_report):
        df = val_report.to_dataframe()
        for col in ["check", "passed", "count", "detail"]:
            assert col in df.columns

    def test_summary_is_string(self, val_report):
        assert isinstance(val_report.summary(), str)


# ---------------------------------------------------------------------------
# Individual check tests
# ---------------------------------------------------------------------------


class TestIndividualChecks:
    def _get_check(self, report: ValidationReport, name: str):
        for chk in report.checks:
            if chk.name == name:
                return chk
        return None

    def test_source_columns_preserved(self, val_report):
        chk = self._get_check(val_report, "source_columns_preserved")
        assert chk is not None
        assert chk.passed

    def test_required_columns_exist(self, val_report):
        chk = self._get_check(val_report, "required_columns_exist")
        assert chk is not None
        assert chk.passed

    def test_fraud_label_binary(self, val_report):
        chk = self._get_check(val_report, "fraud_label_binary")
        assert chk is not None
        assert chk.passed

    def test_derived_columns_present(self, val_report):
        chk = self._get_check(val_report, "derived_columns_present")
        assert chk is not None
        assert chk.passed

    def test_no_infinite_values(self, val_report):
        chk = self._get_check(val_report, "no_infinite_values")
        assert chk is not None
        assert chk.passed

    def test_metric_reconciliation(self, val_report):
        chk = self._get_check(val_report, "metric_reconciliation")
        assert chk is not None
        assert chk.passed


# ---------------------------------------------------------------------------
# Failed checks on deliberately broken data
# ---------------------------------------------------------------------------


class TestFailureDetection:
    def test_detects_wrong_fraud_values(self):
        """ValidationReport should detect non-binary isFraud values."""
        raw = generate()
        cleaned, _, _ = clean_paysim(raw)
        broken = cleaned.copy()
        broken.loc[0, "isFraud"] = 2   # Invalid value
        report = validate_cleaned(broken)
        chk = next((c for c in report.checks if c.name == "fraud_label_binary"), None)
        assert chk is not None
        # The check inspects isFraud values; 2 is not in {0, 1}
        assert not chk.passed

    def test_detects_missing_required_column(self):
        """Removing 'any_quality_flag' should fail the required-columns check."""
        raw = generate()
        cleaned, _, _ = clean_paysim(raw)
        broken = cleaned.drop(columns=["any_quality_flag"])
        report = validate_cleaned(broken)
        chk = next((c for c in report.checks if c.name == "required_columns_exist"), None)
        assert chk is not None
        assert not chk.passed
