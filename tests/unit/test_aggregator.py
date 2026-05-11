"""tests/unit/test_aggregator.py — Unit tests for smart_budget.aggregator (TC-3.1–TC-3.8)."""
import pandas as pd
import pytest

from smart_budget.aggregator import (
    aggregate_monthly,
    zero_fill,
    apply_p90_cap,
    apply_gating,
    prepare_smart_budget_data,
)
from smart_budget.filters import filter_transactions
from tests.conftest import _load_fixture


# ---------------------------------------------------------------------------
# TC-3.1 — aggregate_monthly: correct group sum
# ---------------------------------------------------------------------------

def test_aggregate_monthly_sum():
    df = pd.DataFrame({
        "idclient": ["C1"] * 3,
        "idcompany": ["CO1"] * 3,
        "idmember": ["M1", "M1", "M1"],
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES"],
        "date": ["2025-01-05", "2025-01-15", "2025-02-10"],
        "amount": [100.0, 50.0, 200.0],
    })
    result = aggregate_monthly(df)
    jan = result[(result["period_yyyymm"] == "2025-01")]
    assert jan.iloc[0]["monthly_total"] == 150.0
    assert len(result) == 2  # January + February


# ---------------------------------------------------------------------------
# TC-3.2 — aggregate_monthly: clamp negatives to 0
# ---------------------------------------------------------------------------

def test_aggregate_monthly_clamp_negative():
    df = pd.DataFrame({
        "idclient": ["C1"],
        "idcompany": ["CO1"],
        "idmember": ["M1"],
        "defaultcategory": ["SHOPPING"],
        "date": ["2025-03-10"],
        "amount": [-50.0],  # REF > expense
    })
    result = aggregate_monthly(df)
    assert result.iloc[0]["monthly_total"] == 0.0


# ---------------------------------------------------------------------------
# TC-3.3 — zero_fill: inserts missing months with 0
# ---------------------------------------------------------------------------

def test_zero_fill_inserts_missing_months():
    # M1 has GROCERIES in Jan and Mar, but not Feb
    df = pd.DataFrame({
        "idclient": ["C1", "C1"],
        "idcompany": ["CO1", "CO1"],
        "idmember": ["M1", "M1"],
        "defaultcategory": ["GROCERIES", "GROCERIES"],
        "period_yyyymm": ["2025-01", "2025-03"],
        "monthly_total": [100.0, 80.0],
    })
    result = zero_fill(df)
    feb = result[
        (result["idmember"] == "M1") &
        (result["defaultcategory"] == "GROCERIES") &
        (result["period_yyyymm"] == "2025-02")
    ]
    assert len(feb) == 1
    assert feb.iloc[0]["monthly_total"] == 0.0


# ---------------------------------------------------------------------------
# TC-3.4 — apply_p90_cap: P90 cap applied correctly
# ---------------------------------------------------------------------------

def test_apply_p90_cap():
    totals = list(range(1, 101))  # 1..100; P90 = 90
    df = pd.DataFrame({
        "idclient": ["C1"] * 100,
        "idcompany": ["CO1"] * 100,
        "idmember": [f"M{i}" for i in range(100)],
        "defaultcategory": ["GROCERIES"] * 100,
        "period_yyyymm": ["2025-01"] * 100,
        "monthly_total": [float(t) for t in totals],
    })
    result = apply_p90_cap(df)
    assert result["monthly_total"].max() <= 90.0
    assert result[result["monthly_total"] == 90.0]["capped"].all()
    assert not result[result["monthly_total"] < 90.0]["capped"].any()


# ---------------------------------------------------------------------------
# TC-3.5 — apply_gating: exclude buckets with < 3 months
# ---------------------------------------------------------------------------

def test_apply_gating_excludes_low_data_buckets():
    # M1-GROCERIES: 3 months (passes) · M1-DINING: 2 months (excluded)
    df = pd.DataFrame({
        "idmember": ["M1"] * 5,
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES", "DINING", "DINING"],
        "period_yyyymm": ["2025-01", "2025-02", "2025-03", "2025-01", "2025-02"],
        "monthly_total": [100.0, 80.0, 90.0, 50.0, 60.0],
        "capped": [False] * 5,
        "idclient": ["C1"] * 5,
        "idcompany": ["CO1"] * 5,
    })
    result = apply_gating(df, min_months=3)
    assert set(result["defaultcategory"].unique()) == {"GROCERIES"}
    assert "DINING" not in result["defaultcategory"].values


# ---------------------------------------------------------------------------
# TC-3.6 — apply_gating: zero-filled months do NOT count toward gating
# ---------------------------------------------------------------------------

def test_apply_gating_zero_months_dont_count():
    # M1-GROCERIES: 3 months but 1 is zero → only 2 months with data → excluded
    df = pd.DataFrame({
        "idmember": ["M1"] * 3,
        "defaultcategory": ["GROCERIES"] * 3,
        "period_yyyymm": ["2025-01", "2025-02", "2025-03"],
        "monthly_total": [100.0, 0.0, 80.0],  # Feb is zero-filled
        "capped": [False] * 3,
        "idclient": ["C1"] * 3,
        "idcompany": ["CO1"] * 3,
    })
    result = apply_gating(df, min_months=3)
    # Only 2 months with data (Jan + Mar) → excluded
    assert len(result) == 0


# ---------------------------------------------------------------------------
# TC-3.7 — prepare_smart_budget_data: full pipeline end-to-end
# ---------------------------------------------------------------------------

def test_prepare_smart_budget_data_end_to_end():
    df = _load_fixture("fact_transactions_test.csv")
    filtered = filter_transactions(df)
    result = prepare_smart_budget_data(filtered, min_months=3)
    # Output column contract
    expected_cols = {
        "idclient", "idcompany", "idmember", "defaultcategory",
        "period_yyyymm", "monthly_total", "capped",
    }
    assert expected_cols.issubset(set(result.columns))
    assert (result["monthly_total"] >= 0).all()
    assert result["monthly_total"].max() <= result["monthly_total"].quantile(0.90) + 0.01
    # All remaining buckets have >= 3 months with data
    counts = result[result["monthly_total"] > 0].groupby(
        ["idmember", "defaultcategory"]
    )["period_yyyymm"].nunique()
    assert (counts >= 3).all()


# ---------------------------------------------------------------------------
# TC-3.8 — Idempotency: two runs produce identical output
# ---------------------------------------------------------------------------

def test_prepare_idempotent():
    df = _load_fixture("fact_transactions_test.csv")
    filtered = filter_transactions(df)
    result_1 = prepare_smart_budget_data(filtered.copy(), min_months=3)
    result_2 = prepare_smart_budget_data(filtered.copy(), min_months=3)
    pd.testing.assert_frame_equal(
        result_1.sort_values(result_1.columns.tolist()).reset_index(drop=True),
        result_2.sort_values(result_2.columns.tolist()).reset_index(drop=True),
    )
