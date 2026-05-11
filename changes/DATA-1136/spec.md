# Spec — DATA-1136: DS - Ajuste y validación de datos

**Plan:** changes/DATA-1136/plan.md  
**Estado:** ready for /execute  
**Modelo:** TDD — tests primero, luego implementación mínima

---

## Task T1 — Módulo src/smart_budget (scaffold)

**Archivos:**
- `src/smart_budget/__init__.py` (crear, vacío)
- `src/smart_budget/filters.py` (crear)
- `src/smart_budget/aggregator.py` (crear)

**Descripción:**
Crear el módulo Python `src/smart_budget/` con los dos archivos de lógica. Sin dependencias externas
más allá de `pandas` (ya en requirements). Exports públicos tipados con type hints obligatorios.

**No hacer:** no crear lógica en `__init__.py`. No importar desde scripts/.

---

## T1 — Test Contracts

### TC-1.1 — El módulo es importable
```python
def test_module_importable():
    from smart_budget import filters, aggregator
    assert hasattr(filters, "filter_transactions")
    assert hasattr(aggregator, "prepare_smart_budget_data")
```

---

## Task T2 — filters.py: filter_transactions()

**Archivo:** `src/smart_budget/filters.py`

**Firma:**
```python
def filter_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica las 5 reglas de filtrado sobre fact_transactions.

    Reglas (en orden):
        1. deletedat IS NULL (soft delete)
        2. incomeexpenditure == 'expenditure'
        3. defaultcategory NOT IN (None, 'UNCATEGORIZED', 'INCOME', 'MONEY_SENT')
        4. OLB (SUB/LOAN prefix): status IS NULL ó status NOT IN ('PENDING', 'HOLD')
        5. External (EXT prefix / Plaid): status == 'POSTED'

    Args:
        df: DataFrame con esquema de fact_transactions (columnas en minúsculas).

    Returns:
        DataFrame filtrado. Índice reseteado.
    """
```

**Columnas requeridas en el input:** `deletedat`, `incomeexpenditure`, `defaultcategory`,
`idtransaction`, `status`.

**Columnas del output:** todas las del input (no se agregan ni eliminan columnas).

---

## T2 — Test Contracts

### TC-2.1 — Filtro A2: excluir soft-deleted
```python
def test_filter_removes_soft_deleted():
    df = pd.DataFrame({
        "deletedat": [None, "2025-01-01", None],
        "incomeexpenditure": ["expenditure", "expenditure", "expenditure"],
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES"],
        "idtransaction": ["SUB1", "SUB2", "SUB3"],
        "status": [None, None, None],
        "amount": [100.0, 50.0, 80.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2
    assert "SUB2" not in result["idtransaction"].values
```

### TC-2.2 — Filtro A3: excluir income
```python
def test_filter_removes_income_transactions():
    df = pd.DataFrame({
        "deletedat": [None, None, None],
        "incomeexpenditure": ["expenditure", "income", "expenditure"],
        "defaultcategory": ["GROCERIES", "SALARY", "DINING"],
        "idtransaction": ["SUB1", "SUB2", "SUB3"],
        "status": [None, None, None],
        "amount": [100.0, 2000.0, 50.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2
    assert "income" not in result["incomeexpenditure"].values
```

### TC-2.3 — Filtro A4: excluir UNCATEGORIZED, NULL, INCOME, MONEY_SENT (categoría)
```python
@pytest.mark.parametrize("category", ["UNCATEGORIZED", None, "INCOME", "MONEY_SENT"])
def test_filter_removes_invalid_categories(category):
    df = pd.DataFrame({
        "deletedat": [None, None],
        "incomeexpenditure": ["expenditure", "expenditure"],
        "defaultcategory": [category, "GROCERIES"],
        "idtransaction": ["SUB1", "SUB2"],
        "status": [None, None],
        "amount": [100.0, 80.0],
    })
    result = filter_transactions(df)
    assert len(result) == 1
    assert result.iloc[0]["defaultcategory"] == "GROCERIES"
```

### TC-2.4 — Filtro A5: excluir OLB con status PENDING
```python
def test_filter_removes_olb_pending():
    df = pd.DataFrame({
        "deletedat": [None, None, None],
        "incomeexpenditure": ["expenditure"] * 3,
        "defaultcategory": ["GROCERIES"] * 3,
        "idtransaction": ["SUB1", "SUB2", "LOAN1"],
        "status": [None, "PENDING", None],
        "amount": [100.0, 75.0, 200.0],
    })
    result = filter_transactions(df)
    assert len(result) == 2
    assert "SUB2" not in result["idtransaction"].values
```

### TC-2.5 — Filtro A6: external (EXT/Plaid) solo POSTED
```python
def test_filter_external_only_posted():
    df = pd.DataFrame({
        "deletedat": [None, None, None],
        "incomeexpenditure": ["expenditure"] * 3,
        "defaultcategory": ["DINING"] * 3,
        "idtransaction": ["EXT1", "EXT2", "EXT3"],
        "status": ["POSTED", "PENDING", None],
        "amount": [50.0, 80.0, 90.0],
    })
    result = filter_transactions(df)
    assert len(result) == 1
    assert result.iloc[0]["idtransaction"] == "EXT1"
```

### TC-2.6 — Todas las reglas combinadas (caso realista)
```python
def test_filter_combined_rules():
    """Fixture: 10 filas, 5 deben sobrevivir los 5 filtros."""
    df = _load_fixture("fact_transactions_test.csv")
    result = filter_transactions(df)
    expected_ids = {"SUB_VALID_1", "SUB_VALID_2", "LOAN_VALID_1", "EXT_POSTED_1", "EXT_POSTED_2"}
    assert set(result["idtransaction"].values) == expected_ids
```

### TC-2.7 — DataFrame vacío no lanza excepción
```python
def test_filter_empty_dataframe():
    df = pd.DataFrame(columns=["deletedat","incomeexpenditure","defaultcategory",
                                 "idtransaction","status","amount"])
    result = filter_transactions(df)
    assert len(result) == 0
    assert isinstance(result, pd.DataFrame)
```

---

## Task T3 — aggregator.py: pipeline completo

**Archivo:** `src/smart_budget/aggregator.py`

**Funciones a implementar:**

```python
def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa por (idclient, idcompany, idaccount, idcategory, defaultcategory, period_yyyymm)
    y suma amount. Clampea negativos a 0. Retorna columna monthly_total."""

def zero_fill(df: pd.DataFrame) -> pd.DataFrame:
    """Genera el grid completo (account×category×all_months en rango del dataset).
    Hace left join con df. Rellena NaN → 0 en monthly_total.
    Propaga idclient e idcompany del account (consistent dentro del grupo)."""

def apply_gating(df: pd.DataFrame, min_months: int = 3) -> pd.DataFrame:
    """Cuenta meses únicos (no-cero) por (idaccount, idcategory, defaultcategory).
    Excluye pares con count < min_months. Retorna df sin esos pares."""

def prepare_smart_budget_data(
    df: pd.DataFrame,
    min_months: int = 3,
) -> pd.DataFrame:
    """Orquesta el pipeline completo:
    aggregate_monthly → zero_fill → apply_gating."""
```

**Columnas del output de `prepare_smart_budget_data`:**
`idclient`, `idcompany`, `idaccount`, `idcategory`, `defaultcategory`, `period_yyyymm`,
`monthly_total` (float, ≥ 0).

---

## T3 — Test Contracts

### TC-3.1 — aggregate_monthly: suma correcta por grupo
```python
def test_aggregate_monthly_sum():
    df = pd.DataFrame({
        "idclient": ["C1"] * 3,
        "idcompany": ["CO1"] * 3,
        "idaccount": ["M1", "M1", "M1"],
        "idcategory": ["8"] * 3,
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES"],
        "date": ["2025-01-05", "2025-01-15", "2025-02-10"],
        "amount": [100.0, 50.0, 200.0],
    })
    result = aggregate_monthly(df)
    jan = result[(result["period_yyyymm"] == "2025-01")]
    assert jan.iloc[0]["monthly_total"] == 150.0
    assert len(result) == 2  # enero + febrero
```

### TC-3.2 — aggregate_monthly: clamp negativos a 0
```python
def test_aggregate_monthly_clamp_negative():
    df = pd.DataFrame({
        "idclient": ["C1"],
        "idcompany": ["CO1"],
        "idaccount": ["M1"],
        "idcategory": ["15"],
        "defaultcategory": ["SHOPPING"],
        "date": ["2025-03-10"],
        "amount": [-50.0],  # REF mayor que gasto
    })
    result = aggregate_monthly(df)
    assert result.iloc[0]["monthly_total"] == 0.0
```

### TC-3.3 — zero_fill: genera meses faltantes con 0
```python
def test_zero_fill_inserts_missing_months():
    # M1 tiene GROCERIES en ene y mar, pero no feb
    df = pd.DataFrame({
        "idclient": ["C1", "C1"],
        "idcompany": ["CO1", "CO1"],
        "idaccount": ["M1", "M1"],
        "idcategory": ["8", "8"],
        "defaultcategory": ["GROCERIES", "GROCERIES"],
        "period_yyyymm": ["2025-01", "2025-03"],
        "monthly_total": [100.0, 80.0],
    })
    result = zero_fill(df)
    feb = result[(result["idaccount"] == "M1") &
                 (result["defaultcategory"] == "GROCERIES") &
                 (result["period_yyyymm"] == "2025-02")]
    assert len(feb) == 1
    assert feb.iloc[0]["monthly_total"] == 0.0
```

### TC-3.4 — apply_gating: excluir buckets con < 3 meses
```python
def test_apply_gating_excludes_low_data_buckets():
    # M1-GROCERIES: 3 meses (pasa) · M1-DINING: 2 meses (excluido)
    df = pd.DataFrame({
        "idaccount": ["M1"] * 5,
        "idcategory": ["8", "8", "8", "7", "7"],
        "defaultcategory": ["GROCERIES", "GROCERIES", "GROCERIES", "DINING", "DINING"],
        "period_yyyymm": ["2025-01", "2025-02", "2025-03", "2025-01", "2025-02"],
        "monthly_total": [100.0, 80.0, 90.0, 50.0, 60.0],
        "idclient": ["C1"] * 5,
        "idcompany": ["CO1"] * 5,
    })
    result = apply_gating(df, min_months=3)
    assert set(result["defaultcategory"].unique()) == {"GROCERIES"}
    assert "DINING" not in result["defaultcategory"].values
```

### TC-3.5 — apply_gating: meses con $0 NO cuentan para el gating
```python
def test_apply_gating_zero_months_dont_count():
    # M1-GROCERIES: 3 meses pero 1 es cero → solo 2 meses con data → excluido
    df = pd.DataFrame({
        "idaccount": ["M1"] * 3,
        "idcategory": ["8"] * 3,
        "defaultcategory": ["GROCERIES"] * 3,
        "period_yyyymm": ["2025-01", "2025-02", "2025-03"],
        "monthly_total": [100.0, 0.0, 80.0],  # feb es zero-fill
        "idclient": ["C1"] * 3,
        "idcompany": ["CO1"] * 3,
    })
    result = apply_gating(df, min_months=3)
    # Solo 2 meses con data (ene + mar) → excluido
    assert len(result) == 0
```

### TC-3.6 — prepare_smart_budget_data: pipeline completo end-to-end
```python
def test_prepare_smart_budget_data_end_to_end():
    df = _load_fixture("fact_transactions_test.csv")
    filtered = filter_transactions(df)
    result = prepare_smart_budget_data(filtered, min_months=3)
    # Contrato del output
    expected_cols = {
        "idclient", "idcompany", "idaccount", "idcategory", "defaultcategory",
        "period_yyyymm", "monthly_total",
    }
    assert expected_cols.issubset(set(result.columns))
    assert (result["monthly_total"] >= 0).all()
    # Ningún bucket excluido tiene < 3 meses
    counts = result[result["monthly_total"] > 0].groupby(
        ["idaccount", "defaultcategory"])["period_yyyymm"].nunique()
    assert (counts >= 3).all()
```

### TC-3.7 — Idempotencia: dos runs producen output idéntico
```python
def test_prepare_idempotent():
    df = _load_fixture("fact_transactions_test.csv")
    filtered = filter_transactions(df)
    result_1 = prepare_smart_budget_data(filtered.copy(), min_months=3)
    result_2 = prepare_smart_budget_data(filtered.copy(), min_months=3)
    pd.testing.assert_frame_equal(
        result_1.sort_values(result_1.columns.tolist()).reset_index(drop=True),
        result_2.sort_values(result_2.columns.tolist()).reset_index(drop=True),
    )
```

---

## Task T4 — Fixture sintética tests/fixtures/fact_transactions_test.csv

**Archivo:** `tests/fixtures/fact_transactions_test.csv`

**Descripción:**
Crear un CSV sintético (~50 filas) que cubra todos los casos edge de los tests.
**Sin PII real.** Usar IDs sintéticos (`M001`, `M002`…) y nombres de categoría reales del schema.

**Casos a cubrir en la fixture:**
- 5 filas válidas (pasan todos los filtros)
- 1 soft-deleted (`deletedat` no nulo)
- 1 `incomeexpenditure = 'income'`
- 1 `defaultcategory = 'UNCATEGORIZED'`
- 1 `defaultcategory = 'INCOME'`
- 1 OLB con `status = 'PENDING'`
- 1 External (EXT / Plaid) con `status = 'PENDING'` (debe excluirse)
- 1 External (EXT / Plaid) con `status = 'POSTED'` (debe incluirse)
- Suficientes filas para que M001-GROCERIES tenga 3 meses de data (pasa gating)
- Suficientes filas para que M001-DINING tenga solo 2 meses (falla gating)
- 1 fila con amount negativo (REF)

**Columnas mínimas requeridas:**
`idtransaction, idclient, idcompany, idmember, defaultcategory, incomeexpenditure,
amount, date, status, deletedat`

---

## Task T5 — scripts/run_smart_budget_prep.py

**Archivo:** `scripts/run_smart_budget_prep.py`

**Descripción:**
CLI wrapper que orquesta el pipeline end-to-end. Lee `fact_transactions.csv`, aplica
`filter_transactions` + `prepare_smart_budget_data`, escribe `smart_budget_prep.csv`.

**Uso:**
```bash
python scripts/run_smart_budget_prep.py \
  --input data/dough/fact_transactions.csv \
  --output data/dough/smart_budget_prep.csv \
  --min-months 3
```

**Argumentos:**
- `--input` (default: `data/dough/fact_transactions.csv`)
- `--output` (default: `data/dough/smart_budget_prep.csv`)
- `--min-months` (default: 3, type: int)

**Error handling (requerido — F2 de threats.md):**
Envolver todo el pipeline en un `try/except` global que:
- Loguee un mensaje de error sanitizado (sin raw DataFrame, sin member IDs, sin montos)
- Salga con código 1
```python
try:
    # pipeline completo
except Exception as exc:
    logger.error("pipeline_failed", error_type=type(exc).__name__,
                 hint="ver logs para detalles; no se expone contenido de datos")
    sys.exit(1)
```
No propagar tracebacks con DataFrame contents a stdout/stderr.

**Logs estructurados requeridos** (structlog):
- Al inicio: `job_start`, `input_path`, `min_months`
- Tras filtrado: `rows_original`, `rows_after_filter`, `rows_removed_pct`
- Tras agregación: `unique_members`, `unique_categories`, `periods_range`
- Tras P90 cap: `p90_value`, `rows_capped`
- Tras gating: `buckets_removed`, `rows_in_output`
- Al final: `job_done`, `output_path`, `output_rows`

**No loguear:** montos individuales de transacciones, member IDs sin hashear.

---

## Verificación del implementador (no omitir)

Antes de hacer commit, verificar:
- [ ] `pytest tests/unit/test_filters.py -v` — todos los TC pasan
- [ ] `pytest tests/unit/test_aggregator.py -v` — todos los TC pasan
- [ ] `python scripts/run_smart_budget_prep.py --input data/dough/fact_transactions_sample.csv` — no lanza excepciones, genera output
- [ ] Output tiene columnas: `idclient, idcompany, idmember, defaultcategory, period_yyyymm, monthly_total, capped`
- [ ] `monthly_total >= 0` en todo el output
- [ ] Sin PII en fixtures ni en logs
