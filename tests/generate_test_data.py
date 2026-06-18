"""
generate_test_data.py
=====================
Generates a reproducible PaySim-schema test dataset (10 000 rows)
for use in automated tests.  Intentionally injects:
  - A small number of duplicate rows
  - Several rows with negative amounts
  - Several rows with balance mismatches
  - A handful of fraudulent transactions

Output: data/raw/paysim_test_sample.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "paysim_test_sample.csv"

RANDOM_SEED = 42
RNG = np.random.default_rng(RANDOM_SEED)

N_ROWS = 10_000
TYPES = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]
TYPE_WEIGHTS = [0.20, 0.35, 0.05, 0.30, 0.10]


def generate() -> pd.DataFrame:
    n = N_ROWS

    steps = RNG.integers(1, 745, size=n).astype("int32")
    types = RNG.choice(TYPES, size=n, p=TYPE_WEIGHTS)
    amounts = RNG.exponential(scale=10_000, size=n).round(2)

    # Originator balances
    old_bal_orig = RNG.uniform(0, 200_000, size=n).round(2)
    new_bal_orig = (old_bal_orig - amounts).clip(min=0).round(2)

    # Destination balances
    old_bal_dest = RNG.uniform(0, 100_000, size=n).round(2)
    new_bal_dest = (old_bal_dest + amounts).round(2)

    # Account IDs
    orig_ids = [f"C{RNG.integers(1_000_000, 9_999_999):07d}" for _ in range(n)]
    dest_ids = []
    for t in types:
        if t in ("PAYMENT", "CASH_OUT") and RNG.random() < 0.15:
            dest_ids.append(f"M{RNG.integers(1_000_000, 9_999_999):07d}")
        else:
            dest_ids.append(f"C{RNG.integers(1_000_000, 9_999_999):07d}")

    is_fraud = (RNG.random(size=n) < 0.008).astype("int8")
    is_flagged_fraud = (is_fraud & (amounts > 200_000)).astype("int8")

    df = pd.DataFrame({
        "step": steps,
        "type": types,
        "amount": amounts,
        "nameOrig": orig_ids,
        "oldbalanceOrg": old_bal_orig,
        "newbalanceOrig": new_bal_orig,
        "nameDest": dest_ids,
        "oldbalanceDest": old_bal_dest,
        "newbalanceDest": new_bal_dest,
        "isFraud": is_fraud,
        "isFlaggedFraud": is_flagged_fraud,
    })

    # --- Inject known data-quality issues ---

    # 1. Duplicate rows (rows 0–4 duplicated at the end)
    dupes = df.iloc[:5].copy()
    df = pd.concat([df, dupes], ignore_index=True)

    # 2. Negative amounts (5 rows)
    df.loc[10:14, "amount"] = -500.0

    # 3. Balance mismatch (5 rows): newbalanceOrig set incorrectly
    df.loc[20:24, "newbalanceOrig"] = df.loc[20:24, "oldbalanceOrg"] + 99999.0

    # 4. Zero amounts (3 rows)
    df.loc[30:32, "amount"] = 0.0

    return df


if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = generate()
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Test dataset written: {OUTPUT_PATH} ({len(df):,} rows)")
