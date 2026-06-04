---
title: Cómo construir el dataset idmember para Smart Budget
aliases: [Dataset idmember, smart_budget_synthetic_idmember, DATA-1179 dataset]
tags: [guide, dataset, idmember, etl, smart-budget, data-1179]
type: guide
audience: ds-ml
ticket: DATA-1179
last_updated: 2026-06-02
---

# Cómo construir el dataset `idmember` para Smart Budget

Esta guía explica el paso a paso para construir
`data/dough/smart_budget_synthetic_idmember.csv` — el dataset de entrada del
modelo Smart Budget con grain `idmember` (introducido en DATA-1179).

A diferencia del dataset anterior (grain `idaccount`), aquí la unidad de
análisis es el **miembro de la Credit Union**, no su cuenta individual.

---

## Qué es este dataset

```
data/dough/smart_budget_synthetic_idmember.csv
```

| Campo | Descripción |
|---|---|
| Un registro por | `(idmember, idcategory, period_yyyymm)` — combinación única de miembro × categoría × mes |
| Grain | `idmember` — el usuario final de la CU |
| Uso | Input del modelo Smart Budget: cálculo de sugerencias de presupuesto |
| Origen | Datos sintéticos (dev/test). Para producción: `fact_transactions_expenditure.csv` via `run_smart_budget_prep.py` |

---

## Schema completo — origen de cada campo

| Campo | Tipo | Origen | Descripción |
|---|---|---|---|
| `idclient` | `string` | `fact_transactions.idclient` | ID del cliente/producto Blossom (ej. `1 = Blossom`, `2 = Davivienda`). Filtro de multi-tenancy nivel 1. |
| `idcompany` | `string` | `fact_transactions.idcompany` | ID de la Credit Union. Filtro de multi-tenancy nivel 2. |
| `idmember` | `string` | Resuelto por join dual (ver §3) | ID del miembro individual de la CU. **Grain del modelo.** No viene directamente de `fact_transactions` — se resuelve vía `memberaccount`. |
| `idaccount` | `string` | `fact_transactions.idaccount` | ID de la cuenta que originó las transacciones. Se conserva para trazabilidad; el modelo no lo usa como groupby. |
| `idcategory` | `string` | `fact_transactions.idcategory` | ID interno de la categoría de gasto. |
| `defaultcategory` | `string` | `fact_transactions.defaultcategory` (vía join con `defaultcategory` table) | Nombre legible de la categoría: `GROCERIES`, `Auto & Transport`, `Bills & Utilities`, etc. |
| `period_yyyymm` | `string` | Derivado de `fact_transactions.date` | Mes calendario en formato `YYYY-MM`. Calculado como `pd.to_datetime(date).dt.to_period("M")`. Solo meses **completos** (el mes en curso se excluye del modelo). |
| `monthly_total` | `float ≥ 0` | `SUM(fact_transactions.amount)` por grupo | Gasto mensual neto por miembro × categoría × mes. Clampeado a `0.0` si la suma neta es negativa (reembolsos > gastos). |

---

## Arquitectura del flujo de construcción

```
S3 silver (DOUGH + OLB)
       ↓  extract_datalake_to_csv.py
data/dough/dev/silver/                 ← tablas DOUGH en CSV
data/olb/dev/silver/                   ← tablas OLB en CSV
       ↓  build_fact_transactions.py   ← une OLB + EXT + resuelve idmember
data/dough/fact_transactions.csv       ← ~1.4M filas, grain: transacción
       ↓  run_smart_budget_prep.py     ← filtra (6 reglas) + agrega por mes
data/dough/smart_budget_prep.csv       ← grain: (idmember, category, month)
       ↓  (si es dataset sintético)
tests/fixtures/generate_golden_set.py  ← genera datos deterministas para tests
data/dough/smart_budget_synthetic_idmember.csv
```

---

## Paso 1 — Extraer tablas desde S3

```bash
aws sso login --profile blossom-dev

# Tablas DOUGH (contiene externaltransaction, member, account, memberaccount, etc.)
python3 scripts/extract_datalake_to_csv.py --source DOUGH --layer silver

# Tablas OLB (contiene OLBSubAccountTransaction, OLBLoanTransaction, etc.)
python3 scripts/extract_datalake_to_csv.py --source OLB --layer silver --workers 40
```

**Tablas descargadas relevantes:**

| Tabla | Path | Uso |
|---|---|---|
| `externaltransaction` | `data/dough/dev/silver/` | Transacciones Plaid/Finicity (prefijo `EXT`) |
| `memberaccount` | `data/dough/dev/silver/` | Puente entre `idaccount` e `idmember` |
| `account` | `data/dough/dev/silver/` | Puente OLB: `blossomdoughconsolidatedaccountid` → `id` |
| `defaultcategory` | `data/dough/dev/silver/` | Catálogo de categorías |
| `OLBSubAccountTransaction` | `data/olb/dev/silver/` | Transacciones OLB (prefijo `SUB`) |
| `OLBLoanTransaction` | `data/olb/dev/silver/` | Pagos de préstamos (prefijo `LOAN`, excluidos) |

---

## Paso 2 — Construir `fact_transactions` con `idmember`

Este es el paso clave introducido en DATA-1179. El script
`build_fact_transactions.py` une OLB y DOUGH **y resuelve `idmember`** para
cada transacción mediante una estrategia de join dual.

```bash
# Opción A: desde DB (recomendado — datos idénticos al equipo DE)
python3 scripts/build_fact_transactions.py --source db

# Opción B: desde los CSVs del Paso 1 (offline)
python3 scripts/build_fact_transactions.py --source s3 --env dev
```

### Cómo se resuelve `idmember` (join dual)

`fact_transactions` no tiene `idmember` directamente. Se resuelve con la
función `_resolve_idmember()` en `build_fact_transactions.py`:

```
Caso 1 — Cuentas EXT (Plaid/Finicity):
    idaccount = "EXT2"
    → strip prefijo "EXT" → "2"
    → validar que es numérico (si no → idmember = null + warning)
    → JOIN memberaccount ON memberaccount.idaccount = 2
    → obtener memberaccount.idmember

Caso 2 — Cuentas OLB (SUB, INT):
    idaccount = "SUB8406"
    → buscar en account.blossomdoughconsolidatedaccountid = "SUB8406"
    → obtener account.id
    → JOIN memberaccount ON memberaccount.idaccount = account.id
    → obtener memberaccount.idmember

Caso 3 — Sin match:
    idmember = null
    → structlog warning("unresolvable_account")
    → fila excluida en los pasos siguientes
```

**Tablas involucradas en el join:**

```
externaltransaction / OLBSubAccountTransaction
    ↓ (idaccount)
memberaccount   [idaccount → idmember]
    + 
account         [blossomdoughconsolidatedaccountid → id]  ← solo para OLB
```

### Output del Paso 2

```
data/dough/fact_transactions.csv              ← ~1.4M filas en dev (2022–2026)
data/dough/fact_transactions_expenditure.csv  ← ya filtrada (solo gastos)
```

Schema completo → ver [[How-To-Build-Fact-Transactions]].

---

## Paso 3 — Filtrar y agregar por mes (`smart_budget_prep.csv`)

```bash
PYTHONPATH=src python3 scripts/run_smart_budget_prep.py \
    --input data/dough/fact_transactions.csv \
    --output data/dough/smart_budget_prep.csv \
    --min-months 3
```

El script aplica **6 reglas de filtrado** (implementadas en `filters.py`) y
luego agrega por mes.

### Reglas de filtrado aplicadas

| # | Regla | Columna | Condición |
|---|---|---|---|
| 1 | Soft delete | `deletedat` | `IS NULL` → incluir |
| 2 | Solo gastos | `incomeexpenditure` | `== "expenditure"` |
| 3 | Categorías válidas | `defaultcategory` | No `UNCATEGORIZED`, `INCOME`, `MONEY_SENT`, ni null |
| 4 | Excluir LOAN | `idtransaction` | No empieza con `"LOAN"` |
| 5 | Estado OLB (`SUB*`) | `status` | No `PENDING` ni `HOLD` |
| 6 | Estado EXT (`EXT*`) | `status` | Solo `POSTED` (exacto, case-insensitive) |

### Agregación mensual (`aggregate_monthly`)

Después del filtrado, `aggregator.py → aggregate_monthly()` hace:

```python
GROUP BY (idclient, idcompany, idmember, idaccount, idcategory, defaultcategory, period_yyyymm)
SUM(amount) → monthly_total

# Clamp: si la suma neta es negativa (REF > gastos) → monthly_total = 0.0
monthly_total = max(monthly_total, 0.0)
```

> **Nota sobre miembros con múltiples cuentas:** Un miembro puede tener `EXT2`
> (Plaid) y `SUB8406` (OLB). En este paso, ambas cuentas generan filas separadas
> con el mismo `idmember`. La suma a grain `idmember` ocurre en `apply_gating`
> (paso siguiente).

### Zero-fill

`zero_fill(df)` completa el grid `(idmember × idcategory) × todos_los_meses`.
Meses sin transacciones → `monthly_total = 0.0`.

- ✅ Mes con $0 y cuenta activa → data point = 0 (incluir)
- ❌ Mes sin cuenta activa → excluir (ausencia, no cero)

### Gating mínimo (`apply_gating`)

```python
GROUP BY (idclient, idcompany, idmember, idcategory, defaultcategory)
→ contar meses con monthly_total > 0
→ excluir si count < min_months (default: 3)
```

El groupby incluye `idclient` e `idcompany` para evitar mezcla cross-CU cuando
dos CUs tienen miembros con el mismo `idmember` numérico.

| Meses con gasto > 0 | Resultado |
|---|---|
| `< min_months` | ❌ Excluir — no hay suficiente historial |
| `>= min_months` | ✅ Incluir |

### Output del Paso 3

`data/dough/smart_budget_prep.csv`:

| Columna | Tipo | Descripción |
|---|---|---|
| `idclient` | string | Multi-tenancy nivel 1 |
| `idcompany` | string | Multi-tenancy nivel 2 (CU) |
| `idmember` | string | Grain del modelo |
| `idaccount` | string | Cuenta de origen (trazabilidad) |
| `idcategory` | string | ID de categoría |
| `defaultcategory` | string | Nombre de categoría |
| `period_yyyymm` | string | Mes calendario (YYYY-MM) |
| `monthly_total` | float ≥ 0 | Gasto neto mensual |

---

## Paso 4 — Dataset sintético (para tests / dev sin S3)

Para desarrollo local y tests sin acceso a S3, el script
`tests/fixtures/generate_golden_set.py` genera un dataset determinista con
estructura idéntica al output real.

```bash
# Desde la raíz del repo
python3 tests/fixtures/generate_golden_set.py
```

Genera dos archivos:

| Archivo | Descripción |
|---|---|
| `data/dough/smart_budget_synthetic_idmember.csv` | Dataset de input sintético (72 filas) |
| `tests/fixtures/golden_set.csv` | Dataset con valores esperados del modelo (golden set) |

### Estructura del dataset sintético

```
3 miembros × 8 categorías × 6 meses (2025-10 → 2026-03) = 72 filas
```

| `idmember` | `idaccount` | Tipo de cuenta | Categorías | Notas |
|---|---|---|---|---|
| `10` | `EXT2` | EXT (Plaid/Finicity) | Auto & Transport, GROCERIES, Bills & Utilities | 6 meses completos → pasa gating |
| `20` | `EXT22` + `SUB8406` | EXT + OLB (2 cuentas) | Auto & Transport, Bills & Utilities, Health & Fitness, Subscriptions | Representa miembro con cuentas mixtas |
| `30` | `EXT33` | EXT | GROCERIES, Home & Rent, Food & Dining, Entertainment & Leisure | Entertainment: solo 2 meses con gasto → no pasa gating |

> **Guard de seguridad:** El script tiene protección contra ejecución en
> producción:
> ```python
> if os.environ.get("ENVIRONMENT", "").lower() in ("prod", "production"):
>     sys.exit(1)  # Nunca en producción
> ```

---

## Paso 5 — Correr el modelo sobre el dataset

Con el dataset listo, ejecutar el modelo:

```bash
PYTHONPATH=src python3 scripts/run_methods.py \
    --method wma \
    --treatment A \
    --reference-date 2026-03 \
    --lookback-months 6 \
    --input data/dough/smart_budget_synthetic_idmember.csv
```

### Output del modelo

El output incluye por cada `(idmember, idcategory)`:

| Campo | Descripción |
|---|---|
| `idmember` | Grain: miembro de la CU |
| `category_id` | ID de categoría |
| `defaultcategory` | Nombre de categoría |
| `suggested_amount` | Sugerencia calculada (null si < min_months meses con gasto) |
| `total_suggested` | Suma de sugerencias no-nulas del miembro. `0.0` si todas son nulas |
| `confidence` | `high` (≥6 meses), `medium` (3–5), `low` (2) |
| `basis.months_analyzed` | Meses dentro de la ventana N |
| `basis.data_points` | Meses con gasto efectivo usados |
| `basis.period_range` | Rango: `"YYYY-MM ~ YYYY-MM"` |

---

## Verificar el dataset

```python
import pandas as pd

df = pd.read_csv("data/dough/smart_budget_synthetic_idmember.csv")

# Checks básicos
assert "idmember" in df.columns, "idmember debe estar presente"
assert df["idmember"].notna().all(), "No debe haber idmember nulos"
assert df["monthly_total"].min() >= 0, "No debe haber monthly_total negativos"
assert df["period_yyyymm"].nunique() == 6, "Debe tener 6 meses"
assert df["idmember"].nunique() >= 3, "Debe tener al menos 3 miembros"

print(f"✅ Dataset válido: {len(df)} filas, {df['idmember'].nunique()} miembros")
print(df.groupby("idmember")["defaultcategory"].nunique().rename("categorias_por_miembro"))
```

---

## Diferencias vs. dataset anterior (pre DATA-1179)

| Aspecto | Dataset anterior (`idaccount`) | Dataset nuevo (`idmember`) |
|---|---|---|
| Grain | `(idaccount, category, month)` | `(idmember, category, month)` |
| Archivo | `smart_budget_prep.csv` | `smart_budget_synthetic_idmember.csv` |
| `idmember` presente | ❌ No | ✅ Sí |
| Multi-cuenta por miembro | ❌ Filas separadas | ✅ Suma colapsada en `apply_gating` |
| `total_suggested` | ❌ No existe | ✅ Sum de sugerencias por miembro |
| Meses cubiertos | 4 (2025-12 → 2026-03) | 6 (2025-10 → 2026-03) |
| Members en dataset sintético | 1 (idaccount) | 3 (idmember 10, 20, 30) |

---

## Restricciones de seguridad

| Regla | Descripción |
|---|---|
| ❌ No commitear CSVs | `data/` está en `.gitignore` — nunca commitear datos reales |
| ❌ No loguear `idmember` en claro | Usar SHA-256 + `SB_LOG_SALT` en todos los logs que referencien `idmember` |
| ✅ Multi-tenancy | Todo groupby que incluya `idmember` debe incluir también `idclient` + `idcompany` |
| ❌ No correr `generate_golden_set.py` en producción | El script tiene guard de entorno que bloquea ejecución |

---

## Backlinks

- [[How-To-Extract-Data]] — guía original de extracción (grain idaccount)
- [[How-To-Build-Fact-Transactions]] — construcción de fact_transactions
- [[How-To-Extract-From-S3]] — extracción de tablas desde S3
- [[How-To-Run-Pipeline]] — pipeline completo de sugerencias
- `src/smart_budget/filters.py` — 6 reglas de filtrado
- `src/smart_budget/aggregator.py` — aggregate_monthly, zero_fill, apply_gating
- `src/smart_budget/model.py` — compute_budget_suggestions, total_suggested
- `scripts/build_fact_transactions.py` — join dual para idmember
- `tests/fixtures/generate_golden_set.py` — generador de dataset sintético
