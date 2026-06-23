# Changelog

## [DATA-1275] — Migración fuente de datos a Athena (2026-06-23)

Migración del endpoint Smart Budget (FastAPI + SageMaker) de CSV/PostgreSQL a consulta en tiempo real contra la tabla Glue `dlh_gold_dough_dev.smart_budget_transactions` vía pyathena. Los datos ya no se empaquetan en el modelo — se consultan en cada invocación.

### Fuente de datos
- Nuevo módulo `src/smart_budget/athena_loader.py`: `load_history_by_member_athena()`, `member_exists_athena()`, `AthenaQueryError`; conexión cacheada a nivel de módulo
- Tabla fuente: `dlh_gold_dough_dev.smart_budget_transactions` (Athena/Glue, mantenida por DE en `homecu/dwh_dough`)
- Query parametrizada por `idmember` + rango `txn_month` (formato `YYYY-MM`); tabla pre-filtrada (solo gastos, sin LOAN, sin PENDING)
- Dependencia agregada: `pyathena>=3.0,<4` (en `requirements.txt` y `src/sagemaker/requirements.txt`)

### Schema — breaking change (D4)
- `SuggestionItem`: eliminado `defaultcategory`; agregados `category_id: str` y `category_name: str` (alineado al schema Glue)
- `aggregator.py` y `model.py`: columnas `idcategory`/`defaultcategory` renombradas a `category_id`/`category_name` en todo el pipeline

### SageMaker
- `inference.py`: `predict_fn` llama `load_history_by_member_athena` en lugar del CSV loader
- `notebooks/smart_budget_sagemaker_endpoint.ipynb`: CSV packaging eliminado de cell 6; env vars Athena (`ATHENA_S3_STAGING_DIR`, `ATHENA_REGION_NAME`, `ATHENA_DATABASE`, `ATHENA_TABLE`) agregadas al `SKLearnModel`
- `model.tar.gz` ahora contiene solo código (sin `data/*.csv`)

### Limpieza
- Eliminado `src/smart_budget/loader.py` (CSV loader, reemplazado por `athena_loader.py`)
- Eliminado `scripts/extract_smart_budget_monthly.py` (extracción PostgreSQL, reemplazada por Athena)
- Eliminado `tests/unit/test_loader.py` (testeaba el loader eliminado)
- `scripts/build_fact_transactions.py`: marcado LEGACY (modo `--source db` deprecado)

### Docs
- Nueva guía: `docs/guides/smart-budget/How-To-Query-Athena.md`
- Actualizados: `README.md`, `How-To-Use-Endpoint.md`, `How-To-Extract-Data.md`, codemap completo

---

## [DATA-1179] — Dataset real + grain idmember + entornos dev/alpha (2026-06, en progreso)

Migración del pipeline de datos sintéticos a datos reales de la DB, cambio de grain de `idaccount` → `idmember`, y soporte de entornos dev/alpha en endpoint y SageMaker.

### Dataset y extracción
- Nuevo script `extract_smart_budget_monthly.py`: extrae datos reales desde `blossom-dough-consolidated` (dev o alpha) con query SQL directa — sin S3
- **dev:** 26,417 filas · 421 miembros · 3 CUs · períodos 2022-09 → 2026-05
- **alpha:** 195,923 filas · 2,929 miembros · 18 CUs · períodos 2019-06 → 2026-06
- EDA completos para dev y alpha (`docs/guides/smart-budget/`)
- Solo cuentas `INT`/`SUB` en la DB actual (no hay cuentas EXT replicadas)
- Convención de signos OLB confirmada: amounts negativos → normalizados con `ABS()` en SQL
- Status confirmado: `POSTED` (mayúsculas) en la DB de producción

### Modelo — cambio de grain a idmember
- `aggregator.py`: `aggregate_monthly` incluye `idmember` en groupby; `zero_fill` valida pares `(idmember, idclient, idcompany)`; `apply_gating` agrupa por `(idclient, idcompany, idmember)` — sin cross-tenant
- `model.py`: `bucket_keys` → `idmember`; nuevo campo `total_suggested` (suma de suggested_amount no nulos por miembro, `0.0` si todos null); `_null_suggestion` reemplaza `idaccount` con `idmember`
- `build_fact_transactions.py`: helper `_resolve_idmember` para join dual (EXT: strip "EXT" → memberaccount; OLB: via `blossomdoughconsolidatedaccountid` → account → memberaccount)
- `run_smart_budget_prep.py`: `idmember` agregado a columnas requeridas (warning-only para backward compat)
- `run_methods.py`: output incluye `idmember` + `total_suggested`

### Endpoint FastAPI — entornos dev/alpha
- Variable `SB_ENV=dev|alpha` selecciona el dataset activo al startup (resuelto en import time)
- Fix `_build_amount_by_month`: usa `groupby().sum()` — resuelve crash por períodos duplicados en CSV real
- Dropdown Swagger dinámico: top-10 miembros con sugerencias reales en >1 categoría (calculado al startup)
- `loader.py`: parámetro `csv_name` opcional; comparación `idmember` siempre como string
- Parámetro de entrada cambiado: `idaccount` + `defaultcategory` → `idmember` + `period_id`
- Respuesta: todas las categorías del miembro en una llamada (antes: 1 categoría por request)

### SageMaker
- `inference.py` reescrito: nuevo contrato `{idmember, period_id}` → respuesta multi-categoría
- CSV en tarball: `smart_budget_data.csv` (nombre canónico — env-agnostic)
- Notebook actualizado: celda `ENV = "dev" | "alpha"` al inicio; S3 paths separados `v1/dev/model.tar.gz` y `v1/alpha/model.tar.gz`; endpoint names: `smart-budget-suggestion-endpoint-dev/alpha`

### Tests
- 133 passed, 4 skipped (vs 107 en Fase 0)
- Nuevos: `test_build_fact_transactions_idmember.py`, `test_prep_idmember.py`, `test_multitenancy.py` (cross-member/cross-company leak)
- `test_inference.py` reescrito: 8 TCs para contrato `{idmember, period_id}`
- Golden set re-frozen: 3 miembros sintéticos, 6 períodos, schema con `idmember`

---

## Fase 0 — El Reflejo (2025-12 → 2026-05)

Implementación MVP del módulo Smart Budget para el producto Dough de Blossom.
El modelo refleja el comportamiento pasado del usuario sin inventar ni recomendar.

---

### Pipeline de datos

- Extracción desde S3 (datalake alpha/dev, capas bronze/silver) para fuentes OLB y Dough
- Construcción de `fact_transactions` unificando OLBSubAccountTransaction, OLBLoanTransaction y externaltransaction
- Scripts de preparación: extracción por capa/fuente, build de la tabla central, prep para el modelo
- Corrección de convención de signo en transacciones OLB (amounts normalizados a positivos)
- Exclusión de transacciones LOAN del modelo presupuestal (obligaciones fijas, no gasto discrecional)

### Modelo de sugerencias

- 6 reglas de filtrado obligatorias (soft delete, solo gastos, categorías válidas, LOAN exclusion, status SUB, status EXT)
- Agregación mensual por `(member, category)` con zero-fill y clamp a cero
- 4 métodos de cálculo evaluados: WMA, EWMA, mediana, Holt-Winters
- Método seleccionado: **WMA tratamiento B, lookback 3 meses** (CRWS = 0.5372)
- Gating: mínimo 2 meses con data para emitir sugerencia
- Confidence levels: `high` (≥6 meses), `medium` (3–5), `low` (2)

### API y serving

- Endpoint FastAPI: `GET /smart-budget/suggestion` con parámetros enum (Swagger dropdowns)
- Respuesta con `suggested_amount`, `basis`, `confidence`, `display_label`, `amount_by_month`
- 3 reglas de validación: cuenta existente, período válido, categoría presente en datos
- `POST /smart-budget/decision` para captura del loop de retroalimentación
- Deploy en SageMaker (inference.py + notebook de deploy)

### Testing

- Suite pytest con cobertura ~93%
- Golden set de regresión (65 sugerencias sintéticas)
- Tests unitarios: filtros, agregador, edge cases, idempotencia, multi-tenancy
- Tests de contrato API (TC-T2.1–T2.9)
- Datasets de test separados por fuente (internal/external)

### Documentación

- Codemap completo (`docs/codemap/`) — arquitectura, módulos, glosario, pipeline de datos
- Guías paso a paso (`docs/guides/`) — extracción, build, API local, SageMaker, datos sintéticos
- Evaluation report con comparación de los 4 métodos y justificación de selección
- AGENTS.md y CLAUDE.md con contexto para agentes AI
