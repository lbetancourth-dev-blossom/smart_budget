"""
Orquestador del pipeline Smart Budget Fase 0.

Lee desde data/dough/test/, ejecuta filtros + mediana, escribe
los resultados en budget.csv y budgetcategory.csv del mismo directorio.

Uso:
    python scripts/run_phase0.py [--period YYYY-MM] [--n-months N]
"""

import argparse
import os
import sys

import pandas as pd
import structlog

# Agregar src/ al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from smart_budget.filters import (
    get_expense_category_ids,
    filter_manual_transactions,
    filter_members_with_tac,
)
from smart_budget.aggregator import (
    aggregate_monthly_spend,
    calculate_suggestions,
    suggestions_to_dataframe,
    build_budget_rows,
    build_budgetcategory_rows,
    MODEL_VERSION,
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

DATA_DIR       = os.path.join(os.path.dirname(__file__), "..", "data", "dough", "test")
QUERY_DIR      = os.path.join(DATA_DIR, "query")


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, f"{name}.csv"))


def save(df: pd.DataFrame, name: str) -> None:
    os.makedirs(QUERY_DIR, exist_ok=True)
    path = os.path.join(QUERY_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    log.info("saved", file=f"test/query/{name}.csv", rows=len(df))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Budget Fase 0 pipeline")
    parser.add_argument("--period",   default="2026-05",
                        help="Período objetivo YYYY-MM (default: 2026-05)")
    parser.add_argument("--n-months", type=int, default=6,
                        help="Ventana de meses históricos (default: 6)")
    args = parser.parse_args()

    period_id      = args.period
    n_months       = args.n_months
    reference_date = pd.Timestamp(f"{period_id}-01")

    log.info("pipeline_start", period_id=period_id, n_months=n_months,
             model_version=MODEL_VERSION)

    # ── Carga ──────────────────────────────────────────────────────────────────
    mt   = load("manualtransaction")
    ma   = load("manualaccount")
    dc   = load("defaultcategory")
    tac  = load("membertacacceptance")
    per  = load("period")

    # ── Filtros ────────────────────────────────────────────────────────────────
    expense_cats = get_expense_category_ids(dc)

    filtered = filter_manual_transactions(
        mt, ma, expense_cats, reference_date, n_months
    )

    # Gate T&C
    valid_members = filter_members_with_tac(filtered["idmember"], tac)
    filtered = filtered[filtered["idmember"].isin(valid_members)]
    log.info("after_tac_filter", rows=len(filtered),
             members=int(filtered["idmember"].nunique()))

    if filtered.empty:
        log.warning("no_data_after_filters", period_id=period_id)
        return

    # ── Agregación mensual ─────────────────────────────────────────────────────
    monthly = aggregate_monthly_spend(filtered)
    save(monthly, f"monthly_spend_{period_id}")

    # ── Modelo de mediana + gating ─────────────────────────────────────────────
    results = calculate_suggestions(monthly, period_id=period_id, n_months=n_months)

    suggestions = suggestions_to_dataframe(results)
    active      = suggestions[suggestions["suggested_amount"].notna()].copy()

    # ── Construir output ───────────────────────────────────────────────────────
    existing_budget = load("budget")
    next_budget_id  = int(existing_budget["id"].max()) + 1 if not existing_budget.empty else 1

    budget_rows = build_budget_rows(active, per, next_budget_id)

    existing_bc = load("budgetcategory")
    next_bc_id  = int(existing_bc["id"].max()) + 1 if not existing_bc.empty else 1

    bc_rows = build_budgetcategory_rows(active, budget_rows, dc, next_bc_id)

    # ── Guardar ────────────────────────────────────────────────────────────────
    save(budget_rows, "budget")
    save(bc_rows,     "budgetcategory")

    # ── Reporte final ──────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print(f"  Smart Budget Fase 0 — Período: {period_id}")
    print("="*60)
    print(f"  Members procesados : {int(active['idmember'].nunique())}")
    print(f"  Sugerencias activas: {len(active)}")
    print(f"  Sin sugerencia     : {len(suggestions) - len(active)}")
    print()

    for _, bgt in budget_rows.iterrows():
        member_cats = bc_rows[bc_rows["idbudget"] == bgt["id"]]
        print(f"  Member {int(bgt['idmember'])}  →  Total: ${bgt['amountlimit']:,.2f}")
        for _, cat in member_cats.iterrows():
            dc_name = dc[dc["id"] == cat["idcategory"]]["name"].values
            cat_name = dc_name[0] if len(dc_name) else cat["idcategory"]
            print(f"    • {cat_name:<28} ${cat['allocatedamount']:>8,.2f}"
                  f"  [{cat['confidence']}]  {cat['display_label']}")
        print()

    print(f"  Resultados guardados en: {os.path.abspath(QUERY_DIR)}/")
    print("="*60)


if __name__ == "__main__":
    main()
