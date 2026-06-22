"""tests/unit/test_athena_loader.py — Unit tests for src/smart_budget/athena_loader.py (DATA-1275).

Tests for AthenaQueryError, _get_connection, load_history_by_member_athena,
and member_exists_athena using mocked pyathena.
"""
from __future__ import annotations

import os
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# T1.1 — _get_connection
# ---------------------------------------------------------------------------


def test_get_connection_uses_env_vars(monkeypatch):
    """
    Arrange: set ATHENA_S3_STAGING_DIR and ATHENA_REGION_NAME env vars; reset module-level _CONN.
    Act: call _get_connection().
    Assert: pyathena.connect called with exact kwargs s3_staging_dir and region_name.
    """
    monkeypatch.setenv("ATHENA_S3_STAGING_DIR", "s3://bucket/path/")
    monkeypatch.setenv("ATHENA_REGION_NAME", "us-west-2")

    mock_conn = MagicMock()

    import smart_budget.athena_loader as loader_mod
    monkeypatch.setattr(loader_mod, "_CONN", None)

    with patch("smart_budget.athena_loader.pyathena.connect", return_value=mock_conn) as mock_connect:
        result = loader_mod._get_connection()

    mock_connect.assert_called_once_with(
        s3_staging_dir="s3://bucket/path/",
        region_name="us-west-2",
    )
    assert result is mock_conn


def test_get_connection_caches_result(monkeypatch):
    """
    Arrange: set env vars; reset _CONN; call _get_connection() twice.
    Act: two consecutive calls.
    Assert: pyathena.connect invoked exactly once (cached).
    """
    monkeypatch.setenv("ATHENA_S3_STAGING_DIR", "s3://bucket/path/")
    monkeypatch.setenv("ATHENA_REGION_NAME", "us-east-2")

    mock_conn = MagicMock()

    import smart_budget.athena_loader as loader_mod
    monkeypatch.setattr(loader_mod, "_CONN", None)

    with patch("smart_budget.athena_loader.pyathena.connect", return_value=mock_conn) as mock_connect:
        r1 = loader_mod._get_connection()
        r2 = loader_mod._get_connection()

    mock_connect.assert_called_once()
    assert r1 is r2


def test_get_connection_missing_staging_dir_raises(monkeypatch):
    """
    Arrange: unset ATHENA_S3_STAGING_DIR; reset _CONN.
    Act: call _get_connection().
    Assert: AthenaQueryError raised mentioning ATHENA_S3_STAGING_DIR.
    """
    monkeypatch.delenv("ATHENA_S3_STAGING_DIR", raising=False)

    import smart_budget.athena_loader as loader_mod
    monkeypatch.setattr(loader_mod, "_CONN", None)

    with pytest.raises(loader_mod.AthenaQueryError, match="ATHENA_S3_STAGING_DIR"):
        loader_mod._get_connection()


# ---------------------------------------------------------------------------
# T1.2 — load_history_by_member_athena
# ---------------------------------------------------------------------------


def _sample_raw_df(idmember="42", n=3):
    """Helper: raw DataFrame as returned by pd.read_sql (before post-processing)."""
    return pd.DataFrame({
        "idclient": ["1"] * n,
        "idcompany": ["1"] * n,
        "idmember": [idmember] * n,
        "idaccount": ["ACC1"] * n,
        "category_id": ["5"] * n,
        "category_name": ["Groceries"] * n,
        "txn_month": [f"2026-0{i+1}-01" for i in range(n)],
        "total_amount": [100.0 + i * 10 for i in range(n)],
    })


def test_load_history_happy_path(monkeypatch):
    """
    Arrange: mock pd.read_sql returns raw rows for idmember.
    Act: call load_history_by_member_athena(idmember="42").
    Assert: returned DataFrame has exactly 8 columns, period_yyyymm is YYYY-MM format,
    monthly_total is float.
    """
    raw_df = _sample_raw_df()

    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=raw_df):
        result = loader_mod.load_history_by_member_athena(idmember="42")

    expected_cols = {
        "idclient", "idcompany", "idmember", "idaccount",
        "category_id", "category_name", "period_yyyymm", "monthly_total",
    }
    assert set(result.columns) == expected_cols
    assert len(result.columns) == 8
    for p in result["period_yyyymm"]:
        assert len(p) == 7 and p[4] == "-"
    assert result["monthly_total"].dtype == float


def test_load_history_empty(monkeypatch):
    """
    Arrange: mock pd.read_sql returns empty DataFrame with raw columns.
    Act: call load_history_by_member_athena.
    Assert: result is empty with the 8-column schema.
    """
    empty_raw = pd.DataFrame(columns=[
        "idclient", "idcompany", "idmember", "idaccount",
        "category_id", "category_name", "txn_month", "total_amount",
    ])

    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=empty_raw):
        result = loader_mod.load_history_by_member_athena(idmember="42")

    expected_cols = {
        "idclient", "idcompany", "idmember", "idaccount",
        "category_id", "category_name", "period_yyyymm", "monthly_total",
    }
    assert set(result.columns) == expected_cols
    assert len(result) == 0


def test_load_history_param_binding_safe(monkeypatch):
    """
    Arrange: idmember string with special chars.
    Act: call load_history_by_member_athena(idmember="42'; DROP TABLE--").
    Assert: pd.read_sql called with params={"idmember": "42'; DROP TABLE--"} (no interpolation).
    """
    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()
    dangerous_id = "42'; DROP TABLE--"
    raw_df = _sample_raw_df(idmember=dangerous_id, n=0)
    raw_df = pd.DataFrame(columns=[
        "idclient", "idcompany", "idmember", "idaccount",
        "category_id", "category_name", "txn_month", "total_amount",
    ])

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn) as _mock_get, \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=raw_df) as mock_read_sql:
        loader_mod.load_history_by_member_athena(idmember=dangerous_id)

    _, kwargs = mock_read_sql.call_args
    assert kwargs.get("params") == {"idmember": dangerous_id}


def test_load_history_clamps_negative_total(monkeypatch):
    """
    Arrange: raw row with total_amount=-50.
    Act: call load_history_by_member_athena.
    Assert: monthly_total == 0.0 (clamped).
    """
    raw_df = pd.DataFrame({
        "idclient": ["1"],
        "idcompany": ["1"],
        "idmember": ["42"],
        "idaccount": ["ACC1"],
        "category_id": ["5"],
        "category_name": ["Groceries"],
        "txn_month": ["2026-01-01"],
        "total_amount": [-50.0],
    })

    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=raw_df):
        result = loader_mod.load_history_by_member_athena(idmember="42")

    assert result["monthly_total"].iloc[0] == 0.0


def test_load_history_uses_env_db_table(monkeypatch):
    """
    Arrange: set ATHENA_DATABASE=foo, ATHENA_TABLE=bar.
    Act: call load_history_by_member_athena.
    Assert: SQL query passed to pd.read_sql contains 'foo.bar'.
    """
    monkeypatch.setenv("ATHENA_DATABASE", "foo")
    monkeypatch.setenv("ATHENA_TABLE", "bar")

    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()
    raw_df = pd.DataFrame(columns=[
        "idclient", "idcompany", "idmember", "idaccount",
        "category_id", "category_name", "txn_month", "total_amount",
    ])

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=raw_df) as mock_read_sql:
        loader_mod.load_history_by_member_athena(idmember="42")

    sql_arg = mock_read_sql.call_args[0][0]
    assert "foo.bar" in sql_arg


def test_load_history_wraps_exception(monkeypatch):
    """
    Arrange: pd.read_sql raises RuntimeError.
    Act: call load_history_by_member_athena.
    Assert: AthenaQueryError raised with original exception chained.
    """
    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", side_effect=RuntimeError("boom")):
        with pytest.raises(loader_mod.AthenaQueryError) as exc_info:
            loader_mod.load_history_by_member_athena(idmember="42")

    assert exc_info.value.__cause__ is not None


# ---------------------------------------------------------------------------
# T1.3 — member_exists_athena
# ---------------------------------------------------------------------------


def test_member_exists_true(monkeypatch):
    """
    Arrange: pd.read_sql returns 1-row DataFrame.
    Act: call member_exists_athena.
    Assert: returns True.
    """
    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()
    one_row = pd.DataFrame({"1": [1]})

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=one_row):
        result = loader_mod.member_exists_athena(idmember="42")

    assert result is True


def test_member_exists_false(monkeypatch):
    """
    Arrange: pd.read_sql returns empty DataFrame.
    Act: call member_exists_athena.
    Assert: returns False.
    """
    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()
    empty = pd.DataFrame()

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", return_value=empty):
        result = loader_mod.member_exists_athena(idmember="42")

    assert result is False


def test_member_exists_wraps_exception(monkeypatch):
    """
    Arrange: pd.read_sql raises RuntimeError.
    Act: call member_exists_athena.
    Assert: AthenaQueryError raised.
    """
    import smart_budget.athena_loader as loader_mod
    mock_conn = MagicMock()

    with patch.object(loader_mod, "_get_connection", return_value=mock_conn), \
         patch("smart_budget.athena_loader.pd.read_sql", side_effect=RuntimeError("timeout")):
        with pytest.raises(loader_mod.AthenaQueryError):
            loader_mod.member_exists_athena(idmember="42")
