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

## Stack y arquitectura

| Capa | Tecnología |
|---|---|
| Warehouse (fuente) | Redshift / S3 |
| Pipeline ETL | dbt + Python (o SQL puro en Redshift) |
| Serving | BlossomAPI (REST) |
| Frontend | Dough UI (no está en este repo) |
| Orquestación | Airflow (batch nocturno o mensual) |

Flujo de datos:

```
Redshift (raw transactions)
  → ETL / filtros
  → Agregación: member × category × month
  → Modelo: mediana por categoría
  → Tabla: smartBudgetSuggestion
  → BlossomAPI (GET /smart-budget/suggestion)
  → Dough UI (muestra sugerencia al usuario)
  → BlossomAPI (POST /smart-budget/decision)
  → Tabla: smartBudgetSuggestionLog
```

---

## Modelo de datos — tablas clave (Redshift)

```
transaction          → eventos financieros base
transactionSplit     → unidad real de agregación por categoría (un tx puede tener N splits)
userCategoryTransaction → vínculo tx ↔ categoría asignada por el usuario
category             → catálogo: globales (Blossom) + personalizadas por usuario
defaultCategory      → categorías base globales

-- Output DS-ML:
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
tipo_transaccion NOT IN ('Internal', 'Member-to-Member')
categoria        != 'Uncategorized'
estado           IN ('Pending', 'Failed', 'Cancelled')
```

Referencia: `docs/DECISIONS.md` · Q6, Q8, Q3

---

## Lógica del modelo — Mediana simple

```python
# Para cada (member_id, category_id):
#   1. Obtener meses calendario COMPLETOS con gasto > 0 en los últimos N meses
#   2. Gating: si count(meses) < 2 → no sugerir (campo vacío + mensaje)
#   3. Si count(meses) >= 2 → suggested_amount = median(monthly_amounts)
#
# N = configurable por CU (default: 6, rango: 3–24)
# Mes en curso: EXCLUIR del cálculo (solo meses calendario completos)
# Mes con $0 y cuenta activa: incluir como data point = 0
# Mes sin cuenta activa: excluir (ausencia, no cero)
```

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

Reglas de `confidence`:
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
  model_version     VARCHAR(50),
  calculated_at     TIMESTAMP DEFAULT NOW()
);

-- Loop de retroalimentación (capturar desde día 1, aunque no se use en Fase 0)
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
  ts_presented              TIMESTAMP,
  ts_confirmed              TIMESTAMP,
  model_version             VARCHAR(50)
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

**Ejemplos de copy válida:** "Basado en tus últimos 3 meses" ✅  
**Ejemplos de copy inválida:** "Deberías gastar menos en X" ❌ · "Gastas más que el promedio" ❌

---

## Casos edge que el código debe manejar

```
1. Usuario con < 2 meses de historial en una categoría → no sugerir, retornar null
2. CU sin RICH (Ntropy) activo → solo categorías base de Blossom disponibles
3. Categoría 'Uncategorized' → nunca recibe sugerencia
4. Cuenta externa desconectada (Plaid off) → conservar histórico en warehouse (no borrar)
5. Reembolso (REF) → reduce el gasto neto del mes (signo negativo, no descartar)
6. transactionSplit con monto 0 → incluir en conteo de splits pero no inflar monto
7. T&C no aceptados por el usuario → no servir sugerencia
```

---

## Métricas de Fase 0 (qué hay que poder medir)

```
acceptance_rate       = sugerencias aceptadas sin cambio / total sugerencias presentadas
edit_rate             = sugerencias modificadas / total sugerencias presentadas
abandonment_rate      = usuarios que inician setup pero no completan / total que inician
time_to_budget        = timestamp(setup completo) - timestamp(inicio flujo)
coverage              = categorías con sugerencia / total categorías del usuario
```

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
```

---

## Archivos de referencia en este repo

```
docs/PRD_SMART_BUDGET.md        → PRD completo (Fases 0–3)
docs/ARCHITECTURE.md            → Diagrama del pipeline DS-ML
docs/DECISIONS.md               → Decision Log del Top 12 (resolución de preguntas bloqueantes)
docs/DATA_CONTRACT.md           → Schema JSON del output versionado
```
