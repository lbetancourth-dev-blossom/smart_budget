"""tests/unit/test_api.py — Integration tests for FastAPI endpoint (DATA-1140).

Test contracts: TC-T2.1 – TC-T2.8

Reglas de validación del endpoint:
  Regla 1 (TC-T2.5): Si la cuenta no existe → 404 Not Found
  Regla 2 (TC-T2.6): Si la categoría no existe (no reconocida) → 422 Unprocessable Entity
  Regla 3 (TC-T2.7, TC-T2.8): Si la cuenta y categoría existen pero no hay datos → 200 null

Uses TestClient from starlette (via fastapi.testclient).
"""
from __future__ import annotations

import pandas as pd
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_history_df(
    idaccount="SYN001",
    defaultcategory="Groceries",
    idclient="1",
    idcompany="1",
    n_months=3,
    monthly_total=300.0,
):
    """Construye un DataFrame de historial pre-agregado mínimo."""
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


def _make_client(tmp_path, monkeypatch):
    """Crea un TestClient con SMART_BUDGET_DATA_DIR apuntando a tmp_path."""
    monkeypatch.setenv("SMART_BUDGET_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# TC-T2.1 — Happy path: cuenta con historial → 200 con todos los campos
# ---------------------------------------------------------------------------

def test_get_suggestion_happy_path_returns_200(tmp_path, monkeypatch):
    """
    Arrange: load_history retorna 3 meses de historial para SYN001/Groceries.
    Act: GET /smart-budget/suggestion con parámetros válidos.
    Assert: HTTP 200; respuesta contiene todos los campos del contrato.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    expected_keys = {
        "idaccount", "idclient", "idcompany", "defaultcategory", "period_id",
        "suggested_amount", "confidence", "basis", "display_label", "model_version",
        "amount_by_month",
    }
    assert expected_keys.issubset(body.keys())


# ---------------------------------------------------------------------------
# TC-T2.2 — suggested_amount siempre >= 0.0
# ---------------------------------------------------------------------------

def test_get_suggestion_suggested_amount_non_negative(tmp_path, monkeypatch):
    """
    Arrange: 3 meses de historial con gasto positivo.
    Act: GET /smart-budget/suggestion.
    Assert: suggested_amount >= 0.0 (nunca negativo).
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df(monthly_total=250.0)

    with patch("src.api.router.load_history", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    if body["suggested_amount"] is not None:
        assert body["suggested_amount"] >= 0.0


# ---------------------------------------------------------------------------
# TC-T2.3 — basis.method == "wma" y basis.treatment == "B"
# ---------------------------------------------------------------------------

def test_get_suggestion_basis_method_and_treatment(tmp_path, monkeypatch):
    """
    Arrange: cuenta con 3 meses de historial.
    Act: GET /smart-budget/suggestion.
    Assert: basis.method == "wma"; basis.treatment == "B".
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history", return_value=history_df):
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
# TC-T2.4 — Campo "explanation" NO debe aparecer en la respuesta
# ---------------------------------------------------------------------------

def test_get_suggestion_explanation_not_in_response(tmp_path, monkeypatch):
    """
    Arrange: cuenta con 3 meses de historial.
    Act: GET /smart-budget/suggestion.
    Assert: "explanation" no está en el body de la respuesta.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df()

    with patch("src.api.router.load_history", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    assert "explanation" not in response.json()


# ---------------------------------------------------------------------------
# TC-T2.5 — Regla 1: Cuenta no existe → 404
#
# Si el idaccount no está en ningún CSV de datos, el endpoint debe retornar
# 404 Not Found. En uso normal (via enum) todos los accounts están en el CSV,
# por lo que este caso se verifica vía mock.
# ---------------------------------------------------------------------------

def test_get_suggestion_account_not_found_returns_404(tmp_path, monkeypatch):
    """
    Regla 1: Si la cuenta no existe → Error 404.

    Arrange: account_exists=False (la cuenta no tiene datos en ningún CSV).
    Act: GET /smart-budget/suggestion.
    Assert: HTTP 404 con mensaje de error.
    """
    tc = _make_client(tmp_path, monkeypatch)

    with patch("src.api.router.load_history", return_value=pd.DataFrame()), \
         patch("src.api.router.account_exists", return_value=False):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TC-T2.6 — Regla 2: Categoría no existe (no reconocida) → 422
#
# Si defaultcategory no está en el catálogo de categorías válidas (enum),
# FastAPI rechaza la request con 422 Unprocessable Entity antes de ejecutar
# cualquier lógica de negocio.
# ---------------------------------------------------------------------------

def test_get_suggestion_invalid_category_returns_422(tmp_path, monkeypatch):
    """
    Regla 2: Si la categoría no existe → Error 422.

    Arrange: defaultcategory con valor no listado en el enum Category.
    Act: GET /smart-budget/suggestion?defaultcategory=CategoriaInexistente
    Assert: HTTP 422 (FastAPI enum validation).
    """
    tc = _make_client(tmp_path, monkeypatch)

    response = tc.get(
        "/smart-budget/suggestion",
        params={
            "idaccount": "SYN001",
            "defaultcategory": "CategoriaInexistente",
            "period_id": "2026-05",
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# TC-T2.7 — Regla 3a: Cuenta y categoría existen, sin datos para esa
#            combinación → 200 null
#
# Ejemplo real: SYN001 existe en el CSV pero NO tiene datos de Groceries
# (sus categorías son: Auto & Transport, Bills & Utilities,
# Entertainment & Leisure, Home & Rent, Pets).
# ---------------------------------------------------------------------------

def test_get_suggestion_account_and_category_exist_no_data_returns_null(tmp_path, monkeypatch):
    """
    Regla 3a: Si cuenta y categoría existen pero sin datos para ese período → 200 null.

    Arrange: account_exists=True (cuenta existe), load_history vacío
             (no hay transacciones para esa combinación cuenta/categoría).
    Act: GET /smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries
    Assert: HTTP 200; suggested_amount=null; basis=null; confidence=null;
            display_label indica historial insuficiente.
    """
    tc = _make_client(tmp_path, monkeypatch)

    with patch("src.api.router.load_history", return_value=pd.DataFrame()), \
         patch("src.api.router.account_exists", return_value=True):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_amount"] is None
    assert body["confidence"] is None
    assert body["basis"] is None
    assert "historial" in body["display_label"].lower()


# ---------------------------------------------------------------------------
# TC-T2.8 — Regla 3b: Cuenta y categoría existen, historial < 2 meses
#            (gating) → 200 null
#
# Subvariante de Regla 3: hay datos pero son insuficientes para calcular
# una sugerencia confiable (mínimo 2 meses requeridos).
# ---------------------------------------------------------------------------

def test_get_suggestion_insufficient_months_returns_null(tmp_path, monkeypatch):
    """
    Regla 3b: Si cuenta y categoría existen pero historial < 2 meses → 200 null.

    Arrange: load_history retorna 1 mes → apply_gating(min_months=2) lo filtra.
    Act: GET /smart-budget/suggestion.
    Assert: HTTP 200; suggested_amount=null; confidence=null; basis=null.
    """
    tc = _make_client(tmp_path, monkeypatch)
    history_df = _make_history_df(n_months=1)

    with patch("src.api.router.load_history", return_value=history_df):
        response = tc.get(
            "/smart-budget/suggestion",
            params={"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_amount"] is None
    assert body["confidence"] is None
    assert body["basis"] is None
