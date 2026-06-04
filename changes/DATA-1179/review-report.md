# Review Report: DATA-1179

Reviewer: blossom-reviewer (automated)  
Inputs:   `changes/DATA-1179/spec.md`, `changes/DATA-1179/testing-report.md`, `git diff main..HEAD`  
Date:     2026-06-03  
Cycle:    1 of 2

---

## Verdict

**ISSUES FOUND**

Two critical wiring defects were found across the 7-task implementation. All test
contracts from the spec are present and pass (16/16 new tests green, 133 total passing).
TDD commit order is respected for all tasks. The core model logic (`aggregator.py`,
`model.py`) and all authentication/security guards (AUTH-2, cross-company collision)
are correctly implemented. The two criticals are integration/wiring gaps that prevent
the pipeline from operating end-to-end with `idmember` data, not logic errors in
the core model.

---

## TDD Evidence

All 7 tasks show a `test(...)` commit **before** the corresponding `feat(...)` commit
in `git log --oneline main..HEAD`:

| Task | Test commit (RED) | Feat commit (GREEN) | Order |
|------|-------------------|---------------------|-------|
| T1 | `58dba3a test(DATA-1179): add contracts for T1` | `048b6d8 feat(DATA-1179): implement T1` | ✅ |
| T3 | `7fa92d6 test(DATA-1179): add contracts for T3` | `78a6067 feat(DATA-1179): implement T3` | ✅ |
| T4 | `8c5808f test(DATA-1179): add contracts for T4` | `9c59e77 feat(DATA-1179): implement T4` | ✅ |
| T2 | `e6f5887 test(DATA-1179): add contracts for T2` | `d2ec5d2 feat(DATA-1179): implement T2` | ✅ |
| T5 | `0024d9e test(DATA-1179): add contracts for T5` | `300a844 feat(DATA-1179): implement T5` | ✅ |
| T6 | `7a525e2 test(DATA-1179): add contracts for T6` | `c217d3d feat(DATA-1179): implement T6` | ✅ |
| T7 | `431db55 test(DATA-1179): add tests for T7`     | `8bff065 feat(DATA-1179): implement T7` | ✅ |

TDD order is clean for all 7 tasks. ✅

---

## Audit Results

| Audit | Result | Notes |
|---|---|---|
| C1. Branch matches spec | ✅ | `feat/DATA-1179` matches `spec.md` §Branch |
| C2. Files to create — all present | ✅ | 4/4: `generate_golden_set.py`, `test_build_fact_transactions_idmember.py`, `test_prep_idmember.py`, `test_multitenancy.py` |
| C3. Files to modify — all modified | ✅ | 8/8 spec files present in diff |
| C4. Signatures match | ⚠️ | Core signatures correct; 2 minor warnings (see below) |
| C5. Tests present | ✅ | 16/16 spec test contracts present and passing (verified by live run) |
| C6. Test execution evidence | ✅ | `testing-report.md` present; V1 confirmed pass; 16 new tests confirmed green |
| C7. Wiring rule (no orphans) | ❌ | **CRITICAL×2**: `_resolve_idmember` not called in pipeline; `run_smart_budget_prep.py` uses `df_out["idaccount"]` on post-T3 output |
| C8. Feature flag wiring | ✅ N/A | No feature flag in spec |
| C9. Audit trail | ✅ | `run_methods.audit` event logged with all 6 required fields (TC-T7-3 passes) |
| C10. No PII in logs | ✅ | No individual `idmember` values logged; all log fields are counts/aggregates |

---

## Critical Issues

### [C7-1] `_resolve_idmember` is an orphan — not wired into either pipeline path

- **Spec** (`spec.md` T1, lines 14-19):
  > "Agregar columna `idmember` via join dual en ambos modos (`--source s3` y `--source db`)."
  > "EXT: strip `"EXT"` del `idaccount` → buscar en `memberaccount.idaccount` → obtener `memberaccount.idmember`"
  > "OLB (`SUB…`, `INT…`): buscar `fact_transactions.idaccount` en `account.blossomdoughconsolidatedaccountid`…"

- **Code (`scripts/build_fact_transactions.py`)**:
  - `_resolve_idmember` is defined at **line 94** (in-memory S3 path).
  - `_resolve_idmember_db` is defined at **line 174** (DB path).
  - `main()` `--source s3` path (lines 653–677): calls `build_sub_transactions`, `build_loan_transactions`, `build_external_transactions`, `pd.concat`, `save_outputs` — **`_resolve_idmember` is never called**.
  - `build_from_db()` (lines 538–561): executes `SELECT * FROM public.fact_transactions` and returns — **`_resolve_idmember_db` is never called**.
  - `save_outputs()` (line 573): fills any CANONICAL_COLS column not present in the DataFrame with `None`. So `idmember` is populated with a column of `None` values in both pipeline modes — not resolved values.

- **Testing report discrepancy**: The "Wiring" section states "`_resolve_idmember` called in `build_fact_transactions.py` `process_chunk()`". No function named `process_chunk` exists anywhere in `build_fact_transactions.py`. This claim masked the wiring gap.

- **Impact**: `fact_transactions.csv` output from either `--source s3` or `--source db` mode will have `idmember = None` for all rows. All downstream tasks (T3 aggregator, T4 model, T5 run_methods) depend on `idmember` being populated by `build_fact_transactions`.

- **Resolution**: Wire the calls. In `main()` S3 path, after the `pd.concat` at line 671, load `memberaccount` and `account` tables and call `fact = _resolve_idmember(fact, memberaccount, account)`. In `build_from_db()`, after reading from the DB, call `_resolve_idmember_db(conn, fact["idaccount"].tolist())` and map results back. Add a wiring test (TC-T1-4 covers CANONICAL_COLS but not the call chain; add TC-T1-7: `main(source='s3')` produces non-null `idmember` for EXT rows with valid memberaccount data).

  Run `/blossom-workflow:fix` to patch.

---

### [C7-2] `run_smart_budget_prep.py` crashes at runtime with `KeyError: 'idaccount'` when processing idmember data

- **Spec** (`spec.md` T2, line 66–67):
  > "Pass-through `idmember` al output sin modificación" (implies the full pipeline runs successfully)

- **Root cause**: T3 changed `prepare_smart_budget_data()` in `aggregator.py` (lines 176–178) to drop `idaccount` from its output when `idmember` is present:
  ```python
  output_cols = [
      "idclient", "idcompany", "idmember", "idcategory", "defaultcategory",
      "period_yyyymm", "monthly_total",
  ]
  ```
  `idaccount` is intentionally not included. However, `run_smart_budget_prep.py` was not updated to match this new output contract:

  - **Line 182**: `unique_members = df_out["idaccount"].nunique()` → `KeyError: 'idaccount'`
  - **Line 205**: `total_buckets_after = df_out.groupby(["idaccount", "defaultcategory"]).ngroups` → `KeyError: 'idaccount'`

- **Failure mode**: The `try/except` at line 236 catches the `KeyError` and calls `sys.exit(1)`. The pipeline logs `"pipeline_failed"` and exits silently with a non-zero code. No stack trace is surfaced to the caller.

- **Test gap**: T2 tests (`test_TC_T2_1`, `test_TC_T2_2`) only test `validate_columns()` in isolation. No test runs `main()` with an idmember-containing input through the full pipeline, so this crash path is untested.

- **Resolution**: Update `run_smart_budget_prep.py`:
  - Line 182: `unique_members = df_out.get("idmember", df_out.get("idaccount", pd.Series())).nunique()`
    — or simply: `unique_members = df_out["idmember"].nunique() if "idmember" in df_out.columns else df_out["idaccount"].nunique()`
  - Lines 200–205: replace `"idaccount"` with `"idmember"` (or appropriate member-grain key) in the groupby stats.
  - Add a test that runs `main()` end-to-end with a small idmember-containing CSV and asserts exit code 0 / non-empty output.

  Run `/blossom-workflow:fix` to patch.

---

## Warnings

### [W1] Testing report "Wiring" section contains an incorrect claim

- The testing report (line 218) states: "`_resolve_idmember` called in `build_fact_transactions.py` `process_chunk()`".
- No function `process_chunk()` exists in `build_fact_transactions.py`. This claim is fabricated or refers to a planned refactor that was not committed.
- This masked Critical Issue C7-1 during the implementer's self-review. The testing-report "Structural Audit / Wiring" section should be corrected to reflect the actual (unwired) state.

### [W2] T2 and T1 test contracts only cover isolated functions, not the pipeline call chain

- `test_TC_T2_1` / `test_TC_T2_2`: test only `validate_columns()`. No test exercises `main()` with idmember data. → C7-2 crash is undetected.
- `test_TC_T1_1` through `test_TC_T1_6`: test `_resolve_idmember` / `_resolve_idmember_db` in isolation. No test validates the functions are called from `main()`. → C7-1 wiring gap is undetected.
- These are not blocking on their own, but they are the proximate reason the two critical bugs went undetected by the test suite.

### [W3] `_null_suggestion()` output has an extra `reason` field not in spec's JSON contract

- `spec.md` T4 defines exactly 12 required fields for the output JSON: `{ category_id, defaultcategory, idmember, idclient, idcompany, suggested_amount, basis, confidence, display_label, explanation, model_version, total_suggested }`.
- `_null_suggestion()` (`model.py` line 188) returns a dict with 13 keys — it adds `"reason": _NULL_SUGGESTION_REASON`. After Step 10 in `compute_budget_suggestions`, the `reason` field persists in null-suggestion entries.
- `test_TC4_8_json_contract_fields` (`test_model.py` line 428) checks `set(r.keys()) == required_fields` but only for a non-null case — the test correctly passes. A null case would fail the exact-match assertion.
- Not blocking (the undocumented `reason` field is additive), but the null-suggestion JSON schema drifts from the spec contract.

### [W4] T2 implementation uses `OPTIONAL_RECOMMENDED_COLUMNS` instead of adding `idmember` to `REQUIRED_COLUMNS`

- `spec.md` T2, line 64: "Agregar `'idmember'` a `REQUIRED_COLUMNS` con modo warning"
- Code (`run_smart_budget_prep.py` lines 53–56): uses a separate `OPTIONAL_RECOMMENDED_COLUMNS = {"idmember"}` set, not `REQUIRED_COLUMNS`.
- Behavior is functionally equivalent (warning when missing, no fatal error). Not blocking — the observable contract is satisfied. But the implementation departs from the spec's literal instruction.

---

## What Passed

- **Branch & TDD**: `feat/DATA-1179` matches spec; all 7 tasks follow strict RED→GREEN commit order. ✅
- **All 16 spec test contracts present and passing**: verified by live `pytest` run (0 failures). ✅
- **aggregator.py T3 grain change**: `aggregate_monthly` group_keys include `idmember`; `zero_fill` validates idmember→(idclient, idcompany) uniqueness; `apply_gating` AUTH-2 groupby `(idclient, idcompany, idmember, idcategory, defaultcategory)` prevents cross-tenant mixing; `prepare_smart_budget_data` output_cols drops `idaccount`, drops null idmember rows with warning. ✅
- **model.py T4 changes**: `bucket_keys = ["idmember", "idcategory", "defaultcategory"]`; `_null_suggestion` has `idmember`, no `idaccount`; Step 0 pre-collapses multi-account to idmember grain; Step 10 computes `total_suggested` per `(idclient, idcompany, idmember)`; all-null → `0.0` (not None). ✅
- **AUTH-2 security guard (T7)**: `compute_budget_suggestions` raises `ValueError("Cross-company idmember collision detected…")` when same idmember integer appears with multiple `idcompany` values. TC-T7-2 confirms this. ✅
- **Audit trail (T7)**: `run_methods.audit` structlog event with all 6 required fields (`job_id`, `model_version`, `n_members_processed`, `n_null_idmember`, `started_at`, `finished_at`). TC-T7-3 confirms. ✅
- **Parameterized SQL (T1, C8)**: `_resolve_idmember_db` uses `%s` placeholders; TC-T1-6 asserts no literal account_id in query strings. ✅
- **No PII in logs (C10)**: No individual `idmember` values logged in any production code path; all log fields are counts/aggregates. ✅
- **Golden set re-freeze (T6)**: `golden_set.csv` has `idmember`, ≥3 distinct members, 6 distinct periods; TC-T6-4 WMA regression match passes. ✅
- **CANONICAL_COLS (T1)**: `idmember` present after `idcompany` at `build_fact_transactions.py` line 79. ✅
- **run_smart_budget_prep.py validate_columns (T2)**: `OPTIONAL_RECOMMENDED_COLUMNS` and warning path work correctly; `validate_columns()` tested by TC-T2-1 and TC-T2-2. ✅
- **run_methods.py output (T5)**: `compute_budget_suggestions` output contains `idmember` + `total_suggested`; TC-T5-1 passes; `idaccount` absent from output. ✅
- **No hardcoded secrets (C9)**: grep found no secrets in diff. ✅
- **Coverage**: aggregator 88%, model 97%, filters 100% — all above 80% threshold. ✅

---

## Gate Decision

**ISSUES FOUND** — 2 critical issues must be resolved before this branch can proceed to PR.

1. Wire `_resolve_idmember` into `main() --source s3` and `build_from_db()` / `main() --source db`
2. Update `run_smart_budget_prep.py` lines 182 and 205 to use `idmember` instead of `idaccount` on post-T3 `df_out`

Next step: → **`/blossom-workflow:fix`** — address the two critical issues, then re-run `/blossom-workflow:review`.

> **Note**: If this is the second review cycle and the same issues persist, escalate with `/blossom-workflow:spec DATA-1179` — the spec did not explicitly mandate updating the stats block in T2 to account for T3's output contract change, and the wiring section of T1 may need more explicit call-site specification.
