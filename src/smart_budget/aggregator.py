"""src/smart_budget/aggregator.py — Aggregation pipeline for Smart Budget."""

import pandas as pd
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
_logger = structlog.get_logger()


def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa por (idclient, idcompany, idmember, idaccount, category_id, category_name, period_yyyymm)
    y suma amount. Clampea negativos a 0. Retorna columna monthly_total.

    Crea period_yyyymm desde la columna `date` como "YYYY-MM".
    idaccount se mantiene en el groupby para preservar granularidad; el cambio
    de grain a idmember ocurre en apply_gating y model.py.
    """
    df = df.copy()
    df["period_yyyymm"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)

    group_keys = [
        "idclient",
        "idcompany",
        "idmember",
        "idaccount",
        "category_id",
        "category_name",
        "period_yyyymm",
    ]
    # Only include keys present in the df
    group_keys = [k for k in group_keys if k in df.columns]
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

    Each idmember must map to exactly one (idclient, idcompany) pair.

    Raises:
        ValueError: if any idmember maps to more than one (idclient, idcompany) pair.
    """
    has_idmember = "idmember" in df.columns

    if has_idmember:
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
    else:
        # Legacy path: validate idaccount
        member_company = (
            df[["idaccount", "idclient", "idcompany"]]
            .drop_duplicates()
            .groupby("idaccount")
            .size()
        )
        violations = member_company[member_company > 1]
        if not violations.empty:
            raise ValueError(
                f"idaccount maps to multiple (idclient, idcompany) pairs: "
                f"{len(violations)} account(s) violated the uniqueness constraint."
            )

    # Determine all months in [min_month, max_month] range
    periods = pd.PeriodIndex(df["period_yyyymm"].unique(), freq="M")
    all_months = pd.period_range(start=periods.min(), end=periods.max(), freq="M")
    all_months_str = [str(p) for p in all_months]

    # Get unique member×category pairs (include idmember if present)
    member_cols = ["idclient", "idcompany", "idaccount", "category_id", "category_name"]
    if has_idmember:
        member_cols = [
            "idclient",
            "idcompany",
            "idmember",
            "idaccount",
            "category_id",
            "category_name",
        ]
    member_cat = df[member_cols].drop_duplicates()

    # Build full grid: cross join member_cat × all_months
    months_df = pd.DataFrame({"period_yyyymm": all_months_str})
    months_df["_key"] = 1
    member_cat = member_cat.copy()
    member_cat["_key"] = 1
    full_grid = pd.merge(member_cat, months_df, on="_key").drop(columns=["_key"])

    # Left join grid ← actual data
    join_keys = ["idaccount", "category_id", "category_name", "period_yyyymm"]
    if has_idmember:
        join_keys = [
            "idmember",
            "idaccount",
            "category_id",
            "category_name",
            "period_yyyymm",
        ]
    agg_cols = join_keys + ["monthly_total"]
    result = pd.merge(
        full_grid,
        df[agg_cols],
        on=join_keys,
        how="left",
    )
    result["monthly_total"] = result["monthly_total"].fillna(0.0)

    return result.reset_index(drop=True)


def apply_gating(df: pd.DataFrame, min_months: int = 3) -> pd.DataFrame:
    """
    Cuenta meses únicos con monthly_total > 0 por (idclient, idcompany, idmember, category_id, category_name).
    Excluye pares con count < min_months.
    Zero-filled months (monthly_total == 0) do NOT count toward the gating threshold.

    Security [AUTH-2]: idclient and idcompany are included in the groupby to prevent
    cross-tenant mixing when different CUs share the same idmember integer value.
    """
    has_idmember = "idmember" in df.columns

    nonzero = df[df["monthly_total"] > 0]

    if has_idmember:
        gating_keys = [
            "idclient",
            "idcompany",
            "idmember",
            "category_id",
            "category_name",
        ]
    else:
        gating_keys = [
            "idclient",
            "idcompany",
            "idaccount",
            "category_id",
            "category_name",
        ]

    month_counts = (
        nonzero.groupby(gating_keys)["period_yyyymm"]
        .nunique()
        .reset_index(name="month_count")
    )
    qualifying = month_counts[month_counts["month_count"] >= min_months][gating_keys]
    result = pd.merge(df, qualifying, on=gating_keys, how="inner")
    return result.reset_index(drop=True)


def prepare_smart_budget_data(
    df: pd.DataFrame,
    min_months: int = 3,
) -> pd.DataFrame:
    """
    Orquesta el pipeline completo:
    aggregate_monthly → zero_fill → apply_gating.

    Returns DataFrame with columns:
        idclient, idcompany, idmember, category_id, category_name, period_yyyymm,
        monthly_total (float, >= 0).

    Note: idaccount is removed from output — the model grain is idmember.
    Rows with null idmember are dropped with a structlog warning before returning.
    """
    monthly = aggregate_monthly(df)
    filled = zero_fill(monthly)
    gated = apply_gating(filled, min_months=min_months)

    has_idmember = "idmember" in gated.columns

    if has_idmember:
        # Drop rows with null idmember
        null_mask = gated["idmember"].isna()
        if null_mask.any():
            n_null = null_mask.sum()
            _logger.warning(
                "null_idmember_rows_dropped",
                n_rows=int(n_null),
                hint="Rows without idmember excluded from model output",
            )
            gated = gated[~null_mask]

        output_cols = [
            "idclient",
            "idcompany",
            "idmember",
            "category_id",
            "category_name",
            "period_yyyymm",
            "monthly_total",
        ]
    else:
        # Legacy path: idmember not available
        output_cols = [
            "idclient",
            "idcompany",
            "category_id",
            "category_name",
            "period_yyyymm",
            "monthly_total",
        ]

    # Only include columns that exist
    output_cols = [c for c in output_cols if c in gated.columns]
    return gated[output_cols].reset_index(drop=True)
