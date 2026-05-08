# GitHub Copilot — Smart Budget · Fase 0 (MVP)

## Qué es este proyecto

**Smart Budget** es un módulo del producto **Dough** (PFM de Blossom), que vive dentro del OLB
de Credit Unions americanas. Resuelve el problema del "presupuesto en blanco": en lugar de que
el usuario adivine cuánto poner en cada categoría, el sistema calcula una sugerencia basada en
su propio historial transaccional.

**Fase 0 — El Reflejo:** implementación MVP. El modelo no inventa — refleja el comportamiento
pasado del usuario mediante una mediana simple. Sin ML complejo, sin benchmarking, sin
recomendaciones.

Repositorio de referencia de documentos: `docs/`

---

## Origen de datos (real)

```
S3 bucket:    s3://blossom-analytics-datalake-alpha/datalake/{bronze,silver}/DOUGH/
AWS profile:  blossom-dev
Capas:        bronze (raw CDC desde DMS) · silver (limpia, sin metadata DMS) · gold (vacía hoy)
```

- **Lectura del modelo:** capa silver (no bronze).
- **Materialización del output DS-ML:** capa gold (a crear) o BlossomAPI.
- **Entorno actual:** alpha. Volumen mínimo (2 CUs, 14 members, 0 transacciones reales).
- **Tablas transaccionales (`transaction`, `transactionSplit`, `userCategoryTransaction`, `account`)
  no están todavía en el lake alpha.** Cuando se incorporen, los pipelines deben asumir el mismo
  prefijo S3 y la misma estructura medallion.

Para más detalle, ver `docs/data_review.md` §0 y §4.

---

## Stack y arquitectura

| Capa | Tecnología |
|---|---|
| Warehouse (fuente) | Redshift / S3 |
| Pipeline ETL | dbt + Python (o SQL puro en Redshift) |
| Serving | BlossomAPI (REST) |
| Frontend | Dough UI (no está en este repo) |
| Orquestación | Airflow (batch nocturno o mensual) |

**Modo de operación: batch + serving.** El pipeline pre-calcula sugerencias en tabla; la API solo
lee. Nunca calcular en tiempo de request.

Flujo de datos:

```
S3 (bronze) → S3 (silver, dbt staging)
  → Agregación: member × category × month
  → Modelo: mediana por categoría
  → S3 (gold) / Tabla: smartBudgetSuggestion (idempotente: upsert por clave única)
  → BlossomAPI (GET /smart-budget/suggestion)
  → Dough UI (muestra sugerencia al usuario)
  → BlossomAPI (POST /smart-budget/decision)
  → Tabla: smartBudgetSuggestionLog (append-only, nunca update/delete)
```

---

## Convenciones de código

### Python
- **Versión:** Python 3.11+
- **Formato:** `black` (línea 100)
- **Linter:** `ruff`
- **Type hints obligatorios** en funciones públicas y modelos.
- **Docstrings:** estilo Google.
- **Tests:** `pytest` + `pytest-cov`. Cobertura mínima 80% en módulos de filtrado y cálculo.
- **Comentarios:** en español (consistencia con la documentación del producto).
- **Logs:** `structlog` con campos estructurados, nunca `print`.

### SQL / dbt
- Keywords en MAYÚSCULAS (`SELECT`, `FROM`, `WHERE`).
- Identificadores en `snake_case`.
- Usar CTEs antes que subqueries anidadas.
- Modelos dbt con `unique_key` declarado y tests `not_null` / `unique` / `relationships`.
- Materializaciones: `incremental` para agregados mensuales, `table` para output final.

### Naming
- Tablas: `snake_case` (`smart_budget_suggestion`).
- Columnas: `snake_case` (`id_member`, `suggested_amount`).
- Variables Python: `snake_case`.
- Constantes: `UPPER_SNAKE_CASE` (`MIN_MONTHS_FOR_SUGGESTION = 2`).

### Estructura del repo
```
src/
  smart_budget/
    pipeline/         → jobs Airflow + tareas
    models/           → dataclasses / Pydantic models
    queries/          → SQL templates parametrizados
    aggregator.py     → lógica de mediana y confidence
    filters.py        → reglas de filtrado (Posted, Expense, etc.)
    api/              → handlers BlossomAPI (si aplica desde este repo)
tests/
  unit/
  integration/        → contra Redshift staging
  fixtures/           → golden sets (CSV o JSON)
docs/
dbt/
  models/
    staging/          → apunta a silver
    marts/
      smart_budget/   → apunta a gold
data/
  dough/
    bronze/ silver/ gold/
scripts/
  extract_dough_to_csv.py
```

---

## Modelo de datos — tablas clave

### Tablas de lectura (silver)

```
-- Disponibles hoy en s3://...alpha/datalake/silver/DOUGH/
defaultcategory, categorygroup, companyntropycategory   → catálogo de categorías
client, company, member, termandcondition,
membertacacceptance                                     → multi-tenancy + compliance
accountclassification, defaulttypeaccount,
defaultaccountsubtype, companytypeaccount,
companyaccountsubtype, membertypeaccountorder           → taxonomía de cuentas
manualaccount, manualtransaction                        → cuentas/transacciones manuales
provider                                                → Finicity, Plaid

-- Esperadas / pendientes de replicación al lake (ver docs/data_review.md §4):
transaction              → eventos financieros base
transactionSplit         → unidad real de agregación por categoría
userCategoryTransaction  → vínculo tx ↔ categoría asignada por el usuario
category                 → categorías custom por usuario
account                  → cuentas externas (Plaid/Finicity)
budget, budgetCategory, budgetHistory   → estructura del budget al confirmar
```

### Tablas de escritura (output DS-ML)

```
smartBudgetSuggestion     → sugerencia calculada por (member, category, period)
smartBudgetSuggestionLog  → captura de la decisión del usuario (loop)
```

Jerarquía de multi-tenancy: `client → company (CU) → member → account → transaction`

**Toda query DEBE filtrar por `idClient`, `idCompany`, `idMember`. Nunca cross-user ni cross-CU.**

---

## Reglas de filtrado (obligatorias, no negociables)

```python
# INCLUIR
estado       == 'Posted'          # Nunca Pending, Failed ni Cancelled
tipo_expense == True              # Solo categorías de tipo Expense (no Income, no Others)
unidad       == transactionSplit  # Agregar por split, no por transaction

# EXCLUIR
tipo_transaccion NOT IN ('Internal', 'Member-to-Member', 'SIG')
categoria        != 'Uncategorized'
estado           IN ('Pending', 'Failed', 'Cancelled')
```

Referencia: `docs/DECISIONS.md` · Q6, Q8, Q3 (a crear conforme se cierren las decisiones).

---

## Lógica del modelo — Mediana simple

```python
# Para cada (member_id, category_id):
#   1. Obtener meses calendario COMPLETOS con gasto > 0 en los últimos N meses
#   2. Gating: si count(meses) < 2 → no sugerir (campo vacío + mensaje)
#   3. Si count(meses) >= 2 → suggested_amount = median(monthly_amounts)
#   4. Redondear a 2 decimales (cent precision)
#
# N = configurable por CU (default: 6, rango: 3–24)
# Mes en curso: EXCLUIR del cálculo (solo meses calendario completos)
# Mes con $0 y cuenta activa: incluir como data point = 0
# Mes sin cuenta activa: excluir (ausencia, no cero)
# Mes con suma neta negativa (REF > gastos): clamp a 0, no negativos
# Moneda: USD (asumido). Si llega otra moneda → log warning + skip.
# Time zone para boundaries de mes: UTC (alinear con warehouse) — confirmar vs timeZone CU.
```

### Idempotencia
Toda corrida del pipeline debe poder repetirse el mismo día sin duplicar filas.
La clave única en `smartBudgetSuggestion` es `(id_member, category_id, period_id, model_version)`.
Usar `INSERT ... ON CONFLICT DO UPDATE` o `MERGE` según motor.

### Snapshot freeze
Una sugerencia mostrada al usuario **nunca se modifica** retroactivamente.
Si el modelo recalcula con nuevos datos, se inserta una **fila nueva** con timestamp distinto.
Esto preserva la trazabilidad histórica para el loop y para auditoría.

---

## Contrato JSON de output (BlossomAPI)

```json
{
  "category_id": "string",
  "suggested_amount": 420.00,
  "basis": {
    "months_analyzed": 3,
    "method": "median",
    "data_points": 3,
    "period_range": "2025-11 ~ 2026-01"
  },
  "confidence": "high | medium | low",
  "display_label": "Basado en tus últimos 3 meses",
  "model_version": "fase0-v1"
}
```

**Aclaración de campos:**
- `months_analyzed`: número total de meses dentro de la ventana N considerados.
- `data_points`: número de meses con data efectiva usados para calcular la mediana
  (puede ser menor que `months_analyzed` si hay meses sin cuenta activa).

Reglas de `confidence` (Fase 0, basado solo en `data_points`):
- `high`   → ≥ 6 meses con data
- `medium` → 3–5 meses con data
- `low`    → 2 meses con data

Cuando no hay sugerencia (gating):
```json
{
  "category_id": "string",
  "suggested_amount": null,
  "basis": null,
  "confidence": null,
  "display_label": "No hay suficiente historial para esta categoría"
}
```

### Endpoints
```
GET  /smart-budget/suggestion?member_id=...&period_id=YYYY-MM
     → 200 con array de sugerencias (una por categoría) o array vacío
     → 404 solo si member no existe
     → Nunca 500 por falta de data — devolver array vacío y log

POST /smart-budget/decision
     Body: { member_id, category_id, period_id, original_suggested_amount,
             final_user_amount, accepted_without_change, ts_presented, ts_confirmed }
     → 201 al insertar en smartBudgetSuggestionLog
     → 200 idempotente si ya existe (mismo trio member+category+period+ts_presented)
```

---

## Schema de tablas de output

```sql
-- Sugerencias calculadas
CREATE TABLE smartBudgetSuggestion (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_client         VARCHAR NOT NULL,
  id_company        VARCHAR NOT NULL,   -- CU
  id_member         VARCHAR NOT NULL,
  category_id       VARCHAR NOT NULL,
  period_id         VARCHAR NOT NULL,   -- formato: YYYY-MM
  suggested_amount  DECIMAL(12,2),      -- NULL si no hay suficiente data
  months_analyzed   INT,
  data_points       INT,
  period_range      VARCHAR,
  confidence        VARCHAR(10),        -- high | medium | low | null
  display_label     VARCHAR(255),
  model_version     VARCHAR(50) NOT NULL,
  calculated_at     TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_suggestion UNIQUE (id_member, category_id, period_id, model_version)
);

CREATE INDEX idx_sb_lookup
  ON smartBudgetSuggestion (id_client, id_company, id_member, period_id);

-- Loop de retroalimentación (capturar desde día 1, aunque no se use en Fase 0)
-- APPEND-ONLY: nunca UPDATE ni DELETE.
CREATE TABLE smartBudgetSuggestionLog (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_client                VARCHAR NOT NULL,
  id_company               VARCHAR NOT NULL,
  id_member                VARCHAR NOT NULL,
  category_id              VARCHAR NOT NULL,
  period_id                VARCHAR NOT NULL,
  original_suggested_amount DECIMAL(12,2),
  final_user_amount         DECIMAL(12,2),
  accepted_without_change   BOOLEAN,
  ts_presented              TIMESTAMP NOT NULL,
  ts_confirmed              TIMESTAMP,
  model_version             VARCHAR(50) NOT NULL
);
```

---

## Restricciones legales (impactan el código y la copy)

| Restricción | Impacto en implementación |
|---|---|
| No robo-adviser (SEC) | El sistema NO puede recomendar qué hacer con el dinero |
| UDAAP / CFPB | `display_label` debe ser neutral y descriptivo, nunca prescriptivo |
| Multi-tenancy | Toda query filtrada por `idClient/idCompany/idMember` |
| Section 1033 | Datos de Plaid/Finicity: consultar política de retención antes de borrar |
| T&C aceptados | No servir sugerencia si el miembro no aceptó T&C de Dough |

**Ejemplos de copy válida:** "Basado en tus últimos 3 meses" ✅
**Ejemplos de copy inválida:** "Deberías gastar menos en X" ❌ · "Gastas más que el promedio" ❌

---

## Manejo de PII y logging

- **Nunca loguear** montos de transacciones individuales en logs de aplicación.
- **Sí loguear** agregados (mediana, count de meses, member_id en formato hasheado).
- **Member ID en logs:** hashear con SHA-256 + salt configurable (`SB_LOG_SALT`).
- **Toda corrida** del pipeline debe loguear: `job_id`, `model_version`, `n_members_processed`,
  `n_suggestions_emitted`, `started_at`, `finished_at`.
- **Nunca commitear** datos reales de members en fixtures de tests — usar fakers.

---

## Manejo de errores y degradación

```
1. Falla parcial del job → continuar con miembros restantes; reportar al final.
2. Schema drift en warehouse → fallar fast con mensaje claro, no silenciar.
3. Member sin transacciones en warehouse → no es error: emitir 0 sugerencias.
4. Categoría custom huérfana (sin defaultCategory) → loguear warning, no incluir.
5. Pipeline falla completo → API sirve la última corrida válida (no devolver vacío).
6. RICH apagado en una CU → emitir solo sugerencias sobre categorías base.
7. Moneda distinta a USD → skip + log warning (no implementado en Fase 0).
```

---

## Casos edge que el código debe manejar

```
1. Usuario con < 2 meses de historial en una categoría → no sugerir, retornar null
2. CU sin RICH (Ntropy) activo → solo categorías base de Blossom disponibles
3. Categoría 'Uncategorized' → nunca recibe sugerencia
4. Cuenta externa desconectada (Plaid off) → conservar histórico en warehouse (no borrar)
5. Reembolso (REF) → reduce el gasto neto del mes; suma negativa se clampa a 0
6. transactionSplit con monto 0 → incluir en conteo de splits pero no inflar monto
7. T&C no aceptados por el usuario → no servir sugerencia
8. Gasto bimodal (alquiler mensual + gastos diarios) → la mediana puede sentirse rara,
   está aceptado para Fase 0; outliers se atacan en Fase 2
9. Joint accounts / Team Owner-Member → la sugerencia se calcula por id_member;
   un Member solo recibe sugerencias sobre categorías que el Owner le habilitó
```

---

## Testing

```
unit/
  test_filters.py            → reglas de Posted, Expense, exclusiones
  test_aggregator.py         → mediana, gating, confidence, redondeo
  test_edge_cases.py         → casos 1-9 de la sección anterior
  test_idempotency.py        → re-runs del pipeline no duplican
  test_multitenancy.py       → leak detection: ningún cruce member/CU

integration/
  test_pipeline_redshift.py  → contra staging (datos sintéticos)
  test_api_contract.py       → JSON match con docs/DATA_CONTRACT.md

fixtures/
  golden_set.csv             → 50–100 miembros sintéticos con resultado esperado
```

Cualquier PR que toque `filters.py`, `aggregator.py` o queries de transacciones
**debe incluir un test nuevo o actualizar uno existente.**

---

## Métricas de Fase 0 (qué hay que poder medir)

```
acceptance_rate       = sugerencias aceptadas sin cambio / total sugerencias presentadas
edit_rate             = sugerencias modificadas / total sugerencias presentadas
abandonment_rate      = usuarios que inician setup pero no completan / total que inician
time_to_budget        = timestamp(setup completo) - timestamp(inicio flujo)
coverage              = categorías con sugerencia / total categorías del usuario
```

Definición de "aceptación sin modificación": **match exacto entre `original_suggested_amount`
y `final_user_amount`.** No aplicar tolerancia.

Umbral mínimo para pasar a Fase 1: `acceptance_rate + edit_rate > 60%`

---

## Lo que NO está en scope de Fase 0

```
❌ Ajuste por intención del usuario (es Fase 1)
❌ Estacionalidad o tendencia (es Fase 2)
❌ Exclusión de outliers / gastos extraordinarios
❌ Benchmarking o comparación entre usuarios
❌ Predicción de ingresos
❌ Notificaciones proactivas
❌ Recomendaciones explícitas de comportamiento
❌ Cálculo on-demand desde la API (siempre batch)
❌ Soporte multi-moneda
```

---

## Cosas que NUNCA debes hacer

```
❌ Bypassear filtros de multi-tenancy (idClient/idCompany/idMember)
❌ Loguear montos individuales o member IDs sin hashear
❌ UPDATE o DELETE sobre smartBudgetSuggestionLog (append-only)
❌ Modificar una sugerencia ya emitida (snapshot freeze: insertar nueva fila)
❌ Calcular sugerencias en tiempo de request (siempre batch)
❌ Asumir que todas las CUs tienen RICH activo
❌ Redondear el suggested_amount con un método no documentado (usar 2 decimales)
❌ Mezclar Pending con Posted en el agregado
❌ Generar copy prescriptiva ("deberías", "tienes que", "te conviene")
❌ Hardcodear N (ventana de meses) — leer de configuración por CU
❌ Apuntar el código a credenciales de prod sin revisión de PII
```

---

## Archivos de referencia en este repo

```
README.md                       → Onboarding al repo
docs/data_review.md             → Estado de bronze/silver/gold + diccionario + ER + gaps
docs/glosario.md                → Definiciones de términos del proyecto
docs/PRD_SMART_BUDGET.md        → PRD completo (a copiar desde Drive cuando aplique)
docs/ARCHITECTURE.md            → Diagrama del pipeline DS-ML (pendiente)
docs/DECISIONS.md               → Decision Log del Top 12 (pendiente)
docs/DATA_CONTRACT.md           → Schema JSON del output versionado (pendiente)
docs/COPY_GUIDELINES.md         → Lineamientos UDAAP para display_label (pendiente)
scripts/extract_dough_to_csv.py → Extracción S3 alpha → CSV local
```
