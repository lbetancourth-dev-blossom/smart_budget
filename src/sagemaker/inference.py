"""src/sagemaker/inference.py — Script de inferencia para endpoint SageMaker (DATA-1140).

Este archivo es EXCLUSIVO para SageMaker. No importa ni depende de FastAPI,
uvicorn ni ningún otro framework web. SageMaker maneja el HTTP layer internamente
(gunicorn + Flask propios del container sklearn:1.2-1).

Contrato SageMaker SKLearnModel:
  model_fn(model_dir) → carga artefactos; retorna base_dir como "model"
  input_fn(input_data, content_type) → deserializa JSON request → dict
  predict_fn(data, model) → ejecuta pipeline WMA → dict de sugerencia
  output_fn(prediction, accept) → serializa a JSON string

Reglas de validación (mismas que el endpoint FastAPI local en src/api/router.py):
  Regla 1: Si la cuenta no existe en los datos → ValueError (SageMaker retorna error 400)
  Regla 2: Si la categoría no es válida → ValueError (SageMaker retorna error 400)
  Regla 3: Si cuenta y categoría existen pero sin datos para el período → null en sugerencia

Formato de request (application/json):
  {"idaccount": "EXT2", "defaultcategory": "Food & Dining", "period_id": "2026-05"}

Formato de response (application/json):
  {ver schema acordado en plan.md — idéntico al endpoint FastAPI}
"""

import json
import sys
from pathlib import Path

# Catálogo de categorías válidas — debe estar sincronizado con router.py (Category enum)
_VALID_CATEGORIES = {
    "Auto & Transport",
    "Bills & Utilities",
    "Education",
    "Entertainment & Leisure",
    "Food & Dining",
    "Gas",
    "Gifts & Donations",
    "Groceries",
    "Health & Fitness",
    "Home & Rent",
    "Personal Care & Beauty",
    "Pets",
    "Shopping",
    "Subscriptions",
    "Travel & Trips",
}

_METHOD = "wma"
_TREATMENT = "B"
_LOOKBACK = 3
_MIN_MONTHS_GATING = 2


def model_fn(model_dir: str):
    """
    Retorna base_dir con los CSVs bundleados en model.tar.gz.

    Args:
        model_dir: Directorio donde SageMaker descomprimió model.tar.gz.

    Returns:
        str path a model_dir (contiene los CSVs y el paquete smart_budget/).
    """
    base = Path(model_dir)
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    return str(base)


def input_fn(input_data: str, content_type: str) -> dict:
    """
    Deserializa el request JSON y aplica Regla 2 (categoría válida).

    Args:
        input_data: JSON string con idaccount, defaultcategory, period_id.
        content_type: Debe ser "application/json".

    Returns:
        dict con claves: idaccount, defaultcategory, period_id.

    Raises:
        ValueError: si content_type no es application/json, JSON inválido,
                    o defaultcategory no está en el catálogo válido (Regla 2).
    """
    if content_type != "application/json":
        raise ValueError(
            f"Unsupported content type: {content_type!r}. Expected 'application/json'."
        )
    try:
        data = json.loads(input_data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    # Regla 2: categoría debe estar en el catálogo válido
    category = data.get("defaultcategory", "")
    if category not in _VALID_CATEGORIES:
        raise ValueError(
            f"Invalid defaultcategory: {category!r}. "
            f"Valid values: {sorted(_VALID_CATEGORIES)}"
        )

    return data


def predict_fn(data: dict, model) -> dict:
    """
    Ejecuta load_history → apply_gating → compute_budget_suggestions.

    Aplica las 3 reglas de validación:
      Regla 1: cuenta no existe → ValueError
      Regla 3: cuenta+categoría existen sin datos → retorna null en sugerencia

    Args:
        data: dict con idaccount, defaultcategory, period_id.
        model: base_dir str retornado por model_fn.

    Returns:
        dict con la sugerencia de presupuesto (schema idéntico al endpoint FastAPI).

    Raises:
        ValueError: si la cuenta no existe en los datos (Regla 1).
    """
    import pandas as pd

    from smart_budget.aggregator import apply_gating
    from smart_budget.loader import account_exists, load_history, _synthetic_accounts
    from smart_budget.model import compute_budget_suggestions

    idaccount = data["idaccount"]
    defaultcategory = data["defaultcategory"]
    period_id = data["period_id"]

    base_dir = Path(model) / "data"  # CSVs empacados en data/ dentro del tarball
    reference_date = str(pd.Period(period_id, freq="M") - 1)

    # Limpiar caché para que cada invocación lea los CSVs bundleados
    _synthetic_accounts.cache_clear()

    history = load_history(idaccount, defaultcategory, base_dir)

    # Regla 1 y Regla 3: distinguir cuenta inexistente de combinación sin datos
    if history.empty:
        if not account_exists(idaccount, base_dir):
            # Regla 1: cuenta no existe → error
            raise ValueError(f"idaccount not found: {idaccount!r}")
        # Regla 3a: cuenta existe pero sin datos para esta categoría → null
        return _null_response(idaccount, "", "", defaultcategory, period_id,
                               "No hay datos para esta cuenta y categoría")

    gated = apply_gating(history, min_months=_MIN_MONTHS_GATING)

    # Regla 3b: datos insuficientes (gating < 2 meses) → null
    if gated.empty:
        idclient = str(history["idclient"].iloc[0])
        idcompany = str(history["idcompany"].iloc[0])
        return _null_response(idaccount, idclient, idcompany, defaultcategory, period_id,
                               "No hay suficiente historial para esta categoría")

    results = compute_budget_suggestions(
        gated,
        method=_METHOD,
        treatment=_TREATMENT,
        reference_date=reference_date,
        lookback_months=_LOOKBACK,
    )

    if not results:
        idclient = str(history["idclient"].iloc[0])
        idcompany = str(history["idcompany"].iloc[0])
        return _null_response(idaccount, idclient, idcompany, defaultcategory, period_id,
                               "No hay suficiente historial para esta categoría")

    r = results[0]
    if r.get("suggested_amount") is None:
        idclient = str(history["idclient"].iloc[0])
        idcompany = str(history["idcompany"].iloc[0])
        return _null_response(idaccount, idclient, idcompany, defaultcategory, period_id,
                               "No hay suficiente historial para esta categoría")

    basis_raw = r.get("basis") or {}
    basis = {
        "months_analyzed": basis_raw.get("months_analyzed", 0),
        "months_with_positive_spend": basis_raw.get("months_with_positive_spend", 0),
        "period_range": basis_raw.get("period_range", ""),
        "method": basis_raw.get("method", _METHOD),
        "treatment": basis_raw.get("treatment", _TREATMENT),
    }

    amount_by_month = _build_amount_by_month(gated, reference_date, _LOOKBACK)

    return {
        "idaccount": r["idaccount"],
        "idclient": r["idclient"],
        "idcompany": r["idcompany"],
        "defaultcategory": r["defaultcategory"],
        "period_id": period_id,
        "suggested_amount": round(r["suggested_amount"], 2),
        "confidence": r.get("confidence"),
        "basis": basis,
        "amount_by_month": amount_by_month,
        "display_label": r.get("display_label", ""),
        "model_version": r.get("model_version", "fase0-v1"),
    }


def output_fn(prediction: dict, accept: str) -> str:
    """
    Serializa la respuesta a JSON string.

    Args:
        prediction: dict retornado por predict_fn.
        accept: Tipo de contenido solicitado (ej: "application/json").

    Returns:
        JSON string de la respuesta.
    """
    return json.dumps(prediction, default=str)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _null_response(
    idaccount: str,
    idclient: str,
    idcompany: str,
    defaultcategory: str,
    period_id: str,
    display_label: str,
) -> dict:
    """Construye una respuesta null (Regla 3) con todos los campos del contrato."""
    return {
        "idaccount": idaccount,
        "idclient": idclient,
        "idcompany": idcompany,
        "defaultcategory": defaultcategory,
        "period_id": period_id,
        "suggested_amount": None,
        "confidence": None,
        "basis": None,
        "amount_by_month": None,
        "display_label": display_label,
        "model_version": "fase0-v1",
    }


def _build_amount_by_month(
    history,
    reference_date: str,
    lookback_months: int,
) -> dict:
    """
    Retorna los montos mensuales de la ventana usada para calcular la sugerencia.

    El resultado es un dict ordenado cronológicamente, ej.:
    {"2026-02": 45.00, "2026-03": 0.0, "2026-04": 101.50}

    Args:
        history: DataFrame con columnas period_yyyymm, monthly_total.
        reference_date: Último mes incluido en el historial (YYYY-MM).
        lookback_months: Número de meses en la ventana.

    Returns:
        dict período → monto redondeado a 2 decimales.
    """
    import pandas as pd

    ref = pd.Period(reference_date, freq="M")
    window_start = ref - (lookback_months - 1)

    mask = (history["period_yyyymm"] >= str(window_start)) & (
        history["period_yyyymm"] <= str(ref)
    )
    window = history.loc[mask].set_index("period_yyyymm")["monthly_total"]

    all_periods = [str(window_start + i) for i in range(lookback_months)]
    return {p: round(float(window.get(p, 0.0)), 2) for p in all_periods}
