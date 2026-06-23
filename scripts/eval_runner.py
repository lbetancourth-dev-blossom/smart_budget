"""scripts/eval_runner.py — CLI to evaluate forecasting methods (DATA-1138).

Usage:
    python scripts/eval_runner.py \\
        [--input data/dough/smart_budget_synthetic.csv] \\
        [--reference-date 2026-03] \\
        [--holdout-month 2026-04] \\
        [--lookbacks 3,6,9,12] \\
        [--output results/eval_results.csv] \\
        [--min-months 3]

Outputs a 16-row CSV (4 methods × 4 lookbacks) with evaluation metrics.
Default dataset: smart_budget_synthetic.csv — 804 rows, sha256 documented in
evaluation_report.md.  Requires the data file to be present locally (gitignored).
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running directly: python scripts/eval_runner.py
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
)

import pandas as pd
import structlog

import sys as _sys

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=_sys.stderr),
)

from smart_budget.aggregator import apply_gating  # noqa: E402
from smart_budget.model import compute_budget_suggestions  # noqa: E402

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEASONAL_CATEGORIES: set[str] = {"Travel & Trips", "Gifts & Donations", "Education"}

_METHODS_DEFAULT: list[str] = ["wma", "ewma", "median", "holt_winters"]
_LOOKBACKS_DEFAULT: list[int] = [3, 6, 9, 12]
_TREATMENT_DEFAULT: str = "B"  # Treatment B only (DATA-1137 decision A7)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _normalize_reference_date(value: str) -> str:
    """Acepta YYYY-MM o YYYY-MM-DD y devuelve siempre YYYY-MM."""
    parts = value.strip().split("-")
    if len(parts) < 2:
        raise ValueError(
            f"--reference-date inválido: {value!r}. Formato esperado: YYYY-MM"
        )
    try:
        year, month = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(
            f"--reference-date inválido: {value!r}. Formato esperado: YYYY-MM"
        )
    if year < 2000 or month < 1 or month > 12:
        raise ValueError(f"--reference-date fuera de rango: {value!r}")
    return f"{year:04d}-{month:02d}"


def _parse_lookbacks(value: str) -> list[int]:
    """Parse a comma-separated string of integers into a list."""
    try:
        return [int(x.strip()) for x in value.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--lookbacks must be comma-separated integers, got: {value!r}"
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Smart Budget suggestion methods — holdout comparison (DATA-1138)",
    )
    parser.add_argument(
        "--input",
        default="data/dough/smart_budget_synthetic.csv",
        metavar="CSV_PATH",
        help="Path to input CSV (default: data/dough/smart_budget_synthetic.csv)",
    )
    parser.add_argument(
        "--reference-date",
        default="2026-03",
        dest="reference_date",
        metavar="YYYY-MM",
        help="Last training month (inclusive). Accepts YYYY-MM or YYYY-MM-DD. (default: 2026-03)",
    )
    parser.add_argument(
        "--holdout-month",
        default="2026-04",
        dest="holdout_month",
        metavar="YYYY-MM",
        help="Holdout actuals month. (default: 2026-04)",
    )
    parser.add_argument(
        "--lookbacks",
        default=[3, 6, 9, 12],
        type=_parse_lookbacks,
        metavar="N,N,...",
        help="Comma-separated lookback windows in months (default: 3,6,9,12)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="CSV_PATH",
        help="Output CSV path (default: stdout)",
    )
    parser.add_argument(
        "--min-months",
        type=int,
        default=3,
        dest="min_months",
        metavar="N",
        help="Minimum months with positive spend for gating (default: 3)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_and_split(
    input_path: str,
    reference_date: str,
    holdout_month: str,
    min_months: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga el CSV de input, aplica gating sobre el train set, separa el holdout.

    Args:
        input_path: ruta al CSV (columnas: idclient, idcompany, idaccount, idcategory,
                    defaultcategory, period_yyyymm, monthly_total)
        reference_date: último mes del train set, formato "YYYY-MM"
        holdout_month: mes de actuals, formato "YYYY-MM"
        min_months: umbral de gating (meses positivos mínimos)

    Returns:
        train_df: DataFrame con columnas del aggregator, periodos <= reference_date,
                  gating aplicado
        actuals_df: DataFrame con columnas [idaccount, idcategory, defaultcategory,
                    monthly_total] para holdout_month
    """
    df = pd.read_csv(input_path)
    # Compatibilidad con CSV generado con schema legacy (pre-DATA-1275)
    df = df.rename(columns={
        "idcategory": "category_id",
        "defaultcategory": "category_name",
        "idaccount": "idmember",  # CSVs pre-DATA-1179 usan idaccount como grain
    })
    if "idclient" not in df.columns:
        df["idclient"] = "1"
    if "idcompany" not in df.columns:
        df["idcompany"] = "1"

    # Train: periods <= reference_date (CSV is pre-aggregated monthly; no aggregate_monthly needed)
    train_df = df[df["period_yyyymm"] <= reference_date].copy()
    train_df = apply_gating(train_df, min_months=min_months)

    # Actuals: rows for holdout month
    actuals_df = (
        df[df["period_yyyymm"] == holdout_month][
            ["idmember", "category_id", "category_name", "monthly_total"]
        ]
        .copy()
        .reset_index(drop=True)
    )

    return train_df, actuals_df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    suggestions: list[dict],
    actuals_df: pd.DataFrame,
    seasonal_categories: set[str] | None = None,
) -> dict[str, float | int]:
    """
    Calcula las 6 métricas de evaluación para una lista de sugerencias.

    Args:
        suggestions: output de compute_budget_suggestions()
                     (keys: idaccount, category_id, defaultcategory, suggested_amount)
        actuals_df: DataFrame con [idaccount, idcategory, defaultcategory, monthly_total]
                    para el mes de holdout
        seasonal_categories: set de nombres de categoría estacional
                             (default: {"Travel & Trips", "Gifts & Donations", "Education"})

    Returns dict con keys:
        n_total_holdout: int  — total buckets in actuals_df
        n_evaluated:     int  — buckets with non-null suggestion AND matching actual
        accuracy_delta:  float — MAE on n_evaluated buckets (primary metric)
        coverage_rate:   float — n_evaluated / n_total_holdout * 100
        null_rate:       float — null_suggestions / total_suggestions * 100
        mape:            float — MAPE on non-zero actuals only (None if no valid buckets)
        mape_n:          int   — number of buckets used for MAPE
        mae_seasonal:    float — MAE on seasonal category buckets only
        mae_regular:     float — MAE on non-seasonal category buckets
        n_seasonal:      int   — seasonal buckets evaluated
        n_regular:       int   — regular buckets evaluated

    Notes:
        - null suggestions are EXCLUDED from accuracy_delta denominator
        - MAPE denominator excludes buckets where actual_spend == 0
        - mae_seasonal / mae_regular use the same null-exclusion rule
        - Suggestion bucket key not found in actuals_df is silently skipped
    """
    if seasonal_categories is None:
        seasonal_categories = SEASONAL_CATEGORIES

    n_total_holdout: int = len(actuals_df)

    # Build lookup: (idmember, category_id, category_name) → monthly_total
    actuals_lookup: dict[tuple[str, str, str], float] = {}
    for _, row in actuals_df.iterrows():
        key = (
            str(row["idmember"]),
            str(row["category_id"]),
            str(row["category_name"]),
        )
        actuals_lookup[key] = float(row["monthly_total"])

    n_suggestions: int = len(suggestions)
    n_null: int = 0

    errors: list[float] = []
    mape_errors: list[float] = []
    seasonal_errors: list[float] = []
    regular_errors: list[float] = []

    for r in suggestions:
        suggested = r.get("suggested_amount")

        if suggested is None:
            n_null += 1
            continue

        # Match by (idmember, category_id, category_name)
        key = (str(r["idmember"]), str(r["category_id"]), str(r["category_name"]))
        if key not in actuals_lookup:
            # Silently skip unmatched suggestions
            continue

        actual = actuals_lookup[key]
        error = abs(float(suggested) - actual)
        errors.append(error)

        # MAPE: exclude zero-actual buckets
        if actual > 0:
            mape_errors.append(abs(float(suggested) - actual) / actual)

        # Seasonal vs regular split
        if str(r["category_name"]) in seasonal_categories:
            seasonal_errors.append(error)
        else:
            regular_errors.append(error)

    n_evaluated = len(errors)
    null_rate = round((n_null / n_suggestions * 100) if n_suggestions > 0 else 0.0, 2)
    coverage_rate = round(
        (n_evaluated / n_total_holdout * 100) if n_total_holdout > 0 else 0.0, 2
    )

    accuracy_delta: float | None = (
        round(sum(errors) / n_evaluated, 2) if n_evaluated > 0 else None
    )

    mape_n = len(mape_errors)
    mape: float | None = (
        round(sum(mape_errors) / mape_n * 100, 2) if mape_n > 0 else None
    )

    n_seasonal = len(seasonal_errors)
    n_regular = len(regular_errors)
    mae_seasonal: float | None = (
        round(sum(seasonal_errors) / n_seasonal, 2) if n_seasonal > 0 else None
    )
    mae_regular: float | None = (
        round(sum(regular_errors) / n_regular, 2) if n_regular > 0 else None
    )

    return {
        "n_total_holdout": n_total_holdout,
        "n_evaluated": n_evaluated,
        "accuracy_delta": accuracy_delta,
        "coverage_rate": coverage_rate,
        "null_rate": null_rate,
        "mape": mape,
        "mape_n": mape_n,
        "mae_seasonal": mae_seasonal,
        "mae_regular": mae_regular,
        "n_seasonal": n_seasonal,
        "n_regular": n_regular,
    }


# ---------------------------------------------------------------------------
# Composite Reliability-Weighted Score (CRWS)
# ---------------------------------------------------------------------------


def compute_composite_score(
    mae_regular: float | None,
    coverage_rate_pct: float,
    null_rate_pct: float,
    lookback_months: int,
    mae_regular_ref: float,
    lb_min: int = 3,
    w_precision: float = 0.65,
    w_coverage: float = 0.35,
) -> float | None:
    """
    Calcula el Composite Reliability-Weighted Score (CRWS) para una configuración.

    Combina precisión sobre categorías regulares, cobertura y robustez ante datos
    escasos en un único número [0, 1]. Mayor CRWS = mejor configuración.

    Formula:
        precision      = max(0, 1 − mae_regular / mae_regular_ref)
        coverage_score = (coverage_rate / 100) × (1 − null_rate / 100)
        sparsity_factor = sqrt(lb_min / lookback_months)
        CRWS = (w_precision × precision + w_coverage × coverage_score) × sparsity_factor

    Decisiones de diseño:
    - Usa mae_regular (no MAE global) para precisión: desacopla el análisis de
      categorías estacionales, que se evalúan por separado con lb=12.
    - data_weight = solo sparsity_factor, sin n_evaluated/n_total: la cobertura ya
      está penalizada en coverage_score — incluirla en data_weight la castigaría dos veces.
    - mae_regular_ref es un valor fijo externo (no el max del grid) para que el score
      sea portable entre distintas ejecuciones del evaluador.

    sparsity_factor (recompensa configuraciones que funcionan con poco historial):
        lb=3  → 1.00  (funciona con solo 3 meses — más universal)
        lb=6  → 0.71
        lb=9  → 0.58
        lb=12 → 0.50  (requiere 1 año completo — menos accesible para usuarios nuevos)

    Args:
        mae_regular: MAE sobre categorías no-estacionales (None si n_regular == 0).
        coverage_rate_pct: porcentaje de buckets holdout con sugerencia no-null.
        null_rate_pct: porcentaje de sugerencias que resultaron null.
        lookback_months: ventana de meses usada por el método.
        mae_regular_ref: referencia fija de MAE para normalización. Se recomienda
            el peor mae_regular observado en el grid de referencia histórico.
        lb_min: lookback mínimo del grid (default 3).
        w_precision: peso del componente de precisión (default 0.65).
        w_coverage: peso del componente de cobertura (default 0.35).

    Returns:
        CRWS en [0, 1], o None si mae_regular es None o mae_regular_ref es 0.
    """
    if mae_regular is None or mae_regular_ref == 0:
        return None

    import math

    precision = max(0.0, 1.0 - mae_regular / mae_regular_ref)
    coverage_score = (coverage_rate_pct / 100.0) * (1.0 - null_rate_pct / 100.0)
    sparsity_factor = math.sqrt(lb_min / lookback_months)

    crws = (w_precision * precision + w_coverage * coverage_score) * sparsity_factor
    return round(crws, 4)


# ---------------------------------------------------------------------------
# Evaluation grid
# ---------------------------------------------------------------------------


def run_evaluation_grid(
    train_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    methods: list[str],
    lookbacks: list[int],
    treatment: str,
    reference_date: str,
    seasonal_categories: set[str] | None = None,
) -> pd.DataFrame:
    """
    Corre compute_budget_suggestions para cada (method, lookback) y computa métricas.

    Returns DataFrame con columnas:
        method, lookback_months, treatment, n_total_holdout, n_evaluated,
        accuracy_delta, coverage_rate_pct, null_rate_pct, mape, mape_n,
        mae_seasonal, mae_regular, n_seasonal, n_regular, crws

    crws (Composite Reliability-Weighted Score): combina precisión, cobertura y
    robustez ante datos escasos en [0,1]. Mayor = mejor.

    Ordenado por accuracy_delta ASC (menor MAE primero; nulls last).
    Treatment is always "B" per decision A7; the parameter is accepted for generality.
    """
    results_list: list[dict] = []

    for method in methods:
        for lb in lookbacks:
            suggestions = compute_budget_suggestions(
                train_df,
                method=method,
                treatment=treatment,
                reference_date=reference_date,
                lookback_months=lb,
            )

            metrics = compute_metrics(suggestions, actuals_df, seasonal_categories)

            row: dict = {
                "method": method,
                "lookback_months": lb,
                "treatment": treatment,
                "n_total_holdout": metrics["n_total_holdout"],
                "n_evaluated": metrics["n_evaluated"],
                "accuracy_delta": metrics["accuracy_delta"],
                "coverage_rate_pct": metrics["coverage_rate"],
                "null_rate_pct": metrics["null_rate"],
                "mape": metrics["mape"],
                "mape_n": metrics["mape_n"],
                "mae_seasonal": metrics["mae_seasonal"],
                "mae_regular": metrics["mae_regular"],
                "n_seasonal": metrics["n_seasonal"],
                "n_regular": metrics["n_regular"],
            }
            results_list.append(row)

    df = pd.DataFrame(results_list)

    # Sort by accuracy_delta ASC (lowest MAE first); NaN rows go last
    df = df.sort_values(
        "accuracy_delta", ascending=True, na_position="last"
    ).reset_index(drop=True)

    # Compute CRWS:
    # - Usa mae_regular (no global) → desacopla estacionales
    # - mae_regular_ref fijo = peor mae_regular del grid actual (portable dentro del run)
    # - data_weight = solo sparsity_factor, sin n_eval/n_total (evita doble castigo a cov)
    lb_min = int(df["lookback_months"].min()) if not df.empty else 3
    mae_regular_ref = float(df["mae_regular"].max(skipna=True)) if not df.empty else 1.0
    df["crws"] = df.apply(
        lambda r: compute_composite_score(
            mae_regular=r["mae_regular"],
            coverage_rate_pct=r["coverage_rate_pct"],
            null_rate_pct=r["null_rate_pct"],
            lookback_months=int(r["lookback_months"]),
            mae_regular_ref=mae_regular_ref,
            lb_min=lb_min,
        ),
        axis=1,
    )

    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    reference_date = _normalize_reference_date(args.reference_date)

    log = logger.bind(
        reference_date=reference_date,
        holdout_month=args.holdout_month,
        n_methods=len(_METHODS_DEFAULT),
        n_lookbacks=len(args.lookbacks),
        input_path=args.input,
    )
    log.info("eval_runner.start")

    # Step 1: load data
    train_df, actuals_df = load_and_split(
        args.input,
        reference_date=reference_date,
        holdout_month=args.holdout_month,
        min_months=args.min_months,
    )

    # Step 2: run evaluation grid
    result_df = run_evaluation_grid(
        train_df=train_df,
        actuals_df=actuals_df,
        methods=_METHODS_DEFAULT,
        lookbacks=args.lookbacks,
        treatment=_TREATMENT_DEFAULT,
        reference_date=reference_date,
    )

    # Step 3: log summary
    best_row = result_df.dropna(subset=["accuracy_delta"]).iloc[0]
    log.info(
        "eval_runner.done",
        n_configurations=len(result_df),
        best_method=best_row["method"],
        best_lookback=int(best_row["lookback_months"]),
        best_accuracy_delta=best_row["accuracy_delta"],
    )

    # Step 4: output CSV
    if args.output is not None:
        result_df.to_csv(args.output, index=False)
    else:
        sys.stdout.write(result_df.to_csv(index=False))


if __name__ == "__main__":
    main()
