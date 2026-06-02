"""scripts/run_methods.py — CLI to run budget suggestion methods (DATA-1137).

Usage:
    python scripts/run_methods.py \\
        --method wma \\
        --treatment A \\
        --reference-date 2026-05 \\
        [--lookback-months 3] \\
        [--input data/dough/smart_budget_synthetic.csv] \\
        [--output results.json] \\
        [--min-months 3]

Output is a JSON list of suggestion dicts, written to --output or stdout.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import uuid

# Allow running directly: python scripts/run_methods.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pandas as pd
import structlog

import sys as _sys

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=_sys.stderr),
)

from smart_budget.aggregator import apply_gating
from smart_budget.model import compute_budget_suggestions

logger = structlog.get_logger()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Smart Budget suggestion model (DATA-1137)",
    )
    parser.add_argument(
        "--method",
        required=True,
        choices=["wma", "ewma", "holt_winters", "median"],
        help="Forecasting method to use",
    )
    parser.add_argument(
        "--treatment",
        default="A",
        choices=["A", "B", "C"],
        help="Zero-treatment variant (default: A)",
    )
    parser.add_argument(
        "--reference-date",
        required=True,
        metavar="YYYY-MM",
        help=(
            "Mes de referencia (inclusive). Acepta YYYY-MM o YYYY-MM-DD. "
            "Ej: 2026-05 o 2026-05-01"
        ),
    )
    parser.add_argument(
        "--input",
        default="data/dough/smart_budget_synthetic.csv",
        metavar="CSV_PATH",
        help="Path to input CSV (default: data/dough/smart_budget_synthetic.csv)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="JSON_PATH",
        help="Output JSON path (default: stdout)",
    )
    parser.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        dest="lookback_months",
        metavar="N",
        help=(
            "Ventana de meses hacia atrás desde reference_date (inclusive). "
            "Default: todos los meses disponibles. "
            "Ej: --lookback-months 3 con --reference-date 2026-05-01 "
            "usa: 2026-03, 2026-04, 2026-05."
        ),
    )
    parser.add_argument(
        "--min-months",
        type=int,
        default=3,
        dest="min_months",
        help="Minimum months with positive spend for gating (default: 3)",
    )
    return parser.parse_args(argv)


def _normalize_reference_date(value: str) -> str:
    """Acepta YYYY-MM o YYYY-MM-DD y devuelve siempre YYYY-MM."""
    parts = value.strip().split("-")
    if len(parts) < 2:
        raise ValueError(f"--reference-date inválido: {value!r}. Formato esperado: YYYY-MM")
    try:
        year, month = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"--reference-date inválido: {value!r}. Formato esperado: YYYY-MM")
    if year < 2000 or month < 1 or month > 12:
        raise ValueError(f"--reference-date fuera de rango: {value!r}")
    return f"{year:04d}-{month:02d}"


def main(argv=None):
    args = _parse_args(argv)
    reference_date = _normalize_reference_date(args.reference_date)
    started_at = datetime.datetime.utcnow().isoformat() + "Z"
    job_id = str(uuid.uuid4())

    log = logger.bind(
        method=args.method,
        treatment=args.treatment,
        reference_date=reference_date,
        lookback_months=args.lookback_months,
        input_path=args.input,
    )
    log.info("run_methods.start")

    # Step 1: read CSV
    raw_df = pd.read_csv(args.input)

    # Count null idmember rows before filtering
    n_null_idmember = 0
    if "idmember" in raw_df.columns:
        n_null_idmember = int(raw_df["idmember"].isna().sum())

    # Step 2: apply gating (CSV is already aggregated monthly data)
    prepared_df = apply_gating(raw_df, min_months=args.min_months)

    # Step 3: compute suggestions
    results = compute_budget_suggestions(
        prepared_df,
        method=args.method,
        treatment=args.treatment,
        reference_date=reference_date,
        lookback_months=args.lookback_months,
    )

    # Warn if idmember is not in results (backward-compat check)
    if results and "idmember" not in results[0]:
        log.warning("run_methods.idmember_missing", hint="Results do not contain idmember — check pipeline input")

    # Step 4: serialize
    output_json = json.dumps(results, indent=2, ensure_ascii=False)

    # Step 5: write
    if args.output is not None:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output_json)
    else:
        print(output_json)

    n_suggestions = sum(1 for r in results if r.get("suggested_amount") is not None)
    n_null = sum(1 for r in results if r.get("suggested_amount") is None)
    n_members = len(set(r.get("idmember", r.get("idaccount", "?")) for r in results))
    finished_at = datetime.datetime.utcnow().isoformat() + "Z"

    log.info("run_methods.done", n_suggestions=n_suggestions, n_null_suggestions=n_null, n_members=n_members)

    # Structured audit log for compliance/traceability (DATA-1179)
    from smart_budget.model import _MODEL_VERSION  # noqa: PLC0415
    log.info(
        "run_methods.audit",
        job_id=job_id,
        model_version=_MODEL_VERSION,
        n_members_processed=n_members,
        n_null_idmember=n_null_idmember,
        started_at=started_at,
        finished_at=finished_at,
    )


if __name__ in ("__main__", "__test__"):
    main()
