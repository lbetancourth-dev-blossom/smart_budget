# Smart Budget

Repositorio del módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual.

---

## Estado

### Fase 0 ✅ COMPLETADA

| Ticket | Descripción | Estado |
|--------|-------------|--------|
| `DATA-1136` | Preparación de datos: filtros, agregación mensual, gating | ✅ Merged |
| `DATA-1137` | Dataset sintético para pruebas | ✅ Merged |
| `DATA-1138` | Evaluación de métodos: WMA, EWMA, mediana, Holt-Winters | ✅ Merged — **WMA Treatment B seleccionado** |
| `DATA-1139` | Datasets de test por fuente (internal / external) | ✅ Merged |
| `DATA-1140` | Endpoint on-demand de inferencia (FastAPI + SageMaker) | ✅ Merged |

**Fase 0 cerrada el 2026-05-19.** Todos los tickets en `development`. Cobertura de tests: ~93%.

### En progreso

| Ticket | Descripción | Estado |
|--------|-------------|--------|
| `DATA-1179` | Dataset real desde DB + grain `idmember` + entornos dev/alpha | 🔄 Draft PR #12 |

**DATA-1179:** migra el modelo de `idaccount` → `idmember`, extrae datos reales desde la DB (dev: 26,417 filas / 421 miembros · alpha: 195,923 filas / 2,929 miembros), y agrega soporte de entornos `dev`/`alpha` en el endpoint y SageMaker. Cobertura de tests: **133 passed, 4 skipped**.

---

## Método seleccionado: WMA Treatment B · lb=3

`DATA-1138` evaluó 4 métodos × 4 lookbacks (16 configuraciones) con split temporal: train Jun2025–Mar2026, holdout Apr2026 (73 buckets reales). Métrica de selección: **CRWS** (Composite Relative Weighted Score — mayor es mejor).

### Ranking por CRWS (top 9)

| # | Método | lb | CRWS | MAE | MAE regular | MAE estacional | null% |
|---|---|---|---|---|---|---|---|
| **1** | **WMA-B** ✅ | **3** | **0.5372** | **$48.63** | **$39.95** | $176.62 (4 buckets) | 7.35% |
| 2 | EWMA-B | 3 | 0.5174 | $50.53 | $41.97 | $176.81 | 7.35% |
| 3 | Median-B | 3 | 0.4947 | $52.70 | $44.28 | $176.81 | 7.35% |
| 4 | EWMA-B | 6 | 0.3763 | $80.92 | $44.20 | $395.66 | 1.47% |
| 5 | EWMA-B | 9 | 0.3091 | $113.87 | $44.83 | $631.64 | 0.00% |
| 6 | WMA-B | 6 | 0.3053 | $93.47 | $54.41 | $428.32 | 1.47% |
| 7 | Median-B | 6 | 0.2870 | $91.31 | $57.04 | $385.04 | 1.47% |
| 8 | Holt-Winters-B | 6 | 0.2857 | $63.01 | $51.73 | $280.96 | 10.29% |
| 9 | EWMA-B | 12 | 0.2679 | $100.75 | $44.79 | $520.47 | 0.00% |

### Método seleccionado: WMA-B lb=3

- **Mejor CRWS (0.5372):** +3.8% sobre EWMA lb=3, +87% sobre Median lb=6
- **Menor MAE ($48.63):** 47% mejor que Median lb=6 ($91.31)
- **Mejor MAE regular ($39.95):** 30% más preciso en categorías de gasto frecuente (Groceries, Gas, Food & Dining)
- **null_rate 7.35% ya penalizado en CRWS** — no es un disqualifier externo

> **Limitación conocida:** con lb=3 solo se evalúan 4/8 buckets estacionales. Fase 1 implementará selección adaptativa: WMA lb=3 para categorías regulares, Median lb=6 para estacionales (Travel, Gifts, Education).

> **Treatment B:** excluye meses con $0 — calcula solo sobre meses con gasto real.
> **lookback=3:** usa los últimos 3 meses calendario completos antes del mes presupuestado.

---

## Arquitectura del pipeline

```
DB blossom-dough-consolidated (dev | alpha)
    │
    ├── scripts/extract_smart_budget_monthly.py  → data/dough/smart_budget_db_{env}.csv
    │        SQL directo a la DB — sin S3
    │
    ├── scripts/build_fact_transactions.py       → data/dough/fact_transactions.csv (referencia histórica)
    │        (legado — usado para análisis sobre fact_transactions completa)
    │
    ├── scripts/run_smart_budget_prep.py         → data/dough/smart_budget_prep.csv (agregado mensual)
    │
    └── scripts/run_methods.py                   → data/dough/results/<method>_results.csv
         │   method=wma, treatment=B, lookback=3 (grain: idmember)
         ▼
    SB_ENV=dev|alpha
    GET /smart-budget/suggestion?idmember=...&period_id=YYYY-MM   ← src/api/router.py (FastAPI)
    ▲                                                              ← src/sagemaker/inference.py (SageMaker)
    │
    Dough UI
```

**Modo de operación:** batch pre-calculado. El endpoint lee el CSV del entorno activo (`SB_ENV`) y ejecuta el pipeline por request. En Fase 1 se materializa en tabla `smartBudgetSuggestion`.

---

## Endpoint de inferencia

### Local (FastAPI)

```bash
# Entorno dev (top-10 miembros con sugerencias reales)
SB_ENV=dev PYTHONPATH=$(pwd)/src uvicorn src.main:app --reload --port 8000

# Entorno alpha
SB_ENV=alpha PYTHONPATH=$(pwd)/src uvicorn src.main:app --reload --port 8001

# Swagger UI: http://localhost:8000/docs  (dropdown con miembros reales del entorno)
```

```bash
# Sugerencias para un miembro (todas las categorías)
curl "http://localhost:8000/smart-budget/suggestion?idmember=11393&period_id=2026-05"

# Sin datos suficientes → suggested_amount: null en cada categoría (HTTP 200)
curl "http://localhost:8000/smart-budget/suggestion?idmember=30&period_id=2026-05"
```

La variable `SB_ENV` selecciona el dataset activo al startup:

| `SB_ENV` | Dataset | Miembros | Período |
|----------|---------|----------|---------|
| `dev` | `smart_budget_db_dev.csv` | 421 | 2022-09 → 2026-05 |
| `alpha` | `smart_budget_db_alpha.csv` | 2,929 | 2019-06 → 2026-06 |

### Reglas de validación del endpoint

| # | Condición | Respuesta |
|---|-----------|-----------|
| 1 | `idmember` no existe en los datos | HTTP 404 — `member not found` |
| 2 | Sin datos suficientes para una categoría | HTTP 200 — `suggested_amount: null` |
| 3 | `period_id` con formato inválido | HTTP 422 — validation error |

### Respuesta de ejemplo

```json
{
  "idmember": "11393",
  "period_id": "2026-05",
  "idclient": "1",
  "idcompany": "1",
  "total_suggested": 285.50,
  "suggestions": [
    {
      "category_id": "cat_groceries",
      "defaultcategory": "Groceries",
      "suggested_amount": 185.50,
      "confidence": "medium",
      "display_label": "Basado en tus últimos 3 meses",
      "basis": {
        "months_analyzed": 3,
        "data_points": 3,
        "method": "wma",
        "treatment": "B",
        "period_range": "2026-02~2026-04"
      },
      "model_version": "fase0-v1"
    }
  ]
}
```

**Niveles de `confidence`:** `high` (≥6 meses) · `medium` (3–5 meses) · `low` (2 meses) · `null` (sin datos).

---

## Reglas de filtrado (obligatorias)

```python
# INCLUIR
status     == 'Posted'    # Nunca Pending, Cancelled, Hold
tipo       == 'expense'   # Solo gastos (expenditure), no income
deletedat  IS NULL        # Excluir soft-deleted

# EXCLUIR
defaultcategory IN ('UNCATEGORIZED', None, 'INCOME', 'MONEY_SENT')
tipo_transaccion IN ('Internal', 'Member-to-Member')
```

Implementadas en `src/smart_budget/filters.py`. **Nunca bypassear.**

---

## Estructura del repo

```
smart_budget/
├── src/
│   ├── main.py                          Entrypoint FastAPI
│   ├── api/
│   │   ├── router.py                    Endpoint GET /smart-budget/suggestion (SB_ENV dev|alpha)
│   │   └── CLAUDE.md
│   ├── sagemaker/
│   │   ├── inference.py                 Script SageMaker — contrato {idmember, period_id}
│   │   ├── requirements.txt             Pins para imagen sklearn:1.2-1
│   │   └── CLAUDE.md
│   └── smart_budget/
│       ├── filters.py                   6 reglas de filtrado obligatorias
│       ├── aggregator.py                Agregación mensual (grain: idmember) + zero-fill + gating
│       ├── model.py                     4 métodos + compute_budget_suggestions() + total_suggested
│       └── loader.py                    Carga CSVs con parámetro csv_name opcional
├── scripts/
│   ├── extract_datalake_to_csv.py       (legado) Extrae S3 datalake → CSV local
│   ├── extract_smart_budget_monthly.py  Extrae datos reales desde DB → smart_budget_db_{env}.csv
│   ├── build_fact_transactions.py       Construye fact_transactions (OLB + DOUGH) con _resolve_idmember
│   ├── run_smart_budget_prep.py         Pipeline: filtra, agrega, gating
│   ├── extract_test_datasets.py         Split por fuente: internal / external
│   ├── eval_runner.py                   Evaluación comparativa de métodos
│   ├── run_methods.py                   CLI del modelo (output: idmember + total_suggested)
│   └── generate_synthetic_dataset.py   Dataset sintético para pruebas
├── notebooks/
│   └── smart_budget_sagemaker_endpoint.ipynb  Deploy SageMaker dev/alpha (cambiar celda ENV)
├── tests/
│   ├── unit/
│   │   ├── test_filters.py
│   │   ├── test_aggregator.py
│   │   ├── test_model.py
│   │   ├── test_api.py
│   │   ├── test_loader.py
│   │   ├── test_inference.py            8 TCs — contrato {idmember, period_id}
│   │   ├── test_build_fact_transactions_idmember.py
│   │   ├── test_prep_idmember.py
│   │   ├── test_multitenancy.py         Cross-member y cross-company leak detection
│   │   └── test_golden_set.py
│   └── fixtures/
│       ├── golden_set.csv               Re-frozen con schema idmember (3 miembros, 6 períodos)
│       └── generate_golden_set.py       Script generador del golden set
├── data/                               Gitignored — nunca commitear
│   └── dough/
│       ├── smart_budget_db_dev.csv      Dataset real dev (26,417 filas, 421 miembros)
│       ├── smart_budget_db_alpha.csv    Dataset real alpha (195,923 filas, 2,929 miembros)
│       ├── fact_transactions.csv        Tabla central: 1.4M filas
│       └── smart_budget_prep.csv        Datos listos para el modelo
└── docs/
    ├── fact_transactions_README.md
    ├── guides/smart-budget/
    │   ├── How-To-Use-Endpoint.md
    │   ├── EDA-Smart-Budget-Dataset-Dev.md    EDA dataset dev
    │   └── EDA-Smart-Budget-Dataset-Alpha.md  EDA dataset alpha
    └── codemap/
```

---

## Setup y ejecución

```bash
# 1. Entorno virtual
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# 2. Tests
pytest tests/ -v --cov=src/smart_budget --cov-report=term-missing

# 3. Datos reales desde DB (requiere AWS SSO)
aws sso login --profile blossom-dev
python scripts/extract_smart_budget_monthly.py --env dev   # → data/dough/smart_budget_db_dev.csv
python scripts/extract_smart_budget_monthly.py --env alpha # → data/dough/smart_budget_db_alpha.csv

# 4. Ejecutar modelo
python scripts/run_methods.py --method wma --treatment B --lookback-months 3 --reference-date 2026-05

# 5. Endpoint local
SB_ENV=dev PYTHONPATH=$(pwd)/src uvicorn src.main:app --reload --port 8000
# → http://localhost:8000/docs  (dropdown con miembros reales del entorno dev)

# SageMaker — ver notebooks/smart_budget_sagemaker_endpoint.ipynb
# Cambiar ENV = "dev" | "alpha" en la celda 2 del notebook
```

---

## Catálogo de categorías

Smart Budget **solo opera sobre Grupo 1 (Expenses)**. Grupos 2–4 se excluyen del modelo.

| Grupo | Categorías | Incluidas |
|-------|-----------|-----------|
| 1 — Expenses | Auto & Transport, Bills & Utilities, Business Services, Education, Entertainment & Leisure, Financial Services, Food & Dining, Groceries, Gifts & Donations, Health & Fitness, Home & Rent, Kids & Family, Personal Care & Beauty, Pets, Shopping, Subscriptions, Taxes & Fees, Travel & Trips, Gas, Transfers & Payments | ✅ |
| 2 — Incomes | Business Income, Income | ❌ |
| 3 — Excluded | Internal Transfers, Credit Card Payment, Loan Payment, ATM & Cash, Savings & Investments | ❌ |
| 4 — Other | Other (`shouldshow = false`) | ❌ |

---

## Documentación clave

| Documento | Para qué |
|---|---|
| [`docs/guides/smart-budget/How-To-Use-Endpoint.md`](docs/guides/smart-budget/How-To-Use-Endpoint.md) | Uso completo del endpoint: local, SageMaker, TCs, curls |
| [`docs/fact_transactions_README.md`](docs/fact_transactions_README.md) | Schema de `fact_transactions` |
| [`changes/archive/2026-05-14-DATA-1138/plan.md`](changes/archive/2026-05-14-DATA-1138/plan.md) | Evaluación de métodos y decisión WMA-B |
| [`changes/archive/2026-05-12-DATA-1136/plan.md`](changes/archive/2026-05-12-DATA-1136/plan.md) | Decisiones de filtrado y preparación de datos |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Convenciones, restricciones legales, casos edge |

---

## Restricciones legales

- **No robo-adviser (SEC):** el sistema sugiere basado en historial — nunca recomienda qué hacer.
- **UDAAP / CFPB:** `display_label` neutral y descriptivo. ❌ "Deberías gastar menos en X".
- **Multi-tenancy:** toda operación filtrada por `idClient / idCompany / idMember`.
- **Section 1033:** datos de Plaid/Finicity con reglas de portabilidad — no borrar sin revisión.
- **PII:** nunca loguear montos individuales ni IDs sin hashear (SHA-256 + `SB_LOG_SALT`).

---

## Contacto

- **Producto:** David Segovia (Analytics).
- **DS-ML:** Landneyker.
