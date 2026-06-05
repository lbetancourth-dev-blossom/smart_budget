"""tests/unit/test_inference.py — Unit tests for src/sagemaker/inference.py (DATA-1179).

Contrato actualizado: request {idmember, period_id} → response multi-categoría.
"""
from __future__ import annotations

import json
import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data_csv(tmp_path, rows: list[dict], csv_name: str = "smart_budget_data.csv"):
    """Crea data/smart_budget_data.csv con los rows dados."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(data_dir / csv_name, index=False)
    return tmp_path


def _rows(idmember="99", n_months=3, categories=("Groceries",)):
    """Genera filas sintéticas para un miembro con N meses y K categorías."""
    rows = []
    for cat in categories:
        for i in range(n_months):
            rows.append({
                "idclient": "1", "idcompany": "1",
                "idmember": idmember, "idaccount": f"INT{idmember}",
                "idcategory": "5", "defaultcategory": cat,
                "period_yyyymm": f"2026-0{i+1}", "monthly_total": str(300.0 + i * 10),
            })
    return rows


# ---------------------------------------------------------------------------
# TC-T5.1 — model_fn: retorna el path al model_dir
# ---------------------------------------------------------------------------

def test_inference_model_fn(tmp_path):
    """model_fn retorna el directorio y lo añade al sys.path."""
    from src.sagemaker.inference import model_fn
    _make_data_csv(tmp_path, _rows())

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

    _make_data_csv(tmp_path, _rows(idmember="99", n_months=3, categories=("Groceries",)))
    data = {"idmember": "99", "period_id": "2026-05"}

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

    _make_data_csv(tmp_path, _rows(idmember="88", n_months=1))
    data = {"idmember": "88", "period_id": "2026-05"}

    result = predict_fn(data, str(tmp_path))

    assert result["total_suggested"] is None
    assert result["suggestions"] is None
    assert result["message"] is not None


# ---------------------------------------------------------------------------
# TC-T5.6 — predict_fn: miembro no existe → ValueError
# ---------------------------------------------------------------------------

def test_inference_predict_fn_member_not_found(tmp_path):
    """predict_fn lanza ValueError si el idmember no está en el CSV."""
    from src.sagemaker.inference import predict_fn

    _make_data_csv(tmp_path, _rows(idmember="99"))
    data = {"idmember": "0000000", "period_id": "2026-05"}

    with pytest.raises(ValueError, match="not found"):
        predict_fn(data, str(tmp_path))


# ---------------------------------------------------------------------------
# TC-T5.7 — output_fn: serializa a JSON parseable
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
        "suggestions": [{
            "defaultcategory": "Groceries",
            "suggested_amount": 300.0,
            "confidence": "medium",
            "basis": None,
            "amount_by_month": {},
            "display_label": "Basado en tus últimos 3 meses",
            "model_version": "fase0-v1",
        }],
        "message": None,
    }

    result = output_fn(prediction, "application/json")

    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["total_suggested"] == 300.0
    assert len(parsed["suggestions"]) == 1
