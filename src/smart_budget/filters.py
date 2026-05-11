"""src/smart_budget/filters.py — Transaction filtering rules for Smart Budget."""
# TODO(prod): add T&C gate (membertacacceptance) before processing — deferred for dev/alpha
import pandas as pd


def filter_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica las 5 reglas de filtrado sobre fact_transactions.

    Reglas (en orden):
        1. deletedat IS NULL (soft delete)
        2. incomeexpenditure == 'expenditure'
        3. defaultcategory NOT IN (None, 'UNCATEGORIZED', 'INCOME')
        4. OLB (SUB/LOAN prefix): status IS NULL ó status NOT IN ('PENDING', 'HOLD')
        5. External (MANT prefix): status == 'POSTED'

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
    df = df[df["defaultcategory"].notna()]
    df = df[~df["defaultcategory"].isin(["UNCATEGORIZED", "INCOME"])]

    # Rules 4 & 5 — A5/A6: status filter by transaction source (idtransaction prefix)
    is_olb = df["idtransaction"].str.startswith(("SUB", "LOAN"))
    is_ext = df["idtransaction"].str.startswith("MANT")

    olb_ok = is_olb & (df["status"].isna() | ~df["status"].isin(["PENDING", "HOLD"]))
    ext_ok = is_ext & (df["status"] == "POSTED")

    df = df[olb_ok | ext_ok]

    return df.reset_index(drop=True)
