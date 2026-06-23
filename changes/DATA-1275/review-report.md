# Review Report: DATA-1275

Reviewer: blossom-reviewer (automated)
Inputs:   changes/DATA-1275/spec.md, current branch diff, changes/DATA-1275/testing-report.md
Date:     2026-06-23

## Verdict

**ISSUES FOUND**

The implementation is largely complete and architecturally sound. The Athena loader, router swap, SageMaker inference rewrite, and notebook changes all land correctly. However, V6 (D4 clean break) fails: `idcategory` and `defaultcategory` survive in three MODIFIED files (`src/smart_budget/model.py`, `tests/unit/test_model.py`, `tests/unit/test_multitenancy.py`) and one occurrence in `tests/unit/test_inference.py`. There is also a TDD ordering violation for T3.1 (feat commit precedes its test commit). The SQL file and legacy loader occurrences are in spec-declared UNCHANGED files and are not violations.

---

## Audit results

| Audit | Result | Notes |
|---|---|---|
| C1. Branch matches spec | Warning | Spec says `DATA-1275`; actual branch is `feat/DATA-1275`. Different prefix but same ticket. Noted, not blocked. |
| C2. Files to create present | PASS | `src/smart_budget/athena_loader.py` and `tests/unit/test_athena_loader.py` both exist and are in the diff. |
| C3. Files to modify modified | PASS | All 9 MODIFY paths appear in `git diff --name-only main...HEAD`. |
| C4. Signatures match | PASS | `AthenaQueryError`, `_get_connection()`, `load_history_by_member_athena(idmember, conn, database, table)`, `member_exists_athena(idmember, conn, database, table)`, `SuggestionItem` (with `category_id: str`, `category_name: str`, no `defaultcategory`) all match spec exactly. |
| C5. Tests present | PASS | All named tests confirmed: T1.1 (3), T1.2 (6), T1.3 (3), TC-API-10/11/12, TC-T5.7/T5.8/T5.9, `test_notebook_structure.py` (4 checks). |
| C6. Test execution evidence | PASS | `testing-report.md` covers all V1–V13. V1: 12 passed, V2: 12 passed (incl. TC-API-10/11/12), V3: 147 passed / 4 skipped, V10: 11 passed. All steps marked passing. |
| C7. Wiring rule (no orphans) | PASS | `athena_loader` is imported by `router.py`, `inference.py`, and test files. All public exports are used. |
| C8. Feature flag wiring | N/A | No feature flag specified in spec. |
| C9. Audit trail | N/A | Spec does not mark this as a financial operation. |
| C10. No PII in logs | PASS | `load_history_by_member_athena` logs `idmember`, `rows`, `duration_ms` — not `total_amount`. No PII patterns found in diff. |

---

## TDD commit order audit

The spec mandates: test commit (RED) before feat commit (GREEN), per task.

| Task | Test commit | Feat commit | Order |
|---|---|---|---|
| T1.1/T1.2/T1.3 | `c7e709c test(DATA-1275): add tests for T1.1/T1.2/T1.3` | `eb57664 feat(DATA-1275): implement T1.1/T1.2/T1.3` | PASS |
| T2.1/T2.2 | `2387c24 test(DATA-1275): update tests for T2.1/T2.2` | `5c92b6f feat(DATA-1275): implement T2.1/T2.2` | PASS |
| T3.1 | `81503ec test(DATA-1275): update test_api.py for T3.1/T6.1` | `3e19fdf feat(DATA-1275): implement T3.1` | **VIOLATION — feat precedes test** |
| T5.1 | (no test commit — grep contract only) | `637a1cc feat(DATA-1275): implement T5.1` | Warning — no test commit (spec allows grep contract) |
| T5.2 | `b8c032c test(DATA-1275): update test_inference.py for T5.2` | `0da1629 feat(DATA-1275): implement T5.2` | PASS |
| T5.3 | `7c8e5d6 test(DATA-1275): add test_notebook_structure.py for T5.3` | `b08f256 feat(DATA-1275): implement T5.3` | PASS |

Reading the `git log` from newest to oldest (top = newest):
```
3e19fdf feat(DATA-1275): implement T3.1   ← newer commit (closer to HEAD)
81503ec test(DATA-1275): update test_api.py for T3.1
```
The feat commit `3e19fdf` is above (newer than) the test commit `81503ec`. In git log newest-first ordering this means T3.1 was implemented BEFORE its tests were written. This violates the TDD rule in the spec.

---

## Critical issues

- **[V6 / D4] `idcategory` and `defaultcategory` survive in modified test files**

  The spec (spec.md, line 307) states V6 must return ZERO matches in `src/` and `tests/`. The spec (spec.md, lines 171–176, T2.1/T2.2) requires that existing tests pass with renamed columns. The following files are NOT in the UNCHANGED manifest and contain violations:

  - `tests/unit/test_model.py` — 16 occurrences. The helper `_make_budget_df(idmember, idcategory, defaultcategory, ...)` uses the old names as Python parameter names (lines 246, 267-268, 288-289, 309-310, etc.). Although the function body correctly maps them to `category_id`/`category_name` (lines 253-254), the function signature and all call sites still carry the old column names as identifiers, violating D4.
  - `tests/unit/test_multitenancy.py` — 3 occurrences (line 41: `idcategory: str, defaultcategory: str` as parameter names).
  - `src/smart_budget/model.py` — 1 occurrence (line 217 docstring: `"Pipeline por bucket (idmember × idcategory × defaultcategory)"`).
  - `tests/unit/test_inference.py` — 1 occurrence (line 160: `"defaultcategory": "Groceries"` used as a dict key in `TC-T5.6b`'s `output_fn` fixture). This is a data key, not just a parameter name.

  Spec reference: spec.md line 307 (`grep -r "defaultcategory\|idcategory" src/ tests/` returns ZERO matches). Success criterion line 328: "`defaultcategory` and `idcategory` appear nowhere in `src/` or `tests/`".

  Resolution: rename the helper parameters in `test_model.py` and `test_multitenancy.py`, update the docstring in `model.py`, and remove the stale `defaultcategory` key from the `test_inference.py` fixture. Then run `/blossom-workflow:fix`.

- **[TDD] T3.1 feat commit precedes test commit**

  Spec (spec.md, line 298): "Commit pattern: `test(DATA-1275): tests for T<N>` then `feat(DATA-1275): implement T<N>`. No implementation without a RED test."

  In the branch history, `3e19fdf feat(DATA-1275): implement T3.1` is a newer commit than `81503ec test(DATA-1275): update test_api.py for T3.1/T6.1`. The test was written after the implementation. This is a TDD ordering violation.

  Note: this is a process violation. The tests exist and pass (V2 green), so there is no functional gap. However, the spec is explicit about commit order.

  Resolution: acknowledge in the testing report or re-order via interactive rebase (if the team's process requires strict TDD commit ordering). If the team accepts "tests exist and pass" as sufficient, the planner can revise this rule in the spec.

---

## Warnings

- **[C1] Branch name prefix mismatch** — spec says branch `DATA-1275`; actual branch is `feat/DATA-1275`. Not a blocking issue since the ticket ID is present and the diff is correct.

- **[T5.1 TDD] No test commit for T5.1** — The testing report notes "grep contract, no test file" for T5.1. The spec's test contract for T5.1 is a grep command (`grep '^pyathena' src/sagemaker/requirements.txt`), not a pytest file, which the testing report characterizes correctly. This is acceptable per the spec's intent, but worth noting for future consistency.

- **[V4/V5] Ruff and black not verified** — testing-report.md V4 says "Not installed in venv; no lint issues observed" and V5 says "Not installed in venv; formatting consistent." These are unverified assertions, not actual tool runs. The spec requires zero errors from ruff and black, not "probably fine." This is a gap in evidence quality, not a confirmed failure.

---

## What passed

- All files in the manifest (CREATE and MODIFY) are present and changed in the diff.
- All signatures match spec exactly: `athena_loader.py` exports, `SuggestionItem` schema (D4 clean break at schema level), `router.py` imports.
- `athena_loader.py` is fully wired: imported by `router.py`, `inference.py`, and multiple test files — no orphan exports.
- `requirements.txt` has `pyathena>=3.0,<4` (V8 PASS); `src/sagemaker/requirements.txt` also has `pyathena>=3.0,<4` (V13 PASS).
- `inference.py` is clean of `_DATA_CSV`, `smart_budget_data.csv`, and `csv_name=` (V12 PASS).
- `router.py` references `load_history_by_member_athena` and `member_exists_athena` at least 4 times (V7 PASS).
- All 12 named test contracts for T1.1/T1.2/T1.3 are present in `test_athena_loader.py` and cover the correct behaviors.
- TC-API-10, TC-API-11, TC-API-12 are present and correctly mock `src.api.router.load_history_by_member_athena`.
- TC-T5.7, TC-T5.8, TC-T5.9 are present in `test_inference.py` and mock `smart_budget.athena_loader.*`.
- Notebook structural tests in `test_notebook_structure.py` cover all four V11 assertions.
- TDD ordering correct for T1.1/T1.2/T1.3, T2.1/T2.2, T5.2, T5.3.
- No PII (SSN, CVV, cardNumber, accountNumber, password) found in any log statement in the diff.
- `src/smart_budget/queries/smart_budget_monthly_spend.sql` correctly UNCHANGED per manifest — its `idcategory`/`defaultcategory` SQL references are upstream pipeline columns, not D4 violations.

---

## Gate decision

**ISSUES FOUND** — 2 critical issues block approval:

1. V6/D4 violations in `test_model.py`, `test_multitenancy.py`, `model.py` docstring, and `test_inference.py` fixture.
2. TDD ordering violation: T3.1 feat commit precedes its test commit.

Run `/blossom-workflow:fix` to address the critical issues, then re-run `/blossom-workflow:review`.
