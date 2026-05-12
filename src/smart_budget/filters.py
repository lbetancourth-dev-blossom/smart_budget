"""src/smart_budget/filters.py — Transaction filtering rules for Smart Budget."""
# TODO(prod): add T&C gate (membertacacceptance) before processing — deferred for dev/alpha
import pandas as pd


def filter_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica las 5 reglas de filtrado sobre fact_transactions.

    Reglas (en orden):
        1. deletedat IS NULL (soft delete)
        2. incomeexpenditure == 'expenditure'
        3. defaultcategory NOT IN (None, 'UNCATEGORIZED', 'INCOME', 'MONEY_SENT')
        4. OLB (SUB/LOAN prefix): status IS NULL ó status NOT IN ('PENDING', 'HOLD')
        5. External Dough (EXT prefix, Plaid/Finicity): status == 'POSTED' (case-insensitive)

    Args:
        df: DataFrame con esquema de fact_transactions (columnas en minúsculas).

    Returns:
        DataFrame filtrado. Índice reseteado.
    """
    if df.empty:
        return df.reset_index(drop=True)

    # Rule 1 — A2: exclude soft-deleted rows
    df = df[df["deletedat"].isna()]

    # Rule 2 — A3: only expenditure transactions
    df = df[df["incomeexpenditure"] == "expenditure"]

    # Rule 3 — A4: valid categories only
    # MONEY_SENT excluido: label legacy OLB (Ntropy), equivale a Internal Transfers
    # (grupo 3 = Excluded en defaultcategory). No es gasto discrecional presupuestable.
    EXCLUDED_CATEGORIES = {"UNCATEGORIZED", "INCOME", "MONEY_SENT"}
    df = df[df["defaultcategory"].notna()]
    df = df[~df["defaultcategory"].isin(EXCLUDED_CATEGORIES)]

    # Rules 4 & 5 — A5/A6: status filter by transaction source (idtransaction prefix)
    # OLB (SUB/LOAN): exclude if status IN ('PENDING', 'HOLD')
    # External Dough (EXT, via Plaid/Finicity): exclude if status != 'POSTED'
    # Unknown prefixes: pass through (no status rule defined yet — avoids silent data loss)
    is_olb = df["idtransaction"].str.startswith(("SUB", "LOAN"))
    is_ext = df["idtransaction"].str.startswith("EXT")

    olb_invalid = is_olb & df["status"].notna() & df["status"].str.upper().isin(["PENDING", "HOLD"])
    ext_invalid = is_ext & (df["status"].str.upper() != "POSTED")

    df = df[~(olb_invalid | ext_invalid)]

    return df.reset_index(drop=True)
