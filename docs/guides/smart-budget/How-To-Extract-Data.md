---
title: Cómo extraer datos del datalake para Smart Budget
aliases: [Extracción de datos, Data extraction, ETL Smart Budget]
tags: [guide, extraction, etl, s3, filters, rules]
type: guide
audience: ds-ml
ticket: DATA-1136
last_updated: 2026-05-20
---

# Cómo extraer datos del datalake para Smart Budget

Guía completa del flujo de extracción: desde S3 (raw) hasta `smart_budget_prep.csv`
(datos listos para el modelo). Incluye todas las reglas de filtrado obligatorias
y los criterios de inclusión/exclusión aplicados en cada etapa.

> **Prerequisito:** acceso AWS activo.
> ```bash
> aws sso login --profile blossom-dev
> ```

---

## Arquitectura del flujo

```
S3 bronze (CDC raw)
      ↓
S3 silver (tablas limpias por fuente)
      ↓  extract_datalake_to_csv.py
data/dough/dev/silver/   ← CSVs locales por tabla
data/olb/dev/silver/
      ↓  build_fact_transactions.py
data/dough/fact_transactions.csv   ← tabla unificada de transacciones
      ↓  run_smart_budget_prep.py
data/dough/smart_budget_prep.csv   ← datos filtrados y agregados por mes
      ↓  run_methods.py
sugerencias de presupuesto (WMA, EWMA, Median, Holt-Winters)
```

---

## Paso 1 — Extraer tablas desde S3

El script `scripts/extract_datalake_to_csv.py` descarga tablas parquet desde
el datalake S3 y las guarda como CSV locales.

### Buckets

| Entorno | Bucket S3 |
|---|---|
| `dev` (default) | `blossom-analytics-datalake-dev` |
| `alpha` | `blossom-analytics-datalake-alpha` |

### Comandos

```bash
cd /ruta/a/smart_budget

# Extraer solo DOUGH (silver) — mínimo necesario para Smart Budget
python3 scripts/extract_datalake_to_csv.py --source DOUGH --layer silver

# Extraer OLB (silver) — transacciones OLB
python3 scripts/extract_datalake_to_csv.py --source OLB --layer silver --workers 40

# Ver fuentes disponibles
python3 scripts/extract_datalake_to_csv.py --list

# Extraer una sola tabla
python3 scripts/extract_datalake_to_csv.py --source DOUGH --layer silver --table externaltransaction

# Entorno alpha
python3 scripts/extract_datalake_to_csv.py --source DOUGH --layer silver --env alpha
```

### Output

Los CSVs se guardan en:

```
data/
├── dough/dev/silver/        ← tablas DOUGH
│   ├── externaltransaction.csv
│   ├── defaultcategory.csv
│   ├── member.csv
│   └── ...
└── olb/dev/silver/          ← tablas OLB
    ├── olbsubaccounttransaction.csv
    ├── olbloantransaction.csv
    ├── olbsubaccount.csv
    └── ...
```

> **Nota:** `data/` está en `.gitignore` — nunca commitear datos reales.

---

## Paso 2 — Construir `fact_transactions`

El script `scripts/build_fact_transactions.py` unifica las fuentes OLB y DOUGH
en una única tabla canónica de transacciones.

### Fuentes disponibles

| Fuente (`--source`) | Descripción | Cuándo usar |
|---|---|---|
| `db` **(recomendado)** | Lee directo desde `blossom-dough-consolidated-dev` (Postgres) | Datos idénticos al equipo DE |
| `s3` | Construye desde los CSVs del Paso 1 | Offline o sin acceso a la DB |

```bash
# Fuente DB (recomendado)
python3 scripts/build_fact_transactions.py --source db

# Fuente S3 (offline)
python3 scripts/build_fact_transactions.py --source s3 --env dev
```

### Credenciales DB (fuente `db`)

```bash
export DB_HOST=blossomdoughconsolidatedrdsencrypt-dev-cluster.cluster-csls5euwsof9.us-east-2.rds.amazonaws.com
export DB_NAME=blossom-dough-consolidated-dev
export DB_USER=<usuario>
export DB_PASS=<password>
```

### Output

```
data/dough/fact_transactions.csv                ← tabla completa (~1.4M filas en dev)
data/dough/fact_transactions_expenditure.csv    ← solo gastos (ya filtrada)
data/dough/fact_transactions_sample.csv         ← muestra aleatoria 50k filas
```

### Esquema de `fact_transactions`

| Columna | Tipo | Descripción |
|---|---|---|
| `idtransaction` | `string` | ID único. Prefijo indica fuente: `SUB*`, `LOAN*` (OLB), `EXT*` (Dough externo) |
| `idclient` | `string` | ID del cliente (nivel top de multi-tenancy) |
| `idcompany` | `string` | ID de la Credit Union |
| `idaccount` | `string` | ID de la cuenta del miembro |
| `idcategory` | `string` | ID interno de categoría |
| `defaultcategory` | `string` | Nombre de categoría (e.g. `GROCERIES`, `Food & Dining`) |
| `incomeexpenditure` | `string` | `expenditure` o `income` |
| `amount` | `float` | Monto de la transacción (puede ser negativo si es reembolso) |
| `date` | `date` | Fecha de la transacción |
| `status` | `string` | Estado: `POSTED`, `PENDING`, `HOLD`, etc. |
| `deletedat` | `datetime \| null` | Timestamp de soft delete; `null` = activa |

---

## Paso 3 — Filtrar y agregar (`smart_budget_prep.csv`)

El script `scripts/run_smart_budget_prep.py` aplica las **5 reglas de filtrado**
obligatorias y agrega las transacciones por mes.

```bash
python3 scripts/run_smart_budget_prep.py \
    --input data/dough/fact_transactions.csv \
    --output data/dough/smart_budget_prep.csv \
    --min-months 3
```

---

## Reglas de filtrado (obligatorias — nunca bypassear)

Estas reglas se aplican en `src/smart_budget/filters.py` → `filter_transactions()`.
**Son no negociables.** Bypassearlas produce sugerencias incorrectas o con datos inválidos.

### Regla 1 — Soft delete

```python
df = df[df["deletedat"].isna()]
```

| Columna | Condición | Resultado |
|---|---|---|
| `deletedat` | `IS NULL` | ✅ Incluir |
| `deletedat` | Tiene valor (timestamp) | ❌ Excluir |

> Las transacciones marcadas como eliminadas no representan gasto real del usuario.

### Regla 2 — Solo gastos (`expenditure`)

```python
df = df[df["incomeexpenditure"] == "expenditure"]
```

| Valor | Resultado |
|---|---|
| `expenditure` | ✅ Incluir |
| `income` | ❌ Excluir |
| Cualquier otro valor | ❌ Excluir |

> Los ingresos no se presupuestan en Fase 0. Solo gastos discrecionales.

### Regla 3 — Categorías válidas

```python
EXCLUIDAS = {"UNCATEGORIZED", "INCOME", "MONEY_SENT"}
df = df[df["defaultcategory"].notna()]
df = df[~df["defaultcategory"].isin(EXCLUIDAS)]
```

| Categoría | Resultado | Razón |
|---|---|---|
| `UNCATEGORIZED` | ❌ Excluir | Sin categoría asignada — no presupuestable |
| `INCOME` | ❌ Excluir | Es ingreso, no gasto |
| `MONEY_SENT` | ❌ Excluir | Transferencias internas (legacy OLB/Ntropy) |
| `null` / `None` | ❌ Excluir | Sin categoría |
| Cualquier otra categoría válida | ✅ Incluir | — |

### Regla 4 — Estado de transacciones OLB (`SUB*` / `LOAN*`)

```python
is_olb = df["idtransaction"].str.startswith(("SUB", "LOAN"))
olb_invalid = is_olb & df["status"].notna() & df["status"].str.upper().isin(["PENDING", "HOLD"])
df = df[~olb_invalid]
```

Aplica solo cuando `idtransaction` empieza con `SUB` o `LOAN`.

| `status` | Resultado |
|---|---|
| `NULL` / vacío | ✅ Incluir (confirmada en el core bancario) |
| `PENDING` | ❌ Excluir |
| `HOLD` | ❌ Excluir |
| Cualquier otro valor | ✅ Incluir |

### Regla 5 — Estado de transacciones externas Dough (`EXT*`)

```python
is_ext = df["idtransaction"].str.startswith("EXT")
ext_invalid = is_ext & (df["status"].str.upper() != "POSTED")
df = df[~ext_invalid]
```

Aplica solo cuando `idtransaction` empieza con `EXT` (Plaid / Finicity).

| `status` | Resultado |
|---|---|
| `POSTED` (case-insensitive) | ✅ Incluir |
| `PENDING` | ❌ Excluir |
| `FAILED` | ❌ Excluir |
| `CANCELLED` | ❌ Excluir |
| Cualquier otro valor | ❌ Excluir |

> **Fuentes sin prefijo conocido** (ni SUB, LOAN, ni EXT): pasan sin filtro de status
> para evitar pérdida silenciosa de datos. Se emite warning en log.

---

## Reglas de agregación mensual

Después del filtrado, `aggregate_monthly()` en `src/smart_budget/aggregator.py`
agrupa las transacciones por mes calendario.

### Agrupación

```
GROUP BY (idclient, idcompany, idaccount, idcategory, defaultcategory, period_yyyymm)
SUM(amount) → monthly_total
```

- `period_yyyymm` se deriva de la columna `date` como `"YYYY-MM"`.
- **Mes en curso:** se excluye del cálculo del modelo (solo meses calendario completos).

### Clamp de negativos

```python
monthly_total = max(monthly_total, 0.0)
```

Si la suma neta de un mes es negativa (reembolsos superan gastos), se clampea a `0.0`.
Nunca se emiten sugerencias negativas.

### Zero-fill

```python
zero_fill(df)
```

Se genera el grid completo `(cuenta × categoría) × todos_los_meses`.
Los meses sin transacciones se rellenan con `monthly_total = 0.0`.

- **Mes con $0 y cuenta activa:** se incluye como data point `= 0`.
- **Mes sin cuenta activa:** se excluye (ausencia, no cero).

### Gating mínimo

```python
apply_gating(df, min_months=3)  # configurable por CLI
```

Solo pasan las combinaciones `(idaccount, idcategory)` con al menos `min_months`
meses con `monthly_total > 0`. Los meses zero-filled no cuentan.

| Meses con gasto > 0 | Resultado |
|---|---|
| `< min_months` (default 3) | ❌ Excluir del cálculo |
| `>= min_months` | ✅ Incluir |

---

## Output del Paso 3

`data/dough/smart_budget_prep.csv` con esquema:

| Columna | Tipo | Descripción |
|---|---|---|
| `idclient` | `string` | Multi-tenancy: cliente |
| `idcompany` | `string` | Multi-tenancy: Credit Union |
| `idaccount` | `string` | Multi-tenancy: miembro |
| `idcategory` | `string` | ID interno de categoría |
| `defaultcategory` | `string` | Nombre de categoría |
| `period_yyyymm` | `string` | Mes agregado (formato `YYYY-MM`) |
| `monthly_total` | `float ≥ 0` | Gasto total del mes (clampeado a 0 si era negativo) |

---

## Resumen del flujo completo

```bash
# 1. Credenciales
aws sso login --profile blossom-dev

# 2. Extraer silver desde S3
python3 scripts/extract_datalake_to_csv.py --source DOUGH --layer silver
python3 scripts/extract_datalake_to_csv.py --source OLB   --layer silver --workers 40

# 3. Construir fact_transactions (preferir --source db si hay acceso)
python3 scripts/build_fact_transactions.py --source db
# o sin acceso a DB:
# python3 scripts/build_fact_transactions.py --source s3 --env dev

# 4. Filtrar y agregar
PYTHONPATH=src python3 scripts/run_smart_budget_prep.py \
    --input data/dough/fact_transactions.csv \
    --output data/dough/smart_budget_prep.csv \
    --min-months 3

# 5. Ejecutar el modelo
PYTHONPATH=src python3 scripts/run_methods.py \
    --method wma \
    --treatment B \
    --reference-date 2026-05 \
    --lookback-months 3
```

---

## Restricciones de seguridad y PII

| Regla | Descripción |
|---|---|
| ❌ No commitear CSVs | `data/` está en `.gitignore`. Nunca commitear datos reales. |
| ❌ No loguear montos | Los logs de aplicación nunca incluyen `amount` individual ni `idaccount` en claro. |
| ✅ Multi-tenancy | Toda query y procesamiento filtra `idclient / idcompany / idaccount`. Nunca cross-tenant. |
| ✅ Escritura atómica | Los scripts usan `tmp_path → os.replace() → chmod(0o600)` al escribir CSVs. |
| ❌ No apuntar a prod | Las credenciales deben apuntar solo a `dev` o `alpha` durante desarrollo. |

---

## Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| `NoCredentialsError` | Sesión AWS expirada | `aws sso login --profile blossom-dev` |
| Tabla no encontrada en S3 | La tabla no existe en esa capa/fuente | Usar `--list` para ver fuentes disponibles |
| `fact_transactions.csv` vacío | Tablas OLB o DOUGH no descargadas | Verificar que `data/olb/dev/silver/` y `data/dough/dev/silver/` tienen CSVs |
| `ModuleNotFoundError: smart_budget` | `PYTHONPATH` no configurado | Ejecutar con `PYTHONPATH=src` al inicio del comando |
| `monthly_total` negativo en output | Bug en clamp | No debería ocurrir — reportar como bug en `aggregator.py` |
| Pocas filas después del filtrado | Reglas 4/5 muy restrictivas | Verificar prefijos de `idtransaction` con `df['idtransaction'].str[:3].value_counts()` |

---

## Backlinks

- [[How-To-Run-Pipeline]] — pipeline completo de sugerencias (paso siguiente)
- [[How-To-Use-Endpoint]] — servir sugerencias via API local
- `src/smart_budget/filters.py` — implementación de las 5 reglas
- `src/smart_budget/aggregator.py` — agregación mensual, zero-fill, gating
- `scripts/extract_datalake_to_csv.py` — extracción S3 → CSV
- `scripts/build_fact_transactions.py` — construcción de fact_transactions
- `scripts/run_smart_budget_prep.py` — pipeline de preparación
