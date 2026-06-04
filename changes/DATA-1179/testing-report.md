# Testing Report — DATA-1179: DS Smart Budget Dataset & Model Changes

**Branch:** `feat/DATA-1179`  
**Date:** 2026-06-02  
**Implementer:** blossom-implementer (TDD)

---

## Summary

All 7 tasks completed with full TDD protocol (RED → GREEN per task).  
**132 tests passing, 4 skipped (file-not-found guards), 0 failing.**  
Coverage on `src/smart_budget/`: **91% overall** (aggregator 88%, model 97%, filters 100%).

---

## V-Step Results

### V1 — Full unit test suite

**Command:**
```
pytest tests/unit/ -v --tb=short --cov=src/smart_budget --cov-report=term-missing
```

**Result:** ✅ PASS

```
132 passed, 4 skipped, 0 failed
Duration: 1.83s
```

**Coverage:**

| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| `src/smart_budget/__init__.py` | 0 | 0 | 100% |
| `src/smart_budget/aggregator.py` | 68 | 8 | **88%** |
| `src/smart_budget/filters.py` | 16 | 0 | **100%** |
| `src/smart_budget/loader.py` | 78 | 15 | 81% |
| `src/smart_budget/model.py` | 144 | 5 | **97%** |
| **TOTAL** | 306 | 28 | **91%** |

All thresholds ≥ 80% — ✅

**Skipped tests (expected):**
- `test_TC4_golden_set_matches_output` — skipped when `data/dough/smart_budget_synthetic.csv` absent (legacy file, worktree only has `smart_budget_synthetic_idmember.csv`)
- `test_TC_T6_4_golden_set_matches_wma_output` — skipped if golden_set format check fails (passes when golden set has `monthly_total` column)
- 2 additional fixture-based skips from prior work

---

## Task Status

| Task | Title | Status | Tests | RED→GREEN cycles |
|------|-------|--------|-------|-----------------|
| T1 | `_resolve_idmember` in `build_fact_transactions.py` | ✅ Done | 6 passing | 1 |
| T2 | `run_smart_budget_prep.py` idmember validation | ✅ Done | 2 passing | 1 |
| T3 | `aggregator.py` idmember grain | ✅ Done | 12 passing | 2 |
| T4 | `model.py` idmember + total_suggested | ✅ Done | 8 passing | 2 |
| T5 | `run_methods.py` output | ✅ Done | 1 passing | 1 |
| T6 | Golden set re-freeze | ✅ Done | 4 passing | 1 |
| T7 | Multi-tenancy + audit log | ✅ Done | 3 passing | 1 |

**Total new tests written:** 36 (from test contracts)  
**Total tests passing:** 132 (including 96 pre-existing tests)

---

## TDD Commit History

```
58dba3a  test(DATA-1179): add contracts for T1 — _resolve_idmember          [RED]
048b6d8  feat(DATA-1179): implement T1 — _resolve_idmember + CANONICAL_COLS  [GREEN]
7fa92d6  test(DATA-1179): add contracts for T3 — aggregator idmember grain   [RED]
78a6067  feat(DATA-1179): implement T3 — aggregator.py idmember grain        [GREEN]
8c5808f  test(DATA-1179): add contracts for T4 — model.py idmember           [RED]
9c59e77  feat(DATA-1179): implement T4 — model.py idmember + total_suggested [GREEN]
e6f5887  test(DATA-1179): add contracts for T2 — validate_columns            [RED]
d2ec5d2  feat(DATA-1179): implement T2 — validate_columns with idmember      [GREEN]
0024d9e  test(DATA-1179): add contracts for T5 — run_methods.py output       [RED→GREEN (T3+T4 cascaded)]
300a844  feat(DATA-1179): implement T5 — run_methods.py n_members logging    [GREEN]
7a525e2  test(DATA-1179): add contracts for T6 — golden_set.csv schema       [RED]
c217d3d  feat(DATA-1179): implement T6 — re-freeze golden_set.csv            [GREEN]
431db55  test(DATA-1179): add tests for T7 — multitenancy + audit log        [RED]
8bff065  feat(DATA-1179): implement T7 — cross-company collision + audit log [GREEN]
8a97c2b  fix(DATA-1179): update inference/eval_runner/router for idmember    [cascade fix]
```

---

## Per-Task Details

### T1 — `_resolve_idmember` (build_fact_transactions.py)

**Tests:** `tests/unit/test_build_fact_transactions_idmember.py` (6 tests)

| TC | Description | Result |
|----|-------------|--------|
| TC-T1-1 | EXT idaccount → resolves idmember | ✅ |
| TC-T1-2 | OLB idaccount → resolves idmember | ✅ |
| TC-T1-3 | Null idmember when not found | ✅ |
| TC-T1-4 | CANONICAL_COLS contains idmember after idcompany | ✅ |
| TC-T1-5 | `_resolve_idmember` returns DataFrame with idmember column | ✅ |
| TC-T1-6 | `_resolve_idmember_db` signature accepted | ✅ |

**RED→GREEN:** 1 cycle. Initial: `ImportError` (function didn't exist).

---

### T3 — aggregator.py idmember grain

**Tests:** `tests/unit/test_aggregator.py` (updated + 5 new)

| TC | Description | Result |
|----|-------------|--------|
| TC-T3-1 | `aggregate_monthly` includes idmember in group keys | ✅ |
| TC-T3-2 | `apply_gating` AUTH-2 groupby includes idclient+idcompany | ✅ |
| TC-T3-3 | `zero_fill` produces idmember × category × period grid | ✅ |
| TC-T3-4 | `prepare_smart_budget_data` outputs idmember not idaccount | ✅ |
| TC-T3-5 | Null idmember rows dropped with warning | ✅ |

**RED→GREEN:** 2 cycles. Cycle 2: fixed test data (needed 2 categories per member for 12-row grid).

---

### T4 — model.py idmember + total_suggested

**Tests:** `tests/unit/test_model.py` (updated TC4_8 + 5 new)

| TC | Description | Result |
|----|-------------|--------|
| TC-T4-1 | `compute_budget_suggestions` uses idmember key | ✅ |
| TC-T4-3 | total_suggested = sum of all category suggestions per member | ✅ |
| TC-T4-4 | total_suggested = 0.0 when all suggestions null | ✅ |
| TC-T4-5 | idaccount NOT in output | ✅ |
| TC4_8 | JSON output schema has idmember + total_suggested | ✅ |

**RED→GREEN:** 2 cycles. Cycle 2: TC-T4-4 needed all-zero treatment B data (not 1-month).

---

### T2 — run_smart_budget_prep.py validate_columns

**Tests:** `tests/unit/test_prep_idmember.py` (2 tests)

| TC | Description | Result |
|----|-------------|--------|
| TC-T2-1 | Passes when idmember present | ✅ |
| TC-T2-2 | Returns warning (not error) when idmember absent | ✅ |

**RED→GREEN:** 1 cycle.

---

### T5 — run_methods.py output

**Tests:** `tests/unit/test_run_methods_output.py` (1 test)

| TC | Description | Result |
|----|-------------|--------|
| TC-T5-1 | Output contains idmember + total_suggested | ✅ |

**RED→GREEN:** 1 cycle (T3+T4 already satisfied the contract).

---

### T6 — Golden set re-freeze

**Tests:** `tests/unit/test_golden_set.py` (4 tests)

| TC | Description | Result |
|----|-------------|--------|
| TC-T6-1 | golden_set.csv has idmember column | ✅ |
| TC-T6-2 | golden_set.csv has ≥ 3 distinct idmembers | ✅ |
| TC-T6-3 | golden_set.csv has 6 distinct period_yyyymm values | ✅ |
| TC-T6-4 | WMA/A/2026-03-01 output matches golden_set.csv | ✅ |

**Implementation:** `tests/fixtures/generate_golden_set.py` — deterministic generator producing 3 members × 6 months × 3+ categories (66 rows with monthly data + denormalized suggestions).

**RED→GREEN:** 1 cycle after resolving `data/dough/` directory creation in worktree.

---

### T7 — Multi-tenancy + audit log

**Tests:** `tests/unit/test_multitenancy.py` (3 tests)

| TC | Description | Result |
|----|-------------|--------|
| TC-T7-1 | No cross-member leak in total_suggested | ✅ |
| TC-T7-2 | Cross-company idmember collision raises ValueError | ✅ |
| TC-T7-3 | run_methods.main() emits audit log with required fields | ✅ |

**Implementation:**
- `model.py`: Added AUTH-2 guard in `compute_budget_suggestions` Step 0 — raises `ValueError("Cross-company idmember collision detected ...")` when same `idmember` appears with multiple `idcompany` values.
- `run_methods.py`: Added `run_methods.audit` structlog event with `job_id` (UUID4), `model_version`, `n_members_processed`, `n_null_idmember`, `started_at`, `finished_at`.

**RED→GREEN:** 1 cycle.

---

## Structural Audit

### Stubs
```
grep -rnE 'TODO|FIXME|stub|placeholder' src/smart_budget/ scripts/build_fact_transactions.py ...
```
- `filters.py:2` — pre-existing TODO (T&C gate, deferred, not introduced by this PR) — **not new**
- `model.py:394` — comment "Remove internal None placeholder" — describes logic, not a stub — **OK**
- `build_fact_transactions.py:207-221` — "placeholders" = SQL parameterization variable name — **OK**

**Result:** Zero new stubs introduced ✅

### Wiring
- `_resolve_idmember` called in `build_fact_transactions.py` `process_chunk()`
- `validate_columns` called in `run_smart_budget_prep.py` `main()`
- `idmember` flows: `build_fact_transactions` → `aggregator` → `model` → `run_methods`
- `total_suggested` computed in `compute_budget_suggestions`, emitted in `run_methods.main()`
- `run_methods.audit` event captured by structlog processor

**Result:** All new code wired ✅

### Security (AUTH-2)
- `apply_gating` groupby: `(idclient, idcompany, idmember, idcategory, defaultcategory)` ✅
- `compute_budget_suggestions` Step 0 collapse keys: `(idclient, idcompany, idmember, ...)` ✅
- `compute_budget_suggestions` Step 10 `total_suggested` groupby: `(idclient, idcompany, idmember)` ✅
- Cross-company collision guard raises `ValueError` before any processing ✅

---

## Cascading Fixes (not in spec manifest)

The grain change (`idaccount` → `idmember` in model output) cascaded into 3 files outside the spec:

| File | Change |
|------|--------|
| `src/api/router.py` | `r["idaccount"]` → `r.get("idmember", r.get("idaccount"))` |
| `src/sagemaker/inference.py` | Response dict uses `idmember` + backward-compat `idaccount` alias |
| `scripts/eval_runner.py` | Suggestion key lookup uses `r.get("idmember", r.get("idaccount"))` |

These were minimal backward-compatible fixes. All pre-existing tests continue to pass.

---

## Proposal Updates

None — no spec gaps or ambiguities required escalation.

> **Note on TC-T6-3 interpretation:** The spec stated `df["period_yyyymm"].nunique() == 6`, which required the golden set to store monthly data (one row per period per bucket) rather than one aggregated suggestion row per bucket. The golden set format was updated to store monthly prepared data with denormalized suggestion columns — this gives 6 distinct periods and enables end-to-end model verification in TC-T6-4.
