"""src/api/router.py — FastAPI router para Smart Budget (DATA-1179).

Contrato de endpoint (DATA-1179):
  GET /smart-budget/suggestion?idmember=15632&period_id=2026-02
    → 200: MemberSuggestionResponse con array de todas las categorías + total_suggested
    → 404: si idmember no existe
    → nunca 500 por falta de data — devolver suggestions vacío y log

Entorno activo: variable de entorno SB_ENV=dev|alpha (default: dev).
El idmember en Swagger muestra la lista completa de miembros del entorno activo.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import List, Optional, Type

import pandas as pd
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from smart_budget.aggregator import apply_gating
from smart_budget.loader import member_exists, load_history_by_member
from smart_budget.model import compute_budget_suggestions

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Enums para Swagger UI — dropdowns en "Try it out"
# ---------------------------------------------------------------------------

_ENV_CSV: dict[str, str] = {
    "dev":   "smart_budget_db_dev.csv",
    "alpha": "smart_budget_db_alpha.csv",
}

_ACTIVE_ENV: str = os.getenv("SB_ENV", "dev").lower()
_DATA_PATH: Path = (
    Path(os.getenv("SMART_BUDGET_DATA_DIR", "data"))
    / _ENV_CSV.get(_ACTIVE_ENV, _ENV_CSV["dev"])
)


# Top-10 miembros con sugerencias en >1 categoría (pre-calculado por entorno, lb=3)
_IDMEMBERS_DEV = [
    "11393", "9646", "10859", "11001", "11066",
    "12274", "12277", "12284", "12288", "12290",
]
_IDMEMBERS_ALPHA = [
    "385462", "593079", "385543", "385664", "586384",
    "388104", "388305", "385952", "538781", "385640",
]

_members = _IDMEMBERS_ALPHA if _ACTIVE_ENV == "alpha" else _IDMEMBERS_DEV
IdMember: Type[str] = Enum("IdMember", {f"m_{m}": m for m in _members}, type=str)  # type: ignore[return-value]


class PeriodId(str, Enum):
    p_2025_09 = "2025-09"
    p_2025_10 = "2025-10"
    p_2025_11 = "2025-11"
    p_2025_12 = "2025-12"
    p_2026_01 = "2026-01"
    p_2026_02 = "2026-02"
    p_2026_03 = "2026-03"
    p_2026_04 = "2026-04"
    p_2026_05 = "2026-05"
    p_2026_06 = "2026-06"


# ---------------------------------------------------------------------------
# Schemas de respuesta
# ---------------------------------------------------------------------------


class BasisDetail(BaseModel):
    months_analyzed: int
    months_with_spend: int
    period_range: str


class SuggestionItem(BaseModel):
    """Sugerencia de presupuesto para una categoría individual."""

    defaultcategory: str
    suggested_amount: Optional[float]
    confidence: Optional[str]
    basis: Optional[BasisDetail]
    amount_by_month: Optional[dict[str, Optional[float]]]


class MemberSuggestionResponse(BaseModel):
    """Respuesta completa del endpoint: sugerencias de todas las categorías para un miembro."""

    idmember: str
    idclient: str
    idcompany: str
    period_id: str
    method: str
    treatment: str
    model_version: str
    total_suggested: Optional[float]
    suggestions: Optional[List[SuggestionItem]]
    message: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/smart-budget", tags=["Smart Budget"])

_METHOD = "wma"
_TREATMENT = "B"
_LOOKBACK = 3
_MIN_MONTHS_GATING = 2


@router.get("/suggestion", response_model=MemberSuggestionResponse)
def get_suggestion(
    idmember: str = Query(
        ...,
        description="ID del miembro",
        json_schema_extra={"enum": [e.value for e in IdMember]},
    ),
    period_id: PeriodId = Query(..., description="Mes a presupuestar (YYYY-MM)"),
) -> MemberSuggestionResponse:
    """
    Retorna sugerencias de presupuesto para todas las categorías del miembro.

    El entorno de datos (dev/alpha) se configura al iniciar el servidor con `SB_ENV=dev|alpha`.
    La lista de idmember disponibles en este Swagger corresponde al entorno activo.

    Una sola llamada devuelve todas las categorías del miembro para el período.
    El historial considerado son los 3 meses ANTERIORES a period_id (lookback=3,
    reference_date = period_id − 1 mes). Method=WMA, Treatment=B (DATA-1138).
    """
    idmember_val: str = str(idmember)
    period_id_val: str = period_id.value

    # reference_date = period_id − 1 mes (meses ANTERIORES al período a presupuestar)
    reference_date = str(pd.Period(period_id_val, freq="M") - 1)

    log = logger.bind(idmember=idmember_val, period_id=period_id_val, reference_date=reference_date, env=_ACTIVE_ENV)
    log.info("smart_budget.suggestion.start")

    # Cargar historial de todas las categorías del miembro desde el CSV del entorno
    try:
        history = load_history_by_member(idmember_val, _DATA_PATH.parent, csv_name=_DATA_PATH.name)
    except FileNotFoundError:
        log.error("smart_budget.suggestion.base_dir_not_found", data_path=str(_DATA_PATH))
        raise HTTPException(status_code=500, detail=f"data file not found: {_DATA_PATH.name}")

    # Miembro no existe → 404
    if history.empty:
        if not member_exists(idmember_val, _DATA_PATH.parent, csv_name=_DATA_PATH.name):
            log.info("smart_budget.suggestion.not_found")
            raise HTTPException(status_code=404, detail="idmember not found")
        # Miembro existe pero no tiene datos → 200 con null + mensaje
        log.info("smart_budget.suggestion.empty", reason="no_data_for_member")
        return MemberSuggestionResponse(
            idmember=str(idmember_val),
            idclient="",
            idcompany="",
            period_id=period_id_val,
            method=_METHOD,
            treatment=_TREATMENT,
            model_version="fase0-v1",
            total_suggested=None,
            suggestions=None,
            message="No hay datos disponibles para este miembro.",
        )

    # Extraer idclient/idcompany del historial (primer registro)
    idclient = str(history["idclient"].iloc[0])
    idcompany = str(history["idcompany"].iloc[0])

    # Gating: filtrar categorías con datos insuficientes
    gated = apply_gating(history, min_months=_MIN_MONTHS_GATING)

    if gated.empty:
        log.info("smart_budget.suggestion.empty", reason="gating_min_months_all_categories")
        return MemberSuggestionResponse(
            idmember=str(idmember_val),
            idclient=idclient,
            idcompany=idcompany,
            period_id=period_id_val,
            method=_METHOD,
            treatment=_TREATMENT,
            model_version="fase0-v1",
            total_suggested=None,
            suggestions=None,
            message="Not enough history to calculate suggestions. At least 2 months of data required.",
        )

    # Calcular sugerencias para todas las categorías que pasaron gating
    results = compute_budget_suggestions(
        gated,
        method=_METHOD,
        treatment=_TREATMENT,
        reference_date=reference_date,
        lookback_months=_LOOKBACK,
    )

    if not results:
        log.info("smart_budget.suggestion.empty", reason="no_results_in_window")
        return MemberSuggestionResponse(
            idmember=str(idmember_val),
            idclient=idclient,
            idcompany=idcompany,
            period_id=period_id_val,
            method=_METHOD,
            treatment=_TREATMENT,
            model_version="fase0-v1",
            total_suggested=None,
            suggestions=None,
            message="Not enough history to calculate suggestions for the requested period.",
        )

    # Construir items por categoría
    suggestions: list[SuggestionItem] = []
    for r in results:
        basis_data = r.get("basis") or {}
        cat = r.get("defaultcategory", "")

        # amount_by_month: filtrar historial de esta categoría para la ventana
        cat_history = gated[gated["defaultcategory"] == cat] if cat else pd.DataFrame()
        amount_by_month = _build_amount_by_month(cat_history, reference_date, _LOOKBACK)

        amount = r.get("suggested_amount")
        suggestions.append(
            SuggestionItem(
                defaultcategory=cat,
                suggested_amount=round(amount, 2) if amount is not None else None,
                confidence=r.get("confidence"),
                basis=BasisDetail(
                    months_analyzed=basis_data.get("months_analyzed", 0),
                    months_with_spend=basis_data.get("months_with_positive_spend", 0),
                    period_range=basis_data.get("period_range", ""),
                ) if basis_data else None,
                amount_by_month=amount_by_month,
            )
        )

    model_version = results[0].get("model_version", "fase0-v1") if results else "fase0-v1"
    total_suggested = float(results[0].get("total_suggested") or 0.0)

    log.info(
        "smart_budget.suggestion.done",
        n_categories=len(suggestions),
        total_suggested=total_suggested,
    )

    return MemberSuggestionResponse(
        idmember=str(idmember_val),
        idclient=idclient,
        idcompany=idcompany,
        period_id=period_id_val,
        method=_METHOD,
        treatment=_TREATMENT,
        model_version=model_version,
        total_suggested=round(total_suggested, 2),
        suggestions=suggestions,
        message=f"Based on your last {_LOOKBACK} months",
    )


def _build_amount_by_month(
    history: pd.DataFrame,
    reference_date: str,
    lookback_months: int,
) -> dict[str, Optional[float]]:
    """Retorna los montos mensuales de la ventana usada para calcular la sugerencia.

    El resultado es un dict ordenado cronológicamente, ej.:
    {"2026-01": 45.00, "2026-02": 0.0, "2026-03": 101.50}
    Los meses con $0 se muestran como 0.0 (gasto nulo registrado).
    """
    if history.empty:
        ref = pd.Period(reference_date, freq="M")
        window_start = ref - (lookback_months - 1)
        return {str(window_start + i): 0.0 for i in range(lookback_months)}

    ref = pd.Period(reference_date, freq="M")
    window_start = ref - (lookback_months - 1)

    mask = (history["period_yyyymm"] >= str(window_start)) & (
        history["period_yyyymm"] <= str(ref)
    )
    # Agrupar por período para evitar duplicados en el CSV real (idaccount múltiple)
    window = history.loc[mask].groupby("period_yyyymm")["monthly_total"].sum()

    all_periods = [str(window_start + i) for i in range(lookback_months)]
    return {p: round(float(window.get(p, 0.0)), 2) for p in all_periods}
