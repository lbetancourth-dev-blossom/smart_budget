"""tests/unit/test_run_methods_output.py — TDD tests for DATA-1179 T5.

Test contracts for run_methods.py output with idmember + total_suggested.
"""
import sys
import os
import json
import io
import pathlib
import tempfile

import pandas as pd
import pytest

# Add scripts/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


def _make_synthetic_csv(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a minimal synthetic CSV with idmember for run_methods testing."""
    rows = []
    # member 10: 3+ months for GROCERIES to pass gating
    for period, total in [("2025-10", 100.0), ("2025-11", 110.0), ("2025-12", 120.0)]:
        rows.append({
            "idclient": "C1",
            "idcompany": "CO1",
            "idmember": 10,
            "idaccount": "EXT10",
            "idcategory": "5",
            "defaultcategory": "GROCERIES",
            "period_yyyymm": period,
            "monthly_total": total,
        })
    # member 20: 3+ months for DINING
    for period, total in [("2025-10", 200.0), ("2025-11", 210.0), ("2025-12", 220.0)]:
        rows.append({
            "idclient": "C1",
            "idcompany": "CO1",
            "idmember": 20,
            "idaccount": "EXT20",
            "idcategory": "9",
            "defaultcategory": "DINING",
            "period_yyyymm": period,
            "monthly_total": total,
        })
    df = pd.DataFrame(rows)
    csv_path = tmp_path / "test_synthetic.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


# ---------------------------------------------------------------------------
# TC-T5-1: output JSON contains idmember and total_suggested fields
# ---------------------------------------------------------------------------

def test_TC_T5_1_output_has_idmember_and_total_suggested(tmp_path):
    """Arrange: run pipeline complete with synthetic data that has idmember.
    Act: run_methods.main with synthetic CSV.
    Assert: 'idmember' in output keys, 'total_suggested' in output keys.
    """
    from run_methods import main

    input_csv = _make_synthetic_csv(tmp_path)
    output_json = tmp_path / "output.json"

    main([
        "--method", "wma",
        "--treatment", "A",
        "--reference-date", "2026-03",
        "--input", str(input_csv),
        "--output", str(output_json),
        "--min-months", "2",
    ])

    assert output_json.exists(), "Output JSON file should have been created"
    results = json.loads(output_json.read_text())
    assert len(results) > 0, "Output should have at least one suggestion"

    r = results[0]
    assert "idmember" in r, (
        f"Expected 'idmember' in output result keys, got: {list(r.keys())}"
    )
    assert "total_suggested" in r, (
        f"Expected 'total_suggested' in output result keys, got: {list(r.keys())}"
    )
    # idaccount should not be in output (grain changed to idmember)
    assert "idaccount" not in r, (
        f"'idaccount' should not be in output — grain changed to idmember: {list(r.keys())}"
    )
