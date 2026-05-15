# Preflight Report: DATA-1137

**Reviewer:** blossom-reviewer (automated preflight — step 8.5)
**Date:** 2026-05-12
**Spec:** `changes/DATA-1137/spec.md`
**Plan:** `changes/DATA-1137/plan.md`

---

## Verdict

### ❌ BLOCKED

One critical blocker found: the default `--input` path referenced throughout the spec
(`data/dough/test/query/smart_budget_synthetic.csv`) does not exist in the repository.
The actual file lives at `data/dough/smart_budget_synthetic.csv`. This would cause T3.1
to fail on its very first step and all three mandatory verification CLI commands to fail
at runtime. The spec must be corrected before handing off to the implementer.

Four additional warnings are recorded below — none are blockers on their own, but two
(pytest-cov missing from requirements, ambiguous tool choice in T2.1) should be resolved
before execution to avoid implementation ambiguity.

---

## Check results

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | File manifest — unique paths + clear Action | ✅ PASS | 8 entries, all unique, all have CREATE/MODIFY/UNCHANGED |
| 2 | Function signatures complete (no TBD / "if needed") | ✅ PASS | All 6 signatures fully typed with return types, params, and raise conditions |
| 3 | Test contracts concrete (no vague assertions) | ⚠️ WARN | 3 tests use `float >= 0` only; see W-2 |
| 4 | No forbidden words | ✅ PASS | No "if needed", "if applicable", "prefer", "may be", "possibly", "maybe", "consider", "TBD" found |
| 5 | Mandatory verification has runnable commands | ❌ BLOCKED | Commands reference non-existent input path — see BLOCKER below |
| 6 | At least 1 task exists | ✅ PASS | 10 tasks: T0.1, T1.1–T1.7, T2.1, T3.1 |

---

## 🔴 Critical blockers

### BLOCKER-1 — Default input path does not exist

**Location:** `spec.md` lines 226, 246, 273–275; T3.1 step 1

**Evidence:**

The spec defines the CLI's `--input` default and T3.1's source file as:
```
data/dough/test/query/smart_budget_synthetic.csv
```

The directory `data/dough/test/query/` does not exist. The actual file is at:
```
data/dough/smart_budget_synthetic.csv
```

**Impact — three spec locations break:**

1. `spec.md` line 226 — `scripts/run_methods.py` argparse default:
   ```
   --input (default="data/dough/test/query/smart_budget_synthetic.csv")
   ```
   → CLI will crash with `FileNotFoundError` when run without `--input` override.

2. `spec.md` line 246 — T3.1 step 1:
   > "Verificar que `data/dough/test/query/smart_budget_synthetic.csv` existe."
   → Verification will fail immediately.

3. `spec.md` lines 273–275 — Mandatory verification commands all omit `--input`,
   relying on the broken default:
   ```bash
   python scripts/run_methods.py --method wma --treatment A --reference-date 2026-03-01 | python -m json.tool
   python scripts/run_methods.py --method ewma --treatment B --reference-date 2026-03-01 | python -m json.tool
   python scripts/run_methods.py --method holt_winters --treatment A --reference-date 2026-03-01 | python -m json.tool
   ```

**Resolution:** Update the spec to use the correct path `data/dough/smart_budget_synthetic.csv`
in all three locations (T2.1 argparse default, T3.1 step 1, and all mandatory verification
commands). Run `/blossom-workflow:plan DATA-1137` to revise the spec, then re-run preflight.

---

## ⚠️ Warnings

### W-1 — `pytest-cov` not declared in requirements.txt, not in T0.1

**Location:** `spec.md` line 272 (mandatory verification) and `requirements.txt` (current)

The mandatory verification includes:
```bash
python -m pytest tests/ -v --cov=smart_budget --cov-report=term-missing
```
This requires `pytest-cov`. Current `requirements.txt` has `pandas`, `pytest>=7.0.0`, and
`structlog>=21.0.0` — no `pytest-cov`. T0.1 only specifies adding `statsmodels>=0.14.0`.

**Risk:** Implementer finishes T0.1, then hits `no module named pytest_cov` at V2.

**Recommended fix:** Add `pytest-cov>=4.0.0` to T0.1's requirements change, or add it
explicitly as a separate line in the manifest's MODIFY for `requirements.txt`.

---

### W-2 — Three Holt-Winters test contracts assert `float >= 0` only

**Location:** `spec.md` lines 191, 193, 218

Affected tests:
- `test_compute_holt_winters_6_months` — Assert: `float >= 0`
- `test_compute_holt_winters_clamps_negative` — Assert: `float >= 0.0`
- `test_TC4_6_holt_winters_returns_float` — Assert: `suggested_amount` is `float >= 0.0`

These assertions verify type and non-negativity but not value correctness. A no-op
implementation returning `0.0` would pass all three. This is partially acceptable for
a non-deterministic statistical function, but `test_compute_holt_winters_clamps_negative`
in particular (input `[100, 50, 1]`) is testing a specific clamp behavior and should
assert that the returned value equals the raw ExponentialSmoothing forecast clamped to 0.0
(i.e., the raw forecast should be negative with this input — assert `result == 0.0` exactly
rather than `result >= 0.0`).

**Impact:** Low — these tests will not catch a broken HW implementation that returns
a constant positive number.

---

### W-3 — T2.1 test contract has unresolved tool choice ("importlib o runpy")

**Location:** `spec.md` line 238

```
*(No usar subprocess en tests — marcar como skip si el test env no tiene el script en PATH;
usar `importlib` o `runpy` en su lugar.)*
```

Two issues:
1. **Unresolved "or":** `importlib` vs `runpy` — the implementer must choose. These have
   different APIs and different failure modes. Pick one (recommend `runpy.run_path`).
2. **Conditional skip:** "marcar como skip si el test env no tiene el script en PATH" —
   the condition "script in PATH" is never defined. `scripts/run_methods.py` is a file path,
   not a PATH-executable. The skip logic will likely be confused or omitted.

**Impact:** Medium — the `test_run_methods_help_exits_0` test may be skipped unconditionally
or use the wrong invocation pattern, leaving the CLI untested.

**Recommended fix:** Replace the parenthetical with a concrete implementation directive:
> "Use `runpy.run_path('scripts/run_methods.py', run_name='__main__')` with a mocked
> `sys.argv = ['run_methods.py', '--help']`. Expect `SystemExit(0)`."

---

### W-4 — TC-4.4 test contract embeds inline design deliberation

**Location:** `spec.md` lines 214 (full paragraph)

The `test_TC4_4_treatment_B_all_zeros_returns_null` contract contains a multi-sentence
inline reasoning block ("Arrange: df con 3 meses [0,0,0]... espera, gating requiere...
→ Redefinir:...") that restates design decisions rather than giving a clean test arrange/act/assert.
While the final Assert is concrete, the setup instruction requires the implementer to parse
through the deliberation to extract the actual fixture.

**Impact:** Low — the test is ultimately described, but the inline reasoning increases
the chance of misinterpretation.

**Recommended fix (optional for this ticket):** Collapse the TC-4.4 setup to just:
> "Arrange: construct df directly with 3 rows, `monthly_total = [0, 0, 0]`, for one
> bucket. Act: `compute_budget_suggestions(df, 'wma', 'B', '2026-03-01')`. Assert:
> `suggested_amount is None`, `reason == '...'`, `display_label == '...'`."

---

## ✅ What passed

- **File manifest (Check 1):** All 8 entries are uniquely identified with clear Actions.
  UNCHANGED files (`aggregator.py`, `filters.py`, `conftest.py`) all physically exist in
  the repo at the specified paths. The `tests/unit/` and `tests/fixtures/` directories
  already exist.
- **Function signatures (Check 2):** All 6 signatures in `spec.md` are fully specified —
  typed parameters, return types, raise conditions, and docstring behavior contracts.
  No "TBD", no "if needed", no optional-feeling parameters left unresolved.
- **Forbidden words (Check 4):** Zero occurrences of "if needed", "if applicable",
  "prefer", "may be", "possibly", "maybe", "consider", or "TBD" in the spec.
- **`_load_fixture()` exists:** `tests/conftest.py` line 8 exposes `_load_fixture()` as
  referenced in T3.1's golden set test contract.
- **`structlog` in requirements:** `structlog>=21.0.0` is already present — the CLI
  logging requirement (lines 235–236) is satisfiable without additional deps.
- **Task count (Check 6):** 10 tasks across T0–T3. TDD cycle is explicitly described
  with commit message conventions. No ambiguity in task ordering.
- **Data contracts:** Both JSON shapes (with and without suggestion) are fully tabulated
  with field names, types, presence rules, and transformation formulas.

---

## Required action before execution

**Fix BLOCKER-1 first:**

The spec planner must correct the synthetic CSV path in three locations:
- `spec.md` line 226: `--input` argparse default → `data/dough/smart_budget_synthetic.csv`
- `spec.md` line 246: T3.1 step 1 verification → `data/dough/smart_budget_synthetic.csv`
- `spec.md` lines 273–275: mandatory verification CLI commands → add `--input data/dough/smart_budget_synthetic.csv`

**Recommended: also fix W-1 (pytest-cov) in the same pass** by adding
`pytest-cov>=4.0.0` to the T0.1 requirements change to avoid a surprise failure at V2.

Run `/blossom-workflow:plan DATA-1137` to revise the spec, then re-run
`/blossom-workflow:review DATA-1137` (preflight mode) before handing off to the implementer.
