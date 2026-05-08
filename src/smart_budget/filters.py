"""
Reglas de filtrado para Smart Budget Fase 0.

Todas las reglas son obligatorias según docs/DECISIONS.md Q3, Q6, Q8.
NUNCA modificar sin actualizar el Decision Log.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

# Categorías que NUNCA reciben sugerencia
EXCLUDED_CATEGORY_NAMES = {"Uncategorized"}

# Grupos de categoría válidos para presupuesto (solo Expense)
EXPENSE_CATEGORY_GROUP = 1

# IDs de tipo de transacción excluidos (cuando el campo esté disponible)
EXCLUDED_TX_TYPES = {"Internal", "Member-to-Member", "credit"}

# Estados válidos de transacción (externaltransaction)
VALID_STATUS = {"posted", "Posted"}

MIN_AMOUNT = 0.0  # Los reembolsos (negativos) se clampa a 0 antes de agregar


def get_expense_category_ids(default_categories: pd.DataFrame) -> set[int]:
    """Devuelve el set de IDs de categorías de tipo Expense.

    Args:
        default_categories: DataFrame de la tabla defaultcategory.

    Returns:
        Set de category IDs válidos para el cálculo.
    """
    mask = (
        (default_categories["idcategorygroup"] == EXPENSE_CATEGORY_GROUP)
        & (default_categories["shouldshow"] == True)  # noqa: E712
        & (default_categories["deletedat"].isna())
        & (~default_categories["name"].isin(EXCLUDED_CATEGORY_NAMES))
    )
    ids = set(default_categories.loc[mask, "id"].astype(int).tolist())
    log.debug("expense_categories_loaded", count=len(ids))
    return ids


def filter_manual_transactions(
    mt: pd.DataFrame,
    ma: pd.DataFrame,
    expense_cat_ids: set[int],
    reference_date: pd.Timestamp,
    n_months: int = 6,
) -> pd.DataFrame:
    """Filtra manualtransaction según reglas de Fase 0.

    manualtransaction no tiene campo status ni type, por lo que:
    - Se filtran por deletedat IS NULL
    - Se aceptan todos los tipos (son entradas manuales del usuario)
    - El tipo se infiere por la categoría asignada

    Args:
        mt: DataFrame de manualtransaction.
        ma: DataFrame de manualaccount.
        expense_cat_ids: Set de IDs de categorías Expense válidas.
        reference_date: Mes en curso (excluido). Usar el 1er día del mes.
        n_months: Ventana de meses hacia atrás.

    Returns:
        DataFrame filtrado con columna idmember añadida.
    """
    df = mt.copy()
    df["processdate"] = pd.to_datetime(df["processdate"])

    start_date = reference_date - pd.DateOffset(months=n_months)

    initial = len(df)

    # Excluir eliminados
    df = df[df["deletedat"].isna()]

    # Solo meses calendario COMPLETOS (excluir mes en curso)
    df = df[df["processdate"] >= start_date]
    df = df[df["processdate"] < reference_date]

    # Solo transacciones categorizadas con categoría Expense
    df = df[df["idcategory"].notna()]
    df = df[df["idcategory"].astype(int).isin(expense_cat_ids)]

    # Montos positivos (clampear reembolsos a 0 está en aggregator)
    df = df[df["amount"] > MIN_AMOUNT]

    # Unir con manualaccount para obtener idmember
    df = df.merge(
        ma[["id", "idmember"]].rename(columns={"id": "idmanualaccount"}),
        on="idmanualaccount",
        how="inner",
    )

    # Excluir cuentas eliminadas
    active_accounts = set(ma[ma["deletedat"].isna()]["id"].tolist())
    df = df[df["idmanualaccount"].isin(active_accounts)]

    log.info(
        "manual_transactions_filtered",
        initial=initial,
        final=len(df),
        members=int(df["idmember"].nunique()),
    )
    return df


def filter_external_transactions(
    et: pd.DataFrame,
    account: pd.DataFrame,
    member_account: pd.DataFrame,
    expense_cat_ids: set[int],
    reference_date: pd.Timestamp,
    n_months: int = 6,
) -> pd.DataFrame:
    """Filtra externaltransaction según reglas de Fase 0.

    Args:
        et: DataFrame de externaltransaction.
        account: DataFrame de account.
        member_account: DataFrame de memberaccount.
        expense_cat_ids: Set de IDs de categorías Expense válidas.
        reference_date: Mes en curso (excluido).
        n_months: Ventana de meses hacia atrás.

    Returns:
        DataFrame filtrado con columna idmember añadida.
    """
    df = et.copy()
    df["processdate"] = pd.to_datetime(df["processdate"])

    start_date = reference_date - pd.DateOffset(months=n_months)

    # Solo Posted
    df = df[df["status"].isin(VALID_STATUS)]

    # Excluir créditos (income) y tipos internos
    if "type" in df.columns:
        df = df[~df["type"].isin(EXCLUDED_TX_TYPES)]

    # Ventana temporal
    df = df[df["processdate"] >= start_date]
    df = df[df["processdate"] < reference_date]

    # Solo categorizadas con Expense
    df = df[df["idcategory"].notna()]
    df = df[df["idcategory"].astype(int).isin(expense_cat_ids)]

    df = df[df["amount"] < 0]        # debits son negativos en externaltransaction
    df["amount"] = df["amount"].abs()

    df = df[df["deletedat"].isna()]

    # Unir member via account → memberaccount
    df = df.merge(account[["id", "deletedat"]].rename(
        columns={"id": "idaccount", "deletedat": "account_deletedat"}
    ), on="idaccount", how="inner")
    df = df[df["account_deletedat"].isna()]

    df = df.merge(
        member_account[["idaccount", "idmember"]],
        on="idaccount",
        how="inner",
    )

    log.info("external_transactions_filtered", final=len(df),
             members=int(df["idmember"].nunique()))
    return df


def filter_members_with_tac(
    member_ids: pd.Series,
    membertacacceptance: pd.DataFrame,
) -> set[int]:
    """Devuelve solo los member IDs que aceptaron T&C.

    Args:
        member_ids: Serie con todos los member IDs candidatos.
        membertacacceptance: DataFrame de membertacacceptance.

    Returns:
        Set de member IDs que aceptaron T&C.
    """
    accepted = set(membertacacceptance["idmember"].astype(int).unique())
    valid = set(member_ids.astype(int).unique()) & accepted
    log.info("tac_filter", candidates=len(member_ids.unique()), valid=len(valid))
    return valid
