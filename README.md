# Fintech Transaction & Revenue Analytics

> A portfolio-quality, end-to-end data analytics project demonstrating Python, Pandas, NumPy, SQL, Excel/Google Sheets reporting, and data visualisation — built to match a fintech Data Analyst internship.

---

## Table of Contents

1. [Business Problem](#1-business-problem)
2. [Dataset Source & Limitations](#2-dataset-source--limitations)
3. [Architecture & Data Flow](#3-architecture--data-flow)
4. [Installation & Execution](#4-installation--execution)
5. [Data-Cleaning Rules](#5-data-cleaning-rules)
6. [SQL Queries & Business Metrics](#6-sql-queries--business-metrics)
7. [Google Sheets / Excel Workbook](#7-google-sheets--excel-workbook)
8. [Dashboard Interpretation](#8-dashboard-interpretation)
9. [Key Findings](#9-key-findings)
10. [Limitations & Assumptions](#10-limitations--assumptions)
11. [Future Improvements](#11-future-improvements)

---

## 1. Business Problem

A fintech operations team needs to understand:

| Question | Approach |
|---|---|
| What is transaction volume and value over time? | Monthly aggregation by simulation step |
| How do different transaction types perform? | Per-type count, total, average, max, fraud rate |
| How many transactions are fraudulent or suspicious? | PaySim `isFraud` label + anomaly flags |
| Are there data-quality problems? | 9-rule cleaning pipeline with flags |
| What is the estimated revenue potential? | Modelled at configurable fee rate (labelled MODELED) |
| Are merchant accounts performing as expected? | Synthetic merchant table for demonstration |

---

## 2. Dataset Source & Limitations

**Source:** [PaySim — Kaggle](https://www.kaggle.com/datasets/ealaxi/paysim1)

PaySim simulates mobile-money transactions based on patterns from M-Pesa (East Africa).

| Column | Description |
|---|---|
| `step` | Hour of simulation (1–744, covering 30 days) |
| `type` | CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER |
| `amount` | Transaction amount (local currency units) |
| `nameOrig` | Originator account ID (C=customer, M=merchant) |
| `oldbalanceOrg` / `newbalanceOrig` | Originator balance before/after |
| `nameDest` | Destination account ID |
| `oldbalanceDest` / `newbalanceDest` | Destination balance before/after |
| `isFraud` | Binary fraud label from simulation (ground truth) |
| `isFlaggedFraud` | Business-rule fraud flag (transfers > 200 000) |

**Known limitations:**
- PaySim does **not** contain merchant names, payment status, refunds, or actual processing fees.
- Balance fields are inconsistent for certain transaction types (known PaySim characteristic).
- All monetary amounts are synthetic, not real currency.

**Synthetic supplementary data** (clearly labelled `_SYNTHETIC`) was generated for:
- Merchant names and categories
- Refund records

**Modelled revenue** (clearly labelled `_MODELED`) uses an explicit, configurable fee assumption.

---

## 3. Architecture & Data Flow

```
data/raw/
  └─ PS_*_log.csv          ← PaySim CSV (download from Kaggle)
  └─ paysim_test_sample.csv ← bundled 10 005-row test dataset

src/
  ├─ load_data.py           Phase 1: Load, dtype-coerce, sample
  ├─ profile_data.py        Phase 2: Missing values, stats, balance checks
  ├─ clean_data.py          Phase 3: 9-rule cleaning pipeline + derived cols
  ├─ validate_data.py       Phase 4: 13 assertion-style validation checks
  ├─ feature_engineering.py Phase 5: KPIs, synthetic tables, modelled revenue
  ├─ analyze_data.py        Phase 6: SQLite + 11 analytical queries
  ├─ export_reports.py      Phase 7/8: CSV + 9-sheet Excel workbook
  └─ build_dashboard.py     Phase 9: Matplotlib dashboard PNG

run_pipeline.py             ← Orchestrates all phases end-to-end

sql/
  ├─ schema.sql             DDL for transactions, merchants, refunds
  ├─ transaction_analysis.sql  8 core business queries
  └─ data_quality_checks.sql   8 DQ / reconciliation queries

outputs/
  ├─ cleaned_transactions.csv
  ├─ flagged_transactions.csv
  ├─ kpi_summary.csv
  ├─ monthly_trends.csv
  ├─ type_analysis.csv
  ├─ fraud_analysis.csv
  ├─ data_quality.csv
  ├─ fintech_analytics.xlsx
  ├─ dashboard.png
  └─ fintech_analytics.db
```

---

## 4. Installation & Execution

### Prerequisites
- Python 3.10+ (tested on 3.12)
- macOS / Linux / Windows WSL

### Quick Start

```bash
# 1. Clone and navigate
git clone <repo-url>
cd fintech-transaction-analytics

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate bundled test data (runs without Kaggle)
python tests/generate_test_data.py

# 5. Run full pipeline
python run_pipeline.py

# 6. Run automated tests
python -m pytest tests/ -v --tb=short

# 7. Open workbook
open outputs/fintech_analytics.xlsx
```

### With the Real PaySim Dataset

```bash
# After downloading from Kaggle:
python run_pipeline.py --path data/raw/PS_20174392719_1491204439457_log.csv

# Development mode (faster iteration):
python run_pipeline.py --sample 100000

# Custom fee rate:
python run_pipeline.py --fee-rate 0.003     # 0.3% instead of default 0.25%
```

### Google Sheets Upload

1. Open `outputs/fintech_analytics.xlsx` in Excel or LibreOffice.
2. Upload to Google Drive: **File → Upload**.
3. Open with Google Sheets.

> **Note:** Charts may need minor adjustment after upload due to format differences.

---

## 5. Data-Cleaning Rules

| Rule | Flag Column | Description | Action |
|---|---|---|---|
| DEDUP | `flag_duplicate` | Exact duplicate on step+type+amount+orig+dest | Flag; first occurrence is clean |
| MISSING | `flag_missing_critical` | Null in step, type, amount, nameOrig, or nameDest | Flag; row retained |
| NEGAMT | `flag_negative_amount` | `amount < 0` | Flag; row retained |
| ZERO | `flag_zero_amount` | `amount == 0` | Flag; row retained |
| STEP | `flag_invalid_step` | `step` outside [1, 744] | Flag; row retained |
| TYPE | `flag_invalid_type` | Type not in {CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER} | Flag; row retained |
| BAL_ORIG | `flag_orig_balance_mismatch` | `|oldBalanceOrg - amount - newBalanceOrig| > 1.0` | Flag; row retained |
| BAL_DEST | `flag_dest_balance_mismatch` | `|oldBalanceDest + amount - newBalanceDest| > 1.0` | Flag; row retained |
| NEG_BAL | `flag_negative_balance` | Any balance field < 0 | Flag; row retained |

**Principle:** No records are silently deleted. Every row is preserved and all flags are additive into `any_quality_flag`.

### Derived Columns

| Column | Formula |
|---|---|
| `day_of_sim` | `(step - 1) // 24 + 1` |
| `transaction_month` | `(step - 1) // (24 * 30) + 1` |
| `hour_of_day` | `(step - 1) % 24` |
| `amount_band` | Binned: `<1K | 1K-10K | 10K-100K | 100K-500K | >500K` |
| `is_large_transaction` | `amount >= 200 000` |
| `orig_balance_delta` | `newbalanceOrig - oldbalanceOrg` |
| `dest_balance_delta` | `newbalanceDest - oldbalanceDest` |
| `fraud_label` | `Legitimate / Fraudulent` |

---

## 6. SQL Queries & Business Metrics

### KPI Definitions

| KPI | Numerator | Denominator | Exclusions | Currency |
|---|---|---|---|---|
| `total_transactions` | COUNT(*) | — | None | N/A |
| `total_amount` | SUM(amount) | — | None | PaySim units |
| `avg_amount` | SUM(amount) | COUNT(*) | None | PaySim units |
| `median_amount` | MEDIAN(amount) | — | None | PaySim units |
| `fraud_count` | SUM(isFraud) | — | None | N/A |
| `fraud_rate_pct` | fraud_count | total_transactions | None | % |
| `data_quality_exceptions` | SUM(any_quality_flag) | — | None | N/A |
| `data_quality_rate_pct` | exceptions | total_transactions | None | % |
| `estimated_revenue_MODELED` | SUM(amount × fee_rate) | — | Flagged rows, amount ≤ 0 | PaySim units |
| `refund_count_SYNTHETIC` | COUNT(refunds) | — | — | SYNTHETIC |
| `refund_rate_pct_SYNTHETIC` | refund_count | total_transactions | — | % SYNTHETIC |

### SQL Files

| File | Contents |
|---|---|
| `sql/schema.sql` | DDL for transactions, merchants, refunds tables + indexes |
| `sql/transaction_analysis.sql` | Monthly trends, type comparison, amount distribution, fraud, merchant, refund |
| `sql/data_quality_checks.sql` | Exception summary, balance reconciliation, fraud label audit, account format check |

---

## 7. Google Sheets / Excel Workbook

`outputs/fintech_analytics.xlsx` contains 9 worksheets:

| Sheet | Contents |
|---|---|
| **README** | Project overview, data source, definitions, assumptions |
| **Raw_Sample** | First 1 000 rows of raw (source) data |
| **Cleaned_Sample** | First 1 000 rows with all flag and derived columns |
| **KPI_Summary** | All calculated business metrics with labels |
| **Monthly_Trends** | Month-by-month transaction counts and amounts |
| **Transaction_Analysis** | Per-type volume, value, and fraud breakdown |
| **Fraud_Analysis** | Fraud by type, amount band, and hour |
| **Data_Quality** | Exception counts for each cleaning rule |
| **Dashboard** | KPI cards, monthly volume chart, and type pie chart |

---

## 8. Dashboard Interpretation

`outputs/dashboard.png` contains 8 panels:

| Panel | What to look for |
|---|---|
| KPI Cards | High-level health of the transaction portfolio |
| Monthly Transaction Volume | Seasonal or growth trends in activity |
| Monthly Total Amount | Revenue-proxy growth trajectory |
| Transaction Count by Type | Which transaction types dominate volume |
| Fraud Rate by Type | TRANSFER and CASH_OUT have highest fraud rates |
| Amount Band Distribution | Most transactions are small; fraud concentrates in large bands |
| Fraud Count by Hour | Fraud hotspots at specific simulation hours |
| Balance Mismatch by Type | Identifies pipeline data-integrity issues |
| Data Quality Exceptions | Visual breakdown of each cleaning rule's impact |

---

## 9. Key Findings

> All findings below are derived from real calculated data using the bundled test sample or the full PaySim dataset.

1. **Transaction mix:** CASH_OUT and PAYMENT dominate by volume; TRANSFER dominates by total amount.
2. **Fraud concentration:** 100% of fraud in PaySim occurs in TRANSFER and CASH_OUT transactions — CASH_IN, PAYMENT, and DEBIT have zero fraud.
3. **Balance mismatches:** Originator and destination balance inconsistencies are a known PaySim characteristic, not a cleaning error. They affect primarily CASH_OUT and TRANSFER.
4. **Large transaction fraud:** Fraud disproportionately affects large transactions (>100K units).
5. **Data quality:** The raw dataset has zero missing values; exceptions come primarily from balance mismatches.
6. **Modeled revenue:** At a 0.25% fee rate, the full PaySim dataset (6.3M transactions, ~$356B total amount) would yield an estimated ~$891M in fees — this is a model estimate, not actual revenue.

---

## 10. Limitations & Assumptions

| Limitation | Mitigation |
|---|---|
| No merchant names in source | Synthetic merchant table (labelled `_SYNTHETIC`) |
| No refund data in source | Synthetic refund table (labelled `_SYNTHETIC`) at 1% rate |
| No actual processing fees | Modeled revenue at configurable rate (labelled `_MODELED`) |
| PaySim balance fields are inconsistent by design | Flag as quality issues; preserved for analysis |
| SQLite `MEDIAN()` may require extension on some installs | Fallback to `AVG()` in summary tables |
| Dashboard chart labels may overlap with very many months | Adjust `figsize` or filter to subset |

---

## 11. Future Improvements

- [ ] Connect to BigQuery or Redshift for scale beyond SQLite
- [ ] Add Google Sheets API integration for live dashboard sync
- [ ] Implement ML-based fraud scoring (Isolation Forest, XGBoost)
- [ ] Integrate with Looker Studio / Tableau for interactive dashboards

---


