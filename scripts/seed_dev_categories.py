"""
Seed script — Step 1 de Fase 0: Smart Budget

Toma los datos reales de dev/silver, aplica filtros de calidad,
asigna idcategory a las transacciones y genera datos sintéticos
para completar al menos 6 meses de historial por member.

Output: data/dough/test/  (misma estructura que dev/silver)

Uso:
    python scripts/seed_dev_categories.py
"""

import os
import random
import pandas as pd
import numpy as np
from datetime import date
from dateutil.relativedelta import relativedelta

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

SRC  = os.path.join(os.path.dirname(__file__), "..", "data", "dough", "dev", "silver")
DEST = os.path.join(os.path.dirname(__file__), "..", "data", "dough", "test")

# Ventana de historial para el test
MONTHS_HISTORY = 6
REFERENCE_DATE = date(2026, 5, 1)          # mes en curso (excluido del cálculo)
START_DATE     = REFERENCE_DATE - relativedelta(months=MONTHS_HISTORY)

# Categorías de gasto válidas (grupo 1, shouldshow=True)
EXPENSE_CATEGORY_IDS = [1, 2, 5, 7, 8, 10, 11, 15, 16, 18]

# Patrones de gasto mensual realistas por categoría [min, max, freq_per_month]
CATEGORY_PATTERNS = {
    7:  {"name": "Food & Dining",          "monthly_range": (80,  250), "tx_count": (4, 12)},
    8:  {"name": "Groceries",              "monthly_range": (100, 400), "tx_count": (2, 5)},
    2:  {"name": "Bills & Utilities",      "monthly_range": (80,  200), "tx_count": (1, 3)},
    1:  {"name": "Auto & Transport",       "monthly_range": (30,  150), "tx_count": (2, 6)},
    15: {"name": "Shopping",               "monthly_range": (20,  300), "tx_count": (1, 4)},
    10: {"name": "Health & Fitness",       "monthly_range": (20,  100), "tx_count": (1, 2)},
    11: {"name": "Home & Rent",            "monthly_range": (500, 1500), "tx_count": (1, 2)},
    16: {"name": "Subscriptions",          "monthly_range": (10,  60),  "tx_count": (2, 4)},
    5:  {"name": "Entertainment & Leisure","monthly_range": (15,  120), "tx_count": (1, 3)},
    18: {"name": "Travel & Trips",         "monthly_range": (50,  400), "tx_count": (0, 1)},
}

# Categorías que cada member usará (3-6 categorías por member)
MEMBER_CATEGORIES = {
    2:  [7, 8, 2, 1, 15],
    7:  [7, 8, 16, 10],
    9:  [7, 2, 1, 15, 5],
    18: [8, 2, 11, 16, 10],
    27: [7, 8, 1, 11, 18, 5],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def assign_category_by_amount(amount: float) -> int:
    """Asigna una categoría basada en el monto (heurística para datos reales)."""
    if amount <= 15:
        return random.choice([7, 16])     # Food & Dining, Subscriptions
    elif amount <= 50:
        return random.choice([7, 8, 5])   # Food, Groceries, Entertainment
    elif amount <= 150:
        return random.choice([8, 1, 15])  # Groceries, Transport, Shopping
    elif amount <= 500:
        return random.choice([2, 10, 15]) # Bills, Health, Shopping
    else:
        return random.choice([11, 18])    # Home & Rent, Travel


def months_in_window():
    """Genera los N meses calendario completos de la ventana."""
    months = []
    for i in range(MONTHS_HISTORY):
        m = START_DATE + relativedelta(months=i)
        months.append(date(m.year, m.month, 1))
    return months


def random_day_in_month(year: int, month: int) -> date:
    """Devuelve una fecha aleatoria dentro de un mes."""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, random.randint(1, last_day))


# ─── Carga tablas base ─────────────────────────────────────────────────────────

def load_tables():
    tables = {}
    for name in ["manualtransaction", "manualaccount", "member", "defaultcategory",
                 "membertacacceptance", "budget", "budgetcategory", "period",
                 "company", "companyntropycategory", "account", "memberaccount",
                 "externaltransaction", "accountclassification", "categorygroup",
                 "client", "color", "colorgroup", "companyaccountsubtype",
                 "companytypeaccount", "defaultaccountsubtype", "defaulttypeaccount",
                 "provider", "termandcondition"]:
        path = os.path.join(SRC, f"{name}.csv")
        if os.path.exists(path):
            tables[name] = pd.read_csv(path)
    return tables


# ─── Filtrar transacciones reales ─────────────────────────────────────────────

def filter_real_transactions(mt: pd.DataFrame, ma: pd.DataFrame) -> pd.DataFrame:
    """Filtra manualtransaction a registros usables y asigna idcategory."""
    mt = mt.copy()
    mt["processdate"] = pd.to_datetime(mt["processdate"])

    # Filtros de calidad
    mt = mt[mt["deletedat"].isna()]
    mt = mt[mt["amount"].between(0.50, 2000)]
    mt = mt[mt["processdate"] >= pd.Timestamp(START_DATE)]
    mt = mt[mt["processdate"] <  pd.Timestamp(REFERENCE_DATE)]

    # Solo miembros en scope
    valid_members = set(MEMBER_CATEGORIES.keys())
    mt = mt.merge(ma[["id", "idmember"]], left_on="idmanualaccount", right_on="id",
                  suffixes=("", "_ma"))
    mt = mt[mt["idmember"].isin(valid_members)]

    # Asignar categoría
    mt["idcategory"] = mt["amount"].apply(assign_category_by_amount)

    # Limpiar columnas extra del merge
    mt = mt.drop(columns=["id_ma", "idmember"], errors="ignore")

    print(f"  Transacciones reales filtradas: {len(mt)} filas")
    return mt


# ─── Generar transacciones sintéticas ─────────────────────────────────────────

def generate_synthetic_transactions(ma: pd.DataFrame,
                                    real_mt: pd.DataFrame,
                                    next_id: int) -> pd.DataFrame:
    """
    Genera transacciones sintéticas para completar 6 meses de historial
    en todas las categorías de cada member.
    """
    rows = []
    months = months_in_window()

    for member_id, cat_ids in MEMBER_CATEGORIES.items():
        # Cuenta de meses reales por categoría para este member
        real_by_cat_month = set()
        if len(real_mt) > 0:
            member_real = real_mt.merge(
                ma[["id", "idmember"]], left_on="idmanualaccount", right_on="id"
            )
            member_real = member_real[member_real["idmember"] == member_id]
            for _, row in member_real.iterrows():
                ym = pd.to_datetime(row["processdate"]).strftime("%Y-%m")
                real_by_cat_month.add((int(row["idcategory"]), ym))

        # Obtener manualaccount del member
        member_accounts = ma[ma["idmember"] == member_id]["id"].tolist()
        if not member_accounts:
            continue
        account_id = member_accounts[0]

        for cat_id in cat_ids:
            pattern = CATEGORY_PATTERNS.get(cat_id, {
                "monthly_range": (20, 200), "tx_count": (1, 3)
            })

            for month_start in months:
                ym = month_start.strftime("%Y-%m")

                # Si ya hay datos reales para este member+cat+mes, saltar
                if (cat_id, ym) in real_by_cat_month:
                    continue

                # Generar N transacciones en este mes
                n_tx = random.randint(*pattern["tx_count"])
                if n_tx == 0:
                    continue

                monthly_total = round(
                    random.uniform(*pattern["monthly_range"]), 2
                )
                # Distribuir el monto mensual entre las N transacciones
                splits = np.random.dirichlet(np.ones(n_tx)) * monthly_total

                for amount in splits:
                    tx_date = random_day_in_month(month_start.year, month_start.month)
                    rows.append({
                        "id":                               next_id,
                        "idmanualaccount":                  account_id,
                        "idcategory":                       cat_id,
                        "blossomdoughconsolidatedtransactionid": None,
                        "amount":                           round(float(amount), 2),
                        "balance":                          None,
                        "processdate":                      tx_date.isoformat(),
                        "effectivedate":                    None,
                        "status":                           None,
                        "type":                             None,
                        "description":                      f"[seed] {CATEGORY_PATTERNS.get(cat_id,{}).get('name', cat_id)}",
                        "merchantname":                     None,
                        "note":                             None,
                        "issplit":                          False,
                        "metadata":                         None,
                        "createdat":                        pd.Timestamp.now().isoformat(),
                        "updatedat":                        pd.Timestamp.now().isoformat(),
                        "deletedat":                        None,
                        "_last_cdc_timestamp":              None,
                    })
                    next_id += 1

    synthetic = pd.DataFrame(rows)
    print(f"  Transacciones sintéticas generadas: {len(synthetic)} filas")
    return synthetic


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DEST, exist_ok=True)

    print("📂 Cargando tablas de dev/silver...")
    tables = load_tables()

    mt = tables["manualtransaction"].copy()
    ma = tables["manualaccount"].copy()

    print(f"\n🔍 Filtrando transacciones reales...")
    real_filtered = filter_real_transactions(mt, ma)

    next_id = int(mt["id"].max()) + 1000  # evitar colisión con IDs reales
    print(f"\n🔧 Generando transacciones sintéticas (a partir de id={next_id})...")
    synthetic = generate_synthetic_transactions(ma, real_filtered, next_id)

    # Combinar reales filtradas + sintéticas
    test_mt = pd.concat([real_filtered, synthetic], ignore_index=True)
    test_mt = test_mt.drop_duplicates(subset=["id"])
    print(f"\n✅ manualtransaction total en test: {len(test_mt)} filas")

    # ── Estadísticas por member+categoría+mes ──────────────────────────────────
    test_mt["processdate"] = pd.to_datetime(test_mt["processdate"])
    enriched = test_mt.merge(ma[["id", "idmember"]], left_on="idmanualaccount", right_on="id",
                             suffixes=("", "_ma"))
    enriched["year_month"] = enriched["processdate"].dt.strftime("%Y-%m")

    print("\n📊 Resumen: meses con datos por member × categoría:")
    summary = (
        enriched.groupby(["idmember", "idcategory", "year_month"])["amount"]
        .sum()
        .reset_index()
        .groupby(["idmember", "idcategory"])
        .agg(meses=("year_month", "nunique"), gasto_mediana=("amount", "median"))
        .reset_index()
    )
    print(summary.to_string(index=False))

    # ── Guardar tablas en data/dough/test/ ────────────────────────────────────
    print(f"\n💾 Guardando tablas en {os.path.abspath(DEST)}/")

    # manualtransaction modificada
    test_mt_clean = test_mt.drop(columns=["idmember", "id_ma"], errors="ignore")
    test_mt_clean.to_csv(os.path.join(DEST, "manualtransaction.csv"), index=False)
    print(f"  ✓ manualtransaction.csv ({len(test_mt_clean)} filas)")

    # Tablas de output vacías (listas para recibir el resultado del modelo)
    empty_budget = tables["budget"].iloc[0:0]
    empty_budget.to_csv(os.path.join(DEST, "budget.csv"), index=False)
    print(f"  ✓ budget.csv (vacío — tabla de output)")

    empty_budgetcat = tables["budgetcategory"].iloc[0:0]
    empty_budgetcat.to_csv(os.path.join(DEST, "budgetcategory.csv"), index=False)
    print(f"  ✓ budgetcategory.csv (vacío — tabla de output)")

    # Todas las demás tablas sin modificar
    passthrough = [
        "manualaccount", "member", "defaultcategory", "membertacacceptance",
        "period", "company", "companyntropycategory", "account", "memberaccount",
        "externaltransaction", "accountclassification", "categorygroup",
        "client", "color", "colorgroup", "companyaccountsubtype",
        "companytypeaccount", "defaultaccountsubtype", "defaulttypeaccount",
        "provider", "termandcondition",
    ]
    for name in passthrough:
        if name in tables:
            tables[name].to_csv(os.path.join(DEST, f"{name}.csv"), index=False)
            print(f"  ✓ {name}.csv ({len(tables[name])} filas)")

    print(f"\n✅ Seed completo. Datos listos en: {os.path.abspath(DEST)}/")
    print(f"   Members en scope: {sorted(MEMBER_CATEGORIES.keys())}")
    print(f"   Ventana: {START_DATE} → {REFERENCE_DATE} ({MONTHS_HISTORY} meses completos)")


if __name__ == "__main__":
    main()
