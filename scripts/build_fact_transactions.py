"""
build_fact_transactions.py
==========================
Construye la tabla fact_transactions unificando:
  - Transacciones OLB internas (SubAccount + Loan) desde S3 silver
  - Transacciones externas Dough (externaltransaction) desde S3 silver

Sigue la lógica del script de referencia del equipo de DE:
  Downloads/ref_fact_transactions_olb.py

Output: data/dough/fact_transactions.csv

Uso:
    python3 scripts/build_fact_transactions.py
    python3 scripts/build_fact_transactions.py --env alpha
"""

import argparse
import os
import pandas as pd
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
OLB_DIR  = ROOT / "data" / "olb" / "dev" / "silver"
DOUGH_DIR_DEV   = ROOT / "data" / "dough" / "dev"  / "silver"
DOUGH_DIR_ALPHA = ROOT / "data" / "dough" / "alpha" / "silver"
OUT_DIR  = ROOT / "data" / "dough"


def load(folder: Path, table: str) -> pd.DataFrame:
    """Load a CSV table from the given folder; returns empty DataFrame if missing."""
    path = folder / f"{table}.csv"
    if not path.exists():
        print(f"  ⚠️  {path.name} not found — skipping")
        return pd.DataFrame()
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.lower() for c in df.columns]
    return df


def build_sub_transactions(olb: Path) -> pd.DataFrame:
    """
    Reproduce la lógica PySpark de df_txn_sub:
    olbsubaccounttransaction → JOIN olbsubaccount → JOIN olbaccountnumber
      → JOIN olbtransactioninfo → JOIN olbtransactioncategory
    """
    print("→ Cargando tablas OLB (SubAccount)...")
    sat  = load(olb, "olbsubaccounttransaction")
    osa  = load(olb, "olbsubaccount")
    oan  = load(olb, "olbaccountnumber")
    oti  = load(olb, "olbtransactioninfo")
    otc  = load(olb, "olbtransactioncategory")

    if sat.empty:
        print("  ⚠️  olbsubaccounttransaction vacío — sin SUB transactions")
        return pd.DataFrame()

    # Filtrar HOLD
    sat = sat[sat["status"].isna() | (sat["status"] != "HOLD")].copy()
    print(f"  olbsubaccounttransaction: {len(sat):,} filas (post-filter)")

    # JOIN sat → osa
    df = sat.merge(
        osa[["id", "idolbaccountnumber"]].rename(columns={"id": "_osa_id"}),
        left_on="idsubaccount", right_on="_osa_id", how="left"
    )
    # JOIN → oan
    if not oan.empty:
        df = df.merge(
            oan[["id", "idfi"]].rename(columns={"id": "_oan_id"}),
            left_on="idolbaccountnumber", right_on="_oan_id", how="left"
        )
    else:
        df["idfi"] = None

    # JOIN → oti
    if "idolbtransactioninfo" in df.columns and not oti.empty:
        df = df.merge(
            oti[["id", "idolbtransactioncategory", "note"]].rename(columns={"id": "_oti_id"}),
            left_on="idolbtransactioninfo", right_on="_oti_id", how="left"
        )
    else:
        df["idolbtransactioncategory"] = None
        df["note"] = None

    # JOIN → otc
    if "idolbtransactioncategory" in df.columns and not otc.empty:
        df = df.merge(
            otc[["id", "name"]].rename(columns={"id": "_otc_id", "name": "defaultcategory"}),
            left_on="idolbtransactioncategory", right_on="_otc_id", how="left"
        )
    else:
        df["defaultcategory"] = None

    # Construir columnas canonicas
    result = pd.DataFrame({
        "idTransaction"        : "SUB" + df["id"].astype(str),
        "idClient"             : 1,
        "idCompany"            : df.get("idfi", pd.Series([None]*len(df))).astype(str),
        "idAccount"            : "INT" + df["idolbaccountnumber"].astype(str),
        "idSubAccount"         : "SUB" + df["idsubaccount"].astype(str),
        "amount"               : pd.to_numeric(df["amount"], errors="coerce"),
        "currency"             : "USD",
        "originalAmount"       : None,
        "timestamp"            : pd.to_datetime(df["date"], errors="coerce"),
        "date"                 : pd.to_datetime(df["date"], errors="coerce").dt.date,
        "incomeExpenditure"    : df["amount"].apply(lambda a: "expenditure" if float(a or 0) < 0 else "income"),
        "status"               : df["status"],
        "description"          : df.get("description"),
        "balance"              : pd.to_numeric(df.get("balance"), errors="coerce"),
        "isEnriched"           : df.get("isenriched", False),
        "enrichment"           : None,
        "enrichmentLogo"       : None,
        "enrichmentName"       : None,
        "enrichmentLocation"   : None,
        "enrichmentUrl"        : None,
        "defaultCategory"      : df.get("defaultcategory"),
        "idOLBTransactionInfo" : df.get("idolbtransactioninfo", pd.Series([None]*len(df))).astype(str),
        "transactionComplete"  : df.get("transactioncomplete"),
        "note"                 : df.get("note"),
        "checkNumber"          : df.get("checknumber"),
        "isSplit"              : False,
        "splitedTransactions"  : None,
        "createdAt"            : pd.to_datetime(df.get("createdat"), errors="coerce"),
        "deletedAt"            : pd.to_datetime(df.get("deletedat"), errors="coerce"),
        "doughId"              : None,
        "source"               : "OLB_SUB",
    })
    print(f"  ✅ SUB transactions: {len(result):,}")
    return result


def build_loan_transactions(olb: Path) -> pd.DataFrame:
    """
    Reproduce la lógica PySpark de df_txn_loan:
    olbloantransaction → JOIN olbloan → JOIN olbaccountnumber
      → JOIN olbtransactioninfo → JOIN olbtransactioncategory
    """
    print("→ Cargando tablas OLB (Loan)...")
    lt   = load(olb, "olbloantransaction")
    ol   = load(olb, "olbloan")
    oan  = load(olb, "olbaccountnumber")
    oti  = load(olb, "olbtransactioninfo")
    otc  = load(olb, "olbtransactioncategory")

    if lt.empty:
        print("  ⚠️  olbloantransaction vacío — sin LOAN transactions")
        return pd.DataFrame()

    lt = lt[lt["status"].isna() | (lt["status"] != "HOLD")].copy()
    print(f"  olbloantransaction: {len(lt):,} filas (post-filter)")

    # JOIN lt → ol
    if not ol.empty:
        df = lt.merge(
            ol[["id", "idolbaccountnumber"]].rename(columns={"id": "_ol_id"}),
            left_on="idolbloan", right_on="_ol_id", how="left"
        )
    else:
        lt["idolbaccountnumber"] = None
        df = lt

    # JOIN → oan
    if not oan.empty:
        df = df.merge(
            oan[["id", "idfi"]].rename(columns={"id": "_oan_id"}),
            left_on="idolbaccountnumber", right_on="_oan_id", how="left"
        )
    else:
        df["idfi"] = None

    # JOIN → oti
    if "idolbtransactioninfo" in df.columns and not oti.empty:
        df = df.merge(
            oti[["id", "idolbtransactioncategory", "note"]].rename(columns={"id": "_oti_id"}),
            left_on="idolbtransactioninfo", right_on="_oti_id", how="left"
        )
    else:
        df["idolbtransactioncategory"] = None
        df["note"] = None

    # JOIN → otc
    if "idolbtransactioncategory" in df.columns and not otc.empty:
        df = df.merge(
            otc[["id", "name"]].rename(columns={"id": "_otc_id", "name": "defaultcategory"}),
            left_on="idolbtransactioncategory", right_on="_otc_id", how="left"
        )
    else:
        df["defaultcategory"] = None

    # Columna de amount: principalamount (columna puede variar en case)
    amount_col = next((c for c in df.columns if c.lower() == "principalamount"), None)
    if amount_col is None:
        print("  ⚠️  principalAmount no encontrado — usando amount si existe")
        amount_col = "amount" if "amount" in df.columns else None

    result = pd.DataFrame({
        "idTransaction"        : "LOAN" + df["id"].astype(str),
        "idClient"             : 1,
        "idCompany"            : df.get("idfi", pd.Series([None]*len(df))).astype(str),
        "idAccount"            : "INT" + df["idolbaccountnumber"].astype(str),
        "idSubAccount"         : "LOAN" + df["idolbloan"].astype(str),
        "amount"               : pd.to_numeric(df[amount_col], errors="coerce") if amount_col else None,
        "currency"             : "USD",
        "originalAmount"       : None,
        "timestamp"            : pd.to_datetime(df["date"], errors="coerce"),
        "date"                 : pd.to_datetime(df["date"], errors="coerce").dt.date,
        "incomeExpenditure"    : df[amount_col].apply(
                                     lambda a: "expenditure" if float(a or 0) < 0 else "income"
                                 ) if amount_col else None,
        "status"               : df["status"],
        "description"          : df.get("description"),
        "balance"              : pd.to_numeric(df.get("balance"), errors="coerce"),
        "isEnriched"           : df.get("isenriched", False),
        "enrichment"           : None,
        "enrichmentLogo"       : None,
        "enrichmentName"       : None,
        "enrichmentLocation"   : None,
        "enrichmentUrl"        : None,
        "defaultCategory"      : df.get("defaultcategory"),
        "idOLBTransactionInfo" : df.get("idolbtransactioninfo", pd.Series([None]*len(df))).astype(str),
        "transactionComplete"  : df.get("transactioncomplete"),
        "note"                 : df.get("note"),
        "checkNumber"          : None,
        "isSplit"              : False,
        "splitedTransactions"  : None,
        "createdAt"            : pd.to_datetime(df.get("createdat"), errors="coerce"),
        "deletedAt"            : pd.to_datetime(df.get("deletedat"), errors="coerce"),
        "doughId"              : None,
        "source"               : "OLB_LOAN",
    })
    print(f"  ✅ LOAN transactions: {len(result):,}")
    return result


def build_external_transactions(dough: Path) -> pd.DataFrame:
    """
    Transacciones externas de Dough (via Plaid/Finicity).
    Mapea externaltransaction → esquema canónico de fact_transactions.
    """
    print("→ Cargando externaltransaction (DOUGH)...")
    ext = load(dough, "externaltransaction")

    if ext.empty:
        print("  ⚠️  externaltransaction vacío")
        return pd.DataFrame()

    print(f"  externaltransaction: {len(ext):,} filas")

    # amount en externaltransaction puede ser positivo=gasto, negativo=ingreso (Plaid convention)
    amount = pd.to_numeric(ext.get("amount"), errors="coerce")

    result = pd.DataFrame({
        "idTransaction"        : "EXT" + ext["id"].astype(str),
        "idClient"             : 1,
        "idCompany"            : ext.get("idcompany", ext.get("idfi")),
        "idAccount"            : "EXT" + ext.get("idaccount", pd.Series([None]*len(ext))).astype(str),
        "idSubAccount"         : None,
        "amount"               : amount,
        "currency"             : ext.get("currency", "USD"),
        "originalAmount"       : pd.to_numeric(ext.get("originalamount"), errors="coerce"),
        "timestamp"            : pd.to_datetime(ext["date"] if "date" in ext.columns else ext.get("createdat"), errors="coerce"),
        "date"                 : pd.to_datetime(ext["date"] if "date" in ext.columns else ext.get("createdat"), errors="coerce").dt.date,
        "incomeExpenditure"    : amount.apply(lambda a: "expenditure" if float(a or 0) > 0 else "income"),
        "status"               : ext.get("status"),
        "description"          : ext["description"] if "description" in ext.columns else ext.get("name"),
        "balance"              : None,
        "isEnriched"           : ext.get("isenriched", False),
        "enrichment"           : None,
        "enrichmentLogo"       : None,
        "enrichmentName"       : ext.get("merchantname"),
        "enrichmentLocation"   : None,
        "enrichmentUrl"        : None,
        "defaultCategory"      : ext.get("categoryname"),
        "idOLBTransactionInfo" : None,
        "transactionComplete"  : None,
        "note"                 : None,
        "checkNumber"          : None,
        "isSplit"              : False,
        "splitedTransactions"  : None,
        "createdAt"            : pd.to_datetime(ext.get("createdat"), errors="coerce"),
        "deletedAt"            : pd.to_datetime(ext.get("deletedat"), errors="coerce"),
        "doughId"              : ext.get("id").astype(str),
        "source"               : "DOUGH_EXT",
    })
    print(f"  ✅ EXT transactions: {len(result):,}")
    return result


def main(env: str = "dev"):
    dough_dir = DOUGH_DIR_DEV if env == "dev" else DOUGH_DIR_ALPHA

    print(f"\n{'='*60}")
    print(f"  build_fact_transactions — env={env}")
    print(f"{'='*60}\n")

    parts = []

    # 1. OLB SubAccount
    sub = build_sub_transactions(OLB_DIR)
    if not sub.empty:
        parts.append(sub)

    # 2. OLB Loan
    loan = build_loan_transactions(OLB_DIR)
    if not loan.empty:
        parts.append(loan)

    # 3. Dough External
    ext = build_external_transactions(dough_dir)
    if not ext.empty:
        parts.append(ext)

    if not parts:
        print("\n❌ Sin datos — abortando")
        return

    print("\n→ Uniendo todas las fuentes...")
    fact = pd.concat(parts, ignore_index=True)

    # Eliminar duplicados por idTransaction
    before = len(fact)
    fact = fact.drop_duplicates(subset=["idTransaction"])
    print(f"  Deduplicación: {before:,} → {len(fact):,} (eliminados {before - len(fact):,})")

    # Guardar
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "fact_transactions.csv"
    fact.to_csv(out_path, index=False)

    print(f"\n{'='*60}")
    print(f"✅ fact_transactions.csv guardado en: {out_path}")
    print(f"   Total filas   : {len(fact):,}")
    print(f"   Fuentes:")
    for src, grp in fact.groupby("source"):
        print(f"     {src:20s} → {len(grp):,} filas")
    print(f"   Columnas      : {len(fact.columns)}")
    date_col = pd.to_datetime(fact["date"], errors="coerce")
    print(f"   Rango fechas  : {date_col.min().date()} → {date_col.max().date()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build fact_transactions.csv from OLB + DOUGH sources")
    parser.add_argument("--env", default="dev", choices=["dev", "alpha"],
                        help="Environment to use for DOUGH external transactions")
    args = parser.parse_args()
    main(args.env)
