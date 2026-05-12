"""src/smart_budget/model.py — Budget suggestion model (DATA-1137).

Pipeline: apply_treatment → compute method → confidence → explanation → JSON dict.
"""
from __future__ import annotations

import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EPSILON_DEFAULT: float = 0.01
EWMA_SPAN_DEFAULT: int = 3

# ---------------------------------------------------------------------------
# Treatment
# ---------------------------------------------------------------------------


def apply_treatment(
    df: pd.DataFrame,
    treatment: str,
    epsilon: float = EPSILON_DEFAULT,
) -> pd.DataFrame:
    """
    Aplica el tratamiento de ceros sobre la columna monthly_total.

    A — include_zeros: sin cambio (retorna copia).
    B — exclude_zeros: filtra filas donde monthly_total == 0.
    C — epsilon_replace: reemplaza monthly_total == 0 por epsilon.

    Raises:
        ValueError: si treatment no está en {"A", "B", "C"}.
    """
    if treatment not in {"A", "B", "C"}:
        raise ValueError(f"treatment must be one of 'A', 'B', 'C' — got {treatment!r}")

    out = df.copy()

    if treatment == "A":
        return out
    elif treatment == "B":
        return out[out["monthly_total"] != 0].reset_index(drop=True)
    else:  # C
        out["monthly_total"] = out["monthly_total"].replace(0.0, epsilon)
        return out


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------


def compute_wma(series: pd.Series) -> float:
    """
    Weighted Moving Average con pesos lineales crecientes [1, 2, ..., n] normalizados.

    Raises:
        ValueError: si series está vacía.
    """
    if len(series) == 0:
        raise ValueError("compute_wma: series must not be empty")

    n = len(series)
    weights = [i for i in range(1, n + 1)]
    total_weight = sum(weights)
    wma = sum(w * v for w, v in zip(weights, series))
    result = round(max(0.0, wma / total_weight), 2)
    return result


def compute_ewma(series: pd.Series, span: int = EWMA_SPAN_DEFAULT) -> float:
    """
    Exponentially Weighted Moving Average con pandas.ewm(span=span, adjust=False).mean().

    Raises:
        ValueError: si series está vacía.
    """
    if len(series) == 0:
        raise ValueError("compute_ewma: series must not be empty")

    ewma_series = series.ewm(span=span, adjust=False).mean()
    value = ewma_series.iloc[-1]
    return round(max(0.0, value), 2)


def compute_holt_winters(series: pd.Series) -> float:
    """
    Holt-Winters con ExponentialSmoothing(trend='add', seasonal=None).

    Raises:
        ValueError: si series tiene menos de 3 observaciones.
    """
    if len(series) < 3:
        raise ValueError(
            f"compute_holt_winters: need at least 3 observations, got {len(series)}"
        )

    model = ExponentialSmoothing(series, trend="add", seasonal=None)
    fit = model.fit()
    forecast = fit.forecast(1)
    value = float(forecast.iloc[0])
    return round(max(0.0, value), 2)


# ---------------------------------------------------------------------------
# Confidence + Explanation
# ---------------------------------------------------------------------------


def compute_confidence(data_points: int) -> str:
    """
    Retorna "high" si data_points >= 6, "medium" si 3-5, "low" si == 2.

    data_points = número de meses con monthly_total > 0 en el df PRE-treatment.
    """
    if data_points >= 6:
        return "high"
    elif data_points >= 3:
        return "medium"
    else:
        return "low"


def build_explanation(
    months_analyzed: int,
    months_with_positive_spend: int,
    confidence: str | None,
) -> str:
    """
    Genera la explicación en lenguaje natural de la sugerencia.
    UDAAP/CFPB compliant — nunca prescriptiva ni comparativa.
    """
    if confidence is None:
        return (
            "No hay datos históricos suficientes para calcular una sugerencia en esta categoría."
        )
    elif confidence == "high":
        return (
            f"En {months_with_positive_spend} de tus últimos {months_analyzed} meses "
            f"tuviste gastos en esta categoría. Esta sugerencia tiene alta confiabilidad."
        )
    elif confidence == "medium":
        return (
            f"En {months_with_positive_spend} de tus últimos {months_analyzed} meses "
            f"tuviste gastos en esta categoría. Esta sugerencia tiene confiabilidad media."
        )
    else:  # "low"
        return (
            f"En {months_with_positive_spend} de tus últimos {months_analyzed} meses "
            f"tuviste gastos en esta categoría. Esta sugerencia está basada en pocos datos "
            f"— revísala antes de confirmarla."
        )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

_NULL_SUGGESTION_REASON = "No hay suficiente historial para calcular el monto sugerido"
_NULL_DISPLAY_LABEL = "No hay suficiente historial para esta categoría"
_NULL_EXPLANATION = (
    "No hay datos históricos suficientes para calcular una sugerencia en esta categoría."
)
_MODEL_VERSION = "fase0-v1"


def _null_suggestion(bucket_meta: dict) -> dict:
    """Build a null-suggestion dict for the given bucket metadata."""
    return {
        "category_id": bucket_meta["idcategory"],
        "defaultcategory": bucket_meta["defaultcategory"],
        "idaccount": bucket_meta["idaccount"],
        "idclient": bucket_meta["idclient"],
        "idcompany": bucket_meta["idcompany"],
        "suggested_amount": None,
        "basis": None,
        "confidence": None,
        "display_label": _NULL_DISPLAY_LABEL,
        "explanation": _NULL_EXPLANATION,
        "model_version": _MODEL_VERSION,
        "reason": _NULL_SUGGESTION_REASON,
    }


def compute_budget_suggestions(
    df: pd.DataFrame,
    method: str,
    treatment: str,
    reference_date: str,
    lookback_months: int | None = None,
    ewma_span: int = EWMA_SPAN_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
) -> list[dict]:
    """
    Función principal. Pipeline por bucket (idaccount × idcategory × defaultcategory):

    1. Filtrar df a los N meses anteriores a reference_date (inclusive)
    2. PRE-treatment basis extraction
    3. apply_treatment
    4. If treatment B and all zeros → null suggestion
    5. Build chronological series
    6. Call method
    7. Clamp negative to 0, round to 2 decimals
    8. Build explanation
    9. Build JSON dict

    Args:
        lookback_months: ventana de meses hacia atrás desde reference_date (inclusive).
            None = usar todos los meses disponibles hasta reference_date.
            Ej: lookback_months=3 con reference_date="2026-05-01" usa: 2026-03, 2026-04, 2026-05.

    Raises:
        ValueError: si method no está en {"wma", "ewma", "holt_winters"}.
    """
    if method not in {"wma", "ewma", "holt_winters"}:
        raise ValueError(f"method must be one of 'wma', 'ewma', 'holt_winters' — got {method!r}")

    if df.empty:
        return []

    # Step 1: filter to months dentro de la ventana de lookback_months hasta reference_date.
    # El mes de reference_date ES incluido (<= es intencional).
    ref_period = pd.Period(reference_date, freq="M")
    df = df.copy()
    df["_period"] = pd.PeriodIndex(df["period_yyyymm"], freq="M")
    df = df[df["_period"] <= ref_period]
    if lookback_months is not None:
        start_period = ref_period - lookback_months + 1
        df = df[df["_period"] >= start_period]
    df = df.drop(columns=["_period"])

    if df.empty:
        return []

    results = []
    bucket_keys = ["idaccount", "idcategory", "defaultcategory"]

    for bucket, df_bucket in df.groupby(bucket_keys, sort=True):
        idaccount, idcategory, defaultcategory = bucket

        # Pull consistent metadata from the bucket
        idclient = str(df_bucket["idclient"].iloc[0])
        idcompany = str(df_bucket["idcompany"].iloc[0])
        bucket_meta = {
            "idaccount": str(idaccount),
            "idcategory": str(idcategory),
            "defaultcategory": str(defaultcategory),
            "idclient": idclient,
            "idcompany": idcompany,
        }

        # Sort chronologically
        df_bucket = df_bucket.sort_values("period_yyyymm").reset_index(drop=True)

        # Step 2: PRE-treatment basis
        months_analyzed = len(df_bucket)
        months_with_zero = int((df_bucket["monthly_total"] == 0.0).sum())
        months_with_positive_spend = int((df_bucket["monthly_total"] > 0.0).sum())
        min_period = df_bucket["period_yyyymm"].min()
        max_period = df_bucket["period_yyyymm"].max()
        period_range = f"{min_period} ~ {max_period}"

        # Step 3: apply_treatment
        df_treated = apply_treatment(df_bucket, treatment, epsilon=epsilon)

        # Step 4: treatment B + all zeros → null
        if treatment == "B" and df_treated.empty:
            results.append(_null_suggestion(bucket_meta))
            continue

        # Step 5: build chronological series
        series = df_treated["monthly_total"].reset_index(drop=True)

        # Confidence and gating (PRE-treatment months_with_positive_spend)
        confidence = compute_confidence(months_with_positive_spend)

        # Step 6: call method
        try:
            if method == "wma":
                value = compute_wma(series)
            elif method == "ewma":
                value = compute_ewma(series, span=ewma_span)
            else:  # holt_winters
                value = compute_holt_winters(series)
        except ValueError:
            results.append(_null_suggestion(bucket_meta))
            continue

        # Step 7: clamp + round (already done inside each compute_* function)
        suggested_amount = value

        # Step 8: build explanation
        explanation = build_explanation(months_analyzed, months_with_positive_spend, confidence)

        # Step 9: build JSON dict
        result = {
            "category_id": str(idcategory),
            "defaultcategory": str(defaultcategory),
            "idaccount": str(idaccount),
            "idclient": idclient,
            "idcompany": idcompany,
            "suggested_amount": suggested_amount,
            "basis": {
                "months_analyzed": months_analyzed,
                "months_with_zero": months_with_zero,
                "months_with_positive_spend": months_with_positive_spend,
                "period_range": period_range,
                "method": method,
                "treatment": treatment,
            },
            "confidence": confidence,
            "display_label": f"Basado en tus últimos {months_analyzed} meses",
            "explanation": explanation,
            "model_version": _MODEL_VERSION,
        }
        results.append(result)

    return results
