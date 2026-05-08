# Plan Fase 0 — Smart Budget (El Reflejo)

## Contexto

El objetivo de Fase 0 es calcular una **sugerencia de presupuesto por categoría** basada en el
historial de gasto real del member, usando la mediana de los últimos N meses (default: 6).
No se inventa nada — el modelo refleja el comportamiento pasado del usuario.

---

## Estado del datalake de dev (análisis de tablas)

### Fuentes de transacciones disponibles

| Tabla | Filas | Status | Type | idcategory | Notas |
|---|---|---|---|---|---|
| `manualtransaction` | 86 | ❌ siempre null | ❌ siempre null | ❌ 0/86 llenos | Tabla principal según el equipo. Sin filtro de estado ni tipo. |
| `externaltransaction` | 15 | ✅ `posted` | ✅ `debit/credit` | ❌ 0/15 llenos | Transacciones via provider (Plaid/Finicity). |

### Tablas de soporte clave

| Tabla | Filas | Rol en Fase 0 |
|---|---|---|
| `manualaccount` | 51 | Vincula `manualtransaction → member` |
| `account` | 5 | Vincula `externaltransaction → member` |
| `memberaccount` | 3 | Relación member ↔ account |
| `member` | 21 | Unidad de cálculo |
| `membertacacceptance` | 60 | Gate de T&C: 17 members aceptaron |
| `defaultcategory` | 29 | 18 categorías de tipo Expense (shouldshow=true, grupo 1) |
| `companyntropycategory` | 1352 | Mapa Ntropy → defaultcategory (cuando RICH está activo) |
| `budget` | 2 | **Tabla de output** ya existe en schema |
| `budgetcategory` | 4 | **Tabla de output** ya existe en schema |
| `period` | 1 | Período mensual definido (id=1, monthly) |

### Hallazgos críticos

1. **`idcategory` es NULL en todas las transacciones de dev.** No hay datos categorizados aún.
   Para validar el modelo necesitamos generar un dataset de prueba con categorías asignadas.

2. **`manualtransaction` no tiene `status` ni `type`.** Las transacciones manuales no pasan
   por el workflow de posting. Se tratan como gastos directos; el tipo se infiere desde la categoría.

3. **Las tablas de output (`budget`, `budgetcategory`) ya existen** en el schema de Dough.
   La Fase 0 escribe directamente en ellas.

4. **No existe `transactionSplit` en Dough dev.** El flag `issplit` en `manualtransaction`
   siempre es `False` en dev. La unidad de agregación será la transacción directa.

5. **Categorías de tipo Expense** disponibles: 18 categorías del grupo 1 (`shouldshow=true`).
   Excluir grupos 2 (Income) y 3 (Transfers/Internal).

---

## Modelo de datos — flujo Fase 0

```
manualtransaction (amount, processdate, idcategory)
  → JOIN manualaccount (idmember)
  → JOIN member (idcompany)
  → FILTER: deletedat IS NULL (activo)
  → FILTER: idcategory NOT NULL (categorizado)
  → FILTER: idcategory IN categorías grupo Expense
  → AGGREGATE: SUM(amount) GROUP BY (idmember, idcategory, YYYY-MM)
  → MODEL: MEDIAN de monthly_amounts por (idmember, idcategory)
  → GATE: si meses_con_data < 2 → no sugerir
  → OUTPUT → budget + budgetcategory
```

**Futura extensión** (cuando externaltransaction tenga categorías):
```
externaltransaction (status='posted', type='debit', idcategory)
  → misma lógica
  → UNION con manualtransaction antes del agregado
```

---

## Tablas de output (ya en schema)

### `budget`
```sql
id, idmember, idperiod, name, amountlimit, startdate, isactive
```
- Una fila por member por período (YYYY-MM)
- `amountlimit` = suma de todos los `allocatedamount` de sus categorías sugeridas
- `name` = 'Smart Budget {YYYY-MM}'
- `idperiod` = 1 (monthly)

### `budgetcategory`
```sql
id, idbudget, idcategory, idcategorygroup, allocatedamount, categoryslug
```
- Una fila por categoría sugerida dentro del budget
- `allocatedamount` = mediana calculada para esa categoría
- `categoryslug` = slug de la categoría (ej: `food-dining`)

---

## Pasos de implementación

### Step 1 — Dataset de prueba con categorías (dev)
Generar un CSV o script de inserción que asigne `idcategory` a transacciones existentes
en `manualtransaction` para poder probar el modelo end-to-end en dev.

**Tablas afectadas:** `manualtransaction` (UPDATE idcategory)
**Herramienta:** script Python o SQL seed

### Step 2 — Query de agregación mensual ✅
Construir la query SQL que produce la tabla intermedia:
```
member_id | category_id | year_month | monthly_amount
```

```sql
SELECT
  ma.idmember,
  mt.idcategory,
  TO_CHAR(mt.processdate, 'YYYY-MM') AS year_month,
  SUM(mt.amount)                     AS monthly_amount
FROM manualtransaction mt
JOIN manualaccount ma ON mt.idmanualaccount = ma.id
WHERE mt.deletedat IS NULL
  AND ma.deletedat IS NULL
  AND mt.idcategory IS NOT NULL
  AND mt.idcategory IN (
      SELECT id FROM defaultcategory
      WHERE idcategorygroup = 1 AND shouldshow = true AND deletedat IS NULL
  )
GROUP BY ma.idmember, mt.idcategory, TO_CHAR(mt.processdate, 'YYYY-MM')
```

**Archivos implementados:**
- `src/smart_budget/filters.py` — filtrado de transacciones (T&C gate, Expense cats, fecha)
- `src/smart_budget/aggregator.py` — mediana, gating, confidence, display_label, builders de output
- `src/smart_budget/queries/monthly_spend.sql` — query parametrizada para Redshift
- `scripts/run_phase0.py` — orquestador completo

**Ejecución:**
```bash
python3 scripts/run_phase0.py --period 2026-05 --n-months 6
```

**Resultado sobre datos de test** (period `2026-05`, ventana `2025-11 → 2026-04`):
```
Members procesados : 4   ← 1 sin transacciones categorizadas en la ventana
Sugerencias activas: 20
Sin sugerencia     : 4   ← no pasaron el gating (< 2 meses con data)

Member 2   → $840.27   (5 categorías, todas high confidence)
Member 7   → $414.84   (5 categorías, 1 low = solo 2 meses)
Member 9   → $528.19   (5 categorías, todas high)
Member 18  → $1,435.01 (5 categorías, todas high)
```

**Outputs guardados en `data/dough/test/query/`:**

El pipeline genera 3 archivos con responsabilidades distintas:

| Archivo | Qué contiene | Para qué sirve |
|---|---|---|
| `monthly_spend_YYYY-MM.csv` | Gasto sumado por member × categoría × mes (120 filas) | Auditoría, debugging, base para futuras fases |
| `budget.csv` | Una fila por member con el total sugerido del período | Encabezado que ve el usuario en Dough UI |
| `budgetcategory.csv` | Una fila por categoría sugerida, ligada al budget | Detalle editable por categoría, loop de feedback, contrato de API |

Flujo entre los 3:
```
monthly_spend  →  INPUT del modelo
                      ↓  mediana por (member, category)
budgetcategory →  OUTPUT atómico  (una sugerencia por categoría)
                      ↓  SUM(allocatedamount) GROUP BY member
budget         →  OUTPUT agregado (total del presupuesto del member)
```

### Step 3 — Modelo de mediana + gating
```python
# Para cada (idmember, idcategory):
monthly = df.groupby(["idmember","idcategory","year_month"])["monthly_amount"].sum()
summary = monthly.groupby(["idmember","idcategory"]).agg(
    months_with_data=("monthly_amount", lambda x: (x > 0).sum()),
    suggested_amount=("monthly_amount", "median"),
    data_points=("monthly_amount", "count"),
)
# Gate: excluir si months_with_data < 2
suggestions = summary[summary.months_with_data >= 2].copy()
suggestions["suggested_amount"] = suggestions["suggested_amount"].round(2)
```

### Step 4 — Confidence y display_label
```python
def get_confidence(months_with_data):
    if months_with_data >= 6: return "high"
    if months_with_data >= 3: return "medium"
    return "low"  # 2 meses exactos
```

### Step 5 — Escritura en budget + budgetcategory
- UPSERT en `budget` por `(idmember, idperiod, model_version)`
- UPSERT en `budgetcategory` por `(idbudget, idcategory)`
- Calcular `amountlimit` del budget como SUM de todos los `allocatedamount`

### Step 6 — Validación con golden set
Crear fixtures en `tests/fixtures/golden_set.csv` con:
- 5+ members sintéticos con 6+ meses de historia
- Resultado esperado calculado manualmente
- Comparar output del modelo vs expected

---

## Gaps a resolver antes de codear

| Gap | Acción |
|---|---|
| `idcategory` siempre NULL en dev | Crear seed script con categorías de prueba |
| ¿`manualtransaction` solo o + `externaltransaction`? | Confirmar con el equipo cuál es la fuente principal en Fase 0 |
| ¿Ventana N por CU o global en dev? | Usar default N=6, hardcodeado para dev |
| `budget.name` — ¿formato acordado? | Proponer `Smart Budget YYYY-MM` |

---

## Archivos a crear

```
src/
  smart_budget/
    filters.py        → reglas de categorías Expense, exclusiones
    aggregator.py     → lógica mediana, gating, confidence
    queries/
      monthly_spend.sql → query de agregación mensual

tests/
  unit/
    test_filters.py
    test_aggregator.py
  fixtures/
    golden_set.csv

scripts/
  seed_dev_categories.py   → asigna idcategory a transacciones de dev para pruebas
  run_phase0.py            → orquesta el pipeline completo (Step 2 → 5)
```
