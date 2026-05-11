# Plan — DATA-1136: DS - Ajuste y validación de datos

**Ticket:** https://blossomtechnology.atlassian.net/browse/DATA-1136  
**Sprint:** Data Sprint 10.26  
**Risk:** Medium  
**Estimate:** M · 4 SP · ~9–12h  
**Branch:** feat/DATA-1136 (base: DATA-1041)

---

## Problema y enfoque

La tabla `fact_transactions` (1,413,948 filas) contiene transacciones OLB internas y externas (Dough).
Los datos no están limpios para el modelo de Smart Budget: incluyen transacciones de ingreso,
Pending, soft-deleted y sin categoría válida.

Este ticket implementa la capa de preparación de datos:
1. Filtrar `fact_transactions` según las reglas acordadas
2. Agregar por `(idclient, idcompany, idmember, defaultcategory, YYYY-MM)` → suma mensual
3. Zero-fill: meses sin transacciones → $0 (serie completa por member × category)
4. Clamp negativos a $0 (REF > gastos da neto negativo)
5. Outlier handling: P90 cap sobre totales mensuales (global)
6. Gating: buckets con < 3 meses de data → excluidos del output

Output: `data/dough/smart_budget_prep.csv`

---

## DCR — Decisiones

### Auto-cerradas (grounded en código)

| # | Dimensión | Decisión |
|---|-----------|----------|
| A1 | "bucket" | = `defaultcategory` (alineado con condiciones del usuario) |
| A2 | Soft delete | `deletedat IS NULL` (26% de filas tienen soft delete) |
| A3 | Tipo de transacción | `incomeexpenditure = 'expenditure'` |
| A4 | Categorías excluidas | `defaultcategory NOT IN ('UNCATEGORIZED', NULL, 'INCOME')` |
| A5 | Status OLB (SUB/LOAN) | `status IS NULL` ó `status NOT IN ('PENDING', 'HOLD')` |
| A6 | Status External (MANT/Dough) | `status = 'POSTED'` exacto, explícito |
| A7 | Identificar fuente | `idtransaction` prefix: SUB/LOAN = OLB, MANT = External |
| A8 | Clave de agregación | `(idclient, idcompany, idmember, defaultcategory, period_yyyymm)` |
| A9 | Clamp negativos | `monthly_total = max(0, monthly_total)` |
| A10 | P90 cap | Global sobre todos los totales mensuales del dataset filtrado |
| A11 | Módulos | `src/smart_budget/filters.py` + `aggregator.py` |
| A12 | Output | `data/dough/smart_budget_prep.csv` |

### Cerradas por el dev (DCR interactivo)

| # | Pregunta | Respuesta | Impacto |
|---|----------|-----------|---------|
| H1 | Zero-fill | **Incluir meses con total = $0** (ticket lo especifica explícitamente) | `aggregator.py` genera grid completo (member × category × all months en rango) |
| H2 | Rango del grid | **Todos los meses en el rango del dataset** (dinámico, no hardcodeado) | La serie completa queda disponible para que el modelo elija cualquier ventana N |

---

## HLTC — Arquitectura delta

### Bloques auto-aceptados

- **src/smart_budget/__init__.py** — módulo vacío, sin lógica
- **src/smart_budget/filters.py** — 5 reglas de filtrado, sin dependencias externas, testeable unitariamente
- **scripts/run_smart_budget_prep.py** — CLI wrapper: carga `fact_transactions.csv`, aplica pipeline, escribe output
- **tests/unit/test_filters.py + test_aggregator.py** — fixtures sintéticas (no PII real)

### Bloque revisado (HLTC-3)

**HLTC-3 — Zero-fill cross-join:**  
`aggregator.py` genera el grid completo `(member × category) × all_months`. Enfoque:
1. Agregar las transacciones filtradas → DataFrame `monthly_actual`
2. Extraer todos los pares únicos `(member, category)` + todos los meses en `[min_month, max_month]`
3. Cross-join → `full_grid` (# filas ≈ n_pairs × n_months)
4. Left join `full_grid` ← `monthly_actual`, fill NaN → 0
5. Aplicar clamp → P90 → gating
Escalabilidad: ~500 members × 20 categories × 48 months = 480,000 filas máx — manejable en pandas.

---

## Estructura de archivos a crear/modificar

```
src/
  smart_budget/
    __init__.py              [crear]
    filters.py               [crear] — función filter_transactions()
    aggregator.py            [crear] — funciones aggregate_monthly(), apply_p90_cap(), apply_gating()

scripts/
  run_smart_budget_prep.py   [crear] — CLI: --input, --output, --min-months, --p90

tests/
  unit/
    test_filters.py          [crear] — casos parametrizados para las 5 reglas
    test_aggregator.py       [crear] — monthly sum, zero-fill, clamp, P90, gating
  fixtures/
    fact_transactions_test.csv  [crear] — datos sintéticos sin PII (~50-100 rows)

data/dough/
  smart_budget_prep.csv      [output, no commitear — ya en .gitignore]
```

---

## Lógica detallada

### filters.py — filter_transactions()

```python
def filter_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica las 5 reglas de filtrado sobre fact_transactions."""
    # A2: soft delete
    df = df[df["deletedat"].isna()]
    # A3: solo gastos
    df = df[df["incomeexpenditure"] == "expenditure"]
    # A4: categorías válidas
    df = df[df["defaultcategory"].notna()]
    df = df[~df["defaultcategory"].isin(["UNCATEGORIZED", "INCOME"])]
    # A5/A6: status por fuente
    is_olb = df["idtransaction"].str.startswith(("SUB", "LOAN"))
    is_ext = df["idtransaction"].str.startswith("MANT")
    olb_ok = is_olb & (df["status"].isna() | ~df["status"].isin(["PENDING", "HOLD"]))
    ext_ok = is_ext & (df["status"] == "POSTED")
    df = df[olb_ok | ext_ok]
    return df.reset_index(drop=True)
```

### aggregator.py — pipeline completo

```python
# 1. aggregate_monthly(): GROUP BY key → SUM(amount), clamp a 0
# 2. zero_fill(): genera grid completo (member×category×all_months), left join → fill 0
# 3. apply_p90_cap(): calcula P90 global, aplica clip, marca columna 'capped'
# 4. apply_gating(): cuenta meses únicos por (member, category), filtra < min_months
# 5. prepare_smart_budget_data(): orquesta el pipeline completo
```

---

## Contrato de output

Columnas de `smart_budget_prep.csv`:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| idclient | str | Multi-tenancy: cliente |
| idcompany | str | Multi-tenancy: CU |
| idmember | str | Miembro |
| defaultcategory | str | Categoría (bucket) |
| period_yyyymm | str | "YYYY-MM" |
| monthly_total | float | Gasto mensual neto (clamped, P90-capped, en USD) |
| capped | bool | True si el total original superó el P90 |

Registros excluidos por gating **no aparecen** en el output.

---

## Casos edge cubiertos

| # | Caso | Manejo |
|---|------|--------|
| E1 | Mes sin transacciones para (member, category) | Incluido con monthly_total = 0 |
| E2 | Suma mensual neta negativa (REF > gastos) | Clamp a 0 antes del P90 |
| E3 | Total mensual > P90 global | Reemplazado por P90, capped=True |
| E4 | Bucket con < 3 meses de data | Excluido del output (gating) |
| E5 | Transacción MANT sin status POSTED | Excluida por filtro A6 |
| E6 | OLB con status PENDING | Excluida por filtro A5 |
| E7 | defaultcategory NULL / UNCATEGORIZED / INCOME | Excluida por filtro A4 |
| E8 | deletedat IS NOT NULL (soft-deleted) | Excluida por filtro A2 |

---

## Criterios de aceptación (del ticket)

- [x] Output es serie limpia `(user × bucket × month)` con totales mensuales
- [x] Buckets con < 3 meses excluidos del dataset
- [x] Outlier handling (P90 cap) documentado y aplicado consistentemente
- [x] Solo transacciones Posted incluidas (por fuente: OLB vs External)
- [x] Condiciones adicionales del dev: UNCATEGORIZED/NULL/INCOME excluidas, PENDING excluido

---

**Decision: approved by lbetancourth-dev-blossom — 2026-05-11**

All DCR decisions closed, HLTC blocks reviewed. Ready for security + spec generation.
