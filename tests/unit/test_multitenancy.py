"""tests/unit/test_multitenancy.py — Multi-tenancy + audit log tests (DATA-1179 T7).

TC-T7-1: no cross-member leak in total_suggested
TC-T7-2: cross-company idmember collision raises ValueError
TC-T7-3: pipeline emits structured audit log at batch completion
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import textwrap

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure src is on path
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from smart_budget.model import compute_budget_suggestions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_monthly_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal monthly-aggregated DataFrame for model input."""
    return pd.DataFrame(rows)


def _months_6() -> list[str]:
    return ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]


def _member_df(idmember: int, idclient: int, idcompany: int,
               idcategory: str, defaultcategory: str,
               amounts: list[float]) -> list[dict]:
    """Create 6 monthly rows for one member/category."""
    months = _months_6()[: len(amounts)]
    return [
        {
            "idmember": idmember,
            "idclient": idclient,
            "idcompany": idcompany,
            "idcategory": idcategory,
            "defaultcategory": defaultcategory,
            "period_yyyymm": m,
            "monthly_total": amt,
        }
        for m, amt in zip(months, amounts)
    ]


# ---------------------------------------------------------------------------
# TC-T7-1: no cross-member leak in total_suggested
# ---------------------------------------------------------------------------

class TestTC_T7_1_NoCrossMemberLeak:
    """total_suggested must be computed independently per member.

    If member_A spends 100/month and member_B spends 500/month, they must
    NOT see each other's amounts in total_suggested.
    """

    def test_total_suggested_is_member_scoped(self):
        """Arrange: 2 members same category same company.
        Act: compute_budget_suggestions.
        Assert: each member's total_suggested reflects only their own data.
        """
        # Arrange
        rows = (
            _member_df(10, 1, 1, "CAT1", "Groceries", [100.0] * 6)
            + _member_df(20, 1, 1, "CAT1", "Groceries", [500.0] * 6)
        )
        df = _make_monthly_df(rows)

        # Act
        results = compute_budget_suggestions(df, method="wma", treatment="A",
                                             reference_date="2026-03-01")

        # Assert
        assert len(results) == 2, "Should produce one result per member"
        by_member = {r["idmember"]: r for r in results}
        assert "10" in by_member and "20" in by_member

        total_10 = by_member["10"]["total_suggested"]
        total_20 = by_member["20"]["total_suggested"]

        # Member totals must differ — each sees their own spend
        assert total_10 != total_20, (
            f"total_suggested should differ by member: member10={total_10}, member20={total_20}"
        )
        # Member 10 spends ~100/month, member 20 spends ~500/month
        assert total_10 < total_20, (
            f"Member 10 (low spender) total_suggested={total_10} should be < "
            f"member 20 (high spender) total_suggested={total_20}"
        )


# ---------------------------------------------------------------------------
# TC-T7-2: cross-company idmember collision raises ValueError
# ---------------------------------------------------------------------------

class TestTC_T7_2_CrossCompanyCollision:
    """Same idmember integer appearing with two different idcompany values
    is a security violation (AUTH-2) and must raise ValueError.
    """

    def test_raises_on_cross_company_idmember(self):
        """Arrange: idmember=10, idcompany=1 (6 months) + idmember=10, idcompany=2 (6 months).
        Act: compute_budget_suggestions.
        Assert: raises ValueError with message containing 'Cross-company idmember collision'.
        """
        # Arrange: same idmember, different idcompany
        rows = (
            _member_df(10, 1, 1, "CAT1", "Groceries", [100.0] * 6)  # company=1
            + _member_df(10, 1, 2, "CAT1", "Groceries", [200.0] * 6)  # company=2 ← collision
        )
        df = _make_monthly_df(rows)

        # Act + Assert
        with pytest.raises(ValueError, match="Cross-company idmember collision"):
            compute_budget_suggestions(df, method="wma", treatment="A",
                                       reference_date="2026-03-01")


# ---------------------------------------------------------------------------
# TC-T7-3: pipeline emits structured audit log at batch completion
# ---------------------------------------------------------------------------

class TestTC_T7_3_AuditLog:
    """run_methods.main() must emit a structured audit log at batch completion
    with fields: job_id, model_version, n_members_processed, n_null_idmember,
    started_at, finished_at.
    """

    def _write_input_csv(self, tmp_dir: str) -> str:
        """Write a small monthly-aggregated CSV for run_methods test."""
        rows = (
            _member_df(10, 1, 1, "CAT1", "Groceries", [100.0] * 6)
            + _member_df(20, 1, 1, "CAT1", "Groceries", [200.0] * 6)
        )
        df = pd.DataFrame(rows)
        path = os.path.join(tmp_dir, "test_input.csv")
        df.to_csv(path, index=False)
        return path

    def test_audit_log_emitted_with_required_fields(self):
        """Arrange: minimal 2-member dataset, run main().
        Act: capture structlog events.
        Assert: 'run_methods.audit' event has job_id, model_version,
                n_members_processed, n_null_idmember, started_at, finished_at.
        """
        import structlog.testing

        # Import here (not at top) to avoid import-order issues
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
        sys.path.insert(0, scripts_dir)
        from run_methods import main  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_csv = self._write_input_csv(tmp_dir)
            output_json = os.path.join(tmp_dir, "output.json")

            with structlog.testing.capture_logs() as logs:
                main([
                    "--method", "wma",
                    "--treatment", "A",
                    "--reference-date", "2026-03",
                    "--input", input_csv,
                    "--output", output_json,
                ])

        # Find the audit event
        audit_events = [e for e in logs if e.get("event") == "run_methods.audit"]
        assert len(audit_events) >= 1, (
            f"Expected at least one 'run_methods.audit' event. Got events: "
            f"{[e.get('event') for e in logs]}"
        )
        audit = audit_events[0]

        required_fields = [
            "job_id", "model_version", "n_members_processed",
            "n_null_idmember", "started_at", "finished_at",
        ]
        for field in required_fields:
            assert field in audit, (
                f"Audit log missing field '{field}'. Got: {list(audit.keys())}"
            )
