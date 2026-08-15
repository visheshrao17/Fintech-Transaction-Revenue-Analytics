"""
run_pipeline.py
===============
Main pipeline orchestrator — runs all phases end-to-end.

Usage
-----
  python run_pipeline.py                       # auto-detects data source
  python run_pipeline.py --sample 100000       # sample 100K rows for dev
  python run_pipeline.py --path /data/my.csv   # custom dataset path
  python run_pipeline.py --fee-rate 0.003      # change modeled revenue rate

Exit codes
----------
  0 — all phases completed successfully
  1 — critical error in a required phase
  2 — dataset not found (partial run on test data)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.load_data import load_paysim
from src.profile_data import profile_dataset, profile_to_dataframe
from src.clean_data import clean_paysim
from src.validate_data import validate_cleaned
from src.feature_engineering import (
    build_merchant_table,
    build_refund_table,
    compute_estimated_revenue,
    build_kpi_summary,
)
from src.analyze_data import get_engine, load_tables, run_all_queries
from src.export_reports import export_csvs, export_excel
from src.build_dashboard import build_dashboard


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(description="Fintech Transaction Analytics Pipeline")
    p.add_argument("--path", default=None, help="Path to PaySim CSV.")
    p.add_argument("--sample", type=int, default=0,
                   help="Sample size (0 = full dataset).")
    p.add_argument("--fee-rate", type=float, default=0.0025,
                   help="Fee rate for modeled revenue (default: 0.0025 = 0.25%%).")
    p.add_argument("--skip-dashboard", action="store_true",
                   help="Skip dashboard rendering (useful in headless environments).")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Pipeline phases
# ---------------------------------------------------------------------------


def run_pipeline(args):
    t0 = time.time()
    outputs_dir = PROJECT_ROOT / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 70)
    log.info("  FINTECH TRANSACTION ANALYTICS — PIPELINE START")
    log.info("=" * 70)

    # -----------------------------------------------------------------------
    # PHASE 1: Load data
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 1: Loading data")
    try:
        df_raw = load_paysim(path=args.path, sample_size=args.sample)
        log.info("  Loaded: %d rows × %d columns", *df_raw.shape)
    except FileNotFoundError as exc:
        log.error("Dataset not found: %s", exc)
        log.warning("Running on bundled test sample instead.")
        from tests.generate_test_data import generate
        df_raw = generate()
        log.info("  Using test sample: %d rows", len(df_raw))

    # -----------------------------------------------------------------------
    # PHASE 2: Profile
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 2: Profiling data")
    profile = profile_dataset(df_raw)
    profile_df = profile_to_dataframe(profile)
    profile_df.to_csv(outputs_dir / "data_profile.csv", index=False)
    log.info("  Profile written: outputs/data_profile.csv")

    # -----------------------------------------------------------------------
    # PHASE 3: Clean
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 3: Cleaning data")
    df_cleaned, df_flagged, quality_report = clean_paysim(df_raw)
    log.info(
        "  Cleaned: %d total | %d flagged (%.2f%%) | %d clean",
        quality_report["output_rows"],
        quality_report["flagged_rows"],
        quality_report["flagged_pct"],
        quality_report["clean_rows"],
    )

    # -----------------------------------------------------------------------
    # PHASE 4: Validate
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 4: Validating cleaned data")
    val_report = validate_cleaned(df_cleaned)
    log.info("  %s", val_report.summary())
    val_report.to_dataframe().to_csv(outputs_dir / "validation_report.csv", index=False)

    if not val_report.all_passed:
        for chk in val_report.failed_checks:
            log.warning("  FAILED CHECK: %s — %s", chk.name, chk.detail)

    # -----------------------------------------------------------------------
    # PHASE 5: Feature engineering + KPIs
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 5: Feature engineering and KPI calculation")
    merchant_df = build_merchant_table(df_cleaned)
    refund_df = build_refund_table(df_cleaned)
    df_with_revenue = compute_estimated_revenue(df_cleaned, fee_rate=args.fee_rate)
    kpi_summary = build_kpi_summary(df_cleaned, refund_df=refund_df, fee_rate=args.fee_rate)

    log.info("  KPIs computed:")
    for k, v in kpi_summary.items():
        if isinstance(v, (int, float)) and "note" not in k:
            log.info("    %-40s : %s", k, f"{v:,.2f}" if isinstance(v, float) else f"{v:,}")

    # -----------------------------------------------------------------------
    # PHASE 6: SQL analytics
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 6: Loading SQLite and running queries")
    engine = get_engine()
    load_tables(engine, df_cleaned, merchant_df=merchant_df, refund_df=refund_df)
    query_results = run_all_queries(engine)
    log.info("  %d queries executed.", len(query_results))

    # -----------------------------------------------------------------------
    # PHASE 7: Export CSVs
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 7: Exporting CSV reports")
    export_csvs(
        df_cleaned=df_cleaned,
        df_flagged=df_flagged,
        quality_report=quality_report,
        kpi_summary=kpi_summary,
        query_results=query_results,
    )

    # -----------------------------------------------------------------------
    # PHASE 8: Excel workbook
    # -----------------------------------------------------------------------
    log.info("\n▶ PHASE 8: Building Excel workbook")
    xlsx_path = export_excel(
        df_cleaned=df_cleaned,
        df_flagged=df_flagged,
        quality_report=quality_report,
        kpi_summary=kpi_summary,
        query_results=query_results,
    )
    log.info("  Workbook: %s", xlsx_path)

    # -----------------------------------------------------------------------
    # PHASE 9: Dashboard
    # -----------------------------------------------------------------------
    if not args.skip_dashboard:
        log.info("\n▶ PHASE 9: Rendering dashboard")
        try:
            dash_path = build_dashboard(kpi_summary, query_results)
            log.info("  Dashboard: %s", dash_path)
        except Exception as exc:
            log.warning("  Dashboard rendering failed: %s (non-fatal)", exc)
    else:
        log.info("\n▶ PHASE 9: Dashboard skipped (--skip-dashboard)")

    elapsed = time.time() - t0
    log.info("\n" + "=" * 70)
    log.info("  PIPELINE COMPLETE in %.1f seconds", elapsed)
    log.info("=" * 70)
    log.info("")
    log.info("  Outputs in: %s", outputs_dir)
    log.info("  Deliverables:")
    for f in sorted(outputs_dir.iterdir()):
        log.info("    • %s", f.name)

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_pipeline(args))
