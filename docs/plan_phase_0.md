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

### Step 1 — Extracción de datos DOUGH ✅ COMPLETADO

Extracción de tablas DOUGH desde S3 datalake dev y alpha.

**Script:** `scripts/extract_dough_to_csv.py`  
**Output:** `data/dough/dev/silver/*.csv` (30 tablas), `data/dough/alpha/silver/*.csv`

```bash
python3 scripts/extract_dough_to_csv.py --env dev
```

---

### Step 2 — Extracción de tablas OLB ✅ COMPLETADO

Extracción de las 7 tablas OLB necesarias para construir `fact_transactions`.

**Tablas extraídas** desde `blossom-analytics-datalake-dev/datalake/silver/OLB/`:
- `olbsubaccounttransaction` — transacciones de cuentas (1M+ filas)
- `olbsubaccount` — información de subcuentas
- `olbaccountnumber` — números de cuenta e `idfi`
- `olbtransactioninfo` — link a categoría de transacción
- `olbtransactioncategory` — nombre de categoría OLB nativa
- `olbloantransaction` — transacciones de préstamos
- `olbloan` — información de préstamos

**Output:** `data/olb/dev/silver/*.csv`

---

### Step 3 — Construcción de fact_transactions

Unión de las tres fuentes en un esquema canónico, siguiendo `ref_fact_transactions_olb.py`.

**Script:** `scripts/build_fact_transactions.py`  
**Output:** `data/dough/fact_transactions.csv`

```bash
python3 scripts/build_fact_transactions.py --env dev
```

**Esquema de fact_transactions:**

| Columna | Fuente SUB | Fuente LOAN | Fuente EXT |
|---------|-----------|-------------|------------|
| `idTransaction` | `"SUB" + sat.id` | `"LOAN" + lt.id` | `"EXT" + ext.id` |
| `idAccount` | `"INT" + idolbaccountnumber` | `"INT" + idolbaccountnumber` | `"EXT" + idaccount` |
| `amount` | `sat.amount` | `lt.principalAmount` | `ext.amount` |
| `incomeExpenditure` | `amount < 0 → "expenditure"` | idem | `amount > 0 → "expenditure"` ¹ |
| `defaultCategory` | `otc.name` | `otc.name` | `ext.categoryname` |

> ¹ Plaid usa convención inversa: positivo = gasto, negativo = ingreso

**Nota:** Las columnas `enrichment*` son NULL en local (datos de DynamoDB no disponibles en S3 silver).

**Ver:** `docs/fact_transactions_README.md` para documentación completa del esquema.

---

### Step 4 — Aplicar modelo Smart Budget

Usar `fact_transactions` como fuente, aplicar filtros, agregar mensualmente, calcular mediana.

**Archivos:**
- `src/smart_budget/filters.py` — T&C gate, expense categories, date window
- `src/smart_budget/aggregator.py` — mediana, gating, confidence, output builders
- `scripts/run_phase0.py` — orquestador (será actualizado para usar fact_transactions)

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

---

### Step 5 — Output: budget + budgetcategory

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
| Low | 2 meses | Mostrar con advertencia |
| Medium | 3-5 meses | Mostrar |
| High | ≥ 6 meses | Mostrar con confianza |

---

## Archivos del proyecto

```
scripts/
  extract_dough_to_csv.py      ✅ Extrae DOUGH silver → CSV
  build_fact_transactions.py   ✅ Construye fact_transactions desde OLB + DOUGH
  run_phase0.py                🔄 Orquestador (actualizar para usar fact_transactions)

src/smart_budget/
  filters.py                   ✅ Filtros de transacciones
  aggregator.py                ✅ Modelo mediana, gating, confidence
  queries/monthly_spend.sql    ✅ Query de agregación mensual

docs/
  plan_phase_0.md              ✅ Este archivo
  fact_transactions_README.md  ✅ Documentación de la tabla central

data/ (gitignored)
  dough/dev/silver/*.csv       ✅ 30 tablas DOUGH dev
  dough/alpha/silver/*.csv     ✅ Tablas DOUGH alpha
  dough/fact_transactions.csv  🔄 Tabla central (generar con Step 3)
  olb/dev/silver/*.csv         ✅ 7 tablas OLB dev
```
