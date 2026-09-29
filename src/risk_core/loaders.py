from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_BOOK_DIR = Path("config/risk_book")


def _read_csv(book_dir: Path, filename: str) -> pd.DataFrame:
    path = book_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Synthetic risk-book file not found: {path}")
    return pd.read_csv(path)


def load_fx_positions(book_dir: Path = DEFAULT_BOOK_DIR) -> pd.DataFrame:
    return _read_csv(book_dir, "fx_positions.csv")


def load_bond_positions(book_dir: Path = DEFAULT_BOOK_DIR) -> pd.DataFrame:
    return _read_csv(book_dir, "bond_positions.csv")


def load_liquidity_gap(book_dir: Path = DEFAULT_BOOK_DIR) -> pd.DataFrame:
    df = _read_csv(book_dir, "liquidity_gap.csv")
    return df.sort_values("bucket_order").reset_index(drop=True)


def load_risk_limits(book_dir: Path = DEFAULT_BOOK_DIR) -> pd.DataFrame:
    return _read_csv(book_dir, "risk_limits.csv")


def load_stress_scenarios(book_dir: Path = DEFAULT_BOOK_DIR) -> pd.DataFrame:
    return _read_csv(book_dir, "stress_scenarios.csv")
