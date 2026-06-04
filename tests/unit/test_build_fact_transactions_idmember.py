"""tests/unit/test_build_fact_transactions_idmember.py — TDD tests for DATA-1179 T1.

Test contracts for _resolve_idmember function in build_fact_transactions.py.
"""
import sys
import os
import math

import pandas as pd
import pytest

# Allow importing scripts/build_fact_transactions directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))


# ---------------------------------------------------------------------------
# TC-T1-1: EXT account resolves idmember
# ---------------------------------------------------------------------------

def test_TC_T1_1_ext_account_resolves_idmember():
    """Arrange: fact with idaccount="EXT2", memberaccount with idaccount=2, idmember=10.
    Act: _resolve_idmember(fact, memberaccount, account)
    Assert: fact["idmember"].iloc[0] == 10
    """
    from build_fact_transactions import _resolve_idmember

    fact = pd.DataFrame({
        "idaccount": ["EXT2"],
        "amount": [100.0],
    })
    memberaccount = pd.DataFrame({
        "idaccount": [2],
        "idmember": [10],
    })
    account = pd.DataFrame({
        "blossomdoughconsolidatedaccountid": [],
        "id": [],
    })

    result = _resolve_idmember(fact, memberaccount, account)
    assert result["idmember"].iloc[0] == 10


# ---------------------------------------------------------------------------
# TC-T1-2: OLB account resolves idmember via blossomdoughconsolidatedaccountid
# ---------------------------------------------------------------------------

def test_TC_T1_2_olb_account_resolves_idmember_via_consolidated():
    """Arrange: fact with idaccount="SUB8406",
       account with blossomdoughconsolidatedaccountid="SUB8406" and id=50,
       memberaccount with idaccount=50, idmember=20.
    Act: _resolve_idmember(fact, memberaccount, account)
    Assert: fact["idmember"].iloc[0] == 20
    """
    from build_fact_transactions import _resolve_idmember

    fact = pd.DataFrame({
        "idaccount": ["SUB8406"],
        "amount": [200.0],
    })
    memberaccount = pd.DataFrame({
        "idaccount": [50],
        "idmember": [20],
    })
    account = pd.DataFrame({
        "blossomdoughconsolidatedaccountid": ["SUB8406"],
        "id": [50],
    })

    result = _resolve_idmember(fact, memberaccount, account)
    assert result["idmember"].iloc[0] == 20


# ---------------------------------------------------------------------------
# TC-T1-3: Account without match → idmember is None/NaN
# ---------------------------------------------------------------------------

def test_TC_T1_3_unmatched_account_idmember_is_nan():
    """Arrange: fact with idaccount="SUB9999", no match in account or memberaccount.
    Act: _resolve_idmember(fact, memberaccount, account)
    Assert: pd.isna(fact["idmember"].iloc[0])
    """
    from build_fact_transactions import _resolve_idmember

    fact = pd.DataFrame({
        "idaccount": ["SUB9999"],
        "amount": [50.0],
    })
    memberaccount = pd.DataFrame({
        "idaccount": [1, 2, 3],
        "idmember": [10, 20, 30],
    })
    account = pd.DataFrame({
        "blossomdoughconsolidatedaccountid": ["SUB0001", "SUB0002"],
        "id": [1, 2],
    })

    result = _resolve_idmember(fact, memberaccount, account)
    assert pd.isna(result["idmember"].iloc[0])


# ---------------------------------------------------------------------------
# TC-T1-4: idmember in CANONICAL_COLS
# ---------------------------------------------------------------------------

def test_TC_T1_4_idmember_in_canonical_cols():
    """Assert: "idmember" is present in CANONICAL_COLS."""
    from build_fact_transactions import CANONICAL_COLS
    assert "idmember" in CANONICAL_COLS


# ---------------------------------------------------------------------------
# TC-T1-5: EXT strip with non-numeric value → idmember = None, warning logged
# ---------------------------------------------------------------------------

def test_TC_T1_5_ext_non_numeric_idmember_null_and_warning(caplog):
    """Arrange: fact with idaccount="EXTABC" (non-numeric after strip).
    Act: _resolve_idmember(...)
    Assert: pd.isna(row["idmember"]) AND warning is logged.
    """
    import logging
    from build_fact_transactions import _resolve_idmember

    fact = pd.DataFrame({
        "idaccount": ["EXTABC"],
        "amount": [100.0],
    })
    memberaccount = pd.DataFrame({
        "idaccount": [2],
        "idmember": [10],
    })
    account = pd.DataFrame({
        "blossomdoughconsolidatedaccountid": [],
        "id": [],
    })

    import structlog
    import io

    # Capture structlog output
    log_output = []

    def capture_processor(logger, method, event_dict):
        log_output.append(event_dict.copy())
        raise structlog.DropEvent()

    old_processors = structlog.get_config().get("processors", [])
    structlog.configure(processors=[capture_processor])

    try:
        result = _resolve_idmember(fact, memberaccount, account)
    finally:
        structlog.configure(processors=old_processors)

    assert pd.isna(result["idmember"].iloc[0])
    # Verify warning was logged about invalid EXT account
    events = [e.get("event", "") for e in log_output]
    assert any("invalid_ext_account" in str(e) for e in events), (
        f"Expected 'invalid_ext_account' warning in logs, got: {events}"
    )


# ---------------------------------------------------------------------------
# TC-T1-6: --source db uses parameterized queries (no SQL string concatenation)
# ---------------------------------------------------------------------------

def test_TC_T1_6_db_source_uses_parameterized_queries():
    """Arrange: mock DB connection that records executed queries.
    Act: build_fact_transactions pipeline --source db with idmember JOIN.
    Assert: No JOIN string contains blossomdoughconsolidatedaccountid literal value.
    """
    from build_fact_transactions import _resolve_idmember_db

    executed_queries = []
    executed_params = []

    class MockCursor:
        def execute(self, query, params=None):
            executed_queries.append(query)
            executed_params.append(params)
        def fetchall(self):
            return []
        @property
        def description(self):
            return [("idmember",)]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class MockConn:
        def cursor(self):
            return MockCursor()

    account_ids = ["SUB8406", "EXT2"]
    _resolve_idmember_db(MockConn(), account_ids)

    # Assert all queries use parameterized form (% placeholders), not string literals
    for query, params in zip(executed_queries, executed_params):
        for account_id in account_ids:
            assert account_id not in query, (
                f"SQL query contains literal account_id '{account_id}' — "
                f"should use parameterized queries: {query}"
            )
