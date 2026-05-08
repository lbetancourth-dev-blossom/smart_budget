"""
Lógica central del modelo Smart Budget Fase 0 — El Reflejo.

Calcula sugerencias de presupuesto por categoría usando la mediana
de gasto mensual histórico. Sin ML, sin benchmarking, sin recomendaciones.

Referencia: docs/plan_phase_0.md · Steps 2-4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()

MODEL_VERSION = "fase0-v1"

# Umbrales de gating y confidence
MIN_MONTHS_FOR_SUGGESTION = 2
CONFIDENCE_HIGH_THRESHOLD   = 6
CONFIDENCE_MEDIUM_THRESHOLD = 3

# Claves únicas de output
SUGGESTION_UNIQUE_KEY = ["idmember", "category_id", "period_id", "model_version"]


@dataclass
class SuggestionResult:
    """Resultado del modelo para un par (member, categoría)."""

    idmember:           int
    category_id:        int
    period_id:          str                  # formato YYYY-MM
    suggested_amount:   Optional[float]      # None si no pasa el gating
    months_analyzed:    int
    data_points:        int
    period_range:       Optional[str]        # "YYYY-MM ~ YYYY-MM"
    confidence:         Optional[str]        # high | medium | low | None
    display_label:      str
    model_version:      str = field(default=MODEL_VERSION)


# ─── Agregación mensual ────────────────────────────────────────────────────────

def aggregate_monthly_spend(filtered_df: pd.DataFrame) -> pd.DataFrame:
    """Suma el gasto por (idmember, category_id, year_month).

    Args:
        filtered_df: DataFrame ya filtrado por filters.py. Debe tener columnas:
                     idmember, idcategory, processdate, amount.

    Returns:
        DataFrame con columnas: idmember, category_id, year_month, monthly_amount.
    """
    df = filtered_df.copy()
    df["processdate"] = pd.to_datetime(df["processdate"])
    df["year_month"] = df["processdate"].dt.strftime("%Y-%m")

    # Clampear reembolsos: suma neta negativa → 0
    monthly = (
        df.groupby(["idmember", "idcategory", "year_month"], as_index=False)["amount"]
        .sum()
        .rename(columns={"idcategory": "category_id", "amount": "monthly_amount"})
    )
    monthly["monthly_amount"] = monthly["monthly_amount"].clip(lower=0).round(2)

    # Excluir filas con monto 0 (no son data points útiles para la mediana)
    monthly = monthly[monthly["monthly_amount"] > 0]

    log.info(
        "monthly_aggregation_done",
        rows=len(monthly),
        members=int(monthly["idmember"].nunique()),
        categories=int(monthly["category_id"].nunique()),
    )
    return monthly


# ─── Modelo de mediana ─────────────────────────────────────────────────────────

def get_confidence(months_with_data: int) -> Optional[str]:
    """Calcula el nivel de confidence basado en meses con data efectiva.

    Args:
        months_with_data: Número de meses con gasto > 0 en la ventana.

    Returns:
        "high" | "medium" | "low" | None si no pasa el gating.
    """
    if months_with_data < MIN_MONTHS_FOR_SUGGESTION:
        return None
    if months_with_data >= CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if months_with_data >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def get_display_label(months_with_data: int, has_suggestion: bool) -> str:
    """Genera el display_label siguiendo lineamientos UDAAP (neutral, nunca prescriptivo).

    Args:
        months_with_data: Meses con data efectiva usados en el cálculo.
        has_suggestion: Si el gating fue superado.

    Returns:
        Texto descriptivo para mostrar al usuario.
    """
    if not has_suggestion:
        return "No hay suficiente historial para esta categoría"
    return f"Basado en tus últimos {months_with_data} meses"


def calculate_suggestions(
    monthly_df: pd.DataFrame,
    period_id: str,
    n_months: int = 6,
) -> list[SuggestionResult]:
    """Aplica la mediana y el gating para generar sugerencias.

    Para cada (idmember, category_id):
      1. Cuenta meses con gasto > 0 en la ventana
      2. Gating: si count < 2 → no sugerir
      3. suggested_amount = median(monthly_amounts) redondeado a 2 decimales

    Args:
        monthly_df: Output de aggregate_monthly_spend().
        period_id: Período objetivo en formato YYYY-MM.
        n_months: Ventana analizada (para registrar en basis).

    Returns:
        Lista de SuggestionResult (uno por member × categoría).
    """
    results: list[SuggestionResult] = []

    for (member_id, cat_id), group in monthly_df.groupby(["idmember", "category_id"]):
        amounts      = group["monthly_amount"].values
        data_points  = int(len(amounts))
        months_range = f"{group['year_month'].min()} ~ {group['year_month'].max()}"

        confidence = get_confidence(data_points)
        has_suggestion = confidence is not None

        if has_suggestion:
            suggested = round(float(np.median(amounts)), 2)
        else:
            suggested = None

        results.append(SuggestionResult(
            idmember         = int(member_id),
            category_id      = int(cat_id),
            period_id        = period_id,
            suggested_amount = suggested,
            months_analyzed  = n_months,
            data_points      = data_points,
            period_range     = months_range if has_suggestion else None,
            confidence       = confidence,
            display_label    = get_display_label(data_points, has_suggestion),
            model_version    = MODEL_VERSION,
        ))

    with_suggestion    = sum(1 for r in results if r.suggested_amount is not None)
    without_suggestion = len(results) - with_suggestion

    log.info(
        "suggestions_calculated",
        total=len(results),
        with_suggestion=with_suggestion,
        without_suggestion=without_suggestion,
        period_id=period_id,
        model_version=MODEL_VERSION,
    )
    return results


def suggestions_to_dataframe(results: list[SuggestionResult]) -> pd.DataFrame:
    """Convierte lista de SuggestionResult a DataFrame.

    Args:
        results: Output de calculate_suggestions().

    Returns:
        DataFrame con una fila por (member, categoría).
    """
    return pd.DataFrame([vars(r) for r in results])


# ─── Builders de output (budget + budgetcategory) ──────────────────────────────

def build_budget_rows(
    suggestions_df: pd.DataFrame,
    period_table: pd.DataFrame,
    next_budget_id: int = 1,
) -> pd.DataFrame:
    """Construye filas para la tabla `budget` (una por member).

    Args:
        suggestions_df: Output de suggestions_to_dataframe(), solo con sugerencias activas.
        period_table: DataFrame de la tabla period.
        next_budget_id: Primer ID disponible en la tabla budget.

    Returns:
        DataFrame listo para insertar/upsert en budget.
    """
    period_id_db = int(period_table.iloc[0]["id"])  # siempre "monthly" = 1

    rows = []
    budget_id = next_budget_id

    for (member_id, period_id), grp in suggestions_df.groupby(["idmember", "period_id"]):
        amount_limit = round(float(grp["suggested_amount"].sum()), 2)
        rows.append({
            "id":             budget_id,
            "idmember":       int(member_id),
            "idperiod":       period_id_db,
            "name":           f"Smart Budget {period_id}",
            "amountlimit":    amount_limit,
            "startdate":      f"{period_id}-01",
            "enddate":        None,
            "isactive":       True,
            "alertthreshold": None,
            "model_version":  MODEL_VERSION,
            "createdat":      pd.Timestamp.now().isoformat(),
            "updatedat":      pd.Timestamp.now().isoformat(),
            "deletedat":      None,
        })
        budget_id += 1

    return pd.DataFrame(rows)


def build_budgetcategory_rows(
    suggestions_df: pd.DataFrame,
    budget_df: pd.DataFrame,
    default_categories: pd.DataFrame,
    next_id: int = 1,
) -> pd.DataFrame:
    """Construye filas para `budgetcategory` (una por member × categoría).

    Args:
        suggestions_df: Sugerencias activas (suggested_amount IS NOT NULL).
        budget_df: Output de build_budget_rows().
        default_categories: DataFrame de defaultcategory.
        next_id: Primer ID disponible.

    Returns:
        DataFrame listo para insertar/upsert en budgetcategory.
    """
    # Mapas auxiliares
    cat_group  = default_categories.set_index("id")["idcategorygroup"].to_dict()
    cat_slug   = (
        default_categories.set_index("id")["name"]
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "-", regex=True)
        .str.strip("-")
        .to_dict()
    )
    # Extraer period_id desde el nombre "Smart Budget YYYY-MM"
    bdf = budget_df.copy()
    bdf["period_id"] = bdf["name"].str.replace("Smart Budget ", "", regex=False)
    budget_key = bdf.set_index(["idmember", "period_id"])[["id"]].rename(
        columns={"id": "idbudget"}
    )

    rows = []
    row_id = next_id

    for _, s in suggestions_df.iterrows():
        try:
            idbudget = int(budget_key.loc[(int(s["idmember"]), s["period_id"]), "idbudget"])
        except KeyError:
            continue

        rows.append({
            "id":              row_id,
            "idbudget":        idbudget,
            "idcategory":      int(s["category_id"]),
            "idcategorygroup": cat_group.get(int(s["category_id"])),
            "allocatedamount": float(s["suggested_amount"]),
            "categoryslug":    cat_slug.get(int(s["category_id"]), ""),
            "confidence":      s["confidence"],
            "display_label":   s["display_label"],
            "data_points":     int(s["data_points"]),
            "period_range":    s["period_range"],
            "model_version":   MODEL_VERSION,
            "createdat":       pd.Timestamp.now().isoformat(),
            "updatedat":       pd.Timestamp.now().isoformat(),
            "deletedat":       None,
        })
        row_id += 1

    return pd.DataFrame(rows)
