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

### Step 2 — Query de agregación mensual
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

---

## Resultado Step 2 — Ejecución en datos de test

**Comando ejecutado:**
```bash
python3 scripts/run_phase0.py --period 2026-05 --n-months 6
```

**Parámetros:**
- Período objetivo: `2026-05` (mes en curso, excluido del cálculo)
- Ventana histórica: 6 meses completos (`2025-11` → `2026-04`)
- Members en scope: 5 (con T&C aceptados y cuentas activas)
- Model version: `fase0-v1`

**Resultado:**
```
Members procesados : 4   ← 1 sin transacciones categorizadas en la ventana
Sugerencias activas: 20
Sin sugerencia     : 4   ← no pasaron el gating (< 2 meses con data)

Member 2   → $840.27   (5 categorías, todas high confidence)
Member 7   → $414.84   (5 categorías, 1 low = solo 2 meses)
Member 9   → $528.19   (5 categorías, todas high)
Member 18  → $1,435.01 (5 categorías, todas high)
```

### Por qué se generan 3 archivos en `data/dough/test/query/`

El pipeline tiene **3 niveles de resultado** que corresponden a 3 responsabilidades distintas:

#### 1. `monthly_spend_YYYY-MM.csv` — Tabla intermedia de agregación
> **Qué es:** El gasto real sumado por member × categoría × mes calendario.

```
idmember | category_id | year_month | monthly_amount
       2 |           1 |    2025-11 |         137.73
       2 |           1 |    2025-12 |          40.91
       ...
```

Es la materia prima del modelo. Una fila por cada mes en que un member tuvo gasto
en una categoría. Se guarda porque es útil para:
- **Auditar** el cálculo de la mediana (ver los datos que la generaron)
- **Debugging** de casos edge (meses con $0, reembolsos, etc.)
- **Futuras fases** que necesiten tendencias o estacionalidad

#### 2. `budget.csv` — Presupuesto total por member
> **Qué es:** Una fila por member con el total sugerido para el período.

```
id | idmember | idperiod | name                 | amountlimit | model_version
 9 |        2 |        1 | Smart Budget 2026-05 |      840.27 | fase0-v1
10 |        7 |        1 | Smart Budget 2026-05 |      414.84 | fase0-v1
```

Es el **encabezado del presupuesto** que el usuario ve en Dough UI. El `amountlimit`
es la suma de todos los `allocatedamount` de sus categorías sugeridas. Separado de
`budgetcategory` porque el usuario puede editar el total independientemente de las
categorías individuales.

#### 3. `budgetcategory.csv` — Sugerencia por categoría
> **Qué es:** Una fila por cada categoría sugerida, vinculada al budget del member.

```
id | idbudget | idcategory | allocatedamount | confidence | display_label                  | period_range
41 |        9 |          1 |          115.87 |       high | Basado en tus últimos 6 meses  | 2025-11 ~ 2026-04
42 |        9 |          2 |          127.81 |       high | Basado en tus últimos 6 meses  | 2025-11 ~ 2026-04
```

Es el **detalle por categoría** que Dough UI muestra al usuario para que ajuste cada
línea. Separado de `budget` porque:
- El usuario puede aceptar unas categorías y modificar otras
- El `smartBudgetSuggestionLog` necesita rastrear decisiones a nivel de categoría
- La API `/smart-budget/suggestion` devuelve un array (una entrada por categoría)

#### Relación entre los 3 archivos

```
monthly_spend  →  INPUT del modelo
                      ↓  mediana por (member, category)
budgetcategory →  OUTPUT atómico  (una sugerencia por categoría)
                      ↓  SUM(allocatedamount) GROUP BY member
budget         →  OUTPUT agregado (total del presupuesto del member)
```

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
