"""tests/unit/test_loader.py — Unit tests for src/smart_budget/loader.py (DATA-1140).

Test contracts: TC-T1.1 – TC-T1.7
"""
from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers — build minimal CSV fixtures in tmp_path
# ---------------------------------------------------------------------------

def _make_synthetic_csv(base_dir, rows=None):
    """Write a minimal smart_budget_synthetic.csv to base_dir."""
    if rows is None:
        rows = [
            # SYN001 / GROCERIES — 3 months
            {"idclient": "1", "idcompany": "1", "idaccount": "SYN001",
             "idcategory": "5", "defaultcategory": "GROCERIES",
             "period_yyyymm": "2026-02", "monthly_total": "300.0"},
            {"idclient": "1", "idcompany": "1", "idaccount": "SYN001",
             "idcategory": "5", "defaultcategory": "GROCERIES",
             "period_yyyymm": "2026-03", "monthly_total": "320.0"},
            {"idclient": "1", "idcompany": "1", "idaccount": "SYN001",
             "idcategory": "5", "defaultcategory": "GROCERIES",
             "period_yyyymm": "2026-04", "monthly_total": "340.0"},
            # EXT2 / GROCERIES — 3 months
            {"idclient": "1", "idcompany": "1", "idaccount": "EXT2",
             "idcategory": "5", "defaultcategory": "GROCERIES",
             "period_yyyymm": "2026-02", "monthly_total": "100.0"},
            {"idclient": "1", "idcompany": "1", "idaccount": "EXT2",
             "idcategory": "5", "defaultcategory": "GROCERIES",
             "period_yyyymm": "2026-03", "monthly_total": "110.0"},
            {"idclient": "1", "idcompany": "1", "idaccount": "EXT2",
             "idcategory": "5", "defaultcategory": "GROCERIES",
             "period_yyyymm": "2026-04", "monthly_total": "120.0"},
        ]
    df = pd.DataFrame(rows)
    synth_path = base_dir / "smart_budget_synthetic.csv"
    df.to_csv(synth_path, index=False)
    return synth_path


def _make_internal_csv(base_dir):
    """Write a minimal test/test_internal.csv to base_dir."""
    test_dir = base_dir / "test"
    test_dir.mkdir(exist_ok=True)
    rows = [
        # SUB prefix (OLB) → amounts are negative in raw CSV
        {"idclient": "1", "idcompany": "1", "idaccount": "INT23",
         "idtransaction": "SUB0001", "defaultcategory": "GROCERIES",
         "date": "2026-02-10", "amount": "-150.0",
         "incomeexpenditure": "expenditure", "deletedat": "", "status": ""},
        {"idclient": "1", "idcompany": "1", "idaccount": "INT23",
         "idtransaction": "SUB0002", "defaultcategory": "GROCERIES",
         "date": "2026-03-15", "amount": "-200.0",
         "incomeexpenditure": "expenditure", "deletedat": "", "status": ""},
        {"idclient": "1", "idcompany": "1", "idaccount": "INT23",
         "idtransaction": "SUB0003", "defaultcategory": "GROCERIES",
         "date": "2026-04-20", "amount": "-180.0",
         "incomeexpenditure": "expenditure", "deletedat": "", "status": ""},
    ]
    df = pd.DataFrame(rows)
    int_path = test_dir / "test_internal.csv"
    df.to_csv(int_path, index=False)
    return int_path


def _make_external_csv(base_dir):
    """Write a minimal test/test_external.csv to base_dir (amounts already positive)."""
    test_dir = base_dir / "test"
    test_dir.mkdir(exist_ok=True)
    rows = [
        {"idclient": "1", "idcompany": "1", "idaccount": "EXT99",
         "idtransaction": "EXT0001", "defaultcategory": "RESTAURANTS",
         "date": "2026-02-05", "amount": "75.0",
         "incomeexpenditure": "expenditure", "deletedat": "", "status": "POSTED"},
    ]
    df = pd.DataFrame(rows)
    ext_path = test_dir / "test_external.csv"
    df.to_csv(ext_path, index=False)
    return ext_path


# ---------------------------------------------------------------------------
# TC-T1.1 — load_history: synthetic account returns monthly df
# ---------------------------------------------------------------------------

def test_load_history_synthetic_account_returns_monthly_df(tmp_path):
    """
    Arrange: base_dir with smart_budget_synthetic.csv containing SYN001/GROCERIES.
    Act: load_history("SYN001", "GROCERIES", tmp_path).
    Assert: DataFrame non-empty with correct columns; monthly_total >= 0.
    """
    from smart_budget.loader import load_history, _synthetic_accounts

    _synthetic_accounts.cache_clear()
    _make_synthetic_csv(tmp_path)

    result = load_history("SYN001", "GROCERIES", tmp_path)

    expected_cols = {"idclient", "idcompany", "idaccount", "idcategory",
                     "defaultcategory", "period_yyyymm", "monthly_total"}
    assert not result.empty, "Expected non-empty DataFrame for SYN001/GROCERIES"
    assert set(result.columns) >= expected_cols
    assert (result["monthly_total"] >= 0).all()
    assert (result["idaccount"] == "SYN001").all()
    assert (result["defaultcategory"] == "GROCERIES").all()


# ---------------------------------------------------------------------------
# TC-T1.2 — load_history: raw OLB account returns positive amounts
# ---------------------------------------------------------------------------

def test_load_history_raw_account_returns_positive_amounts(tmp_path):
    """
    Arrange: base_dir with test_internal.csv (SUB prefix, negative amounts),
             no synthetic CSV.
    Act: load_history("INT23", "GROCERIES", tmp_path).
    Assert: DataFrame non-empty; all monthly_total >= 0 (abs() applied).
    """
    from smart_budget.loader import load_history, _synthetic_accounts

    _synthetic_accounts.cache_clear()
    _make_internal_csv(tmp_path)
    # Also create empty external CSV to avoid missing-file path
    _make_external_csv(tmp_path)

    result = load_history("INT23", "GROCERIES", tmp_path)

    assert not result.empty, "Expected non-empty DataFrame for INT23/GROCERIES"
    assert (result["monthly_total"] >= 0).all(), "OLB amounts must be abs()-normalised"


# ---------------------------------------------------------------------------
# TC-T1.3 — load_history: unknown account returns empty DataFrame
# ---------------------------------------------------------------------------

def test_load_history_unknown_account_returns_empty(tmp_path):
    """
    Arrange: base_dir with synthetic CSV (no NONEXISTENT_XYZ).
    Act: load_history("NONEXISTENT_XYZ", "GROCERIES", tmp_path).
    Assert: empty DataFrame, no exception.
    """
    from smart_budget.loader import load_history, _synthetic_accounts

    _synthetic_accounts.cache_clear()
    _make_synthetic_csv(tmp_path)
    _make_internal_csv(tmp_path)
    _make_external_csv(tmp_path)

    result = load_history("NONEXISTENT_XYZ", "GROCERIES", tmp_path)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ---------------------------------------------------------------------------
# TC-T1.4 — load_history: nonexistent category for synthetic account → empty
# ---------------------------------------------------------------------------

def test_load_history_nonexistent_category_returns_empty(tmp_path):
    """
    Arrange: SYN001 exists but with GROCERIES only; request CATEGORIA_QUE_NO_EXISTE.
    Act: load_history("SYN001", "CATEGORIA_QUE_NO_EXISTE", tmp_path).
    Assert: empty DataFrame.
    """
    from smart_budget.loader import load_history, _synthetic_accounts

    _synthetic_accounts.cache_clear()
    _make_synthetic_csv(tmp_path)

    result = load_history("SYN001", "CATEGORIA_QUE_NO_EXISTE", tmp_path)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ---------------------------------------------------------------------------
# TC-T1.5 — _normalize_olb_amounts: SUB prefix → abs()
# ---------------------------------------------------------------------------

def test_normalize_olb_amounts_sub_prefix():
    """
    Arrange: DataFrame with idtransaction='SUB123', amount=-150.0.
    Act: _normalize_olb_amounts(df).
    Assert: amount == 150.0.
    """
    from smart_budget.loader import _normalize_olb_amounts

    df = pd.DataFrame({
        "idtransaction": ["SUB123"],
        "amount": [-150.0],
    })

    result = _normalize_olb_amounts(df)

    assert result.iloc[0]["amount"] == 150.0


# ---------------------------------------------------------------------------
# TC-T1.6 — _normalize_olb_amounts: EXT prefix → unchanged
# ---------------------------------------------------------------------------

def test_normalize_olb_amounts_ext_prefix_unchanged():
    """
    Arrange: DataFrame with idtransaction='EXT456', amount=75.0.
    Act: _normalize_olb_amounts(df).
    Assert: amount == 75.0 (positive, no change).
    """
    from smart_budget.loader import _normalize_olb_amounts

    df = pd.DataFrame({
        "idtransaction": ["EXT456"],
        "amount": [75.0],
    })

    result = _normalize_olb_amounts(df)

    assert result.iloc[0]["amount"] == 75.0


# ---------------------------------------------------------------------------
# TC-T1.7 — load_history: FileNotFoundError on missing base_dir
# ---------------------------------------------------------------------------

def test_load_history_raises_on_missing_base_dir():
    """
    Arrange: base_dir path that does not exist.
    Act: load_history("SYN001", "GROCERIES", "/ruta/que/no/existe/XYZ_999").
    Assert: FileNotFoundError raised.
    """
    from smart_budget.loader import load_history

    with pytest.raises(FileNotFoundError):
        load_history("SYN001", "GROCERIES", "/ruta/que/no/existe/XYZ_999")
