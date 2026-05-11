"""scripts/generate_synthetic_dataset.py — Genera dataset sintético para Smart Budget.

Toma los últimos 6 meses del rango disponible, combina miembros existentes
(EXT + OLB) con miembros nuevos sintéticos y asigna montos aleatorios realistas
(algunos ceros para probar gating). Excluye MONEY_SENT.

Output: data/dough/smart_budget_synthetic.csv

Uso:
    python3 scripts/generate_synthetic_dataset.py
    python3 scripts/generate_synthetic_dataset.py --months 6 --output data/dough/custom.csv
"""

import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# Categorías válidas (grupo Expenses del catálogo, excluyendo MONEY_SENT y FEES legacy)
EXPENSE_CATEGORIES = [
    "Auto & Transport",
    "Bills & Utilities",
    "Food & Dining",
    "Groceries",
    "Gas",
    "Health & Fitness",
    "Home & Rent",
    "Shopping",
    "Subscriptions",
    "Entertainment & Leisure",
    "Personal Care & Beauty",
    "Education",
    "Pets",
    "Gifts & Donations",
    "Travel & Trips",
]

# Mapa de nombre de categoría → idcategory (del catálogo defaultcategory)
CATEGORY_ID_MAP: dict[str, str] = {
    "Auto & Transport":       "1",
    "Bills & Utilities":      "2",
    "Food & Dining":          "3",
    "Groceries":              "4",
    "Gas":                    "5",
    "Health & Fitness":       "6",
    "Home & Rent":            "7",
    "Shopping":               "8",
    "Subscriptions":          "9",
    "Entertainment & Leisure": "10",
    "Personal Care & Beauty": "11",
    "Education":              "12",
    "Pets":                   "13",
    "Gifts & Donations":      "14",
    "Travel & Trips":         "15",
}

# Rangos de montos realistas por categoría (min, max, prob_zero)
# prob_zero: probabilidad de que un mes sea $0 (cuenta activa, sin gasto)
CATEGORY_PROFILES = {
    "Auto & Transport":       (50,   300, 0.10),
    "Bills & Utilities":      (60,   200, 0.05),
    "Food & Dining":          (30,   250, 0.15),
    "Groceries":              (80,   400, 0.10),
    "Gas":                    (20,   120, 0.20),
    "Health & Fitness":       (20,   150, 0.30),
    "Home & Rent":            (500, 1800, 0.05),
    "Shopping":               (30,   300, 0.40),
    "Subscriptions":          (10,    80, 0.10),
    "Entertainment & Leisure":(20,   200, 0.35),
    "Personal Care & Beauty": (15,   100, 0.30),
    "Education":              (50,   500, 0.50),
    "Pets":                   (20,   150, 0.45),
    "Gifts & Donations":      (10,   200, 0.50),
    "Travel & Trips":         (50,  1500, 0.65),
}


def random_amount(category: str, rng: np.random.Generator) -> float:
    """Genera un monto mensual aleatorio para una categoría, respetando prob_zero."""
    low, high, prob_zero = CATEGORY_PROFILES[category]
    if rng.random() < prob_zero:
        return 0.0
    # Distribución log-normal cenrada en la media del rango
    mu = (low + high) / 2
    amount = float(rng.uniform(low, high))
    return round(amount, 2)


def build_synthetic_members(
    n_members: int,
    periods: list[str],
    rng: np.random.Generator,
    id_prefix: str = "SYN",
    categories_per_member: tuple[int, int] = (4, 10),
) -> pd.DataFrame:
    """Crea miembros 100% sintéticos con montos aleatorios."""
    rows = []
    for i in range(1, n_members + 1):
        member_id = f"{id_prefix}{i:03d}"
        n_cats = int(rng.integers(*categories_per_member))
        member_cats = random.sample(EXPENSE_CATEGORIES, min(n_cats, len(EXPENSE_CATEGORIES)))
        for cat in member_cats:
            for period in periods:
                rows.append({
                    "idclient":         "1",
                    "idcompany":        "1",
                    "idaccount":         member_id,
                    "idcategory":       CATEGORY_ID_MAP.get(cat, "99"),
                    "defaultcategory":  cat,
                    "period_yyyymm":    period,
                    "monthly_total":    random_amount(cat, rng),
                })
    return pd.DataFrame(rows)


def enrich_existing_members(
    df_existing: pd.DataFrame,
    periods: list[str],
    rng: np.random.Generator,
    extra_categories: int = 4,
) -> pd.DataFrame:
    """Agrega categorías adicionales a los miembros existentes con montos aleatorios."""
    members = df_existing["idaccount"].unique()
    rows = []
    for member_id in members:
        # Categorías que ya tiene este miembro
        existing_cats = set(
            df_existing[df_existing["idaccount"] == member_id]["defaultcategory"].unique()
        )
        # Candidatas: categorías que aún no tiene
        candidates = [c for c in EXPENSE_CATEGORIES if c not in existing_cats]
        if not candidates:
            continue
        n_new = min(extra_categories, len(candidates))
        new_cats = random.sample(candidates, n_new)
        for cat in new_cats:
            for period in periods:
                rows.append({
                    "idclient":         df_existing[df_existing["idaccount"] == member_id]["idclient"].iloc[0],
                    "idcompany":        df_existing[df_existing["idaccount"] == member_id]["idcompany"].iloc[0],
                    "idaccount":         member_id,
                    "idcategory":       CATEGORY_ID_MAP.get(cat, "99"),
                    "defaultcategory":  cat,
                    "period_yyyymm":    period,
                    "monthly_total":    random_amount(cat, rng),
                })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Genera dataset sintético Smart Budget")
    parser.add_argument("--months",   type=int, default=6,  help="Últimos N meses a incluir (default: 6)")
    parser.add_argument("--seed",     type=int, default=42, help="Semilla aleatoria para reproducibilidad")
    parser.add_argument("--new-members", type=int, default=8, help="Miembros sintéticos nuevos (default: 8)")
    parser.add_argument("--extra-cats",  type=int, default=4, help="Categorías extra por miembro existente")
    parser.add_argument(
        "--input",
        default=None,
        help="Path al smart_budget_prep.csv base (auto-detectado si no se especifica)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path de salida (default: data/dough/smart_budget_synthetic.csv)",
    )
    args = parser.parse_args()

    # Auto-detectar ROOT (worktree vs repo principal)
    # Worktree path: <repo>/.worktrees/DATA-1136/scripts/ → subir 3 niveles
    # Repo principal path: <repo>/scripts/ → subir 1 nivel
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent
    # Subir hasta encontrar data/olb/dev/silver (máx 3 niveles)
    for _ in range(3):
        if (root / "data" / "olb" / "dev" / "silver").exists():
            break
        root = root.parent

    input_path  = Path(args.input)  if args.input  else root / "data" / "dough" / "smart_budget_prep.csv"
    output_path = Path(args.output) if args.output else root / "data" / "dough" / "smart_budget_synthetic.csv"

    rng = np.random.default_rng(args.seed)
    random.seed(args.seed)

    print(f"📂 Leyendo: {input_path}")
    df_base = pd.read_csv(input_path)

    # Últimos N meses disponibles
    all_periods = sorted(df_base["period_yyyymm"].unique())
    last_periods = all_periods[-args.months:]
    print(f"📅 Periodos seleccionados ({args.months} meses): {last_periods[0]} → {last_periods[-1]}")

    # Filtrar base a esos períodos y excluir MONEY_SENT / FEES legacy
    EXCLUDED_CATS = {"MONEY_SENT", "FEES"}
    df_filtered = df_base[
        (df_base["period_yyyymm"].isin(last_periods)) &
        (~df_base["defaultcategory"].isin(EXCLUDED_CATS))
    ].copy()
    print(f"✅ Miembros existentes: {df_filtered['idaccount'].nunique()} "
          f"| Categorías: {df_filtered['defaultcategory'].nunique()}")

    # Enriquecer miembros existentes con categorías adicionales
    print(f"➕ Agregando hasta {args.extra_cats} categorías nuevas por miembro existente...")
    df_enriched = enrich_existing_members(df_filtered, last_periods, rng, args.extra_cats)
    print(f"   → {len(df_enriched)} filas nuevas para miembros existentes")

    # Generar miembros sintéticos nuevos
    print(f"🧪 Generando {args.new_members} miembros sintéticos nuevos...")
    df_new = build_synthetic_members(args.new_members, last_periods, rng)
    print(f"   → {len(df_new)} filas para miembros nuevos")

    # Unir todo
    df_final = pd.concat([df_filtered, df_enriched, df_new], ignore_index=True)

    # Ordenar
    df_final = df_final.sort_values(["idaccount", "defaultcategory", "period_yyyymm"]).reset_index(drop=True)

    # Estadísticas de cobertura
    total_members   = df_final["idaccount"].nunique()
    total_cats      = df_final["defaultcategory"].nunique()
    zero_pct        = (df_final["monthly_total"] == 0).mean() * 100
    nonzero_median  = df_final[df_final["monthly_total"] > 0]["monthly_total"].median()

    print()
    print("=" * 60)
    print(f"✅  Dataset sintético generado")
    print(f"   Filas           : {len(df_final):,}")
    print(f"   Miembros        : {total_members} ({df_filtered['idaccount'].nunique()} existentes + {args.new_members} nuevos)")
    print(f"   Categorías      : {total_cats}")
    print(f"   Meses           : {last_periods[0]} → {last_periods[-1]}")
    print(f"   % filas en $0   : {zero_pct:.1f}% (para test de gating)")
    print(f"   Mediana no-cero : ${nonzero_median:.2f}")
    print("=" * 60)
    print()

    # Distribución por miembro
    summary = (
        df_final.groupby("idaccount")
        .agg(
            categorias=("defaultcategory", "nunique"),
            meses=("period_yyyymm", "nunique"),
            meses_con_gasto=("monthly_total", lambda x: (x > 0).sum()),
            median_amount=("monthly_total", lambda x: round(x[x > 0].median(), 2) if (x > 0).any() else 0),
        )
        .reset_index()
    )
    print(summary.to_string(index=False))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(output_path, index=False)
    print(f"\n💾 Guardado en: {output_path}")


if __name__ == "__main__":
    main()
