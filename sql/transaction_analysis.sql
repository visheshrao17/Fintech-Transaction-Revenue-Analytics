-- =============================================================================
-- transaction_analysis.sql
-- PaySim Transaction Analytics — Core Business Queries
-- Dialect: SQLite (portable SQL where possible)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Monthly transaction trends
--    Numerator: COUNT(*) per month
--    Denominator: All rows in transactions table
-- ---------------------------------------------------------------------------
SELECT
    day_of_sim / 30 + 1                                 AS sim_month,
    COUNT(*)                                            AS transaction_count,
    ROUND(SUM(amount), 2)                               AS total_amount,
    ROUND(AVG(amount), 2)                               AS avg_amount,
    MAX(amount)                                         AS max_amount,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)       AS fraud_count,
    ROUND(
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        4
    )                                                   AS fraud_rate_pct
FROM transactions
GROUP BY sim_month
ORDER BY sim_month;


-- ---------------------------------------------------------------------------
-- 2. Transaction type comparison
--    Shows volume, value, and fraud breakdown by type
-- ---------------------------------------------------------------------------
SELECT
    type,
    COUNT(*)                                                AS transaction_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)      AS share_of_volume_pct,
    ROUND(SUM(amount), 2)                                   AS total_amount,
    ROUND(AVG(amount), 2)                                   AS avg_amount,
    ROUND(MIN(amount), 2)                                   AS min_amount,
    ROUND(MAX(amount), 2)                                   AS max_amount,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)           AS fraud_count,
    ROUND(
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        4
    )                                                       AS fraud_rate_pct,
    SUM(CASE WHEN any_quality_flag = 1 THEN 1 ELSE 0 END)  AS flagged_count
FROM transactions
GROUP BY type
ORDER BY total_amount DESC;


-- ---------------------------------------------------------------------------
-- 3. Transaction amount distribution by band
-- ---------------------------------------------------------------------------
SELECT
    amount_band,
    COUNT(*)                    AS transaction_count,
    ROUND(SUM(amount), 2)       AS total_amount,
    ROUND(AVG(amount), 2)       AS avg_amount,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) AS fraud_count,
    ROUND(
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        4
    )                           AS fraud_rate_pct
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
    END;


-- ---------------------------------------------------------------------------
-- 4. Hourly transaction pattern (fraud focus)
-- ---------------------------------------------------------------------------
SELECT
    hour_of_day,
    COUNT(*)                                            AS total_transactions,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)       AS fraud_count,
    ROUND(
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        4
    )                                                   AS fraud_rate_pct,
    ROUND(AVG(amount), 2)                               AS avg_amount
FROM transactions
GROUP BY hour_of_day
ORDER BY hour_of_day;


-- ---------------------------------------------------------------------------
-- 5. Top 20 originator accounts by total sent (excluding flagged records)
-- ---------------------------------------------------------------------------
SELECT
    nameOrig,
    COUNT(*)                    AS tx_count,
    ROUND(SUM(amount), 2)       AS total_sent,
    ROUND(AVG(amount), 2)       AS avg_sent,
    MAX(amount)                 AS max_single_tx,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) AS fraud_count
FROM transactions
WHERE any_quality_flag = 0
GROUP BY nameOrig
ORDER BY total_sent DESC
LIMIT 20;


-- ---------------------------------------------------------------------------
-- 6. Large transaction analysis (>= 200,000 units)
-- ---------------------------------------------------------------------------
SELECT
    type,
    COUNT(*)                                            AS large_tx_count,
    ROUND(SUM(amount), 2)                               AS large_tx_total,
    ROUND(AVG(amount), 2)                               AS large_tx_avg,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END)       AS fraud_count,
    ROUND(
        SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        4
    )                                                   AS fraud_rate_pct
FROM transactions
WHERE is_large_transaction = 1
GROUP BY type
ORDER BY large_tx_total DESC;


-- ---------------------------------------------------------------------------
-- 7. Merchant performance (joined with synthetic merchant table)
--    Destination accounts beginning with 'M' are merchant-type receivers
-- ---------------------------------------------------------------------------
SELECT
    t.nameDest                              AS merchant_id,
    m.merchant_name_SYNTHETIC,
    m.merchant_category_SYNTHETIC,
    COUNT(*)                                AS transaction_count,
    ROUND(SUM(t.amount), 2)                 AS total_received,
    ROUND(AVG(t.amount), 2)                 AS avg_transaction,
    SUM(CASE WHEN t.isFraud = 1 THEN 1 ELSE 0 END) AS fraud_count,
    ROUND(
        SUM(CASE WHEN t.isFraud=1 THEN 1 ELSE 0 END)*100.0/COUNT(*), 4
    )                                       AS fraud_rate_pct
FROM transactions t
LEFT JOIN merchants m
    ON t.nameDest = m.merchant_id
WHERE t.nameDest LIKE 'M%'
  AND t.any_quality_flag = 0
GROUP BY t.nameDest
ORDER BY total_received DESC
LIMIT 50;


-- ---------------------------------------------------------------------------
-- 8. Refund analysis (SYNTHETIC data — joined view)
-- ---------------------------------------------------------------------------
SELECT
    r.refund_status_SYNTHETIC               AS refund_status,
    r.refund_reason_SYNTHETIC               AS refund_reason,
    COUNT(*)                                AS refund_count,
    ROUND(SUM(r.refund_amount_SYNTHETIC), 2) AS total_refund_amount,
    ROUND(AVG(r.refund_amount_SYNTHETIC), 2) AS avg_refund_amount,
    ROUND(AVG(r.refund_amount_SYNTHETIC / NULLIF(r.original_amount, 0) * 100), 2) AS avg_refund_rate_pct
FROM refunds r
GROUP BY r.refund_status_SYNTHETIC, r.refund_reason_SYNTHETIC
ORDER BY refund_count DESC;
