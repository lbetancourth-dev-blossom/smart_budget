# Testing Report — DATA-1139

**Ticket:** DATA-1139 — DS - Extraer datasets de test por fuente (test_internal / test_external)
**Branch:** feat/DATA-1139
**Date:** 2026-05-15
**Implementer:** Blossom Implementer (TDD)

---

## Summary

| Metric | Value |
|--------|-------|
| Tasks completed | 2 / 2 |
| Test contracts written | 9 |
| Tests passing | 9 / 9 |
| Mandatory V-steps | 4 / 4 passed |
| TDD commits | 1 test commit + 1 impl commit |
| Stubs remaining | 0 |
| Proposal updates | None |

---

## TDD Iteration History

### Task 1 — `tests/unit/test_extract_test_datasets.py` (RED)

- **Commit:** `49fd9fd` — `test(extract-test-datasets): add 9 TDD contracts for DATA-1139`
- **Result on commit:** `ModuleNotFoundError: No module named 'extract_test_datasets'` (expected RED)
- **Iterations:** 1 — tests were correctly RED from the first run

### Task 2 — `scripts/extract_test_datasets.py` (GREEN)

- **Commit:** `0c62fd4` — `feat(extract-test-datasets): implement split + atomic write for DATA-1139`
- **RED→GREEN iterations:** 1 — all 9 tests passed on the first run after implementation
- **Lint cycles:** 0 — `ruff check` was clean on first pass

---

## V-Step Results

### V1 — Target unit tests

**Command:** `python3 -m pytest tests/unit/test_extract_test_datasets.py -v`

```
============================= test session starts ==============================
collected 9 items

tests/unit/test_extract_test_datasets.py::test_split_sub_goes_to_internal PASSED           [ 11%]
tests/unit/test_extract_test_datasets.py::test_split_loan_goes_to_internal PASSED           [ 22%]
tests/unit/test_extract_test_datasets.py::test_member_in_both_files_when_has_olb_and_ext PASSED [ 33%]
tests/unit/test_extract_test_datasets.py::test_unknown_prefix_excluded_from_both PASSED     [ 44%]
tests/unit/test_extract_test_datasets.py::test_filter_applied_pending_olb_excluded PASSED   [ 55%]
tests/unit/test_extract_test_datasets.py::test_empty_source_returns_empty_df_not_exception PASSED [ 66%]
tests/unit/test_extract_test_datasets.py::test_write_atomic_creates_file_with_restricted_permissions PASSED [ 77%]
tests/unit/test_extract_test_datasets.py::test_write_atomic_tmp_file_has_restricted_permissions_before_replace PASSED [ 88%]
tests/unit/test_extract_test_datasets.py::test_split_output_uses_only_output_columns PASSED [100%]

9 passed in 0.05s
```

**Result:** ✅ PASS — 9/9

---

### V2 — Ruff lint

**Command:** `python3 -m ruff check scripts/extract_test_datasets.py`

```
All checks passed!
```

**Result:** ✅ PASS — 0 violations

---

### V3 — Module import smoke test

**Command:** `cd scripts && python3 -c "from extract_test_datasets import OUTPUT_COLUMNS, split_by_source; print('OK')"`

```
OK
```

**Result:** ✅ PASS

---

### V4 — Security primitives present

**Command:** `grep -n "os.replace\|chmod\|getpid" scripts/extract_test_datasets.py`

```
97:    - ``chmod 0o600`` is applied to the ``.tmp`` file **before** ``os.replace``
104:    tmp = Path(str(path) + f".{os.getpid()}.tmp")  # SC-2: PID suffix
106:    os.chmod(tmp, 0o600)                             # SC-3: secure .tmp before replace
107:    os.replace(tmp, path)
108:    os.chmod(path, 0o600)                            # double-secure final file
```

**Result:** ✅ PASS — `os.replace`, `chmod`, and `getpid` all present

---

## Full Test Suite

**Command:** `python3 -m pytest tests/ -v --cov=src/smart_budget --cov-report=term-missing`

```
collected 88 items

... 84 passed, 3 skipped, 1 failed (pre-existing)

Name                             Stmts   Miss  Cover   Missing
--------------------------------------------------------------
src/smart_budget/__init__.py         0      0   100%
src/smart_budget/aggregator.py      39      1    97%   43
src/smart_budget/filters.py         15      0   100%
src/smart_budget/model.py          114      4    96%   97, 233, 236, 250
--------------------------------------------------------------
TOTAL                              168      5    97%
```

**Pre-existing failure:** `tests/unit/test_model.py::test_TC4_golden_set_matches_output`
— `FileNotFoundError: data/dough/smart_budget_synthetic.csv` — missing data file, unrelated to
DATA-1139. Confirmed pre-existing by running the test against the baseline before any changes.

**Result:** ✅ All tests attributable to DATA-1139 pass. 0 regressions introduced.

---

## Coverage

- `src/smart_budget/filters.py`: **100%** (our test_filter_applied_pending_olb_excluded + TC-5 exercise
  OLB PENDING exclusion path; existing filter tests cover the rest)
- New `scripts/extract_test_datasets.py` is covered via direct import in unit tests (split/atomic write
  paths). The `main()` CLI path is marked `# pragma: no cover` per standard practice for integration
  entry points.

---

## Structural Audit

- **Stubs:** 0 (`grep TODO\|FIXME\|XXX\|stub\|placeholder` → no matches)
- **Wiring:** `split_by_source` and `write_atomic` both imported and called in test suite;
  `main()` callable via `python scripts/extract_test_datasets.py --help`
- **Security:** SC-1 (`OUTPUT_COLUMNS` only), SC-2 (PID suffix), SC-3 (chmod before replace) — all
  verified by V4 grep and TC-7/TC-8/TC-9

---

## Proposal Updates

None — spec was complete and sufficient. No halts or blockers.
