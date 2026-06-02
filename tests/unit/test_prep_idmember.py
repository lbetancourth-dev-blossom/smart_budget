"""tests/unit/test_prep_idmember.py — TDD tests for DATA-1179 T2.

Test contracts for run_smart_budget_prep.py idmember handling.
"""
import sys
import os
import io

import pandas as pd
import pytest

# Add scripts/ to path for direct import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))


def _make_prep_df(include_idmember: bool = True) -> pd.DataFrame:
    """Build minimal dataframe for prep pipeline testing."""
    base = {
        "idtransaction": ["T1", "T2", "T3", "T4", "T5"],
        "idclient": ["C1"] * 5,
        "idcompany": ["CO1"] * 5,
        "idaccount": ["EXT2", "EXT2", "EXT2", "EXT2", "EXT2"],
        "defaultcategory": ["GROCERIES"] * 5,
        "incomeexpenditure": ["expenditure"] * 5,
        "amount": [100.0, 80.0, 90.0, 70.0, 110.0],
        "date": ["2025-01-05", "2025-02-05", "2025-03-05", "2025-04-05", "2025-05-05"],
        "status": ["", "", "", "", ""],
        "deletedat": ["", "", "", "", ""],
        "idcategory": ["5"] * 5,
    }
    if include_idmember:
        base["idmember"] = [10, 10, 10, 10, 10]
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# TC-T2-1: Dataset with idmember passes validation
# ---------------------------------------------------------------------------

def test_TC_T2_1_dataset_with_idmember_passes_validation():
    """Arrange: df with all REQUIRED_COLUMNS including idmember.
    Act: prep pipeline (validate_columns).
    Assert: no idmember warnings, idmember in output.
    """
    from run_smart_budget_prep import validate_columns

    df = _make_prep_df(include_idmember=True)

    log_events = []

    import structlog

    def capture_processor(logger, method, event_dict):
        log_events.append(event_dict.copy())
        raise structlog.DropEvent()

    structlog.configure(processors=[capture_processor])
    try:
        result_df, warnings = validate_columns(df)
    finally:
        structlog.configure(processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ])

    # No idmember warning should be in the logs
    idmember_warnings = [
        e for e in log_events
        if "idmember" in str(e.get("event", "")).lower() and "missing" in str(e.get("event", "")).lower()
    ]
    assert len(idmember_warnings) == 0, (
        f"Unexpected idmember warning when idmember is present: {idmember_warnings}"
    )
    # idmember should be in output
    assert "idmember" in result_df.columns


# ---------------------------------------------------------------------------
# TC-T2-2: Dataset without idmember emits warning but does not fail
# ---------------------------------------------------------------------------

def test_TC_T2_2_dataset_without_idmember_warns_but_completes():
    """Arrange: df without idmember column.
    Act: prep pipeline (validate_columns).
    Assert: log contains 'idmember column missing', pipeline completes without exception.
    """
    from run_smart_budget_prep import validate_columns

    df = _make_prep_df(include_idmember=False)

    log_events = []

    import structlog

    def capture_processor(logger, method, event_dict):
        log_events.append(event_dict.copy())
        raise structlog.DropEvent()

    structlog.configure(processors=[capture_processor])
    try:
        result_df, warnings = validate_columns(df)
    finally:
        structlog.configure(processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ])

    # Should have logged an idmember missing warning
    idmember_events = [e for e in log_events if "idmember" in str(e)]
    assert len(idmember_events) > 0, (
        f"Expected 'idmember column missing' warning in logs, got: {log_events}"
    )
    assert any("missing" in str(e).lower() for e in idmember_events), (
        f"Expected 'missing' in idmember event: {idmember_events}"
    )

    # Pipeline should complete without exception — result_df should exist
    assert result_df is not None
    # warnings should mention idmember
    assert any("idmember" in str(w).lower() for w in warnings), (
        f"Expected idmember in warnings list: {warnings}"
    )
