"""tests/unit/test_golden_set.py — TDD tests for DATA-1179 T6.

Test contracts for golden_set.csv with idmember schema.
"""
import pathlib
import pandas as pd
import pytest


_FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"


def _load_golden() -> pd.DataFrame:
    return pd.read_csv(_FIXTURES_DIR / "golden_set.csv", dtype=str, keep_default_na=False)


# ---------------------------------------------------------------------------
# TC-T6-1: golden_set.csv has idmember column
# ---------------------------------------------------------------------------

def test_TC_T6_1_golden_set_has_idmember_column():
    """Assert: 'idmember' in golden_set.csv columns."""
    golden = _load_golden()
    assert "idmember" in golden.columns, (
        f"Expected 'idmember' in golden_set.csv columns, got: {list(golden.columns)}"
    )


# ---------------------------------------------------------------------------
# TC-T6-2: golden_set.csv has at least 3 distinct idmember
# ---------------------------------------------------------------------------

def test_TC_T6_2_golden_set_has_at_least_3_idmembers():
    """Assert: golden_set.csv has at least 3 distinct idmember values."""
    golden = _load_golden()
    assert "idmember" in golden.columns, "idmember column must exist"
    n_members = golden["idmember"].nunique()
    assert n_members >= 3, (
        f"Expected >= 3 distinct idmember in golden_set.csv, got: {n_members}"
    )


# ---------------------------------------------------------------------------
# TC-T6-3: golden_set.csv has 6 distinct periods
# ---------------------------------------------------------------------------

def test_TC_T6_3_golden_set_has_6_periods():
    """Assert: golden_set.csv has exactly 6 distinct period_yyyymm values."""
    golden = _load_golden()
    assert "period_yyyymm" in golden.columns, "period_yyyymm column must exist"
    n_periods = golden["period_yyyymm"].nunique()
    assert n_periods == 6, (
        f"Expected 6 distinct period_yyyymm in golden_set.csv, got: {n_periods}"
    )


# ---------------------------------------------------------------------------
# TC-T6-4: golden_set.csv output matches WMA/A/2026-03 computation
# ---------------------------------------------------------------------------

def test_TC_T6_4_golden_set_matches_wma_output():
    """WMA/A/2026-03-01 output matches committed golden_set.csv exactly."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

    from smart_budget.aggregator import apply_gating
    from smart_budget.model import compute_budget_suggestions

    golden = _load_golden()
    golden["suggested_amount"] = golden["suggested_amount"].astype(float)

    # Load source data
    data_path = pathlib.Path(__file__).parent.parent.parent / "data" / "dough" / "smart_budget_synthetic.csv"
    if not data_path.exists():
        pytest.skip(f"Synthetic data file not found: {data_path}")

    raw_df = pd.read_csv(data_path)
    prepared_df = apply_gating(raw_df, min_months=3)

    results = compute_budget_suggestions(
        prepared_df, method="wma", treatment="A", reference_date="2026-03-01"
    )

    # Build map using idmember + category
    results_map = {
        (str(r["idmember"]), r["category_id"], r["defaultcategory"]): r["suggested_amount"]
        for r in results
    }

    for _, row in golden.iterrows():
        key = (str(row["idmember"]), row["category_id"], row["defaultcategory"])
        assert key in results_map, f"Bucket {key} missing from model output"
        expected = float(row["suggested_amount"])
        actual = results_map[key]
        assert actual == expected, (
            f"Bucket {key}: expected {expected}, got {actual}"
        )
