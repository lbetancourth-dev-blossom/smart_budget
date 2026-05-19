# Preflight Review — DATA-1140: Endpoint Smart Budget (on-demand)

**Reviewer:** blossom-reviewer (adversarial preflight, pre-implementation)  
**Date:** 2026-05-15  
**Mode:** FEATURE | Risk: HIGH  
**Inputs:** `changes/DATA-1140/spec.md`, `changes/DATA-1140/plan.md`, codebase at worktree root  

---

## Verdict

### ✅ PASS WITH WARNINGS

*(Updated 2026-05-15 — los 3 hallazgos CRITICAL fueron corregidos directamente en spec.md antes de ejecutar)*

**C1, C2, C3 corregidos en spec.md:**
- C1: `from api.router import router` → `from .api.router import router`
- C2: `@lru_cache(maxsize=None)` añadido a `_synthetic_accounts`
- C3: contrato de test T1 actualizado para usar `tmp_path` en lugar de `data/dough real`

Quedan 3 hallazgos IMPORTANT y 4 MINOR (no bloqueantes).

---

## Finding Counts

| Severity | Count |
|---|---|
| 🔴 CRITICAL | 3 |
| 🟡 IMPORTANT | 3 |
| 🟢 MINOR | 4 |

---

## 🔴 CRITICAL Findings

---

### C1 — `src/main.py` import chain fails at uvicorn startup

**Check:** Import chains — does `from api.router import router` resolve at runtime?

**Evidence:**

The spec prescribes `src/main.py` with this import:
```python
# spec.md line 473
from api.router import router
```

The spec also prescribes this startup command (spec.md line 573, plan.md line 417):
```bash
SMART_BUDGET_DATA_DIR=data/dough uvicorn src.main:app --reload --port 8001
```

When uvicorn invokes `src.main:app`:
- Python adds the **project root** to `sys.path`
- `src.main` is resolved from project root → `src/main.py` ✓
- Inside `src/main.py`, `from api.router import router` is an **absolute import** that searches `sys.path = [project_root, ...]`
- `api/` does **not exist at project root** — it lives at `src/api/` (spec.md line 17)
- Result: `ModuleNotFoundError: No module named 'api'` ← **V3 fails before the server ever starts**

Verified live:
```
python3 -c "import sys; sys.path.insert(0, '<project_root>'); import importlib; importlib.import_module('api')"
# → BLOCKED - No module named 'api'
```

`conftest.py` adds `src/` to `sys.path` (line 7), so **pytest tests pass** — this masks the failure. V3–V7 manual verification steps all fail.

**Why it's CRITICAL:** V3 (`Application startup complete`) is the first manual gate. It fails immediately. All downstream `curl` tests (V4–V7) also fail. The FastAPI app can never run.

**Concrete fix (choose one):**

Option A — relative import in `src/main.py` (cleanest; works with `uvicorn src.main:app`):
```python
# src/main.py
from .api.router import router   # relative import — resolves to src.api.router
```

Option B — full dotted import:
```python
# src/main.py
from src.api.router import router
```
(requires updating test `from src.main import app` to match, and ensuring `src` is importable from project root — it is, since `src/__init__.py` exists)

Option C — change the uvicorn command to set `PYTHONPATH`:
```bash
PYTHONPATH=src SMART_BUDGET_DATA_DIR=data/dough uvicorn main:app --reload --port 8001
```
(requires renaming the startup command in spec plan.md and V3)

**Recommended:** Option A (relative import) — minimal change, no env var requirement.

---

### C2 — `lru_cache` imported but never applied — ruff F401 breaks V2

**Check:** Placeholder scan + import chains — does the spec import `lru_cache` but never use it?

**Evidence:**

The spec's `loader.py` header (spec.md line 68) imports:
```python
from functools import lru_cache
```

But searching spec.md for `@lru_cache` returns zero hits. The decorator is never applied. The `_synthetic_accounts` docstring says "Usa lru_cache implícito a través del llamador" (spec.md line 92), but this is a dangling comment — the decorator is absent from the function definition (spec.md line 89).

The V2 verification gate (spec.md line 566–568) runs:
```bash
ruff check src/smart_budget/loader.py ...
```
with the criterion **"0 errores"**.

`ruff` enables `F401` (imported but unused) by default. An unused `lru_cache` import **fails F401** → V2 fails.

**Why it's CRITICAL:** V2 is an explicit spec gate. The spec creates a file that fails its own linting check.

**Concrete fix (choose one):**

Option A — apply the decorator (makes the caching work as intended):
```python
@lru_cache(maxsize=None)
def _synthetic_accounts(base_dir: Path) -> frozenset[str]:
```
Note: `lru_cache` requires the argument to be hashable. `Path` is hashable. ✓

Option B — remove the unused import and update the docstring:
```python
# Remove: from functools import lru_cache
# Update docstring: "Llamar solo una vez por base_dir — no cacheable sin state externo."
```

**Recommended:** Option A. Matches the design intent in plan.md (A4: "Cacheable (lectura única por proceso)") and eliminates both the linting error and the performance regression.

---

### C3 — Data files are gitignored — test contracts and V4 smoke test fail

**Check:** Runtime env — are data files present in the worktree?

**Evidence:**

`.gitignore` (line 1–2):
```
data/
!data/.gitkeep
```

The entire `data/` directory (including `data/dough/smart_budget_synthetic.csv`, `data/dough/test/test_internal.csv`, `data/dough/test/test_external.csv`) is git-ignored. The worktree at `.worktrees/DATA-1140/` has **no `data/dough/` directory**:
```bash
ls .worktrees/DATA-1140/data/dough/
# → ls: No such file or directory
```

This causes three failures:

**Failure 1 — T1 test contract `test_load_history_raw_account_returns_positive_amounts`** (spec.md line 257–260):
```yaml
input: "idaccount='INT23', defaultcategory='GROCERIES', base_dir apunta a data/dough real"
```
In CI, `base_dir = "data/dough"` does not exist → `load_history` raises `FileNotFoundError` (spec.md line 236) → test fails with exception, not with assertion.

**Failure 2 — T1 test contract `test_load_history_synthetic_account_returns_monthly_df`** (spec.md line 253–256):
```yaml
input: "idaccount='SYN001', defaultcategory=primer category de SYN001 en synthetic CSV"
```
Same `base_dir` issue — `smart_budget_synthetic.csv` doesn't exist in worktree.

**Failure 3 — V4 smoke test** (spec.md line 579):
```bash
curl "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=2026-05"
```
`base_dir = Path(os.getenv("SMART_BUDGET_DATA_DIR", "data/dough"))` → dir doesn't exist → `FileNotFoundError` → HTTP 500.

**Contradiction with T3 section:** spec.md line 531–533 says:
> "Fixture de apoyo: crear un directorio temporal con un CSV sintético mínimo (3 accounts × 1 category × 6 periods) para tests de carga **sin depender de `data/`**. Usar `tmp_path` de pytest."

The T1 test contracts contradict T3 — one says use real data, the other says use `tmp_path`. The implementer cannot satisfy both.

**Why it's CRITICAL:** Two of the 7 T1 test contracts (29%) fail unconditionally in CI. V4 fails whenever `data/` is absent. The spec's own coverage requirement (≥80% for new modules) is jeopardized.

**Concrete fix:**

Align the T1 test contracts to the T3 instruction. Replace real-data test contracts with fixture-based ones:

```python
# test_load_history_raw_account_returns_positive_amounts — replace with:
def test_load_history_raw_account_returns_positive_amounts(tmp_path):
    # Create minimal test_internal.csv with INT23, GROCERIES, negative OLB amounts
    internal_csv = tmp_path / "test" / "test_internal.csv"
    internal_csv.parent.mkdir()
    internal_csv.write_text(
        "idtransaction,idclient,idcompany,idaccount,defaultcategory,"
        "incomeexpenditure,amount,date,status,deletedat\n"
        "SUB001,1,1,INT23,GROCERIES,expenditure,-500.0,2026-02-14,,\n"
        "SUB002,1,1,INT23,GROCERIES,expenditure,-420.0,2026-03-10,,\n"
        "SUB003,1,1,INT23,GROCERIES,expenditure,-380.0,2026-04-05,,\n"
    )
    # Create empty external CSV
    ext_csv = tmp_path / "test" / "test_external.csv"
    ext_csv.write_text(
        "idtransaction,idclient,idcompany,idaccount,defaultcategory,"
        "incomeexpenditure,amount,date,status,deletedat\n"
    )
    # Create synthetic CSV without INT23 (forces raw path)
    synth_csv = tmp_path / "smart_budget_synthetic.csv"
    synth_csv.write_text(
        "idclient,idcompany,idaccount,idcategory,defaultcategory,period_yyyymm,monthly_total\n"
        "1,1,SYN001,1,GROCERIES,2026-02,300.0\n"
    )
    result = load_history("INT23", "GROCERIES", tmp_path)
    assert not result.empty
    assert (result["monthly_total"] >= 0).all()
```

Apply the same fixture pattern to `test_load_history_synthetic_account_returns_monthly_df`.

For V4: document in the spec that V4 requires `data/dough/` to be populated from the shared dev data store (or a dev setup script).

---

## 🟡 IMPORTANT Findings

---

### I1 — `sagemaker>=2.200.0` in shared `requirements.txt` will bloat/break CI

**Check:** Runtime env — dependency conflicts and install time

**Evidence:**

spec.md line 14 and T0 (line 37–42) add:
```
sagemaker>=2.200.0
```
to the **single shared `requirements.txt`** (plan.md A13: "el único archivo de deps del repo").

The `sagemaker` SDK has:
- ~100MB+ install size
- Mandatory transitive deps including `boto3`, `botocore`, `protobuf`, `dill`, `pathos`, `jsonschema`, `docker`, `urllib3`
- No AWS credentials required for import, but `sagemaker.Session()` (used in the notebook) errors without credentials

This bloats the standard `pip install -r requirements.txt` (T4 V1) and CI runs with unnecessary deps. The sagemaker package is only used in `notebooks/smart_budget_sagemaker_endpoint.ipynb` — not in any source module or pytest test.

Furthermore, `sagemaker` pins `protobuf>=3.12,<5.0` and `boto3>=1.26.131,<2.0` — these may conflict with future additions to the project.

**Concrete fix:**

Create a separate `requirements-sagemaker.txt`:
```
-r requirements.txt
sagemaker>=2.200.0
```

Update T0 in the spec: standard `requirements.txt` gets only `fastapi`, `uvicorn`, `httpx`. SageMaker extras are installed separately when working on T5. Update V1 criterion accordingly.

---

### I2 — `src/api/inference.py` is fully stubbed — T5 tests cannot pass

**Check:** Placeholder scan — are there unimplemented functions in spec?

**Evidence:**

spec.md lines 656–670 define all four SageMaker inference functions with `...` (ellipsis) as body:
```python
def model_fn(model_dir: str):
    """Retorna base_dir con los CSVs bundleados en model.tar.gz."""
    ...   # ← STUB

def input_fn(input_data: str, content_type: str) -> dict:
    """Deserializa el request JSON."""
    ...   # ← STUB

def predict_fn(data: dict, model) -> dict:
    """Ejecuta load_history → apply_gating → compute_budget_suggestions."""
    ...   # ← STUB

def output_fn(prediction: dict, accept: str) -> str:
    """Serializa la respuesta a JSON string."""
    ...   # ← STUB
```

The spec has 6 test contracts for T5 (spec.md lines 729–754), including:
- `test_inference_predict_fn_returns_valid_schema`: expects `suggested_amount float >= 0`
- `test_inference_predict_fn_gating`: expects `confidence=null` for 1-month history

Against stub implementations, every T5 test that calls a function will either return `None` (Python's implicit return from `...`) or raise `TypeError` when the caller tries to unpack the result. All 4 behavioral tests fail.

V9 (spec.md line 760) only checks importability:
```bash
python3 -c "from src.api.inference import model_fn, input_fn, predict_fn, output_fn; print('ok')"
```
This PASSES with stubs (functions are importable). But the test suite fails.

**Concrete fix:**

The spec must either:
- Provide actual implementation logic for each of the 4 functions (recommended — the logic is trivially derivable from `loader.py + aggregator.py + model.py`)
- OR explicitly mark T5 as "stub only, no test contracts" and remove the 6 test contracts + `tests/unit/test_inference.py` from the manifest

Minimum `predict_fn` implementation (derives from router.py pattern already in the spec):
```python
def predict_fn(data: dict, model) -> dict:
    base_dir = Path(model)
    history = load_history(data["idaccount"], data["defaultcategory"], base_dir)
    if history.empty:
        return {"suggested_amount": None, "confidence": None, "basis": None}
    reference_date = str(pd.Period(data["period_id"], freq="M") - 1)
    gated = apply_gating(history, min_months=2)
    if gated.empty:
        return {"suggested_amount": None, "confidence": None, "basis": None}
    results = compute_budget_suggestions(gated, method="wma", treatment="B",
                                         reference_date=reference_date, lookback_months=3)
    return results[0] if results else {"suggested_amount": None, "confidence": None, "basis": None}
```

---

### I3 — `apply_gating` called on full history, not on lookback window — untested edge case

**Check:** Coverage matrix — does the spec cover all edge cases from plan?

**Evidence:**

spec.md line 392: `gated = apply_gating(history, min_months=_MIN_MONTHS_GATING)`

The `history` DataFrame contains all months available for the account (potentially years of data). `apply_gating` counts months with `monthly_total > 0` across the **entire history**. A user with 10 months of data from 2024 but 0 months in the last 3 months (the lookback window for 2026-05) would:
1. Pass gating (10 months > 2) ✓
2. Pass to `compute_budget_suggestions` with `lookback_months=3, reference_date="2026-04"`
3. Have empty data in the window → `results = []` → null response

This path exists and returns null, but the spec's test contract coverage gap:
- No test covers "account has old history beyond lookback window but zero data in the 3-month window"
- The spec test `test_get_suggestion_period_id_not_in_historical_window` (spec.md line 520–523) covers `period_id` in far future, but not the case where history exists but predates the window.

This is not a crash but causes a silent null result that could be confused with a gating failure. The plan's error table (plan.md line 132–134) does not distinguish between "gated" and "no data in window".

**Concrete fix:**

Add one test contract to T2:
```yaml
- name: test_get_suggestion_history_predates_window_returns_null
  input: "Mock: load_history returns 3 months of data from 2024-01~2024-03; period_id=2026-05"
  expected: "HTTP 200; confidence=null; suggested_amount=null (no data in 3-month lookback window)"
```

Optionally add a log line in the router distinguishing `reason="no_results_in_window"` (already in the spec, spec.md line 408) from `reason="gating_min_months"` — the spec already does this. The gap is only the missing test contract.

---

## 🟢 MINOR Findings

---

### M1 — `_synthetic_accounts` reads CSV on every call (no caching despite design intent)

**Check:** Coverage matrix — design decisions vs. spec implementation

**Evidence:**

plan.md decision A4 says `_synthetic_accounts` is "Cacheable (lectura única por proceso)". The spec imports `lru_cache` (spec.md line 68) but does not apply `@lru_cache` to `_synthetic_accounts` (addressed in C2 above as the linting issue). The performance consequence: every `load_history` call for a non-synthetic account reads the entire `smart_budget_synthetic.csv` just to check membership.

In dev use with a single server, this means one file read per request. Not catastrophic, but inconsistent with the stated design intent. Resolved as part of C2 fix (adding `@lru_cache`).

---

### M2 — `notebooks/` parent directory does not exist in worktree

**Check:** Runtime env — file system prerequisites

**Evidence:**

```bash
ls .worktrees/DATA-1140/ | grep notebooks
# → (no output) — directory does not exist
```

The spec manifest (spec.md line 20) lists `notebooks/smart_budget_sagemaker_endpoint.ipynb` as **CREATE**. The parent directory `notebooks/` does not exist. The implementer must `mkdir notebooks/` before creating the file, or the file creation will fail.

**Concrete fix:** Add `notebooks/.gitkeep` to the manifest as CREATE, or add `mkdir -p notebooks/` to T5 instructions. Minor but will cause confusion.

---

### M3 — `sagemaker.get_execution_role()` silently fails outside SageMaker

**Check:** Runtime env — notebook execution context

**Evidence:**

spec.md line 694: `role = get_execution_role()`

This call raises `ValueError: Must setup local AWS configuration with a role ARN...` when run outside a SageMaker Notebook Instance or Studio environment. The notebook provides no fallback pattern and no comment warning about the execution context requirement.

The plan (T5 decisions, plan.md line 375–376) uses `blossom-dev` AWS profile but `get_execution_role()` does not use local AWS profiles — it reads the IAM role attached to the SageMaker execution environment.

**Concrete fix:** Add a fallback cell comment and optional override:
```python
try:
    role = get_execution_role()
except Exception:
    # Running locally — set role ARN manually
    role = "arn:aws:iam::<account-id>:role/SageMakerExecutionRole-blossom-dev"
```

---

### M4 — `test_get_suggestion_insufficient_data_returns_null_200` mock path is ambiguous

**Check:** Test coverage — are mock targets correct?

**Evidence:**

spec.md line 551:
```python
unittest.mock.patch("src.api.router.load_history")
```

But `conftest.py` adds `src/` to sys.path, so tests import `main` (not `src.main`) and `api.router` (not `src.api.router`). The module reference for `mock.patch` must match the actual import path used by the test.

If `test_api.py` does `from main import app` (spec.md line 542: "o from main import app si el sys.path lo permite"), the router module is loaded as `api.router`, not `src.api.router`. The patch target `"src.api.router.load_history"` would **not intercept** the call — the mock would be applied to the wrong module reference, the real `load_history` runs, and the test fails.

**Concrete fix:** Align the mock target with the actual import path. If `conftest.py` adds `src/` to sys.path and the router is loaded as `api.router`:
```python
mock.patch("api.router.load_history")  # matches actual module path
```
Or, if using `from src.main import app` (the other option in the spec), the target is `"src.api.router.load_history"`. The spec must commit to one import path and document the mock target accordingly.

---

## Integration Seams — Summary

| Seam | Spec assumption | Reality | Status |
|---|---|---|---|
| `aggregate_monthly` group_keys require `idcategory` | spec.md A6, loader.py step 6 | `aggregator.py:15` — confirmed | ✓ |
| `apply_gating(df, min_months)` signature | spec.md line 392 | `aggregator.py:76` — confirmed | ✓ |
| `compute_budget_suggestions(df, method, treatment, reference_date, lookback_months)` | spec.md line 399–405 | `model.py:202–210` — confirmed | ✓ |
| `filter_transactions(df)` — requires `deletedat`, `incomeexpenditure`, `defaultcategory`, `idtransaction`, `status` | spec.md line 182 | `filters.py:6` — confirmed | ✓ |
| `compute_budget_suggestions` returns `list[dict]` with keys `idaccount`, `idclient`, `idcompany`, `basis`, `confidence`, `display_label`, `model_version` | spec.md line 424–440 | `model.py:315–334` — confirmed | ✓ |
| `basis` dict keys: `months_analyzed`, `months_with_positive_spend`, `period_range`, `method`, `treatment` | spec.md BasisDetail | `model.py:321–329` — confirmed | ✓ |
| `test_internal.csv` has no `idcategory` column | plan.md A6 | Confirmed: columns are `idtransaction,idclient,idcompany,idaccount,defaultcategory,incomeexpenditure,amount,date,status,deletedat` | ✓ |
| `smart_budget_synthetic.csv` has `idaccount` column | spec.md line 97 | Confirmed: `idclient,idcompany,idaccount,idcategory,defaultcategory,period_yyyymm,monthly_total` | ✓ |
| SYN001 exists in synthetic CSV | spec.md T1 + T2 contracts | Confirmed: SYN001–SYN008 present | ✓ |
| `structlog` available | spec.md line 72 | `requirements.txt:3` — `structlog>=21.0.0` | ✓ |
| `pandas`, `statsmodels` available | spec.md — no new models | `requirements.txt:1,4` | ✓ |
| `fastapi`, `uvicorn`, `httpx` NOT yet in requirements.txt | spec.md T0 | Confirmed: absent from current `requirements.txt` | ✓ needs T0 |

---

## What's Solid

- **Core pipeline seams verified**: `aggregate_monthly → apply_gating → compute_budget_suggestions` all match the spec's assumed signatures and return types. The spec's router code will work against the existing model without modifications.
- **Pydantic response schema is sound**: `BasisDetail` and `SuggestionResponse` field names correctly map to `compute_budget_suggestions` output keys (`basis.months_with_positive_spend`, `basis.period_range`, etc.).
- **OLB normalization is correct**: The `_normalize_olb_amounts` logic (abs() on SUB/LOAN prefix rows) correctly mirrors `build_fact_transactions.py:289-290`. The raw CSV columns confirm this works.
- **`reference_date = period_id − 1` is correct**: `str(pd.Period("2026-05", freq="M") - 1) == "2026-04"`. Combined with `lookback_months=3`, the window is `[2026-02, 2026-04]`, matching the agreed example in plan.md A3.
- **Gating threshold (min_months=2) is correctly justified**: plan.md note on why `min_months=2` instead of 3 is sound and implemented consistently in spec.
- **7 T1 test contracts are well-scoped** (minus the 2 that depend on gitignored data — fixable per C3).
- **Synthetic path bypasses aggregate_monthly correctly**: `_load_synthetic_for_account` returns the pre-aggregated DataFrame directly. No attempt to call `aggregate_monthly` on already-aggregated data.

---

## Required Actions Before Implementation

| Priority | Action | Spec section |
|---|---|---|
| 🔴 MUST FIX | Change `from api.router import router` → `from .api.router import router` in `src/main.py` spec | T2 spec, line 473 |
| 🔴 MUST FIX | Add `@lru_cache(maxsize=None)` to `_synthetic_accounts` in `loader.py` spec | T1 spec, line 89 |
| 🔴 MUST FIX | Replace real-data T1 test contracts with `tmp_path` fixtures; document V4 data prerequisite | T1 test contracts + T3 |
| 🟡 SHOULD FIX | Move `sagemaker>=2.200.0` to separate `requirements-sagemaker.txt` | T0 spec |
| 🟡 SHOULD FIX | Provide actual implementations for all 4 `inference.py` functions (not stubs) | T5 spec |
| 🟡 SHOULD FIX | Add test contract for "history predates lookback window → null 200" | T2 test contracts |
| 🟢 NICE TO HAVE | Add `mkdir -p notebooks/` to T5 prerequisites | T5 spec |
| 🟢 NICE TO HAVE | Add `get_execution_role()` fallback in notebook | T5 notebook cells |
| 🟢 NICE TO HAVE | Clarify mock patch target path (`api.router.load_history` vs `src.api.router.load_history`) | T3 section |
