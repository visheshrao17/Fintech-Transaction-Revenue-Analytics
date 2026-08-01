-- =============================================================================
-- schema.sql
-- PaySim Transaction Analytics — SQLite Schema
-- =============================================================================

-- Main transactions table
-- Mirrors the cleaned PaySim DataFrame schema (all columns including flags)
CREATE TABLE IF NOT EXISTS transactions (
    -- Original PaySim columns
    step                    INTEGER NOT NULL,
    type                    TEXT    NOT NULL,
    amount                  REAL    NOT NULL,
    nameOrig                TEXT    NOT NULL,
    oldbalanceOrg           REAL,
    newbalanceOrig          REAL,
    nameDest                TEXT    NOT NULL,
    oldbalanceDest          REAL,
    newbalanceDest          REAL,
    isFraud                 INTEGER NOT NULL DEFAULT 0,
    isFlaggedFraud          INTEGER NOT NULL DEFAULT 0,

    -- Cleaning flag columns
    flag_duplicate                  INTEGER NOT NULL DEFAULT 0,
    flag_missing_critical           INTEGER NOT NULL DEFAULT 0,
    flag_negative_amount            INTEGER NOT NULL DEFAULT 0,
    flag_zero_amount                INTEGER NOT NULL DEFAULT 0,
    flag_invalid_step               INTEGER NOT NULL DEFAULT 0,
    flag_invalid_type               INTEGER NOT NULL DEFAULT 0,
    flag_orig_balance_mismatch      INTEGER NOT NULL DEFAULT 0,
    flag_dest_balance_mismatch      INTEGER NOT NULL DEFAULT 0,
    flag_negative_balance           INTEGER NOT NULL DEFAULT 0,
    any_quality_flag                INTEGER NOT NULL DEFAULT 0,

    -- Derived columns
    day_of_sim              INTEGER,
    transaction_month       INTEGER,
    hour_of_day             INTEGER,
    amount_band             TEXT,
    is_large_transaction    INTEGER DEFAULT 0,
    orig_balance_delta      REAL,
    dest_balance_delta      REAL,
    fraud_label             TEXT
);

-- Synthetic merchant lookup table
-- ⚠️ SYNTHETIC DATA — generated for analytical demonstration purposes only
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id                     TEXT PRIMARY KEY,
    merchant_name_SYNTHETIC         TEXT,
    merchant_category_SYNTHETIC     TEXT,
    city_SYNTHETIC                  TEXT,
    country_SYNTHETIC               TEXT,
    registration_year_SYNTHETIC     INTEGER,
    data_origin                     TEXT
);

-- Synthetic refund table
-- ⚠️ SYNTHETIC DATA — generated for analytical demonstration purposes only
CREATE TABLE IF NOT EXISTS refunds (
    refund_id                   TEXT PRIMARY KEY,
    original_step               INTEGER,
    original_nameOrig           TEXT,
    original_amount             REAL,
    refund_amount_SYNTHETIC     REAL,
    refund_reason_SYNTHETIC     TEXT,
    refund_status_SYNTHETIC     TEXT,
    data_origin                 TEXT
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_tx_type    ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_tx_fraud   ON transactions(isFraud);
CREATE INDEX IF NOT EXISTS idx_tx_step    ON transactions(step);
CREATE INDEX IF NOT EXISTS idx_tx_orig    ON transactions(nameOrig);
CREATE INDEX IF NOT EXISTS idx_tx_dest    ON transactions(nameDest);
CREATE INDEX IF NOT EXISTS idx_tx_month   ON transactions(transaction_month);
CREATE INDEX IF NOT EXISTS idx_tx_amtband ON transactions(amount_band);
