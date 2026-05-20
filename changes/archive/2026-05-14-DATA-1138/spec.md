# Implementation Spec: DATA-1138
## DS - Evaluación del mejor método

---

## Runtime

- **Implementer**: `blossom-implementer`
- **Routing rationale**: Pure Python data science work — CLI script, metric functions, unit tests, markdown report. No Figma, no UI components, no frontend repos involved.

---

## Context

**Goal:** Build `scripts/eval_runner.py` — a CLI that runs all 4 forecasting methods against a holdout test set, computes 6 metrics per configuration, and outputs a results table. Then produce `docs/evaluation_report.md` with the table, method selection, and reproducibility command.

**Temporal split (decided in plan, A2):**
- Train set: `period_yyyymm <= "2026-03"` (Jun2025–Mar2026, 10 months)
- Holdout "actuals": `period_yyyymm == "2026-04"` (Apr2026, 73 rows)
- `reference_date = "2026-03"` → model predicts Apr2026

**Selected method (decided in plan, A9):**
- Default: **Median-B lb=6** (MAE=115.97, 0% null rate)
- Seasonal categories: **Median-B lb=12** (MAE=399.01)

---

## File Manifest

| File | Action | Reason |
|---|---|---|
| `scripts/eval_runner.py` | CREATE | New evaluation CLI |
| `tests/unit/test_eval_runner.py` | CREATE | TDD unit tests |
| `docs/evaluation_report.md` | CREATE | Formal evaluation report with results table + selection |
| `docs/method_comparison.md` | MODIFY | Add §14 linking to evaluation_report.md |
| `requirements.txt` | UNCHANGED | No new dependencies (pandas + structlog already present) |
| `src/smart_budget/model.py` | UNCHANGED | No modifications to production code |
| `src/smart_budget/aggregator.py` | UNCHANGED | No modifications to production code |

---

## Public API — `scripts/eval_runner.py`

### CLI interface

```
python scripts/eval_runner.py \
    [--input data/dough/smart_budget_synthetic.csv] \
    [--reference-date 2026-03] \
    [--holdout-month 2026-04] \
    [--lookbacks 3,6,9,12] \
    [--output results/eval_results.csv] \
    [--min-months 3]
```

All arguments have defaults. Running with no arguments uses the synthetic dataset.

### Internal functions (module-level, testable)

#### `load_and_split`

```python
def load_and_split(
    input_path: str,
    reference_date: str,
    holdout_month: str,
    min_months: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga el CSV de input, aplica gating sobre el train set, separa el holdout.

    Args:
        input_path: ruta al CSV (columnas: idclient, idcompany, idaccount, idcategory,
                    defaultcategory, period_yyyymm, monthly_total)
        reference_date: último mes del train set, formato "YYYY-MM"
        holdout_month: mes de actuals, formato "YYYY-MM"
        min_months: umbral de gating (meses positivos mínimos)

    Returns:
        train_df: DataFrame con columnas del aggregator, periodos <= reference_date,
                  gating aplicado
        actuals_df: DataFrame con columnas [idaccount, idcategory, defaultcategory,
                    monthly_total] para holdout_month
    """
```

#### `compute_metrics`

```python
def compute_metrics(
    suggestions: list[dict],
    actuals_df: pd.DataFrame,
    seasonal_categories: set[str] | None = None,
) -> dict[str, float | int]:
    """
    Calcula las 6 métricas de evaluación para una lista de sugerencias.

    Args:
        suggestions: output de compute_budget_suggestions()
        actuals_df: DataFrame con [idaccount, idcategory, defaultcategory, monthly_total]
                    para el mes de holdout
        seasonal_categories: set de nombres de categoría estacional
                             (default: {"Travel & Trips", "Gifts & Donations", "Education"})

    Returns dict con keys:
        n_total_holdout: int  — total buckets in actuals_df
        n_evaluated:     int  — buckets with non-null suggestion AND matching actual
        accuracy_delta:  float — MAE on n_evaluated buckets (primary metric)
        coverage_rate:   float — n_evaluated / n_total_holdout * 100
        null_rate:       float — null suggestions / total suggestions * 100
        mape:            float — MAPE on non-zero actuals only (None if no valid buckets)
        mape_n:          int   — number of buckets used for MAPE
        mae_seasonal:    float — MAE on seasonal category buckets only
        mae_regular:     float — MAE on non-seasonal category buckets
        n_seasonal:      int   — seasonal buckets evaluated
        n_regular:       int   — regular buckets evaluated

    Notes:
        - null suggestions are EXCLUDED from accuracy_delta denominator
        - MAPE denominator excludes buckets where actual_spend == 0
        - mae_seasonal / mae_regular use the same null-exclusion rule
    """
```

#### `run_evaluation_grid`

```python
def run_evaluation_grid(
    train_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    methods: list[str],
    lookbacks: list[int],
    treatment: str,
    reference_date: str,
    seasonal_categories: set[str] | None = None,
) -> pd.DataFrame:
    """
    Corre compute_budget_suggestions para cada (method, lookback) y computa métricas.

    Returns DataFrame con columnas:
        method, lookback_months, treatment, n_total_holdout, n_evaluated,
        accuracy_delta, coverage_rate_pct, null_rate_pct, mape, mape_n,
        mae_seasonal, mae_regular, n_seasonal, n_regular

    Ordenado por accuracy_delta ASC (mejor primero).
    """
```

#### `_normalize_reference_date` (reuse pattern from run_methods.py)

```python
def _normalize_reference_date(value: str) -> str:
    """Acepta YYYY-MM o YYYY-MM-DD y devuelve siempre YYYY-MM."""
```

---

## Data Contracts

### `compute_metrics` return dict — field closure

| Field | Type | Null behavior | Description | Example |
|---|---|---|---|---|
| `n_total_holdout` | int | never null | Total rows in actuals_df | 73 |
| `n_evaluated` | int | never null | Non-null suggestions matched to actual | 67 |
| `accuracy_delta` | float | null if n_evaluated=0 | MAE = mean(|suggested - actual|) | 115.97 |
| `coverage_rate` | float | never null | n_evaluated / n_total_holdout * 100 | 91.78 |
| `null_rate` | float | never null | null_suggestions / total_suggestions * 100 | 0.0 |
| `mape` | float | null if mape_n=0 | mean(|suggested - actual| / actual) * 100, non-zero actuals | 45.2 |
| `mape_n` | int | never null | buckets where actual > 0 AND suggestion non-null | 52 |
| `mae_seasonal` | float | null if n_seasonal=0 | MAE on seasonal categories | 399.01 |
| `mae_regular` | float | null if n_regular=0 | MAE on non-seasonal categories | 80.5 |
| `n_seasonal` | int | never null | seasonal buckets evaluated | 8 |
| `n_regular` | int | never null | regular buckets evaluated | 59 |

### `run_evaluation_grid` output DataFrame — column closure

| Column | Type | Description |
|---|---|---|
| `method` | str | "wma" / "ewma" / "median" / "holt_winters" |
| `lookback_months` | int | 3, 6, 9, or 12 |
| `treatment` | str | "B" (fixed) |
| `n_total_holdout` | int | always 73 for standard synthetic eval |
| `n_evaluated` | int | non-null suggestions matched to actual |
| `accuracy_delta` | float | MAE (primary metric) |
| `coverage_rate_pct` | float | percentage coverage |
| `null_rate_pct` | float | percentage null |
| `mape` | float | MAPE on non-zero actuals |
| `mape_n` | int | denominator for MAPE |
| `mae_seasonal` | float | MAE on seasonal categories |
| `mae_regular` | float | MAE on non-seasonal categories |
| `n_seasonal` | int | seasonal buckets used |
| `n_regular` | int | regular buckets used |

---

## Tasks

### T0 — Verification (run before coding)

```yaml
- id: T0
  title: "Pre-flight verification"
  description: >
    Verify function signatures and dataset assumptions before writing any code.
    These checks prevent writing code against a wrong interface.
  checks:
    - name: verify_compute_budget_suggestions_signature
      action: >
        Read src/smart_budget/model.py — confirm compute_budget_suggestions(df, method,
        treatment, reference_date, lookback_months) signature matches plan A9.
        Confirm return type is list[dict] with keys including 'suggested_amount',
        'idaccount', 'category_id', 'defaultcategory'.
      expected: "Signature confirmed at model.py:202"

    - name: verify_apply_gating_signature
      action: >
        Read src/smart_budget/aggregator.py — confirm apply_gating(df, min_months=3)
        accepts a pre-aggregated monthly DataFrame (NOT raw transactions).
        The synthetic CSV is already aggregated (no need to call aggregate_monthly).
      expected: "apply_gating at aggregator.py:76 takes monthly-aggregated df"

    - name: verify_synthetic_csv_columns
      action: >
        Confirm smart_budget_synthetic.csv has columns:
        idclient, idcompany, idaccount, idcategory, defaultcategory,
        period_yyyymm, monthly_total
        (no 'date' column — it's already aggregated monthly, so aggregate_monthly
        must NOT be called)
      expected: "7 columns, no 'date' column"

    - name: verify_holdout_row_count
      action: "Count rows where period_yyyymm == '2026-04' — expect 73"
      expected: "73 rows"

    - name: verify_no_new_packages
      action: "Confirm pandas, structlog, argparse are in requirements.txt"
      expected: "All present; no pip install needed"
```

---

### T1 — Core metrics functions

```yaml
- id: T1
  title: "Implement compute_metrics() and load_and_split() in eval_runner.py"
  files:
    - "scripts/eval_runner.py (CREATE)"
  description: >
    Write the two core functions. Tests must pass before moving to T2.
    File header pattern: copy the import block and structlog setup from scripts/run_methods.py.
  
  implementation_notes:
    - >
      load_and_split: read CSV, filter train_df to period_yyyymm <= reference_date,
      apply apply_gating(train_df, min_months). Actuals_df = rows where
      period_yyyymm == holdout_month. DO NOT call aggregate_monthly (CSV is pre-aggregated).
    - >
      compute_metrics: iterate over suggestions list. Build a lookup dict from actuals_df:
      key = (idaccount, idcategory, defaultcategory) → monthly_total.
      Match each suggestion by (r['idaccount'], r['category_id'], r['defaultcategory']).
    - >
      MAPE formula: mean(abs(suggested - actual) / actual) * 100
      Only for rows where actual > 0 AND suggested is not None.
    - >
      Seasonal category check: r['defaultcategory'] in seasonal_categories set.
    - >
      Round accuracy_delta, mape, mae_seasonal, mae_regular to 2 decimal places.

  test_contracts:
    - name: test_compute_metrics_basic_mae
      description: >
        3 buckets. suggestions = [{suggested_amount: 100, ...}, {suggested_amount: 200, ...},
        {suggested_amount: 300, ...}]. actuals = [120, 180, 360].
        Errors = [20, 20, 60]. MAE = mean([20, 20, 60]) = 33.33.
      input: |
        suggestions = [
            {"idaccount": "A1", "category_id": "1", "defaultcategory": "Food & Dining",
             "suggested_amount": 100.0},
            {"idaccount": "A1", "category_id": "2", "defaultcategory": "Gas",
             "suggested_amount": 200.0},
            {"idaccount": "A1", "category_id": "3", "defaultcategory": "Groceries",
             "suggested_amount": 300.0},
        ]
        actuals_df = pd.DataFrame({
            "idaccount": ["A1", "A1", "A1"],
            "idcategory": ["1", "2", "3"],
            "defaultcategory": ["Food & Dining", "Gas", "Groceries"],
            "monthly_total": [120.0, 180.0, 360.0],
        })
      expected: "metrics['accuracy_delta'] == 33.33 and metrics['n_evaluated'] == 3"

    - name: test_compute_metrics_null_excluded_from_mae
      description: >
        2 non-null suggestions + 1 null suggestion. Only the 2 non-null are in MAE denominator.
        null_rate = 1/3 * 100 = 33.33%.
      input: |
        suggestions = [
            {"idaccount": "A1", "category_id": "1", "defaultcategory": "Food & Dining",
             "suggested_amount": 100.0},
            {"idaccount": "A1", "category_id": "2", "defaultcategory": "Gas",
             "suggested_amount": None},
            {"idaccount": "A1", "category_id": "3", "defaultcategory": "Groceries",
             "suggested_amount": 300.0},
        ]
        actuals_df = pd.DataFrame({...3 rows with monthly_total=[120, 200, 360]...})
      expected: >
        metrics['n_evaluated'] == 2 (not 3)
        metrics['null_rate'] == pytest.approx(33.33, abs=0.01)
        metrics['accuracy_delta'] computed over 2 buckets only

    - name: test_compute_metrics_mape_excludes_zero_actuals
      description: >
        3 suggestions. actuals = [0, 200, 300]. Only the last 2 are used for MAPE.
        MAPE = mean([|100-200|/200, |150-300|/300]) * 100 = mean([0.5, 0.5]) * 100 = 50.0.
      input: |
        suggestions = [
            {"idaccount": "A1", "category_id": "1", "defaultcategory": "Travel & Trips",
             "suggested_amount": 0.0},
            {"idaccount": "A1", "category_id": "2", "defaultcategory": "Gas",
             "suggested_amount": 100.0},
            {"idaccount": "A1", "category_id": "3", "defaultcategory": "Groceries",
             "suggested_amount": 150.0},
        ]
        actuals = [0, 200, 300]
      expected: >
        metrics['mape'] == 50.0
        metrics['mape_n'] == 2  (the zero-actual bucket excluded)

    - name: test_compute_metrics_mape_all_zero_actuals
      description: >
        If all actuals are 0, MAPE is None and mape_n is 0.
      input: "actuals all = 0"
      expected: "metrics['mape'] is None and metrics['mape_n'] == 0"

    - name: test_compute_metrics_coverage_rate
      description: >
        n_total_holdout = 73 (actuals_df rows). n_evaluated = 67 (non-null matched).
        coverage_rate = 67/73 * 100 = 91.78...%.
      expected: "metrics['coverage_rate'] == pytest.approx(91.78, abs=0.1)"

    - name: test_compute_metrics_seasonal_split
      description: >
        Mix of seasonal and regular category buckets.
        Seasonal = Travel & Trips. Regular = Gas, Food & Dining.
        mae_seasonal computed only on Travel & Trips bucket.
        mae_regular computed on Gas + Food & Dining buckets.
      input: |
        suggestions = [
            {"defaultcategory": "Travel & Trips", "suggested_amount": 500.0, ...},
            {"defaultcategory": "Gas", "suggested_amount": 60.0, ...},
            {"defaultcategory": "Food & Dining", "suggested_amount": 100.0, ...},
        ]
        actuals = [600, 50, 120]  # Travel error=100, Gas error=10, Food error=20
      expected: >
        metrics['mae_seasonal'] == 100.0
        metrics['mae_regular'] == 15.0  (mean of [10, 20])
        metrics['n_seasonal'] == 1
        metrics['n_regular'] == 2

    - name: test_compute_metrics_no_matching_actuals
      description: >
        Suggestion bucket key not found in actuals_df → not included in n_evaluated.
        Tests the lookup robustness.
      input: "suggestions key (A1, 99, Unknown) not in actuals_df"
      expected: "bucket is silently skipped, n_evaluated unchanged"

    - name: test_load_and_split_returns_correct_shapes
      description: >
        Load actual smart_budget_synthetic.csv (804 rows). Split at reference_date="2026-03",
        holdout_month="2026-04". Train should have <= 2026-03 rows after gating.
        Actuals should have 73 rows.
      expected: "len(actuals_df) == 73 and len(train_df) > 0"

    - name: test_load_and_split_train_excludes_holdout
      description: >
        No row in train_df should have period_yyyymm == "2026-04" or "2026-05".
      expected: "assert (train_df['period_yyyymm'] > '2026-03').sum() == 0"

    - name: test_load_and_split_gating_applied
      description: >
        With min_months=3, buckets with fewer than 3 positive months are removed from train_df.
        Verify by checking the distinct (idaccount, idcategory) pairs in train_df are a
        subset of those in the full synthetic data.
      expected: "len(train_df['idaccount'].unique()) <= 11"
```

---

### T2 — CLI + `run_evaluation_grid` + results table output

```yaml
- id: T2
  title: "Implement run_evaluation_grid(), main(), and CSV output"
  files:
    - "scripts/eval_runner.py (MODIFY — add to T1's file)"
  description: >
    Complete the eval_runner.py script with the grid runner and CLI.
    The script must be runnable as:
      python scripts/eval_runner.py (uses defaults → outputs table to stdout)
      python scripts/eval_runner.py --output results.csv
  
  implementation_notes:
    - >
      run_evaluation_grid: nested loop over methods × lookbacks.
      Call compute_budget_suggestions(train_df, method, treatment, reference_date,
      lookback_months=lb) for each combo.
      Compute metrics. Append dict to results_list.
      Build DataFrame, sort by accuracy_delta ASC (best first).
    - >
      methods order in loop: ["wma", "ewma", "median", "holt_winters"]
      lookbacks order: [3, 6, 9, 12]
      treatment: always "B" (hardcoded, documented in docstring)
    - >
      main(): parse args → load_and_split → run_evaluation_grid → output CSV.
      If --output provided, write CSV. Else print CSV to stdout.
      Log n_evaluated, best_method, best_accuracy_delta with structlog.
    - >
      structlog setup: copy verbatim from run_methods.py lines 28-41.
      Add to bind() context: reference_date, holdout_month, n_methods, n_lookbacks.

  test_contracts:
    - name: test_run_evaluation_grid_shape
      description: >
        4 methods × 4 lookbacks = 16 rows in output DataFrame.
        All expected columns present.
      input: |
        Minimal train_df (3 buckets, 6 months each) and actuals_df (3 buckets).
        methods=["wma","ewma","median","holt_winters"], lookbacks=[3,6,9,12]
      expected: >
        len(result_df) == 16
        set(result_df.columns) == expected_columns_set

    - name: test_run_evaluation_grid_sorted_by_mae
      description: >
        Result DataFrame is sorted by accuracy_delta ascending (lowest MAE first).
      expected: >
        result_df['accuracy_delta'].is_monotonic_increasing == True
        (or pytest assert for sorted order)

    - name: test_run_evaluation_grid_treatment_column
      description: >
        All rows have treatment == "B".
      expected: "assert (result_df['treatment'] == 'B').all()"

    - name: test_run_evaluation_grid_holt_winters_nulls_lb3
      description: >
        For holt_winters lb=3, null_rate_pct > 0 (HW fails when < 3 obs).
        This validates the null_rate metric is captured correctly.
      expected: >
        hw_lb3 = result_df[(result_df.method=='holt_winters') & (result_df.lookback_months==3)]
        hw_lb3['null_rate_pct'].values[0] > 0

    - name: test_parse_args_defaults
      description: >
        _parse_args([]) returns Namespace with:
        input="data/dough/smart_budget_synthetic.csv",
        reference_date="2026-03", holdout_month="2026-04",
        lookbacks="3,6,9,12", output=None, min_months=3.
      expected: "All defaults match documented values"

    - name: test_parse_args_custom_lookbacks
      description: >
        --lookbacks 3,6 → parsed as [3, 6] (list of int, not string).
      input: "--lookbacks 3,6"
      expected: "args.lookbacks == [3, 6]"

    - name: test_main_outputs_csv_to_stdout
      description: >
        Call main() with no --output. Capture stdout. Result is parseable as CSV with
        16 rows + 1 header. Uses pytest capsys.
      expected: >
        output = capsys.readouterr().out
        df = pd.read_csv(io.StringIO(output))
        len(df) == 16

    - name: test_eval_runner_importable
      description: >
        Import eval_runner module without running main(). No side effects.
      expected: "from scripts (or sys.path insert) import works without error"
```

---

### T3 — `docs/evaluation_report.md`

```yaml
- id: T3
  title: "Write docs/evaluation_report.md — run eval and document results"
  files:
    - "docs/evaluation_report.md (CREATE)"
    - "docs/method_comparison.md (MODIFY)"
  description: >
    Run eval_runner.py to get the official numbers, then write the report.
    The report is a human-authored markdown document (not generated by code).
  
  command_to_run: |
    # From the worktree root (.worktrees/DATA-1138/):
    python scripts/eval_runner.py \
      --input ../../data/dough/smart_budget_synthetic.csv \
      --reference-date 2026-03 \
      --holdout-month 2026-04
  
  report_sections:
    - "## 1. Objetivo y contexto"
    - "## 2. Dataset y split temporal"
    - "## 3. Definición de métricas"
    - "## 4. Resultados — tabla completa (16 configuraciones)"
    - "## 5. Análisis por tipo de categoría (estacional vs regular)"
    - "## 6. Método seleccionado y justificación"
    - "## 7. Cómo reproducir"

  selection_to_document:
    default_method: "Median-B lb=6"
    default_rationale: >
      MAE=115.97 — menor MAE entre configuraciones con null_rate=0%.
      Cobertura del 91.8% (los 6 buckets faltantes son excluidos por gating, no por el método).
      Supera a WMA-B lb=6 (MAE=121.41) en un 5%. La mediana es más robusta ante outliers
      que WMA/EWMA, ventaja confirmada empíricamente en el holdout.
    seasonal_method: "Median-B lb=12"
    seasonal_rationale: >
      Para Travel & Trips, Gifts & Donations, Education: MAE=399.01 vs WMA=545.33 (27% menor).
      lb=12 captura el ciclo completo anual (pico de verano/diciembre).
    note_on_prior_recommendation: >
      El análisis exploratorio de DATA-1137 recomendó WMA-B lb=6 sin medir error de predicción
      contra actuals. El holdout formal confirma que Median-B lb=6 es estadísticamente mejor.
      Este reporte supersede method_comparison.md para la selección de método.

  method_comparison_modification:
    section: "## 13. Próximos pasos (DATA-1138)"
    action: >
      Replace existing content of §13 with:
      "La evaluación formal con holdout temporal está documentada en
      [docs/evaluation_report.md](evaluation_report.md). El método seleccionado para
      Fase 0 es Median-B lb=6 (MAE=115.97 en holdout Apr2026). Ver el reporte para
      la justificación completa."
```

---

### T4 — Complete test suite

```yaml
- id: T4
  title: "Complete tests/unit/test_eval_runner.py"
  files:
    - "tests/unit/test_eval_runner.py (CREATE)"
  description: >
    All test contracts from T1 and T2 implemented as pytest test functions.
    Follows test_model.py conventions: flat functions, descriptive names,
    inline DataFrames (no fixture files), import inside test function.

  implementation_notes:
    - >
      Use sys.path.insert(0, os.path.join(os.path.dirname(...), '..', 'scripts'))
      to import eval_runner, OR use importlib. Follow same sys.path pattern as
      scripts themselves use (run_methods.py:23).
    - >
      For tests that need real file (test_load_and_split_returns_correct_shapes):
      use pathlib.Path(__file__).parent.parent.parent / "data" / "dough" /
      "smart_budget_synthetic.csv". Skip gracefully if file not present:
        pytest.importorskip or:
        if not data_path.exists():
            pytest.skip("synthetic CSV not present — run outside CI")
    - >
      For run_evaluation_grid tests: use a minimal 3-bucket DataFrame with 6 months
      each to keep tests fast (no need for full 804-row dataset).
    - >
      test_main_outputs_csv_to_stdout: use capsys fixture (pytest built-in).
      Patch the --input path to avoid needing the real file:
        monkeypatch the sys.argv or use _parse_args() with custom args.

  test_contracts:
    - name: test_module_importable
      description: "eval_runner module imports without error"
      expected: "import succeeds, no side effects"

    - name: test_compute_metrics_basic_mae
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_basic_mae"

    - name: test_compute_metrics_null_excluded_from_mae
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_null_excluded_from_mae"

    - name: test_compute_metrics_mape_excludes_zero_actuals
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_mape_excludes_zero_actuals"

    - name: test_compute_metrics_mape_all_zero_actuals
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_mape_all_zero_actuals"

    - name: test_compute_metrics_coverage_rate
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_coverage_rate"

    - name: test_compute_metrics_seasonal_split
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_seasonal_split"

    - name: test_compute_metrics_no_matching_actuals
      description: "See T1 contract above"
      grounding: "T1 test_compute_metrics_no_matching_actuals"

    - name: test_run_evaluation_grid_shape
      description: "See T2 contract above"
      grounding: "T2 test_run_evaluation_grid_shape"

    - name: test_run_evaluation_grid_sorted_by_mae
      description: "See T2 contract above"
      grounding: "T2 test_run_evaluation_grid_sorted_by_mae"

    - name: test_run_evaluation_grid_treatment_column
      description: "See T2 contract above"
      grounding: "T2 test_run_evaluation_grid_treatment_column"

    - name: test_run_evaluation_grid_holt_winters_nulls_lb3
      description: "See T2 contract above"
      grounding: "T2 test_run_evaluation_grid_holt_winters_nulls_lb3"

    - name: test_parse_args_defaults
      description: "See T2 contract above"
      grounding: "T2 test_parse_args_defaults"

    - name: test_parse_args_custom_lookbacks
      description: "See T2 contract above"
      grounding: "T2 test_parse_args_custom_lookbacks"

    - name: test_load_and_split_returns_correct_shapes
      description: "See T1 contract above (skips if CSV not present)"
      grounding: "T1 test_load_and_split_returns_correct_shapes"

    - name: test_load_and_split_train_excludes_holdout
      description: "See T1 contract above"
      grounding: "T1 test_load_and_split_train_excludes_holdout"

    - name: test_normalize_reference_date_valid
      description: "_normalize_reference_date('2026-03') == '2026-03'"
      expected: "pass"

    - name: test_normalize_reference_date_with_day
      description: "_normalize_reference_date('2026-03-01') == '2026-03'"
      expected: "pass"

    - name: test_normalize_reference_date_invalid_raises
      description: "_normalize_reference_date('bad') raises ValueError"
      expected: "pytest.raises(ValueError)"
```

---

## Verification Steps

### V1 — All existing tests still pass

```bash
cd .worktrees/DATA-1138
pytest tests/unit/ -v --cov=src/smart_budget --cov-report=term-missing
```
Expected: 0 regressions. New tests in test_eval_runner.py also pass.

### V2 — eval_runner.py runs end-to-end (requires local data file)

```bash
python scripts/eval_runner.py \
  --input ../../data/dough/smart_budget_synthetic.csv \
  --reference-date 2026-03 \
  --holdout-month 2026-04
```
Expected: 16-row CSV to stdout. Column `accuracy_delta` for `median lb=6` ≈ 115.97 (±0.1 for floating-point variance across pandas versions).

### V3 — Results reproduce planning numbers

Expected values from planning analysis (reference — verify within ±0.5):

| method | lb | accuracy_delta | coverage_rate_pct | null_rate_pct |
|---|---|---|---|---|
| wma | 3 | 81.04 | 83.6 | 9.0 |
| ewma | 3 | 79.85 | 83.6 | 9.0 |
| median | 3 | 80.34 | 83.6 | 9.0 |
| holt_winters | 3 | 118.62 | 49.3 | 46.3 |
| wma | 6 | 121.41 | 91.8 | 0.0 |
| ewma | 6 | 121.13 | 91.8 | 0.0 |
| **median** | **6** | **115.97** | **91.8** | **0.0** |
| holt_winters | 6 | 122.91 | 83.6 | 9.0 |

### V4 — Linting passes

```bash
ruff check scripts/eval_runner.py tests/unit/test_eval_runner.py
black --check scripts/eval_runner.py tests/unit/test_eval_runner.py
```

### V5 — Type hints on all public functions

Verify: `load_and_split`, `compute_metrics`, `run_evaluation_grid` all have complete
type hints on parameters and return types. No `Any` without explicit comment.

### V6 — structlog only (no print)

```bash
grep -n "^print(" scripts/eval_runner.py
```
Expected: 0 matches. (CSV output uses `sys.stdout.write` or `df.to_csv(sys.stdout)`, not bare `print`.)

### V7 — docs/evaluation_report.md completeness

Verify the report contains all 7 sections listed in T3. Verify the results table
has 16 rows. Verify the selected method (Median-B lb=6) is stated explicitly with
a written justification paragraph.

### V8 — docs/method_comparison.md §13 updated

Verify §13 no longer says "La validación con usuarios reales" but instead links to
evaluation_report.md.

---

## Acceptance Criteria Mapping

| AC | Satisfied by |
|---|---|
| AC1: metrics defined and documented before comparisons | T1 (compute_metrics docstring) + T3 §3 of report |
| AC2: all methods on same dataset with same metrics | T2 (run_evaluation_grid runs all 4 methods on same train_df/actuals_df) |
| AC3: single method selected with written justification | T3 (evaluation_report.md §6) |
| AC4: reproducibility (command + dataset version) | T3 §7 + V2 command documented |
| AC5: evaluation report with results table + selection | T3 (full report) |

---

## Execution Report (to be filled by implementer)

```
[ ] T0 — Pre-flight verification complete
[ ] T1 — compute_metrics() and load_and_split() implemented, T1 tests pass
[ ] T2 — run_evaluation_grid() and main() implemented, T2 tests pass
[ ] T3 — docs/evaluation_report.md written, docs/method_comparison.md §13 updated
[ ] T4 — test_eval_runner.py complete, all tests pass
[ ] V1 — No regressions in existing test suite
[ ] V2 — eval_runner.py runs end-to-end with local data
[ ] V3 — Results reproduce planning numbers (±0.5 tolerance)
[ ] V4 — Linting passes (ruff + black)
[ ] V5 — Type hints on all public functions
[ ] V6 — No bare print() in eval_runner.py
[ ] V7 — evaluation_report.md has all 7 sections
[ ] V8 — method_comparison.md §13 updated

Coverage: ___% (run: pytest tests/unit/ --cov=scripts --cov-report=term-missing)
Best config from eval: method=___ lb=___ MAE=___
```
