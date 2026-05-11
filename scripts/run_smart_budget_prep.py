#!/usr/bin/env python3
"""scripts/run_smart_budget_prep.py — CLI wrapper for Smart Budget data preparation pipeline.

Usage:
    python scripts/run_smart_budget_prep.py \\
        --input data/dough/fact_transactions.csv \\
        --output data/dough/smart_budget_prep.csv \\
        --min-months 3
"""
import argparse
import hashlib
import os
import sys

# Add src/ to path so smart_budget is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import structlog

from smart_budget.filters import filter_transactions
from smart_budget.aggregator import prepare_smart_budget_data

# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Required input columns
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {
    "idtransaction",
    "idclient",
    "idcompany",
    "idaccount",
    "defaultcategory",
    "incomeexpenditure",
    "amount",
    "date",
    "status",
    "deletedat",
}


def _sha256_file(path: str) -> str:
    """Compute SHA-256 hash of a file for provenance logging."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smart Budget data preparation pipeline"
    )
    parser.add_argument(
        "--input",
        default="data/dough/fact_transactions.csv",
        help="Path to input fact_transactions CSV",
    )
    parser.add_argument(
        "--output",
        default="data/dough/smart_budget_prep.csv",
        help="Path to write the prepared output CSV",
    )
    parser.add_argument(
        "--min-months",
        dest="min_months",
        type=int,
        default=3,
        help="Minimum months of data required for a bucket to be included (gating)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    input_path: str = args.input
    output_path: str = args.output
    min_months: int = args.min_months

    try:
        # ------------------------------------------------------------------ #
        # Job start
        # ------------------------------------------------------------------ #
        logger.info(
            "job_start",
            input_path=input_path,
            min_months=min_months,
        )

        # ------------------------------------------------------------------ #
        # Input schema validation
        # ------------------------------------------------------------------ #
        df_raw = pd.read_csv(input_path, dtype=str, keep_default_na=False)

        missing_cols = REQUIRED_COLUMNS - set(df_raw.columns)
        if missing_cols:
            raise ValueError(
                f"Input CSV is missing required columns: {sorted(missing_cols)}"
            )

        if df_raw.empty:
            raise ValueError("Input CSV has 0 rows — nothing to process.")

        # Convert types
        for col in ["deletedat", "status"]:
            df_raw[col] = df_raw[col].replace("", None)
        df_raw["amount"] = df_raw["amount"].astype(float)

        rows_original = len(df_raw)

        # ------------------------------------------------------------------ #
        # Filter
        # ------------------------------------------------------------------ #
        df_filtered = filter_transactions(df_raw)
        rows_after_filter = len(df_filtered)
        rows_removed = rows_original - rows_after_filter
        rows_removed_pct = (
            round(rows_removed / rows_original * 100, 2) if rows_original > 0 else 0.0
        )

        logger.info(
            "filter_complete",
            rows_original=rows_original,
            rows_after_filter=rows_after_filter,
            rows_removed_pct=rows_removed_pct,
        )

        # ------------------------------------------------------------------ #
        # Aggregation + pipeline
        # ------------------------------------------------------------------ #
        # Normalizar montos: en fact_transactions los gastos vienen como
        # negativos (convención débito negativo). Tomamos valor absoluto para
        # que la agregación opere con cantidades positivas. El filtro ya
        # garantiza que solo quedan registros tipo gasto.
        df_filtered = df_filtered.copy()
        df_filtered["amount"] = df_filtered["amount"].abs()

        df_out = prepare_smart_budget_data(df_filtered, min_months=min_months)

        unique_members = df_out["idaccount"].nunique()
        unique_categories = df_out["defaultcategory"].nunique()
        periods = sorted(df_out["period_yyyymm"].unique())
        periods_range = f"{periods[0]}..{periods[-1]}" if periods else "none"

        logger.info(
            "aggregation_complete",
            unique_accounts=unique_members,
            unique_categories=unique_categories,
            periods_range=periods_range,
        )

        # ------------------------------------------------------------------ #
        # P90 cap stats
        # ------------------------------------------------------------------ #
        # ------------------------------------------------------------------ #
        # Gating stats
        # ------------------------------------------------------------------ #
        from smart_budget.aggregator import aggregate_monthly, zero_fill

        monthly = aggregate_monthly(df_filtered)
        filled = zero_fill(monthly)
        total_buckets_before = filled.groupby(["idaccount", "defaultcategory"]).ngroups
        total_buckets_after = df_out.groupby(["idaccount", "defaultcategory"]).ngroups
        buckets_removed = total_buckets_before - total_buckets_after
        rows_in_output = len(df_out)

        logger.info(
            "gating_complete",
            buckets_removed=buckets_removed,
            rows_in_output=rows_in_output,
        )

        # ------------------------------------------------------------------ #
        # Atomic write with restricted permissions
        # ------------------------------------------------------------------ #
        tmp_path = output_path + ".tmp"
        df_out.to_csv(tmp_path, index=False)
        os.replace(tmp_path, output_path)
        os.chmod(output_path, 0o600)

        # Provenance hash of input file
        try:
            input_hash = _sha256_file(input_path)
        except OSError:
            input_hash = "unavailable"

        logger.info(
            "job_done",
            output_path=output_path,
            output_rows=rows_in_output,
            input_file_hash=input_hash,
        )

    except Exception as exc:
        # F2 — Sanitized error logging: no raw DataFrame, no member IDs, no amounts
        logger.error(
            "pipeline_failed",
            error_type=type(exc).__name__,
            hint="ver logs para detalles; no se expone contenido de datos",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
