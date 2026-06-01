"""tests/unit/test_aggregator.py — Unit tests for smart_budget.aggregator (TC-3.1–TC-3.7 + DATA-1179 TC-T3-1–T3-5)."""
import pandas as pd
import pytest

from smart_budget.aggregator import (
    aggregate_monthly,
    zero_fill,
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
        "idmember": [10, 10, 10],
        "idaccount": ["M1", "M1", "M1"],
        "idcategory": ["5", "5", "5"],
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
        "idmember": [10],
        "idaccount": ["M1"],
        "idcategory": ["5"],
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
        "idmember": [10, 10],
        "idaccount": ["M1", "M1"],
        "idcategory": ["5", "5"],
        "defaultcategory": ["GROCERIES", "GROCERIES"],
        "period_yyyymm": ["2025-01", "2025-03"],
        "monthly_total": [100.0, 80.0],
    })
    result = zero_fill(df)
    feb = result[
        (result["idmember"] == 10) &
        (result["defaultcategory"] == "GROCERIES") &
        (result["period_yyyymm"] == "2025-02")
    ]
    assert len(feb) == 1
    assert feb.iloc[0]["monthly_total"] == 0.0


# ---------------------------------------------------------------------------
# TC-3.4 — apply_gating: exclude buckets with < 3 months
# ---------------------------------------------------------------------------

def test_apply_gating_excludes_low_data_buckets():
    # M1-GROCERIES: 3 months (passes) · M1-DINING: 2 months (excluded)
    df = pd.DataFrame({
        "idmember": [10] * 5,
        "idaccount": ["M1"] * 5,
        "idcategory": ["5", "5", "5", "9", "9"],
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES", "DINING", "DINING"],
        "period_yyyymm": ["2025-01", "2025-02", "2025-03", "2025-01", "2025-02"],
        "monthly_total": [100.0, 80.0, 90.0, 50.0, 60.0],
        "idclient": ["C1"] * 5,
        "idcompany": ["CO1"] * 5,
    })
    result = apply_gating(df, min_months=3)
    assert set(result["defaultcategory"].unique()) == {"GROCERIES"}
    assert "DINING" not in result["defaultcategory"].values


# ---------------------------------------------------------------------------
# TC-3.5 — apply_gating: zero-filled months do NOT count toward gating
# ---------------------------------------------------------------------------

def test_apply_gating_zero_months_dont_count():
    # M1-GROCERIES: 3 months but 1 is zero → only 2 months with data → excluded
    df = pd.DataFrame({
        "idmember": [10] * 3,
        "idaccount": ["M1"] * 3,
        "idcategory": ["5"] * 3,
        "defaultcategory": ["GROCERIES"] * 3,
        "period_yyyymm": ["2025-01", "2025-02", "2025-03"],
        "monthly_total": [100.0, 0.0, 80.0],  # Feb is zero-filled
        "idclient": ["C1"] * 3,
        "idcompany": ["CO1"] * 3,
    })
    result = apply_gating(df, min_months=3)
    # Only 2 months with data (Jan + Mar) → excluded
    assert len(result) == 0


# ---------------------------------------------------------------------------
# TC-3.6 — prepare_smart_budget_data: full pipeline end-to-end (updated)
# ---------------------------------------------------------------------------

def test_prepare_smart_budget_data_end_to_end():
    df = _load_fixture("fact_transactions_test.csv")
    filtered = filter_transactions(df)
    # Add idmember for the test (all rows get member 1)
    filtered = filtered.copy()
    filtered["idmember"] = 1
    result = prepare_smart_budget_data(filtered, min_months=3)
    # Output column contract: idmember replaces idaccount in output
    expected_cols = {
        "idclient", "idcompany", "idmember", "idcategory", "defaultcategory",
        "period_yyyymm", "monthly_total",
    }
    assert expected_cols.issubset(set(result.columns))
    assert (result["monthly_total"] >= 0).all()
    # All remaining buckets have >= 3 months with data
    if len(result) > 0:
        counts = result[result["monthly_total"] > 0].groupby(
            ["idmember", "defaultcategory"]
        )["period_yyyymm"].nunique()
        assert (counts >= 3).all()


# ---------------------------------------------------------------------------
# TC-3.7 — Idempotency: two runs produce identical output
# ---------------------------------------------------------------------------

def test_prepare_idempotent():
    df = _load_fixture("fact_transactions_test.csv")
    filtered = filter_transactions(df)
    filtered = filtered.copy()
    filtered["idmember"] = 1
    result_1 = prepare_smart_budget_data(filtered.copy(), min_months=3)
    result_2 = prepare_smart_budget_data(filtered.copy(), min_months=3)
    pd.testing.assert_frame_equal(
        result_1.sort_values(result_1.columns.tolist()).reset_index(drop=True),
        result_2.sort_values(result_2.columns.tolist()).reset_index(drop=True),
    )


# ---------------------------------------------------------------------------
# TC-T3-1 (DATA-1179): aggregate_monthly includes idmember in output
# ---------------------------------------------------------------------------

def test_TC_T3_1_aggregate_monthly_includes_idmember():
    """Arrange: df with idmember=10, idaccount="EXT2", 2 transactions.
    Act: aggregate_monthly(df)
    Assert: "idmember" in result.columns AND result["idmember"].iloc[0] == 10
    """
    df = pd.DataFrame({
        "idclient": ["C1", "C1"],
        "idcompany": ["CO1", "CO1"],
        "idmember": [10, 10],
        "idaccount": ["EXT2", "EXT2"],
        "idcategory": ["5", "5"],
        "defaultcategory": ["GROCERIES", "GROCERIES"],
        "date": ["2025-01-05", "2025-01-15"],
        "amount": [100.0, 50.0],
    })
    result = aggregate_monthly(df)
    assert "idmember" in result.columns
    assert result["idmember"].iloc[0] == 10


# ---------------------------------------------------------------------------
# TC-T3-2 (DATA-1179): zero_fill validates idmember (not idaccount)
# ---------------------------------------------------------------------------

def test_TC_T3_2_zero_fill_validates_idmember_uniqueness():
    """Arrange: df where idmember=10 maps to idclient=1 in some rows, idclient=2 in others.
    Act: zero_fill(df)
    Assert: raises ValueError with "idmember maps to multiple"
    """
    df = pd.DataFrame({
        "idclient": ["C1", "C2"],
        "idcompany": ["CO1", "CO1"],
        "idmember": [10, 10],
        "idaccount": ["EXT2", "EXT3"],
        "idcategory": ["5", "5"],
        "defaultcategory": ["GROCERIES", "GROCERIES"],
        "period_yyyymm": ["2025-01", "2025-01"],
        "monthly_total": [100.0, 80.0],
    })
    with pytest.raises(ValueError, match="idmember maps to multiple"):
        zero_fill(df)


# ---------------------------------------------------------------------------
# TC-T3-3 (DATA-1179): zero_fill preserves idmember in expanded grid
# ---------------------------------------------------------------------------

def test_TC_T3_3_zero_fill_preserves_idmember_in_grid():
    """Arrange: df with 2 idmembers, 2 categories, 3 months (some empty).
    Act: zero_fill(df)
    Assert: "idmember" in result.columns
    Assert: len(result) == 2 * 2 * 3 (members × categories × months)
    """
    # member 10: GROCERIES months Jan, Mar (Feb missing)
    # member 20: DINING months Jan, Feb (Mar missing)
    df = pd.DataFrame({
        "idclient": ["C1", "C1", "C1", "C1"],
        "idcompany": ["CO1", "CO1", "CO1", "CO1"],
        "idmember": [10, 10, 20, 20],
        "idaccount": ["EXT2", "EXT2", "EXT22", "EXT22"],
        "idcategory": ["5", "5", "9", "9"],
        "defaultcategory": ["GROCERIES", "GROCERIES", "DINING", "DINING"],
        "period_yyyymm": ["2025-01", "2025-03", "2025-01", "2025-02"],
        "monthly_total": [100.0, 80.0, 50.0, 60.0],
    })
    result = zero_fill(df)
    assert "idmember" in result.columns
    # Expected: 2 members × 2 categories × 3 months = 12
    assert len(result) == 2 * 2 * 3


# ---------------------------------------------------------------------------
# TC-T3-4 (DATA-1179): apply_gating groups by (idclient, idcompany, idmember) — not idaccount
# ---------------------------------------------------------------------------

def test_TC_T3_4_apply_gating_uses_idmember_grain():
    """Arrange: idmember=10, idcompany=1, 2 accounts (EXT2, SUB8406),
       both with 3 months of spend in same category.
    Act: apply_gating(df, min_months=2)
    Assert: result has 1 unique (idclient, idcompany, idmember, category), not 2
    """
    # Build 2 accounts × 3 months for same idmember and category
    rows = []
    for account in ["EXT2", "SUB8406"]:
        for period in ["2025-01", "2025-02", "2025-03"]:
            rows.append({
                "idclient": "C1",
                "idcompany": "CO1",
                "idmember": 10,
                "idaccount": account,
                "idcategory": "5",
                "defaultcategory": "GROCERIES",
                "period_yyyymm": period,
                "monthly_total": 100.0,
            })
    df = pd.DataFrame(rows)

    result = apply_gating(df, min_months=2)

    # Should have 1 unique (idclient, idcompany, idmember, defaultcategory) bucket
    unique_buckets = result[["idclient", "idcompany", "idmember", "defaultcategory"]].drop_duplicates()
    assert len(unique_buckets) == 1, (
        f"Expected 1 unique (idclient, idcompany, idmember, category) bucket, got {len(unique_buckets)}"
    )


# ---------------------------------------------------------------------------
# TC-T3-5 (DATA-1179): apply_gating does NOT mix idmember=10 from idcompany=1 with idmember=10 from idcompany=2
# ---------------------------------------------------------------------------

def test_TC_T3_5_apply_gating_prevents_cross_company_mixing():
    """Arrange: idmember=10/idcompany=1 (4 months) + idmember=10/idcompany=2 (1 month).
    Act: apply_gating(df, min_months=2)
    Assert: only idmember=10/idcompany=1 passes gating; idmember=10/idcompany=2 excluded.
    """
    rows = []
    # Company 1: 4 months of data
    for period in ["2025-01", "2025-02", "2025-03", "2025-04"]:
        rows.append({
            "idclient": "C1",
            "idcompany": "CO1",
            "idmember": 10,
            "idaccount": "EXT2",
            "idcategory": "5",
            "defaultcategory": "GROCERIES",
            "period_yyyymm": period,
            "monthly_total": 100.0,
        })
    # Company 2: only 1 month (should NOT pass gating with min_months=2)
    rows.append({
        "idclient": "C1",
        "idcompany": "CO2",
        "idmember": 10,
        "idaccount": "EXT2",
        "idcategory": "5",
        "defaultcategory": "GROCERIES",
        "period_yyyymm": "2025-01",
        "monthly_total": 100.0,
    })
    df = pd.DataFrame(rows)

    result = apply_gating(df, min_months=2)

    # Only company CO1 should pass
    assert "CO1" in result["idcompany"].values
    assert "CO2" not in result["idcompany"].values, (
        "Cross-company mixing detected: idcompany=CO2 should not pass gating"
    )

