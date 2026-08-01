"""
analyze_data.py
===============
SQL-powered analytics layer using SQLite via SQLAlchemy.

Responsibilities:
  - Create SQLite database schema (schema.sql)
  - Load cleaned data + supplementary tables into the DB
  - Execute analytical SQL queries
  - Return results as DataFrames for reporting
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "outputs" / "fintech_analytics.db"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_engine(db_path: Path | str | None = None) -> Any:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    log.info("SQLite engine: %s", path)
    return engine


def load_tables(
    engine: Any,
    df_cleaned: pd.DataFrame,
    merchant_df: pd.DataFrame | None = None,
    refund_df: pd.DataFrame | None = None,
) -> None:
    """Write DataFrames to SQLite tables (replace if exists)."""
    log.info("Loading 'transactions' table (%d rows)…", len(df_cleaned))
    df_cleaned.to_sql("transactions", engine, if_exists="replace", index=False)

    if merchant_df is not None:
        log.info("Loading 'merchants' table (%d rows)…", len(merchant_df))
        merchant_df.to_sql("merchants", engine, if_exists="replace", index=False)

    if refund_df is not None:
        log.info("Loading 'refunds' table (%d rows)…", len(refund_df))
        refund_df.to_sql("refunds", engine, if_exists="replace", index=False)

    log.info("All tables loaded.")


# ---------------------------------------------------------------------------
# Analytical queries
# ---------------------------------------------------------------------------


def run_query(engine: Any, sql: str, label: str = "") -> pd.DataFrame:
    """Execute a SQL string and return a DataFrame."""
    log.info("Running query: %s", label or sql[:80])
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn)


def monthly_transaction_trends(engine: Any) -> pd.DataFrame:
    """Monthly volume, value, and fraud counts."""
    sql = """
    SELECT
        day_of_sim / 30 + 1                   AS sim_month,
        COUNT(*)                               AS transaction_count,
        ROUND(SUM(amount), 2)                  AS total_amount,
        ROUND(AVG(amount), 2)                  AS avg_amount,
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)  AS fraud_count,
        ROUND(
            SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
            4
        )                                      AS fraud_rate_pct
    FROM transactions
    GROUP BY sim_month
    ORDER BY sim_month
    """
    return run_query(engine, sql, "monthly_transaction_trends")


def transaction_type_analysis(engine: Any) -> pd.DataFrame:
    """Per-type volume, value, and fraud breakdown."""
    sql = """
    SELECT
        type,
        COUNT(*)                                           AS transaction_count,
        ROUND(SUM(amount), 2)                              AS total_amount,
        ROUND(AVG(amount), 2)                              AS avg_amount,
        MAX(amount)                                        AS max_amount,
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)      AS fraud_count,
        ROUND(
            SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
            4
        )                                                  AS fraud_rate_pct,
        SUM(CASE WHEN any_quality_flag = 1 THEN 1 ELSE 0 END) AS flagged_count
    FROM transactions
    GROUP BY type
    ORDER BY total_amount DESC
    """
    return run_query(engine, sql, "transaction_type_analysis")


def fraud_analysis(engine: Any) -> pd.DataFrame:
    """Fraud patterns by type, amount band, and hour."""
    sql = """
    SELECT
        type,
        amount_band,
        hour_of_day,
        COUNT(*)                            AS total_transactions,
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)   AS fraud_count,
        ROUND(SUM(CASE WHEN isFraud = 1 THEN amount ELSE 0 END), 2) AS fraud_amount,
        ROUND(
            SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
            4
        )                                   AS fraud_rate_pct
    FROM transactions
    GROUP BY type, amount_band, hour_of_day
    ORDER BY fraud_count DESC
    LIMIT 200
    """
    return run_query(engine, sql, "fraud_analysis")


def amount_distribution(engine: Any) -> pd.DataFrame:
    """Transaction count and total by amount band."""
    sql = """
    SELECT
        amount_band,
        COUNT(*)                    AS transaction_count,
        ROUND(SUM(amount), 2)       AS total_amount,
        ROUND(AVG(amount), 2)       AS avg_amount,
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) AS fraud_count
    FROM transactions
    WHERE amount_band IS NOT NULL
    GROUP BY amount_band
    ORDER BY
        CASE amount_band
            WHEN '<1K'        THEN 1
            WHEN '1K-10K'     THEN 2
            WHEN '10K-100K'   THEN 3
            WHEN '100K-500K'  THEN 4
            WHEN '>500K'      THEN 5
        END
    """
    return run_query(engine, sql, "amount_distribution")


def data_quality_summary(engine: Any) -> pd.DataFrame:
    """Data-quality exception counts by flag type."""
    flag_cols = [
        "flag_duplicate", "flag_missing_critical", "flag_negative_amount",
        "flag_zero_amount", "flag_invalid_step", "flag_invalid_type",
        "flag_orig_balance_mismatch", "flag_dest_balance_mismatch",
        "flag_negative_balance", "any_quality_flag",
    ]
    rows = []
    with engine.connect() as conn:
        for col in flag_cols:
            try:
                res = conn.execute(text(
                    f"SELECT SUM(CASE WHEN {col}=1 THEN 1 ELSE 0 END) AS cnt, "
                    f"COUNT(*) AS total FROM transactions"
                )).fetchone()
                cnt, total = res
                rows.append({
                    "flag": col,
                    "count": int(cnt or 0),
                    "total": int(total or 0),
                    "pct": round(int(cnt or 0) / int(total or 1) * 100, 4),
                })
            except Exception as exc:
                log.warning("Skipping flag column '%s': %s", col, exc)
    return pd.DataFrame(rows)


def hourly_fraud_pattern(engine: Any) -> pd.DataFrame:
    """Fraud count by hour of day."""
    sql = """
    SELECT
        hour_of_day,
        COUNT(*) AS total,
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) AS fraud_count,
        ROUND(SUM(CASE WHEN isFraud=1 THEN 1 ELSE 0 END)*100.0/COUNT(*), 4) AS fraud_rate_pct
    FROM transactions
    GROUP BY hour_of_day
    ORDER BY hour_of_day
    """
    return run_query(engine, sql, "hourly_fraud_pattern")


def large_transaction_analysis(engine: Any) -> pd.DataFrame:
    """Analysis of transactions above the large-transaction threshold."""
    sql = """
    SELECT
        type,
        COUNT(*) AS large_tx_count,
        ROUND(SUM(amount), 2) AS large_tx_total,
        ROUND(AVG(amount), 2) AS large_tx_avg,
        SUM(CASE WHEN isFraud=1 THEN 1 ELSE 0 END) AS fraud_count
    FROM transactions
    WHERE is_large_transaction = 1
    GROUP BY type
    ORDER BY large_tx_total DESC
    """
    return run_query(engine, sql, "large_transaction_analysis")


def balance_reconciliation(engine: Any) -> pd.DataFrame:
    """Balance mismatch reconciliation by transaction type."""
    sql = """
    SELECT
        type,
        COUNT(*) AS total,
        SUM(CASE WHEN flag_orig_balance_mismatch=1 THEN 1 ELSE 0 END) AS orig_mismatch,
        SUM(CASE WHEN flag_dest_balance_mismatch=1 THEN 1 ELSE 0 END) AS dest_mismatch,
        ROUND(
            SUM(CASE WHEN flag_orig_balance_mismatch=1 THEN 1 ELSE 0 END)*100.0/COUNT(*), 4
        ) AS orig_mismatch_pct,
        ROUND(
            SUM(CASE WHEN flag_dest_balance_mismatch=1 THEN 1 ELSE 0 END)*100.0/COUNT(*), 4
        ) AS dest_mismatch_pct
    FROM transactions
    GROUP BY type
    ORDER BY orig_mismatch DESC
    """
    return run_query(engine, sql, "balance_reconciliation")


def merchant_performance(engine: Any) -> pd.DataFrame:
    """Merchant-level aggregation joined with synthetic merchant table."""
    sql = """
    SELECT
        t.nameDest                         AS merchant_id,
        m.merchant_name_SYNTHETIC,
        m.merchant_category_SYNTHETIC,
        COUNT(*)                           AS transaction_count,
        ROUND(SUM(t.amount), 2)            AS total_amount,
        ROUND(AVG(t.amount), 2)            AS avg_amount,
        SUM(CASE WHEN t.isFraud=1 THEN 1 ELSE 0 END) AS fraud_count
    FROM transactions t
    LEFT JOIN merchants m ON t.nameDest = m.merchant_id
    WHERE t.nameDest LIKE 'M%'
    GROUP BY t.nameDest
    ORDER BY total_amount DESC
    LIMIT 50
    """
    return run_query(engine, sql, "merchant_performance")


def refund_analysis(engine: Any) -> pd.DataFrame:
    """Synthetic refund summary by status and reason."""
    sql = """
    SELECT
        refund_status_SYNTHETIC    AS status,
        refund_reason_SYNTHETIC    AS reason,
        COUNT(*)                   AS refund_count,
        ROUND(SUM(refund_amount_SYNTHETIC), 2) AS total_refund_amount,
        ROUND(AVG(refund_amount_SYNTHETIC), 2) AS avg_refund_amount
    FROM refunds
    GROUP BY refund_status_SYNTHETIC, refund_reason_SYNTHETIC
    ORDER BY refund_count DESC
    """
    return run_query(engine, sql, "refund_analysis")


def top_originator_accounts(engine: Any, n: int = 20) -> pd.DataFrame:
    sql = f"""
    SELECT
        nameOrig,
        COUNT(*)                       AS tx_count,
        ROUND(SUM(amount), 2)          AS total_sent,
        SUM(CASE WHEN isFraud=1 THEN 1 ELSE 0 END) AS fraud_count,
        MAX(amount)                    AS max_single_tx
    FROM transactions
    WHERE any_quality_flag = 0
    GROUP BY nameOrig
    ORDER BY total_sent DESC
    LIMIT {n}
    """
    return run_query(engine, sql, "top_originator_accounts")


def run_all_queries(engine: Any) -> dict[str, pd.DataFrame]:
    """Run all queries and return a dict of {name: DataFrame}."""
    funcs = {
        "monthly_trends": monthly_transaction_trends,
        "type_analysis": transaction_type_analysis,
        "fraud_analysis": fraud_analysis,
        "amount_distribution": amount_distribution,
        "data_quality": data_quality_summary,
        "hourly_fraud": hourly_fraud_pattern,
        "large_transactions": large_transaction_analysis,
        "balance_reconciliation": balance_reconciliation,
        "merchant_performance": merchant_performance,
        "top_originators": top_originator_accounts,
    }
    results = {}
    for name, fn in funcs.items():
        try:
            results[name] = fn(engine)
            log.info("✓ %s: %d rows", name, len(results[name]))
        except Exception as exc:
            log.warning("Query '%s' failed: %s", name, exc)
            results[name] = pd.DataFrame()

    # Refund analysis is only possible if the refunds table exists
    try:
        results["refund_analysis"] = refund_analysis(engine)
    except Exception as exc:
        log.warning("Refund analysis skipped: %s", exc)
        results["refund_analysis"] = pd.DataFrame()

    return results
