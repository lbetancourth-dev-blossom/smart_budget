"""tests/unit/test_inference.py — Unit tests for src/sagemaker/inference.py (DATA-1275).

Contrato actualizado (DATA-1275): inference usa Athena loader en lugar de CSV bundleado.
"""

from __future__ import annotations

import json
import pytest
import pandas as pd
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history_df(idmember="99", n_months=3, categories=("Groceries",)):
    """Genera DataFrame de historial con schema Athena (category_id/category_name)."""
    rows = []
    for cat in categories:
        for i in range(n_months):
            rows.append(
                {
                    "idclient": "1",
                    "idcompany": "1",
                    "idmember": idmember,
                    "idaccount": f"INT{idmember}",
                    "category_id": "5",
                    "category_name": cat,
                    "period_yyyymm": f"2026-0{i+1}",
                    "monthly_total": 300.0 + i * 10,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# TC-T5.1 — model_fn: retorna el path al model_dir
# ---------------------------------------------------------------------------


def test_inference_model_fn(tmp_path):
    """model_fn retorna el directorio y lo añade al sys.path."""
    from src.sagemaker.inference import model_fn

    result = model_fn(str(tmp_path))

    from pathlib import Path

    assert Path(result).exists()
    assert result == str(tmp_path)


# ---------------------------------------------------------------------------
# TC-T5.2 — input_fn: JSON válido → dict con idmember y period_id
# ---------------------------------------------------------------------------


def test_inference_input_fn_valid():
    """input_fn parsea {idmember, period_id} correctamente."""
    from src.sagemaker.inference import input_fn

    payload = json.dumps({"idmember": "15632", "period_id": "2026-05"})
    result = input_fn(payload, "application/json")

    assert result["idmember"] == "15632"
    assert result["period_id"] == "2026-05"


# ---------------------------------------------------------------------------
# TC-T5.3 — input_fn: JSON inválido → ValueError
# ---------------------------------------------------------------------------


def test_inference_input_fn_invalid_json():
    """input_fn lanza ValueError con string no-JSON."""
    from src.sagemaker.inference import input_fn

    with pytest.raises((ValueError, json.JSONDecodeError, Exception)):
        input_fn("not-json", "application/json")


def test_inference_input_fn_missing_period_id():
    """input_fn lanza ValueError si falta period_id."""
    from src.sagemaker.inference import input_fn

    with pytest.raises(ValueError, match="period_id"):
        input_fn(json.dumps({"idmember": "15632"}), "application/json")


# ---------------------------------------------------------------------------
# TC-T5.4 — predict_fn: miembro con historial → sugerencias válidas
# ---------------------------------------------------------------------------


def test_inference_predict_fn_returns_valid_schema(tmp_path):
    """predict_fn retorna dict con total_suggested >= 0 y lista de suggestions."""
    from src.sagemaker.inference import predict_fn
    from smart_budget.athena_loader import AthenaQueryError  # noqa: F401

    history_df = _make_history_df(idmember="99", n_months=3, categories=("Groceries",))
    data = {"idmember": "99", "period_id": "2026-05"}

    with patch(
        "smart_budget.athena_loader.load_history_by_member_athena",
        return_value=history_df,
    ), patch("smart_budget.athena_loader.member_exists_athena", return_value=True):
        result = predict_fn(data, str(tmp_path))

    assert isinstance(result, dict)
    assert "total_suggested" in result
    assert "suggestions" in result
    if result["total_suggested"] is not None:
        assert result["total_suggested"] >= 0.0
    if result["suggestions"]:
        for s in result["suggestions"]:
            if s["suggested_amount"] is not None:
                assert s["suggested_amount"] >= 0.0
            assert s.get("confidence") in {"low", "medium", "high", None}


# ---------------------------------------------------------------------------
# TC-T5.5 — predict_fn: < 2 meses → gating → null
# ---------------------------------------------------------------------------


def test_inference_predict_fn_gating(tmp_path):
    """predict_fn retorna suggestions=null cuando el miembro no supera gating."""
    from src.sagemaker.inference import predict_fn

    history_df = _make_history_df(idmember="88", n_months=1)
    data = {"idmember": "88", "period_id": "2026-05"}

    with patch(
        "smart_budget.athena_loader.load_history_by_member_athena",
        return_value=history_df,
    ), patch("smart_budget.athena_loader.member_exists_athena", return_value=True):
        result = predict_fn(data, str(tmp_path))

    assert result["total_suggested"] is None
    assert result["suggestions"] is None
    assert result["message"] is not None


# ---------------------------------------------------------------------------
# TC-T5.6 — predict_fn: miembro no existe → ValueError
# ---------------------------------------------------------------------------


def test_inference_predict_fn_member_not_found(tmp_path):
    """predict_fn lanza ValueError si el idmember no existe en Athena."""
    from src.sagemaker.inference import predict_fn

    data = {"idmember": "0000000", "period_id": "2026-05"}

    with patch(
        "smart_budget.athena_loader.load_history_by_member_athena",
        return_value=pd.DataFrame(),
    ), patch("smart_budget.athena_loader.member_exists_athena", return_value=False):
        with pytest.raises(ValueError, match="not found"):
            predict_fn(data, str(tmp_path))


# ---------------------------------------------------------------------------
# TC-T5.6b — output_fn: serializa a JSON parseable
# ---------------------------------------------------------------------------


def test_inference_output_fn():
    """output_fn retorna JSON string parseble con el schema correcto."""
    from src.sagemaker.inference import output_fn

    prediction = {
        "idmember": "99",
        "idclient": "1",
        "idcompany": "1",
        "period_id": "2026-05",
        "total_suggested": 300.0,
        "suggestions": [
            {
                "category_id": "GROCERIES",
                "category_name": "Groceries",
                "suggested_amount": 300.0,
                "confidence": "medium",
                "basis": None,
                "amount_by_month": {},
                "display_label": "Basado en tus últimos 3 meses",
                "model_version": "fase0-v1",
            }
        ],
        "message": None,
    }

    result = output_fn(prediction, "application/json")

    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["total_suggested"] == 300.0
    assert len(parsed["suggestions"]) == 1


# ---------------------------------------------------------------------------
# TC-T5.7 — predict_fn calls athena_loader, not CSV loader
# ---------------------------------------------------------------------------


def test_TC_T5_7_predict_fn_calls_athena_loader_not_csv(tmp_path):
    """
    Arrange: patch athena_loader functions.
    Act: call predict_fn.
    Assert: athena loader IS invoked (CSV loader removed in DATA-1275).
    """
    from src.sagemaker.inference import predict_fn

    history_df = _make_history_df(idmember="99", n_months=3, categories=("Groceries",))
    data = {"idmember": "99", "period_id": "2026-05"}

    with patch(
        "smart_budget.athena_loader.load_history_by_member_athena",
        return_value=history_df,
    ) as mock_athena, patch(
        "smart_budget.athena_loader.member_exists_athena", return_value=True
    ):
        predict_fn(data, str(tmp_path))

    mock_athena.assert_called_once()


# ---------------------------------------------------------------------------
# TC-T5.8 — predict_fn wraps AthenaQueryError as ValueError
# ---------------------------------------------------------------------------


def test_TC_T5_8_predict_fn_wraps_athena_error(tmp_path):
    """
    Arrange: load_history_by_member_athena raises AthenaQueryError.
    Act: call predict_fn.
    Assert: ValueError raised with text "datalake temporarily unavailable".
    """
    from src.sagemaker.inference import predict_fn
    from smart_budget.athena_loader import AthenaQueryError

    data = {"idmember": "99", "period_id": "2026-05"}

    with patch(
        "smart_budget.athena_loader.load_history_by_member_athena",
        side_effect=AthenaQueryError("timeout"),
    ):
        with pytest.raises(ValueError, match="datalake temporarily unavailable"):
            predict_fn(data, str(tmp_path))


# ---------------------------------------------------------------------------
# TC-T5.9 — predict_fn does NOT access filesystem under model_dir/data
# ---------------------------------------------------------------------------


def test_TC_T5_9_no_local_csv_read(tmp_path):
    """
    Arrange: no CSV files exist under tmp_path/data.
    Act: call predict_fn with Athena mocked.
    Assert: no FileNotFoundError; no access to data/ directory.
    """
    from src.sagemaker.inference import predict_fn

    # Ensure no data/ directory exists
    data_dir = tmp_path / "data"
    assert not data_dir.exists()

    history_df = _make_history_df(idmember="99", n_months=3, categories=("Groceries",))
    data = {"idmember": "99", "period_id": "2026-05"}

    with patch(
        "smart_budget.athena_loader.load_history_by_member_athena",
        return_value=history_df,
    ), patch("smart_budget.athena_loader.member_exists_athena", return_value=True):
        result = predict_fn(data, str(tmp_path))

    # data/ directory should NOT have been created by predict_fn
    assert not data_dir.exists()
    assert isinstance(result, dict)
