# Implementation Spec: DATA-1275

> This spec is the sole input for the implementer subagent (see `## Runtime` below). Every file listed here MUST exist at the end of execution. Every mandatory verification step MUST pass. Task IDs are stable — the Execution Report at the bottom is updated by the implementer as it progresses.

## Runtime

- **Implementer**: `blossom-implementer`
- **Routing rationale**: default — backend Python (py-agents) change. No Figma/UI signals.

## Branch

- **Name**: `DATA-1275`
- **Base**: `main`
- **Target in PR**: `main`

## Closed decisions snapshot

- **D1** — Athena conn: `s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/'`, `region='us-east-2'`, via env vars `ATHENA_S3_STAGING_DIR` / `ATHENA_REGION_NAME`.
- **D2** — Table `dlh_gold_dough_dev.smart_budget_transactions` is pre-filtered. No `type_category` filter in WHERE.
- **D3** — _Revised by dev clarification._ SageMaker deployment already exists via `smart_budget_sagemaker_endpoint.ipynb`. No new entrypoint/surface. Router stays as the FastAPI handler; this ticket only swaps the loader underneath.
- **D4** — **Replace, no backwards compat.** Drop `defaultcategory` entirely. Use `category_id: str` and `category_name: str` from Glue directly. Rename downstream pipeline columns.

## File manifest

| Action | Path | Purpose |
|---|---|---|
| CREATE | `src/smart_budget/athena_loader.py` | Athena loader: `load_history_by_member_athena`, `member_exists_athena`, `_get_connection`, `AthenaQueryError` |
| CREATE | `tests/unit/test_athena_loader.py` | Unit tests for the Athena loader (mocks pyathena) |
| MODIFY | `src/api/router.py` | Swap loader imports CSV → Athena. `SuggestionItem` schema: drop `defaultcategory`, add required `category_id` + `category_name`. Map `AthenaQueryError` → 503. No new module, no `entrypoint.py`. |
| MODIFY | `src/smart_budget/aggregator.py` | Groupby keys: `idcategory, defaultcategory` → `category_id, category_name` |
| MODIFY | `src/smart_budget/model.py` | All column references renamed: `idcategory` → `category_id`, `defaultcategory` → `category_name` |
| MODIFY | `tests/unit/test_api.py` | Mock targets switched to `athena_loader.*`; helper updated; new tests TC-API-10/11 |
| MODIFY | `requirements.txt` | Add `pyathena>=3.0,<4` (matches `blossom-ml-safe-txns/endpoint/requirements.txt`) |
| MODIFY | `src/sagemaker/inference.py` | **KEY CHANGE.** Swap CSV-based loader (`load_history_by_member` / `member_exists` on bundled CSV) for live Athena calls (`load_history_by_member_athena` / `member_exists_athena`). Remove `_DATA_CSV` constant and `base_dir = Path(model) / "data"` reference. Map `AthenaQueryError` to a 4xx-ish `ValueError("datalake temporarily unavailable")` so SageMaker returns `ModelError`. |
| MODIFY | `src/sagemaker/requirements.txt` | Add `pyathena>=3.0,<4` (so the inference container has it at runtime; pin matches `blossom-ml-safe-txns/endpoint/requirements.txt`). |
| MODIFY | `notebooks/smart_budget_sagemaker_endpoint.ipynb` | **KEY CHANGE.** Cell 6 (packaging): stop copying `data/smart_budget_db_<env>.csv` into the staging dir — the artifact no longer carries data. Cell 8 (`SKLearnModel`): pass `env={"ATHENA_S3_STAGING_DIR": "...", "ATHENA_REGION_NAME": "us-east-2", "ATHENA_DATABASE": "dlh_gold_dough_dev", "ATHENA_TABLE": "smart_budget_transactions"}` so the endpoint container can connect at inference time. Cell 4 (markdown): update the description to reflect "data is queried live from Athena per request — not packaged". |
| MODIFY | `tests/unit/test_inference.py` | Mocks switched from CSV fixtures (`tmp_path / "data" / *.csv`) to `smart_budget.athena_loader.load_history_by_member_athena` / `member_exists_athena`. Helper fixtures emit `category_id`/`category_name` columns (D4). New test: `TC-T5.7_inference_calls_athena_loader_not_csv`. |
| UNCHANGED | `src/smart_budget/loader.py` | Kept for batch scripts |
| UNCHANGED | `src/smart_budget/filters.py` | Pipeline unchanged |
| UNCHANGED | `src/smart_budget/queries/smart_budget_monthly_spend.sql` | Upstream pipeline SQL, not used by endpoint |

## Signatures

```python
# src/smart_budget/athena_loader.py

class AthenaQueryError(Exception):
    """Raised when an Athena query fails (timeout, credentials, etc.)."""

def _get_connection() -> "pyathena.Connection":
    """Lazy-init module-level pyathena connection. Reads:
       ATHENA_S3_STAGING_DIR (required), ATHENA_REGION_NAME (default us-east-2).
       Returns a cached connection object. Raises AthenaQueryError if env missing."""

def load_history_by_member_athena(
    idmember: "int | str",
    conn: "pyathena.Connection | None" = None,
    database: str | None = None,
    table: str | None = None,
) -> pd.DataFrame:
    """Query the Glue table for the given idmember.
       Returns DataFrame with columns:
         idclient, idcompany, idmember, idaccount,
         category_id, category_name, period_yyyymm, monthly_total
       Empty DataFrame (with the same column schema) if member has no rows.
       Raises AthenaQueryError on connection/query failure."""

def member_exists_athena(
    idmember: "int | str",
    conn: "pyathena.Connection | None" = None,
    database: str | None = None,
    table: str | None = None,
) -> bool:
    """True iff at least one row exists for the given idmember.
       Raises AthenaQueryError on failure."""
```

```python
# src/api/router.py — modified SuggestionItem (D4 clean break)
class SuggestionItem(BaseModel):
    category_id: str           # NEW (required)
    category_name: str         # NEW (required)
    suggested_amount: Optional[float]
    confidence: Optional[str]
    basis: Optional[BasisDetail]
    amount_by_month: Optional[dict[str, Optional[float]]]
    # NOTE: defaultcategory REMOVED (D4 — clean break, no alias)
```

## Data contracts

### Glue table — `dlh_gold_dough_dev.smart_budget_transactions` (read-only)

| Field | Type | Presence | Source | Missing behavior | Transformation |
|---|---|---|---|---|---|
| `idclient` | string | required | Glue | drop row + warn | pass through |
| `idcompany` | string | required | Glue | drop row + warn | pass through |
| `idmember` | string/int | required | Glue (filter key) | n/a (filtered) | cast to str on output |
| `idaccount` | string | required | Glue | drop row + warn | pass through |
| `category_id` | string | required | Glue | drop row + warn | cast to str |
| `category_name` | string | required | Glue | drop row + warn | pass through |
| `type_category` | string | optional | Glue | ignored (D2) | not projected |
| `txn_month` | string `YYYY-MM` | required | Glue | drop row + warn | `str[:7]` → `period_yyyymm` |
| `total_amount` | float/decimal | required | Glue | drop row + warn | cast to float → `monthly_total`; clamp `<0` to 0 |
| `year`, `month` | int | optional | Glue | ignored | not projected |

### `SuggestionItem` — fields touched by D4

| Field | Type | Presence | Source | Missing behavior | Transformation |
|---|---|---|---|---|---|
| ~~`defaultcategory`~~ | — | **REMOVED** | — | — | dropped per D4 |
| `category_id` | string | **required** | DataFrame column `category_id` | row excluded from response | cast to str |
| `category_name` | string | **required** | DataFrame column `category_name` | row excluded from response | cast to str |

## Tasks (TDD)

### Phase 0 — Setup

- [ ] **T0.1** — Ensure branch `DATA-1275` from latest `main`.

- [ ] **T0.2** — Add `pyathena>=3.0,<4` to `requirements.txt` (version pin matches `blossom-ml-safe-txns/endpoint/requirements.txt`). Run `pip install -r requirements.txt`.
  - Verify: `python -c "import pyathena; print(pyathena.__version__)"` prints a 3.x version.

- [ ] **T0.3** — Verify SDK methods exist on installed `pyathena`:
  - `python -c "from pyathena import connect; print(callable(connect))"` → `True`
  - Confirm `pd.read_sql` accepts a pyathena connection (PEP 249).
  - **If any name differs, STOP and write `proposal-update.md`.**

### Phase 1 — Athena loader

- [ ] **T1.1** — Create `src/smart_budget/athena_loader.py` with `AthenaQueryError` and `_get_connection()`. Env: `ATHENA_S3_STAGING_DIR` (required), `ATHENA_REGION_NAME` (default `us-east-2`). Cache result in module-level `_CONN`.

  **Test contracts** (`tests/unit/test_athena_loader.py`):
  - `test_get_connection_uses_env_vars` — sets envs, mocks `pyathena.connect`; expects exact kwargs.
  - `test_get_connection_caches_result` — two calls → `connect` invoked once.
  - `test_get_connection_missing_staging_dir_raises` — env unset → `AthenaQueryError` mentioning `ATHENA_S3_STAGING_DIR`.

- [ ] **T1.2** — Implement `load_history_by_member_athena`.

  Query:
  ```sql
  SELECT idclient, idcompany, idmember, idaccount,
         category_id, category_name, txn_month, total_amount
  FROM <database>.<table>
  WHERE idmember = %(idmember)s
  ```
  Use `pd.read_sql(sql, conn, params={"idmember": str(idmember)})`. Post-read:
  - `df['period_yyyymm'] = df['txn_month'].astype(str).str[:7]`
  - `df['monthly_total'] = pd.to_numeric(df['total_amount'], errors='coerce').fillna(0.0).clip(lower=0.0)`
  - `df['category_id'] = df['category_id'].astype(str)`
  - `df['category_name'] = df['category_name'].astype(str)`
  - `df['idmember'] = df['idmember'].astype(str)`
  - Return `df[['idclient','idcompany','idmember','idaccount','category_id','category_name','period_yyyymm','monthly_total']]`
  - Wrap exceptions: `raise AthenaQueryError(...) from e`. Log `smart_budget.athena.error` / `.done` with `idmember`, `rows`, `duration_ms`. Never log `total_amount`.
  - Defaults: `database = os.getenv("ATHENA_DATABASE", "dlh_gold_dough_dev")`, `table = os.getenv("ATHENA_TABLE", "smart_budget_transactions")`.

  **Test contracts:**
  - `test_load_history_happy_path` — mock returns rows; expect 8 columns exactly, `period_yyyymm` YYYY-MM, `monthly_total` float.
  - `test_load_history_empty` — mock returns empty DF; expect empty DF with the 8-column schema.
  - `test_load_history_param_binding_safe` — idmember with quotes; expect `pd.read_sql` called with `params={"idmember": "<raw>"}` (no interpolation).
  - `test_load_history_clamps_negative_total` — `total_amount=-50` → `monthly_total=0.0`.
  - `test_load_history_uses_env_db_table` — set `ATHENA_DATABASE=foo`, `ATHENA_TABLE=bar`; expect query contains `foo.bar`.
  - `test_load_history_wraps_exception` — mock raises `RuntimeError`; expect `AthenaQueryError`, original chained.

- [ ] **T1.3** — Implement `member_exists_athena`. Query: `SELECT 1 FROM <db>.<table> WHERE idmember = %(idmember)s LIMIT 1`. True iff result has ≥1 row.

  **Test contracts:**
  - `test_member_exists_true` / `_false` / `_wraps_exception`.

### Phase 2 — Pipeline rename (D4 clean break)

- [ ] **T2.1** — Modify `src/smart_budget/aggregator.py`: replace every reference to `idcategory` → `category_id` and `defaultcategory` → `category_name` (groupby keys, column selections, return shape).

  **Test contracts:** existing aggregator tests pass with renamed columns (helper fixtures updated).

- [ ] **T2.2** — Modify `src/smart_budget/model.py`: same rename. The output of `compute_budget_suggestions` now carries `category_id` and `category_name` instead of `idcategory`/`defaultcategory`.

  **Test contracts:** existing model tests pass with renamed columns.

### Phase 3 — Router data-source swap

- [ ] **T3.1** — Modify `src/api/router.py`:

  1. Imports — replace:
     ```
     from smart_budget.loader import member_exists, load_history_by_member
     ```
     with:
     ```
     from smart_budget.athena_loader import (
         AthenaQueryError,
         load_history_by_member_athena,
         member_exists_athena,
     )
     ```
  2. `SuggestionItem` — remove `defaultcategory`. Add `category_id: str` and `category_name: str` as required fields (no `Optional`, no default).
  3. Handler body — substitute the calls:
     - `member_exists(...)` → `member_exists_athena(idmember=idmember_val)`
     - `load_history_by_member(...)` → `load_history_by_member_athena(idmember=idmember_val)`
     - Rest of the pipeline (`apply_gating`, `compute_budget_suggestions(method='wma', treatment='B', lookback=3)`, response build) **remains in the router** — no extraction to a new module.
  4. Wrap the loader/exists calls in try/except for `AthenaQueryError`:
     ```python
     except AthenaQueryError as e:
         log.error("smart_budget.suggestion.athena_error", error=str(e))
         raise HTTPException(status_code=503, detail="datalake temporarily unavailable")
     ```
  5. Remove `_DATA_PATH` references inside the handler (CSV path no longer used). Module-level `_DATA_PATH` constant may remain only if other handlers use it; otherwise delete.
  6. The `IdMember` Enum and the hardcoded member list stay as-is (out of scope per dev clarification).

  **Test contracts** (`tests/unit/test_api.py`):
  - `TC-API-10_response_includes_category_id_and_name` — mock `athena_loader.load_history_by_member_athena` returning a DataFrame with `category_id="42"`, `category_name="Groceries"`; expect those values in JSON response.
  - `TC-API-11_athena_error_returns_503` — mock `load_history_by_member_athena` raises `AthenaQueryError("timeout")`; expect 503 + `{"detail":"datalake temporarily unavailable"}`.
  - `TC-API-12_no_defaultcategory_in_response` — successful response JSON must NOT contain the key `defaultcategory` (D4 verification).

### Phase 4 — SageMaker: data fetched live at inference time (KEY change)

This is the architectural core of the ticket per dev clarification: the deployed SageMaker endpoint stops carrying data inside `model.tar.gz` and instead queries Athena live, per request, for the requested `idmember`.

- [ ] **T5.1** — Modify `src/sagemaker/requirements.txt`: add `pyathena>=3.0,<4` (the inference container must have the SDK installed; pin matches `blossom-ml-safe-txns/endpoint/requirements.txt`).

  **Test contract:** `grep '^pyathena' src/sagemaker/requirements.txt` returns 1 line.

- [ ] **T5.2** — Modify `src/sagemaker/inference.py`:

  1. Remove constant `_DATA_CSV = "smart_budget_data.csv"`.
  2. In `predict_fn`:
     - Replace imports:
       ```
       from smart_budget.loader import load_history_by_member, member_exists
       ```
       with:
       ```
       from smart_budget.athena_loader import (
           AthenaQueryError,
           load_history_by_member_athena,
           member_exists_athena,
       )
       ```
     - Delete `base_dir = Path(model) / "data"` (no local data anymore). Keep the `reference_date` line standalone (gotcha in `src/sagemaker/CLAUDE.md`).
     - Substitute calls:
       - `load_history_by_member(idmember, base_dir, csv_name=_DATA_CSV)` → `load_history_by_member_athena(idmember=idmember)`
       - `member_exists(idmember, base_dir, csv_name=_DATA_CSV)` → `member_exists_athena(idmember=idmember)`
     - Wrap both calls in try/except for `AthenaQueryError`; re-raise as `ValueError("datalake temporarily unavailable")` so SageMaker surfaces a `ModelError` (the runtime contract upstream of `output_fn`).
  3. Update docstrings to reflect: "data is fetched live from Athena per request — not from a bundled CSV".

  **Test contracts** (`tests/unit/test_inference.py`):
  - `TC-T5.7_predict_fn_calls_athena_loader_not_csv` — patch `smart_budget.athena_loader.load_history_by_member_athena` and `smart_budget.athena_loader.member_exists_athena`; assert they are invoked. Assert `smart_budget.loader.load_history_by_member` is NOT invoked (use a spy/mock).
  - `TC-T5.8_predict_fn_wraps_athena_error` — mock loader raises `AthenaQueryError("timeout")`; expect `ValueError` with text `datalake temporarily unavailable`.
  - `TC-T5.9_no_local_csv_read` — ensure the modified `predict_fn` does NOT touch the filesystem under `model_dir / "data"` (no `Path.exists`, no `read_csv` of fixtures).
  - Existing TC-T5.1..T5.6 are updated to mock the Athena loader instead of building CSV fixtures.

- [ ] **T5.3** — Modify `notebooks/smart_budget_sagemaker_endpoint.ipynb`:

  Use a programmatic edit (load JSON, mutate cells, write back) so the diff is grep-able. Required changes:

  1. **Cell 0 (markdown)** — update the table row that currently says "Empaquetar y subir `model.tar.gz`" so its description notes "(sin CSV — datos se consultan de Athena en tiempo de inferencia)".
  2. **Cell 4 (code)** — remove the line `DATA_CSV_SRC  = f'smart_budget_db_{ENV}.csv'  # CSV del entorno`. Add:
     ```python
     ATHENA_S3_STAGING_DIR = 's3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/'
     ATHENA_REGION_NAME    = 'us-east-2'
     ATHENA_DATABASE       = 'dlh_gold_dough_dev'
     ATHENA_TABLE          = 'smart_budget_transactions'
     ```
  3. **Cell 6 (code)** — remove the block that copies `DATA_DIR / DATA_CSV_SRC` into the staging dir as `smart_budget_data.csv`. The staging dir should contain ONLY the `smart_budget/` package (plus any non-data files). Add a comment: `# NOTE: ningún CSV se empaca — los datos se leen de Athena en cada invocación.`
  4. **Cell 8 (code)** — replace the `SKLearnModel(...)` constructor to pass an `env` dict:
     ```python
     sk_model = SKLearnModel(
         model_data=S3_URI,
         role=role,
         entry_point='inference.py',
         source_dir=str(REPO_ROOT / 'src' / 'sagemaker'),
         framework_version='1.2-1',
         sagemaker_session=sagemaker_session,
         env={
             'ATHENA_S3_STAGING_DIR': ATHENA_S3_STAGING_DIR,
             'ATHENA_REGION_NAME':    ATHENA_REGION_NAME,
             'ATHENA_DATABASE':       ATHENA_DATABASE,
             'ATHENA_TABLE':          ATHENA_TABLE,
         },
     )
     ```
  5. Add a new markdown cell after Cell 1 (Step 0) documenting the IAM prerequisite: the SageMaker **execution role** must have `athena:StartQueryExecution`, `athena:GetQueryResults`, `athena:GetQueryExecution`, `glue:GetTable`, `glue:GetDatabase`, and `s3:GetObject`/`PutObject`/`ListBucket` on the staging bucket and the Glue table. If permissions are missing, the endpoint will return `ModelError` on first invocation.

  **Test contracts** — programmatic notebook checks (run as part of V11):
  - `notebook_has_no_data_csv_packaging` — JSON-load the notebook; assert no cell source contains `DATA_CSV_SRC` or `smart_budget_data.csv`.
  - `notebook_has_athena_env_vars` — assert at least one cell contains all four strings: `ATHENA_S3_STAGING_DIR`, `ATHENA_REGION_NAME`, `ATHENA_DATABASE`, `ATHENA_TABLE`.
  - `notebook_sklearn_model_passes_env` — assert the `SKLearnModel(` constructor cell contains `env=` and references `ATHENA_S3_STAGING_DIR`.
  - `notebook_documents_iam_requirements` — assert a markdown cell contains both `athena:StartQueryExecution` and `execution role` (case-insensitive).

### Phase 5 — Test refresh

- [ ] **T6.1** — In `tests/unit/test_api.py`, find every `patch("...load_history_by_member")` and `patch("...member_exists")`; replace with patches on `smart_budget.athena_loader.load_history_by_member_athena` and `smart_budget.athena_loader.member_exists_athena` (or on the names as re-imported in `src.api.router`). Update `_make_history_df` helper to emit columns `category_id`, `category_name` (drop `idcategory`, `defaultcategory`).

  **Test contracts:** all existing TC-API-1..9 pass with new mock targets and renamed helper columns.

### TDD rule

Per task: write tests from contracts → RED → minimal impl → GREEN → refactor. Commit pattern: `test(DATA-1275): tests for T<N>` then `feat(DATA-1275): implement T<N>`. **No implementation without a RED test.**

## Mandatory verification steps

- [ ] **V1** — `pytest tests/unit/test_athena_loader.py -v` — all pass.
- [ ] **V2** — `pytest tests/unit/test_api.py -v` — all pass incl. TC-API-10/11/12.
- [ ] **V3** — `pytest tests/ -v --cov=src/smart_budget --cov-report=term-missing` — all pass; coverage ≥ 90% on `athena_loader.py`.
- [ ] **V4** — `ruff check src/ tests/` — zero errors.
- [ ] **V5** — `black --check src/ tests/` — zero diffs (line 100).
- [ ] **V6** — `grep -r "defaultcategory\|idcategory" src/ tests/` returns ZERO matches (D4 clean break verified).
- [ ] **V7** — `grep -r "load_history_by_member_athena\|member_exists_athena" src/api/router.py` returns ≥ 2 lines.
- [ ] **V8** — `grep "pyathena" requirements.txt` returns 1 line.
- [ ] **V9** — Import smoke: `python -c "from src.api.router import router; print('ok')"` prints `ok`.
- [ ] **V10** — `pytest tests/unit/test_inference.py -v` — all pass incl. TC-T5.7/T5.8/T5.9.
- [ ] **V11** — Notebook structural checks (run via `python -c` snippet that JSON-loads the notebook):
  - No cell source mentions `DATA_CSV_SRC` or `smart_budget_data.csv`.
  - At least one cell contains all four env-var names (`ATHENA_S3_STAGING_DIR`, `ATHENA_REGION_NAME`, `ATHENA_DATABASE`, `ATHENA_TABLE`).
  - The `SKLearnModel(` constructor cell contains `env=` referencing `ATHENA_S3_STAGING_DIR`.
  - A markdown cell documents the IAM execution-role prerequisite (matches `athena:StartQueryExecution` and `execution role`).
- [ ] **V12** — `grep -n '_DATA_CSV\|smart_budget_data.csv\|csv_name=' src/sagemaker/inference.py` returns ZERO matches.
- [ ] **V13** — `grep '^pyathena' src/sagemaker/requirements.txt` returns 1 line.

## Success criterion

- All files in manifest match the Action column.
- All signatures present with exact shape.
- All test contracts pass.
- V1–V13 all green.
- `category_id` and `category_name` are required `str` fields in `SuggestionItem`.
- `defaultcategory` and `idcategory` appear nowhere in `src/` or `tests/` (V6).
- The FastAPI handler reads from Athena (no CSV path).
- `src/sagemaker/inference.py` reads from Athena (no `_DATA_CSV`, no `csv_name=`).
- The notebook no longer packages any CSV into `model.tar.gz` and passes Athena env vars to `SKLearnModel`.

## Proposal update protocol

STOP and write `changes/DATA-1275/proposal-update.md` if:
- `pyathena` method names differ (T0.3).
- Glue table columns don't match the assumed schema on first real query.
- Renaming `idcategory`/`defaultcategory` reveals a downstream consumer not in this manifest (e.g., a script under `scripts/` that imports from `aggregator.py`/`model.py`).
- The SageMaker container image (`sklearn:1.2-1`, Python 3.9) cannot install `pyathena>=3.0,<4` due to dependency conflicts (T5.1) — dev confirmed Python 3.9 supports `pyathena>=3.0.0` and `blossom-ml-safe-txns` uses the same pin successfully in a similar SageMaker context, so this risk is low.
- The SageMaker execution role cannot be granted Athena/Glue/S3 permissions in time (T5.3) — flag for infra team handoff.

---

## Execution Report

*(Filled in by the `blossom-implementer` subagent as it executes the spec.)*

### Task status

- [ ] T0.1, [ ] T0.2, [ ] T0.3
- [ ] T1.1, [ ] T1.2, [ ] T1.3
- [ ] T2.1, [ ] T2.2
- [ ] T3.1
- [ ] T5.1, [ ] T5.2, [ ] T5.3
- [ ] T6.1

### Verification status

- [ ] V1, [ ] V2, [ ] V3, [ ] V4, [ ] V5, [ ] V6, [ ] V7, [ ] V8, [ ] V9, [ ] V10, [ ] V11, [ ] V12, [ ] V13

### Iterations

### Proposal updates

### Final report
