# Review Report: DATA-1140

Reviewer: blossom-reviewer (automated)
Inputs:   changes/DATA-1140/spec.md, changes/DATA-1140/testing-report.md, changes/DATA-1140/threats.md, branch diff
Date:     2026-05-15

---

## Verdict

**APPROVED**

All 10 compliance audits pass. Every file in the spec manifest is present in the diff and
has been committed on this branch. All 21 test functions (7 T1 + 8 T2 + 6 T5) match their
spec-mandated names exactly. The four SageMaker contract functions are implemented with
correct signatures. All 10 V-steps (V1–V10) are evidenced in the testing-report. TDD
ordering is correct for every task with testable logic (T1, T2, T5). No PII from the C10
watchlist appears in any log statement. There are no critical issues; five minor warnings
are noted below.

---

## Audit results

| Audit | Result | Notes |
|---|---|---|
| C1. Branch matches spec | ✅ | `feat/DATA-1140` — 11 commits ahead of `origin/development` |
| C2. Files to create present | ✅ | 9/9 — all diff-confirmed (includes `test_inference.py`, see W1) |
| C3. Files to modify modified | ✅ | `requirements.txt` — +5 lines (fastapi, uvicorn, httpx, sagemaker) |
| C4. Signatures match | ✅ ⚠️ | All public/private symbols present; 2 minor annotation deviations (W2, W3) |
| C5. Tests present | ✅ | 21/21 — all function names match spec verbatim |
| C6. Test execution evidence | ✅ | V1–V10 all ✅ in testing-report; coverage ≥ 80% on all new modules |
| C7. Wiring rule (no orphans) | ✅ | `load_history` → router.py + inference.py; `router` → main.py; SageMaker fns → test_inference.py |
| C8. Feature flag wiring | N/A | No feature flag in spec |
| C9. Audit trail | N/A | GET-only dev endpoint; no monetary mutations; threats.md: audit log deferred to prod |
| C10. No PII in logs | ✅ | No ssn/password/cvv/pan/cardNumber/accountNumber in any log call; idaccount waiver see W5 |

---

## Critical issues

*None.*

---

## Warnings

- **[W1] `tests/unit/test_inference.py` absent from spec file manifest table**
  - Spec (`spec.md`, lines 15–26): File manifest table lists `test_loader.py` and `test_api.py`
    as CREATE entries, but omits `test_inference.py`.
  - T5 section (`spec.md`, line 729) does specify six named test contracts for
    `tests/unit/test_inference.py` and the file is present in the diff.
  - Assessment: spec manifest omission. The T5 contract list is authoritative; file exists
    and all 6 tests pass. No action required by implementer — this is a planner artifact gap.

- **[W2] `_synthetic_accounts` return type `frozenset` vs `frozenset[str]`**
  - Spec (`spec.md`, line 90): `def _synthetic_accounts(base_dir: Path) -> frozenset[str]:`
  - Code (`src/smart_budget/loader.py`, line 33): `def _synthetic_accounts(base_dir: Path) -> frozenset:`
  - Runtime behavior is identical. The `frozenset[str]` generic subscript requires Python 3.9+;
    `frozenset` is valid in all target versions. No functional impact.

- **[W3] `Optional[float]` / `Optional[str]` instead of `float | None` / `str | None` in `SuggestionResponse`**
  - Spec (`spec.md`, lines 327–330): uses `float | None` and `str | None` union syntax.
  - Code (`src/api/router.py`, lines 37–41): uses `Optional[float]` and `Optional[str]`.
  - Testing-report TDD history documents this as an intentional Python 3.9 compatibility fix
    made in T2 iteration 2. Functionally equivalent. No action required.

- **[W4] `changes/DATA-1137/` and `changes/DATA-1139/` artifact files in diff**
  - `git diff --name-only origin/development..HEAD` lists 13 `changes/DATA-1137/*` and
    `changes/DATA-1139/*` files.
  - These appear because `origin/development` subsequently received archive commits
    (`90e1db3`, `cdb3a2e`) that moved/removed those files after this branch was cut from
    `616ad1e`. The branch has not been rebased since.
  - These are SDD artifact files, not source code; they do not affect DATA-1140 functionality.
  - **Recommendation:** rebase `feat/DATA-1140` onto `origin/development` before opening the
    PR to avoid re-introducing archived artifacts into the base branch.

- **[W5] `idaccount` logged in plain text — AGENTS.md rule, waived for Fase 0**
  - `src/api/router.py`, line ~79: `log = logger.bind(idaccount=idaccount, ...)`
  - AGENTS.md mandates: *"Member IDs en logs: hashear con SHA-256 + `SB_LOG_SALT`."*
  - `threats.md` Section 3 and Approval (2026-05-15, Landneyker Betancourth): hash requirement
    explicitly waived for Fase 0 dev/test; mandatory control downgraded to a TODO comment.
  - Required TODO comment is present in code:
    `# TODO(prod): hashear idaccount con SHA-256 + SB_LOG_SALT antes de promover a alpha/prod`
  - C10 audit literal pattern (`ssn|password|cvv|pan|cardNumber|accountNumber`) does not
    match `idaccount` → C10 passes. This warning is raised for AGENTS.md awareness only.
  - **No action required before merging.** Hash must be implemented before any alpha/prod
    promotion as documented in threats.md.

---

## TDD evidence

| Task | Test commit | Impl commit | Order |
|---|---|---|---|
| T0 (requirements.txt) | — (glue-only; pip-install contract verified in testing-report V1) | `f1e2b53` | ✅ acceptable |
| T1 (loader.py) | `f9e8896` test(DATA-1140): add tests for T1 | `1253267` feat(DATA-1140): T1 | ✅ test before impl |
| T2 (router.py + main.py) | `6a2fedc` test(DATA-1140): add tests for T2 | `0aad856` feat(DATA-1140): T2 | ✅ test before impl |
| T5 (inference.py + notebook) | `4fcd8a0` test(DATA-1140): add tests for T5 | `f916572` feat(DATA-1140): T5 | ✅ test before impl |

---

## What passed

- **Branch name**: `feat/DATA-1140` matches spec exactly; 11 commits ahead of base.
- **All 9 files in manifest** created and diff-confirmed (8 manifest entries + `test_inference.py` implied by T5).
- **`requirements.txt`** modified correctly — `fastapi>=0.100.0`, `uvicorn[standard]>=0.20.0`, `httpx>=0.23.0`, `sagemaker>=2.200.0` all present after `pytest-cov` as specified.
- **All 21 test functions** present with verbatim spec names across 3 test files.
- **`load_history` public signature** matches spec exactly (idaccount, defaultcategory, base_dir, FileNotFoundError raise).
- **`get_suggestion` endpoint** at `GET /smart-budget/suggestion` with correct query params, 404 for unknown account, 422 for malformed period_id, null-200 for insufficient data.
- **Pydantic schemas** `BasisDetail` and `SuggestionResponse` match all 10 spec-mandated fields.
- **SageMaker contract** `model_fn / input_fn / predict_fn / output_fn` all implemented with correct behavior (model_fn returns path, input_fn raises ValueError on bad JSON/content-type, predict_fn handles gating, output_fn returns JSON string).
- **Notebook** has all 3 required keywords: `deploy`, `invoke_endpoint`, `delete_endpoint`.
- **`main.py`** title `"Smart Budget API"` matches V5 verification criterion.
- **V1–V10 all ✅** in testing-report; 105 passed, coverage 89–97% on new modules (all ≥ 80%).
- **No regressions**: pre-existing `test_TC4_golden_set_matches_output` failure documented as pre-branch (requires gitignored production data).
- **C10 PII check**: zero matches for ssn/password/cvv/pan/cardNumber/accountNumber in any logger call.
- **TDD ordering correct** for all 3 tasks with testable logic (T1, T2, T5).

---

## Gate decision

**APPROVED** — all critical checks pass. The feature is ready for `/blossom-workflow:pr`.

Before opening the PR, the dev should address **W4** (rebase onto `origin/development`) to
keep the PR diff clean. Warnings W1–W3 and W5 require no code changes.
