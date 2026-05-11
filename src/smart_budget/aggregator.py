"""src/smart_budget/aggregator.py — Aggregation pipeline for Smart Budget."""
import pandas as pd
import numpy as np


def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa por (idclient, idcompany, idmember, defaultcategory, period_yyyymm)
    y suma amount. Clampea negativos a 0. Retorna columna monthly_total.

    Crea period_yyyymm desde la columna `date` como "YYYY-MM".
    """
    df = df.copy()
    df["period_yyyymm"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)

    group_keys = ["idclient", "idcompany", "idmember", "defaultcategory", "period_yyyymm"]
    agg = df.groupby(group_keys, as_index=False)["amount"].sum()
    agg.rename(columns={"amount": "monthly_total"}, inplace=True)

    # Clamp negative totals to 0 (REF > expenses case)
    agg["monthly_total"] = agg["monthly_total"].clip(lower=0.0)

    return agg.reset_index(drop=True)


def zero_fill(df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera el grid completo (member × category) × all_months en rango del dataset.
    Hace left join con df. Rellena NaN → 0 en monthly_total.
    Propaga idclient e idcompany del miembro (consistent dentro del grupo).

    Raises:
        ValueError: if any idmember maps to more than one (idclient, idcompany) pair.
    """
    # Validate: each idmember must map to exactly one (idclient, idcompany)
    member_company = (
        df[["idmember", "idclient", "idcompany"]]
        .drop_duplicates()
        .groupby("idmember")
        .size()
    )
    violations = member_company[member_company > 1]
    if not violations.empty:
        raise ValueError(
            f"idmember maps to multiple (idclient, idcompany) pairs: "
            f"{len(violations)} member(s) violated the uniqueness constraint."
        )

    # Determine all months in [min_month, max_month] range
    periods = pd.PeriodIndex(df["period_yyyymm"].unique(), freq="M")
    all_months = pd.period_range(start=periods.min(), end=periods.max(), freq="M")
    all_months_str = [str(p) for p in all_months]

    # Get unique (idmember, defaultcategory) pairs
    member_cat = df[["idclient", "idcompany", "idmember", "defaultcategory"]].drop_duplicates()

    # Build full grid: cross join member_cat × all_months
    months_df = pd.DataFrame({"period_yyyymm": all_months_str})
    months_df["_key"] = 1
    member_cat = member_cat.copy()
    member_cat["_key"] = 1
    full_grid = pd.merge(member_cat, months_df, on="_key").drop(columns=["_key"])

    # Left join grid ← actual data
    agg_cols = ["idmember", "defaultcategory", "period_yyyymm", "monthly_total"]
    result = pd.merge(
        full_grid,
        df[agg_cols],
        on=["idmember", "defaultcategory", "period_yyyymm"],
        how="left",
    )
    result["monthly_total"] = result["monthly_total"].fillna(0.0)

    return result.reset_index(drop=True)


def apply_p90_cap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula el percentil 90 global de monthly_total (post zero-fill).
    Aplica clip(upper=p90). Agrega columna booleana 'capped'.

    El P90 se calcula SOLO sobre filas con monthly_total > 0 para evitar
    que los meses zero-filled (valor sintético, no gasto real) distorsionen
    el umbral hacia 0. Si no hay filas no-cero, no se capea nada.

    Uses 'lower' interpolation so P90 lands on an actual observed value.
    Rows at or above the P90 threshold are marked as capped=True.
    """
    df = df.copy()
    nonzero_vals = df.loc[df["monthly_total"] > 0, "monthly_total"]
    if nonzero_vals.empty:
        df["capped"] = False
        return df.reset_index(drop=True)
    p90 = nonzero_vals.quantile(0.90, interpolation="lower")
    # Mark capped BEFORE clipping (values at or above p90)
    df["capped"] = df["monthly_total"] >= p90
    df["monthly_total"] = df["monthly_total"].clip(upper=p90)
    return df.reset_index(drop=True)


def apply_gating(df: pd.DataFrame, min_months: int = 3) -> pd.DataFrame:
    """
    Cuenta meses únicos con monthly_total > 0 por (idmember, defaultcategory).
    Excluye pares con count < min_months.
    Zero-filled months (monthly_total == 0) do NOT count toward the gating threshold.
    """
    nonzero = df[df["monthly_total"] > 0]
    month_counts = (
        nonzero
        .groupby(["idmember", "defaultcategory"])["period_yyyymm"]
        .nunique()
        .reset_index(name="month_count")
    )
    qualifying = month_counts[month_counts["month_count"] >= min_months][
        ["idmember", "defaultcategory"]
    ]
    result = pd.merge(df, qualifying, on=["idmember", "defaultcategory"], how="inner")
    return result.reset_index(drop=True)


def prepare_smart_budget_data(
    df: pd.DataFrame,
    min_months: int = 3,
) -> pd.DataFrame:
    """
    Orquesta el pipeline completo:
    aggregate_monthly → zero_fill → apply_p90_cap → apply_gating.

    Returns DataFrame with columns:
        idclient, idcompany, idmember, defaultcategory, period_yyyymm,
        monthly_total (float, >= 0, <= P90), capped (bool).
    """
    monthly = aggregate_monthly(df)
    filled = zero_fill(monthly)
    capped = apply_p90_cap(filled)
    gated = apply_gating(capped, min_months=min_months)

    output_cols = [
        "idclient", "idcompany", "idmember", "defaultcategory",
        "period_yyyymm", "monthly_total", "capped",
    ]
    return gated[output_cols].reset_index(drop=True)
