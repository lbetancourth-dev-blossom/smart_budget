# Implementation Spec: DATA-1137

> This spec is the sole input for the implementer subagent. Every file listed here MUST exist at the end of execution. Every mandatory verification step MUST pass. Task IDs are stable — the Execution Report at the bottom is updated by the implementer as it progresses.

## Runtime

- **Implementer**: `blossom-implementer`
- **Routing rationale**: default — generic TDD, Python/pandas/statsmodels pipeline.

## Branch

- **Name**: `feat/DATA-1137`
- **Base**: `development`
- **Worktree**: `.worktrees/DATA-1137/`

## File manifest

| Action | Path | Purpose |
|---|---|---|
| MODIFY | `requirements.txt` | Agregar `statsmodels>=0.14.0` |
| CREATE | `src/smart_budget/model.py` | Módulo principal — 3 métodos × 3 treatments |
| CREATE | `scripts/run_methods.py` | CLI — ejecuta un método y emite JSON |
| MODIFY | `requirements.txt` | Agregar `pytest-cov>=4.0.0` para cobertura |
| CREATE | `tests/unit/test_model.py` | Tests TC-4.1–TC-4.8 |
| CREATE | `tests/fixtures/golden_set.csv` | Golden set WMA/A/2026-03-01 generado y commiteado |
| UNCHANGED | `src/smart_budget/aggregator.py` | Referencia — no modificar |
| UNCHANGED | `src/smart_budget/filters.py` | Referencia — no modificar |
| UNCHANGED | `tests/conftest.py` | Referencia — usar `_load_fixture()` existente |

## Function signatures

### `src/smart_budget/model.py`

```python
EPSILON_DEFAULT: float = 0.01
EWMA_SPAN_DEFAULT: int = 3

def apply_treatment(
    df: pd.DataFrame,
    treatment: str,          # "A" | "B" | "C"
    epsilon: float = EPSILON_DEFAULT,
) -> pd.DataFrame:
    """
    Aplica el tratamiento de ceros sobre la columna monthly_total.
    Recibe una copia del df PRE-treatment. Nunca modifica el df original.
    A — include_zeros: sin cambio (retorna copia).
    B — exclude_zeros: filtra filas donde monthly_total == 0.
    C — epsilon_replace: reemplaza monthly_total == 0 por epsilon.
    Raises: ValueError si treatment no está en {"A", "B", "C"}.
    """

def compute_wma(series: pd.Series) -> float:
    """
    Weighted Moving Average con pesos lineales crecientes [1, 2, ..., n] normalizados.
    Recibe una pd.Series de floats ordenados cronológicamente (índice = posición temporal).
    Retorna float redondeado a 2 decimales. Nunca negativo.
    Raises: ValueError si series está vacía.
    """

def compute_ewma(series: pd.Series, span: int = EWMA_SPAN_DEFAULT) -> float:
    """
    Exponentially Weighted Moving Average con pandas.ewm(span=span).mean().
    Retorna el último valor de la serie EWMA, redondeado a 2 decimales. Nunca negativo.
    Raises: ValueError si series está vacía.
    """

def compute_holt_winters(series: pd.Series) -> float:
    """
    Holt-Winters con ExponentialSmoothing(trend='add', seasonal=None).
    Retorna el primer forecast (1 step ahead), redondeado a 2 decimales. Nunca negativo.
    Clampea negativos a 0.0 antes de redondear.
    Raises: ValueError si series tiene menos de 3 observaciones.
    """

def compute_confidence(data_points: int) -> str:
    """
    Retorna "high" si data_points >= 6, "medium" si 3-5, "low" si == 2.
    data_points = número de meses con monthly_total > 0 en el df PRE-treatment.
    """

def build_explanation(
    months_analyzed: int,
    months_with_positive_spend: int,
    confidence: str | None,
) -> str:
    """
    Genera la explicación en lenguaje natural de la sugerencia.
    - confidence == None: "No hay datos históricos suficientes para calcular una sugerencia en esta categoría."
    - confidence == "high": f"En {months_with_positive_spend} de tus últimos {months_analyzed} meses tuviste gastos en esta categoría. Esta sugerencia tiene alta confiabilidad."
    - confidence == "medium": f"En {months_with_positive_spend} de tus últimos {months_analyzed} meses tuviste gastos en esta categoría. Esta sugerencia tiene confiabilidad media."
    - confidence == "low": f"En {months_with_positive_spend} de tus últimos {months_analyzed} meses tuviste gastos en esta categoría. Esta sugerencia está basada en pocos datos — revísala antes de confirmarla."
    Copy: neutral y descriptiva (UDAAP/CFPB). Nunca prescriptiva ni comparativa entre usuarios.
    """

def compute_budget_suggestions(
    df: pd.DataFrame,            # output de prepare_smart_budget_data()
    method: str,                 # "wma" | "ewma" | "holt_winters"
    treatment: str,              # "A" | "B" | "C"
    reference_date: str,         # "YYYY-MM-DD" — punto de corte (inclusive)
    ewma_span: int = EWMA_SPAN_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
) -> list[dict]:
    """
    Función principal. Pipeline por bucket (idaccount × idcategory × defaultcategory):
    1. Filtrar df a meses <= month(reference_date) — todos los meses del dataset hasta ese punto
    2. Extraer basis PRE-treatment: months_with_zero, months_with_positive_spend
    3. apply_treatment(df_bucket, treatment, epsilon)
    4. Si treatment=="B" y df_tratado está vacío → emitir null suggestion con reason
    5. Construir pd.Series cronológica de monthly_total para el método
    6. Llamar al método correspondiente (compute_wma / compute_ewma / compute_holt_winters)
    7. Clampear resultado a 0.0 si negativo
    8. Redondear a 2 decimales
    9. Generar `explanation` con el template definido en plan.md §JSON contract, usando confidence y months_with_positive_spend y months_analyzed
    10. Calcular confidence con data_points (count de meses con monthly_total > 0 PRE-treatment)
    11. Construir dict JSON por bucket con el contrato definido abajo
    Retorna lista de dicts (uno por bucket). Lista vacía si df está vacío.
    Raises: ValueError si method no está en {"wma", "ewma", "holt_winters"}.
    """
```

## Data contracts

### JSON — Sugerencia con monto (suggested_amount != null)

| Campo | Tipo | Presencia | Fuente | Transformación |
|---|---|---|---|---|
| `category_id` | str | required | `df.idcategory` | pass-through |
| `defaultcategory` | str | required | `df.defaultcategory` | pass-through |
| `idaccount` | str | required | `df.idaccount` | pass-through |
| `idclient` | str | required | `df.idclient` | pass-through |
| `idcompany` | str | required | `df.idcompany` | pass-through |
| `suggested_amount` | float | required | resultado del método | `round(max(0.0, value), 2)` |
| `basis.months_analyzed` | int | required | count de meses en df PRE-treatment tras filtro reference_date | count |
| `basis.months_with_zero` | int | required | count de meses donde monthly_total == 0.0 PRE-treatment | count |
| `basis.months_with_positive_spend` | int | required | count de meses donde monthly_total > 0.0 PRE-treatment | count |
| `basis.period_range` | str | required | `"{min_month} ~ {max_month}"` del df PRE-treatment | format |
| `basis.method` | str | required | valor del argumento `method` | pass-through |
| `basis.treatment` | str | required | valor del argumento `treatment` | pass-through |
| `confidence` | str | required | `compute_confidence(months_with_positive_spend)` | "high"\|"medium"\|"low" |
| `display_label` | str | required | `f"Basado en tus últimos {months_analyzed} meses"` | format |
| `explanation` | str | required | template por confidence (ver plan.md §JSON contract) | format |
| `model_version` | str | required | `"fase0-v1"` | literal |
| `reason` | str | omitido | — | no incluir si suggested_amount != null |

### JSON — Sin sugerencia (suggested_amount = null)

Aplica cuando: (a) treatment B excluye todos los meses del bucket, o (b) gating no pasó (< 3 meses con datos PRE-treatment).

| Campo | Valor | Notas |
|---|---|---|
| `category_id` | str — idcategory | pass-through |
| `defaultcategory` | str | pass-through |
| `idaccount` | str | pass-through |
| `idclient` | str | pass-through |
| `idcompany` | str | pass-through |
| `suggested_amount` | `null` | Python `None` |
| `basis` | `null` | Python `None` |
| `confidence` | `null` | Python `None` |
| `display_label` | `"No hay suficiente historial para esta categoría"` | literal |
| `explanation` | `"No hay datos históricos suficientes para calcular una sugerencia en esta categoría."` | literal |
| `model_version` | `"fase0-v1"` | literal |
| `reason` | `"No hay suficiente historial para calcular el monto sugerido"` | solo cuando null |

---

## Tasks (con TDD test contracts)

### T0 — Setup

- [ ] **T0.1** — En `requirements.txt`, agregar las líneas `statsmodels>=0.14.0,<1.0.0` y `pytest-cov>=4.0.0`. Verificar que `pip install -r requirements.txt` instala sin error.

  **Test contracts:** ninguno (verificación manual con `python -c "import statsmodels; import pytest_cov"`).

### T1 — Módulo model.py

- [ ] **T1.1** — Crear `src/smart_budget/model.py` con constantes `EPSILON_DEFAULT = 0.01` y `EWMA_SPAN_DEFAULT = 3`.

  **Test contracts:** `test_module_importable` — `from smart_budget.model import compute_budget_suggestions` sin ImportError.

- [ ] **T1.2** — Implementar `apply_treatment(df, treatment, epsilon)` con el contrato de la firma.

  **Test contracts:**
  - `test_apply_treatment_A_unchanged` — Input: df con [100, 0, 50], treatment="A". Expect: monthly_total == [100, 0, 50].
  - `test_apply_treatment_B_excludes_zeros` — Input: df con [100, 0, 50], treatment="B". Expect: monthly_total == [100, 50], length == 2.
  - `test_apply_treatment_C_replaces_zeros` — Input: df con [100, 0, 50], treatment="C". Expect: monthly_total == [100, 0.01, 50].
  - `test_apply_treatment_invalid_raises` — Input: treatment="X". Expect: ValueError.
  - `test_apply_treatment_does_not_mutate_original` — Input: df original. After apply_treatment(), df original unchanged.

- [ ] **T1.3** — Implementar `compute_wma(series)`.

  **Test contracts:**
  - `test_compute_wma_3_months` — Input: series=[100, 200, 300] (pesos 1,2,3 → sum pesos=6). Expect: (100×1 + 200×2 + 300×3)/6 = round(233.33, 2) = 233.33.
  - `test_compute_wma_single_value` — Input: series=[150]. Expect: 150.0.
  - `test_compute_wma_empty_raises` — Input: series=[]. Expect: ValueError.
  - `test_compute_wma_with_zeros` — Input: series=[0, 0, 100]. Expect: (0×1+0×2+100×3)/6 = 50.0.

- [ ] **T1.4** — Implementar `compute_ewma(series, span=EWMA_SPAN_DEFAULT)`.

  **Test contracts:**
  - `test_compute_ewma_known_series` — Input: series=[100, 200, 300], span=3. Expect: pandas.Series([100,200,300]).ewm(span=3).mean().iloc[-1], redondeado a 2 decimales.
  - `test_compute_ewma_single_value` — Input: series=[250], span=3. Expect: 250.0.
  - `test_compute_ewma_empty_raises` — Input: series=[]. Expect: ValueError.
  - `test_compute_ewma_non_negative` — Input: series=[0, 0, 0], span=3. Expect: 0.0 (nunca negativo).

- [ ] **T1.5** — Implementar `compute_holt_winters(series)`.

  **Test contracts:**
  - `test_compute_holt_winters_6_months` — Input: series=[100, 110, 105, 120, 115, 130]. Expect: float >= 0 AND float <= 200 (razonable para la serie dada — no mayor a 2× el máximo de la serie).
  - `test_compute_holt_winters_below_min_raises` — Input: series=[100, 200]. Expect: ValueError (menos de 3 obs).
  - `test_compute_holt_winters_clamps_negative` — Arrange: mockear `ExponentialSmoothing.fit().forecast()` para que retorne -5.0. Expect: `compute_holt_winters` retorna 0.0.
  - `test_compute_holt_winters_with_zeros` — Input: series=[100, 0, 80, 0, 90, 0], trend='add'. Expect: float >= 0.0 AND float != 0.0 (la serie tiene valores > 0, el forecast no debe ser exactamente 0).

- [ ] **T1.6** — Implementar `compute_confidence(data_points)` y `build_explanation(months_analyzed, months_with_positive_spend, confidence)`.

  **Test contracts para `compute_confidence`:**
  - `test_confidence_high` — Input: data_points=6. Expect: "high".
  - `test_confidence_high_8` — Input: data_points=8. Expect: "high".
  - `test_confidence_medium_3` — Input: data_points=3. Expect: "medium".
  - `test_confidence_medium_5` — Input: data_points=5. Expect: "medium".
  - `test_confidence_low` — Input: data_points=2. Expect: "low".

  **Test contracts para `build_explanation`:**
  - `test_explanation_high` — Input: months_analyzed=6, months_with_positive_spend=4, confidence="high". Expect: contiene "4" y "6" y "alta confiabilidad".
  - `test_explanation_medium` — Input: months_analyzed=4, months_with_positive_spend=3, confidence="medium". Expect: contiene "3" y "4" y "confiabilidad media".
  - `test_explanation_low` — Input: months_analyzed=3, months_with_positive_spend=2, confidence="low". Expect: contiene "2" y "3" y "pocos datos".
  - `test_explanation_none` — Input: confidence=None. Expect: "No hay datos históricos suficientes para calcular una sugerencia en esta categoría."
  - `test_explanation_no_prescriptive_words` — Input: cualquier confidence válido. Expect: la cadena retornada NO contiene "deberías", "tienes que", "te conviene", "más que".

- [ ] **T1.7** — Implementar `compute_budget_suggestions(df, method, treatment, reference_date, ...)` con el pipeline de 10 pasos del contrato.

  **Test contracts (TC-4.x):**

  - `test_TC4_1_wma_treatment_A_includes_zeros` — Arrange: df rectangular con 1 cuenta, 1 categoría, 4 meses [100, 0, 200, 150], reference_date="2026-03-01". Act: `compute_budget_suggestions(df, "wma", "A", "2026-03-01")`. Assert: `suggested_amount` == `compute_wma(pd.Series([100, 0, 200, 150]))`, `basis.months_with_zero` == 1, `basis.months_with_positive_spend` == 3.

  - `test_TC4_2_wma_treatment_B_excludes_zeros` — Arrange: same df. Act: method="wma", treatment="B". Assert: `suggested_amount` == `compute_wma(pd.Series([100, 200, 150]))` (zeros excluidos), `basis.months_with_zero` == 1 (PRE-treatment), `basis.months_with_positive_spend` == 3.

  - `test_TC4_3_treatment_C_epsilon_replace` — Arrange: df con 4 meses [100, 0, 200, 150]. Act: treatment="C". Assert: el valor calculado usa series=[100, 0.01, 200, 150]. También: `basis.months_with_zero` == 1 (PRE-treatment, no 0).

  - `test_TC4_4_treatment_B_all_zeros_returns_null` — Arrange: construir df directamente (sin pasar por `prepare_smart_budget_data`) con 3 filas para 1 bucket (idaccount="M1", idcategory="5", defaultcategory="GROCERIES", idclient="C1", idcompany="CO1"), periods=["2025-10","2025-11","2025-12"], monthly_total=[0.0, 0.0, 0.0]. Act: `compute_budget_suggestions(df, "wma", "B", "2026-03-01")`. Assert: resultado tiene 1 elemento, `suggested_amount` is None, `reason` == `"No hay suficiente historial para calcular el monto sugerido"`, `display_label` == `"No hay suficiente historial para esta categoría"`.

  - `test_TC4_5_confidence_levels` — Arrange: tres dfs distintos — (a) 6 meses todos > 0 → confidence "high"; (b) 4 meses > 0 → confidence "medium"; (c) 2 meses > 0 → confidence "low". Assert por caso.

  - `test_TC4_6_holt_winters_returns_float` — Arrange: df con 6 meses de gasto positivo. Act: method="holt_winters", treatment="A". Assert: `suggested_amount` es float >= 0.0.

  - `test_TC4_7_reference_date_cutoff` — Arrange: df con meses 2025-01 a 2026-03 (15 meses). reference_date="2025-06-01". Assert: `basis.months_analyzed` == 6 (solo hasta 2025-06), meses de 2025-07 en adelante ignorados.

  - `test_TC4_8_json_contract_fields` — Arrange: df válido. Act: compute_budget_suggestions. Assert: cada dict en la lista contiene exactamente los campos: category_id, defaultcategory, idaccount, idclient, idcompany, suggested_amount, basis, confidence, display_label, explanation, model_version. "reason" NO está presente cuando suggested_amount != None. El campo `explanation` es un string no vacío que contiene el valor de `months_with_positive_spend` como substring cuando suggested_amount != None.

### T2 — CLI `scripts/run_methods.py`

- [ ] **T2.1** — Crear `scripts/run_methods.py` con argparse y argumentos: `--method` (required, choices=[wma, ewma, holt_winters]), `--treatment` (default="A", choices=[A, B, C]), `--reference-date` (required, format YYYY-MM-DD), `--input` (default="data/dough/smart_budget_synthetic.csv"), `--output` (default=None = stdout), `--min-months` (default=3, int).

  Pipeline del CLI:
  1. Leer CSV del `--input`
  2. Llamar `prepare_smart_budget_data(df, min_months=args.min_months)`
  3. Llamar `compute_budget_suggestions(gated_df, method, treatment, reference_date)`
  4. Serializar lista a JSON con `json.dumps(results, indent=2, ensure_ascii=False)`
  5. Escribir a `--output` file o stdout

  Logging con structlog: al inicio loguear `method`, `treatment`, `reference_date`, `input_path`. Al final: `n_suggestions`, `n_null_suggestions`.

  **Test contracts:**
  - `test_run_methods_importable` — `import runpy; runpy.run_path("scripts/run_methods.py", run_name="__test__")` no lanza ImportError ni SyntaxError. El test usa `pytest.raises(SystemExit)` envolviendo la llamada (argparse hace sys.exit en ausencia de args requeridos).
  - La integración CLI completa se valida en TC-4.8 (golden set).

### T3 — Golden set

- [ ] **T3.1** — Generar `tests/fixtures/golden_set.csv` con el siguiente proceso (ejecutar una vez, commitear el resultado):
  1. Verificar que `data/dough/smart_budget_synthetic.csv` existe.
  2. Ejecutar: `python scripts/run_methods.py --method wma --treatment A --reference-date 2026-03-01 --output /tmp/golden_raw.json`
  3. Convertir el JSON a CSV con columnas: `idaccount,idclient,idcompany,category_id,defaultcategory,suggested_amount,confidence,months_analyzed,months_with_zero,months_with_positive_spend`
  4. Guardar en `tests/fixtures/golden_set.csv`.
  5. Commitear: `git -C .worktrees/DATA-1137 add tests/fixtures/golden_set.csv && git -C .worktrees/DATA-1137 commit -m "test(DATA-1137): add golden set WMA/A/2026-03-01"`

  **Test contracts:**
  - `test_TC4_golden_set_matches_output` — Load golden_set.csv via `_load_fixture("golden_set.csv")`. Run `compute_budget_suggestions` con `method="wma", treatment="A", reference_date="2026-03-01"` sobre los mismos datos fuente. Assert: para cada fila del golden_set, el `suggested_amount` en el output coincide exactamente (sin tolerancia — match exacto por float round 2 decimales).

### TDD rule

El implementer DEBE seguir este ciclo por cada task:
1. Escribir los tests del test contract → commit `test(DATA-1137): add tests for T<N>`
2. Correr tests → verificar que FALLAN (RED)
3. Escribir el mínimo código para pasar → GREEN
4. Refactorizar si es necesario (sin romper tests)
5. Commit: `feat(DATA-1137): implement T<N> — <descripción breve>`

**Nunca `--no-verify`. Nunca commitear tests y código en el mismo commit.**

### Mandatory verification

Antes de declarar el ticket done, el implementer DEBE ejecutar y reportar:

```bash
# Desde .worktrees/DATA-1137/
pip install -r requirements.txt
python -m pytest tests/unit/test_model.py -v --tb=short
python -m pytest tests/ -v --cov=smart_budget --cov-report=term-missing
python scripts/run_methods.py --method wma --treatment A --reference-date 2026-03-01 | python -m json.tool
python scripts/run_methods.py --method ewma --treatment B --reference-date 2026-03-01 | python -m json.tool
python scripts/run_methods.py --method holt_winters --treatment A --reference-date 2026-03-01 | python -m json.tool
```

Todos deben salir con exit code 0 y sin errores.

Cobertura mínima: **80%** en `src/smart_budget/model.py`.

---

## Execution Report

*(Actualizado por el implementer a medida que avanza)*

| Task | Status | Commit |
|---|---|---|
| T0.1 | pending | — |
| T1.1 | pending | — |
| T1.2 | pending | — |
| T1.3 | pending | — |
| T1.4 | pending | — |
| T1.5 | pending | — |
| T1.6 | pending | — |
| T1.7 | pending | — |
| T2.1 | pending | — |
| T3.1 | pending | — |
| V1 (unit tests) | pending | — |
| V2 (coverage ≥80%) | pending | — |
