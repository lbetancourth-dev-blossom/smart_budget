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
    assert "alta confiabilidad" in result


def test_explanation_medium():
    from smart_budget.model import build_explanation
    result = build_explanation(4, 3, "medium")
    assert "3" in result
    assert "4" in result
    assert "confiabilidad media" in result


def test_explanation_low():
    from smart_budget.model import build_explanation
    result = build_explanation(3, 2, "low")
    assert "2" in result
    assert "3" in result
    assert "pocos datos" in result


def test_explanation_none():
    from smart_budget.model import build_explanation
    result = build_explanation(0, 0, None)
    assert result == "No hay datos históricos suficientes para calcular una sugerencia en esta categoría."


def test_explanation_no_prescriptive_words():
    from smart_budget.model import build_explanation
    for confidence in ("high", "medium", "low"):
        result = build_explanation(6, 4, confidence)
        for forbidden in ("deberías", "tienes que", "te conviene", "más que"):
            assert forbidden not in result, f"Found forbidden word '{forbidden}' in: {result}"


# ---------------------------------------------------------------------------
# T1.7 — compute_budget_suggestions (TC-4.x)
# ---------------------------------------------------------------------------

def _make_budget_df(idaccount, idcategory, defaultcategory, idclient, idcompany, periods, monthly_totals):
    """Helper: build a minimal compute_budget_suggestions-compatible df."""
    return pd.DataFrame({
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
        idaccount="M1",
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
        idaccount="M1",
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
        idaccount="M1",
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
        idaccount="M1",
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
    assert r["reason"] == "No hay suficiente historial para calcular el monto sugerido"
    assert r["display_label"] == "No hay suficiente historial para esta categoría"


def test_TC4_5_confidence_levels():
    """TC-4.5: confidence levels — high (>=6), medium (3-5), low (2)."""
    from smart_budget.model import compute_budget_suggestions

    # (a) 6 months all > 0 → high
    df_a = _make_budget_df(
        "M1", "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"],
        [100, 110, 120, 130, 140, 150],
    )
    res_a = compute_budget_suggestions(df_a, "wma", "A", "2026-03-01")
    assert res_a[0]["confidence"] == "high"

    # (b) 4 months > 0, 1 month zero → 4 months_with_positive_spend → medium
    df_b = _make_budget_df(
        "M1", "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01"],
        [100, 110, 120, 0, 130],
    )
    res_b = compute_budget_suggestions(df_b, "wma", "A", "2026-03-01")
    assert res_b[0]["confidence"] == "medium"

    # (c) 2 months > 0, 1 month zero → 2 months_with_positive_spend → low
    df_c = _make_budget_df(
        "M1", "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-11", "2025-12", "2026-01"],
        [100, 0, 150],
    )
    res_c = compute_budget_suggestions(df_c, "wma", "A", "2026-03-01")
    assert res_c[0]["confidence"] == "low"


def test_TC4_6_holt_winters_returns_float():
    """TC-4.6: holt_winters method returns non-negative float."""
    from smart_budget.model import compute_budget_suggestions
    df = _make_budget_df(
        "M1", "CAT1", "GROCERIES", "C1", "CO1",
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
        "M1", "CAT1", "GROCERIES", "C1", "CO1",
        periods,
        monthly_totals,
    )
    results = compute_budget_suggestions(df, "wma", "A", "2025-06-01")
    assert len(results) == 1
    assert results[0]["basis"]["months_analyzed"] == 6


def test_TC4_8_json_contract_fields():
    """TC-4.8: output dict contains exactly required fields; reason absent when suggested_amount != None."""
    from smart_budget.model import compute_budget_suggestions
    df = _make_budget_df(
        "M1", "CAT1", "GROCERIES", "C1", "CO1",
        ["2025-10", "2025-11", "2025-12", "2026-01"],
        [100, 110, 120, 130],
    )
    results = compute_budget_suggestions(df, "wma", "A", "2026-03-01")
    assert len(results) == 1
    r = results[0]

    required_fields = {
        "category_id", "defaultcategory", "idaccount", "idclient", "idcompany",
        "suggested_amount", "basis", "confidence", "display_label", "explanation",
        "model_version",
    }
    assert set(r.keys()) == required_fields, f"Unexpected keys: {set(r.keys()) - required_fields}, missing: {required_fields - set(r.keys())}"

    # reason NOT present when suggested_amount is not None
    assert "reason" not in r

    # explanation is a non-empty string containing months_with_positive_spend
    assert isinstance(r["explanation"], str)
    assert len(r["explanation"]) > 0
    mwps = str(r["basis"]["months_with_positive_spend"])
    assert mwps in r["explanation"]


# ---------------------------------------------------------------------------
# T3.1 — Golden set
# ---------------------------------------------------------------------------

def test_TC4_golden_set_matches_output():
    """TC-4.8 golden: WMA/A/2026-03-01 output matches committed golden_set.csv exactly."""
    import pathlib
    import pandas as pd

    from tests.conftest import _load_fixture
    from smart_budget.aggregator import apply_gating
    from smart_budget.model import compute_budget_suggestions

    golden = _load_fixture("golden_set.csv")
    golden["suggested_amount"] = golden["suggested_amount"].astype(float)

    # Load source data and apply gating
    data_path = pathlib.Path(__file__).parent.parent.parent / "data" / "dough" / "smart_budget_synthetic.csv"
    raw_df = pd.read_csv(data_path)
    prepared_df = apply_gating(raw_df, min_months=3)

    results = compute_budget_suggestions(prepared_df, method="wma", treatment="A", reference_date="2026-03-01")
    results_map = {
        (r["idaccount"], r["category_id"], r["defaultcategory"]): r["suggested_amount"]
        for r in results
    }

    for _, row in golden.iterrows():
        key = (row["idaccount"], row["category_id"], row["defaultcategory"])
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
