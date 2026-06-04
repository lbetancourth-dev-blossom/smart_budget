"""src/sagemaker/inference.py — Script de inferencia para endpoint SageMaker (DATA-1179).

Este archivo es EXCLUSIVO para SageMaker. No importa ni depende de FastAPI,
uvicorn ni ningún otro framework web. SageMaker maneja el HTTP layer internamente
(gunicorn + Flask propios del container sklearn:1.2-1).

Contrato SageMaker SKLearnModel:
  model_fn(model_dir) → carga artefactos; retorna base_dir como "model"
  input_fn(input_data, content_type) → deserializa JSON request → dict
  predict_fn(data, model) → ejecuta pipeline WMA → lista de sugerencias por categoría
  output_fn(prediction, accept) → serializa a JSON string

Formato de request (application/json):
  {"idmember": "15632", "period_id": "2026-05"}

Formato de response (application/json):
  {"idmember": "15632", "idclient": "1", "idcompany": "1",
   "period_id": "2026-05", "total_suggested": 292.18,
   "suggestions": [...], "message": null}
"""

import json
import sys
from pathlib import Path

_METHOD = "wma"
_TREATMENT = "B"
_LOOKBACK = 6
_MIN_MONTHS_GATING = 2

# Nombre del CSV bundleado en el tarball (igual en dev y alpha — se empaca con este nombre)
_DATA_CSV = "smart_budget_data.csv"


def model_fn(model_dir: str):
    """
    Añade model_dir al path y lo retorna como identificador del modelo.

    Args:
        model_dir: Directorio donde SageMaker descomprimió model.tar.gz.

    Returns:
        Path al model_dir.
    """
    base = Path(model_dir)
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    return str(base)


def input_fn(input_data: str, content_type: str) -> dict:
    """
    Deserializa el request JSON y valida campos obligatorios.

    Args:
        input_data: JSON string con idmember y period_id.
        content_type: Debe ser "application/json".

    Returns:
        dict con claves: idmember (str), period_id (str).

    Raises:
        ValueError: si content_type incorrecto, JSON inválido, o faltan campos.
    """
    if content_type != "application/json":
        raise ValueError(
            f"Unsupported content type: {content_type!r}. Expected 'application/json'."
        )
    try:
        data = json.loads(input_data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if "idmember" not in data:
        raise ValueError("Missing required field: 'idmember'")
    if "period_id" not in data:
        raise ValueError("Missing required field: 'period_id'")

    return {"idmember": str(data["idmember"]), "period_id": str(data["period_id"])}


def predict_fn(data: dict, model: str) -> dict:
    """
    Ejecuta load_history_by_member → apply_gating → compute_budget_suggestions.

    Retorna todas las categorías del miembro con sugerencias calculadas.

    Args:
        data: dict con idmember y period_id.
        model: base_dir str retornado por model_fn.

    Returns:
        dict con MemberSuggestionResponse completo (todas las categorías).

    Raises:
        ValueError: si idmember no existe en los datos del modelo.
    """
    import pandas as pd

    from smart_budget.aggregator import apply_gating
    from smart_budget.loader import load_history_by_member, member_exists
    from smart_budget.model import compute_budget_suggestions

    idmember = data["idmember"]
    period_id = data["period_id"]

    base_dir = Path(model) / "data"
    reference_date = str(pd.Period(period_id, freq="M") - 1)

    history = load_history_by_member(idmember, base_dir, csv_name=_DATA_CSV)

    if history.empty:
        if not member_exists(idmember, base_dir, csv_name=_DATA_CSV):
            raise ValueError(f"idmember not found: {idmember!r}")
        return _empty_response(idmember, "", "", period_id, "No hay datos para este miembro.")

    idclient = str(history["idclient"].iloc[0])
    idcompany = str(history["idcompany"].iloc[0])

    gated = apply_gating(history, min_months=_MIN_MONTHS_GATING)

    if gated.empty:
        return _empty_response(
            idmember, idclient, idcompany, period_id,
            "Not enough history. At least 2 months of data required.",
        )

    results = compute_budget_suggestions(
        gated,
        method=_METHOD,
        treatment=_TREATMENT,
        reference_date=reference_date,
        lookback_months=_LOOKBACK,
    )

    if not results:
        return _empty_response(
            idmember, idclient, idcompany, period_id,
            "Not enough history for the requested period.",
        )

    suggestions = []
    total = 0.0
    for r in results:
        basis_raw = r.get("basis") or {}
        cat = r.get("defaultcategory", "")
        cat_history = gated[gated["defaultcategory"] == cat] if cat else pd.DataFrame()
        amount = r.get("suggested_amount")
        if amount is not None:
            total += amount
        suggestions.append({
            "defaultcategory": cat,
            "suggested_amount": round(amount, 2) if amount is not None else None,
            "confidence": r.get("confidence"),
            "basis": {
                "months_analyzed": basis_raw.get("months_analyzed", 0),
                "months_with_positive_spend": basis_raw.get("months_with_positive_spend", 0),
                "period_range": basis_raw.get("period_range", ""),
                "method": basis_raw.get("method", _METHOD),
                "treatment": basis_raw.get("treatment", _TREATMENT),
            } if basis_raw else None,
            "amount_by_month": _build_amount_by_month(cat_history, reference_date, _LOOKBACK),
            "display_label": r.get("display_label", ""),
            "model_version": r.get("model_version", "fase0-v1"),
        })

    return {
        "idmember": idmember,
        "idclient": idclient,
        "idcompany": idcompany,
        "period_id": period_id,
        "total_suggested": round(total, 2),
        "suggestions": suggestions,
        "message": None,
    }


def output_fn(prediction: dict, accept: str) -> str:
    """Serializa la respuesta a JSON string."""
    return json.dumps(prediction, default=str)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _empty_response(
    idmember: str, idclient: str, idcompany: str, period_id: str, message: str
) -> dict:
    """Construye una respuesta vacía (sin sugerencias) con mensaje explicativo."""
    return {
        "idmember": idmember,
        "idclient": idclient,
        "idcompany": idcompany,
        "period_id": period_id,
        "total_suggested": None,
        "suggestions": None,
        "message": message,
    }


def _build_amount_by_month(history, reference_date: str, lookback_months: int) -> dict:
    """Retorna montos mensuales de la ventana de lookback agrupados por período."""
    import pandas as pd

    if history.empty:
        ref = pd.Period(reference_date, freq="M")
        window_start = ref - (lookback_months - 1)
        return {str(window_start + i): 0.0 for i in range(lookback_months)}

    ref = pd.Period(reference_date, freq="M")
    window_start = ref - (lookback_months - 1)

    mask = (history["period_yyyymm"] >= str(window_start)) & (
        history["period_yyyymm"] <= str(ref)
    )
    window = history.loc[mask].groupby("period_yyyymm")["monthly_total"].sum()
    all_periods = [str(window_start + i) for i in range(lookback_months)]
    return {p: round(float(window.get(p, 0.0)), 2) for p in all_periods}

