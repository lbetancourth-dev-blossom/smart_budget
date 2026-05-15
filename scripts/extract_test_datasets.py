"""scripts/extract_test_datasets.py — Extract test datasets by transaction source (DATA-1139).

Produces:
  - test_internal.csv  — OLB transactions (SUB/LOAN prefix)
  - test_external.csv  — External Dough/Plaid transactions (EXT prefix)

Both datasets pass through filter_transactions() and contain only OUTPUT_COLUMNS
(data minimization — security control SC-1).

Usage:
    python scripts/extract_test_datasets.py \\
        --input data/dough/fact_transactions.csv \\
        --output-dir data/dough/test/
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd  # noqa: E402
import structlog  # noqa: E402

from smart_budget.filters import filter_transactions  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Columns written to output CSVs — data minimization (SC-1).
#: Never write full CANONICAL_COLS (contains PII: description, note, balance, enrichment).
OUTPUT_COLUMNS: list[str] = [
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
]

#: Minimum columns required in the input DataFrame.
REQUIRED_COLUMNS: frozenset[str] = frozenset(OUTPUT_COLUMNS)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def split_by_source(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Separate a DataFrame into internal (OLB) and external (Dough/Plaid) transactions.

    Args:
        df: Filtered DataFrame with fact_transactions schema.

    Returns:
        Tuple ``(internal_df, external_df, n_unknown)`` where:

        - *internal_df*: rows whose ``idtransaction`` starts with ``"SUB"`` or ``"LOAN"``
        - *external_df*: rows whose ``idtransaction`` starts with ``"EXT"``
        - *n_unknown*: number of rows excluded because their prefix is unrecognised
    """
    is_internal = df["idtransaction"].str.startswith(("SUB", "LOAN"))
    is_external = df["idtransaction"].str.startswith("EXT")
    is_known = is_internal | is_external
    n_unknown = int((~is_known).sum())

    # Restrict to OUTPUT_COLUMNS (SC-1); only keep cols that actually exist in df
    out_cols = [c for c in OUTPUT_COLUMNS if c in df.columns]

    internal_df = df.loc[is_internal, out_cols].reset_index(drop=True)
    external_df = df.loc[is_external, out_cols].reset_index(drop=True)

    return internal_df, external_df, n_unknown


def write_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write *df* as CSV to *path* atomically with restricted permissions.

    Security controls (SC-2, SC-3):
    - The temporary file uses a PID-based suffix to avoid race conditions.
    - ``chmod 0o600`` is applied to the ``.tmp`` file **before** ``os.replace``
      so the data is never world-readable even for a brief moment.

    Args:
        df: DataFrame to write.
        path: Final destination path.
    """
    tmp = Path(str(path) + f".{os.getpid()}.tmp")  # SC-2: PID suffix
    df.to_csv(tmp, index=False)
    os.chmod(tmp, 0o600)                             # SC-3: secure .tmp before replace
    os.replace(tmp, path)
    os.chmod(path, 0o600)                            # double-secure final file


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:  # pragma: no cover — integration path tested via pytest fixtures
    """Parse CLI arguments, run pipeline, write outputs."""
    parser = argparse.ArgumentParser(
        description="Extract test_internal.csv and test_external.csv from fact_transactions."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_REPO_ROOT / "data" / "dough" / "fact_transactions.csv",
        help="Path to fact_transactions.csv (default: data/dough/fact_transactions.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "data" / "dough" / "test",
        help="Output directory (default: data/dough/test/)",
    )
    args = parser.parse_args()

    input_path: Path = args.input.resolve()
    output_dir: Path = args.output_dir.resolve()

    logger.info("job_start", input_path=str(input_path))

    # ------------------------------------------------------------------
    # Validate input
    # ------------------------------------------------------------------
    if not input_path.exists():
        logger.error("input_not_found", path=str(input_path))
        sys.exit(1)

    df = pd.read_csv(input_path)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        logger.error("schema_error", missing=sorted(missing))
        sys.exit(1)

    # ------------------------------------------------------------------
    # Warn if output dir is outside data/
    # ------------------------------------------------------------------
    data_dir = (_REPO_ROOT / "data").resolve()
    try:
        output_dir.relative_to(data_dir)
    except ValueError:
        logger.warning("output_outside_data_dir", path=str(output_dir))

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------
    rows_before = len(df)
    df = filter_transactions(df)
    rows_after = len(df)
    logger.info("filter_applied", rows_before=rows_before, rows_after=rows_after)

    if df.empty:
        logger.warning("empty_after_filter", rows_before=rows_before)

    # ------------------------------------------------------------------
    # Split by source
    # ------------------------------------------------------------------
    internal, external, n_unknown = split_by_source(df)

    if n_unknown > 0:
        logger.warning("unknown_prefix_skipped", n_unknown=n_unknown)

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)

    p_internal = output_dir / "test_internal.csv"
    p_external = output_dir / "test_external.csv"

    write_atomic(internal, p_internal)
    logger.info(
        "write_complete",
        file="test_internal.csv",
        rows=len(internal),
        path=str(p_internal),
    )

    write_atomic(external, p_external)
    logger.info(
        "write_complete",
        file="test_external.csv",
        rows=len(external),
        path=str(p_external),
    )

    logger.info(
        "job_done",
        n_internal_rows=len(internal),
        n_external_rows=len(external),
        n_unknown_skipped=n_unknown,
        n_internal_accounts=len(internal["idaccount"].unique()) if len(internal) else 0,
        n_external_accounts=len(external["idaccount"].unique()) if len(external) else 0,
    )


if __name__ == "__main__":
    main()
