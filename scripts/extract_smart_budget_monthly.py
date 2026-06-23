"""scripts/extract_smart_budget_monthly.py — LEGACY: extrae gasto mensual desde PostgreSQL.

⚠️  DEPRECADO (DATA-1275): este script extrae desde blossom-dough-consolidated-alpha (PostgreSQL).
    Post-migración, los datos se consultan en tiempo real desde Athena:
      dlh_gold_dough_dev.smart_budget_transactions
    usando smart_budget.athena_loader.load_history_by_member_athena().

    Este script se conserva para pipelines batch históricos y entornos sin acceso a Athena.
    Para nuevas integraciones, usar Athena directamente.

Lee directamente de blossom-dough-consolidated-alpha (schema public).
Aplica todas las reglas de filtrado de Smart Budget en SQL y materializa
la agregación mensual por (idmember, defaultcategory, period_yyyymm).

El output reemplaza smart_budget_synthetic_idmember.csv como fuente de datos
del pipeline y del endpoint GET /smart-budget/suggestion.

Reglas de filtrado aplicadas (equivalentes a filters.py):
    1. deletedat IS NULL
    2. incomeexpenditure = 'expenditure'
    3. defaultcategory NOT IN ('UNCATEGORIZED', 'INCOME', 'MONEY_SENT')
    4. idtransaction NOT LIKE 'LOAN%'
    5. OLB (SUB%): status IS NULL OR status NOT IN ('PENDING', 'HOLD')
    6. EXT (EXT%): UPPER(status) = 'POSTED'

Resolución de idmember:
    fact_transactions.idaccount → bridge_member_account.idaccount → idmember

Uso:
    # Con variables de entorno:
    export DB_HOST=...  DB_USER=...  DB_PASS=...
    python3 scripts/extract_smart_budget_monthly.py

    # Con argumentos explícitos:
    python3 scripts/extract_smart_budget_monthly.py \\
        --host <host> --user <user> --password <pass>

    # Ventana de meses (default: todos los disponibles):
    python3 scripts/extract_smart_budget_monthly.py --months 12

    # Output personalizado:
    python3 scripts/extract_smart_budget_monthly.py --output data/dough/smart_budget_monthly.csv
"""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

import pandas as pd
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
_logger = structlog.get_logger()

# ── Config ────────────────────────────────────────────────────────────────────

DB_HOST_DEFAULT = (
    "blossomdoughconsolidatedrdsencrypt-dev-cluster.cluster-csls5euwsof9.us-east-2.rds.amazonaws.com"
)
DB_NAME_DEFAULT = "blossom-dough-consolidated-alpha"
DB_SCHEMA = "public"
DB_PORT_DEFAULT = 5432

ROOT = Path(__file__).resolve().parent.parent
# Soporte para worktrees: si data/ no existe aquí, buscar en el repo padre
_DATA_CHECK = ROOT / "data" / "dough"
if not _DATA_CHECK.exists() and (ROOT.parent.parent / "data" / "dough").exists():
    ROOT = ROOT.parent.parent

OUT_DIR = ROOT / "data" / "dough"
OUT_FILE_DEFAULT = "smart_budget_synthetic_idmember.csv"

# Ruta al archivo SQL (relativa al repo, no al script)
QUERIES_DIR = Path(__file__).resolve().parent.parent / "src" / "smart_budget" / "queries"
QUERY_FILE = QUERIES_DIR / "smart_budget_monthly_spend.sql"

# Columnas de salida (alineadas con loader.py → load_history_by_member)
OUTPUT_COLS = [
    "idclient",
    "idcompany",
    "idmember",
    "idaccount",
    "idcategory",
    "defaultcategory",
    "period_yyyymm",
    "monthly_total",
]

# ── Query principal ───────────────────────────────────────────────────────────

# Filtra y agrega en una sola pasada sobre fact_transactions.
# La resolución de idmember se hace via JOIN con bridge_member_account.
# Sumas negativas (netas) se clampean a 0 (GREATEST) para evitar negativos.
# La query canónica vive en src/smart_budget/queries/smart_budget_monthly_spend.sql.
_RAW_QUERY = """
WITH base AS (
    SELECT
        ft.idclient,
        ft.idcompany,
        bma.idmember,
        ft.idaccount,
        ft.defaultcategory,
        TO_CHAR(ft.date, 'YYYY-MM')          AS period_yyyymm,
        GREATEST(0, SUM(ft.amount::NUMERIC)) AS monthly_total
    FROM {schema}.fact_transactions ft
    JOIN {schema}.bridge_member_account bma
        ON ft.idaccount::TEXT = bma.idaccount::TEXT
    WHERE
        -- Regla 1: excluir soft-deleted
        ft.deletedat IS NULL
        -- Regla 2: solo gastos
        AND LOWER(ft.incomeexpenditure) = 'expenditure'
        -- Regla 3: categorías válidas
        AND ft.defaultcategory IS NOT NULL
        AND UPPER(ft.defaultcategory) NOT IN ('UNCATEGORIZED', 'INCOME', 'MONEY_SENT')
        -- Regla 4: excluir pagos de préstamos
        AND ft.idtransaction NOT LIKE 'LOAN%'
        -- Reglas 5 y 6: filtro de estado por origen de transacción
        AND (
            -- OLB (SUB%): estado nulo o no PENDING/HOLD
            (
                ft.idtransaction LIKE 'SUB%'
                AND (ft.status IS NULL OR UPPER(ft.status) NOT IN ('PENDING', 'HOLD'))
            )
            OR
            -- Externas Dough (EXT%, Plaid/Finicity): solo POSTED
            (
                ft.idtransaction LIKE 'EXT%'
                AND UPPER(ft.status) = 'POSTED'
            )
            OR
            -- Otros prefijos desconocidos: pasar sin filtro de estado
            (
                ft.idtransaction NOT LIKE 'SUB%'
                AND ft.idtransaction NOT LIKE 'EXT%'
                AND ft.idtransaction NOT LIKE 'LOAN%'
            )
        )
    GROUP BY
        ft.idclient,
        ft.idcompany,
        bma.idmember,
        ft.idaccount,
        ft.defaultcategory,
        period_yyyymm
)
SELECT
    idclient,
    idcompany,
    idmember,
    idaccount,
    -- idcategory como proxy del nombre de categoría (sin catálogo en Fase 0)
    defaultcategory  AS idcategory,
    defaultcategory,
    period_yyyymm,
    monthly_total
FROM base
{where_clause}
ORDER BY idmember, period_yyyymm, defaultcategory
"""


def _build_query(months: int | None) -> str:
    """Construye la query final con filtro de ventana temporal opcional.

    Carga la query canónica desde src/smart_budget/queries/smart_budget_monthly_spend.sql
    cuando el archivo existe. Si no, usa el fallback embebido (_RAW_QUERY).
    """
    # Leer desde el archivo SQL canónico cuando esté disponible
    if QUERY_FILE.exists():
        template = QUERY_FILE.read_text(encoding="utf-8")
        # Remover comentarios de cabecera (líneas que empiezan con '--' antes del WITH)
        lines = template.splitlines()
        sql_start = next((i for i, l in enumerate(lines) if l.strip().upper().startswith("WITH")), 0)
        template = "\n".join(lines[sql_start:])
        # Desactivar el WHERE de ventana temporal si existe comentado, o activarlo si se pide
        if months and months > 0:
            template = template.replace(
                "-- WHERE period_yyyymm >= TO_CHAR(NOW() - INTERVAL 'N months', 'YYYY-MM')",
                f"WHERE period_yyyymm >= TO_CHAR(NOW() - INTERVAL '{months} months', 'YYYY-MM')",
            )
        _logger.debug("_build_query.using_file", path=str(QUERY_FILE))
        return template

    # Fallback embebido (en caso de que el archivo SQL no esté disponible)
    _logger.warning("_build_query.sql_file_missing", path=str(QUERY_FILE), fallback="embedded query")
    if months and months > 0:
        where_clause = f"WHERE period_yyyymm >= TO_CHAR(NOW() - INTERVAL '{months} months', 'YYYY-MM')"
    else:
        where_clause = ""
    return _RAW_QUERY.format(schema=DB_SCHEMA, where_clause=where_clause)


# ── Extracción ────────────────────────────────────────────────────────────────


def extract(
    host: str,
    dbname: str,
    user: str,
    password: str,
    port: int = DB_PORT_DEFAULT,
    months: int | None = None,
) -> pd.DataFrame:
    """Conecta a la DB y extrae el gasto mensual agregado.

    Args:
        host: Hostname del cluster RDS.
        dbname: Nombre de la base de datos.
        user: Usuario de la DB.
        password: Contraseña de la DB.
        port: Puerto TCP (default 5432).
        months: Ventana de meses hacia atrás. None = todos los disponibles.

    Returns:
        DataFrame con columnas: idclient, idcompany, idmember, idaccount,
        idcategory, defaultcategory, period_yyyymm, monthly_total.

    Raises:
        ImportError: si psycopg2 no está instalado.
        Exception: cualquier error de conexión o query se propaga al caller.
    """
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "psycopg2 no instalado. Ejecuta: pip install psycopg2-binary"
        )

    log = _logger.bind(host=host, dbname=dbname, months=months or "all")
    log.info("extract.connecting")

    conn = psycopg2.connect(
        host=host,
        dbname=dbname,
        user=user,
        password=password,
        port=port,
        connect_timeout=15,
    )
    log.info("extract.connected")

    query = _build_query(months)
    log.info("extract.running_query")

    try:
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    log.info(
        "extract.done",
        rows=len(df),
        members=int(df["idmember"].nunique()) if not df.empty else 0,
        categories=int(df["defaultcategory"].nunique()) if not df.empty else 0,
        periods=int(df["period_yyyymm"].nunique()) if not df.empty else 0,
    )
    return df


# ── Escritura segura ──────────────────────────────────────────────────────────


def _write_csv(df: pd.DataFrame, out_path: Path) -> None:
    """Escritura atómica con chmod 600 (nunca PII expuesta parcialmente)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")

    df[OUTPUT_COLS].to_csv(tmp_path, index=False)
    os.replace(tmp_path, out_path)
    out_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600

    _logger.info("extract.saved", path=str(out_path), rows=len(df))


# ── Main ──────────────────────────────────────────────────────────────────────


def main(
    host: str,
    dbname: str,
    user: str,
    password: str,
    port: int = DB_PORT_DEFAULT,
    months: int | None = None,
    output: Path | None = None,
) -> None:
    """Flujo completo: extracción → validación → escritura CSV."""
    out_path = output or (OUT_DIR / OUT_FILE_DEFAULT)

    df = extract(host=host, dbname=dbname, user=user, password=password, port=port, months=months)

    if df.empty:
        _logger.warning("extract.empty_result", hint="Verificar conexión, filtros y bridge_member_account")
        return

    # Validación mínima de columnas
    missing = [c for c in OUTPUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en resultado: {missing}")

    # Coerción de tipos antes de guardar
    df["monthly_total"] = pd.to_numeric(df["monthly_total"], errors="coerce").fillna(0.0)
    df["idmember"] = df["idmember"].astype(str)
    df["idclient"] = df["idclient"].astype(str)
    df["idcompany"] = df["idcompany"].astype(str)

    # Ordenar: idmember, periodo (alineado con spec DATA-1179)
    df = df.sort_values(["idmember", "period_yyyymm"]).reset_index(drop=True)

    _write_csv(df, out_path)

    # Resumen sin montos individuales (PII policy)
    _logger.info(
        "extract.summary",
        output=str(out_path),
        total_rows=len(df),
        unique_members=int(df["idmember"].nunique()),
        unique_categories=int(df["defaultcategory"].nunique()),
        period_range=f"{df['period_yyyymm'].min()} ~ {df['period_yyyymm'].max()}",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extrae gasto mensual por miembro/categoría desde blossom-dough-consolidated-alpha"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("DB_HOST", DB_HOST_DEFAULT),
        help="Hostname RDS (default: DB_HOST env var o cluster dev)",
    )
    parser.add_argument(
        "--dbname",
        default=os.environ.get("DB_NAME", DB_NAME_DEFAULT),
        help=f"Nombre de la DB (default: {DB_NAME_DEFAULT})",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("DB_USER", ""),
        help="Usuario DB (default: DB_USER env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("DB_PASS", ""),
        help="Contraseña DB (default: DB_PASS env var)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DB_PORT", DB_PORT_DEFAULT)),
        help=f"Puerto TCP (default: {DB_PORT_DEFAULT})",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="Ventana de meses hacia atrás. Omitir para todos los disponibles.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Ruta de salida (default: data/dough/{OUT_FILE_DEFAULT})",
    )

    args = parser.parse_args()

    if not args.user or not args.password:
        parser.error(
            "Se requieren credenciales. Usa --user / --password o variables DB_USER / DB_PASS."
        )

    main(
        host=args.host,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        port=args.port,
        months=args.months,
        output=args.output,
    )
