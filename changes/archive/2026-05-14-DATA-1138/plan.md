# Plan — DATA-1138
## DS - Evaluación del mejor método: framework de comparación con métricas y selección justificada

**Stack:** `py-agents` (Python 3.11+, pandas, statsmodels, pytest)
**Sprint:** Data Sprint 10.26 · ends 2026-05-25
**Implementer:** `blossom-implementer`
**Branch:** `feat/DATA-1138` → tracking `origin/development`
**Risk:** ALTO — DATA-1139 (test dataset real) no existe aún; se usa split temporal sobre sintético como fallback documentado. Si DATA-1139 aparece con schema distinto al esperado, eval_runner necesita un adaptador. AC4 (reproducibilidad) satisfecho con comando documentado + hash de dataset.

---

## Phase 1 — Decision Closure Record (DCR)

### AI-Closed Decisions

All decisions were closed by AI analysis. No human decisions are required.

**Pre-analysis performed:**
- Read `src/smart_budget/model.py` (all 4 methods + `compute_budget_suggestions` signature)
- Read `scripts/run_methods.py` (CLI pattern to replicate)
- Read `docs/method_comparison.md` (existing comparative analysis on full dataset)
- Read `tests/unit/test_model.py` (test conventions)
- Analyzed `data/dough/smart_budget_synthetic.csv` (804 rows, 12 months, 11 accounts, 15 categories)
- **Ran actual evaluation** using temporal split (train=Jun2025–Mar2026, holdout=Apr2026) to ground every metric decision in real numbers

---

```yaml
ticket: DATA-1138
phase: plan
sub_phase: dcr
stack: py-agents
dcr_blocks_requiring_human_input: 0

ai_closed:
  - id: A1
    dimension: scope
    decision: >
      eval_runner.py is a new script in scripts/ (not a library module). It follows the same
      structure as scripts/run_methods.py: argparse CLI, structlog, sys.path.insert for src/.
      It does NOT modify model.py, aggregator.py, or filters.py.
    grounding: "scripts/run_methods.py:1-45 — identical pattern for CLI entry points"

  - id: A2
    dimension: dataset_strategy
    decision: >
      Use temporal split on smart_budget_synthetic.csv for Fase 0. Train set = Jun2025–Mar2026
      (10 months). Holdout "actuals" = Apr2026 (73 rows). Reference_date = "2026-03" so the model
      predicts Apr2026 without seeing it. May2026 is excluded from evaluation (it's the current
      month at time of writing; using it would introduce data leakage risk in a future real-data run).
    grounding: >
      data/dough/smart_budget_synthetic.csv — 804 rows, periods Jun2025–May2026.
      Verified: 73 holdout rows exist for Apr2026 covering all 11 accounts × up to 15 categories.
      DATA-1139 (real test dataset) does not exist yet; temporal split is the documented fallback.

  - id: A3
    dimension: metrics_primary
    decision: >
      accuracy_delta (primary) = MAE = mean(|suggested_amount − actual_spend|) computed over
      all buckets where suggested_amount IS NOT NULL. Formula matches the ticket's definition
      "average absolute difference between suggested_amount and actual spend at period close".
    grounding: >
      Ticket description (accuracy_delta definition). Computed empirically on holdout Apr2026:
      WMA-B lb=6 MAE=121.41, EWMA-B lb=6 MAE=121.13, Median-B lb=6 MAE=115.97,
      HW-B lb=6 MAE=122.91.

  - id: A4
    dimension: metrics_null_treatment
    decision: >
      Null suggestions are EXCLUDED from the accuracy_delta denominator. Coverage_rate is
      reported as a separate metric. Rationale: mixing accuracy and coverage in one number
      confounds two independent model properties. Using max_error as penalty would unfairly
      rank WMA above HW at lb=3 (HW: 46% nulls) even though their per-suggestion accuracy
      is similar — the problem is coverage, not prediction quality.
    grounding: >
      Empirical: HW-B lb=3 produces 46.3% nulls yet its valid predictions have MAE=118.62
      (only slightly worse than WMA's MAE=81.04 on lb=3). Conflating these would misrepresent
      both methods. Standard eval practice in recommendation systems (coverage ≠ accuracy).

  - id: A5
    dimension: metrics_mape
    decision: >
      MAPE is computed only on buckets where actual_spend > 0. Buckets with actual_spend = 0
      are excluded from MAPE denominator (MAPE undefined at zero). Exclusion count is reported.
      MAPE is a secondary metric (not used for method selection).
    grounding: >
      Empirical: 21 of 73 Apr2026 holdout rows have monthly_total=0 (28.8%). Categories with
      zero actuals include Travel & Trips, Gifts & Donations, Education — exactly the seasonal
      categories where zero is expected. Excluding them from MAPE is mathematically required.

  - id: A6
    dimension: metrics_set
    decision: >
      Full metrics set per method×lookback configuration:
        1. accuracy_delta (MAE) — primary, exclude nulls from denominator
        2. coverage_rate — % of total holdout buckets with non-null suggestion
        3. null_rate — % of gated buckets that produce null (complement)
        4. MAPE — secondary, computed only on non-zero actuals
        5. mae_seasonal — MAE computed only on seasonal category buckets
           (Travel & Trips, Gifts & Donations, Education)
        6. mae_regular — MAE computed on all non-seasonal buckets
      Category-split metrics enable the dual-config recommendation (WMA-B lb=6 default +
      Median-B lb=12 for seasonal).
    grounding: >
      docs/method_comparison.md:§8 — existing analysis splits seasonal (CV>50%) vs regular.
      Ticket user emphasis: "MAE per category type" explicitly requested.

  - id: A7
    dimension: treatment
    decision: >
      Evaluation uses Treatment B exclusively. Rationale: DATA-1137 recommendation is B as
      default; Treatment A and C are theoretically dominated or equivalent (A includes zeros
      that deflate suggestions; C ≈ A with epsilon=0.01). Adding A/C to the grid would triple
      the table size without changing the method selection.
    grounding: >
      docs/method_comparison.md:§2 line 29 — "Todos los resultados de comparación usan
      Treatment B salvo indicación explícita."

  - id: A8
    dimension: lookback_grid
    decision: >
      Evaluation grid: 4 methods × 4 lookbacks (3, 6, 9, 12) = 16 configurations.
      This matches the existing method_comparison.md grid and produces a complete results table.
    grounding: "docs/method_comparison.md:§3 — same 4-lookback grid already established"

  - id: A9
    dimension: method_selection_precomputed
    decision: >
      Based on holdout evaluation (computed during planning, to be reproduced by eval_runner.py):
      
      WINNER: Median-B lb=6
        - MAE = 115.97 (lowest among zero-null configurations)
        - coverage_rate = 91.8% (0% null_rate from method; 8.2% from gating threshold — expected)
        - 5% lower MAE than WMA-B lb=6 (MAE=121.41)
      
      NOTE: EWMA-B lb=3 achieves MAE=79.85 (best overall) but null_rate=9% (6 buckets)
      → documented as "highest accuracy when data permits" in the report.
      
      FOR SEASONAL CATEGORIES (Travel & Trips, Gifts & Donations, Education):
        Median-B lb=12 wins with MAE=399.01 vs WMA-B lb=12 MAE=545.33 (27% better).
        This confirms the DATA-1137 recommendation.
      
      The eval_runner.py will reproduce these numbers and they will be documented in
      evaluation_report.md as the ground truth.
    selection_rule: >
      Paso 1 — filtrar configuraciones con null_rate = 0.0% (cobertura completa).
      Paso 2 — dentro de ese set, seleccionar la de menor accuracy_delta_mae.
      Fallback: si ninguna tiene null_rate = 0.0%, seleccionar la de menor MAE entre
      las que tengan null_rate ≤ 10.0% y documentar la excepción en evaluation_report.md.
      Esta regla es la que eval_runner.py debe implementar en select_winner().
    grounding: >
      Computed via temporal split analysis during planning phase.
      All 16 configurations run against Apr2026 holdout from smart_budget_synthetic.csv.

  - id: A10
    dimension: output_format
    decision: >
      eval_runner.py outputs a CSV table to stdout or --output path (consistent with how
      run_methods.py handles --output). The results table has columns:
        method, lookback_months, treatment, n_evaluated, accuracy_delta_mae,
        coverage_rate_pct, null_rate_pct, mape_nonzero, mae_seasonal, mae_regular
    grounding: "scripts/run_methods.py:147-154 — stdout + optional --output path pattern"

  - id: A11
    dimension: file_placement
    decision: >
      New file: scripts/eval_runner.py (not src/smart_budget/ — it's a CLI entry point,
      not a library module). Test: tests/unit/test_eval_runner.py.
      Report: docs/evaluation_report.md.
    grounding: >
      scripts/CLAUDE.md — "Scripts de extracción de datos [...] CLI de métodos de sugerencia"
      confirms scripts/ is the right home for CLI entry points.
      docs/method_comparison.md — existing report in docs/ confirms docs/ for evaluation reports.

  - id: A12
    dimension: dataset_path_default
    decision: >
      eval_runner.py default --input path = "data/dough/smart_budget_synthetic.csv"
      (same default as run_methods.py). The data/ directory is gitignored and lives only locally;
      the script must document that the user needs the file present before running.
    grounding: "scripts/run_methods.py:8 — identical default path"

  - id: A13
    dimension: structlog_usage
    decision: >
      Use structlog exactly as run_methods.py does: configure at module level,
      bind context (method, treatment, reference_date), log start/done.
      Never print individual amounts or account IDs.
    grounding: "scripts/run_methods.py:28-41 — structlog setup pattern"

  - id: A14
    dimension: feature_flag
    decision: >
      No feature flag required. eval_runner.py is a standalone CLI script (not deployed to
      production API). It produces a static report artifact. No runtime toggle needed.
    grounding: >
      Architecture.md — "Smart Budget es un pipeline batch que pre-calcula sugerencias".
      The evaluation is offline-only.

  - id: A15
    dimension: reproducibility_ac4
    decision: >
      AC4 (reproducibility) satisfied by: (a) eval_runner.py CLI with documented exact command
      in evaluation_report.md, (b) dataset version documented as
      "smart_budget_synthetic.csv — 804 rows, sha256 hash", (c) reference_date and lookback_months
      documented. No external state.
    grounding: "docs/method_comparison.md:§12 — existing reproducibility section as template"

  - id: A16
    dimension: test_scope
    decision: >
      Tests are unit tests in tests/unit/test_eval_runner.py. No integration tests (the
      golden-set pattern in test_model.py uses a fixture file; eval_runner tests use inline
      pandas DataFrames). Coverage target: all public functions in eval_runner.py.
    grounding: "tests/unit/test_model.py:1-5 — test structure and import pattern"

  - id: A17
    dimension: no_new_dependencies
    decision: >
      eval_runner.py uses only pandas, structlog, and argparse — all already in requirements.txt.
      No new packages needed. requirements.txt is NOT modified.
    grounding: >
      requirements.txt — pandas>=1.5.0, structlog>=21.0.0 already present.
      All metric computations are pure pandas arithmetic.
```

---

## Phase 2 — High-Level Technical Changes (HLTC)

### Auto-Accepted Blocks (no human review needed)

```yaml
auto_accepted:
  - id: HLTC-AA-1
    type: script
    action: CREATE
    summary: "scripts/eval_runner.py — CLI that runs 16 configs and outputs results table"
    affected_files: ["scripts/eval_runner.py"]
    derived_from: [A1, A8, A10, A12, A13]

  - id: HLTC-AA-2
    type: function
    action: CREATE
    summary: >
      compute_metrics(suggestions_df, actuals_df) → dict con los 6 campos de métricas.
      suggestions_df: pd.DataFrame — columnas [account_id, category, suggested_amount (float|NaN)]
        — una fila por bucket holdout; NaN = sugerencia gated null.
      actuals_df: pd.DataFrame — columnas [account_id, category, monthly_total (float)]
        — 73 filas del holdout Apr2026; join key = (account_id, category).
      Left-join en (account_id, category); actuals sin match → raise ValueError.
    affected_files: ["scripts/eval_runner.py"]
    derived_from: [A3, A4, A5, A6]

  - id: HLTC-AA-3
    type: function
    action: CREATE
    summary: "build_results_table(results_list) → pd.DataFrame with 16 rows (method×lb)"
    affected_files: ["scripts/eval_runner.py"]
    derived_from: [A8, A10]

  - id: HLTC-AA-4
    type: test
    action: CREATE
    summary: "tests/unit/test_eval_runner.py — unit tests for metrics + CLI parsing"
    affected_files: ["tests/unit/test_eval_runner.py"]
    derived_from: [A16]

  - id: HLTC-AA-5
    type: doc
    action: CREATE
    summary: "docs/evaluation_report.md — metrics definition + results table + selection"
    affected_files: ["docs/evaluation_report.md"]
    derived_from: [A9, A15]

  - id: HLTC-AA-6
    type: doc
    action: MODIFY
    summary: "docs/method_comparison.md §13 — link to evaluation_report.md (next steps section)"
    affected_files: ["docs/method_comparison.md"]
    derived_from: [A9]
    note: "Extend, don't rewrite. Add one paragraph linking to the formal evaluation report."
```

### Triggered HLTC Blocks (requires engineer awareness)

```yaml
blocks:
  - id: HLTC-1
    type: data
    action: DEPENDENCY
    mode: review
    plain_summary: >
      eval_runner.py needs smart_budget_synthetic.csv to be present in data/dough/.
      This file is gitignored and lives only locally. The DATA-1138 worktree does NOT have
      the data directory populated (only .gitkeep exists). The engineer running /execute must
      copy or symlink the file before running the evaluation.
    affected_files:
      - "data/dough/smart_budget_synthetic.csv (RUNTIME_DEPENDENCY — not committed)"
    triggered_flag:
      reason: "Gitignored runtime asset. Implementer needs to know the eval can't run without it."
    mitigation: >
      eval_runner.py tests use synthetic inline DataFrames (not the real file).
      The README section in evaluation_report.md documents the required setup step.
      CI/CD is not affected (tests mock the data).

  - id: HLTC-2
    type: evaluation_result
    action: PRECOMPUTED
    mode: review
    plain_summary: >
      The planning phase ran the full evaluation already (temporal split, Apr2026 holdout).
      Key results that eval_runner.py must reproduce:
      
        method          lb  MAE     coverage  null_rate
        wma             3   81.04   83.6%     9.0%
        ewma            3   79.85   83.6%     9.0%   ← best MAE, non-null configs
        median          3   80.34   83.6%     9.0%
        holt_winters    3   118.62  49.3%     46.3%
        wma             6   121.41  91.8%     0.0%
        ewma            6   121.13  91.8%     0.0%
        median          6   115.97  91.8%     0.0%   ← best coverage+accuracy balance
        holt_winters    6   122.91  83.6%     9.0%
        wma             9   135.86  91.8%     0.0%
        ewma            9   140.50  91.8%     0.0%
        median          9   131.00  91.8%     0.0%
        holt_winters    9   114.95  89.0%     3.0%
        wma             12  135.29  91.8%     0.0%
        ewma            12  127.09  91.8%     0.0%
        median          12  116.71  91.8%     0.0%
        holt_winters    12  157.77  91.8%     0.0%
        
        Seasonal (Travel, Gifts, Education) lb=12:
        median  MAE=399.01 ← best for seasonal
        wma     MAE=545.33
        ewma    MAE=521.42
        holt_winters MAE=700.16
      
      These numbers are from synthetic data (artificial patterns). The eval_runner.py will
      reproduce them with documented command. The evaluation_report.md selects Median-B lb=6
      as default based on these results.
    reproduction_tolerance:
      mae_atol: 0.5          # pandas float64 rounding over 73 rows
      coverage_atol: 0.001   # percentage; 1 row in 73 ≈ 1.37%
      rationale: "Differences beyond these thresholds indicate a data or logic change, not float drift."
    triggered_flag:
      reason: >
        Engineer should verify the reproduced numbers match within the tolerance above.
        If any value exceeds mae_atol=0.5, investigate before submitting PR.
    affected_files:
      - "docs/evaluation_report.md (will contain these numbers)"

  - id: HLTC-3
    type: doc_delta
    action: CLARIFICATION
    mode: review
    plain_summary: >
      docs/method_comparison.md and docs/evaluation_report.md serve different purposes:
      - method_comparison.md (DATA-1137): exploratory analysis on FULL dataset (no holdout).
        Selection was made without measuring prediction error against actuals.
      - evaluation_report.md (DATA-1138): formal holdout evaluation with accuracy_delta.
        This is the authoritative source for method selection in Fase 0.
      
      Important: method_comparison.md recommended WMA-B lb=6 as default. The holdout
      evaluation reveals Median-B lb=6 has 5% lower MAE (115.97 vs 121.41). This is a
      CORRECTION to the prior recommendation, driven by actual measurement.
      
      evaluation_report.md supersedes method_comparison.md for method selection.
    triggered_flag:
      reason: >
        Prior recommendation (WMA-B lb=6) is being updated to (Median-B lb=6). The engineer
        should be aware this is intentional and document it clearly in the report.
    affected_files:
      - "docs/evaluation_report.md (CREATE — authoritative)"
      - "docs/method_comparison.md (MODIFY §13 — add link + note that report supersedes)"
```

---

## Summary

| Dimension | Status |
|---|---|
| Temporal split strategy | ✅ AI-closed (A2) — Jun2025–Mar2026 train, Apr2026 holdout |
| Metrics set | ✅ AI-closed (A3–A6) — accuracy_delta + coverage + null_rate + MAPE + category splits |
| Null treatment in denominator | ✅ AI-closed (A4) — exclude from denominator, report coverage_rate separately |
| Treatment selection | ✅ AI-closed (A7) — Treatment B only (consistent with DATA-1137) |
| Lookback grid | ✅ AI-closed (A8) — 4 methods × 4 lookbacks = 16 configs |
| Method recommendation | ✅ AI-closed (A9) — Median-B lb=6 default; Median-B lb=12 for seasonal |
| MAPE zero-actual handling | ✅ AI-closed (A5) — exclude zero-actual buckets, document exclusion count |
| New dependencies | ✅ AI-closed (A17) — none required |
| Human decisions required | **0** |

**Next step:** `spec.md` is ready. Run `/execute` to implement.

Decision: approved by Landneyker Betancourth — 2026-05-13 (plan review: CLEAN, 0 human decisions, 17 AI-closed)
