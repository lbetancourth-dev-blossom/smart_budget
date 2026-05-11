# Testing Report — DATA-1136

**Ticket:** DATA-1136 — DS - Ajuste y validación de datos (Smart Budget Fase 0 — data preparation layer)
**Branch:** `feat/DATA-1136`
**Date:** 2026-05-11
**TDD Mode:** feature

---

## Summary

| Metric | Value |
|--------|-------|
| Tasks completed | 5/5 (T1, T2, T3, T4, T5) |
| Tests written | 18 (from spec test contracts) |
| Tests passing | 18/18 |
| Tests failing | 0 |
| Verification steps | V1–V7 all ✅ |
| Structural audit | Clean — 0 stubs, all wired |
| TDD commits | 3 test commits + 4 impl commits |

---

## V-Step Results

### V1 — `pytest tests/unit/test_filters.py -v`
✅ **PASSED** — 9/9 tests pass

```
tests/unit/test_filters.py::test_filter_removes_soft_deleted PASSED
tests/unit/test_filters.py::test_filter_removes_income_transactions PASSED
tests/unit/test_filters.py::test_filter_removes_invalid_categories[UNCATEGORIZED] PASSED
tests/unit/test_filters.py::test_filter_removes_invalid_categories[None] PASSED
tests/unit/test_filters.py::test_filter_removes_invalid_categories[INCOME] PASSED
tests/unit/test_filters.py::test_filter_removes_olb_pending PASSED
tests/unit/test_filters.py::test_filter_external_only_posted PASSED
tests/unit/test_filters.py::test_filter_combined_rules PASSED
tests/unit/test_filters.py::test_filter_empty_dataframe PASSED
9 passed in 0.02s
```

### V2 — `pytest tests/unit/test_aggregator.py -v`
✅ **PASSED** — 8/8 tests pass

```
tests/unit/test_aggregator.py::test_aggregate_monthly_sum PASSED
tests/unit/test_aggregator.py::test_aggregate_monthly_clamp_negative PASSED
tests/unit/test_aggregator.py::test_zero_fill_inserts_missing_months PASSED
tests/unit/test_aggregator.py::test_apply_p90_cap PASSED
tests/unit/test_aggregator.py::test_apply_gating_excludes_low_data_buckets PASSED
tests/unit/test_aggregator.py::test_apply_gating_zero_months_dont_count PASSED
tests/unit/test_aggregator.py::test_prepare_smart_budget_data_end_to_end PASSED
tests/unit/test_aggregator.py::test_prepare_idempotent PASSED
8 passed in 0.04s
```

### V3 — `pytest tests/ -v --tb=short`
✅ **PASSED** — 18/18 tests pass

```
18 passed in 0.06s
```

### V4 — CLI on test fixture
✅ **PASSED** — No exception, generates output CSV

```
2026-05-11T21:18:02.042584Z job_start   input_path=tests/fixtures/fact_transactions_test.csv min_months=3
2026-05-11T21:18:02.044603Z filter_complete   rows_after_filter=10 rows_original=17 rows_removed_pct=41.18
2026-05-11T21:18:02.050105Z aggregation_complete   periods_range=2025-01..2025-03 unique_categories=1 unique_members=1
2026-05-11T21:18:02.050274Z p90_stats   p90_value=45.0 rows_capped=2
2026-05-11T21:18:02.053640Z gating_complete   buckets_removed=1 rows_in_output=3
2026-05-11T21:18:02.054663Z job_done   output_rows=3 output_path=/tmp/sb_test_output.csv
```

### V5 — Output column validation
✅ **PASSED** — All required columns present, `monthly_total >= 0` for all rows

```
V5 PASS — columns and constraints OK
  idclient idcompany idmember defaultcategory period_yyyymm  monthly_total  capped
0     C001     CO001     M001       GROCERIES       2025-01           50.0   False
1     C001     CO001     M001       GROCERIES       2025-02           75.0    True
2     C001     CO001     M001       GROCERIES       2025-03           75.0    True
```

### V6 — TDD commit order
✅ **PASSED** — Every `test(...)` commit precedes its `feat(...)` commit

```
1edc1f7 feat(smart_budget): implement DATA-1136 T5 — CLI
a174e09 feat(smart_budget): implement DATA-1136 T3 — aggregator pipeline
4eb5fce test(smart_budget): add tests for DATA-1136 T3 — aggregator pipeline (TC-3.1–TC-3.8)
96841da feat(smart_budget): implement DATA-1136 T2 — filter_transactions + fixture
055a994 test(smart_budget): add tests for DATA-1136 T2 — filter_transactions (TC-2.1–TC-2.7)
5c0f579 feat(smart_budget): implement DATA-1136 T1 — scaffold src/smart_budget/ module
f267883 test(smart_budget): add tests for DATA-1136 T1 — module importable (TC-1.1)
```

### V7 — No PII in fixtures
✅ **PASSED** — `grep -i "john\|smith\|jane\|doe\|real@\|123-45"` returned empty

---

## Task Status

| Task | Description | Tests | Status | Iterations |
|------|-------------|-------|--------|------------|
| T1 | Scaffold `src/smart_budget/` | TC-1.1 (1 test) | ✅ DONE | 1 RED→GREEN |
| T2 | `filter_transactions()` — 5 filtering rules | TC-2.1–TC-2.7 (9 tests incl. parametrize) | ✅ DONE | 1 RED→GREEN |
| T3 | `aggregator.py` — full pipeline | TC-3.1–TC-3.8 (8 tests) | ✅ DONE | 2 RED→GREEN (TC-3.4 P90 interpolation fix) |
| T4 | Synthetic fixture CSV | Covered by TC-2.6 and TC-3.7 | ✅ DONE | — (no separate tests) |
| T5 | CLI `run_smart_budget_prep.py` | glue-only (no unit tests — V4/V5 integration) | ✅ DONE | — |

---

## TDD Iteration History

### T1 — Scaffold
- **Iteration 1 (RED):** `test_module_importable` → `ImportError: cannot import name 'filters' from 'smart_budget'`
- **Iteration 1 (GREEN):** Created `src/__init__.py`, `src/smart_budget/__init__.py`, stub `filters.py`, stub `aggregator.py`
- **Result:** 1/1 ✅

### T2 — filter_transactions()
- **Iteration 1 (RED):** 9 tests fail — `TypeError: object of type 'NoneType' has no len()` (stub returns None) + `FileNotFoundError` (fixture missing)
- **Iteration 1 (GREEN):** Implemented `filter_transactions()` with 5 filter rules + created `tests/fixtures/fact_transactions_test.csv`
- **Result:** 9/9 ✅

### T3 — aggregator pipeline
- **Iteration 1 (RED):** `ImportError: cannot import name 'aggregate_monthly'` (functions not yet implemented)
- **Iteration 1 (GREEN):** Implemented all 5 functions — 7/8 pass, TC-3.4 fails: `assert 90.10000000000001 <= 90.0`
  - Root cause: pandas `quantile(0.90)` uses linear interpolation → P90 of [1..100] = 90.1 not 90.0
  - Test contract requires P90 = 90 and all rows at P90 marked capped=True
- **Iteration 2 (GREEN):** Fixed `apply_p90_cap` to use `interpolation='lower'` and `capped = (monthly_total >= p90)` after clipping
- **Result:** 8/8 ✅

### T4 — Fixture
- No separate test iterations. Fixture designed to satisfy:
  - TC-2.6: exactly 5 valid IDs `{SUB_VALID_1, SUB_VALID_2, LOAN_VALID_1, MANT_POSTED_1, MANT_POSTED_2}` pass all 5 filters
  - TC-3.7: M001-GROCERIES has 3 months of data (passes gating), M001-DINING has 2 months (excluded)
  - TC-3.7 P90 assertion: fixture values designed so top two monthly totals are equal (both 75.0) → P90 = max → no floating point drift

### T5 — CLI (glue-only)
- No unit tests written (T5 orchestrates already-tested functions)
- CLI verified via V4 (successful run) and V5 (output column/constraint check)

---

## Coverage

| Module | Tests | Note |
|--------|-------|------|
| `src/smart_budget/filters.py` | 9 unit tests (TC-2.1–TC-2.7) | All 5 filter rules exercised individually and combined |
| `src/smart_budget/aggregator.py` | 8 unit tests (TC-3.1–TC-3.8) | All 5 pipeline functions tested; idempotency verified |
| `scripts/run_smart_budget_prep.py` | Integration (V4/V5) | Glue-only; no unit tests per blossom-testing-standard |

---

## Structural Audit

- **Stubs:** 0 (one `TODO(prod)` comment is intentional — spec-required T&C gate placeholder)
- **Wiring:** `filter_transactions` and `prepare_smart_budget_data` both imported and called in CLI
- **All new files in manifest:** imported or called
- **Atomic write:** `output.tmp` → `os.replace()` ✅
- **File permissions:** `os.chmod(output_path, 0o600)` ✅
- **Input schema validation:** `assert required_columns ⊆ df.columns` ✅
- **idmember uniqueness in zero_fill:** raises `ValueError` with count (no raw IDs) ✅
- **Sanitized error logging:** global try/except with `error_type + hint` only ✅

---

## Proposal Updates

None — spec was sufficient for all tasks. The one non-trivial interpretation resolved:
- TC-3.4 P90 semantics: `interpolation='lower'` + `capped = monthly_total >= p90` to satisfy the test contract as written (test comment says "P90 = 90" for [1..100]).

---

## Commit Log (last 15)

```
1edc1f7 feat(smart_budget): implement DATA-1136 T5 — run_smart_budget_prep.py CLI (structlog, atomic write, error handling)
a174e09 feat(smart_budget): implement DATA-1136 T3 — aggregator pipeline (aggregate_monthly, zero_fill, apply_p90_cap, apply_gating, prepare_smart_budget_data)
4eb5fce test(smart_budget): add tests for DATA-1136 T3 — aggregator pipeline (TC-3.1–TC-3.8)
96841da feat(smart_budget): implement DATA-1136 T2 — filter_transactions (5 filtering rules) + fixture
055a994 test(smart_budget): add tests for DATA-1136 T2 — filter_transactions (TC-2.1–TC-2.7)
5c0f579 feat(smart_budget): implement DATA-1136 T1 — scaffold src/smart_budget/ module
f267883 test(smart_budget): add tests for DATA-1136 T1 — module importable (TC-1.1)
99c84b6 DATA-1136: agregar plan, spec y threats para data preparation layer
dde7b0a DATA-1136: data preparation and validation for Smart Budget
```
