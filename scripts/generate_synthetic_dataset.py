"""scripts/generate_synthetic_dataset.py — Genera dataset sintético para Smart Budget.

Toma los últimos N meses del rango disponible, combina miembros existentes
(EXT + OLB) con miembros nuevos sintéticos y asigna montos aleatorios realistas
(algunos ceros para probar gating). Excluye MONEY_SENT.

Con --extend-months M genera M meses sintéticos PREVIOS al inicio del CSV base,
aplicando patrones estacionales en categorías clave (Travel, Gifts, Entertainment).

Output: data/dough/smart_budget_synthetic.csv

Uso:
    python3 scripts/generate_synthetic_dataset.py
    python3 scripts/generate_synthetic_dataset.py --months 6 --output data/dough/custom.csv
    python3 scripts/generate_synthetic_dataset.py --extend-months 6   # genera 12 meses total
"""
from __future__ import annotations

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


def random_amount(category: str, rng: np.random.Generator, seasonal_mult: float = 1.0) -> float:
    """Genera un monto mensual aleatorio para una categoría, respetando prob_zero.

    Args:
        category: Nombre de la categoría.
        rng: Generador de números aleatorios.
        seasonal_mult: Multiplicador estacional (1.0 = normal, >1 = temporada alta, 0 = forzar $0).
    """
    low, high, prob_zero = CATEGORY_PROFILES[category]
    # seasonal_mult=0 fuerza $0 (temporada baja sin gasto)
    if seasonal_mult == 0.0 or rng.random() < prob_zero:
        return 0.0
    amount = float(rng.uniform(low, high)) * seasonal_mult
    return round(amount, 2)


# ---------------------------------------------------------------------------
# Patrones estacionales para categorías clave
# Formato: {mes (1-12): multiplicador}
# ---------------------------------------------------------------------------
SEASONAL_PATTERNS: dict[str, dict[int, float]] = {
    # Viajes: verano (jun-ago) y diciembre → alto; ene-mar → casi sin gasto
    "Travel & Trips": {
        1: 0.0, 2: 0.0, 3: 0.0, 4: 0.4, 5: 0.6,
        6: 2.0, 7: 2.5, 8: 2.0, 9: 0.8, 10: 0.6,
        11: 0.5, 12: 1.8,
    },
    # Regalos: noviembre y diciembre disparados; febrero (San Valentín) moderado; rest bajo
    "Gifts & Donations": {
        1: 0.3, 2: 0.8, 3: 0.3, 4: 0.3, 5: 0.3,
        6: 0.6, 7: 0.3, 8: 0.3, 9: 0.3, 10: 0.5,
        11: 2.0, 12: 3.0,
    },
    # Entretenimiento: verano y diciembre altos
    "Entertainment & Leisure": {
        1: 0.6, 2: 0.6, 3: 0.7, 4: 0.8, 5: 0.9,
        6: 1.3, 7: 1.5, 8: 1.3, 9: 1.0, 10: 1.0,
        11: 1.0, 12: 1.4,
    },
}


def build_synthetic_members(
    n_members: int,
    periods: list[str],
    rng: np.random.Generator,
    id_prefix: str = "SYN",
    categories_per_member: tuple[int, int] = (4, 10),
    member_category_map: dict | None = None,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Crea miembros 100% sintéticos con montos aleatorios.

    Returns:
        (DataFrame con filas, dict {member_id: [categorías asignadas]})
        El dict permite reutilizar la misma asignación de categorías para periodos previos.
    """
    rows = []
    assigned: dict[str, list[str]] = {}
    for i in range(1, n_members + 1):
        member_id = f"{id_prefix}{i:03d}"
        if member_category_map and member_id in member_category_map:
            member_cats = member_category_map[member_id]
        else:
            n_cats = int(rng.integers(*categories_per_member))
            member_cats = random.sample(EXPENSE_CATEGORIES, min(n_cats, len(EXPENSE_CATEGORIES)))
        assigned[member_id] = member_cats
        for cat in member_cats:
            for period in periods:
                month = int(period.split("-")[1])
                mult = SEASONAL_PATTERNS.get(cat, {}).get(month, 1.0)
                rows.append({
                    "idclient":         "1",
                    "idcompany":        "1",
                    "idaccount":         member_id,
                    "idcategory":       CATEGORY_ID_MAP.get(cat, "99"),
                    "defaultcategory":  cat,
                    "period_yyyymm":    period,
                    "monthly_total":    random_amount(cat, rng, mult),
                })
    return pd.DataFrame(rows), assigned


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
                month = int(period.split("-")[1])
                mult = SEASONAL_PATTERNS.get(cat, {}).get(month, 1.0)
                rows.append({
                    "idclient":         df_existing[df_existing["idaccount"] == member_id]["idclient"].iloc[0],
                    "idcompany":        df_existing[df_existing["idaccount"] == member_id]["idcompany"].iloc[0],
                    "idaccount":         member_id,
                    "idcategory":       CATEGORY_ID_MAP.get(cat, "99"),
                    "defaultcategory":  cat,
                    "period_yyyymm":    period,
                    "monthly_total":    random_amount(cat, rng, mult),
                })
    return pd.DataFrame(rows)


def extend_existing_members_back(
    df_existing: pd.DataFrame,
    prior_periods: list[str],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Genera filas históricas previas para los miembros existentes.

    Usa las mismas categorías que ya tiene cada miembro en df_existing,
    aplicando patrones estacionales para categorías clave.
    """
    rows = []
    for member_id in df_existing["idaccount"].unique():
        member_df = df_existing[df_existing["idaccount"] == member_id]
        cats = member_df["defaultcategory"].unique()
        idclient = member_df["idclient"].iloc[0]
        idcompany = member_df["idcompany"].iloc[0]
        for cat in cats:
            idcat = member_df[member_df["defaultcategory"] == cat]["idcategory"].iloc[0]
            for period in prior_periods:
                month = int(period.split("-")[1])
                mult = SEASONAL_PATTERNS.get(cat, {}).get(month, 1.0)
                rows.append({
                    "idclient":        idclient,
                    "idcompany":       idcompany,
                    "idaccount":        member_id,
                    "idcategory":      idcat,
                    "defaultcategory": cat,
                    "period_yyyymm":   period,
                    "monthly_total":   random_amount(cat, rng, mult),
                })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Genera dataset sintético Smart Budget")
    parser.add_argument("--months",   type=int, default=6,  help="Últimos N meses a incluir (default: 6)")
    parser.add_argument("--extend-months", type=int, default=0,
                        help="Genera N meses sintéticos PREVIOS al inicio del CSV base (default: 0). "
                             "Usar 6 para llegar a 12 meses totales.")
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
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent
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

    # Últimos N meses disponibles en el CSV base
    all_periods = sorted(df_base["period_yyyymm"].unique())
    last_periods = all_periods[-args.months:]
    print(f"📅 Periodos base ({args.months} meses): {last_periods[0]} → {last_periods[-1]}")

    # Filtrar base a esos períodos y excluir MONEY_SENT / FEES legacy
    EXCLUDED_CATS = {"MONEY_SENT", "FEES"}
    df_filtered = df_base[
        (df_base["period_yyyymm"].isin(last_periods)) &
        (~df_base["defaultcategory"].isin(EXCLUDED_CATS))
    ].copy()
    # Normalizar nombres de categorías a Title Case para consistencia con CATEGORY_PROFILES
    df_filtered["defaultcategory"] = df_filtered["defaultcategory"].str.title().str.strip()
    df_filtered = df_filtered[df_filtered["defaultcategory"].isin(EXPENSE_CATEGORIES)]
    print(f"✅ Miembros existentes: {df_filtered['idaccount'].nunique()} "
          f"| Categorías: {df_filtered['defaultcategory'].nunique()}")

    # Enriquecer miembros existentes con categorías adicionales (periodos base)
    print(f"➕ Agregando hasta {args.extra_cats} categorías nuevas por miembro existente...")
    df_enriched = enrich_existing_members(df_filtered, last_periods, rng, args.extra_cats)
    print(f"   → {len(df_enriched)} filas nuevas para miembros existentes")

    # Generar miembros sintéticos nuevos (periodos base) — guarda asignación de categorías
    print(f"🧪 Generando {args.new_members} miembros sintéticos nuevos...")
    df_new, syn_cat_map = build_synthetic_members(args.new_members, last_periods, rng)
    print(f"   → {len(df_new)} filas para miembros nuevos")

    # Generar meses históricos previos (extend-months), usando la MISMA asignación de categorías
    df_prior = pd.DataFrame()
    if args.extend_months > 0:
        first_period = pd.Period(last_periods[0], freq="M")
        prior_periods = [
            str(first_period - i) for i in range(args.extend_months, 0, -1)
        ]
        print(f"⏪ Generando {args.extend_months} meses previos: {prior_periods[0]} → {prior_periods[-1]}")
        df_prior_existing = extend_existing_members_back(df_filtered, prior_periods, rng)
        df_prior_syn, _ = build_synthetic_members(
            args.new_members, prior_periods, rng,
            member_category_map=syn_cat_map,  # mismas categorías que en base
        )
        df_prior = pd.concat([df_prior_existing, df_prior_syn], ignore_index=True)
        print(f"   → {len(df_prior):,} filas históricas generadas")

    # Unir todo: historial previo + base filtrada + enriquecimiento + nuevos
    df_final = pd.concat([df_prior, df_filtered, df_enriched, df_new], ignore_index=True)

    # Ordenar
    df_final = df_final.sort_values(["idaccount", "defaultcategory", "period_yyyymm"]).reset_index(drop=True)

    # Estadísticas de cobertura
    all_final_periods = sorted(df_final["period_yyyymm"].unique())
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
    print(f"   Meses           : {all_final_periods[0]} → {all_final_periods[-1]} ({len(all_final_periods)} meses)")
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
