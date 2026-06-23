"""tests/conftest.py — shared helpers for test suite."""

import pathlib
import pandas as pd

_FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load_fixture(filename: str) -> pd.DataFrame:
    """Load a CSV fixture from tests/fixtures/ with proper type handling."""
    path = _FIXTURES_DIR / filename
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    # Convert empty strings to None/NaN for columns that use null semantics
    for col in ["deletedat", "status"]:
        if col in df.columns:
            df[col] = df[col].replace("", None)
    # Convert amount to float
    if "amount" in df.columns:
        df["amount"] = df["amount"].astype(float)
    return df
