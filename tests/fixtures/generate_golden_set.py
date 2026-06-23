#!/usr/bin/env python3
"""tests/fixtures/generate_golden_set.py — Deterministic golden set generator for DATA-1179.

Generates a new golden_set.csv with idmember grain.
- 6 months: 2025-10 to 2026-03
- >= 3 idmember: member 10, 20, 30
  - member 10: account EXT2 (EXT path)
  - member 20: account EXT22 + SUB8406 (OLB path)
  - member 30: account EXT33 — limited categories (tests gating)
- Data is deterministic (fixed seeds, no random_state inconsistency)
- Re-freezes golden_set.csv with WMA/A/2026-03 expected values

Usage:
    python tests/fixtures/generate_golden_set.py

Guard: this script MUST NOT be run with --source db or in production.
"""
import sys
import os
import pathlib

# Guard: prevent accidental run in production
if os.environ.get("ENVIRONMENT", "").lower() in ("prod", "production"):
    print("ERROR: generate_golden_set.py must not run in production environment.")
    sys.exit(1)

# Add src/ to path
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from smart_budget.aggregator import apply_gating
from smart_budget.model import compute_budget_suggestions

PERIODS_6 = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]

# ---------------------------------------------------------------------------
# Deterministic synthetic data: 3+ idmembers, 6 months, 3+ categories each
# ---------------------------------------------------------------------------


def build_synthetic_data() -> pd.DataFrame:
    """Build deterministic synthetic dataset with idmember grain."""
    rows = []

    # member 10 — EXT account (idaccount=EXT2)
    # 3 categories, all 6 months
    member10_data = [
        # (idcategory, defaultcategory, monthly_totals by period)
        ("1", "Auto & Transport", [120.0, 130.0, 140.0, 125.0, 135.0, 115.0]),
        ("5", "GROCERIES", [200.0, 180.0, 220.0, 190.0, 210.0, 205.0]),
        ("2", "Bills & Utilities", [80.0, 85.0, 90.0, 75.0, 88.0, 82.0]),
    ]
    for idcat, defcat, totals in member10_data:
        for period, total in zip(PERIODS_6, totals):
            rows.append(
                {
                    "idclient": "1",
                    "idcompany": "1",
                    "idmember": "10",
                    "idaccount": "EXT2",
                    "idcategory": idcat,
                    "defaultcategory": defcat,
                    "period_yyyymm": period,
                    "monthly_total": total,
                }
            )

    # member 20 — EXT22 + SUB8406 (two accounts mapped to same member)
    # After idmember grain collapse, their totals are summed
    member20_data_ext22 = [
        ("1", "Auto & Transport", [40.0, 45.0, 50.0, 42.0, 48.0, 44.0]),
        ("2", "Bills & Utilities", [55.0, 58.0, 62.0, 57.0, 60.0, 59.0]),
        ("6", "Health & Fitness", [70.0, 75.0, 72.0, 68.0, 76.0, 71.0]),
    ]
    member20_data_sub8406 = [
        (
            "1",
            "Auto & Transport",
            [30.0, 32.0, 35.0, 31.0, 33.0, 34.0],
        ),  # Will be summed with EXT22
        ("9", "Subscriptions", [25.0, 25.0, 25.0, 25.0, 25.0, 25.0]),
    ]
    for idcat, defcat, totals in member20_data_ext22:
        for period, total in zip(PERIODS_6, totals):
            rows.append(
                {
                    "idclient": "1",
                    "idcompany": "1",
                    "idmember": "20",
                    "idaccount": "EXT22",
                    "idcategory": idcat,
                    "defaultcategory": defcat,
                    "period_yyyymm": period,
                    "monthly_total": total,
                }
            )
    for idcat, defcat, totals in member20_data_sub8406:
        for period, total in zip(PERIODS_6, totals):
            rows.append(
                {
                    "idclient": "1",
                    "idcompany": "1",
                    "idmember": "20",
                    "idaccount": "SUB8406",
                    "idcategory": idcat,
                    "defaultcategory": defcat,
                    "period_yyyymm": period,
                    "monthly_total": total,
                }
            )

    # member 30 — EXT33 (limited categories — some won't pass gating)
    member30_data = [
        # These have all 6 months → will pass gating (min=3)
        ("5", "GROCERIES", [150.0, 160.0, 145.0, 155.0, 165.0, 150.0]),
        ("7", "Home & Rent", [1200.0, 1200.0, 1200.0, 1200.0, 1200.0, 1200.0]),
        ("3", "Food & Dining", [90.0, 95.0, 85.0, 92.0, 88.0, 91.0]),
        # This one only has 2 non-zero months → will NOT pass gating (min=3)
        # (zero-filled months don't count)
        ("10", "Entertainment & Leisure", [50.0, 0.0, 0.0, 0.0, 0.0, 55.0]),
    ]
    for idcat, defcat, totals in member30_data:
        for period, total in zip(PERIODS_6, totals):
            rows.append(
                {
                    "idclient": "1",
                    "idcompany": "1",
                    "idmember": "30",
                    "idaccount": "EXT33",
                    "idcategory": idcat,
                    "defaultcategory": defcat,
                    "period_yyyymm": period,
                    "monthly_total": total,
                }
            )

    return pd.DataFrame(rows)


def generate_golden_set(output_path: pathlib.Path) -> None:
    """Generate and save the golden set CSV.

    Format: one row per (idmember, category, period_yyyymm) with monthly_total (input)
    + suggested_amount/total_suggested (model output, denormalized per bucket).
    This gives period_yyyymm.nunique() == 6.
    """
    df = build_synthetic_data()

    # Save synthetic data next to data/dough for model consumption
    synthetic_path = ROOT / "data" / "dough" / "smart_budget_synthetic_idmember.csv"
    df.to_csv(synthetic_path, index=False)
    print(f"  Saved synthetic data → {synthetic_path} ({len(df)} rows)")

    # Apply gating
    prepared = apply_gating(df, min_months=3)
    print(
        f"  After gating: {len(prepared)} rows, {prepared['idmember'].nunique()} members"
    )

    # Compute WMA/A/2026-03 suggestions
    results = compute_budget_suggestions(
        prepared,
        method="wma",
        treatment="A",
        reference_date="2026-03-01",
    )
    print(f"  Suggestions computed: {len(results)}")

    # Build suggestion map: (idmember, category_id, defaultcategory) → suggestion data
    sugg_map = {}
    for r in results:
        key = (r["idmember"], r["category_id"], r["defaultcategory"])
        sugg_map[key] = {
            "suggested_amount": r["suggested_amount"],
            "total_suggested": r["total_suggested"],
            "confidence": r["confidence"],
            "months_analyzed": r["basis"]["months_analyzed"] if r["basis"] else None,
            "months_with_zero": r["basis"]["months_with_zero"] if r["basis"] else None,
            "months_with_positive_spend": (
                r["basis"]["months_with_positive_spend"] if r["basis"] else None
            ),
        }

    # Build golden set: one row per (idmember, category, period_yyyymm)
    # Only include buckets that passed gating (are in sugg_map)
    golden_rows = []
    for _, row in prepared.iterrows():
        key = (
            str(row["idmember"]),
            str(row["idcategory"]),
            str(row["defaultcategory"]),
        )
        if key not in sugg_map:
            continue
        sugg = sugg_map[key]
        golden_rows.append(
            {
                "idmember": row["idmember"],
                "idclient": row["idclient"],
                "idcompany": row["idcompany"],
                "category_id": row["idcategory"],
                "defaultcategory": row["defaultcategory"],
                "period_yyyymm": row["period_yyyymm"],
                "monthly_total": row["monthly_total"],
                "suggested_amount": sugg["suggested_amount"],
                "total_suggested": sugg["total_suggested"],
                "confidence": sugg["confidence"],
                "months_analyzed": sugg["months_analyzed"],
                "months_with_zero": sugg["months_with_zero"],
                "months_with_positive_spend": sugg["months_with_positive_spend"],
            }
        )

    golden_df = pd.DataFrame(golden_rows)

    # Verify constraints
    assert "idmember" in golden_df.columns, "idmember must be in golden set"
    assert golden_df["idmember"].nunique() >= 3, "Must have >= 3 distinct idmembers"
    assert (
        golden_df["period_yyyymm"].nunique() == 6
    ), f"Must have 6 distinct periods, got: {golden_df['period_yyyymm'].nunique()}"

    golden_df.to_csv(output_path, index=False)
    print(f"  Golden set saved → {output_path}")
    print(f"  Members: {sorted(golden_df['idmember'].unique())}")
    print(f"  Periods: {sorted(golden_df['period_yyyymm'].unique())}")
    print(f"  Total rows: {len(golden_df)}")


if __name__ == "__main__":
    output = ROOT / "tests" / "fixtures" / "golden_set.csv"
    print(f"\nGenerating golden_set.csv at {output}...")
    generate_golden_set(output)
    print("Done.\n")
