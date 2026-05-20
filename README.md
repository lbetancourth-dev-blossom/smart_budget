# Smart Budget

Repositorio del módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual.

---

## Estado — Fase 0 ✅ COMPLETADA

| Ticket | Descripción | Estado |
|--------|-------------|--------|
| `DATA-1136` | Preparación de datos: filtros, agregación mensual, gating | ✅ Merged |
| `DATA-1137` | Dataset sintético para pruebas | ✅ Merged |
| `DATA-1138` | Evaluación de métodos: WMA, EWMA, mediana, Holt-Winters | ✅ Merged — **WMA Treatment B seleccionado** |
| `DATA-1139` | Datasets de test por fuente (internal / external) | ✅ Merged |
| `DATA-1140` | Endpoint on-demand de inferencia (FastAPI + SageMaker) | ✅ Merged |

**Fase 0 cerrada el 2026-05-19.** Todos los tickets en `development`. Cobertura de tests: ~93% (107/108 passing).

---

## Método seleccionado: Median Treatment B · lb=6

`DATA-1138` evaluó 4 métodos × 4 lookbacks (16 configuraciones) con split temporal: train Jun2025–Mar2026, holdout Apr2026 (73 buckets reales). Métrica compuesta: **CRWS** (Composite Relative Weighted Score).

### Top configuraciones por CRWS

| Método | lb | MAE | Cobertura | null% | MAE estacional | MAE regular | CRWS |
|---|---|---|---|---|---|---|---|
| WMA-B | 3 | $48.63 | 86.3% | 7.35% | $176.62 | $39.95 | 0.5372 |
| EWMA-B | 3 | $50.53 | 86.3% | 7.35% | $176.81 | $41.97 | 0.5174 |
| Median-B | 3 | $52.70 | 86.3% | 7.35% | $176.81 | $44.28 | 0.4947 |
| EWMA-B | 6 | $80.92 | 91.8% | 1.47% | $395.66 | $44.20 | 0.3763 |
| WMA-B | 6 | $93.47 | 91.8% | 1.47% | $428.32 | $54.41 | 0.3053 |
| **Median-B** ✅ | **6** | **$91.31** | **91.8%** | **1.47%** | **$385.04** | **$57.04** | **0.2870** |
| Holt-Winters-B | 6 | $63.01 | 83.6% | 10.29% | $280.96 | $51.73 | 0.2857 |

> **Configuraciones lb=9/12** producen MAE > $100 y CRWS < 0.25 — descartadas.

### Método seleccionado para Fase 0

**Median + Treatment B + lookback=6** como default único:

- **Mejor MAE estacional** entre lb≥6: $385 vs $428 (WMA) y $395 (EWMA) — categorías de alta varianza (Travel, Gifts, Education) son el caso más difícil.
- **null_rate 1.47%** (1 bucket de 68) — prácticamente cobertura total.
- **Robustez ante outliers**: la mediana no se arrastra por meses de gasto extraordinario.
- lb=3 tiene mejor CRWS (0.53) pero con historial corto (7.35% nulls) — válido para usuarios nuevos, pero menos representativo con dataset completo.

> **Treatment B:** excluye meses con $0 del cálculo — usa solo meses con gasto real.
> **lookback=6:** usa los últimos 6 meses calendario completos antes del mes presupuestado.

---

## Arquitectura del pipeline

```
S3 silver (DOUGH + OLB)
    │
    ├── scripts/build_fact_transactions.py   → data/dough/fact_transactions.csv (1.4M filas)
    │
    ├── scripts/run_smart_budget_prep.py     → data/dough/smart_budget_prep.csv (agregado mensual)
    │
    ├── scripts/extract_test_datasets.py     → data/dough/test/test_internal.csv
    │                                           data/dough/test/test_external.csv
    │
    └── scripts/run_methods.py               → data/dough/results/<method>_results.csv
         │   method=wma, treatment=B, lookback=3
         ▼
    GET /smart-budget/suggestion             ← src/api/router.py (FastAPI)
    ▲                                        ← src/api/inference.py (SageMaker)
    │
    Dough UI
```

**Modo de operación:** batch pre-calculado. El endpoint carga CSVs locales y ejecuta el pipeline completo por request (Fase 0). En Fase 1 se materializa en tabla `smartBudgetSuggestion`.

---

## Endpoint de inferencia (DATA-1140)

### Local (FastAPI)

```bash
# Activar entorno y levantar servidor
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000

# Swagger UI: http://localhost:8000/docs
```

```bash
# Happy path
curl "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Food+%26+Dining&period_id=2026-05"

# Sin datos suficientes → suggested_amount: null (HTTP 200)
curl "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2026-05"
```

### Reglas de validación del endpoint

| # | Condición | Respuesta |
|---|-----------|-----------|
| 1 | `idaccount` no existe en los datos | HTTP 404 — `idaccount not found` |
| 2 | `defaultcategory` no válida (no es una categoría del catálogo) | HTTP 422 — `invalid category` |
| 3 | Cuenta y categoría existen, sin datos para el período | HTTP 200 — `suggested_amount: null` |

### Respuesta de ejemplo

```json
{
  "idaccount": "EXT2",
  "defaultcategory": "Food & Dining",
  "period_id": "2026-05",
  "suggested_amount": 184.32,
  "confidence": "high",
  "display_label": "Basado en tus últimos 3 meses",
  "basis": {
    "months_analyzed": 3,
    "data_points": 3,
    "method": "wma",
    "treatment": "B",
    "period_range": "2026-02~2026-04"
  },
  "amount_by_month": {
    "2026-04": 210.50,
    "2026-03": 175.00,
    "2026-02": 163.20
  },
  "model_version": "fase0-v1"
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
│   │   ├── router.py                    Endpoint GET /smart-budget/suggestion
│   │   ├── inference.py                 Handler SageMaker (misma lógica, protocolo SKLearnModel)
│   │   └── CLAUDE.md
│   ├── sagemaker/
│   │   ├── inference.py                 Script SageMaker (model_fn/input_fn/predict_fn/output_fn)
│   │   ├── requirements.txt             Pins para imagen sklearn:1.2-1
│   │   └── CLAUDE.md
│   └── smart_budget/
│       ├── filters.py                   5 reglas de filtrado
│       ├── aggregator.py                Agregación mensual + zero-fill + gating
│       ├── model.py                     4 métodos + compute_budget_suggestions()
│       └── loader.py                    Carga CSVs (synthetic → raw fallback)
├── scripts/
│   ├── extract_datalake_to_csv.py       Extrae S3 datalake → CSV local
│   ├── build_fact_transactions.py       Construye fact_transactions (OLB + DOUGH)
│   ├── run_smart_budget_prep.py         Pipeline: filtra, agrega, gating
│   ├── extract_test_datasets.py         Split por fuente: internal / external
│   ├── eval_runner.py                   Evaluación comparativa de métodos
│   ├── run_methods.py                   CLI de ejecución del modelo
│   └── generate_synthetic_dataset.py   Dataset sintético para pruebas
├── tests/
│   ├── unit/
│   │   ├── test_filters.py
│   │   ├── test_aggregator.py
│   │   ├── test_model.py
│   │   ├── test_api.py                  10 TCs — reglas de validación del endpoint
│   │   └── test_eval_runner.py
│   └── fixtures/
│       ├── golden_set.csv
│       └── smart_budget_synthetic.csv
├── data/                               Gitignored — nunca commitear
│   └── dough/
│       ├── fact_transactions.csv        Tabla central: 1.4M filas
│       ├── smart_budget_prep.csv        Datos listos para el modelo
│       ├── smart_budget_synthetic.csv   Dataset sintético (11 cuentas, 15 categorías)
│       └── test/
│           ├── test_internal.csv        Transacciones OLB (SUB/LOAN)
│           └── test_external.csv        Transacciones Plaid/Finicity (EXT)
└── docs/
    ├── fact_transactions_README.md
    ├── guides/smart-budget/
    │   └── How-To-Use-Endpoint.md      Uso del endpoint local y SageMaker
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

# 3. Datos (requiere AWS SSO)
aws sso login --profile blossom-dev
python scripts/extract_datalake_to_csv.py --source DOUGH --env dev
python scripts/build_fact_transactions.py --env dev
python scripts/run_smart_budget_prep.py --input data/dough/fact_transactions.csv

# 4. Ejecutar modelo
python scripts/run_methods.py --method wma --treatment B --lookback-months 3 --reference-date 2026-05

# 5. Endpoint local
uvicorn src.main:app --reload --port 8000
# → http://localhost:8000/docs
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
