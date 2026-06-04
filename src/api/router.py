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


def _build_idmember_enum(csv_path: Path) -> Type[str]:
    """Construye un Enum con hasta 10 idmember que reciben sugerencias en >1 categoría.

    Corre el modelo (wma, lookback=6) sobre todos los miembros del CSV activo y
    retiene solo los que producen sugerencias reales en más de 1 categoría.
    Se ordena por número de categorías sugeridas (descendente) y se limita a 10.

    Si el CSV no existe, retorna un Enum vacío sin romper el startup.
    """
    if not csv_path.exists():
        logger.warning("router.idmember_enum.csv_missing", path=str(csv_path))
        return Enum("IdMember", {}, type=str)  # type: ignore[return-value]

    from smart_budget.aggregator import apply_gating
    from smart_budget.model import compute_budget_suggestions

    df = pd.read_csv(csv_path, dtype=str)
    df["monthly_total"] = pd.to_numeric(df["monthly_total"], errors="coerce").fillna(0.0)

    # Usar el último período disponible como referencia para maximizar cobertura
    last_period = df["period_yyyymm"].dropna().max()
    reference_date = str(pd.Period(last_period, freq="M") - 1)

    qualified: list[tuple[str, int]] = []
    for mid, grp in df.groupby("idmember"):
        try:
            gated = apply_gating(grp, min_months=2)
            if gated.empty:
                continue
            suggestions = compute_budget_suggestions(
                gated, method="wma", treatment="B",
                reference_date=reference_date, lookback_months=6,
            )
            if len(suggestions) > 1:
                qualified.append((str(mid), len(suggestions)))
        except Exception:
            continue  # saltar miembros con colisiones multi-company u otros errores

    qualified.sort(key=lambda x: (-x[1], x[0].zfill(20)))
    members = [m for m, _ in qualified[:10]]
    logger.info(
        "router.idmember_enum.built",
        env=_ACTIVE_ENV, total_qualified=len(qualified), selected=len(members),
    )
    return Enum("IdMember", {f"m_{m}": m for m in members}, type=str)  # type: ignore[return-value]


# Enum dinámico: se construye una sola vez al arrancar el servidor
IdMember: Type[str] = _build_idmember_enum(_DATA_PATH)


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
    months_with_positive_spend: int
    period_range: str
    method: str
    treatment: str


class SuggestionItem(BaseModel):
    """Sugerencia de presupuesto para una categoría individual."""

    defaultcategory: str
    suggested_amount: Optional[float]
    confidence: Optional[str]
    basis: Optional[BasisDetail]
    amount_by_month: Optional[dict[str, Optional[float]]]
    display_label: str
    model_version: str


class MemberSuggestionResponse(BaseModel):
    """Respuesta completa del endpoint: sugerencias de todas las categorías para un miembro."""

    idmember: str
    idclient: str
    idcompany: str
    period_id: str
    total_suggested: Optional[float]
    suggestions: Optional[List[SuggestionItem]]
    message: Optional[str] = None


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
            total_suggested=None,
            suggestions=None,
            message="No hay suficiente historial para calcular sugerencias. Se requieren al menos 2 meses de datos.",
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
            total_suggested=None,
            suggestions=None,
            message="No hay suficiente historial para calcular sugerencias en el período solicitado.",
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
                    months_with_positive_spend=basis_data.get("months_with_positive_spend", 0),
                    period_range=basis_data.get("period_range", ""),
                    method=basis_data.get("method", _METHOD),
                    treatment=basis_data.get("treatment", _TREATMENT),
                ) if basis_data else None,
                amount_by_month=amount_by_month,
                display_label=r.get("display_label", ""),
                model_version=r.get("model_version", "fase0-v1"),
            )
        )

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
        total_suggested=round(total_suggested, 2),
        suggestions=suggestions,
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
