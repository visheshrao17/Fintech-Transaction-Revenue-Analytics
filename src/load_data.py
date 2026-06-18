"""
load_data.py
============
Configurable data-loading pipeline for the PaySim dataset.

Supports:
  - Locally downloaded CSV file (default path: data/raw/PS_20174392719_1491204439457_log.csv)
  - User-provided dataset path via DATA_PATH env variable or --path CLI argument
  - Configurable sample size for development (SAMPLE_SIZE env variable or --sample CLI argument)
  - Full-dataset processing when resources permit

Usage
-----
  python -m src.load_data                      # default path, full dataset
  python -m src.load_data --sample 50000       # sample 50 000 rows
  python -m src.load_data --path /tmp/my.csv   # custom path

Environment Variables
---------------------
  DATA_PATH   : override the default CSV path
  SAMPLE_SIZE : integer row count for development sampling (0 = full dataset)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "PS_20174392719_1491204439457_log.csv"
TEST_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "paysim_test_sample.csv"

PAYSIM_DTYPES: dict[str, str] = {
    "step": "int32",
    "type": "category",
    "amount": "float64",
    "nameOrig": "object",
    "oldbalanceOrg": "float64",
    "newbalanceOrig": "float64",
    "nameDest": "object",
    "oldbalanceDest": "float64",
    "newbalanceDest": "float64",
    "isFraud": "int8",
    "isFlaggedFraud": "int8",
}

REQUIRED_COLUMNS = list(PAYSIM_DTYPES.keys())

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_paysim(
    path: str | Path | None = None,
    sample_size: int = 0,
    random_state: int = 42,
) -> pd.DataFrame:
    """Load the PaySim dataset from a CSV file.

    Parameters
    ----------
    path : str or Path, optional
        Absolute or relative path to the CSV file. Falls back to the
        DATA_PATH environment variable, then to the default raw-data path.
        If none resolves to an existing file, the bundled test sample is used.
    sample_size : int
        Number of rows to sample. 0 means the full dataset.
    random_state : int
        Random seed used for reproducible sampling.

    Returns
    -------
    pd.DataFrame
        Raw PaySim DataFrame with standardised column names.
    """
    resolved = _resolve_path(path)

    log.info("Loading data from: %s", resolved)

    if resolved is None or not resolved.exists():
        _print_setup_instructions(path)
        if TEST_DATA_PATH.exists():
            log.warning("Falling back to bundled test sample: %s", TEST_DATA_PATH)
            resolved = TEST_DATA_PATH
        else:
            raise FileNotFoundError(
                f"Dataset not found. Please follow the setup instructions above.\n"
                f"Checked: {path or DEFAULT_DATA_PATH}"
            )

    df = _read_csv(resolved)
    df = _rename_columns(df)
    df = _coerce_dtypes(df)

    if sample_size and sample_size < len(df):
        log.info("Sampling %d rows (random_state=%d).", sample_size, random_state)
        df = df.sample(n=sample_size, random_state=random_state).reset_index(drop=True)
    else:
        log.info("Loaded full dataset: %d rows.", len(df))

    _validate_schema(df)
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_path(user_path: str | Path | None) -> Path | None:
    """Resolve the data file path in priority order."""
    if user_path:
        return Path(user_path).expanduser().resolve()
    env_path = os.getenv("DATA_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_DATA_PATH


def _read_csv(path: Path) -> pd.DataFrame:
    """Read CSV with sensible defaults and progress logging."""
    file_size_mb = path.stat().st_size / (1024 ** 2)
    log.info("File size: %.1f MB", file_size_mb)
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        raise IOError(f"Failed to read CSV at {path}: {exc}") from exc
    log.info("Raw shape: %d rows × %d cols", *df.shape)
    return df


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and normalise column names."""
    df.columns = [c.strip() for c in df.columns]
    return df


def _coerce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Cast columns to preferred dtypes where possible."""
    for col, dtype in PAYSIM_DTYPES.items():
        if col in df.columns:
            try:
                df[col] = df[col].astype(dtype)
            except (ValueError, TypeError) as exc:
                log.warning("Could not cast column '%s' to %s: %s", col, dtype, exc)
    return df


def _validate_schema(df: pd.DataFrame) -> None:
    """Warn if expected columns are missing."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        log.warning("Missing expected columns: %s", missing)


def _print_setup_instructions(path: str | Path | None) -> None:
    instructions = f"""
╔══════════════════════════════════════════════════════════════════╗
║              PaySim Dataset — Setup Instructions                  ║
╠══════════════════════════════════════════════════════════════════╣
║  1. Visit: https://www.kaggle.com/datasets/ealaxi/paysim1        ║
║  2. Sign in to Kaggle and accept the dataset terms.              ║
║  3. Click "Download" to obtain the CSV (~500 MB).               ║
║  4. Place the file here:                                         ║
║     {str(DEFAULT_DATA_PATH):<60s}║
║     OR set the DATA_PATH environment variable:                   ║
║       export DATA_PATH=/path/to/PS_*_log.csv                    ║
║  5. Re-run the pipeline.                                         ║
║                                                                  ║
║  Development: run with --sample 50000 for faster iteration.      ║
╚══════════════════════════════════════════════════════════════════╝
"""
    log.warning(instructions)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load PaySim transaction data.")
    parser.add_argument("--path", default=None, help="Path to the PaySim CSV file.")
    parser.add_argument(
        "--sample",
        type=int,
        default=int(os.getenv("SAMPLE_SIZE", "0")),
        help="Number of rows to sample (0 = full dataset).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    dataset = load_paysim(path=args.path, sample_size=args.sample)
    print(dataset.head())
    print(f"\nShape: {dataset.shape}")
