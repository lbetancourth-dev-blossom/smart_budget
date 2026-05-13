# Review Report: DATA-1137

Reviewer: blossom-reviewer (automated)
Inputs:   changes/DATA-1137/spec.md · changes/DATA-1137/testing-report.md · git diff origin/development...HEAD
Date:     2025-05-12

---

## Verdict

**APPROVED**

All 10 compliance audits pass. All additional ticket-specific checks pass. No critical issues found. Five warnings are documented below — all are minor code comments, spec ambiguities, or dead-code artifacts that do not affect functional correctness. The implementation faithfully follows every test contract in the spec. TDD commit ordering is correct.

---

## Audit results

| Audit | Result | Notes |
|---|---|---|
| C1. Branch matches spec | ✅ | Branch `feat/DATA-1137` matches spec.md §Branch; ahead of `origin/development` by 8 commits |
| C2. Files to create present | ✅ | 4/4 — `src/smart_budget/model.py`, `scripts/run_methods.py`, `tests/unit/test_model.py`, `tests/fixtures/golden_set.csv` all present in diff |
| C3. Files to modify modified | ✅ | 1/1 — `requirements.txt` in diff; adds `statsmodels>=0.14.0,<1.0.0` and `pytest-cov>=4.0.0` |
| C4. Signatures match | ✅ | All 7 public functions exist with correct names, parameter lists, return types, and docstrings. One minor EWMA `adjust=False` deviation from vague spec text — resolved by test contract (see W2) |
| C5. Tests present | ✅ | 38/38 — every TC-x.x from spec mapped and confirmed in `tests/unit/test_model.py` |
| C6. Test execution evidence | ✅ | `testing-report.md` covers V1–V5; all V-steps ✅; 38/38 unit tests + 57/57 full suite; coverage 93% on model.py |
| C7. Wiring rule (no orphans) | ✅ | `model.py` imported by `scripts/run_methods.py` (line 38) and by all 38 tests; no orphan exports |
| C8. Feature flag wiring | N/A | No feature flag in this spec |
| C9. Audit trail | N/A | Spec explicitly marks this as read-only/batch — no DB writes, no financial mutations in scope |
| C10. No PII in logs | ✅ | structlog in `run_methods.py` logs only `method`, `treatment`, `reference_date`, `input_path`, `n_suggestions`, `n_null_suggestions` — no raw amounts per member |

---

## Additional ticket-specific checks

| Check | Result | Notes |
|---|---|---|
| JSON contract — non-null keys | ✅ | `model.py` lines 291–310: exactly {category_id, defaultcategory, idaccount, idclient, idcompany, suggested_amount, basis, confidence, display_label, explanation, model_version} — 11 keys, no `reason` |
| JSON contract — null keys | ✅ | `_null_suggestion()` lines 172–185: adds `reason` key with correct literal; `basis=None`, `confidence=None` |
| `explanation` — neutral copy | ✅ | `build_explanation()` lines 136–155: no prescriptive words found. Test `test_explanation_no_prescriptive_words` enforces "deberías", "tienes que", "te conviene", "más que" are absent |
| `EPSILON_DEFAULT` = 0.01 | ✅ | `model.py` line 14: `EPSILON_DEFAULT: float = 0.01` — module-level constant |
| CLAMP — never negative | ✅ | `compute_wma` (line 70), `compute_ewma` (line 86), `compute_holt_winters` (line 104) all use `max(0.0, value)` before rounding |
| REFERENCE_DATE cutoff — inclusive | ✅ | `model.py` line 224: `df[df["_period"] <= ref_period]` — reference month IS included; confirmed by TC-4.7 (reference_date="2025-06-01" → months_analyzed==6 including 2025-06) |
| No secrets / hardcoded credentials | ✅ | grep across all new/modified files found no API keys, passwords, tokens, or credentials |

---

## TDD Evidence Summary

Commit ordering (oldest → newest):

| SHA | Type | Message |
|---|---|---|
| `dd48838` | feat | add statsmodels and pytest-cov to requirements.txt (T0.1 — no test contract required per spec) |
| **`82a94e9`** | **test** ✅ | add tests for T1.1-T2.1 — model.py + CLI |
| `69d9564` | feat | implement T1.1-T1.7 — model.py |
| `e554cda` | feat | implement T2.1 — scripts/run_methods.py |
| **`d8724fa`** | **test** ✅ | add T3.1 golden set test + fix CLI import |
| `311f299` | feat | implement T3.1 — golden set WMA/A/2026-03-01 |
| `e4c7fe4` | feat | fix run_methods.py structlog stderr (followup to T2.1) |
| `e783695` | docs | add testing report and progress log |

**TDD check — T1.1–T1.7:** test commit `82a94e9` precedes feat commit `69d9564` ✅  
**TDD check — T2.1:** test commit `82a94e9` (contains `test_run_methods_importable`) precedes feat commit `e554cda` ✅  
**TDD check — T3.1:** test commit `d8724fa` precedes feat commit `311f299` ✅  

All required TDD orderings from the spec confirmed. Tests and implementation code never combined in the same commit.

---

## Critical issues

None.

---

## Warnings

**[W1] Misleading comment contradicts correct code — `model.py` lines 219–221**
- Code (line 219): `# The current month (containing reference_date) is EXCLUDED; only months strictly before reference_date month.`
- Code (line 224): `df[df["_period"] <= ref_period]` — this is INCLUSIVE (reference month IS included)
- Spec (`spec.md`, line 106): `"Filtrar df a meses <= month(reference_date)"` — inclusive, matches the code
- TC-4.7 confirms: reference_date="2025-06-01" → months_analyzed==6 (includes 2025-06), so the code is correct
- The comment is wrong/inverted. A future maintainer reading only the comment could introduce a regression by changing `<=` to `<`.
- Resolution: update comment to `# Include the reference month itself (<= is intentional per spec §T1.7 step 1)`

**[W2] EWMA `adjust=False` not specified in spec signature text, but codified in test contract**
- Spec text (`spec.md`, line 63): `pandas.ewm(span=span).mean()` — pandas default is `adjust=True`
- Code (`model.py`, line 84): `series.ewm(span=span, adjust=False).mean()`
- Test contract (`test_model.py`, line 108): `series.ewm(span=3, adjust=False).mean()` — test matches code
- The implementation is self-consistent and the docstring on line 76 correctly documents `adjust=False`. The spec text was ambiguous; the test contract resolves it. No action required.

**[W3] `compute_confidence` undefined for data_points < 2 — spec says "low si == 2"**
- Spec (`spec.md`, line 79): `"low si == 2"` — implies `data_points=0` and `data_points=1` are undefined
- Code (`model.py`, line 123): `else: return "low"` — silently returns "low" for 0 or 1
- In practice, external `apply_gating()` prevents buckets with < 3 months from reaching this function; data_points=0 or 1 is unreachable in the full pipeline. No tests cover this edge case.
- Resolution: spec quality gap — no code change needed; optionally add `assert data_points >= 2` guard.

**[W4] Null-suggestion gating case (b) not implemented inside `compute_budget_suggestions` — internal spec inconsistency resolved in favor of test contracts**
- Spec null section (`spec.md`, line 147): "(b) gating no pasó (< 3 meses con datos PRE-treatment)" → should produce null suggestion
- Code: no explicit `if months_with_positive_spend < 3: return _null_suggestion(...)` check inside `compute_budget_suggestions`
- TC-4.5 (`test_model.py`, line 364–370): df with 2 months positive spend → expects non-null result, confidence="low"
- These two spec sections are internally inconsistent. The implementer correctly followed the test contract (TC-4.5), which takes precedence. The gating behavior is delegated to `apply_gating()` in the CLI pipeline before calling `compute_budget_suggestions`. No code change needed; this is a spec quality issue.

**[W5] Dead variable `meta_keys` — `model.py` line 231**
- Code (`model.py`, line 231): `meta_keys = ["idclient", "idcompany"]` — defined but never used; `idclient`/`idcompany` are extracted via `df_bucket["idclient"].iloc[0]` directly
- Coverage report confirms lines 213/216 are uncovered (this variable definition path)
- No spec requirement to have this variable; it's a residual artifact. No functional impact.
- Resolution: remove dead variable to clean up the uncovered branch. Not a blocker.

**[W6] Execution Report table in `spec.md` not updated by implementer**
- `spec.md` §Execution Report: all tasks still show `Status: pending | Commit: —`
- Spec instructions say "Actualizado por el implementer a medida que avanza"
- The `testing-report.md` fully documents task status and commit SHAs instead
- No functional impact; documentation gap only.

---

## What passed

- **Branch** `feat/DATA-1137` correctly tracks `origin/development` as base
- **All 5 new/modified files** in the spec manifest are present in the diff and non-trivially implemented
- **All 7 public signatures** (`apply_treatment`, `compute_wma`, `compute_ewma`, `compute_holt_winters`, `compute_confidence`, `build_explanation`, `compute_budget_suggestions`) exist with correct names, parameter shapes, return types, and docstrings
- **All 38 spec test contracts** implemented by name and behavior, all passing per testing-report.md
- **TDD commit ordering** respected: both required test-before-feat pairs confirmed in git log
- **JSON contract**: non-null (11 keys, no `reason`) and null (12 keys, with `reason`) both match spec exactly
- **EPSILON_DEFAULT = 0.01** defined at module scope ✅
- **CLAMP** (`max(0.0, ...)`) enforced in all three compute functions ✅
- **Reference date cutoff** inclusive (`<=`) matching spec and TC-4.7 ✅
- **No PII** logged: `run_methods.py` logs only aggregate counts and metadata
- **No secrets** in any new file
- **Coverage 93%** on `model.py` — well above the 80% minimum
- **Golden set** committed with correct columns; `test_TC4_golden_set_matches_output` validates exact float match

---

## Gate decision

**APPROVED** — all critical checks passed. Zero critical issues. Ready for the next step.

→ Run `/blossom-workflow:pr` to open the Draft PR.
