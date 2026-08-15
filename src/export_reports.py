"""
export_reports.py
=================
Exports cleaned data, query results, and KPI summaries to:
  - CSV files (outputs/)
  - SQLite database (outputs/fintech_analytics.db)
  - Excel workbook (outputs/fintech_analytics.xlsx)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------


def export_csvs(
    df_cleaned: pd.DataFrame,
    df_flagged: pd.DataFrame,
    quality_report: dict[str, Any],
    kpi_summary: dict[str, Any],
    query_results: dict[str, pd.DataFrame],
) -> None:
    """Write all CSV deliverables."""
    log.info("Exporting CSVs to: %s", OUTPUTS_DIR)

    # Cleaned data (full dataset)
    _write_csv(df_cleaned, "cleaned_transactions.csv")

    # Flagged / rejected records
    _write_csv(df_flagged, "flagged_transactions.csv")

    # Data quality report
    quality_df = pd.DataFrame(
        [{"metric": k, "value": v} for k, v in quality_report.items()]
    )
    _write_csv(quality_df, "data_quality_report.csv")

    # KPI summary
    kpi_df = pd.DataFrame(
        [{"kpi": k, "value": v} for k, v in kpi_summary.items()]
    )
    _write_csv(kpi_df, "kpi_summary.csv")

    # Individual query results
    for name, df in query_results.items():
        if not df.empty:
            _write_csv(df, f"{name}.csv")

    log.info("CSV export complete.")


def _write_csv(df: pd.DataFrame, filename: str) -> None:
    path = OUTPUTS_DIR / filename
    df.to_csv(path, index=False)
    log.info("  Wrote: %s (%d rows)", path.name, len(df))


# ---------------------------------------------------------------------------
# Excel workbook
# ---------------------------------------------------------------------------


def export_excel(
    df_cleaned: pd.DataFrame,
    df_flagged: pd.DataFrame,
    quality_report: dict[str, Any],
    kpi_summary: dict[str, Any],
    query_results: dict[str, pd.DataFrame],
    output_path: Path | str | None = None,
) -> Path:
    """Write the full formatted Excel workbook."""
    path = Path(output_path) if output_path else OUTPUTS_DIR / "fintech_analytics.xlsx"
    log.info("Building Excel workbook: %s", path)

    with pd.ExcelWriter(str(path), engine="xlsxwriter") as writer:
        wb = writer.book

        # --- Shared formats ---
        fmt_header = wb.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": "#1a3a5c",
            "border": 1, "align": "center", "valign": "vcenter", "font_size": 11,
        })
        fmt_number = wb.add_format({"num_format": "#,##0.00", "border": 1})
        fmt_integer = wb.add_format({"num_format": "#,##0", "border": 1})
        fmt_pct = wb.add_format({"num_format": "0.00%", "border": 1})
        fmt_text = wb.add_format({"border": 1})
        fmt_title = wb.add_format({
            "bold": True, "font_size": 18, "font_color": "#1a3a5c",
        })
        fmt_subtitle = wb.add_format({
            "italic": True, "font_size": 11, "font_color": "#555555",
        })
        fmt_kpi_label = wb.add_format({
            "bold": True, "bg_color": "#EEF2F7", "border": 1, "font_size": 11,
        })
        fmt_kpi_value = wb.add_format({
            "bold": True, "bg_color": "#DDEEFF", "border": 1,
            "num_format": "#,##0.00", "font_size": 12, "align": "right",
        })
        fmt_warn = wb.add_format({
            "bg_color": "#FFF3CD", "border": 1, "font_color": "#856404",
        })

        # ------------------------------------------------------------------
        # Sheet 1: README
        # ------------------------------------------------------------------
        ws_readme = wb.add_worksheet("README")
        ws_readme.set_column("A:A", 80)
        ws_readme.write("A1", "Fintech Transaction & Revenue Analytics", fmt_title)
        ws_readme.write("A2", "Data source: PaySim (simulated mobile-money transactions) — Kaggle", fmt_subtitle)
        readme_lines = [
            ("A4",  "PROJECT OVERVIEW"),
            ("A5",  "This workbook presents analytics derived from the PaySim synthetic mobile-money dataset."),
            ("A6",  "It covers transaction volume/value, fraud analysis, data-quality checks, and modeled revenue."),
            ("A7",  ""),
            ("A8",  "DATA SOURCE"),
            ("A9",  "Dataset: PaySim — https://www.kaggle.com/datasets/ealaxi/paysim1"),
            ("A10", "The dataset simulates mobile-money transactions based on real patterns from M-Pesa (Africa)."),
            ("A11", "It does NOT contain merchant names, payment statuses, refunds, or actual processing fees."),
            ("A12", ""),
            ("A13", "SYNTHETIC DATA DISCLOSURE"),
            ("A14", "Columns labelled _SYNTHETIC are generated for demonstration purposes only."),
            ("A15", "Columns labelled _MODELED represent estimated values using explicit fee assumptions."),
            ("A16", ""),
            ("A17", "SHEETS GUIDE"),
            ("A18", "  Raw_Sample       — first 1000 rows of the original dataset"),
            ("A19", "  Cleaned_Sample   — first 1000 rows of the cleaned dataset with flag columns"),
            ("A20", "  KPI_Summary      — key business metrics"),
            ("A21", "  Monthly_Trends   — month-over-month transaction trends"),
            ("A22", "  Transaction_Analysis — breakdown by transaction type"),
            ("A23", "  Fraud_Analysis   — fraud patterns and distributions"),
            ("A24", "  Data_Quality     — exception counts per cleaning rule"),
            ("A25", "  Dashboard        — KPI cards and charts"),
        ]
        for cell, val in readme_lines:
            ws_readme.write(cell, val)

        # ------------------------------------------------------------------
        # Sheet 2: Raw_Sample
        # ------------------------------------------------------------------
        raw_cols = ["step", "type", "amount", "nameOrig", "oldbalanceOrg",
                    "newbalanceOrig", "nameDest", "oldbalanceDest",
                    "newbalanceDest", "isFraud", "isFlaggedFraud"]
        available_raw = [c for c in raw_cols if c in df_cleaned.columns]
        raw_sample = df_cleaned[available_raw].head(1000)
        raw_sample.to_excel(writer, sheet_name="Raw_Sample", index=False, startrow=1)
        ws_raw = writer.sheets["Raw_Sample"]
        ws_raw.write("A1", "Raw Data Sample (first 1,000 rows — source columns only)", fmt_title)
        _auto_col_width(ws_raw, raw_sample)

        # ------------------------------------------------------------------
        # Sheet 3: Cleaned_Sample
        # ------------------------------------------------------------------
        cleaned_sample = df_cleaned.head(1000)
        cleaned_sample.to_excel(writer, sheet_name="Cleaned_Sample", index=False, startrow=1)
        ws_clean = writer.sheets["Cleaned_Sample"]
        ws_clean.write("A1", "Cleaned Data Sample (first 1,000 rows — all columns including flags)", fmt_title)
        _auto_col_width(ws_clean, cleaned_sample)

        # ------------------------------------------------------------------
        # Sheet 4: KPI_Summary
        # ------------------------------------------------------------------
        ws_kpi = wb.add_worksheet("KPI_Summary")
        ws_kpi.set_column("A:A", 45)
        ws_kpi.set_column("B:B", 25)
        ws_kpi.write("A1", "Key Performance Indicators", fmt_title)

        kpi_rows = [
            ("Total Transactions", kpi_summary.get("total_transactions", "N/A"), "integer"),
            ("Total Transaction Amount", kpi_summary.get("total_amount", 0), "number"),
            ("Average Transaction Amount", kpi_summary.get("avg_amount", 0), "number"),
            ("Median Transaction Amount", kpi_summary.get("median_amount", 0), "number"),
            ("Fraud Count", kpi_summary.get("fraud_count", 0), "integer"),
            ("Fraud Rate (%)", kpi_summary.get("fraud_rate_pct", 0), "number"),
            ("Data Quality Exceptions", kpi_summary.get("data_quality_exceptions", 0), "integer"),
            ("Data Quality Exception Rate (%)", kpi_summary.get("data_quality_rate_pct", 0), "number"),
            ("ESTIMATED Revenue [MODELED]", kpi_summary.get("estimated_revenue_MODELED", 0), "number"),
            ("Fee Rate Assumption (%)", kpi_summary.get("fee_rate_assumption_pct", 0), "number"),
        ]

        if "refund_count_SYNTHETIC" in kpi_summary:
            kpi_rows += [
                ("Refund Count [SYNTHETIC]", kpi_summary.get("refund_count_SYNTHETIC", 0), "integer"),
                ("Total Refund Amount [SYNTHETIC]", kpi_summary.get("refund_total_SYNTHETIC", 0), "number"),
                ("Refund Rate (%) [SYNTHETIC]", kpi_summary.get("refund_rate_pct_SYNTHETIC", 0), "number"),
            ]

        for i, (label, value, fmt_type) in enumerate(kpi_rows):
            row = i + 2
            ws_kpi.write(row, 0, label, fmt_kpi_label)
            val_fmt = fmt_integer if fmt_type == "integer" else fmt_kpi_value
            ws_kpi.write(row, 1, value, val_fmt)

        # Note about modeled values
        note_row = len(kpi_rows) + 4
        ws_kpi.write(note_row, 0, kpi_summary.get("estimated_revenue_note", ""), fmt_warn)

        # ------------------------------------------------------------------
        # Sheet 5: Monthly_Trends
        # ------------------------------------------------------------------
        mt = query_results.get("monthly_trends", pd.DataFrame())
        if not mt.empty:
            mt.to_excel(writer, sheet_name="Monthly_Trends", index=False, startrow=1)
            ws_mt = writer.sheets["Monthly_Trends"]
            ws_mt.write("A1", "Monthly Transaction Trends", fmt_title)
            _auto_col_width(ws_mt, mt)

        # ------------------------------------------------------------------
        # Sheet 6: Transaction_Analysis
        # ------------------------------------------------------------------
        ta = query_results.get("type_analysis", pd.DataFrame())
        if not ta.empty:
            ta.to_excel(writer, sheet_name="Transaction_Analysis", index=False, startrow=1)
            ws_ta = writer.sheets["Transaction_Analysis"]
            ws_ta.write("A1", "Transaction Type Analysis", fmt_title)
            _auto_col_width(ws_ta, ta)

        # ------------------------------------------------------------------
        # Sheet 7: Fraud_Analysis
        # ------------------------------------------------------------------
        fa = query_results.get("fraud_analysis", pd.DataFrame())
        if not fa.empty:
            fa.to_excel(writer, sheet_name="Fraud_Analysis", index=False, startrow=1)
            ws_fa = writer.sheets["Fraud_Analysis"]
            ws_fa.write("A1", "Fraud Analysis (source isFraud label)", fmt_title)
            _auto_col_width(ws_fa, fa)

        # ------------------------------------------------------------------
        # Sheet 8: Data_Quality
        # ------------------------------------------------------------------
        dq = query_results.get("data_quality", pd.DataFrame())
        if not dq.empty:
            dq.to_excel(writer, sheet_name="Data_Quality", index=False, startrow=1)
            ws_dq = writer.sheets["Data_Quality"]
            ws_dq.write("A1", "Data Quality Exception Summary", fmt_title)
            _auto_col_width(ws_dq, dq)

        # ------------------------------------------------------------------
        # Sheet 9: Dashboard
        # ------------------------------------------------------------------
        ws_dash = wb.add_worksheet("Dashboard")
        ws_dash.set_column("A:A", 30)
        ws_dash.set_column("B:B", 20)
        ws_dash.set_column("C:C", 20)
        ws_dash.set_column("D:D", 20)

        ws_dash.write("A1", "📊 Fintech Transaction Analytics Dashboard", fmt_title)
        ws_dash.write("A2", "Source: PaySim dataset | All MODELED/SYNTHETIC values are explicitly labelled", fmt_subtitle)

        # KPI Cards row
        ws_dash.write("A4", "KPI CARDS", wb.add_format({"bold": True, "font_size": 13}))
        kpi_card_data = [
            ("Total Transactions", kpi_summary.get("total_transactions", 0)),
            ("Total Amount",       kpi_summary.get("total_amount", 0)),
            ("Fraud Rate %",       kpi_summary.get("fraud_rate_pct", 0)),
            ("DQ Exception Rate %",kpi_summary.get("data_quality_rate_pct", 0)),
        ]
        for i, (label, val) in enumerate(kpi_card_data):
            col = i
            ws_dash.write(4, col, label, fmt_kpi_label)
            ws_dash.write(5, col, val, fmt_kpi_value)

        # --- Chart 1: Monthly Transaction Volume ---
        if not mt.empty and "transaction_count" in mt.columns:
            chart1 = wb.add_chart({"type": "column"})
            mt.to_excel(writer, sheet_name="Dashboard", index=False, startrow=30, startcol=0)
            n_months = len(mt)
            chart1.add_series({
                "name": "Transaction Count",
                "categories": ["Dashboard", 31, 0, 30 + n_months, 0],
                "values":     ["Dashboard", 31, 1, 30 + n_months, 1],
                "fill": {"color": "#1a3a5c"},
            })
            chart1.set_title({"name": "Monthly Transaction Volume"})
            chart1.set_x_axis({"name": "Month"})
            chart1.set_y_axis({"name": "Transaction Count"})
            chart1.set_size({"width": 480, "height": 280})
            ws_dash.insert_chart("A8", chart1)

        # --- Chart 2: Transaction Type Pie ---
        if not ta.empty and "transaction_count" in ta.columns:
            chart2 = wb.add_chart({"type": "pie"})
            ta.to_excel(writer, sheet_name="Dashboard", index=False, startrow=50, startcol=0)
            n_types = len(ta)
            chart2.add_series({
                "name": "Transaction Types",
                "categories": ["Dashboard", 51, 0, 50 + n_types, 0],
                "values":     ["Dashboard", 51, 1, 50 + n_types, 1],
            })
            chart2.set_title({"name": "Transaction Volume by Type"})
            chart2.set_size({"width": 400, "height": 280})
            ws_dash.insert_chart("D8", chart2)

        # Business findings section
        row = 26
        ws_dash.write(row, 0, "KEY BUSINESS FINDINGS", wb.add_format({"bold": True, "font_size": 13}))
        findings = _generate_findings(kpi_summary, query_results)
        for i, finding in enumerate(findings):
            ws_dash.write(row + 1 + i, 0, f"• {finding}", fmt_text)

    log.info("Excel workbook saved: %s", path)
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auto_col_width(ws: Any, df: pd.DataFrame, min_width: int = 12, max_width: int = 40) -> None:
    for i, col in enumerate(df.columns):
        max_len = max(len(str(col)), df[col].astype(str).str.len().max() if len(df) else 0)
        ws.set_column(i, i, min(max(max_len + 2, min_width), max_width))


def _generate_findings(kpi: dict, results: dict) -> list[str]:
    findings = []
    total = kpi.get("total_transactions", 0)
    fraud_rate = kpi.get("fraud_rate_pct", 0)
    dq_rate = kpi.get("data_quality_rate_pct", 0)

    findings.append(f"Dataset contains {total:,} transactions in total.")

    if fraud_rate is not None:
        if fraud_rate < 0.5:
            findings.append(f"Fraud rate is very low at {fraud_rate:.2f}%, consistent with typical mobile-money fraud rates.")
        else:
            findings.append(f"Fraud rate of {fraud_rate:.2f}% warrants immediate investigation and enhanced monitoring.")

    ta = results.get("type_analysis", pd.DataFrame())
    if not ta.empty and "type" in ta.columns and "fraud_rate_pct" in ta.columns:
        high_fraud_type = ta.loc[ta["fraud_rate_pct"].idxmax()]
        findings.append(
            f"Highest fraud rate by type: {high_fraud_type['type']} ({high_fraud_type['fraud_rate_pct']:.2f}%)."
        )

    findings.append(
        f"Data-quality exception rate: {dq_rate:.2f}%  — "
        "primarily driven by balance-field mismatches (known PaySim characteristic)."
    )

    mt = results.get("monthly_trends", pd.DataFrame())
    if not mt.empty and "transaction_count" in mt.columns:
        peak_month = mt.loc[mt["transaction_count"].idxmax()]
        findings.append(
            f"Peak transaction volume in simulation month {int(peak_month.iloc[0])}: "
            f"{int(peak_month['transaction_count']):,} transactions."
        )

    est_rev = kpi.get("estimated_revenue_MODELED")
    fee_rate = kpi.get("fee_rate_assumption_pct", 0.25)
    if est_rev is not None:
        findings.append(
            f"MODELED estimated revenue at {fee_rate}% fee rate: {est_rev:,.2f} "
            "(not actual revenue — see README and KPI_Summary notes)."
        )

    findings.append("RECOMMENDATION: Implement real-time ML scoring for TRANSFER and CASH_OUT transactions to reduce fraud losses.")
    findings.append("RECOMMENDATION: Investigate balance-field mismatches — they represent potential data-pipeline integrity issues.")

    return findings
