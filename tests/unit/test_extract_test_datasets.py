"""tests/unit/test_extract_test_datasets.py — TDD tests for scripts/extract_test_datasets.py (DATA-1139)."""

from __future__ import annotations

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

from extract_test_datasets import split_by_source, write_atomic, REQUIRED_COLUMNS  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixture / helper
# ---------------------------------------------------------------------------


def _make_fact_df(rows, idaccount="ACC1"):
    """rows: list of (idtransaction, incomeexpenditure, defaultcategory, deletedat, status, amount[, idaccount])"""
    return pd.DataFrame([
        {
            "idtransaction": r[0],
            "incomeexpenditure": r[1],
            "defaultcategory": r[2],
            "deletedat": r[3],
            "status": r[4],
            "amount": r[5],
            "idaccount": r[6] if len(r) > 6 else idaccount,
            "idclient": "CLI1",
            "idcompany": "CO1",
            "date": "2025-06-15",
            "currency": "USD",
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# TC-1 — Split básico: SUB → internal, EXT → external
# ---------------------------------------------------------------------------


def test_split_sub_goes_to_internal():
    # Arrange
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None, None, 100.0),
        ("EXT001", "expenditure", "DINING",    None, "POSTED", 50.0),
    ])
    # Act
    internal, external, n_unknown = split_by_source(df)
    # Assert
    assert len(internal) == 1
    assert internal.iloc[0]["idtransaction"] == "SUB001"
    assert len(external) == 1
    assert external.iloc[0]["idtransaction"] == "EXT001"
    assert n_unknown == 0


# ---------------------------------------------------------------------------
# TC-2 — Prefijo LOAN → internal
# ---------------------------------------------------------------------------


def test_split_loan_goes_to_internal():
    # Arrange
    df = _make_fact_df([
        ("LOAN001", "expenditure", "AUTO", None, None, 200.0),
        ("LOAN002", "expenditure", "AUTO", None, None, 300.0),
    ])
    # Act
    internal, external, n_unknown = split_by_source(df)
    # Assert
    assert len(internal) == 2
    assert len(external) == 0
    assert n_unknown == 0


# ---------------------------------------------------------------------------
# TC-3 — Miembro con txns OLB y EXT aparece en ambos CSVs
# ---------------------------------------------------------------------------


def test_member_in_both_files_when_has_olb_and_ext():
    # Arrange — mismo idaccount en SUB y EXT
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None,    None,     100.0, "ACC1"),
        ("EXT001", "expenditure", "DINING",    None,    "POSTED",  50.0, "ACC1"),
    ])
    # Act
    internal, external, _ = split_by_source(df)
    # Assert
    assert "ACC1" in internal["idaccount"].values
    assert "ACC1" in external["idaccount"].values


# ---------------------------------------------------------------------------
# TC-4 — Prefijo desconocido excluido de ambos, n_unknown > 0
# ---------------------------------------------------------------------------


def test_unknown_prefix_excluded_from_both():
    # Arrange
    df = _make_fact_df([
        ("XYZ001", "expenditure", "DINING", None, "POSTED", 75.0),
        ("SUB001", "expenditure", "DINING", None, None,    100.0),
    ])
    # Act
    internal, external, n_unknown = split_by_source(df)
    # Assert
    assert n_unknown == 1
    assert len(internal) == 1
    assert len(external) == 0
    assert "XYZ001" not in internal["idtransaction"].values
    assert "XYZ001" not in external["idtransaction"].values


# ---------------------------------------------------------------------------
# TC-5 — filter_transactions aplicado: OLB PENDING excluido
# ---------------------------------------------------------------------------


def test_filter_applied_pending_olb_excluded():
    # Arrange — SUB con status PENDING debe ser excluido por filter_transactions
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None, "PENDING", 100.0),
        ("SUB002", "expenditure", "GROCERIES", None, None,      80.0),
    ])
    # Act — pasar por filter antes de split (como hace el script main)
    from smart_budget.filters import filter_transactions
    filtered = filter_transactions(df)
    internal, external, _ = split_by_source(filtered)
    # Assert
    assert len(internal) == 1
    assert internal.iloc[0]["idtransaction"] == "SUB002"


# ---------------------------------------------------------------------------
# TC-6 — Source vacía post-filtro: split devuelve DataFrame vacío, no excepción
# ---------------------------------------------------------------------------


def test_empty_source_returns_empty_df_not_exception():
    # Arrange — solo SUB rows, ningún EXT
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None, None, 100.0),
    ])
    # Act
    internal, external, _ = split_by_source(df)
    # Assert
    assert len(external) == 0
    assert isinstance(external, pd.DataFrame)  # no excepción, DataFrame vacío


# ---------------------------------------------------------------------------
# TC-7 — write_atomic escribe CSV y aplica chmod 600
# ---------------------------------------------------------------------------


def test_write_atomic_creates_file_with_restricted_permissions(tmp_path):
    # Arrange
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    out = tmp_path / "test.csv"
    # Act
    write_atomic(df, out)
    # Assert
    assert out.exists()
    assert not (tmp_path / "test.csv.tmp").exists()  # tmp limpiado
    import stat
    mode = stat.S_IMODE(out.stat().st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# TC-8 — write_atomic aplica chmod 600 al .tmp antes de os.replace
# ---------------------------------------------------------------------------


def test_write_atomic_tmp_file_has_restricted_permissions_before_replace(tmp_path, monkeypatch):
    # Arrange — interceptar os.replace para inspeccionar el .tmp antes de que desaparezca
    import stat
    import os as real_os
    captured_tmp_mode = {}

    original_replace = real_os.replace

    def mock_replace(src, dst):
        captured_tmp_mode["mode"] = stat.S_IMODE(real_os.stat(src).st_mode)
        original_replace(src, dst)

    monkeypatch.setattr("os.replace", mock_replace)

    df = pd.DataFrame({"a": [1], "b": [2]})
    out = tmp_path / "out.csv"
    # Act
    write_atomic(df, out)
    # Assert — .tmp tenía permisos 600 antes de rename
    assert captured_tmp_mode["mode"] == 0o600


# ---------------------------------------------------------------------------
# TC-9 — output contiene solo OUTPUT_COLUMNS (data minimization, SC-1)
# ---------------------------------------------------------------------------


def test_split_output_uses_only_output_columns():
    # Arrange — DataFrame con columnas extra (description, note, balance)
    df = _make_fact_df([("SUB001", "expenditure", "GROCERIES", None, None, 100.0)])
    df["description"] = "Walmart purchase"
    df["note"] = "user note"
    df["balance"] = 500.0
    from smart_budget.filters import filter_transactions
    filtered = filter_transactions(df)
    # Act
    internal, _, _ = split_by_source(filtered)
    # Assert — columnas extra no deben aparecer en el output
    from extract_test_datasets import OUTPUT_COLUMNS
    for col in internal.columns:
        assert col in OUTPUT_COLUMNS, f"Columna inesperada en output: {col}"
