# Review Report: DATA-1140

Reviewer: blossom-reviewer (automated) — cycle 2
Inputs:   changes/DATA-1140/spec.md, changes/DATA-1140/testing-report.md, current branch diff
Date:     2026-05-21
Supersedes: prior review-report.md dated 2026-05-15 (verdict APPROVED — overturned on deeper audit)

---

## Verdict

**ISSUES FOUND**

Nine critical compliance gaps identified between the spec and the current implementation. The
prior APPROVED verdict (2026-05-15) did not account for post-spec in-flight changes that
diverge from spec.md. Key gaps: (1) the SageMaker entry point was created at
src/sagemaker/inference.py instead of the spec-mandated src/api/inference.py; (2)
src/smart_budget/model.py was modified despite being declared UNCHANGED; (3) the
get_suggestion() endpoint signature deviates — spec uses open str params, implementation
uses hardcoded Enums that restrict valid inputs to 11 accounts and 10 periods; (4)
SuggestionResponse gained an undocumented amount_by_month field; (5) two of the eight T2
test contracts are missing or test the wrong scenario; (6) all SHA hashes in the testing
report's TDD table are fabricated and absent from git log; (7) a TODO comment remains in
production code. TDD commit ordering (test-before-implementation) is correct in the actual
git history.

---

## Audit Results

| Audit | Result | Notes |
|---|---|---|
| C1. Branch matches spec | ✅ | feat/DATA-1140; 40+ commits ahead of main |
| C2. Files to create present | ❌ | src/api/inference.py not created; found at src/sagemaker/inference.py. Extra unspecced: src/sagemaker/__init__.py, src/sagemaker/requirements.txt |
| C3. Files to modify modified | ❌ | src/smart_budget/model.py spec-marked UNCHANGED but modified by commit 3893a4c |
| C4. Signatures match | ❌ | get_suggestion() params: spec str → impl IdAccount/Category/PeriodId Enums; SuggestionResponse adds undocumented amount_by_month; _PERIOD_RE regex absent |
| C5. Tests present | ❌ | 6/8 T2 contracts by name; test_get_suggestion_invalid_period_id_returns_422 replaced by different-scenario test; test_get_suggestion_period_id_not_in_historical_window absent. T1 (7/7) and T5 (6/6) ✅ |
| C6. Test execution evidence | ❌ | TDD table SHAs (f9e8896, 1253267, 6a2fedc, 0aad856, 4fcd8a0, f916572, 179c4a9) absent from git log. V9 references src.api.inference but module is at src.sagemaker.inference |
| C7. Wiring rule (no orphans) | ✅ | load_history → router.py + inference.py; router → main.py; SageMaker fns → test_inference.py |
| C8. Feature flag wiring | N/A | No feature flag in spec |
| C9. Audit trail | N/A | GET-only dev endpoint; no monetary mutations |
| C10. No PII in logs / No TODOs | ❌ | src/api/router.py:129 — TODO(prod): hashear idaccount... in production code |

---

## TDD Evidence

Actual commit ordering verified from `git log --oneline --reverse main..HEAD`:

| Task | Test commit (actual) | Impl commit (actual) | Order |
|---|---|---|---|
| T1 (loader.py) | ab2e901 test(DATA-1140): add tests for T1 | 3d3eabe feat(DATA-1140): T1 — implement unified data loader | ✅ test BEFORE impl |
| T2 (router.py + main.py) | d891eba test(DATA-1140): add tests for T2 | 1005bcc feat(DATA-1140): T2 — implement FastAPI endpoint | ✅ test BEFORE impl |
| T5 (inference.py) | 1733d98 test(DATA-1140): add tests for T5 | 314ebd0 feat(DATA-1140): T5 — implement SageMaker inference.py | ✅ test BEFORE impl |

TDD order is correct in the actual git history. However, the testing-report's TDD table
(lines 29-32) cites SHAs f9e8896, 1253267, 6a2fedc, 0aad856, 4fcd8a0, f916572, 179c4a9
— none of which exist in the repository — making that portion of the testing evidence
non-verifiable (C6 violation).

---

## Critical Issues

- **[C2] SageMaker entry point created at wrong path**
  - Spec (spec.md, file manifest, line 17): `src/api/inference.py` — CREATE
  - Code: `src/api/inference.py` does not exist; `src/sagemaker/inference.py` was created instead
  - Impact: spec V9 step (`from src.api.inference import model_fn`) would fail; testing-report V9
    evidence is stale/incorrect as a result
  - Resolution: move `src/sagemaker/inference.py` → `src/api/inference.py` and update all imports,
    OR revise the spec file manifest and V9 step to reflect the `src/sagemaker/` separation.
    Run `/blossom-workflow:fix` if code path is correct; run `/blossom-workflow:plan DATA-1140`
    if spec needs to change.

- **[C3] `src/smart_budget/model.py` modified despite UNCHANGED declaration**
  - Spec (spec.md, file manifest, line 23): `src/smart_budget/model.py` — UNCHANGED
  - Code: commit `3893a4c` ("lazy import statsmodels") modifies model.py by moving
    `from statsmodels.tsa.holtwinters import ExponentialSmoothing` inside `compute_holt_winters()`
    and updates the test_model.py patch target
  - Resolution: update spec file manifest to mark model.py as MODIFY with the lazy-import change
    documented, then re-review.

- **[C4] `get_suggestion()` signature deviates — Enum restriction replaces open str params**
  - Spec (spec.md, T2 section, lines 349-353): `idaccount: str`, `defaultcategory: str`,
    `period_id: str` with `_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")` validation
  - Code (src/api/router.py, lines 26-67, 109-113): `idaccount: IdAccount` (11 hardcoded values),
    `defaultcategory: Category` (15 values), `period_id: PeriodId` (10 hardcoded months); no regex
  - Impact: any idaccount outside the 11-value enum returns 422 instead of 404; any period_id
    outside 10 hardcoded months returns 422 instead of being processed
  - Resolution: align implementation with spec (open strings + regex), or revise spec to declare
    the Enum approach and update test contracts accordingly.

- **[C4] `SuggestionResponse` schema adds undocumented `amount_by_month` field**
  - Spec (spec.md, T2 section, lines 322-332): SuggestionResponse has 10 fields; no amount_by_month
  - Code (src/api/router.py, line 92): `amount_by_month: Optional[dict[str, Optional[float]]]` added
  - Same field appears in src/sagemaker/inference.py response dict
  - Resolution: add amount_by_month to the spec schema, or remove from both router.py and inference.py.

- **[C5] T2 test contract `test_get_suggestion_invalid_period_id_returns_422` not implemented**
  - Spec (spec.md, T2 contracts, lines 514-517): test_get_suggestion_invalid_period_id_returns_422;
    input period_id=2026/05; expected HTTP 422
  - Code (tests/unit/test_api.py, line 192): sixth T2 test is
    test_get_suggestion_invalid_category_returns_422 — tests invalid category, a different scenario
  - Resolution: add `test_get_suggestion_invalid_period_id_returns_422` covering period_id=2026/05.

- **[C5] T2 test contract `test_get_suggestion_period_id_not_in_historical_window` absent**
  - Spec (spec.md, T2 contracts, lines 522-525): test_get_suggestion_period_id_not_in_historical_window;
    input period_id=2030-01 (far future); expected HTTP 200 null response
  - Code: no test by this name or equivalent scenario in tests/unit/test_api.py
  - Resolution: add the missing test.

- **[C6] Testing report TDD table SHA hashes are fabricated**
  - Testing report (testing-report.md, lines 29-32): cites SHAs f9e8896 (T1 RED), 1253267
    (T1 GREEN), 6a2fedc (T2 RED), 0aad856 (T2 GREEN), 4fcd8a0 (T5 RED), f916572 (T5 GREEN),
    179c4a9 (refactor)
  - git log main..HEAD contains none of these; actual SHAs are ab2e901, 3d3eabe, d891eba,
    1005bcc, 1733d98, 314ebd0, 160562c
  - Resolution: update testing-report TDD table with correct SHA hashes.

- **[C6] Testing report V9 evidence references wrong module path**
  - Testing report (testing-report.md, line 185): `from src.api.inference import model_fn, ...`
  - Actual module: src.sagemaker.inference — src/api/inference.py does not exist
  - Resolution: update V9 evidence path (or fix file path — see C2 above).

- **[C10] TODO comment in production code**
  - Code (src/api/router.py, line 129):
    `# TODO(prod): hashear idaccount con SHA-256 + SB_LOG_SALT antes de promover a alpha/prod`
  - Spec does not declare this as an accepted deferred item; per compliance rules no TODO/FIXME
    may remain in production code on a merge-ready branch
  - Resolution: implement the idaccount hashing now, or move the intent to a separate ticket and
    remove the comment.

---

## Warnings

- **[W1] `tests/unit/test_inference.py` absent from spec file manifest table**
  - Spec manifest (lines 15-26) lists test_loader.py and test_api.py but omits test_inference.py
  - T5 contracts section (spec.md, line 733) explicitly references `file: tests/unit/test_inference.py`
  - Assessment: spec manifest omission (planner artifact gap), not an implementer error.

- **[W2] Undocumented files: `src/sagemaker/__init__.py` and `src/sagemaker/requirements.txt`**
  - Both created on this branch; neither appears in the spec file manifest
  - src/sagemaker/requirements.txt pins numpy==1.23.5, pandas==1.5.3, structlog>=21.0.0 to avoid
    ABI conflicts — a motivated in-flight improvement
  - If the src/sagemaker/ separation is accepted (C2 resolution), update the spec manifest.

- **[W3] T2 test #1 name mismatch**
  - Spec: test_get_suggestion_synthetic_account_returns_200
  - Actual (tests/unit/test_api.py, line 56): test_get_suggestion_happy_path_returns_200
  - Same scenario covered; name deviation is minor.

---

## What Passed

- **TDD ordering correct** for all three tasks (T1, T2, T5) — test commits precede impl commits ✅
- **All 7 T1 test contracts** present with exact spec names in tests/unit/test_loader.py ✅
- **All 6 T5 test contracts** present with exact spec names in tests/unit/test_inference.py ✅
- **`load_history` public signature** matches spec exactly (params, return type, FileNotFoundError) ✅
- **4 SageMaker function signatures** (model_fn, input_fn, predict_fn, output_fn) match spec ✅
- **src/api/router.py, src/main.py, src/api/__init__.py, src/smart_budget/loader.py** created ✅
- **Notebook** created with deploy, invoke_endpoint, delete_endpoint cells confirmed ✅
- **requirements.txt** modified with fastapi, uvicorn, httpx, sagemaker entries ✅
- **base_dir = Path(model) / "data"** correctly resolves CSVs inside model.tar.gz ✅
- **No hardcoded secrets or credentials** found in any new file ✅
- **No PII terms** (ssn/password/cvv/pan/cardNumber/accountNumber) in log statements ✅
- **Wiring complete**: all created modules imported and exercised; no orphan exports ✅
- **Pre-existing failure** (test_TC4_golden_set_matches_output) confirmed pre-branch; no regressions ✅
- **Coverage ≥ 80%** on all new modules per testing report ✅

---

## Gate Decision

**ISSUES FOUND** — 9 critical issues must be resolved before this branch can proceed to PR.

→ Run `/blossom-workflow:fix` to address:
1. Resolve src/api/inference.py vs src/sagemaker/inference.py path divergence
2. Update spec to mark model.py as MODIFY (or revert the lazy-import change to a separate ticket)
3. Align get_suggestion() signature — open string params + regex, or update spec to declare Enum approach
4. Resolve amount_by_month in SuggestionResponse — add to spec or remove from code
5. Add test_get_suggestion_invalid_period_id_returns_422
6. Add test_get_suggestion_period_id_not_in_historical_window
7. Correct testing-report TDD SHA hashes to match actual git commits
8. Correct testing-report V9 evidence path
9. Remove TODO comment from src/api/router.py:129
