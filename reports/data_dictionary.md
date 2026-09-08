# Fintech Transaction Analytics — Data Dictionary

**Document Version:** 1.0.0  
**Last Updated:** October 2026  
**Target Systems:** Data Warehouse, SQLite Analytical Store, Executive Excel Reporting, Tableau/Looker  

---

## 1. Core Transaction Dataset (`transactions`)

Primary table originating from the PaySim simulated mobile-money ecosystem, enriched with data-cleaning flags and derived analytical dimensions.

| Column Name | Data Type | Nullable | Origin / Phase | Business Definition | Valid Values / Constraints | Example |
|---|---|---|---|---|---|---|
| `step` | `INTEGER` | No | Source (Raw) | Unit of time representing 1 hour of simulation elapsed since epoch (1 = Day 1, 00:00). Covers 744 hours (31 days). | `1 <= step <= 744` | `142` |
| `type` | `VARCHAR(16)` | No | Source (Raw) | The functional category/modality of the financial transaction. | `'CASH_IN'`, `'CASH_OUT'`, `'DEBIT'`, `'PAYMENT'`, `'TRANSFER'` | `'TRANSFER'` |
| `amount` | `DOUBLE PRECISION` | No | Source (Raw) | The nominal monetary transfer value in local synthetic currency units. | Typically `> 0`. Flagged if `<= 0`. | `18420.50` |
| `nameOrig` | `VARCHAR(32)` | No | Source (Raw) | Unique customer identifier initiating the transaction. Prefixed with 'C' (Customer) or 'M' (Merchant). | Regex: `^[CM][0-9]+$` | `'C1234567890'` |
| `oldbalanceOrg` | `DOUBLE PRECISION` | No | Source (Raw) | Originator account balance immediately prior to transaction execution. | `>= 0.0` | `25000.00` |
| `newbalanceOrig` | `DOUBLE PRECISION` | No | Source (Raw) | Originator account balance immediately after transaction execution. | `>= 0.0` | `6579.50` |
| `nameDest` | `VARCHAR(32)` | No | Source (Raw) | Unique recipient identifier. Prefixed with 'C' (Customer) or 'M' (Merchant). | Regex: `^[CM][0-9]+$` | `'M9876543210'` |
| `oldbalanceDest` | `DOUBLE PRECISION` | No | Source (Raw) | Recipient account balance immediately prior to transaction execution. | `>= 0.0` | `0.00` |
| `newbalanceDest` | `DOUBLE PRECISION` | No | Source (Raw) | Recipient account balance immediately after transaction execution. | `>= 0.0` | `18420.50` |
| `isFraud` | `TINYINT` | No | Source (Raw) | Ground truth simulation flag indicating fraudulent activity committed by simulated agents. | `0` (Legitimate), `1` (Fraudulent) | `1` |
| `isFlaggedFraud` | `TINYINT` | No | Source (Raw) | Legacy business rule flag tripped whenever an unauthorized transfer attempt exceeds 200,000 units. | `0`, `1` | `0` |

---

## 2. Data Quality Flags (Cleaned Layer)

Additive boolean indicators added during Phase 3 of the data pipeline (`src/clean_data.py`). No raw transaction is purged; records are transparently tagged for auditability.

| Column Name | Data Type | Rule ID | Detection Logic / Trigger Condition | Operational Severity |
|---|---|---|---|---|
| `flag_duplicate` | `BOOLEAN` | DEDUP | Duplicate row matching on `[step, type, amount, nameOrig, nameDest]`. First occurrence is clean. | Medium (Client retry) |
| `flag_missing_critical` | `BOOLEAN` | MISSING | Any null or NaN value in mandatory primary keys: `step`, `type`, `amount`, `nameOrig`, `nameDest`. | High (Malformed schema) |
| `flag_negative_amount` | `BOOLEAN` | NEGAMT | Nominal transaction `amount < 0.0`. | High (Accounting error) |
| `flag_zero_amount` | `BOOLEAN` | ZERO | Nominal transaction `amount == 0.0`. | Low (Ping/test transaction) |
| `flag_invalid_step` | `BOOLEAN` | STEP | Simulation step outside valid temporal boundary: `step < 1 OR step > 744`. | High (Clock skew) |
| `flag_invalid_type` | `BOOLEAN` | TYPE | Transaction type not matching allowed enum: `{CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER}`. | High (Protocol violation) |
| `flag_orig_balance_mismatch` | `BOOLEAN` | BAL_ORIG | $\| \text{oldbalanceOrg} - \text{amount} - \text{newbalanceOrig} \| > 1.0$ (Tolerance: 1.0 currency unit for float rounding). | Critical (Ledger desync) |
| `flag_dest_balance_mismatch` | `BOOLEAN` | BAL_DEST | $\| \text{oldbalanceDest} + \text{amount} - \text{newbalanceDest} \| > 1.0$ (Only checked for customer-to-customer flows). | Medium (M-Pesa masking) |
| `flag_negative_balance` | `BOOLEAN` | NEG_BAL | Any balance field (`oldbalanceOrg`, `newbalanceOrig`, `oldbalanceDest`, `newbalanceDest`) $< 0.0$. | High (Unauthorized overdraft) |
| `any_quality_flag` | `BOOLEAN` | AGGREGATE | Logical OR across all 9 individual flag columns above. Indicates row has $\ge 1$ exception. | Variable |

---

## 3. Derived Business Dimensions (Feature Engineering Layer)

Engineered attributes appended during Phase 5 (`src/feature_engineering.py`) to support aggregations, time-series, and risk cohorting.

| Column Name | Data Type | Derivation Formula | Business Purpose |
|---|---|---|---|
| `day_of_sim` | `INTEGER` | `(step - 1) // 24 + 1` | Day of simulation calendar (Day 1 to Day 31). |
| `hour_of_day` | `INTEGER` | `(step - 1) % 24` | Diurnal cycle hour (0 to 23), matching customer daily activity patterns. |
| `transaction_month` | `INTEGER` | `(step - 1) // (24 * 30) + 1` | Simulation month index (Month 1, Month 2). |
| `amount_band` | `VARCHAR(16)` | Binned: `<1K`, `1K-10K`, `10K-100K`, `100K-500K`, `>500K` | Transaction size stratification for risk exposure profiling. |
| `is_large_transaction` | `BOOLEAN` | `amount >= 200,000.0` | Large-ticket transaction flag for compliance thresholds. |
| `orig_balance_delta` | `DOUBLE PRECISION` | `newbalanceOrig - oldbalanceOrg` | Net delta in sender's ledger account. |
| `dest_balance_delta` | `DOUBLE PRECISION` | `newbalanceDest - oldbalanceDest` | Net delta in recipient's ledger account. |
| `fraud_label` | `VARCHAR(16)` | `'Fraudulent' if isFraud == 1 else 'Legitimate'` | Human-readable dimension for BI dashboards and pivot tables. |

---

## 4. Supplementary & Modeled Entities

To simulate enterprise analytics while strictly maintaining transparency, synthetic entities and modeled fields are explicitly identified with suffixes:

### A. Merchants Metadata Table (`merchants_SYNTHETIC`)
Simulated partner directory linked via `merchants_SYNTHETIC.merchant_id = transactions.nameDest`.

| Field Name | Type | Description | Values / Notes |
|---|---|---|---|
| `merchant_id` | `VARCHAR(32)` | Merchant identifier matching PaySim `'M...'` accounts. | Primary Key |
| `merchant_name` | `VARCHAR(64)` | Realistic business operating name. | e.g. "Apex Retail Group" |
| `category` | `VARCHAR(32)` | Merchant category code (MCC) grouping. | Grocery, Electronics, Utilities, Travel, Dining |
| `fee_tier` | `VARCHAR(16)` | Contracted interchange tier. | Tier 1 (15 bps), Tier 2 (25 bps), Tier 3 (35 bps) |

### B. Refunds Table (`refunds_SYNTHETIC`)
Simulated dispute and customer reversal records linked via `refunds_SYNTHETIC.transaction_step = transactions.step AND refunds_SYNTHETIC.nameOrig = transactions.nameOrig`.

| Field Name | Type | Description | Values / Notes |
|---|---|---|---|
| `refund_id` | `VARCHAR(32)` | Unique dispute/refund ticket identifier. | Primary Key (`REF_...`) |
| `transaction_id`| `INTEGER` | Foreign reference to original transaction. | Integer index |
| `refund_amount` | `DOUBLE PRECISION`| Amount credited back to consumer. | Equal to original transaction amount |
| `reason` | `VARCHAR(64)` | Operational reversal reason code. | Duplicate Charge, Fraud Dispute, Customer Return |
| `status` | `VARCHAR(16)` | Settlement state. | `APPROVED`, `PENDING`, `REJECTED` |

### C. Modeled Financial Metrics (`_MODELED`)

| Metric Name | Formula | Default Assumption | Exclusions / Notes |
|---|---|---|---|
| `estimated_revenue_MODELED` | $\sum (\text{amount} \times \text{fee\_rate})$ | $0.25\%$ (25 bps flat) | Excludes rows with `any_quality_flag == True` or `amount <= 0`. Clearly designated as modeled estimate. |
