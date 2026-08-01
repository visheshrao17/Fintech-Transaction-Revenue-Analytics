-- =============================================================================
-- data_quality_checks.sql
-- PaySim Transaction Analytics — Data Quality & Reconciliation Queries
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Overall data-quality exception summary
-- ---------------------------------------------------------------------------
SELECT
    'Total Rows'                AS check_name,
    COUNT(*)                    AS count,
    100.0                       AS pct
FROM transactions

UNION ALL

SELECT 'Duplicate Rows',
    SUM(CASE WHEN flag_duplicate = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_duplicate = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Missing Critical Fields',
    SUM(CASE WHEN flag_missing_critical = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_missing_critical = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Negative Amounts',
    SUM(CASE WHEN flag_negative_amount = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_negative_amount = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Zero Amounts',
    SUM(CASE WHEN flag_zero_amount = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_zero_amount = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Invalid Step Values',
    SUM(CASE WHEN flag_invalid_step = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_invalid_step = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Invalid Transaction Types',
    SUM(CASE WHEN flag_invalid_type = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_invalid_type = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Originator Balance Mismatch',
    SUM(CASE WHEN flag_orig_balance_mismatch = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_orig_balance_mismatch = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Destination Balance Mismatch',
    SUM(CASE WHEN flag_dest_balance_mismatch = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN flag_dest_balance_mismatch = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions

UNION ALL

SELECT 'Any Quality Flag',
    SUM(CASE WHEN any_quality_flag = 1 THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN any_quality_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4)
FROM transactions;


-- ---------------------------------------------------------------------------
-- 2. Balance reconciliation check by type
--    Validates that balance changes are consistent with transaction amounts
-- ---------------------------------------------------------------------------
SELECT
    type,
    COUNT(*)                                                        AS total,
    SUM(CASE WHEN flag_orig_balance_mismatch = 1 THEN 1 ELSE 0 END) AS orig_mismatch_count,
    SUM(CASE WHEN flag_dest_balance_mismatch = 1 THEN 1 ELSE 0 END) AS dest_mismatch_count,
    ROUND(
        SUM(CASE WHEN flag_orig_balance_mismatch = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2
    )                                                               AS orig_mismatch_pct,
    ROUND(
        SUM(CASE WHEN flag_dest_balance_mismatch = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2
    )                                                               AS dest_mismatch_pct
FROM transactions
GROUP BY type
ORDER BY orig_mismatch_count DESC;


-- ---------------------------------------------------------------------------
-- 3. Fraud label consistency check
--    isFraud and isFlaggedFraud cross-tabulation
-- ---------------------------------------------------------------------------
SELECT
    isFraud,
    isFlaggedFraud,
    COUNT(*)                AS count,
    ROUND(AVG(amount), 2)   AS avg_amount
FROM transactions
GROUP BY isFraud, isFlaggedFraud
ORDER BY isFraud DESC, isFlaggedFraud DESC;


-- ---------------------------------------------------------------------------
-- 4. Account-ID format audit
--    PaySim account IDs should start with 'C' (customer) or 'M' (merchant)
-- ---------------------------------------------------------------------------
SELECT
    'nameOrig'          AS column_name,
    CASE
        WHEN nameOrig LIKE 'C%' THEN 'Customer'
        WHEN nameOrig LIKE 'M%' THEN 'Merchant'
        ELSE 'Other/Invalid'
    END                 AS account_type,
    COUNT(*)            AS count
FROM transactions
GROUP BY account_type

UNION ALL

SELECT
    'nameDest',
    CASE
        WHEN nameDest LIKE 'C%' THEN 'Customer'
        WHEN nameDest LIKE 'M%' THEN 'Merchant'
        ELSE 'Other/Invalid'
    END,
    COUNT(*)
FROM transactions
GROUP BY account_type
ORDER BY column_name, count DESC;


-- ---------------------------------------------------------------------------
-- 5. Zero-balance originator analysis
--    Originators with zero old AND new balance may indicate synthetic accounts
-- ---------------------------------------------------------------------------
SELECT
    type,
    COUNT(*)                AS zero_balance_orig_count,
    SUM(CASE WHEN isFraud = 1 THEN 1 ELSE 0 END) AS fraud_in_zero_balance
FROM transactions
WHERE oldbalanceOrg = 0
  AND newbalanceOrig = 0
GROUP BY type
ORDER BY zero_balance_orig_count DESC;


-- ---------------------------------------------------------------------------
-- 6. Metric reconciliation: total count and amount by fraud label
--    Used to verify KPI numerator/denominator correctness
-- ---------------------------------------------------------------------------
SELECT
    fraud_label,
    COUNT(*)                AS transaction_count,
    ROUND(SUM(amount), 2)   AS total_amount,
    ROUND(AVG(amount), 2)   AS avg_amount,
    MIN(amount)             AS min_amount,
    MAX(amount)             AS max_amount
FROM transactions
GROUP BY fraud_label;


-- ---------------------------------------------------------------------------
-- 7. Duplicate transaction detection (beyond flag_duplicate)
--    Checks for same step + type + amount + nameOrig + nameDest
-- ---------------------------------------------------------------------------
SELECT
    step, type, amount, nameOrig, nameDest,
    COUNT(*) AS occurrence_count
FROM transactions
GROUP BY step, type, amount, nameOrig, nameDest
HAVING COUNT(*) > 1
ORDER BY occurrence_count DESC
LIMIT 25;


-- ---------------------------------------------------------------------------
-- 8. Amount outlier detection using IQR method (approximated in SQL)
-- ---------------------------------------------------------------------------
WITH quartiles AS (
    SELECT
        type,
        -- Use percentile_cont equivalent approximation
        MIN(amount)                 AS min_amount,
        MAX(amount)                 AS max_amount,
        AVG(amount)                 AS mean_amount,
        -- SQLite doesn't have percentile_cont; use these as proxies
        COUNT(*)                    AS total_count,
        SUM(CASE WHEN amount > (SELECT AVG(amount) * 3 FROM transactions t2 WHERE t2.type = t1.type)
                 THEN 1 ELSE 0 END) AS extreme_outlier_count
    FROM transactions t1
    GROUP BY type
)
SELECT * FROM quartiles ORDER BY extreme_outlier_count DESC;
