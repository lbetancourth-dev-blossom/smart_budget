"""tests/unit/test_filters.py — Unit tests for smart_budget.filters (TC-2.1 through TC-2.8)."""
import pytest
import pandas as pd

from smart_budget.filters import filter_transactions
from tests.conftest import _load_fixture


# ---------------------------------------------------------------------------
# TC-2.1 — Soft-delete exclusion
# ---------------------------------------------------------------------------

def test_filter_removes_soft_deleted():
    df = pd.DataFrame({
        "deletedat": [None, "2025-01-01", None],
        "incomeexpenditure": ["expenditure", "expenditure", "expenditure"],
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES"],
        "idtransaction": ["SUB1", "SUB2", "SUB3"],
        "status": [None, None, None],
        "amount": [100.0, 50.0, 80.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2
    assert "SUB2" not in result["idtransaction"].values


# ---------------------------------------------------------------------------
# TC-2.2 — Income exclusion
# ---------------------------------------------------------------------------

def test_filter_removes_income_transactions():
    df = pd.DataFrame({
        "deletedat": [None, None, None],
        "incomeexpenditure": ["expenditure", "income", "expenditure"],
        "defaultcategory": ["GROCERIES", "SALARY", "DINING"],
        "idtransaction": ["SUB1", "SUB2", "SUB3"],
        "status": [None, None, None],
        "amount": [100.0, 2000.0, 50.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2
    assert "income" not in result["incomeexpenditure"].values


# ---------------------------------------------------------------------------
# TC-2.3 — Invalid category exclusion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", ["UNCATEGORIZED", None, "INCOME", "MONEY_SENT"])
def test_filter_removes_invalid_categories(category):
    df = pd.DataFrame({
        "deletedat": [None, None],
        "incomeexpenditure": ["expenditure", "expenditure"],
        "defaultcategory": [category, "GROCERIES"],
        "idtransaction": ["SUB1", "SUB2"],
        "status": [None, None],
        "amount": [100.0, 80.0],
    })
    result = filter_transactions(df)
    assert len(result) == 1
    assert result.iloc[0]["defaultcategory"] == "GROCERIES"


# ---------------------------------------------------------------------------
# TC-2.4 — OLB PENDING exclusion
# ---------------------------------------------------------------------------

def test_filter_removes_olb_pending():
    df = pd.DataFrame({
        "deletedat": [None, None, None],
        "incomeexpenditure": ["expenditure"] * 3,
        "defaultcategory": ["GROCERIES"] * 3,
        "idtransaction": ["SUB1", "SUB2", "LOAN1"],
        "status": [None, "PENDING", None],
        "amount": [100.0, 75.0, 200.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2
    assert "SUB2" not in result["idtransaction"].values


# ---------------------------------------------------------------------------
# TC-2.5 — External Dough (EXT/Plaid) only POSTED
# ---------------------------------------------------------------------------

def test_filter_external_only_posted():
    df = pd.DataFrame({
        "deletedat": [None, None, None],
        "incomeexpenditure": ["expenditure"] * 3,
        "defaultcategory": ["DINING"] * 3,
        "idtransaction": ["EXT1", "EXT2", "EXT3"],
        "status": ["POSTED", "PENDING", None],
        "amount": [50.0, 80.0, 90.0],
    })
    result = filter_transactions(df)
    assert len(result) == 1
    assert result.iloc[0]["idtransaction"] == "EXT1"


# ---------------------------------------------------------------------------
# TC-2.6 — Combined rules (realistic fixture)
# ---------------------------------------------------------------------------

def test_filter_combined_rules():
    """Fixture: rows covering all 5 rules; exactly 5 valid IDs must survive."""
    df = _load_fixture("fact_transactions_test.csv")
    result = filter_transactions(df)
    expected_ids = {"SUB_VALID_1", "SUB_VALID_2", "LOAN_VALID_1", "EXT_POSTED_1", "EXT_POSTED_2"}
    assert set(result["idtransaction"].values) == expected_ids


# ---------------------------------------------------------------------------
# TC-2.8 — Unknown prefix passes through (no silent data loss)
# ---------------------------------------------------------------------------

def test_filter_unknown_prefix_passes_through():
    """Transactions with an unknown prefix (not SUB/LOAN/EXT) must not be silently dropped."""
    df = pd.DataFrame({
        "deletedat": [None, None],
        "incomeexpenditure": ["expenditure", "expenditure"],
        "defaultcategory": ["GROCERIES", "DINING"],
        "idtransaction": ["ACH_001", "WIRE_002"],
        "status": ["POSTED", None],
        "amount": [120.0, 80.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2, "Unknown prefixes must not be excluded by status rules"


def test_filter_empty_dataframe():
    df = pd.DataFrame(columns=["deletedat", "incomeexpenditure", "defaultcategory",
                                "idtransaction", "status", "amount"])
    result = filter_transactions(df)
    assert len(result) == 0
    assert isinstance(result, pd.DataFrame)
