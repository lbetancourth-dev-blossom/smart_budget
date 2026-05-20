"""
build_fact_transactions.py
==========================
Construye la tabla fact_transactions. Soporta dos modos:

  --source db   (recomendado) Lee directo de blossom-dough-consolidated-dev.
                Garantiza datos idénticos a los del equipo de DE.
                Requiere variables de entorno o argumentos de conexión.

  --source s3   Construye desde S3 silver (OLB + DOUGH). Útil offline.
                Sigue la lógica de ref_fact_transactions_olb.py (PySpark → pandas).

Output: data/dough/fact_transactions.csv
        data/dough/fact_transactions_expenditure.csv  (solo gastos, apto Excel)
        data/dough/fact_transactions_sample.csv       (50k muestra aleatoria)

Uso:
    # Fuente DB (recomendado):
    python3 scripts/build_fact_transactions.py --source db

    # Fuente S3:
    python3 scripts/build_fact_transactions.py --source s3 --env dev

    # Credenciales DB via env vars:
    export DB_HOST=...  DB_NAME=blossom-dough-consolidated-dev  DB_USER=...  DB_PASS=...
"""

import argparse
import csv
import os
import pandas as pd
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
# Cuando el script se ejecuta desde un worktree (.worktrees/<TICKET>/),
# data/ vive en el repo principal (dos niveles arriba).
# Se verifica con un subdirectorio concreto, no solo la existencia de data/.
_OLB_CHECK = ROOT / "data" / "olb" / "dev" / "silver"
if not _OLB_CHECK.exists() and (ROOT.parent.parent / "data" / "olb" / "dev" / "silver").exists():
    ROOT = ROOT.parent.parent

OLB_DIR         = ROOT / "data" / "olb" / "dev" / "silver"
DOUGH_DIR_DEV   = ROOT / "data" / "dough" / "dev"  / "silver"
DOUGH_DIR_ALPHA = ROOT / "data" / "dough" / "alpha" / "silver"
OUT_DIR         = ROOT / "data" / "dough"

# ── DB defaults (override via env vars or CLI args) ───────────────────────────
DB_HOST_DEFAULT = "blossomdoughconsolidatedrdsencrypt-dev-cluster.cluster-csls5euwsof9.us-east-2.rds.amazonaws.com"
DB_NAME_DEFAULT = "blossom-dough-consolidated-dev"
DB_PORT_DEFAULT = 5432


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
        df["_otc_id"] = None

    # Construir columnas canonicas
    # Convención de signo OLB: débito (gasto) = negativo, crédito (ingreso) = positivo.
    # Se normaliza a positivo para alinear con la convención de EXT (Plaid/Finicity).
    sub_amount_raw = pd.to_numeric(df["amount"], errors="coerce")
    sub_income_exp = sub_amount_raw.apply(lambda a: "expenditure" if float(a or 0) < 0 else "income")
    sub_amount = sub_amount_raw.abs()

    result = pd.DataFrame({
        "idTransaction"        : "SUB" + df["id"].astype(str),
        "idClient"             : 1,
        "idCompany"            : df.get("idfi", pd.Series([None]*len(df))).astype(str),
        "idAccount"            : "INT" + df["idolbaccountnumber"].astype(str),
        "idSubAccount"         : "SUB" + df["idsubaccount"].astype(str),
        "idCategory"           : df.get("_otc_id"),
        "amount"               : sub_amount,
        "currency"             : "USD",
        "originalAmount"       : None,
        "timestamp"            : pd.to_datetime(df["date"], errors="coerce"),
        "date"                 : pd.to_datetime(df["date"], errors="coerce").dt.date,
        "incomeExpenditure"    : sub_income_exp,
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
        df["_otc_id"] = None

    # Columna de amount: principalamount (columna puede variar en case)
    amount_col = next((c for c in df.columns if c.lower() == "principalamount"), None)
    if amount_col is None:
        print("  ⚠️  principalAmount no encontrado — usando amount si existe")
        amount_col = "amount" if "amount" in df.columns else None

    # Convención de signo OLB: débito (gasto) = negativo, crédito (ingreso) = positivo.
    # Se normaliza a positivo para alinear con la convención de EXT (Plaid/Finicity).
    loan_amount_raw = pd.to_numeric(df[amount_col], errors="coerce") if amount_col else None
    loan_income_exp = (
        loan_amount_raw.apply(lambda a: "expenditure" if float(a or 0) < 0 else "income")
        if loan_amount_raw is not None else None
    )
    loan_amount = loan_amount_raw.abs() if loan_amount_raw is not None else None

    result = pd.DataFrame({
        "idTransaction"        : "LOAN" + df["id"].astype(str),
        "idClient"             : 1,
        "idCompany"            : df.get("idfi", pd.Series([None]*len(df))).astype(str),
        "idAccount"            : "INT" + df["idolbaccountnumber"].astype(str),
        "idSubAccount"         : "LOAN" + df["idolbloan"].astype(str),
        "idCategory"           : df.get("_otc_id"),
        "amount"               : loan_amount,
        "currency"             : "USD",
        "originalAmount"       : None,
        "timestamp"            : pd.to_datetime(df["date"], errors="coerce"),
        "date"                 : pd.to_datetime(df["date"], errors="coerce").dt.date,
        "incomeExpenditure"    : loan_income_exp,
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

    Convención de signo Plaid: amount < 0 → gasto (debit/expenditure),
                                amount > 0 → ingreso (credit/income).
    El prefijo de idTransaction es 'EXT' — usado por filters.py para
    aplicar la regla de status POSTED a este tipo de transacciones.
    """
    print("→ Cargando externaltransaction (DOUGH)...")
    ext = load(dough, "externaltransaction")

    if ext.empty:
        print("  ⚠️  externaltransaction vacío")
        return pd.DataFrame()

    print(f"  externaltransaction: {len(ext):,} filas")

    # Convención Plaid: negativo = débito (gasto), positivo = crédito (ingreso)
    amount = pd.to_numeric(ext.get("amount"), errors="coerce")
    income_exp = amount.apply(
        lambda a: "expenditure" if (pd.notna(a) and float(a) < 0) else "income"
    )

    # Normalizar amount a positivo para gastos (valor absoluto del débito)
    amount_abs = amount.abs()

    # Lookup de categoría: idcategory → defaultcategory.name
    default_cat_path = dough / "defaultcategory.csv"
    if default_cat_path.exists():
        cat_df = pd.read_csv(default_cat_path, dtype=str)
        cat_df.columns = [c.lower() for c in cat_df.columns]
        cat_map = cat_df.set_index("id")["name"].to_dict()
        # idcategory viene como float (8.0) por pandas; convertir a int-string para coincidir con el índice
        idcat_str = (
            pd.to_numeric(ext.get("idcategory"), errors="coerce")
            .dropna()
            .astype(int)
            .astype(str)
        )
        idcat_aligned = ext.get("idcategory", pd.Series([None] * len(ext)))
        idcat_aligned = pd.to_numeric(idcat_aligned, errors="coerce")
        idcat_aligned = idcat_aligned.apply(
            lambda v: str(int(v)) if pd.notna(v) else None
        )
        default_category = idcat_aligned.map(cat_map)
    else:
        default_category = pd.Series([None] * len(ext))

    # idCompany: externaltransaction no tiene idcompany — se infiere de la cuenta
    # En dev todos pertenecen a company=1 (mismo CU que OLB)
    id_company = ext.get("idcompany", pd.Series(["1"] * len(ext)))

    date_col = ext["date"] if "date" in ext.columns else ext.get("effectivedate", ext.get("createdat"))

    result = pd.DataFrame({
        "idTransaction"        : "EXT" + ext["id"].astype(str),
        "idClient"             : 1,
        "idCompany"            : id_company,
        "idAccount"            : "EXT" + ext.get("idaccount", pd.Series([None] * len(ext))).astype(str),
        "idSubAccount"         : None,
        "idCategory"           : idcat_aligned if default_cat_path.exists() else pd.Series([None] * len(ext)),
        "amount"               : amount_abs,
        "currency"             : ext.get("currency", "USD"),
        "originalAmount"       : pd.to_numeric(ext.get("originalamount"), errors="coerce"),
        "timestamp"            : pd.to_datetime(date_col, errors="coerce"),
        "date"                 : pd.to_datetime(date_col, errors="coerce").dt.date,
        "incomeExpenditure"    : income_exp,
        "status"               : ext.get("status", "").str.upper(),
        "description"          : ext["description"] if "description" in ext.columns else ext.get("name"),
        "balance"              : None,
        "isEnriched"           : ext.get("isenriched", False),
        "enrichment"           : None,
        "enrichmentLogo"       : None,
        "enrichmentName"       : ext.get("merchantname"),
        "enrichmentLocation"   : None,
        "enrichmentUrl"        : None,
        "defaultCategory"      : default_category,
        "idOLBTransactionInfo" : None,
        "transactionComplete"  : None,
        "note"                 : None,
        "checkNumber"          : None,
        "isSplit"              : ext.get("issplit", False),
        "splitedTransactions"  : None,
        "createdAt"            : pd.to_datetime(ext.get("createdat"), errors="coerce"),
        "deletedAt"            : pd.to_datetime(ext.get("deletedat"), errors="coerce"),
        "doughId"              : ext.get("id").astype(str),
        "source"               : "DOUGH_EXT",
    })
    exp_count = (income_exp == "expenditure").sum()
    print(f"  ✅ EXT transactions: {len(result):,} ({exp_count} expenditure, {len(result)-exp_count} income)")
    return result


def build_from_db(host: str, dbname: str, user: str, password: str, port: int = 5432) -> pd.DataFrame:
    """
    Lee fact_transactions directamente de blossom-dough-consolidated-dev.
    Garantiza datos idénticos a los del equipo de DE.
    """
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 no instalado. Ejecuta: pip3 install psycopg2-binary")
        raise

    print(f"→ Conectando a {dbname} en {host}...")
    conn = psycopg2.connect(
        host=host, dbname=dbname, user=user, password=password,
        port=port, connect_timeout=15
    )
    print("  ✅ Conexión exitosa")

    print("  Descargando fact_transactions...", flush=True)
    df = pd.read_sql("SELECT * FROM public.fact_transactions ORDER BY date", conn)
    conn.close()

    print(f"  ✅ {len(df):,} filas, {len(df.columns)} columnas")
    return df


def save_outputs(fact: pd.DataFrame):
    """Guarda CSV completo + versión expenditure + muestra, con schema idéntico a la DB."""

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Columnas canónicas en el orden exacto de la DB ────────────────────────
    CANONICAL_COLS = [
        "idtransaction", "idclient", "idcompany", "idaccount", "idsubaccount",
        "date", "amount", "currency", "originalamount", "timestamp",
        "incomeexpenditure", "status", "description", "balance", "isenriched",
        "enrichment", "enrichmentlogo", "enrichmentname", "enrichmentlocation",
        "enrichmenturl", "defaultcategory", "idolbtransactioninfo",
        "transactioncomplete", "note", "checknumber", "issplit",
        "splitedtransactions", "createdat", "deletedat", "doughid",
        "firstuploaded", "lastuploaded",
    ]

    # Normalizar nombres de columna a lowercase
    fact.columns = [c.lower() for c in fact.columns]

    # Agregar columnas faltantes como null
    for col in CANONICAL_COLS:
        if col not in fact.columns:
            fact[col] = None

    fact = fact[CANONICAL_COLS].copy()

    # ── Formatear fechas al formato de la DB: YYYY-MM-DD HH:MM:SS.000 ─────────
    def fmt_ts(col, tz_offset=None):
        """Formatea columna timestamp. tz_offset: ej ' -0500' para firstuploaded."""
        s = pd.to_datetime(fact[col], errors="coerce", utc=True)
        if tz_offset:
            # Convertir a -05:00 y formatear como '2026-05-08 12:00:00.000 -0500'
            s = s.dt.tz_convert("America/Chicago")
            fact[col] = s.dt.strftime("%Y-%m-%d %H:%M:%S.000 -0500")
        else:
            fact[col] = s.dt.strftime("%Y-%m-%d %H:%M:%S.000")
        # Donde era NaT → vacío
        fact[col] = fact[col].where(s.notna(), other=None)

    fmt_ts("timestamp")
    fmt_ts("createdat")
    fmt_ts("deletedat")
    fmt_ts("lastuploaded")
    fmt_ts("firstuploaded", tz_offset=True)

    # date → solo YYYY-MM-DD
    fact["date"] = pd.to_datetime(fact["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # checknumber: entero donde no sea null, sino vacío
    fact["checknumber"] = pd.to_numeric(fact["checknumber"], errors="coerce").astype("Int64")

    # amount / balance / originalamount → 2 decimales
    for col in ["amount", "balance", "originalamount"]:
        fact[col] = pd.to_numeric(fact[col], errors="coerce").round(2)

    # ── Limpiar comillas en description ──────────────────────────────────────
    fact["description"] = fact["description"].astype(str).str.replace('"', "'", regex=False).str.strip()
    fact.loc[fact["description"] == "nan", "description"] = None

    kw = dict(index=False, quoting=csv.QUOTE_MINIMAL, encoding="utf-8-sig")

    # 1. Completo
    out = OUT_DIR / "fact_transactions.csv"
    fact.to_csv(out, **kw)
    print(f"  ✅ fact_transactions.csv          → {len(fact):,} filas, {len(fact.columns)} cols")

    # 2. Solo gastos (apto Excel)
    exp = fact[fact["incomeexpenditure"] == "expenditure"].copy()
    out_exp = OUT_DIR / "fact_transactions_expenditure.csv"
    exp.to_csv(out_exp, **kw)
    print(f"  ✅ fact_transactions_expenditure.csv → {len(exp):,} filas (solo gastos, apto Excel)")

    # 3. Muestra 50k
    sample = fact.sample(n=min(10_000, len(fact)), random_state=42)
    out_s = OUT_DIR / "fact_transactions_sample.csv"
    sample.to_csv(out_s, **kw)
    print(f"  ✅ fact_transactions_sample.csv   → {len(sample):,} filas (muestra aleatoria)")


def main(source: str = "db", env: str = "dev",
         db_host: str = None, db_name: str = None,
         db_user: str = None, db_pass: str = None, db_port: int = 5432):

    print(f"\n{'='*60}")
    print(f"  build_fact_transactions — source={source}")
    print(f"{'='*60}\n")

    if source == "db":
        host  = db_host or os.environ.get("DB_HOST", DB_HOST_DEFAULT)
        name  = db_name or os.environ.get("DB_NAME", DB_NAME_DEFAULT)
        user  = db_user or os.environ.get("DB_USER", "")
        pwd   = db_pass or os.environ.get("DB_PASS", "")
        port  = db_port

        if not user or not pwd:
            print("❌ Credenciales DB requeridas. Usa --db-user / --db-pass o env vars DB_USER / DB_PASS")
            return

        fact = build_from_db(host, name, user, pwd, port)

    else:  # source == "s3"
        dough_dir = DOUGH_DIR_DEV if env == "dev" else DOUGH_DIR_ALPHA
        parts = []

        sub = build_sub_transactions(OLB_DIR)
        if not sub.empty: parts.append(sub)

        loan = build_loan_transactions(OLB_DIR)
        if not loan.empty: parts.append(loan)

        ext = build_external_transactions(dough_dir)
        if not ext.empty: parts.append(ext)

        if not parts:
            print("❌ Sin datos — abortando")
            return

        print("\n→ Uniendo fuentes S3...")
        fact = pd.concat(parts, ignore_index=True)
        before = len(fact)
        fact = fact.drop_duplicates(subset=["idTransaction"])
        print(f"  Deduplicación: {before:,} → {len(fact):,}")

    print(f"\n→ Guardando outputs...")
    save_outputs(fact)

    date_col_name = next((c for c in ["date"] if c in fact.columns), None)
    if date_col_name:
        dates = pd.to_datetime(fact[date_col_name], errors="coerce")
        print(f"\n  Rango fechas : {dates.min().date()} → {dates.max().date()}")

    src_col = next((c for c in ["source"] if c in fact.columns), None)
    if src_col:
        print("  Fuentes:")
        for src, grp in fact.groupby(src_col):
            print(f"    {src:20s} → {len(grp):,}")

    print(f"\n{'='*60}")
    print(f"✅ Completado — {len(fact):,} filas totales")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build fact_transactions.csv")
    parser.add_argument("--source", default="db", choices=["db", "s3"],
                        help="Fuente: 'db' = Dough consolidated DB (recomendado), 's3' = S3 silver")
    parser.add_argument("--env", default="dev", choices=["dev", "alpha"],
                        help="Entorno S3 (solo aplica con --source s3)")
    parser.add_argument("--db-host", default=None, help="DB host (default: dev cluster)")
    parser.add_argument("--db-name", default=None, help="DB name (default: blossom-dough-consolidated-dev)")
    parser.add_argument("--db-user", default=None, help="DB user (o env var DB_USER)")
    parser.add_argument("--db-pass", default=None, help="DB password (o env var DB_PASS)")
    parser.add_argument("--db-port", type=int, default=5432)
    args = parser.parse_args()
    main(
        source=args.source, env=args.env,
        db_host=args.db_host, db_name=args.db_name,
        db_user=args.db_user, db_pass=args.db_pass, db_port=args.db_port,
    )
