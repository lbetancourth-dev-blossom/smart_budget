"""scripts/run_methods.py — CLI to run budget suggestion methods (DATA-1137).

Usage:
    python scripts/run_methods.py \\
        --method wma \\
        --treatment A \\
        --reference-date 2026-03-01 \\
        [--input data/dough/smart_budget_synthetic.csv] \\
        [--output results.json] \\
        [--min-months 3]

Output is a JSON list of suggestion dicts, written to --output or stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running directly: python scripts/run_methods.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pandas as pd
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
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
        choices=["wma", "ewma", "holt_winters"],
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
        metavar="YYYY-MM-DD",
        help="Cutoff date — months up to and including this month are used",
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
        "--min-months",
        type=int,
        default=3,
        dest="min_months",
        help="Minimum months with positive spend for gating (default: 3)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)

    log = logger.bind(
        method=args.method,
        treatment=args.treatment,
        reference_date=args.reference_date,
        input_path=args.input,
    )
    log.info("run_methods.start")

    # Step 1: read CSV
    raw_df = pd.read_csv(args.input)

    # Step 2: apply gating (CSV is already aggregated monthly data)
    prepared_df = apply_gating(raw_df, min_months=args.min_months)

    # Step 3: compute suggestions
    results = compute_budget_suggestions(
        prepared_df,
        method=args.method,
        treatment=args.treatment,
        reference_date=args.reference_date,
    )

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
    log.info("run_methods.done", n_suggestions=n_suggestions, n_null_suggestions=n_null)


if __name__ in ("__main__", "__test__"):
    main()
