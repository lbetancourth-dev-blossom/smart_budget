"""tests/unit/test_api.py — Tests para FastAPI endpoint Smart Budget (DATA-1179).

Contrato actualizado: GET /smart-budget/suggestion?idmember=10&period_id=2026-05
  → MemberSuggestionResponse con array de sugerencias por categoría + total_suggested

Casos de test:
  TC-API-1: Happy path — miembro con historial → 200 con suggestions
  TC-API-2: suggested_amount siempre >= 0.0
  TC-API-3: basis.method == "wma" y basis.treatment == "B"
  TC-API-4: Campo "explanation" NO debe aparecer en la respuesta
  TC-API-5: Miembro no existe → 404
  TC-API-6: period_id con formato inválido → 422
  TC-API-7: Miembro existe pero sin datos → 200 suggestions vacío
  TC-API-8: Historial < 2 meses (gating) → 200 suggestions vacío
  TC-API-9: Respuesta incluye total_suggested y idmember (no idaccount)
"""
from __future__ import annotations

import pandas as pd
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_history_df(
    idmember=10,
    idaccount="EXT2",
    defaultcategory="Groceries",
    idclient="1",
    idcompany="1",
    n_months=3,
    monthly_total=300.0,
):
    """Construye un DataFrame de historial pre-agregado con grain idmember."""
    periods = [f"2026-0{i}" for i in range(2, 2 + n_months)]
    return pd.DataFrame({
        "idclient": [idclient] * n_months,
        "idcompany": [idcompany] * n_months,
        "idmember": [idmember] * n_months,
        "idaccount": [idaccount] * n_months,
        "idcategory": ["5"] * n_months,
        "defaultcategory": [defaultcategory] * n_months,
        "period_yyyymm": periods,
        "monthly_total": [monthly_total] * n_months,
    })


def _make_client(tmp_path, monkeypatch):
    """Crea un TestClient con SMART_BUDGET_DATA_DIR apuntando a tmp_path."""
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# TC-API-1 — Happy path: miembro con historial → 200 con array de sugerencias
# ---------------------------------------------------------------------------

def test_get_suggestion_happy_path_returns_200(tmp_path, monkeypatch):
    """
    Arrange: load_history_by_member retorna 3 meses de historial para idmember=10.
    Act: GET /smart-budget/suggestion?idmember=10&period_id=2026-05.
    Assert: HTTP 200; respuesta contiene todos los campos del contrato.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history_by_member", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    expected_keys = {"idmember", "idclient", "idcompany", "period_id", "total_suggested", "suggestions"}
    assert expected_keys.issubset(body.keys())


# ---------------------------------------------------------------------------
# TC-API-2 — suggested_amount siempre >= 0.0
# ---------------------------------------------------------------------------

def test_get_suggestion_suggested_amount_non_negative(tmp_path, monkeypatch):
    """
    Arrange: 3 meses de historial con gasto positivo.
    Act: GET /smart-budget/suggestion.
    Assert: todo suggested_amount en suggestions >= 0.0 (nunca negativo).
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df(monthly_total=250.0)

    with patch("src.api.router.load_history_by_member", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    for item in body["suggestions"]:
        if item["suggested_amount"] is not None:
            assert item["suggested_amount"] >= 0.0


# ---------------------------------------------------------------------------
# TC-API-3 — basis.method == "wma" y basis.treatment == "B"
# ---------------------------------------------------------------------------

def test_get_suggestion_basis_method_and_treatment(tmp_path, monkeypatch):
    """
    Arrange: idmember con 3 meses de historial.
    Act: GET /smart-budget/suggestion.
    Assert: basis.method == "wma"; basis.treatment == "B" en todas las sugerencias con basis.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history_by_member", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    for item in body["suggestions"]:
        if item["basis"] is not None:
            assert item["basis"]["method"] == "wma"
            assert item["basis"]["treatment"] == "B"


# ---------------------------------------------------------------------------
# TC-API-4 — Campo "explanation" NO debe aparecer en la respuesta
# ---------------------------------------------------------------------------

def test_get_suggestion_explanation_not_in_response(tmp_path, monkeypatch):
    """
    Arrange: idmember con 3 meses de historial.
    Act: GET /smart-budget/suggestion.
    Assert: "explanation" no está en el body de la respuesta.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history_by_member", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    assert "explanation" not in response.json()


# ---------------------------------------------------------------------------
# TC-API-5 — Miembro no existe → 404
# ---------------------------------------------------------------------------

def test_get_suggestion_member_not_found_returns_404(tmp_path, monkeypatch):
    """
    Arrange: load_history_by_member vacío, member_exists=False.
    Act: GET /smart-budget/suggestion?idmember=10.
    Assert: HTTP 404 con mensaje "not found".
    """
    tc = _make_client(tmp_path, monkeypatch)

    with patch("src.api.router.load_history_by_member", return_value=pd.DataFrame()), \
         patch("src.api.router.member_exists", return_value=False):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TC-API-6 — period_id con formato inválido → 422
# ---------------------------------------------------------------------------

def test_get_suggestion_invalid_period_id_returns_422(tmp_path, monkeypatch):
    """
    Arrange: period_id con separador "/" en lugar de "-" (no es un PeriodId válido).
    Act: GET /smart-budget/suggestion?period_id=2026/05.
    Assert: HTTP 422 (FastAPI enum validation).
    """
    tc = _make_client(tmp_path, monkeypatch)

    response = tc.get(
        "/smart-budget/suggestion",
        params={"idmember": 10, "period_id": "2026/05"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# TC-API-7 — Miembro existe pero sin datos → 200 suggestions vacío
# ---------------------------------------------------------------------------

def test_get_suggestion_member_exists_no_data_returns_empty(tmp_path, monkeypatch):
    """
    Arrange: load_history_by_member vacío, member_exists=True.
    Act: GET /smart-budget/suggestion?idmember=10.
    Assert: HTTP 200; suggestions=[]; total_suggested=0.0.
    """
    tc = _make_client(tmp_path, monkeypatch)

    with patch("src.api.router.load_history_by_member", return_value=pd.DataFrame()), \
         patch("src.api.router.member_exists", return_value=True):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["suggestions"] is None
    assert body.get("total_suggested") is None
    assert body["message"] is not None


# ---------------------------------------------------------------------------
# TC-API-8 — Historial < 2 meses (gating) → 200 null + mensaje
# ---------------------------------------------------------------------------

def test_get_suggestion_insufficient_months_returns_empty(tmp_path, monkeypatch):
    """
    Arrange: load_history_by_member retorna 1 mes → apply_gating(min_months=2) lo filtra.
    Act: GET /smart-budget/suggestion.
    Assert: HTTP 200; suggestions ausente; total_suggested=null; message con "history".
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df(n_months=1)

    with patch("src.api.router.load_history_by_member", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["suggestions"] is None
    assert body.get("total_suggested") is None
    assert "history" in body["message"].lower()


# ---------------------------------------------------------------------------
# TC-API-9 — Respuesta usa idmember (no idaccount) y tiene total_suggested
# ---------------------------------------------------------------------------

def test_get_suggestion_uses_idmember_not_idaccount(tmp_path, monkeypatch):
    """
    Assert: la respuesta contiene "idmember" y no contiene "idaccount" a nivel raíz.
    Assert: total_suggested es un número >= 0.0.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history_by_member", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idmember": 10, "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "idmember" in body
    assert "idaccount" not in body
    assert isinstance(body["total_suggested"], (int, float))
    assert body["total_suggested"] >= 0.0
