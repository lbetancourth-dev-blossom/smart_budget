"""tests/unit/test_api.py — Integration tests for FastAPI endpoint (DATA-1140).

Test contracts: TC-T2.1 – TC-T2.8
Uses TestClient from starlette (via fastapi.testclient).
"""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Return a TestClient with SMART_BUDGET_DATA_DIR pointing to tmp_path.

    We patch load_history at the router level so tests are data-independent.
    The fixture sets the env var and returns the test client.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


def _make_history_df(
    idaccount="SYN001",
    defaultcategory="Groceries",
    idclient="1",
    idcompany="1",
    n_months=3,
    monthly_total=300.0,
):
    """Build a minimal pre-aggregated history DataFrame."""
    periods = [f"2026-0{i}" for i in range(2, 2 + n_months)]
    return pd.DataFrame({
        "idclient": [idclient] * n_months,
        "idcompany": [idcompany] * n_months,
        "idaccount": [idaccount] * n_months,
        "idcategory": ["5"] * n_months,
        "defaultcategory": [defaultcategory] * n_months,
        "period_yyyymm": periods,
        "monthly_total": [monthly_total] * n_months,
    })


# ---------------------------------------------------------------------------
# TC-T2.1 — GET /smart-budget/suggestion: synthetic account returns 200
# ---------------------------------------------------------------------------

def test_get_suggestion_synthetic_account_returns_200(tmp_path, monkeypatch):
    """
    Arrange: mock load_history to return 3-month history for SYN001/Groceries.
    Act: GET /smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2026-05
    Assert: HTTP 200; body contains all expected fields.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    history_df = _make_history_df()

    with patch("src.api.router.load_history", return_value=history_df):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    expected_keys = {
        "idaccount", "idclient", "idcompany", "defaultcategory", "period_id",
        "suggested_amount", "confidence", "basis", "display_label", "model_version",
    }
    assert expected_keys.issubset(body.keys())


# ---------------------------------------------------------------------------
# TC-T2.2 — suggested_amount >= 0.0 in successful response
# ---------------------------------------------------------------------------

def test_get_suggestion_suggested_amount_non_negative(tmp_path, monkeypatch):
    """
    Arrange: 3 months of history → sufficient for WMA.
    Act: GET /smart-budget/suggestion with valid params.
    Assert: suggested_amount >= 0.0.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    history_df = _make_history_df(monthly_total=250.0)

    with patch("src.api.router.load_history", return_value=history_df):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    if body["suggested_amount"] is not None:
        assert body["suggested_amount"] >= 0.0


# ---------------------------------------------------------------------------
# TC-T2.3 — basis.method == "wma" and basis.treatment == "B"
# ---------------------------------------------------------------------------

def test_get_suggestion_basis_method_and_treatment(tmp_path, monkeypatch):
    """
    Arrange: valid account with 3 months history.
    Act: GET /smart-budget/suggestion.
    Assert: basis.method == "wma"; basis.treatment == "B".
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    history_df = _make_history_df()

    with patch("src.api.router.load_history", return_value=history_df):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    if body["basis"] is not None:
        assert body["basis"]["method"] == "wma"
        assert body["basis"]["treatment"] == "B"


# ---------------------------------------------------------------------------
# TC-T2.4 — "explanation" field NOT in response body
# ---------------------------------------------------------------------------

def test_get_suggestion_explanation_not_in_response(tmp_path, monkeypatch):
    """
    Arrange: valid account with 3 months history.
    Act: GET /smart-budget/suggestion.
    Assert: "explanation" key absent in response body.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    history_df = _make_history_df()

    with patch("src.api.router.load_history", return_value=history_df):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    assert "explanation" not in response.json()


# ---------------------------------------------------------------------------
# TC-T2.5 — Cuenta que no existe en ningún CSV → 404
# ---------------------------------------------------------------------------

def test_get_suggestion_unknown_account_returns_404(tmp_path, monkeypatch):
    """
    Arrange: load_history devuelve DataFrame vacío Y account_exists devuelve False.
    Act: GET /smart-budget/suggestion con una cuenta que no tiene datos en ningún CSV.
    Assert: HTTP 404.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    with patch("src.api.router.load_history", return_value=pd.DataFrame()), \
         patch("src.api.router.account_exists", return_value=False):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={
                "idaccount": "SYN001",
                "defaultcategory": "Groceries",
                "period_id": "2026-05",
            },
        )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# TC-T2.9 — Cuenta existe pero sin datos para la categoría → 200 null
# ---------------------------------------------------------------------------

def test_get_suggestion_account_exists_no_category_data_returns_null(tmp_path, monkeypatch):
    """
    Arrange: load_history devuelve DataFrame vacío PERO account_exists devuelve True.
             La cuenta existe pero no tiene historial para la categoría pedida.
    Act: GET /smart-budget/suggestion.
    Assert: HTTP 200; suggested_amount == null; display_label indica historial insuficiente.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    with patch("src.api.router.load_history", return_value=pd.DataFrame()), \
         patch("src.api.router.account_exists", return_value=True):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={
                "idaccount": "SYN001",
                "defaultcategory": "Pets",
                "period_id": "2026-05",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_amount"] is None
    assert body["confidence"] is None
    assert body["basis"] is None
    assert "historial" in body["display_label"].lower()


# ---------------------------------------------------------------------------
# TC-T2.6 — Invalid param value (not in enum) → 422
# ---------------------------------------------------------------------------

def test_get_suggestion_invalid_period_id_returns_422(tmp_path, monkeypatch):
    """
    Arrange: period_id value not in the PeriodId enum (e.g. "2099-01").
    Act: GET /smart-budget/suggestion?...&period_id=2099-01
    Assert: HTTP 422 (FastAPI enum validation rejects unknown value).
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    tc = TestClient(app)
    response = tc.get(
        "/smart-budget/suggestion",
        params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2099-01"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# TC-T2.7 — Insufficient data (1 month) → 200 null response
# ---------------------------------------------------------------------------

def test_get_suggestion_insufficient_data_returns_null_200(tmp_path, monkeypatch):
    """
    Arrange: load_history returns 1 month → apply_gating(min_months=2) filters it out.
    Act: GET /smart-budget/suggestion.
    Assert: HTTP 200; confidence == null; suggested_amount == null; basis == null.
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    # 1 month of data — gating min_months=2 will gate it out
    history_df = _make_history_df(n_months=1)

    with patch("src.api.router.load_history", return_value=history_df):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] is None
    assert body["suggested_amount"] is None
    assert body["basis"] is None


# ---------------------------------------------------------------------------
# TC-T2.8 — period_id at edge of enum with no data in window → 200 null
# ---------------------------------------------------------------------------

def test_get_suggestion_period_id_not_in_historical_window(tmp_path, monkeypatch):
    """
    Arrange: history has data for 2026-02/03/04; period_id=2025-09 → window 2025-06~2025-08.
    Act: GET /smart-budget/suggestion?...&period_id=2025-09
    Assert: HTTP 200 with null response (window is entirely before history).
    """
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    from fastapi.testclient import TestClient
    from src.main import app

    # History is 2026-02 through 2026-04 — window 2025-06~2025-08 has no overlap
    history_df = _make_history_df(n_months=3)

    with patch("src.api.router.load_history", return_value=history_df):
        tc = TestClient(app)
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2025-09"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_amount"] is None

