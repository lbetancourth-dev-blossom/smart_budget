# API — FastAPI Endpoint

> Contexto por módulo para agentes AI. Complementa `docs/codemap/04-api/README.md`.

## Propósito

Endpoint REST `GET /smart-budget/suggestion` que orquesta el pipeline de carga → gating → modelo y retorna sugerencias de presupuesto por cuenta y categoría.

## Dónde vive cada cosa

```
src/api/
├── __init__.py   → marker de paquete (vacío)
└── router.py     → ruta, Enums, Pydantic schemas, lógica de orquestación
src/main.py       → FastAPI app — monta el router bajo /smart-budget
```

## Archivos clave

- `router.py` — toda la lógica del endpoint (300 líneas aprox.)
  - `IdAccount`, `Category`, `PeriodId` Enums — validación automática FastAPI
  - `SuggestionResponse`, `BasisDetail` — schemas Pydantic de respuesta
  - `get_suggestion()` — handler principal
  - `_build_null_response()`, `_build_amount_by_month()` — helpers internos
- `src/main.py` — entry point de uvicorn

## Convenciones

- Enum params → FastAPI devuelve `422` automáticamente para valores inválidos (sin código extra)
- `reference_date = pd.Period(period_id, freq="M") - 1` — siempre usar el mes PREVIO como límite de historia
- Logs: `structlog` con evento `smart_budget.suggestion.<start|done|null|error>`
- Data dir: leer de `SMART_BUDGET_DATA_DIR` env var (fallback: `data/dough/`)
- Config fija en Fase 0: `method="wma"`, `treatment="B"`, `lookback=3`, `min_months=2`

## Dependencias

- Importa de: `smart_budget.aggregator`, `smart_budget.loader`, `smart_budget.model`
- Importado por: `src/main.py` (y cualquier test que use `TestClient`)

## Tests

- Correr: `pytest tests/unit/test_api.py -v`
- 10 tests: TC-T2.1 – TC-T2.10
- Usar `unittest.mock.patch` para mockear `load_history` y `account_exists`

## Gotchas

- **`PYTHONPATH=src`** es obligatorio para correr uvicorn localmente: `PYTHONPATH=src uvicorn src.main:app --reload --port 8000`
- `SuggestionResponse` incluye `amount_by_month` — no omitir al actualizar el schema
- 404 solo si la cuenta no existe; historia vacía devuelve `200 null` (no error)
- `display_label` nunca puede ser prescriptivo (UDAAP/CFPB) — nunca "deberías" ni "tienes que"

## See also

- [Module overview](../../docs/codemap/04-api/README.md)
- [Root project context](../../CLAUDE.md)
- [SageMaker equivalent](../sagemaker/CLAUDE.md)
