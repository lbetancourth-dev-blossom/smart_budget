"""src/smart_budget/filters.py — Transaction filtering rules for Smart Budget."""
# TODO(prod): add T&C gate (membertacacceptance) before processing — deferred for dev/alpha
import pandas as pd


def filter_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica las 6 reglas de filtrado sobre fact_transactions.

    Reglas (en orden):
        1. deletedat IS NULL (soft delete)
        2. incomeexpenditure == 'expenditure'  (excluye créditos/ingresos)
        3. defaultcategory NOT IN (None, 'UNCATEGORIZED', 'INCOME', 'MONEY_SENT')
        4. Excluir transacciones LOAN (pagos de préstamos — no son gasto discrecional)
        5. OLB (SUB prefix): status IS NULL ó status NOT IN ('PENDING', 'HOLD')
        6. External Dough (EXT prefix, Plaid/Finicity): status == 'POSTED' (case-insensitive)

    Args:
        df: DataFrame con esquema de fact_transactions (columnas en minúsculas).

    Returns:
        DataFrame filtrado. Índice reseteado.
    """
    if df.empty:
        return df.reset_index(drop=True)

    # Rule 1 — A2: exclude soft-deleted rows
    df = df[df["deletedat"].isna()]

    # Rule 2 — A3: only expenditure transactions (excluye créditos e ingresos)
    df = df[df["incomeexpenditure"] == "expenditure"]

    # Rule 3 — A4: valid categories only
    # MONEY_SENT excluido: label legacy OLB (Ntropy), equivale a Internal Transfers
    # (grupo 3 = Excluded en defaultcategory). No es gasto discrecional presupuestable.
    EXCLUDED_CATEGORIES = {"UNCATEGORIZED", "INCOME", "MONEY_SENT"}
    df = df[df["defaultcategory"].notna()]
    df = df[~df["defaultcategory"].isin(EXCLUDED_CATEGORIES)]

    # Rule 4 — excluir transacciones LOAN
    # Los pagos de préstamos (LOAN prefix) son obligaciones financieras fijas,
    # no gasto discrecional. No deben influir en sugerencias de presupuesto.
    df = df[~df["idtransaction"].str.startswith("LOAN")]

    # Rules 5 & 6 — A5/A6: status filter by transaction source (idtransaction prefix)
    # OLB (SUB): exclude if status IN ('PENDING', 'HOLD')
    # External Dough (EXT, via Plaid/Finicity): exclude if status != 'POSTED'
    # Unknown prefixes: pass through (no status rule defined yet — avoids silent data loss)
    is_sub = df["idtransaction"].str.startswith("SUB")
    is_ext = df["idtransaction"].str.startswith("EXT")

    sub_invalid = is_sub & df["status"].notna() & df["status"].str.upper().isin(["PENDING", "HOLD"])
    ext_invalid = is_ext & (df["status"].str.upper() != "POSTED")

    df = df[~(sub_invalid | ext_invalid)]

    return df.reset_index(drop=True)
