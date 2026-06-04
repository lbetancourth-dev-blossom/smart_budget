# Preflight Report — DATA-1179: DS - Smart Budget Dataset & Model Changes

**Reviewer:** blossom-reviewer (automated preflight)
**Inputs:** `changes/DATA-1179/plan.md`, `changes/DATA-1179/spec.md`,
`src/smart_budget/aggregator.py`, `src/smart_budget/model.py`,
`scripts/build_fact_transactions.py`
**Date:** 2026-06-01

---

## Verdict

### ⚠️ PASS WITH WARNINGS

The spec is well-structured overall. All four DCR decisions from `plan.md` are
traceable to at least one task, the TDD test-contract pattern is present in every
task section, and the execution order is safe (no circular dependencies). However,
**2 critical spec gaps** exist that would cause an implementer to either silently
produce broken output or receive the wrong instruction for a pre-existing file. An
additional **7 warnings** describe ambiguities where the implementer would have to
guess or could choose an incorrect path.

Recommended action: resolve the 2 critical gaps in `spec.md` before handing off to
the implementer. The warnings can be addressed inline as implementation notes or as
quick spec clarifications.

---

## Check-by-check results

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Each task has clear deliverables (file + function) | ✅ | T1–T6 name files and functions; T7 needs file-existence fix (see C2) |
| 2 | TDD: test contracts before implementation (RED→GREEN) | ✅ | Every task section contains test contracts; execution order §7 starts with T1 tests |
| 3 | No ambiguous instructions (implementer must not guess) | ⚠️ | 2 critical + 5 warning-level ambiguities — detailed below |
| 4 | All DCR decisions from `plan.md` covered by at least one task | ✅ | D1→T3/T4, D2→T1, D3→T4, D4→T6 — all closed |
| 5 | Execution order is safe (no forward dependency) | ✅ | T1→T3→T4→T2→T5→T6→T7 is valid; T4 correctly depends on T3 grain change |
| 6 | No cross-tenant data access patterns | ✅ | `aggregate_monthly` groupby includes `idclient`+`idcompany`; TC-T7 covers cross-company leak |
| 7 | `idmember` null handling: log + skip | ✅ | T1 spec + TC-T1-3 cover the null path; "Notas" confirms `total_suggested=0.0` not null |
| 8 | `total_suggested` calculation well-specified | ⚠️ | Formula is correct; TC-T4-4 assert is non-definitive (Warning W2); null-suggestion interaction needs clarification (Warning W7) |
| 9 | Golden set re-freeze marked as intentional breaking change | ✅ | plan.md risk table + spec.md "Notas" both flag this; T6 states the procedure |
| 10 | APPEND-ONLY constraint on `smartBudgetSuggestionLog` not violated | ✅ | No task writes to or modifies `smartBudgetSuggestionLog`; all changes are upstream of that table |

---

## Critical issues

### C1 — `prepare_smart_budget_data.output_cols` not listed in T3 scope

**Spec reference:** `spec.md` T3 (lines 80–121) lists three functions to change:
`aggregate_monthly`, `zero_fill`, `apply_gating`. It does **not** list
`prepare_smart_budget_data`.

**Code reference:** `src/smart_budget/aggregator.py` lines 112–116:
```python
output_cols = [
    "idclient", "idcompany", "idaccount", "idcategory", "defaultcategory",
    "period_yyyymm", "monthly_total",
]
return gated[output_cols].reset_index(drop=True)
```

**Impact:** `prepare_smart_budget_data` is the orchestrator called by
`run_smart_budget_prep.py` (line 151). After T3 changes, `aggregate_monthly` will
emit `idmember` and `zero_fill`/`apply_gating` will propagate it — but
`prepare_smart_budget_data` would then **silently drop** `idmember` by selecting
only `output_cols`. This would break T4 (model.py), T5 (run_methods.py), and T6
(golden set) because the output of the prep pipeline would never contain `idmember`.

No unit test in the spec exercises `prepare_smart_budget_data` end-to-end; the
breakage would only surface during T6 golden set integration.

**Resolution:** Add to T3 spec:
> **`prepare_smart_budget_data`**: add `"idmember"` to `output_cols` between
> `"idcompany"` and `"idaccount"` (position consistent with D2 grain hierarchy).

---

### C2 — T7 instructs "Actualizar `tests/unit/test_multitenancy.py`" — file does not exist

**Spec reference:** `spec.md` T7 header and "Archivos impactados" table (line 303):
```
| `tests/unit/test_multitenancy.py` | Actualizar T7-1, T7-2 |
```

**Code reference:** `tests/unit/` directory listing — `test_multitenancy.py` is
**absent**. Confirmed with directory scan: the file does not exist in the worktree.

**Impact:** An implementer following "Actualizar" will search for the file, find
nothing, and either skip the task or create it without the "Crear" safety checks
(e.g., verifying no test fixture dependencies). More importantly, neither TC-T7-1
nor TC-T7-2 are anchored to any existing test structure — there is no describe-block
to update.

**Resolution:** Change the T7 "Archivo" line to:
> **Archivo:** `tests/unit/test_multitenancy.py` **(crear)**

---

## Warnings

### W1 — T4: nested dict example directly precedes the flat-list "Decisión" — confusing read order

**Spec reference:** `spec.md` lines 147–162.

The spec shows a fully-formed nested `{ idmember: { "suggestions": [...] } }` JSON
structure, immediately followed by "O mantener lista plana... **Decisión de
implementación:** retornar `list[dict]`...". An implementer reading top-to-bottom
could begin implementing the nested structure before noticing the override. The
nested example should be labeled `# REJECTED — shown for context only` or removed
entirely.

**Recommendation:** Strike the nested example or prepend: `# Option A (not chosen):`.

---

### W2 — TC-T4-4: assert is non-definitive (`(o None — aclarar en impl)`)

**Spec reference:** `spec.md` T4, TC-T4-4 (line 195):
```python
# Assert: result["total_suggested"] == 0.0  (o None — aclarar en impl)
```

The "Notas de implementación" at the bottom of spec.md (line 321) resolves this:
> `total_suggested`: si un miembro tiene 0 sugerencias no-nulas → `total_suggested = 0.0` (no null).

However, the test contract itself contains `(o None — aclarar en impl)`. An
implementer may copy the comment literally and leave the test as a `pytest.skip` or
write `assert result["total_suggested"] is None`, directly contradicting the Notes
section.

**Recommendation:** Update TC-T4-4 assert to remove the parenthetical:
```python
# Assert: result["total_suggested"] == 0.0  # defined in Notas: never None
```

---

### W3 — T5: `idaccount` retention in CSV output is an unresolved "or"

**Spec reference:** `spec.md` T5 (line 212):
> "Eliminar `idaccount` del output (o mantenerlo como campo opcional para debug)"

This "or" has no decision. `idaccount` appears in the current `run_methods.py`
output column set. Keeping vs. removing it affects backward compatibility with any
downstream CSV consumer. The spec should prescribe one option.

**Recommendation:** Add a "Decisión de implementación" line under T5:
> `idaccount`: eliminar del output final. La trazabilidad debug se preserva
> en `fact_transactions.csv`.

---

### W4 — TC-T7-2: "raises o separa correctamente" — two valid paths, no decision

**Spec reference:** `spec.md` T7, TC-T7-2 (line 282):
```python
# Assert: raises o separa correctamente (multi-tenancy check)
```

The assertion allows either a `ValueError` raise or silent separation. These have
very different security profiles: a `ValueError` stops processing (safe-fail),
while silent separation could mask misconfigured data. Given the medium-risk
multi-tenancy classification in `plan.md`, the spec should prescribe the behaviour.

**Recommendation:** Given D1 (idclient/idcompany are security filters, not model
inputs), the expected answer is: upstream filtering guarantees one (idcompany) per
call; the model should `raise ValueError` if the invariant is violated. Update the
assert to:
```python
# Assert: raises ValueError("idmember maps to multiple companies")
```

---

### W5 — Null `idmember` filtering: no spec task specifies where rows are excluded from the pipeline

**Plan.md reference:** D2 (line 41): "Cuentas sin enlace: `idmember = null`, log warning,
**excluidas del modelo**."

**Spec gap:** TC-T1-3 verifies that `_resolve_idmember` returns NaN for unmatched
accounts. However, no task (T1, T2, T3, T4) specifies WHICH function drops null
`idmember` rows before the model sees them. Pandas `groupby` silently excludes NaN
keys, so in practice the model may "work" — but the log warning prescribed by D2
would never fire if the filter is implicit.

**Recommendation:** Add to T2 or T3 (whichever handles the prepared DataFrame):
> If `idmember` is present and has null values, log structlog warning
> `"idmember_null_rows_excluded"` with count; then drop those rows before
> passing to `aggregate_monthly`.

---

### W6 — PII hashing: no test contract verifies that `idmember` log entries are hashed

**Spec reference:** `spec.md` "Notas de implementación" (line 322):
> **PII**: `idmember` en logs siempre hasheado con SHA-256 + `SB_LOG_SALT`.

**Gap:** None of the 16 test contracts (TC-T1-1 through TC-T7-2) includes an
assertion on log output. The hashing requirement could be skipped with no test
catching it. This is a compliance risk: if `idmember` appears in a plain-text
`structlog.warning(...)` call, it violates the PII policy.

**Recommendation:** Add to T1 or T7 test contracts:
```python
# TC-PII-1: idmember never appears unhashed in log output
# Arrange: _resolve_idmember with a known idmember value
# Act: capture structlog output
# Assert: str(idmember) NOT in captured log; sha256(idmember + salt) IS present
```

---

### W7 — T4: interaction between `_null_suggestion` and the `total_suggested` post-process needs explicit wording

**Spec reference:** `spec.md` T4, item 3 (line 140):
> "Después del loop, agregar paso de `total_suggested`"

**Issue:** Null suggestions are appended inside the loop via `continue`. If the
post-process iterates over `results` and adds `total_suggested` based on `idmember`
grouping, null-suggestion dicts MUST also receive the field to satisfy TC-T4-2's
`required_fields` contract. The spec does not state explicitly that the post-process
covers null-suggestion rows.

**Recommendation:** Add one sentence to T4 item 3:
> The post-process must update **all** rows in `results` (including null-suggestion
> rows) with the `total_suggested` value for their `idmember`. Null-suggestion rows
> count as 0 toward the sum (they do not contribute `suggested_amount`).

---

## What passes cleanly

- **All four DCR decisions traced to tasks**: D1→T3/T4, D2→T1, D3→T4, D4→T6. No
  plan decision is orphaned.
- **Execution order is safe and documented**: The §"Orden de ejecución" section
  correctly sequences T1 before T3, T3 before T4, which matches the actual data
  dependency chain.
- **TDD pattern is structurally present**: Every task has test contracts with
  Arrange/Act/Assert comments. Tests reference newly-created files
  (`test_build_fact_transactions_idmember.py`, `test_prep_idmember.py`, etc.).
- **`idmember` null path is defined**: TC-T1-3 covers unmatched accounts; "Notas"
  specifies `total_suggested=0.0` (not null) for all-null members.
- **Golden set re-freeze is documented as intentional**: plan.md risk table + spec
  "Notas" both flag the intentional test-breakage. The implementer will not be
  surprised.
- **APPEND-ONLY constraint is not at risk**: No task touches `smartBudgetSuggestionLog`
  directly or indirectly. All changes are in the ML pipeline layer (aggregator →
  model → run_methods), which is upstream of that table.
- **Multi-tenancy grain is correct**: `aggregate_monthly` groupby (spec line 84)
  retains `idclient` + `idcompany` so tenant data is naturally partitioned.
  `apply_gating` and `model.py` correctly narrow to `idmember` grain.
- **Backward compat strategy is articulated**: `idaccount` kept in
  `fact_transactions` for traceability; only removed from model output. T2 uses
  warning-not-error for missing `idmember`.

---

## Summary

| Category | Count |
|----------|-------|
| Critical issues | 2 |
| Warnings | 7 |
| Clean checks | 8/10 (checks 1, 2, 4, 5, 6, 7, 9, 10) |

**Next step:** Address **C1** and **C2** in `spec.md` before handing off to the
implementer. The 7 warnings can be resolved as quick spec clarifications (1–3
sentences each) or as inline implementation notes. Once C1–C2 are patched, this
spec is ready for `/blossom-workflow:execute`.
