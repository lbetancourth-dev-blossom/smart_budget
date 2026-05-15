"""src/api/inference.py — Script de inferencia para endpoint SageMaker (DATA-1140).

Contrato SageMaker SKLearnModel:
  model_fn(model_dir) → carga artefactos; retorna base_dir como "model"
  input_fn(input_data, content_type) → deserializa JSON request → dict
  predict_fn(data, model) → ejecuta pipeline WMA → dict de sugerencia
  output_fn(prediction, accept) → serializa a JSON string

Reglas de validación (mismas que el endpoint FastAPI local):
  Regla 1: Si la cuenta no existe en los datos → ValueError (SageMaker retorna error 400)
  Regla 2: Si la categoría no es válida → ValueError (SageMaker retorna error 400)
  Regla 3: Si cuenta y categoría existen pero sin datos para el período → null en sugerencia

Formato de request (application/json):
  {"idaccount": "EXT2", "defaultcategory": "Food & Dining", "period_id": "2026-05"}

Formato de response (application/json):
  {ver schema acordado en plan.md}
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


def model_fn(model_dir: str):
    """
    Retorna base_dir con los CSVs bundleados en model.tar.gz.

    Args:
        model_dir: Directorio donde SageMaker descomprimió model.tar.gz.

    Returns:
        str path a model_dir (contiene los CSVs y el paquete smart_budget/).
    """
    base = Path(model_dir)
    # Ensure the smart_budget package inside model_dir is importable
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
        dict con la sugerencia de presupuesto (schema acordado en plan.md).

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

    base_dir = Path(model)
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

    gated = apply_gating(history, min_months=2)

    # Regla 3b: datos insuficientes (gating < 2 meses) → null
    if gated.empty:
        idclient = str(history["idclient"].iloc[0])
        idcompany = str(history["idcompany"].iloc[0])
        return _null_response(idaccount, idclient, idcompany, defaultcategory, period_id,
                               "No hay suficiente historial para esta categoría")

    results = compute_budget_suggestions(
        gated,
        method="wma",
        treatment="B",
        reference_date=reference_date,
        lookback_months=3,
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
        "method": basis_raw.get("method", "wma"),
        "treatment": basis_raw.get("treatment", "B"),
    }

    return {
        "idaccount": r["idaccount"],
        "idclient": r["idclient"],
        "idcompany": r["idcompany"],
        "defaultcategory": r["defaultcategory"],
        "period_id": period_id,
        "suggested_amount": round(r["suggested_amount"], 2),
        "confidence": r.get("confidence"),
        "basis": basis,
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
        "display_label": display_label,
        "model_version": "fase0-v1",
    }


import json
import sys
from pathlib import Path


def model_fn(model_dir: str):
    """
    Retorna base_dir con los CSVs bundleados en model.tar.gz.

    Args:
        model_dir: Directorio donde SageMaker descomprimió model.tar.gz.

    Returns:
        str path a model_dir (contiene los CSVs y el paquete smart_budget/).
    """
    base = Path(model_dir)
    # Ensure the smart_budget package inside model_dir is importable
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    return str(base)


def input_fn(input_data: str, content_type: str) -> dict:
    """
    Deserializa el request JSON.

    Args:
        input_data: JSON string con idaccount, defaultcategory, period_id.
        content_type: Debe ser "application/json".

    Returns:
        dict con claves: idaccount, defaultcategory, period_id.

    Raises:
        ValueError: si content_type no es application/json o JSON inválido.
    """
    if content_type != "application/json":
        raise ValueError(
            f"Unsupported content type: {content_type!r}. Expected 'application/json'."
        )
    try:
        data = json.loads(input_data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc
    return data


def predict_fn(data: dict, model) -> dict:
    """
    Ejecuta load_history → apply_gating → compute_budget_suggestions.

    Args:
        data: dict con idaccount, defaultcategory, period_id.
        model: base_dir str retornado por model_fn.

    Returns:
        dict con la sugerencia de presupuesto (schema acordado en plan.md).
    """
    import pandas as pd

    from smart_budget.aggregator import apply_gating
    from smart_budget.loader import load_history, _synthetic_accounts
    from smart_budget.model import compute_budget_suggestions

    idaccount = data["idaccount"]
    defaultcategory = data["defaultcategory"]
    period_id = data["period_id"]

    base_dir = Path(model)
    reference_date = str(pd.Period(period_id, freq="M") - 1)

    # Clear cache so each invocation loads fresh data from the bundled CSVs
    _synthetic_accounts.cache_clear()

    history = load_history(idaccount, defaultcategory, base_dir)

    if history.empty:
        return {
            "idaccount": idaccount,
            "idclient": "",
            "idcompany": "",
            "defaultcategory": defaultcategory,
            "period_id": period_id,
            "suggested_amount": None,
            "confidence": None,
            "basis": None,
            "display_label": "No hay datos para esta cuenta y categoría",
            "model_version": "fase0-v1",
        }

    gated = apply_gating(history, min_months=2)

    if gated.empty:
        idclient = str(history["idclient"].iloc[0])
        idcompany = str(history["idcompany"].iloc[0])
        return {
            "idaccount": idaccount,
            "idclient": idclient,
            "idcompany": idcompany,
            "defaultcategory": defaultcategory,
            "period_id": period_id,
            "suggested_amount": None,
            "confidence": None,
            "basis": None,
            "display_label": "No hay suficiente historial para esta categoría",
            "model_version": "fase0-v1",
        }

    results = compute_budget_suggestions(
        gated,
        method="wma",
        treatment="B",
        reference_date=reference_date,
        lookback_months=3,
    )

    if not results:
        idclient = str(history["idclient"].iloc[0])
        idcompany = str(history["idcompany"].iloc[0])
        return {
            "idaccount": idaccount,
            "idclient": idclient,
            "idcompany": idcompany,
            "defaultcategory": defaultcategory,
            "period_id": period_id,
            "suggested_amount": None,
            "confidence": None,
            "basis": None,
            "display_label": "No hay suficiente historial para esta categoría",
            "model_version": "fase0-v1",
        }

    r = results[0]
    basis_raw = r.get("basis") or {}
    basis = {
        "months_analyzed": basis_raw.get("months_analyzed", 0),
        "months_with_positive_spend": basis_raw.get("months_with_positive_spend", 0),
        "period_range": basis_raw.get("period_range", ""),
        "method": basis_raw.get("method", "wma"),
        "treatment": basis_raw.get("treatment", "B"),
    }

    return {
        "idaccount": r["idaccount"],
        "idclient": r["idclient"],
        "idcompany": r["idcompany"],
        "defaultcategory": r["defaultcategory"],
        "period_id": period_id,
        "suggested_amount": r.get("suggested_amount"),
        "confidence": r.get("confidence"),
        "basis": basis,
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
