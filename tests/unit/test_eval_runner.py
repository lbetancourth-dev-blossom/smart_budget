"""tests/unit/test_eval_runner.py — TDD tests for scripts/eval_runner.py (DATA-1138)."""

from __future__ import annotations

import io
import pathlib
import sys

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Module import helper — scripts/ is not on sys.path by default
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = str(pathlib.Path(__file__).parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_actuals_df(
    members=None,
    category_ids=None,
    defaultcategories=None,
    monthly_totals=None,
    accounts=None,
):
    """Build a minimal actuals_df with the 4 required columns."""
    # Acepta 'accounts' como alias de 'members' para compatibilidad con llamadas anteriores
    effective_members = accounts if accounts is not None else members
    return pd.DataFrame(
        {
            "idmember": effective_members,
            "category_id": category_ids,
            "category_name": defaultcategories,
            "monthly_total": monthly_totals,
        }
    )


def _make_suggestion(
    idmember: str,
    category_id: str,
    category_name: str,
    suggested_amount,
) -> dict:
    """Build a minimal suggestion dict matching model.py output structure."""
    return {
        "idmember": idmember,
        "category_id": category_id,
        "category_name": category_name,
        "suggested_amount": suggested_amount,
        "idclient": "cli1",
        "idcompany": "co1",
    }


def _make_test_train_df() -> pd.DataFrame:
    """
    Minimal 3-account × 3-category × 12-month train DataFrame (already gated).

    Structure:
      - 3 accounts: acc1, acc2, acc3
      - 3 categories: cat1/Food & Dining, cat2/Gas, cat3/Travel & Trips
      - 12 months: 2025-01 to 2025-12
      - acc1/cat1 has zeros in Oct and Nov 2025 so that HW with lb=3
        (window: Oct/Nov/Dec) after treatment B returns only [100] → ValueError → null.
      - All other buckets are all-positive in the full window.
    """
    accounts = ["acc1", "acc2", "acc3"]
    categories = [
        ("cat1", "Food & Dining"),
        ("cat2", "Gas"),
        ("cat3", "Travel & Trips"),
    ]
    months = [f"2025-{m:02d}" for m in range(1, 13)]

    records = []
    for acc in accounts:
        for cat_id, cat_name in categories:
            for i, month in enumerate(months):
                # acc1/cat1: Oct (i=9) and Nov (i=10) are zero; Dec (i=11) is positive
                if acc == "acc1" and cat_id == "cat1" and i in (9, 10):
                    value = 0.0
                else:
                    value = 100.0
                records.append(
                    {
                        "idclient": "cli1",
                        "idcompany": "co1",
                        "idmember": acc,
                        "idaccount": acc,
                        "category_id": cat_id,
                        "category_name": cat_name,
                        "period_yyyymm": month,
                        "monthly_total": value,
                    }
                )
    return pd.DataFrame(records)


def _make_test_actuals_df() -> pd.DataFrame:
    """9 actuals rows — one per (member × category) bucket in _make_test_train_df."""
    members = ["acc1", "acc2", "acc3"]
    categories = [
        ("cat1", "Food & Dining"),
        ("cat2", "Gas"),
        ("cat3", "Travel & Trips"),
    ]
    records = []
    for mem in members:
        for cat_id, cat_name in categories:
            records.append(
                {
                    "idmember": mem,
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "monthly_total": 150.0,
                }
            )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# T4 — Module importable
# ---------------------------------------------------------------------------


def test_module_importable():
    """eval_runner module imports without error and without running main()."""
    import eval_runner  # noqa: F401


# ---------------------------------------------------------------------------
# T1 — compute_metrics tests
# ---------------------------------------------------------------------------


def test_compute_metrics_basic_mae():
    """3 buckets, all non-null. MAE = mean([20, 20, 60]) = 33.33."""
    from eval_runner import compute_metrics

    suggestions = [
        _make_suggestion("A1", "1", "Food & Dining", 100.0),
        _make_suggestion("A1", "2", "Gas", 200.0),
        _make_suggestion("A1", "3", "Groceries", 300.0),
    ]
    actuals_df = _make_actuals_df(
        accounts=["A1", "A1", "A1"],
        category_ids=["1", "2", "3"],
        defaultcategories=["Food & Dining", "Gas", "Groceries"],
        monthly_totals=[120.0, 180.0, 360.0],
    )

    metrics = compute_metrics(suggestions, actuals_df)

    # Errors: |100-120|=20, |200-180|=20, |300-360|=60 → MAE = 100/3 = 33.33
    assert metrics["accuracy_delta"] == pytest.approx(33.33, abs=0.01)
    assert metrics["n_evaluated"] == 3


def test_compute_metrics_null_excluded_from_mae():
    """2 non-null + 1 null suggestion. Only the 2 non-null are in MAE denominator."""
    from eval_runner import compute_metrics

    suggestions = [
        _make_suggestion("A1", "1", "Food & Dining", 100.0),
        _make_suggestion("A1", "2", "Gas", None),
        _make_suggestion("A1", "3", "Groceries", 300.0),
    ]
    actuals_df = _make_actuals_df(
        accounts=["A1", "A1", "A1"],
        category_ids=["1", "2", "3"],
        defaultcategories=["Food & Dining", "Gas", "Groceries"],
        monthly_totals=[120.0, 200.0, 360.0],
    )

    metrics = compute_metrics(suggestions, actuals_df)

    assert metrics["n_evaluated"] == 2
    assert metrics["null_rate"] == pytest.approx(33.33, abs=0.01)
    # MAE over 2 buckets: |100-120|=20, |300-360|=60 → mean = 40.0
    assert metrics["accuracy_delta"] == pytest.approx(40.0, abs=0.01)


def test_compute_metrics_mape_excludes_zero_actuals():
    """MAPE = 50.0 when one actual is 0 (excluded from denominator)."""
    from eval_runner import compute_metrics

    suggestions = [
        _make_suggestion("A1", "1", "Travel & Trips", 0.0),
        _make_suggestion("A1", "2", "Gas", 100.0),
        _make_suggestion("A1", "3", "Groceries", 150.0),
    ]
    actuals_df = _make_actuals_df(
        accounts=["A1", "A1", "A1"],
        category_ids=["1", "2", "3"],
        defaultcategories=["Travel & Trips", "Gas", "Groceries"],
        monthly_totals=[0.0, 200.0, 300.0],
    )

    metrics = compute_metrics(suggestions, actuals_df)

    # MAPE = mean([|100-200|/200, |150-300|/300]) * 100 = mean([0.5, 0.5]) * 100 = 50.0
    assert metrics["mape"] == pytest.approx(50.0, abs=0.01)
    assert metrics["mape_n"] == 2


def test_compute_metrics_mape_all_zero_actuals():
    """If all actuals are 0, MAPE is None and mape_n is 0."""
    from eval_runner import compute_metrics

    suggestions = [
        _make_suggestion("A1", "1", "Food & Dining", 100.0),
        _make_suggestion("A1", "2", "Gas", 50.0),
    ]
    actuals_df = _make_actuals_df(
        accounts=["A1", "A1"],
        category_ids=["1", "2"],
        defaultcategories=["Food & Dining", "Gas"],
        monthly_totals=[0.0, 0.0],
    )

    metrics = compute_metrics(suggestions, actuals_df)

    assert metrics["mape"] is None
    assert metrics["mape_n"] == 0


def test_compute_metrics_coverage_rate():
    """coverage_rate = 67/73 * 100 ≈ 91.78%."""
    from eval_runner import compute_metrics

    n_total = 73
    n_non_null = 67

    # Build 73 unique suggestions (67 non-null, 6 null)
    suggestions = [
        _make_suggestion(f"A{i}", str(i), f"Cat{i}", 100.0 if i < n_non_null else None)
        for i in range(n_total)
    ]
    actuals_df = _make_actuals_df(
        accounts=[f"A{i}" for i in range(n_total)],
        category_ids=[str(i) for i in range(n_total)],
        defaultcategories=[f"Cat{i}" for i in range(n_total)],
        monthly_totals=[100.0] * n_total,
    )

    metrics = compute_metrics(suggestions, actuals_df)

    assert metrics["n_total_holdout"] == 73
    assert metrics["n_evaluated"] == 67
    assert metrics["coverage_rate"] == pytest.approx(91.78, abs=0.1)


def test_compute_metrics_seasonal_split():
    """mae_seasonal and mae_regular split by category type."""
    from eval_runner import compute_metrics

    suggestions = [
        _make_suggestion("A1", "1", "Travel & Trips", 500.0),
        _make_suggestion("A1", "2", "Gas", 60.0),
        _make_suggestion("A1", "3", "Food & Dining", 100.0),
    ]
    actuals_df = _make_actuals_df(
        accounts=["A1", "A1", "A1"],
        category_ids=["1", "2", "3"],
        defaultcategories=["Travel & Trips", "Gas", "Food & Dining"],
        monthly_totals=[600.0, 50.0, 120.0],
    )

    metrics = compute_metrics(
        suggestions,
        actuals_df,
        seasonal_categories={"Travel & Trips", "Gifts & Donations", "Education"},
    )

    # Travel error = |500-600| = 100 → mae_seasonal = 100.0
    assert metrics["mae_seasonal"] == pytest.approx(100.0, abs=0.01)
    assert metrics["n_seasonal"] == 1
    # Gas error = |60-50| = 10, Food error = |100-120| = 20 → mean = 15.0
    assert metrics["mae_regular"] == pytest.approx(15.0, abs=0.01)
    assert metrics["n_regular"] == 2


def test_compute_metrics_no_matching_actuals():
    """Suggestion with key not in actuals_df is silently skipped."""
    from eval_runner import compute_metrics

    suggestions = [
        _make_suggestion("A1", "99", "Unknown", 100.0),
        _make_suggestion("A1", "1", "Food & Dining", 200.0),
    ]
    actuals_df = _make_actuals_df(
        accounts=["A1"],
        category_ids=["1"],
        defaultcategories=["Food & Dining"],
        monthly_totals=[180.0],
    )

    metrics = compute_metrics(suggestions, actuals_df)

    # Only 1 matched bucket (idaccount=A1, category_id=1 matches idcategory=1)
    assert metrics["n_evaluated"] == 1
    assert metrics["n_total_holdout"] == 1


# ---------------------------------------------------------------------------
# T1 — _normalize_reference_date tests
# ---------------------------------------------------------------------------


def test_normalize_reference_date_valid():
    """'2026-03' → '2026-03'."""
    from eval_runner import _normalize_reference_date

    assert _normalize_reference_date("2026-03") == "2026-03"


def test_normalize_reference_date_with_day():
    """'2026-03-01' → '2026-03'."""
    from eval_runner import _normalize_reference_date

    assert _normalize_reference_date("2026-03-01") == "2026-03"


def test_normalize_reference_date_invalid_raises():
    """'bad' → raises ValueError."""
    from eval_runner import _normalize_reference_date

    with pytest.raises(ValueError):
        _normalize_reference_date("bad")


# ---------------------------------------------------------------------------
# T1 — load_and_split tests (skip if CSV not present)
# ---------------------------------------------------------------------------

_DATA_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "data"
    / "dough"
    / "smart_budget_synthetic.csv"
)


def test_load_and_split_returns_correct_shapes():
    """
    Load smart_budget_synthetic.csv; actuals should have 73 rows (Apr2026 holdout).
    Skips gracefully if file not present.
    """
    if not _DATA_PATH.exists():
        pytest.skip("smart_budget_synthetic.csv not present — run outside CI")

    from eval_runner import load_and_split

    train_df, actuals_df = load_and_split(
        str(_DATA_PATH),
        reference_date="2026-03",
        holdout_month="2026-04",
        min_months=3,
    )

    assert len(actuals_df) == 73
    assert len(train_df) > 0


def test_load_and_split_train_excludes_holdout():
    """No row in train_df should have period_yyyymm > '2026-03'."""
    if not _DATA_PATH.exists():
        pytest.skip("smart_budget_synthetic.csv not present — run outside CI")

    from eval_runner import load_and_split

    train_df, _ = load_and_split(
        str(_DATA_PATH),
        reference_date="2026-03",
        holdout_month="2026-04",
        min_months=3,
    )

    assert (train_df["period_yyyymm"] > "2026-03").sum() == 0


def test_load_and_split_gating_applied():
    """With min_months=3, gated train_df has ≤ 11 unique accounts."""
    if not _DATA_PATH.exists():
        pytest.skip("smart_budget_synthetic.csv not present — run outside CI")

    from eval_runner import load_and_split

    train_df, _ = load_and_split(
        str(_DATA_PATH),
        reference_date="2026-03",
        holdout_month="2026-04",
        min_months=3,
    )

    assert len(train_df["idaccount"].unique()) <= 11


# ---------------------------------------------------------------------------
# T2 — run_evaluation_grid tests
# ---------------------------------------------------------------------------

_EXPECTED_GRID_COLUMNS = {
    "method",
    "lookback_months",
    "treatment",
    "n_total_holdout",
    "n_evaluated",
    "accuracy_delta",
    "coverage_rate_pct",
    "null_rate_pct",
    "mape",
    "mape_n",
    "mae_seasonal",
    "mae_regular",
    "n_seasonal",
    "n_regular",
    "crws",
}


def test_run_evaluation_grid_shape():
    """4 methods × 4 lookbacks = 16 rows; all expected columns present."""
    from eval_runner import run_evaluation_grid

    train_df = _make_test_train_df()
    actuals_df = _make_test_actuals_df()

    result_df = run_evaluation_grid(
        train_df=train_df,
        actuals_df=actuals_df,
        methods=["wma", "ewma", "median", "holt_winters"],
        lookbacks=[3, 6, 9, 12],
        treatment="B",
        reference_date="2025-12",
    )

    assert len(result_df) == 16
    assert set(result_df.columns) == _EXPECTED_GRID_COLUMNS


def test_run_evaluation_grid_sorted_by_mae():
    """Result DataFrame is sorted by accuracy_delta ascending (lowest MAE first)."""
    from eval_runner import run_evaluation_grid

    train_df = _make_test_train_df()
    actuals_df = _make_test_actuals_df()

    result_df = run_evaluation_grid(
        train_df=train_df,
        actuals_df=actuals_df,
        methods=["wma", "ewma", "median", "holt_winters"],
        lookbacks=[3, 6, 9, 12],
        treatment="B",
        reference_date="2025-12",
    )

    deltas = result_df["accuracy_delta"].dropna().tolist()
    assert deltas == sorted(deltas)


def test_run_evaluation_grid_treatment_column():
    """All rows have treatment == 'B'."""
    from eval_runner import run_evaluation_grid

    train_df = _make_test_train_df()
    actuals_df = _make_test_actuals_df()

    result_df = run_evaluation_grid(
        train_df=train_df,
        actuals_df=actuals_df,
        methods=["wma", "ewma", "median", "holt_winters"],
        lookbacks=[3, 6, 9, 12],
        treatment="B",
        reference_date="2025-12",
    )

    assert (result_df["treatment"] == "B").all()


def test_run_evaluation_grid_holt_winters_nulls_lb3():
    """HW lb=3 produces null_rate_pct > 0 (series < 3 obs after treatment B)."""
    from eval_runner import run_evaluation_grid

    train_df = _make_test_train_df()
    actuals_df = _make_test_actuals_df()

    result_df = run_evaluation_grid(
        train_df=train_df,
        actuals_df=actuals_df,
        methods=["wma", "ewma", "median", "holt_winters"],
        lookbacks=[3, 6, 9, 12],
        treatment="B",
        reference_date="2025-12",
    )

    hw_lb3 = result_df[
        (result_df["method"] == "holt_winters") & (result_df["lookback_months"] == 3)
    ]
    assert len(hw_lb3) == 1
    assert hw_lb3["null_rate_pct"].values[0] > 0


# ---------------------------------------------------------------------------
# T2 — _parse_args tests
# ---------------------------------------------------------------------------


def test_parse_args_defaults():
    """_parse_args([]) returns Namespace with expected defaults."""
    from eval_runner import _parse_args

    args = _parse_args([])

    assert args.input == "data/dough/smart_budget_synthetic.csv"
    assert args.reference_date == "2026-03"
    assert args.holdout_month == "2026-04"
    assert args.lookbacks == [3, 6, 9, 12]
    assert args.output is None
    assert args.min_months == 3


def test_parse_args_custom_lookbacks():
    """--lookbacks 3,6 → parsed as [3, 6] (list of int)."""
    from eval_runner import _parse_args

    args = _parse_args(["--lookbacks", "3,6"])

    assert args.lookbacks == [3, 6]


# ---------------------------------------------------------------------------
# T2 — main() tests
# ---------------------------------------------------------------------------


def test_main_outputs_csv_to_stdout(capsys, monkeypatch):
    """main() with no --output writes parseable 16-row CSV to stdout."""
    import eval_runner

    train_df = _make_test_train_df()
    actuals_df = _make_test_actuals_df()

    monkeypatch.setattr(
        eval_runner,
        "load_and_split",
        lambda *args, **kwargs: (train_df, actuals_df),
    )

    eval_runner.main(
        [
            "--input",
            "fake_path.csv",
            "--reference-date",
            "2025-12",
            "--holdout-month",
            "2026-01",
        ]
    )

    output = capsys.readouterr().out
    df = pd.read_csv(io.StringIO(output))
    assert len(df) == 16


def test_eval_runner_importable():
    """Import eval_runner module without running main(). No side effects."""
    import eval_runner  # noqa: F401

    assert hasattr(eval_runner, "compute_metrics")
    assert hasattr(eval_runner, "load_and_split")
    assert hasattr(eval_runner, "run_evaluation_grid")
    assert hasattr(eval_runner, "main")
