---
title: Core Model · Public API
aliases: [smart_budget API, Exported functions]
tags: [module, core-model, api]
type: api
last_mapped_at: 2026-05-13T10:20:00Z
last_commit: fc0547f
---

# Core Model — Public API

Todas las funciones públicas exportadas por `src/smart_budget/`. Ordenadas por capa del pipeline.

## filters.py

### `filter_transactions(df: DataFrame) → DataFrame`

Aplica las 5 reglas de filtrado sobre `fact_transactions`. Retorna DataFrame filtrado con índice reseteado.

**Reglas aplicadas (en orden):**
1. `deletedat IS NULL` — excluye soft-deleted
2. `incomeexpenditure == 'expenditure'` — solo gastos
3. `defaultcategory NOT IN (None, 'UNCATEGORIZED', 'INCOME', 'MONEY_SENT')` — categorías válidas
4. OLB (`SUB`/`LOAN` prefix): excluye si `status IN ('PENDING', 'HOLD')`
5. EXT (Dough, Plaid/Finicity): excluye si `status != 'POSTED'`
6. Prefijos desconocidos: pasan sin filtro de status (no data loss silencioso)

**Input mínimo:** DataFrame con columnas `deletedat`, `incomeexpenditure`, `defaultcategory`, `idtransaction`, `status`, `amount`.

```python
from smart_budget.filters import filter_transactions
df_clean = filter_transactions(df_raw)
```

---

## aggregator.py

### `aggregate_monthly(df: DataFrame) → DataFrame`

Agrupa por `(idclient, idcompany, idaccount, idcategory, defaultcategory, period_yyyymm)` y suma `amount`. Clampea negativos a 0. Crea `period_yyyymm` desde columna `date`.

**Retorna:** columnas `[..., period_yyyymm, monthly_total]`

### `zero_fill(df: DataFrame) → DataFrame`

Genera el grid completo `(member × category) × all_months` y rellena NaN con 0. Distingue meses sin actividad (0) de meses sin cuenta activa (excluir).

**Raises:** `ValueError` si un `idaccount` mapea a más de un `(idclient, idcompany)`.

### `apply_gating(df: DataFrame, min_months: int = 3) → DataFrame`

Descarta buckets con menos de `min_months` meses con `monthly_total > 0`. Meses con 0 (zero-filled) NO cuentan hacia el threshold.

### `prepare_smart_budget_data(df: DataFrame, min_months: int = 3) → DataFrame`

Orquesta el pipeline completo: `aggregate_monthly` → `zero_fill` → `apply_gating`.

**Output garantizado:** columnas `[idclient, idcompany, idaccount, idcategory, defaultcategory, period_yyyymm, monthly_total]`, `monthly_total >= 0`.

```python
from smart_budget.aggregator import prepare_smart_budget_data
prepared = prepare_smart_budget_data(df_filtered, min_months=3)
```

---

## model.py

### `apply_treatment(df, treatment, epsilon=0.01) → DataFrame`

Aplica la estrategia de tratamiento de ceros:
- `"A"`: sin cambio (incluir ceros)
- `"B"`: filtrar filas con `monthly_total == 0`
- `"C"`: reemplazar `monthly_total == 0` por `epsilon`

**Raises:** `ValueError` si `treatment` no es `A/B/C`.

### `compute_wma(series: Series) → float`

Weighted Moving Average con pesos lineales `[1, 2, ..., n]`. Resultado `>= 0`, redondeado a 2 decimales.

### `compute_ewma(series: Series, span: int = 3) → float`

EWMA con `pandas.ewm(span=span, adjust=False)`. Resultado `>= 0`, redondeado a 2 decimales.

### `compute_median(series: Series) → float`

Mediana simple. Resultado `>= 0`, redondeado a 2 decimales.

### `compute_holt_winters(series: Series) → float`

Holt-Winters con `ExponentialSmoothing(trend='add', seasonal=None)`. Requiere ≥3 observaciones.

**Raises:** `ValueError` si `len(series) < 3`.

### `compute_confidence(data_points: int) → str`

`"high"` (≥6), `"medium"` (3–5), `"low"` (2).

### `build_explanation(months_analyzed, months_with_positive_spend, confidence) → str`

Genera texto UDAAP-compliant para el usuario. Nunca prescriptivo.

### `compute_budget_suggestions(df, method, treatment, reference_date, lookback_months=None, ...) → list[dict]`

**Función principal.** Pipeline por bucket: filter window → treatment → compute → confidence → explanation → JSON dict.

**Args:**
- `method`: `"wma" | "ewma" | "median" | "holt_winters"`
- `treatment`: `"A" | "B" | "C"`
- `reference_date`: `"YYYY-MM"` (el mes para el que se sugiere)
- `lookback_months`: ventana de meses (None = todos disponibles)

**Retorna:** `list[dict]` — un dict por bucket. Null suggestion si gating o método falla.

```python
from smart_budget.model import compute_budget_suggestions
results = compute_budget_suggestions(
    prepared_df,
    method="wma",
    treatment="B",
    reference_date="2026-05",
    lookback_months=6,
)
```

## Constantes exportadas

| Constante | Valor | Descripción |
|---|---|---|
| `EPSILON_DEFAULT` | `0.01` | Valor epsilon para Treatment C |
| `EWMA_SPAN_DEFAULT` | `3` | Span default para EWMA |

## Backlinks

- [[01-core-model/README]]

#api #public-surface #core-model
