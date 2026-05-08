# Fase 0 — Tareas restantes para cerrar el alcance

**Fecha:** 2026-05-08
**Branch:** `DATA-1041`
**Documento padre:** [`plan_phase_0.md`](plan_phase_0.md)
**Tickets:** [DATA-1041](../ticket/DATA-1041.md) (en progreso) · [DATA-1066](../ticket/DATA-1066.md) (TO DO)

---

## Filosofía

Fase 0 es **validación**, no producción. Cuatro tareas concretas, agrupadas y simples — el detalle vive como sub-items.

> **Convención:** 1 día = 8h. Las horas son de trabajo activo, sin esperas por terceros. Las estimaciones asumen que se aprovecha el código ya existente (filters, aggregator, builders) y son mecánicas en buena parte.

---

## ✅ Estado actual

| Step | Estado |
|------|--------|
| Step 1 — Extracción DOUGH (30 dev + 23 alpha) | ✅ |
| Step 2 — Extracción OLB (7 tablas, 1.06M txns) | ✅ |
| Step 3 — `fact_transactions` (1,413,914 filas) | ✅ |
| Mediana + gating + confidence + builders + T&C gate | ✅ (sobre schema antiguo, requiere adaptación) |

---

# Tareas para cerrar Fase 0

## 1️⃣ Revisión y validación de datos · **12 h**

> Garantizar que `fact_transactions` está completo y es equivalente al consolidado que Dough muestra al usuario.

**Incluye:**

- **Adaptación al schema** (refactor mecánico de `filters.py`, `monthly_spend.sql`, `run_phase0.py` al schema canónico). Documentar el path `member ← fact_transactions` por `source` (OLB_SUB → `olbsubaccount.idmember`; OLB_LOAN → `olbloan.idmember`; DOUGH_EXT → `memberaccount` vía `idAccount`).
- **Mapping OLB → Dough** (`defaultCategory` string → `defaultcategory.id`). Identificar gaps con datos reales.
- **Filtro Posted** (confirmar con DE si `status NULL == Posted` en silver de OLB).
- **Sanity checks** (`idTransaction` único, totales mensuales, distribución por `source`, decisión sobre OLB_LOAN).
- **Equivalencia con Dough**: contrastar muestras de `fact_transactions` con lo que Dough muestra en Spending para los mismos members.
- **Output:** `docs/plan/data_validation_report.md`.

**Fundamento:** si la fuente está mal filtrada o categorizada, todos los métodos del modelo dan resultados incorrectos.

---

## 2️⃣ Implementación del modelo con múltiples métodos · **10 h**

> DATA-1041 lo permite explícitamente: *"Si DS considera que un promedio ponderado u otro método mejora el resultado frente a la mediana, puede adoptarlo"*.

**Incluye:**

- **Refactor del aggregator** a interfaz común: `calculate_suggestion(method='median' | 'weighted_avg_recency' | 'weighted_avg_volume' | 'trimmed_mean')`.
- **Mediana** (ya implementada — solo encajar en la interfaz).
- **Weighted average** con dos esquemas: recency-weighted (meses recientes pesan más) y volume-weighted (meses con más txs pesan más).
- **Trimmed mean** (descarta percentiles extremos antes de promediar).
- **Winsorización 10/10** aplicable a cualquier método (cumple DATA-1041: *"outliers deben suavizarse, no excluirse"*).
- **Constantes ajustadas a DATA-1041:** `MIN_MONTHS_FOR_SUGGESTION = 3`, `DEFAULT_WINDOW_N = 3`.

**Fundamento:** sin alternativas no se puede justificar la elección. Implementar 3-4 métodos comparables es la base para Tarea 3.

---

## 3️⃣ Evaluación y elección del mejor método · **10 h**

> Comparar métodos sobre los mismos datos y elegir uno con justificación cuantitativa.

**Incluye:**

- **Métricas de evaluación**:
  - **Estabilidad temporal** (varianza de la sugerencia mes a mes).
  - **Sensibilidad a outliers** (delta si quitas el mes más alto).
  - **Cobertura** (% de members × categorías con sugerencia).
  - **Plausibilidad** (% dentro del rango histórico observado).
- **Backtesting sencillo**: para cada método, predecir mes N usando 1..N-1 y comparar contra el real. Métrica: error absoluto medio.
- **Reporte comparativo**: tabla de métodos × métricas + visualizaciones.
- **Decisión documentada**: cuál se elige y por qué.

**Fundamento:** entregable explícito de DATA-1041: *"DS documenta el approach elegido y el razonamiento"*.

---

## 4️⃣ Documentación y presentación de resultados · **8 h**

> Trazabilidad, entregables formales del ticket y forma concreta de presentar a stakeholders.

**Incluye:**

- **`docs/MODEL_APPROACH.md`** — método elegido, manejo de outliers, desviaciones del baseline.
- **`docs/plan/data_validation_report.md`** (output de Tarea 1).
- **`docs/plan/method_comparison_report.md`** (output de Tarea 3).
- **Decision Records** breves en `docs/decisions/`:
  - `001-fact_transactions-as-source.md`
  - `002-window-and-gating-3-months.md`
  - `003-method-selection.md`
- **Cierre de tickets:**
  - DATA-1066 → mover a "Done" referenciando los archivos del repo.
  - DATA-1041 → comentario con resultado, archivos generados, pendientes para Fase 1+.

**Fundamento:** sin documentación nadie sabe por qué se eligió X. Entregables formales son obligatorios para cerrar DATA-1041.

---

# 📤 Cómo presentar el resultado de Fase 0

DATA-1041 acepta consumo *"vía API o query directa al warehouse"*. Para una **fase de validación** la combinación más útil es:

| Forma | Para quién | Esfuerzo | Pros |
|---|---|---|---|
| **Notebook Jupyter** | DS-ML interno, audit técnico | ~2 h | Combina código, resultado y plots. Ideal para revisión técnica. |
| **CSVs en `data/dough/test/query/`** | QA, Producto, Backend | ~0 h (ya existe) | Machine-readable, fácil de cargar en Excel/Sheets. |
| **Endpoint local FastAPI** | Producto, Backend Dough | ~3 h | Permite probar el contrato JSON real sin comprometer BlossomAPI productivo. Es la mejor forma de validar el shape antes de implementar el endpoint real. |
| **Reporte markdown** (`docs/plan/phase_0_results.md`) | Stakeholders no técnicos | ~2 h | Resumen ejecutivo con cifras clave y screenshots de visualizaciones. |

**Recomendación para Fase 0:** los cuatro formatos en paralelo. Total ~7 h adicionales, ya **incluidos en las tareas T3 y T4** (no es trabajo extra).

### Endpoint local FastAPI (sketch)

```python
# scripts/serve_local.py — endpoint de validación, NO producción
from fastapi import FastAPI
import pandas as pd

app = FastAPI(title="Smart Budget · Fase 0 (local)")

@app.get("/smart-budget/suggestion")
def get_suggestion(member_id: int, period_id: str):
    df = pd.read_csv("data/dough/test/query/budgetcategory.csv")
    rows = df[(df["idmember"] == member_id) & (df["period_id"] == period_id)]
    return {"suggestions": rows.to_dict(orient="records")}

# Levantar:  uvicorn scripts.serve_local:app --reload --port 8001
```

> Sirve el output del pipeline tal cual está en CSV. Permite a Producto y Backend probar el contrato JSON sin que tengamos que persistir en BD operativa.

---

# 🧪 Datos para test

Se usan **tres datasets** según el propósito:

| Dataset | Path | Uso | Volumen |
|---|---|---|---|
| **Sintético controlado** | `tests/fixtures/golden_set.csv` (a crear) | Tests unitarios del aggregator/filters: casos con resultado esperado calculado a mano. | 50-100 members sintéticos con casos: full data, gating, low confidence, outliers, mes en curso. |
| **Real dev (fact_transactions)** | `data/dough/fact_transactions.csv` | Validación del modelo, evaluación de métodos, backtesting. **Es el dataset principal de Fase 0.** | 1,413,914 filas reales de OLB + DOUGH dev (rango 2022–2026). |
| **Sample curado** | `data/dough/test/sample_members.csv` (a generar) | Reporte de Tarea 3 + auditoría manual + endpoint local de demo. | 10-20 members elegidos del real con histórico ≥ 6 meses y ≥ 3 categorías Expense activas. |

**Reglas:**

- **No usar prod en Fase 0** — la validación se hace con dev. Producción se reserva para piloto post-Fase 0.
- **Tests unitarios solo con fixtures sintéticas** — nunca commitear data real, ni siquiera anonimizada.
- **El sample curado** se persiste como CSV en el repo (es de dev, no PII real ni volumen comprometedor) para que la presentación al equipo sea reproducible.

---

## Resumen de estimaciones

| Tarea | Horas | Días |
|---|---|---|
| 1️⃣ Revisión y validación de datos | 12 h | 1.5 d |
| 2️⃣ Implementación de múltiples métodos | 10 h | 1.25 d |
| 3️⃣ Evaluación del mejor método | 10 h | 1.25 d |
| 4️⃣ Documentación y presentación | 8 h | 1 d |
| **Total Fase 0** | **40 h** | **5 días-persona** |

> Con 1 persona full-time: **~1 semana calendario** (con buffer del 30% por reuniones/esperas: ~6.5 días).
> Con 2 personas en paralelo: **~3 días** (T1+T2 paralelos en día 1-2; T3 día 3; T4 día 4).

---

## Roadmap recomendado

```
Día 1-2:    Tarea 1 (validación de datos)
            └── en paralelo: Tarea 2 (multi-método) si hay 2 personas
Día 3:      Tarea 3 (evaluación de métodos)
Día 4:      Tarea 4 (documentación + presentación + cierre tickets)
Día 5:      Buffer / revisión con stakeholders / endpoint local en demo
```

---

## Decisiones bloqueantes (Top 5)

Workshop de 30 min con DE + Backend Dough + Producto:

1. **Tarea 1** — ¿Path canónico `member ← fact_transactions` por `source`?
2. **Tarea 1** — ¿`status NULL == Posted` en silver de OLB?
3. **Tarea 1** — ¿OLB_LOAN se considera gasto?
4. **Tarea 1** — ¿"subcategory" en DATA-1041 = `defaultcategory` actual?
5. **Tarea 1** — ¿Time zone UTC o por CU?

---

## 📌 Anexo — Out of scope para Fase 0

Tareas registradas que **NO se ejecutan en Fase 0** y se reactivan en Fase 1 o launch real:

- DAG de Airflow productivo
- API REST en BlossomAPI productivo (`GET /smart-budget/suggestion`, `POST /smart-budget/decision`)
- Dashboard productivo (Looker / Metabase)
- Compliance review formal con legal (UDAAP / CFPB)
- Plan de rollout / shadow mode / soft launch / rollback con feature flag
- Performance / load testing
- Tests automatizados con cobertura ≥ 80%
- Loop de retroalimentación (`smartBudgetSuggestionLog`) — útil dejar el schema definido, no implementar
- Encuestas H0-1 a H0-4 — coordinar con Producto si se requiere
- Persistencia en BD operativa (`UPSERT` real)
- Acceso a datalake prod / replicación a alpha
