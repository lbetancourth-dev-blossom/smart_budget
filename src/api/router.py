"""src/api/router.py — FastAPI router para Smart Budget (DATA-1140)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from smart_budget.aggregator import apply_gating
from smart_budget.loader import load_history
from smart_budget.model import compute_budget_suggestions

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Schemas de respuesta
# ---------------------------------------------------------------------------


class BasisDetail(BaseModel):
    months_analyzed: int
    months_with_positive_spend: int
    period_range: str
    method: str
    treatment: str


class SuggestionResponse(BaseModel):
    idaccount: str
    idclient: str
    idcompany: str
    defaultcategory: str
    period_id: str
    suggested_amount: Optional[float]
    confidence: Optional[str]
    basis: Optional[BasisDetail]
    amount_by_month: Optional[dict[str, Optional[float]]]
    display_label: str
    model_version: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/smart-budget", tags=["Smart Budget"])

_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")

_METHOD = "wma"
_TREATMENT = "B"
_LOOKBACK = 3
_MIN_MONTHS_GATING = 2


@router.get("/suggestion", response_model=SuggestionResponse)
def get_suggestion(
    idaccount: str = Query(..., description="ID de la cuenta del miembro"),
    defaultcategory: str = Query(..., description="Categoría (ej: GROCERIES)"),
    period_id: str = Query(..., description="Mes a presupuestar (YYYY-MM)"),
) -> SuggestionResponse:
    """
    Calcula y retorna una sugerencia de presupuesto mensual on-demand.

    El historial considerado es los 3 meses ANTERIORES a period_id (lookback=3,
    reference_date = period_id − 1 mes). Method=WMA, Treatment=B (DATA-1138).
    """
    # Paso 1: validar formato period_id
    if not _PERIOD_RE.match(period_id):
        raise HTTPException(
            status_code=422,
            detail=f"period_id debe tener formato YYYY-MM, recibido: {period_id!r}",
        )

    # Paso 2: reference_date = period_id − 1 mes
    reference_date = str(pd.Period(period_id, freq="M") - 1)

    # TODO(prod): hashear idaccount con SHA-256 + SB_LOG_SALT antes de promover a alpha/prod
    log = logger.bind(
        idaccount=idaccount,
        defaultcategory=defaultcategory,
        period_id=period_id,
        reference_date=reference_date,
    )
    log.info("smart_budget.suggestion.start")

    # Paso 3: base_dir desde env var
    base_dir = Path(os.getenv("SMART_BUDGET_DATA_DIR", "data/dough"))

    # Paso 4: cargar historial
    try:
        history = load_history(idaccount, defaultcategory, base_dir)
    except FileNotFoundError:
        log.error("smart_budget.suggestion.base_dir_not_found", base_dir=str(base_dir))
        raise HTTPException(status_code=500, detail="data directory not configured")

    # Paso 5: cuenta no encontrada
    if history.empty:
        log.info("smart_budget.suggestion.not_found")
        raise HTTPException(status_code=404, detail="idaccount not found")

    # Paso 6: gating — mínimo 2 meses con gasto positivo
    gated = apply_gating(history, min_months=_MIN_MONTHS_GATING)

    if gated.empty:
        log.info("smart_budget.suggestion.null", reason="gating_min_months")
        return _build_null_response(idaccount, history, defaultcategory, period_id)

    # Paso 7: compute_budget_suggestions
    results = compute_budget_suggestions(
        gated,
        method=_METHOD,
        treatment=_TREATMENT,
        reference_date=reference_date,
        lookback_months=_LOOKBACK,
    )

    if not results:
        log.info("smart_budget.suggestion.null", reason="no_results_in_window")
        return _build_null_response(idaccount, history, defaultcategory, period_id)

    r = results[0]

    # Paso 8: null suggestion (treatment B all-zeros en ventana)
    if r.get("suggested_amount") is None:
        log.info("smart_budget.suggestion.null", reason="treatment_b_all_zeros")
        return _build_null_response(idaccount, history, defaultcategory, period_id)

    log.info(
        "smart_budget.suggestion.done",
        confidence=r.get("confidence"),
    )

    # Construir amount_by_month desde la ventana de historial usada
    basis = r.get("basis") or {}
    amount_by_month = _build_amount_by_month(gated, reference_date, _LOOKBACK)

    return SuggestionResponse(
        idaccount=r["idaccount"],
        idclient=r["idclient"],
        idcompany=r["idcompany"],
        defaultcategory=r["defaultcategory"],
        period_id=period_id,
        suggested_amount=r["suggested_amount"],
        confidence=r.get("confidence"),
        basis=BasisDetail(
            months_analyzed=basis.get("months_analyzed", 0),
            months_with_positive_spend=basis.get("months_with_positive_spend", 0),
            period_range=basis.get("period_range", ""),
            method=basis.get("method", _METHOD),
            treatment=basis.get("treatment", _TREATMENT),
        ),
        amount_by_month=amount_by_month,
        display_label=r.get("display_label", ""),
        model_version=r.get("model_version", "fase0-v1"),
    )


def _build_null_response(
    idaccount: str,
    history: pd.DataFrame,
    defaultcategory: str,
    period_id: str,
) -> SuggestionResponse:
    """Construye una respuesta null (datos insuficientes) desde el historial disponible."""
    idclient = str(history["idclient"].iloc[0]) if not history.empty else ""
    idcompany = str(history["idcompany"].iloc[0]) if not history.empty else ""
    return SuggestionResponse(
        idaccount=idaccount,
        idclient=idclient,
        idcompany=idcompany,
        defaultcategory=defaultcategory,
        period_id=period_id,
        suggested_amount=None,
        confidence=None,
        basis=None,
        amount_by_month=None,
        display_label="No hay suficiente historial para esta categoría",
        model_version="fase0-v1",
    )


def _build_amount_by_month(
    history: pd.DataFrame,
    reference_date: str,
    lookback_months: int,
) -> dict[str, Optional[float]]:
    """Retorna los montos mensuales de la ventana usada para calcular la sugerencia.

    El resultado es un dict ordenado cronológicamente, ej.:
    {"2026-02": 45.00, "2026-03": 0.0, "2026-04": 101.50}
    Los meses con $0 se muestran como 0.0 (gasto nulo registrado).
    """
    ref = pd.Period(reference_date, freq="M")
    window_start = ref - (lookback_months - 1)

    # Filtrar ventana y construir el dict mes → monto
    mask = (history["period_yyyymm"] >= str(window_start)) & (
        history["period_yyyymm"] <= str(ref)
    )
    window = history.loc[mask].set_index("period_yyyymm")["monthly_total"]

    # Rellenar meses faltantes dentro de la ventana con 0.0
    all_periods = [str(window_start + i) for i in range(lookback_months)]
    return {p: round(float(window.get(p, 0.0)), 2) for p in all_periods}
