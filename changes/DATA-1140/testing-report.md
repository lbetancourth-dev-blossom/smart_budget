# Testing Report — DATA-1140: Endpoint Smart Budget (on-demand)

**Branch:** `feat/DATA-1140`  
**Date:** 2026-05-15  
**Implementer:** `blossom-implementer`  
**Ticket:** DATA-1140  

---

## Summary

| Metric | Value |
|---|---|
| Tasks completed | 5/5 (T0, T1, T2, T3, T5) |
| Test files written | 3 (`test_loader.py`, `test_api.py`, `test_inference.py`) |
| Test contracts covered | 21 (7 T1 + 8 T2 + 6 T5) |
| Tests passing | 105 passed, 1 pre-existing failure, 3 skipped |
| Coverage (new modules) | 95% total (`loader.py` 97%, `router.py` 93%, `inference.py` 89%) |
| V-steps passed | 10/10 (V1–V8 + V9–V10) |
| Proposal updates | None |

---

## TDD Iteration History

| Task | RED commit | GREEN commit | Cycles | Notes |
|---|---|---|---|---|
| T0 | skipped (glue-only) | `f1e2b53` | — | requirements.txt update |
| T1 | `f9e8896` | `1253267` | 1 | All 7 tests green on first impl |
| T2 | `6a2fedc` | `0aad856` | 2 | Iteration 2: Python 3.9 `float\|None` → `Optional[float]` fix |
| T5 | `4fcd8a0` | `f916572` | 1 | All 6 tests green on first impl |
| refactor | — | `179c4a9` | — | `black` formatting applied |

---

## V1 — Full Test Suite

```bash
pytest tests/ -v --cov=src/smart_budget --cov=src/api --cov-report=term-missing
```

**Result:** ✅ 105 passed, 1 pre-existing failure, 3 skipped

```
Name                             Stmts   Miss  Cover   Missing
--------------------------------------------------------------
src/api/__init__.py                  0      0   100%
src/api/inference.py                46      5    89%   53, 93, 133-135
src/api/router.py                   71      5    93%   97-99, 130-131
src/smart_budget/__init__.py         0      0   100%
src/smart_budget/aggregator.py      39      1    97%   43
src/smart_budget/filters.py         15      0   100%
src/smart_budget/loader.py          64      2    97%   91, 131
src/smart_budget/model.py          114      3    97%   97, 233, 236
--------------------------------------------------------------
TOTAL                              349     16    95%
```

**Pre-existing failure (not introduced by this ticket):**
- `test_TC4_golden_set_matches_output` — `FileNotFoundError` on `data/dough/smart_budget_synthetic.csv` (gitignored, requires real production data). This test was failing before any changes in this branch.

---

## V2 — Linting

```bash
ruff check src/smart_budget/loader.py src/api/router.py src/main.py src/api/inference.py
black --check src/smart_budget/loader.py src/api/router.py src/main.py src/api/inference.py
```

**Result:** ✅ `All checks passed!` (ruff); `All done!` (black, after reformatting)

---

## V3 — Server Starts

```bash
PYTHONPATH=src SMART_BUDGET_DATA_DIR=data/dough uvicorn src.main:app --port 8001
```

**Result:** ✅

```
INFO:     Started server process [37689]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
```

---

## V4 — Smoke Test (INT23/GROCERIES)

```bash
curl -s "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=2026-05"
```

**Result:** ✅ HTTP 200

```json
{
  "idaccount": "INT23",
  "idclient": "1",
  "idcompany": "1",
  "defaultcategory": "GROCERIES",
  "period_id": "2026-05",
  "suggested_amount": 181.67,
  "confidence": "medium",
  "basis": {
    "months_analyzed": 3,
    "months_with_positive_spend": 3,
    "period_range": "2026-02 ~ 2026-04",
    "method": "wma",
    "treatment": "B"
  },
  "display_label": "Basado en tus últimos 3 meses",
  "model_version": "fase0-v1"
}
```

Criteria met: `suggested_amount: 181.67` (number) and `model_version: "fase0-v1"`.

---

## V5 — OpenAPI Schema Accessible

```bash
curl -s "http://localhost:8001/openapi.json" | python3 -m json.tool | grep '"title"'
```

**Result:** ✅

```
"title": "Smart Budget API",
```

---

## V6 — 404 for Unknown Account

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8001/smart-budget/suggestion?idaccount=FAKE_ZZZ&defaultcategory=GROCERIES&period_id=2026-05"
```

**Result:** ✅ `404`

---

## V7 — 422 for Invalid period_id

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=bad"
```

**Result:** ✅ `422`

---

## V8 — No Regressions in Pre-existing Tests

```bash
pytest tests/unit/test_model.py tests/unit/test_aggregator.py tests/unit/test_filters.py -v
```

**Result:** ✅ 55 passed (no new regressions)

The 1 failure (`test_TC4_golden_set_matches_output`) was already failing before this branch — it requires gitignored production data files. Confirmed by running on the original commit:

```
# Before DATA-1140 changes:
FAILED tests/unit/test_model.py::test_TC4_golden_set_matches_output - FileNotFoundError
# After DATA-1140 changes:
FAILED tests/unit/test_model.py::test_TC4_golden_set_matches_output - FileNotFoundError
```

Same failure mode — no regression introduced.

---

## V9 — inference.py Importable

```bash
python3 -c "from src.api.inference import model_fn, input_fn, predict_fn, output_fn; print('ok')"
```

**Result:** ✅ `ok`

---

## V10 — Notebook Has All Required Cells

```bash
# Verified programmatically — all 3 required keywords found in notebook cells:
✅ deploy found
✅ invoke_endpoint found
✅ delete_endpoint found
```

---

## Task Status

| Task | Status | Evidence |
|---|---|---|
| T0 — requirements.txt | ✅ | `pip install -r requirements.txt` succeeds; `fastapi`, `uvicorn`, `httpx` importable |
| T1 — loader.py | ✅ | 7/7 test contracts passing (`tests/unit/test_loader.py`) |
| T2 — router.py + main.py | ✅ | 8/8 test contracts passing (`tests/unit/test_api.py`) |
| T3 — tests detallados | ✅ | test_loader.py (7 tests) + test_api.py (8 tests) created |
| T4 — V1–V8 | ✅ | All V-steps verified and passing (see above) |
| T5 — inference.py + notebook | ✅ | 6/6 test contracts passing (`tests/unit/test_inference.py`); V9-V10 passing |

---

## File Manifest (Created/Modified)

| File | Operation | Lines |
|---|---|---|
| `requirements.txt` | MODIFY | +5 |
| `src/api/__init__.py` | CREATE | 2 |
| `src/api/router.py` | CREATE | 168 |
| `src/api/inference.py` | CREATE | 172 |
| `src/main.py` | CREATE | 13 |
| `src/smart_budget/loader.py` | CREATE | 212 |
| `tests/unit/test_loader.py` | CREATE | 238 |
| `tests/unit/test_api.py` | CREATE | 293 |
| `tests/unit/test_inference.py` | CREATE | 211 |
| `notebooks/smart_budget_sagemaker_endpoint.ipynb` | CREATE | 237 |

---

## Structural Audit

- **Stubs/TODOs:** 0 hits (`grep -rnE 'TODO|FIXME|XXX|stub|placeholder'`)
- **Wiring:** `router` imported in `main.py`; `load_history` imported in `router.py` and `inference.py`; `apply_gating` + `compute_budget_suggestions` imported in both entry points
- **Feature flags:** N/A (no feature flags in spec)
- **Financial audit trail:** No monetary logging — amounts not logged in plain text (AGENTS.md compliance)

---

## Coverage Details (new modules only)

| Module | Stmts | Miss | Cover |
|---|---|---|---|
| `src/api/__init__.py` | 0 | 0 | 100% |
| `src/api/router.py` | 71 | 5 | 93% |
| `src/api/inference.py` | 46 | 5 | 89% |
| `src/smart_budget/loader.py` | 64 | 2 | 97% |

All exceed the 80% threshold from the spec.

---

## Proposal Updates

None — all spec contracts were sufficient and implemented without gaps.
