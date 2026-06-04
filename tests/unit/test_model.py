"""tests/unit/test_model.py — TDD tests for src/smart_budget/model.py (DATA-1137)."""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# T1.1 — Module importable
# ---------------------------------------------------------------------------

def test_module_importable():
    """TC-1.1: compute_budget_suggestions is importable from smart_budget.model."""
    from smart_budget.model import compute_budget_suggestions  # noqa: F401


# ---------------------------------------------------------------------------
# T1.2 — apply_treatment
# ---------------------------------------------------------------------------

def _make_df(monthly_totals):
    """Helper: build minimal df with monthly_total column."""
    return pd.DataFrame({"monthly_total": monthly_totals})


def test_apply_treatment_A_unchanged():
    """Treatment A: df is returned unchanged (include zeros)."""
    from smart_budget.model import apply_treatment
    df = _make_df([100, 0, 50])
    result = apply_treatment(df, "A")
    assert list(result["monthly_total"]) == [100, 0, 50]


def test_apply_treatment_B_excludes_zeros():
    """Treatment B: rows where monthly_total == 0 are removed."""
    from smart_budget.model import apply_treatment
    df = _make_df([100, 0, 50])
    result = apply_treatment(df, "B")
    assert list(result["monthly_total"]) == [100, 50]
    assert len(result) == 2


def test_apply_treatment_C_replaces_zeros():
    """Treatment C: monthly_total == 0 replaced by epsilon (default 0.01)."""
    from smart_budget.model import apply_treatment
    df = _make_df([100, 0, 50])
    result = apply_treatment(df, "C")
    assert list(result["monthly_total"]) == [100, 0.01, 50]


def test_apply_treatment_invalid_raises():
    """Treatment 'X' raises ValueError."""
    from smart_budget.model import apply_treatment
    df = _make_df([100, 0, 50])
    with pytest.raises(ValueError):
        apply_treatment(df, "X")


def test_apply_treatment_does_not_mutate_original():
    """apply_treatment never mutates the original dataframe."""
    from smart_budget.model import apply_treatment
    df = _make_df([100, 0, 50])
    original_values = list(df["monthly_total"])
    apply_treatment(df, "B")
    apply_treatment(df, "C")
    assert list(df["monthly_total"]) == original_values


# ---------------------------------------------------------------------------
# T1.3 — compute_wma
# ---------------------------------------------------------------------------

def test_compute_wma_3_months():
    """WMA with weights [1,2,3] → (100*1+200*2+300*3)/6 = 233.33."""
    from smart_budget.model import compute_wma
    result = compute_wma(pd.Series([100, 200, 300]))
    assert result == 233.33


def test_compute_wma_single_value():
    """WMA of single-element series returns that value."""
    from smart_budget.model import compute_wma
    result = compute_wma(pd.Series([150]))
    assert result == 150.0


def test_compute_wma_empty_raises():
    """WMA of empty series raises ValueError."""
    from smart_budget.model import compute_wma
    with pytest.raises(ValueError):
        compute_wma(pd.Series([], dtype=float))


def test_compute_wma_with_zeros():
    """WMA [0, 0, 100] → (0+0+300)/6 = 50.0."""
    from smart_budget.model import compute_wma
    result = compute_wma(pd.Series([0, 0, 100]))
    assert result == 50.0


# ---------------------------------------------------------------------------
# T1.4 — compute_ewma
# ---------------------------------------------------------------------------

def test_compute_ewma_known_series():
    """EWMA matches pandas ewm(span=3, adjust=False).mean().iloc[-1]."""
    from smart_budget.model import compute_ewma
    series = pd.Series([100, 200, 300])
    expected = round(series.ewm(span=3, adjust=False).mean().iloc[-1], 2)
    result = compute_ewma(series, span=3)
    assert result == expected


def test_compute_ewma_single_value():
    """EWMA of single-element series returns that value."""
    from smart_budget.model import compute_ewma
    result = compute_ewma(pd.Series([250]), span=3)
    assert result == 250.0


def test_compute_ewma_empty_raises():
    """EWMA of empty series raises ValueError."""
    from smart_budget.model import compute_ewma
    with pytest.raises(ValueError):
        compute_ewma(pd.Series([], dtype=float))


def test_compute_ewma_non_negative():
    """EWMA of all-zero series returns 0.0 (never negative)."""
    from smart_budget.model import compute_ewma
    result = compute_ewma(pd.Series([0, 0, 0]), span=3)
    assert result == 0.0


# ---------------------------------------------------------------------------
# T1.5 — compute_holt_winters
# ---------------------------------------------------------------------------

def test_compute_holt_winters_6_months():
    """Holt-Winters forecast for 6-month positive series is a reasonable float."""
    from smart_budget.model import compute_holt_winters
    result = compute_holt_winters(pd.Series([100, 110, 105, 120, 115, 130]))
    assert isinstance(result, float)
    assert result >= 0
    assert result <= 200  # not more than 2× the max of the series (130*2=260, capped at 200 per spec)


def test_compute_holt_winters_below_min_raises():
    """Holt-Winters with fewer than 3 observations raises ValueError."""
    from smart_budget.model import compute_holt_winters
    with pytest.raises(ValueError):
        compute_holt_winters(pd.Series([100, 200]))


def test_compute_holt_winters_clamps_negative():
    """If ExponentialSmoothing forecast is negative, result is clamped to 0.0."""
    from smart_budget.model import compute_holt_winters
    with patch("statsmodels.tsa.holtwinters.ExponentialSmoothing") as mock_es:
        mock_fit = MagicMock()
        mock_fit.forecast.return_value = pd.Series([-5.0])
        mock_es.return_value.fit.return_value = mock_fit
        result = compute_holt_winters(pd.Series([100, 200, 300]))
    assert result == 0.0


def test_compute_holt_winters_with_zeros():
    """Holt-Winters with mixed zeros/positives returns float > 0 (series has positive values)."""
    from smart_budget.model import compute_holt_winters
    result = compute_holt_winters(pd.Series([100, 0, 80, 0, 90, 0]))
    assert isinstance(result, float)
    assert result >= 0.0
    # series has positive values, forecast should not be exactly 0
    assert result != 0.0


# ---------------------------------------------------------------------------
# T1.6 — compute_confidence + build_explanation
# ---------------------------------------------------------------------------

def test_confidence_high():
    from smart_budget.model import compute_confidence
    assert compute_confidence(6) == "high"


def test_confidence_high_8():
    from smart_budget.model import compute_confidence
    assert compute_confidence(8) == "high"


def test_confidence_medium_3():
    from smart_budget.model import compute_confidence
    assert compute_confidence(3) == "medium"


def test_confidence_medium_5():
    from smart_budget.model import compute_confidence
    assert compute_confidence(5) == "medium"


def test_confidence_low():
    from smart_budget.model import compute_confidence
    assert compute_confidence(2) == "low"


def test_explanation_high():
    from smart_budget.model import build_explanation
    result = build_explanation(6, 4, "high")
    assert "4" in result
    assert "6" in result
    assert "high confidence" in result


def test_explanation_medium():
    from smart_budget.model import build_explanation
    result = build_explanation(4, 3, "medium")
    assert "3" in result
    assert "4" in result
    assert "medium confidence" in result


def test_explanation_low():
    from smart_budget.model import build_explanation
    result = build_explanation(3, 2, "low")
    assert "2" in result
    assert "3" in result
    assert "limited data" in result


def test_explanation_none():
    from smart_budget.model import build_explanation
    result = build_explanation(0, 0, None)
    assert result == "Not enough historical data to calculate a suggestion for this category."


def test_explanation_no_prescriptive_words():
    from smart_budget.model import build_explanation
    for confidence in ("high", "medium", "low"):
        result = build_explanation(6, 4, confidence)
        for forbidden in ("deberías", "tienes que", "te conviene", "más que"):
            assert forbidden not in result, f"Found forbidden word '{forbidden}' in: {result}"


# ---------------------------------------------------------------------------
# T1.7 — compute_budget_suggestions (TC-4.x)
# ---------------------------------------------------------------------------

def _make_budget_df(idmember, idcategory, defaultcategory, idclient, idcompany, periods, monthly_totals, idaccount=None):
    """Helper: build a minimal compute_budget_suggestions-compatible df."""
    if idaccount is None:
        idaccount = f"EXT{idmember}" if isinstance(idmember, (int, str)) else "EXT_UNKNOWN"
    return pd.DataFrame({
        "idmember": idmember,
        "idaccount": idaccount,
        "idcategory": idcategory,
        "defaultcategory": defaultcategory,
        "idclient": idclient,
        "idcompany": idcompany,
        "period_yyyymm": periods,
        "monthly_total": monthly_totals,
    })


def test_TC4_1_wma_treatment_A_includes_zeros():
    """TC-4.1: WMA/A — zeros included, basis counts correct."""
    from smart_budget.model import compute_budget_suggestions, compute_wma
    df = _make_budget_df(
        idmember=1,
        idcategory="CAT1",
        defaultcategory="GROCERIES",
        idclient="C1",
        idcompany="CO1",
        periods=["2025-11", "2025-12", "2026-01", "2026-02"],
        monthly_totals=[100, 0, 200, 150],
    )
    results = compute_budget_suggestions(df, "wma", "A", "2026-03-01")
    assert len(results) == 1
    r = results[0]
    expected = compute_wma(pd.Series([100, 0, 200, 150]))
    assert r["suggested_amount"] == expected
    assert r["basis"]["months_with_zero"] == 1
    assert r["basis"]["months_with_positive_spend"] == 3


def test_TC4_2_wma_treatment_B_excludes_zeros():
    """TC-4.2: WMA/B — zeros excluded from calculation, basis PRE-treatment."""
    from smart_budget.model import compute_budget_suggestions, compute_wma
    df = _make_budget_df(
        idmember=1,
        idcategory="CAT1",
        defaultcategory="GROCERIES",
        idclient="C1",
        idcompany="CO1",
        periods=["2025-11", "2025-12", "2026-01", "2026-02"],
        monthly_totals=[100, 0, 200, 150],
    )
    results = compute_budget_suggestions(df, "wma", "B", "2026-03-01")
    assert len(results) == 1
    r = results[0]
    expected = compute_wma(pd.Series([100, 200, 150]))
    assert r["suggested_amount"] == expected
    assert r["basis"]["months_with_zero"] == 1  # PRE-treatment
    assert r["basis"]["months_with_positive_spend"] == 3  # PRE-treatment


def test_TC4_3_treatment_C_epsilon_replace():
    """TC-4.3: treatment C replaces zeros with epsilon; basis reflects PRE-treatment."""
    from smart_budget.model import compute_budget_suggestions, compute_wma, EPSILON_DEFAULT
    df = _make_budget_df(
        idmember=1,
        idcategory="CAT1",
        defaultcategory="GROCERIES",
        idclient="C1",
        idcompany="CO1",
        periods=["2025-11", "2025-12", "2026-01", "2026-02"],
        monthly_totals=[100, 0, 200, 150],
    )
    results = compute_budget_suggestions(df, "wma", "C", "2026-03-01")
    assert len(results) == 1
    r = results[0]
    expected = compute_wma(pd.Series([100, EPSILON_DEFAULT, 200, 150]))
    assert r["suggested_amount"] == expected
    assert r["basis"]["months_with_zero"] == 1  # PRE-treatment


def test_TC4_4_treatment_B_all_zeros_returns_null():
    """TC-4.4: treatment B with all-zero bucket returns null suggestion."""
    from smart_budget.model import compute_budget_suggestions
    df = _make_budget_df(
        idmember=1,
        idcategory="5",
        defaultcategory="GROCERIES",
        idclient="C1",
        idcompany="CO1",
        periods=["2025-10", "2025-11", "2025-12"],
        monthly_totals=[0.0, 0.0, 0.0],
    )
    results = compute_budget_suggestions(df, "wma", "B", "2026-03-01")
    assert len(results) == 1
    r = results[0]
    assert r["suggested_amount"] is None
    assert r["reason"] == "Not enough history to calculate a suggested amount"
    assert r["display_label"] == "Not enough history for this category"


def test_TC4_5_confidence_levels():
    """TC-4.5: confidence levels — high (>=6), medium (3-5), low (2)."""
    from smart_budget.model import compute_budget_suggestions

    # (a) 6 months all > 0 → high
    df_a = _make_budget_df(
        1, "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"],
        [100, 110, 120, 130, 140, 150],
    )
    res_a = compute_budget_suggestions(df_a, "wma", "A", "2026-03-01")
    assert res_a[0]["confidence"] == "high"

    # (b) 4 months > 0, 1 month zero → 4 months_with_positive_spend → medium
    df_b = _make_budget_df(
        1, "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01"],
        [100, 110, 120, 0, 130],
    )
    res_b = compute_budget_suggestions(df_b, "wma", "A", "2026-03-01")
    assert res_b[0]["confidence"] == "medium"

    # (c) 2 months > 0, 1 month zero → 2 months_with_positive_spend → low
    df_c = _make_budget_df(
        1, "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-11", "2025-12", "2026-01"],
        [100, 0, 150],
    )
    res_c = compute_budget_suggestions(df_c, "wma", "A", "2026-03-01")
    assert res_c[0]["confidence"] == "low"


def test_TC4_6_holt_winters_returns_float():
    """TC-4.6: holt_winters method returns non-negative float."""
    from smart_budget.model import compute_budget_suggestions
    df = _make_budget_df(
        1, "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"],
        [100, 110, 120, 130, 140, 150],
    )
    results = compute_budget_suggestions(df, "holt_winters", "A", "2026-03-01")
    assert len(results) == 1
    assert isinstance(results[0]["suggested_amount"], float)
    assert results[0]["suggested_amount"] >= 0.0


def test_TC4_7_reference_date_cutoff():
    """TC-4.7: only months <= month(reference_date) are included."""
    from smart_budget.model import compute_budget_suggestions
    # 15 months from 2025-01 to 2026-03, but reference_date = 2025-06-01
    # → only months 2025-01 through 2025-06 (6 months)
    periods = [f"2025-{m:02d}" for m in range(1, 7)] + [f"2025-{m:02d}" for m in range(7, 13)] + ["2026-01", "2026-02", "2026-03"]
    monthly_totals = [100] * 6 + [200] * 6 + [300] * 3
    df = _make_budget_df(
        1, "CAT1", "GROCERIES", "C1", "CO1",
        periods,
        monthly_totals,
    )
    results = compute_budget_suggestions(df, "wma", "A", "2025-06-01")
    assert len(results) == 1
    assert results[0]["basis"]["months_analyzed"] == 6


def test_TC4_8_json_contract_fields():
    """TC-4.8 (updated DATA-1179): output dict contains idmember + total_suggested; NOT idaccount."""
    from smart_budget.model import compute_budget_suggestions
    df = _make_budget_df(
        idmember=10,
        idcategory="CAT1",
        defaultcategory="GROCERIES",
        idclient="C1",
        idcompany="CO1",
        periods=["2025-10", "2025-11", "2025-12", "2026-01"],
        monthly_totals=[100, 110, 120, 130],
    )
    results = compute_budget_suggestions(df, "wma", "A", "2026-03-01")
    assert len(results) == 1
    r = results[0]

    required_fields = {
        "category_id", "defaultcategory", "idmember", "idclient", "idcompany",
        "suggested_amount", "basis", "confidence", "display_label", "explanation",
        "model_version", "total_suggested",
    }
    assert set(r.keys()) == required_fields, (
        f"Unexpected keys: {set(r.keys()) - required_fields}, "
        f"missing: {required_fields - set(r.keys())}"
    )
    # idaccount must NOT be in the output
    assert "idaccount" not in r
    # idmember must be present
    assert "idmember" in r
    # total_suggested must be present
    assert "total_suggested" in r

    # reason NOT present when suggested_amount is not None
    assert "reason" not in r

    # explanation is a non-empty string containing months_with_positive_spend
    assert isinstance(r["explanation"], str)
    assert len(r["explanation"]) > 0
    mwps = str(r["basis"]["months_with_positive_spend"])
    assert mwps in r["explanation"]


# ---------------------------------------------------------------------------
# TC-T4-1 (DATA-1179): _null_suggestion contains idmember (not idaccount)
# ---------------------------------------------------------------------------

def test_TC_T4_1_null_suggestion_has_idmember_not_idaccount():
    """TC-T4-1: _null_suggestion contains idmember field, NOT idaccount.
    Arrange: bucket_meta with idmember="10", idcategory="cat1", etc.
    Act: _null_suggestion(bucket_meta)
    Assert: "idmember" in result AND "idaccount" not in result AND result["idmember"] == "10"
    """
    from smart_budget.model import _null_suggestion

    bucket_meta = {
        "idmember": "10",
        "idcategory": "cat1",
        "defaultcategory": "GROCERIES",
        "idclient": "C1",
        "idcompany": "CO1",
    }
    result = _null_suggestion(bucket_meta)
    assert "idmember" in result
    assert "idaccount" not in result
    assert result["idmember"] == "10"


# ---------------------------------------------------------------------------
# TC-T4-3 (DATA-1179): total_suggested is sum of non-null suggested_amounts
# ---------------------------------------------------------------------------

def test_TC_T4_3_total_suggested_is_sum_of_non_null():
    """TC-T4-3: idmember=10, 3 categories with suggested=[100.0, 50.0, None].
    Assert: results[0]["total_suggested"] == 150.0
    Assert: results[1]["total_suggested"] == 150.0 (same member)
    Assert: results[2]["total_suggested"] == 150.0 (null doesn't sum)
    """
    from smart_budget.model import compute_budget_suggestions

    # Category 1: 3 months of data → will produce suggestion
    # Category 2: 3 months of data → will produce suggestion
    # Category 3: all zeros → treatment B → null suggestion
    rows = []
    for cat, totals in [
        ("CAT1", [100.0, 80.0, 120.0]),
        ("CAT2", [40.0, 60.0, 50.0]),
        ("CAT3", [0.0, 0.0, 0.0]),  # all zeros → null with treatment B
    ]:
        for period, total in zip(["2025-10", "2025-11", "2025-12"], totals):
            rows.append({
                "idmember": 10,
                "idaccount": "EXT10",
                "idcategory": cat,
                "defaultcategory": cat,
                "idclient": "C1",
                "idcompany": "CO1",
                "period_yyyymm": period,
                "monthly_total": total,
            })

    df = pd.DataFrame(rows)
    results = compute_budget_suggestions(df, "wma", "B", "2026-03-01")
    assert len(results) == 3

    # Compute expected total (sum of non-null suggested amounts)
    non_null_amounts = [r["suggested_amount"] for r in results if r["suggested_amount"] is not None]
    expected_total = sum(non_null_amounts)

    for r in results:
        assert r["total_suggested"] == expected_total, (
            f"Expected total_suggested={expected_total}, got {r['total_suggested']}"
        )


# ---------------------------------------------------------------------------
# TC-T4-4 (DATA-1179): total_suggested == 0.0 when all categories are null
# ---------------------------------------------------------------------------

def test_TC_T4_4_total_suggested_zero_when_all_null():
    """TC-T4-4: member with only all-zero data → treatment B → null suggestion.
    Assert: result["total_suggested"] == 0.0 (float, never None)
    """
    from smart_budget.model import compute_budget_suggestions

    df = _make_budget_df(
        idmember=10,
        idcategory="5",
        defaultcategory="GROCERIES",
        idclient="C1",
        idcompany="CO1",
        periods=["2025-10", "2025-11", "2025-12"],  # 3 months, all zero → treatment B → null
        monthly_totals=[0.0, 0.0, 0.0],
        idaccount="EXT10",
    )
    results = compute_budget_suggestions(df, "wma", "B", "2026-03-01")
    assert len(results) == 1
    r = results[0]
    assert r["suggested_amount"] is None
    assert r["total_suggested"] == 0.0, (
        f"Expected total_suggested=0.0 when all suggestions null, got {r['total_suggested']}"
    )
    assert isinstance(r["total_suggested"], float), "total_suggested must be float, not None"


# ---------------------------------------------------------------------------
# TC-T4-5 (DATA-1179): two idmembers have independent total_suggested
# ---------------------------------------------------------------------------

def test_TC_T4_5_two_members_have_independent_total_suggested():
    """TC-T4-5: idmember=10 with suggested=~200, idmember=20 with suggested=~300.
    Assert: results of member 10 have total_suggested ≠ results of member 20.
    """
    from smart_budget.model import compute_budget_suggestions

    # Member 10: one category, 3 months ~200 each
    rows_10 = [
        {"idmember": 10, "idaccount": "EXT10", "idcategory": "CAT1", "defaultcategory": "GROCERIES",
         "idclient": "C1", "idcompany": "CO1", "period_yyyymm": p, "monthly_total": v}
        for p, v in zip(["2025-10", "2025-11", "2025-12"], [180.0, 200.0, 220.0])
    ]
    # Member 20: one category, 3 months ~300 each
    rows_20 = [
        {"idmember": 20, "idaccount": "EXT20", "idcategory": "CAT1", "defaultcategory": "GROCERIES",
         "idclient": "C1", "idcompany": "CO1", "period_yyyymm": p, "monthly_total": v}
        for p, v in zip(["2025-10", "2025-11", "2025-12"], [280.0, 300.0, 320.0])
    ]

    df = pd.DataFrame(rows_10 + rows_20)
    results = compute_budget_suggestions(df, "wma", "A", "2026-03-01")
    assert len(results) == 2

    m10_results = [r for r in results if r["idmember"] == "10"]
    m20_results = [r for r in results if r["idmember"] == "20"]
    assert len(m10_results) == 1
    assert len(m20_results) == 1

    ts_10 = m10_results[0]["total_suggested"]
    ts_20 = m20_results[0]["total_suggested"]

    # total_suggested should be different for different members
    assert ts_10 != ts_20, (
        f"Members should have different total_suggested: member 10={ts_10}, member 20={ts_20}"
    )
    # Member 20 has higher spend → higher total_suggested
    assert ts_20 > ts_10


# ---------------------------------------------------------------------------
# T3.1 — Golden set (updated for DATA-1179 schema)
# ---------------------------------------------------------------------------

def test_TC4_golden_set_matches_output():
    """TC-4.8 golden (updated DATA-1179): WMA/A/2026-03-01 output matches golden_set.csv."""
    import pathlib
    import pandas as pd

    from tests.conftest import _load_fixture
    from smart_budget.aggregator import apply_gating
    from smart_budget.model import compute_budget_suggestions

    golden = _load_fixture("golden_set.csv")
    golden["suggested_amount"] = golden["suggested_amount"].astype(float)

    # Load source data and apply gating
    data_path = pathlib.Path(__file__).parent.parent.parent / "data" / "dough" / "smart_budget_synthetic.csv"
    if not data_path.exists():
        pytest.skip(f"Synthetic data file not found: {data_path} — run generate_golden_set.py first")
    raw_df = pd.read_csv(data_path)
    prepared_df = apply_gating(raw_df, min_months=3)

    results = compute_budget_suggestions(prepared_df, method="wma", treatment="A", reference_date="2026-03-01")

    # Build lookup: use idmember if available, otherwise idaccount
    if "idmember" in golden.columns:
        results_map = {
            (str(r["idmember"]), r["category_id"], r["defaultcategory"]): r["suggested_amount"]
            for r in results
        }
        for _, row in golden.iterrows():
            key = (str(row["idmember"]), row["category_id"], row["defaultcategory"])
            assert key in results_map, f"Bucket {key} missing from output"
            expected = float(row["suggested_amount"])
            actual = results_map[key]
            assert actual == expected, (
                f"Bucket {key}: expected {expected}, got {actual}"
            )
    else:
        # Legacy golden set without idmember
        results_map = {
            (r["idmember"], r["category_id"], r["defaultcategory"]): r["suggested_amount"]
            for r in results
        }
        for _, row in golden.iterrows():
            key = (row.get("idaccount", row.get("idmember")), row["category_id"], row["defaultcategory"])
            assert key in results_map, f"Bucket {key} missing from output"
            expected = float(row["suggested_amount"])
            actual = results_map[key]
            assert actual == expected, (
                f"Bucket {key}: expected {expected}, got {actual}"
            )


def test_run_methods_importable():
    """scripts/run_methods.py is parseable (no ImportError or SyntaxError)."""
    import runpy
    with pytest.raises(SystemExit):
        runpy.run_path("scripts/run_methods.py", run_name="__test__")
