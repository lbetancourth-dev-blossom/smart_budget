"""src/smart_budget/loader.py — Cargador unificado de datos para Smart Budget (DATA-1140/1179).

Estrategia de fuentes:
  - Por idmember (DATA-1179+): smart_budget_synthetic_idmember.csv (grain idmember).
  - Por idaccount (legacy): smart_budget_synthetic.csv → synthetic, o raw CSVs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import structlog

from smart_budget.aggregator import aggregate_monthly
from smart_budget.filters import filter_transactions

logger = structlog.get_logger()

_SYNTHETIC_CSV = "smart_budget_synthetic.csv"
_SYNTHETIC_IDMEMBER_CSV = "smart_budget_synthetic_idmember.csv"
_RAW_INTERNAL_CSV = "test/test_internal.csv"
_RAW_EXTERNAL_CSV = "test/test_external.csv"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)  # C2-fix: evita re-read del CSV en cada request
def _synthetic_accounts(base_dir: Path) -> frozenset:
    """
    Retorna el conjunto de idaccount presentes en smart_budget_synthetic.csv.
    Cacheado por proceso — lectura única.

    Args:
        base_dir: Directorio raíz de datos.

    Returns:
        frozenset de idaccount strings.
    """
    path = base_dir / _SYNTHETIC_CSV
    if not path.exists():
        return frozenset()
    df = pd.read_csv(path, usecols=["idaccount"], dtype=str)
    return frozenset(df["idaccount"].dropna().unique())


def _load_synthetic_for_account(
    idaccount: str,
    defaultcategory: str,
    base_dir: Path,
) -> pd.DataFrame:
    """
    Filtra smart_budget_synthetic.csv por (idaccount, defaultcategory).

    Args:
        idaccount: ID de la cuenta del miembro.
        defaultcategory: Nombre de la categoría (ej: GROCERIES).
        base_dir: Directorio raíz de datos.

    Returns:
        DataFrame con columnas: idclient, idcompany, idaccount, idcategory,
        defaultcategory, period_yyyymm, monthly_total.
    """
    path = base_dir / _SYNTHETIC_CSV
    df = pd.read_csv(path, dtype=str)
    df["monthly_total"] = df["monthly_total"].astype(float)
    mask = (df["idaccount"] == idaccount) & (df["defaultcategory"] == defaultcategory)
    return df[mask].reset_index(drop=True)


def _normalize_olb_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte amounts negativos de OLB (SUB/LOAN prefix) a positivos.
    Las transacciones EXT ya vienen positivas — no se tocan.

    Contexto: build_fact_transactions.py:289-290 aplica abs() a EXT pero no a OLB.
    El loader debe compensar para que aggregate_monthly produzca totals positivos.

    Args:
        df: DataFrame de transacciones con columnas idtransaction y amount.

    Returns:
        DataFrame con amounts de OLB convertidos a absolutos.
    """
    out = df.copy()
    if "idtransaction" not in out.columns or "amount" not in out.columns:
        return out
    is_olb = out["idtransaction"].str.startswith(("SUB", "LOAN"), na=False)
    out.loc[is_olb, "amount"] = out.loc[is_olb, "amount"].abs()
    return out


def _load_raw_for_account(
    idaccount: str,
    defaultcategory: str,
    base_dir: Path,
) -> pd.DataFrame:
    """
    Carga test_internal.csv + test_external.csv, aplica el pipeline de filtrado
    y agregación, y retorna el historial mensual para (idaccount, defaultcategory).

    Pipeline:
        1. Cargar ambos CSV (si existen)
        2. Concatenar
        3. filter_transactions()
        4. _normalize_olb_amounts()
        5. Filtrar por idaccount + defaultcategory
        6. Añadir idcategory = defaultcategory (proxy — raw CSV no tiene esta col)
        7. aggregate_monthly()
        8. Retornar filtrado final

    Args:
        idaccount: ID de la cuenta del miembro.
        defaultcategory: Nombre de la categoría.
        base_dir: Directorio raíz de datos.

    Returns:
        DataFrame pre-agregado con columnas estándar, o vacío si no hay datos.
    """
    frames = []
    for rel_path in (_RAW_INTERNAL_CSV, _RAW_EXTERNAL_CSV):
        path = base_dir / rel_path
        if path.exists():
            frames.append(pd.read_csv(path, dtype=str, keep_default_na=False))

    if not frames:
        return pd.DataFrame()

    raw = pd.concat(frames, ignore_index=True)

    # Convertir columnas numéricas
    raw["amount"] = pd.to_numeric(raw["amount"], errors="coerce").fillna(0.0)
    for col in ["deletedat", "status"]:
        if col in raw.columns:
            raw[col] = raw[col].replace("", None)

    # Paso 3: filtros de negocio
    filtered = filter_transactions(raw)

    # Paso 4: normalizar sign OLB
    filtered = _normalize_olb_amounts(filtered)

    # Paso 5: filtrar por cuenta y categoría solicitadas
    mask = (filtered["idaccount"] == idaccount) & (
        filtered["defaultcategory"] == defaultcategory
    )
    filtered = filtered[mask].reset_index(drop=True)

    if filtered.empty:
        return pd.DataFrame()

    # Paso 6: añadir idcategory sintético (aggregate_monthly lo requiere)
    filtered["idcategory"] = filtered["defaultcategory"]

    # Paso 7: agregación mensual
    aggregated = aggregate_monthly(filtered)

    return aggregated[
        [
            "idclient",
            "idcompany",
            "idaccount",
            "idcategory",
            "defaultcategory",
            "period_yyyymm",
            "monthly_total",
        ]
    ].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def account_exists(
    idaccount: str,
    base_dir: "str | Path" = "data/dough",
) -> bool:
    """
    Verifica si idaccount tiene datos en cualquier categoría.

    Útil para distinguir "cuenta no existe" (→ 404) de "cuenta existe pero
    no tiene datos en la categoría pedida" (→ 200 null).

    Args:
        idaccount: ID de la cuenta del miembro.
        base_dir: Directorio raíz de datos. Default: data/dough.

    Returns:
        True si la cuenta tiene al menos un registro en alguna fuente de datos.
    """
    base = Path(base_dir)
    if not base.exists():
        raise FileNotFoundError(f"base_dir no encontrado: {base}")

    # Verificar en synthetic (la fuente de mayor prioridad)
    if idaccount in _synthetic_accounts(base):
        return True

    # Verificar en raw CSVs
    for csv_name in (_RAW_INTERNAL_CSV, _RAW_EXTERNAL_CSV):
        path = base / csv_name
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["idaccount"], dtype=str, nrows=None)
        if idaccount in df["idaccount"].values:
            return True

    return False


def load_history(
    idaccount: str,
    defaultcategory: str,
    base_dir: "str | Path" = "data/dough",
) -> pd.DataFrame:
    """
    Retorna el historial mensual pre-agregado para (idaccount, defaultcategory).

    Estrategia de fuentes (data/dough/smart_budget_synthetic.csv toma prioridad):
    - Si idaccount está en synthetic → _load_synthetic_for_account()
    - Si no → _load_raw_for_account() (test_internal + test_external)

    Args:
        idaccount: ID de la cuenta del miembro.
        defaultcategory: Nombre de la categoría (ej: GROCERIES).
        base_dir: Directorio raíz de datos. Default: data/dough.

    Returns:
        DataFrame con columnas: idclient, idcompany, idaccount, idcategory,
        defaultcategory, period_yyyymm, monthly_total.
        Vacío si no hay datos para la combinación solicitada.

    Raises:
        FileNotFoundError: si base_dir no existe.
    """
    base = Path(base_dir)
    if not base.exists():
        raise FileNotFoundError(f"base_dir no encontrado: {base}")

    log = logger.bind(idaccount=idaccount, defaultcategory=defaultcategory)

    known_accounts = _synthetic_accounts(base)
    if idaccount in known_accounts:
        log.info("loader.source", source="synthetic")
        return _load_synthetic_for_account(idaccount, defaultcategory, base)

    log.info("loader.source", source="raw_csv")
    return _load_raw_for_account(idaccount, defaultcategory, base)


# ---------------------------------------------------------------------------
# Public API — grain idmember (DATA-1179)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _synthetic_members(base_dir: Path) -> frozenset:
    """
    Retorna el conjunto de idmember presentes en smart_budget_synthetic_idmember.csv.
    Cacheado por proceso — lectura única.

    Args:
        base_dir: Directorio raíz de datos.

    Returns:
        frozenset de idmember como strings.
    """
    path = base_dir / _SYNTHETIC_IDMEMBER_CSV
    if not path.exists():
        return frozenset()
    df = pd.read_csv(path, usecols=["idmember"], dtype=str)
    return frozenset(df["idmember"].dropna().unique())


def member_exists(
    idmember: "int | str",
    base_dir: "str | Path" = "data/dough",
) -> bool:
    """
    Verifica si idmember tiene datos en smart_budget_synthetic_idmember.csv.

    Args:
        idmember: ID numérico del miembro (int o str).
        base_dir: Directorio raíz de datos.

    Returns:
        True si el miembro tiene al menos un registro.
    """
    base = Path(base_dir)
    if not base.exists():
        raise FileNotFoundError(f"base_dir no encontrado: {base}")
    return str(idmember) in _synthetic_members(base)


def load_history_by_member(
    idmember: "int | str",
    base_dir: "str | Path" = "data/dough",
) -> pd.DataFrame:
    """
    Retorna el historial mensual pre-agregado para todas las categorías de un miembro.

    Carga desde smart_budget_synthetic_idmember.csv filtrado por idmember.
    El DataFrame resultante contiene todas las categorías del miembro, listo
    para pasar a compute_budget_suggestions().

    Args:
        idmember: ID numérico del miembro.
        base_dir: Directorio raíz de datos. Default: data/dough.

    Returns:
        DataFrame con columnas: idclient, idcompany, idmember, idaccount,
        idcategory, defaultcategory, period_yyyymm, monthly_total.
        Vacío si el miembro no tiene datos.

    Raises:
        FileNotFoundError: si base_dir no existe.
    """
    base = Path(base_dir)
    if not base.exists():
        raise FileNotFoundError(f"base_dir no encontrado: {base}")

    path = base / _SYNTHETIC_IDMEMBER_CSV
    if not path.exists():
        logger.warning("loader.idmember_csv_missing", path=str(path))
        return pd.DataFrame()

    df = pd.read_csv(path, dtype=str)
    df["monthly_total"] = pd.to_numeric(df["monthly_total"], errors="coerce").fillna(0.0)
    df["idmember"] = pd.to_numeric(df["idmember"], errors="coerce")

    mask = df["idmember"] == int(idmember)
    result = df[mask].reset_index(drop=True)

    logger.info(
        "loader.idmember.loaded",
        idmember=str(idmember),
        rows=len(result),
        categories=int(result["defaultcategory"].nunique()) if not result.empty else 0,
    )
    return result
