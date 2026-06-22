"""src/smart_budget/athena_loader.py — Carga de historial desde Athena (DATA-1275).

Provee conexión lazy a Athena via pyathena y dos funciones públicas:
  - load_history_by_member_athena: consulta historial mensual por idmember.
  - member_exists_athena: verifica si el idmember tiene al menos un registro.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import pandas as pd
import pyathena
import structlog

_logger = structlog.get_logger()

# Conexión cacheada a nivel de módulo — se inicializa una sola vez.
_CONN: Optional["pyathena.Connection"] = None


class AthenaQueryError(Exception):
    """Raised when an Athena query fails (timeout, credentials, etc.)."""


def _get_connection() -> "pyathena.Connection":
    """Lazy-init module-level pyathena connection.

    Lee ATHENA_S3_STAGING_DIR (required) y ATHENA_REGION_NAME (default us-east-2).
    Retorna la conexión cacheada. Raises AthenaQueryError si falta env var.
    """
    global _CONN
    if _CONN is not None:
        return _CONN

    staging_dir = os.getenv("ATHENA_S3_STAGING_DIR")
    if not staging_dir:
        raise AthenaQueryError(
            "Missing required env var ATHENA_S3_STAGING_DIR. "
            "Set it to the S3 path for Athena query results."
        )
    region = os.getenv("ATHENA_REGION_NAME", "us-east-2")

    _CONN = pyathena.connect(s3_staging_dir=staging_dir, region_name=region)
    return _CONN


def load_history_by_member_athena(
    idmember: "int | str",
    conn: "pyathena.Connection | None" = None,
    database: str | None = None,
    table: str | None = None,
) -> pd.DataFrame:
    """Consulta la tabla Glue para el idmember dado.

    Retorna DataFrame con columnas:
        idclient, idcompany, idmember, idaccount,
        category_id, category_name, period_yyyymm, monthly_total

    DataFrame vacío (mismo schema) si el miembro no tiene filas.
    Raises AthenaQueryError en fallo de conexión/query.

    Args:
        idmember: ID del miembro a consultar.
        conn: Conexión pyathena opcional. Si None usa _get_connection().
        database: Base de datos Athena (default: ATHENA_DATABASE env o dlh_gold_dough_dev).
        table: Tabla Athena (default: ATHENA_TABLE env o smart_budget_transactions).
    """
    _OUTPUT_COLS = [
        "idclient", "idcompany", "idmember", "idaccount",
        "category_id", "category_name", "period_yyyymm", "monthly_total",
    ]

    if conn is None:
        conn = _get_connection()

    db = database or os.getenv("ATHENA_DATABASE", "dlh_gold_dough_dev")
    tbl = table or os.getenv("ATHENA_TABLE", "smart_budget_transactions")

    sql = (
        f"SELECT idclient, idcompany, idmember, idaccount, "
        f"category_id, category_name, txn_month, total_amount "
        f"FROM {db}.{tbl} "
        f"WHERE idmember = %(idmember)s"
    )

    idmember_str = str(idmember)
    t0 = time.monotonic()
    try:
        df = pd.read_sql(sql, conn, params={"idmember": idmember_str})
    except Exception as e:
        _logger.error(
            "smart_budget.athena.error",
            idmember=idmember_str,
            error=str(e),
        )
        raise AthenaQueryError(f"Athena query failed for idmember={idmember_str}: {e}") from e

    duration_ms = int((time.monotonic() - t0) * 1000)

    if df.empty:
        _logger.info(
            "smart_budget.athena.done",
            idmember=idmember_str,
            rows=0,
            duration_ms=duration_ms,
        )
        # Retornar DataFrame vacío con schema correcto
        return pd.DataFrame(columns=_OUTPUT_COLS)

    # Post-procesado
    df["period_yyyymm"] = df["txn_month"].astype(str).str[:7]
    df["monthly_total"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0).clip(lower=0.0)
    df["category_id"] = df["category_id"].astype(str)
    df["category_name"] = df["category_name"].astype(str)
    df["idmember"] = df["idmember"].astype(str)

    _logger.info(
        "smart_budget.athena.done",
        idmember=idmember_str,
        rows=len(df),
        duration_ms=duration_ms,
    )

    return df[_OUTPUT_COLS]


def member_exists_athena(
    idmember: "int | str",
    conn: "pyathena.Connection | None" = None,
    database: str | None = None,
    table: str | None = None,
) -> bool:
    """True iff al menos un registro existe para el idmember dado.

    Raises AthenaQueryError on failure.

    Args:
        idmember: ID del miembro a verificar.
        conn: Conexión pyathena opcional. Si None usa _get_connection().
        database: Base de datos Athena.
        table: Tabla Athena.
    """
    if conn is None:
        conn = _get_connection()

    db = database or os.getenv("ATHENA_DATABASE", "dlh_gold_dough_dev")
    tbl = table or os.getenv("ATHENA_TABLE", "smart_budget_transactions")

    sql = (
        f"SELECT 1 FROM {db}.{tbl} "
        f"WHERE idmember = %(idmember)s LIMIT 1"
    )

    idmember_str = str(idmember)
    try:
        df = pd.read_sql(sql, conn, params={"idmember": idmember_str})
    except Exception as e:
        raise AthenaQueryError(f"Athena existence check failed for idmember={idmember_str}: {e}") from e

    return len(df) >= 1
