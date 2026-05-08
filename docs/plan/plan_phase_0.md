# Plan Fase 0 — Smart Budget (El Reflejo)

## Contexto

El objetivo de Fase 0 es calcular una **sugerencia de presupuesto por categoría** basada en el
historial de gasto real del member, usando la mediana de los últimos N meses (default: 6).
No se inventa nada — el modelo refleja el comportamiento pasado del usuario.

---

## Arquitectura de datos (referencia: High Level Architecture DOUGH, pág. 15)

```
OLBSubAccountTransaction ─┐
OLBLoanTransaction       ─┼──→ fact_transactions ──→ fact_labels ──→ Smart Budget
externaltransaction      ─┘         (tabla central)    (categorías)
```

La **tabla central** es `fact_transactions` — unión de:
1. **OLB internal** — cuentas de CU (subaccounts + loans)
2. **Dough external** — agregador Plaid/Finicity (`externaltransaction`)

El equipo de DE mantiene el job PySpark de referencia: `ref_fact_transactions_olb.py`

---

## Fuentes de datos

| Fuente | Bucket S3 | Path | Tablas clave |
|--------|-----------|------|--------------|
| OLB silver | `blossom-analytics-datalake-dev` | `datalake/silver/OLB/` | `olbsubaccounttransaction`, `olbloantransaction`, `olbsubaccount`, `olbloan`, `olbaccountnumber`, `olbtransactioninfo`, `olbtransactioncategory` |
| Dough silver | `blossom-analytics-datalake-dev` | `datalake/silver/DOUGH/` | `externaltransaction`, `defaultcategory`, `companyntropycategory`, `member`, `membertacacceptance` |

---

## Modelo de datos — flujo completo Fase 0

```
fact_transactions (incomeExpenditure='expenditure', deletedAt IS NULL)
  → FILTER: T&C gate (membertacacceptance)
  → JOIN defaultcategory (idcategorygroup=1, shouldshow=true)
  → AGGREGATE: SUM(amount) GROUP BY (idmember, idcategory, YYYY-MM)
  → MODEL: MEDIAN de monthly_amounts por (idmember, idcategory)
  → GATE: si meses_con_data < 2 → no sugerir
  → CONFIDENCE: high(≥6m) / medium(≥3m) / low(2m)
  → OUTPUT → budget + budgetcategory
```

---

## Tablas de output

### `budget`
```sql
id, idmember, idperiod, name, amountlimit, startdate, isactive
```
- Una fila por member por período (YYYY-MM)
- `amountlimit` = SUM de todos los `allocatedamount`
- `name` = `'Smart Budget YYYY-MM'`

### `budgetcategory`
```sql
id, idbudget, idcategory, idcategorygroup, allocatedamount, categoryslug
```
- Una fila por categoría sugerida
- `allocatedamount` = mediana calculada

---

## Pasos de implementación

---

### Step 1 — Extracción de datos DOUGH ✅ COMPLETADO

Extracción de todas las tablas DOUGH desde S3 datalake (dev y alpha) a CSV local.

**Script:** `scripts/extract_dough_to_csv.py`

```bash
python3 scripts/extract_dough_to_csv.py --env dev
python3 scripts/extract_dough_to_csv.py --env alpha
```

**Resultado:**

| Entorno | Tablas extraídas | Path local |
|---------|-----------------|------------|
| dev | 30 tablas | `data/dough/dev/silver/` |
| alpha | 23 tablas | `data/dough/alpha/silver/` |

Tablas clave extraídas (dev):

| Tabla | Filas |
|-------|-------|
| `manualtransaction` | 86 |
| `externaltransaction` | 15 |
| `member` | 21 |
| `membertacacceptance` | 60 |
| `defaultcategory` | 29 |
| `companyntropycategory` | 1,352 |
| `budget` | 2 |
| `budgetcategory` | 4 |

> **Hallazgo clave:** `idcategory` es NULL en el 100% de las transacciones dev. Las tablas `budget` y `budgetcategory` ya existen en el schema como tablas de output.

---

### Step 2 — Extracción de tablas OLB ✅ COMPLETADO

Extracción de las 7 tablas OLB necesarias para construir `fact_transactions` desde `blossom-analytics-datalake-dev/datalake/silver/OLB/`.

**Script:** extracción paralela con `ThreadPoolExecutor(workers=40)` (38+ min sin paralelismo → ~4 min con).

**Output:** `data/olb/dev/silver/`

| Tabla | Archivos parquet | Filas extraídas | Descripción |
|-------|-----------------|-----------------|-------------|
| `olbsubaccounttransaction` | 318 | 1,064,465 | Transacciones de cuentas (fuente principal) |
| `olbsubaccount` | 7,383 | 50,766 | Info de subcuentas (link a account number) |
| `olbaccountnumber` | 106 | 30,596 | Números de cuenta e `idfi` (Financial Institution) |
| `olbtransactioninfo` | 612 | 5,369,690 | Link transacción → categoría OLB |
| `olbtransactioncategory` | 9 | 315 | Catálogo de categorías OLB nativas |
| `olbloantransaction` | 117 | 350,401 | Transacciones de préstamos |
| `olbloan` | 6,021 | 52,817 | Info de préstamos (link a account number) |

> **Nota:** `olbsubaccount` y `olbloan` están particionadas por mes de creación (`createdat_month=YYYY-MM`) con miles de archivos pequeños — la extracción paralela fue crítica para performance.

---

### Step 3 — Construcción de fact_transactions ✅ COMPLETADO

Unión de las tres fuentes en un esquema canónico de 31 columnas, siguiendo la lógica PySpark de `ref_fact_transactions_olb.py` (traducida a pandas).

**Script:** `scripts/build_fact_transactions.py`

```bash
python3 scripts/build_fact_transactions.py --env dev
```

**Output:** `data/dough/fact_transactions.csv`

**Resultado:**

| Métrica | Valor |
|---------|-------|
| Total filas | **1,413,914** |
| Columnas | 31 |
| Rango de fechas | `2022-06-03` → `2026-05-08` |

Desglose por fuente:

| Fuente | Filas | Descripción |
|--------|-------|-------------|
| `OLB_SUB` | 1,063,606 | OLBSubAccountTransaction (excluye HOLD) |
| `OLB_LOAN` | 350,293 | OLBLoanTransaction (excluye HOLD) |
| `DOUGH_EXT` | 15 | externaltransaction (Plaid/Finicity) |
| **Total** | **1,413,914** | Post deduplicación por `idTransaction` |

Distribución por tipo:

| incomeExpenditure | Filas | % |
|-------------------|-------|---|
| `expenditure` | 740,616 | 52.4% |
| `income` | 673,298 | 47.6% |

> **Nota sobre enriquecimiento:** Las columnas `enrichment*` son `NULL` en local — los datos de DynamoDB no están en S3 silver. Solo 19 filas tienen `status` no nulo (ninguna es `HOLD`). El 99.9% de filas tiene `defaultCategory` asignada (vía `olbtransactioncategory`).

**Esquema de idTransaction por fuente:**

| Fuente | Formato `idTransaction` | Formato `idAccount` | Formato `idSubAccount` |
|--------|------------------------|--------------------|-----------------------|
| OLB SUB | `SUB{sat.id}` | `INT{idolbaccountnumber}` | `SUB{idsubaccount}` |
| OLB LOAN | `LOAN{lt.id}` | `INT{idolbaccountnumber}` | `LOAN{idolbloan}` |
| DOUGH EXT | `EXT{ext.id}` | `EXT{idaccount}` | `NULL` |

---

### Step 4 — Aplicar modelo Smart Budget 🔄 PENDIENTE

Usar `fact_transactions` como fuente, aplicar filtros, agregar mensualmente, calcular mediana.

**Archivos ya implementados** (basados en arquitectura anterior — requieren actualización):
- `src/smart_budget/filters.py` — T&C gate, expense categories, date window
- `src/smart_budget/aggregator.py` — mediana, gating, confidence, output builders
- `scripts/run_phase0.py` — orquestador (usar fact_transactions como input)

**Lógica de agregación:**
```python
# Para cada (idmember, idcategory):
monthly = df.groupby(["idmember","idcategory","year_month"])["amount"].sum()
summary = monthly.groupby(["idmember","idcategory"]).agg(
    months_with_data=("amount", lambda x: (x > 0).sum()),
    suggested_amount=("amount", "median"),
)
# Gate: excluir si months_with_data < 2
suggestions = summary[summary.months_with_data >= 2]
```

**Filtros a aplicar sobre fact_transactions:**
- `incomeExpenditure == 'expenditure'`
- `deletedAt IS NULL`
- `defaultCategory` en categorías grupo 1 (Expenses)
- `date` dentro de ventana N meses

---

### Step 5 — Output: budget + budgetcategory 🔄 PENDIENTE

- UPSERT en `budget` por `(idmember, idperiod)`
- UPSERT en `budgetcategory` por `(idbudget, idcategory)`
- `budget.amountlimit` = SUM de todos los `allocatedamount` del member

---

## Confidence y gating

```python
def get_confidence(months_with_data):
    if months_with_data >= 6: return "high"
    if months_with_data >= 3: return "medium"
    return "low"   # 2 meses exactos
```

| Nivel | Criterio | Acción |
|-------|----------|--------|
| Excluir | < 2 meses | No mostrar sugerencia |
| Low | 2 meses exactos | Mostrar con advertencia |
| Medium | 3–5 meses | Mostrar |
| High | ≥ 6 meses | Mostrar con alta confianza |

---

## Archivos del proyecto

```
scripts/
  extract_dough_to_csv.py      ✅ Extrae DOUGH silver → CSV (dev y alpha)
  build_fact_transactions.py   ✅ Construye fact_transactions desde OLB + DOUGH
  run_phase0.py                🔄 Orquestador (actualizar para usar fact_transactions)

src/smart_budget/
  filters.py                   🔄 Filtros (actualizar para fact_transactions schema)
  aggregator.py                ✅ Modelo mediana, gating, confidence
  queries/monthly_spend.sql    🔄 Query (actualizar fuente a fact_transactions)

docs/
  plan/
    plan_phase_0.md            ✅ Este archivo
    phase0_remaining_tasks.md  ✅ Tareas pendientes para producción
  fact_transactions_README.md  ✅ Documentación del esquema canónico
  glosario.md                  ✅ Glosario de términos

data/ (gitignored)
  dough/dev/silver/*.csv       ✅ 30 tablas DOUGH dev
  dough/alpha/silver/*.csv     ✅ 23 tablas DOUGH alpha
  dough/fact_transactions.csv  ✅ 1,413,914 filas (OLB_SUB + OLB_LOAN + DOUGH_EXT)
  olb/dev/silver/*.csv         ✅ 7 tablas OLB dev
```
