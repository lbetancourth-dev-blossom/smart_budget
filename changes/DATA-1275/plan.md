# Plan: DATA-1275 — Migrar Smart Budget de CSV a Athena (data source swap — FastAPI + SageMaker)

## Summary

Hoy tanto el endpoint FastAPI (`GET /smart-budget/suggestion`) como el endpoint SageMaker
(`smart-budget-suggestion-endpoint-<env>`) leen el historial mensual desde un CSV. En el caso
FastAPI, el CSV vive en disco local (`data/smart_budget_db_<env>.csv`); en el caso SageMaker,
el CSV se **empaqueta dentro del `model.tar.gz`** al momento del deploy (cell 6 del notebook
copia el CSV al staging dir y `inference.py` lo lee desde `model_dir/data/`).

Este ticket hace UN cambio arquitectónico, aplicado a ambas superficies:

1. **Fuente de datos (FastAPI + SageMaker)**: migra de CSV a la tabla Glue
   `dlh_gold_dough_dev.smart_budget_transactions` consultada vía Athena con `pyathena`,
   **en tiempo de inferencia** (no en tiempo de build/deploy).

> **Punto clave del ticket (clarificación del dev, 2026-06-22):** el modelo SageMaker deja de
> cargar datos "horneados en el artefacto". El artefacto pasa a contener sólo código
> (`smart_budget/` package). Cada invocación del endpoint dispara una query a Athena por el
> `idmember` solicitado. Esto cambia el perfil de despliegue (data freshness en tiempo real,
> sin re-deploy para refrescar datos) y el perfil de runtime (latencia 2-5s por query, IAM
> nuevo en el execution role, dependencia AWS al request path).

**Lo que NO cambia (clarificación del dev sobre HLTC-9):**
- El notebook `smart_budget_sagemaker_endpoint.ipynb` se **modifica** (no se rediseña): se
  quita el packaging del CSV en cell 6, se agregan env vars de Athena al `SKLearnModel` en
  cell 8, y se documenta el requerimiento de IAM. NO se cambia el flujo deploy → invoke.
- NO se crea `entrypoint.py`. NO se cambia el router FastAPI. El handler FastAPI sigue siendo
  el handler; sólo cambia el loader que llama por debajo.
- Como hay un campo nuevo en el schema del Glue (`category_id`, `category_name`), el pipeline
  downstream sí se actualiza para usar los nombres correctos — pero la superficie pública
  (firma del endpoint, contrato HTTP) no se rediseña.

Método de modelado (WMA), tratamiento (B), lookback (3) y gating (min 2 meses) no cambian.
Cada sugerencia incluye los campos `category_id` y `category_name` además del
`defaultcategory` actual, para alinearse con el schema del Glue.

## Stack

`py-agents` (Python core model + FastAPI handler + SageMaker inference script + notebook de deploy. Cross-cutting porque el data-source swap aplica a las dos superficies de inferencia.)

## Decisions

### Human decisions (7 closed, 0 pending)

| # | Question | Decision | Trigger |
|---|----------|----------|---------|
| D1 | ¿Cómo se determina el `s3_staging_dir` y la `region_name` para `pyathena`? | **CLOSED** — `s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/'`, `region_name='us-east-2'`. Ambos via env vars: `ATHENA_S3_STAGING_DIR` y `ATHENA_REGION_NAME`. Patrón de conexión validado desde SageMaker. Columnas confirmadas: `idclient, idcompany, idmember, idaccount, category_id, category_name, type_category, txn_month, total_amount, year, month`. | #31 (new AWS resource path) |
| D2 | ¿Qué hacer con la columna `type_category` del Glue? El schema la incluye pero el SQL actual (`smart_budget_monthly_spend.sql`) ya aplica el filtro `incomeexpenditure='expenditure'` en su origen. | **CLOSED** — La tabla `dlh_gold_dough_dev.smart_budget_transactions` ya está pre-filtrada y materializada (el SQL fuente aplica `deletedat`, `incomeexpenditure='expenditure'`, exclusiones de LOAN, etc.). NO se filtra por `type_category` en el WHERE. Query final: `SELECT idmember, category_id, category_name, txn_month, total_amount FROM dlh_gold_dough_dev.smart_budget_transactions WHERE idmember = %s AND txn_month BETWEEN %s AND %s`. La proyección se reduce a 5 columnas (idclient, idcompany, idaccount, type_category, year, month quedan sin leer). | - |
| D3 | ¿Cómo se popula el dropdown `IdMember` de Swagger cuando la fuente es Athena? | **CLOSED (revisado tras clarificación del dev).** El despliegue SageMaker **ya existe** vía notebook `smart_budget_sagemaker_endpoint.ipynb` — el ticket NO crea una nueva superficie de invocación. El handler FastAPI sigue intacto en cuanto a su firma; sólo cambia el loader que invoca por debajo. El `IdMember` Enum se mantiene como está (no se actualiza la lista hardcoded en este ticket — fuera de scope). | - |
| D4 | ¿El campo `defaultcategory` actual de `SuggestionItem` se reemplaza por `category_name`, o conviven ambos? | **CLOSED — Opción B (reemplazo, sin backwards compat).** Se elimina `defaultcategory` por completo de `SuggestionItem` y de todo el pipeline downstream. Se usan directamente `category_id: str` y `category_name: str` de la tabla Glue. Sin alias, sin coexistencia — break limpio alineado con el schema nuevo. Justificación: FastAPI se está deprecando y SageMaker es el nuevo target; no hay consumidor legacy que proteger. | - |
| D5 (HLTC-10.1) | ¿El SageMaker execution role tiene los permisos Athena/Glue/S3 necesarios, o requiere infra-work paralelo? | **CLOSED — sin infra-work.** Dev confirmó (2026-06-22) que el SageMaker execution role ya tiene Athena + Glue + S3 staging permissions. El notebook agrega un markdown documentando el requerimiento pero no se levanta ticket de infra. | - |
| D6 (HLTC-10.2) | ¿Cómo se editan las celdas del notebook `smart_budget_sagemaker_endpoint.ipynb` — manual o programáticamente? | **CLOSED — programáticamente.** El implementer edita el `.ipynb` con un script Python (lectura JSON, mutación de `cell.source`, escritura) para garantizar diff determinista y verificable con `grep` en V11. No se hace edición manual en Jupyter. | - |
| D7 (HLTC-10.3) | ¿`pyathena>=3.0.0` instala limpio en el container `sklearn:1.2-1` (Python 3.9), o requiere fallback a pyathena 2.x? | **CLOSED — `pyathena>=3.0,<4` confirmado.** Dev confirmó que Python 3.9 + `sklearn:1.2-1` soporta `pyathena>=3.0.0`. Pin exacto tomado de `blossom-ml-safe-txns/endpoint/requirements.txt` (`pyathena>=3.0,<4`), repo que usa el mismo runtime exitosamente. Sin fallback necesario. | - |

### AI-closed decisions (18)

| # | Decision | Grounding |
|---|----------|-----------|
| A1 | Nueva dependencia: `pyathena>=3.0,<4` agregada a `requirements.txt` y `src/sagemaker/requirements.txt`. Pin tomado de `blossom-ml-safe-txns/endpoint/requirements.txt` (confirmado por dev como referencia válida — mismo runtime SageMaker, mismo Python 3.9, `sklearn:1.2-1`) | `blossom-ml-safe-txns/endpoint/requirements.txt:1` → `pyathena>=3.0,<4` |
| A2 | Nuevo módulo `src/smart_budget/athena_loader.py` con función `load_history_by_member_athena(idmember, conn=None) -> pd.DataFrame` | Sigue la convención de un archivo por responsabilidad — `loader.py` actual ya está saturado con 358 líneas; agregar Athena ahí lo cruza |
| A3 | El nuevo loader proyecta el resultado de Athena al shape downstream renombrando: `txn_month -> period_yyyymm`, `total_amount -> monthly_total`. **Tras D4 (reemplazo limpio):** `category_id` y `category_name` se usan directamente (sin alias a `idcategory`/`defaultcategory`). `aggregator.py` y `model.py` se actualizan para agrupar por `category_id, category_name, period_yyyymm`. | Schema Glue confirmado por dev (D1). D4 cierra el reemplazo total — el pipeline downstream se alinea al nombre nuevo. |
| A4 | `router.py` switches de `load_history_by_member` -> `load_history_by_member_athena` directo, sin feature flag de toggle CSV<->Athena | El ticket DATA-1275 es un cambio dirigido. Mantener un toggle agrega complejidad y el rollback es revertir el PR (las funciones CSV legacy quedan en `loader.py` intactas para batch scripts) |
| A5 | Conexión Athena: construida al startup del módulo con `pyathena.connect()`, cacheada en variable módulo-level `_ATHENA_CONN`. Se reutiliza entre requests | Patrón estándar de pyathena — `connect()` retorna un objeto reusable (ver notebook) |
| A6 | Query Athena parametrizada con `idmember` y rango de `txn_month` via prepared statement de pyathena (`%s` placeholders) — NO interpolación de strings. Query exacta: `SELECT idmember, category_id, category_name, txn_month, total_amount FROM dlh_gold_dough_dev.smart_budget_transactions WHERE idmember = %s AND txn_month BETWEEN %s AND %s`. `txn_month` formato `YYYY-MM` string. Sin filtro de `type_category` (tabla ya pre-filtrada). | Defensa contra SQL injection. Query confirmada por dev (D2). |
| A7 | `txn_month` se normaliza a string `YYYY-MM` mapeando a `period_yyyymm` con `df['period_yyyymm'] = df['txn_month'].astype(str).str[:7]` | El modelo (`model.py:compute_wma`) espera el formato existente. La cadena ya debería venir así si el Glue es `YYYY-MM`, pero el slice es idempotente |
| A8 | `total_amount` se renombra a `monthly_total` (mismo dtype, mismo signo positivo) | El pipeline downstream usa `monthly_total` en todas partes (`aggregator.py`, `model.py`, `router.py:_build_amount_by_month`) |
| A9 | Errores de Athena (timeout, credenciales) -> levantar excepción que el router mapea a HTTP 503 con mensaje genérico ("Datalake temporalmente no disponible") | `src/api/router.py:154` ya tiene patrón análogo para `FileNotFoundError` -> 500. Se agrega una rama paralela para `Exception` de pyathena |
| A10 | `member_exists()` también migra a Athena: `SELECT 1 FROM dlh_gold_dough_dev.smart_budget_transactions WHERE idmember = %s LIMIT 1`. Nueva función `member_exists_athena(idmember) -> bool` | El router llama `member_exists` en línea 159 para distinguir 404 de 200-vacío. Si el loader es Athena pero `member_exists` sigue siendo CSV, el 404 da falso negativo |
| A11 | **Tras D4 cerrado (Opción B — reemplazo):** Schema `SuggestionItem` elimina `defaultcategory` y agrega `category_id: str` y `category_name: str` (requeridos, no opcionales). Breaking change explícito aceptado por el dev — no hay consumidor legacy (D3: FastAPI deprecable, SageMaker es el nuevo target). | D4 cierra el reemplazo limpio. Schema queda alineado 1-a-1 con la tabla Glue. |
| A12 | Tests unitarios usan `unittest.mock.patch` sobre `pyathena.connect` y `pd.read_sql` para no requerir credenciales AWS en CI | Sigue el patrón existente de `tests/unit/test_api.py:20` (`from unittest.mock import patch`) — no se usa moto ni LocalStack |
| A13 | Nuevo conftest no se requiere: el shim para `pyathena` en tests se hace con `monkeypatch.setattr` en cada test que lo necesita | El root `conftest.py:1-9` es minimalista; agregar más imports degrada la suite |
| A14 | Variables de entorno: `ATHENA_S3_STAGING_DIR` (default `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`), `ATHENA_REGION_NAME` (default `us-east-2`), `ATHENA_DATABASE` (default `dlh_gold_dough_dev`), `ATHENA_TABLE` (default `smart_budget_transactions`) | Valores confirmados por dev (D1) desde test en SageMaker. Defaults sensatos para dev. Patrón análogo a `SB_ENV` y `SMART_BUDGET_DATA_DIR` ya existentes en router.py:40-44 |
| A15 | El SQL `src/smart_budget/queries/smart_budget_monthly_spend.sql` NO se modifica en este ticket — sigue siendo la fuente de verdad del pipeline batch que produce el Glue table. Es referencia, no se ejecuta desde el endpoint | El ticket migra el endpoint, no el pipeline upstream. Ese SQL alimenta la tabla Glue offline |
| A16 | Logs: `structlog` con eventos `smart_budget.athena.query.start`, `.done`, `.error` con `idmember`, `duration_ms`, `rows_returned`. Nunca log `total_amount` individual | Mismo patrón de `router.py:148` (`smart_budget.suggestion.start`). El gotcha de `src/smart_budget/CLAUDE.md` prohíbe logear montos individuales |
| ~~A17~~ | **RETRACTED tras clarificación del dev.** No se crea `src/smart_budget/entrypoint.py`. El handler FastAPI existente (`src/api/router.py`) hace el switch directo del loader CSV al loader Athena. No hay nueva superficie callable porque SageMaker ya está desplegado vía `smart_budget_sagemaker_endpoint.ipynb`. | Dev clarification (HLTC-9 retracted) |
| ~~A18~~ | **RETRACTED.** El Enum `IdMember` se mantiene sin cambios. La validación de inputs sigue siendo la de FastAPI/Pydantic existente. | Dev clarification |

## Architectural Delta

### Entrypoints

| Action | Entrypoint | Surface | Notes |
|--------|-----------|---------|-------|
| MODIFIED | `GET /smart-budget/suggestion` | FastAPI | Mismo contrato HTTP. Internamente intercambia el loader CSV por `load_history_by_member_athena` + `member_exists_athena`. Schema `SuggestionItem` cambia por D4 (drop `defaultcategory`, add `category_id`+`category_name`). |
| MODIFIED | `smart-budget-suggestion-endpoint-<env>` (SageMaker) | SageMaker Runtime | Mismo contrato JSON. Internamente `inference.py:predict_fn` deja de leer `model_dir/data/*.csv` y llama `load_history_by_member_athena` + `member_exists_athena`. El `model.tar.gz` ya no carga datos. |
| MODIFIED | `notebooks/smart_budget_sagemaker_endpoint.ipynb` | Deploy notebook | Cell 6 deja de empaquetar el CSV; cell 8 pasa env vars de Athena al `SKLearnModel`; nuevo markdown documenta el IAM del execution role. |

### Schemas

| Action | Schema | Notes |
|--------|--------|-------|
| MODIFIED | `SuggestionItem` (Pydantic) | **Breaking (D4):** elimina `defaultcategory`. Agrega `category_id: str` y `category_name: str` (requeridos). |
| UNCHANGED | `MemberSuggestionResponse`, `BasisDetail`, `IdMember`, `PeriodId` | |

#### `SuggestionItem` — Data Contract (cambio breaking por D4)

| Field | Type | Presence | Source | Missing behavior | Transform |
|-------|------|----------|--------|-----------------|-----------|
| ~~`defaultcategory`~~ | — | **removed** | — | — | reemplazado por `category_name` |
| `category_id` | string | required | Glue column `category_id` | row dropped | cast a str |
| `category_name` | string | required | Glue column `category_name` | row dropped | cast a str |

### Services / modules

| Action | Module | Notes |
|--------|--------|-------|
| NEW | `src/smart_budget/athena_loader.py` | `load_history_by_member_athena()`, `member_exists_athena()`, `_get_connection()` |
| UNCHANGED | `src/smart_budget/loader.py` | Sin cambios — queda para batch scripts |
| MODIFIED | `src/api/router.py` | Switch de imports CSV → Athena (`load_history_by_member_athena`, `member_exists_athena`). **Breaking (D4):** elimina `defaultcategory` de `SuggestionItem` y agrega `category_id: str` + `category_name: str` requeridos. Mapea `AthenaQueryError` a HTTP 503. |
| MODIFIED | `src/smart_budget/aggregator.py` | **Tras D4:** agrupa por `category_id, category_name, period_yyyymm` (antes `idcategory, defaultcategory`). |
| MODIFIED | `src/smart_budget/model.py` | **Tras D4:** todas las referencias a `idcategory`/`defaultcategory` se renombran a `category_id`/`category_name`. |
| MODIFIED | `src/sagemaker/inference.py` | **KEY change.** `predict_fn` deja de leer CSV bundleado (`_DATA_CSV`, `base_dir = model_dir/data`) y llama directo a `load_history_by_member_athena` / `member_exists_athena`. `AthenaQueryError` mapeado a `ValueError("datalake temporarily unavailable")` → `ModelError` desde SageMaker. |
| MODIFIED | `src/sagemaker/requirements.txt` | Agrega `pyathena>=3.0,<4` para que el contenedor de inferencia tenga el SDK. |
| MODIFIED | `notebooks/smart_budget_sagemaker_endpoint.ipynb` | **KEY change.** Sin CSV en `model.tar.gz`. Env vars de Athena en `SKLearnModel`. Markdown con IAM. |
| MODIFIED | `tests/unit/test_inference.py` | Mocks de Athena en lugar de fixtures CSV; nuevos TC-T5.7/8/9. |

### Repositories

| Action | Repository | Notes |
|--------|-----------|-------|
| UNCHANGED | (none) | |

### Integrations

| Action | Integration | Notes |
|--------|------------|-------|
| NEW | AWS Athena via `pyathena` SDK | Lecturas SELECT solamente. Requiere credenciales AWS y un bucket de staging para resultados |

### Tests

| Action | Test file | Notes |
|--------|----------|-------|
| NEW | `tests/unit/test_athena_loader.py` | Mock de `pyathena.connect` + `pd.read_sql`; valida shape de DataFrame, mapeo de columnas, manejo de error |
| MODIFIED | `tests/unit/test_api.py` | Mocks ajustados a `athena_loader.*` (en lugar de `loader.*`). Helper actualizado. Agrega TC-API-10 (`category_id`/`category_name` en respuesta) y TC-API-11 (503 cuando Athena falla). |

## Happy path

1. Cliente HTTP llama `GET /smart-budget/suggestion?idmember=11393&period_id=2026-05`.
2. Router FastAPI valida inputs (Enum existente) y calcula `reference_date = "2026-04"`.
3. Router llama `member_exists_athena(idmember="11393")`. Si False → 404.
4. Router llama `load_history_by_member_athena(idmember="11393")` que ejecuta una query
   contra `dlh_gold_dough_dev.smart_budget_transactions`.
5. El loader normaliza columnas (`txn_month → period_yyyymm`, `total_amount → monthly_total`)
   y proyecta `category_id` / `category_name` directamente.
6. Pipeline aplica `apply_gating` (min 2 meses) y `compute_budget_suggestions(method="wma", treatment="B", lookback=3)`.
7. Router construye `MemberSuggestionResponse` con cada `SuggestionItem` ahora con
   `category_id` y `category_name` (sin `defaultcategory` — D4).
8. Retorna 200 JSON.

## Error paths

- Athena timeout o credenciales inválidas -> log `smart_budget.athena.error` -> HTTP 503
  con `detail="datalake temporarily unavailable"`.
- Miembro no existe en Glue -> 404 (igual que hoy, via `member_exists_athena`).
- Miembro existe pero sin transacciones en la ventana -> 200 con `suggestions=null` y
  `message` apropiado (igual que hoy).
- Period_id mal formado -> 422 (FastAPI Enum validation, sin cambio).

## Side effects

- DB writes: ninguno (read-only)
- Outbound HTTP: ninguno
- Outbound AWS API: queries Athena (read-only) + escrituras a S3 staging dir
  (pyathena escribe el resultset del query). Latencia esperada por query: 2-5s.
  **Esta latencia ahora se materializa en cada invocación del endpoint SageMaker**, no sólo
  en FastAPI. Antes del ticket, SageMaker leía CSV local (latencia <50ms); ahora p99 esperado
  ~3-6s end-to-end por request.
- Audit events: ninguno (no hay money movement)
- Queue messages: ninguno

## Persistence changes

- Migration forward: ninguna (la tabla Glue ya existe — DATA-1136/1140 la produjeron)
- Migration reverse: N/A
- Data backfill: N/A

## Feature flag

- **No se usa feature flag.** El cambio es atómico: o el endpoint lee de Athena, o lee de CSV.
  No hay valor en mantener ambos caminos en paralelo — el rollback es revertir el PR.
- Trade-off aceptado: si Athena cae después del deploy, todos los miembros reciben 503
  hasta que se haga revert. El blast radius es solo este endpoint.

## Risk level

**MEDIUM-HIGH** (subió de MEDIUM tras incorporar el cambio en SageMaker)

Cambio que toca dos superficies de inferencia (FastAPI + SageMaker) e introduce dependencia
nueva (`pyathena`, credenciales AWS, S3 staging bucket) que no existía en el código. Sin
feature flag para rollback fino. Riesgos adicionales del cambio SageMaker:

- El **execution role** del endpoint SageMaker requiere permisos nuevos (Athena/Glue/S3). Si
  el rol no se actualiza antes/junto-con el deploy, el endpoint devuelve `ModelError` en cada
  request.
- Latencia del endpoint sube de <50ms (CSV en disco) a 2-5s (Athena). Si hay consumidores con
  SLA estricto, este cambio los rompe.
- ~~El contenedor `sklearn:1.2-1` (Python 3.9) podría tener conflictos al instalar~~
  ~~`pyathena>=3.0,<4`~~ — riesgo CERRADO por D7 (mismo pin probado en `blossom-ml-safe-txns`).

Approvers: tech lead (Landneyker) + DE/Dough handoff confirmando schema de la tabla Glue.

## Rollback plan

1. `git revert <commit-sha-de-merge>`
2. Redeploy FastAPI.
3. Re-correr el notebook SageMaker (cells 0-9) sobre el commit revertido → re-empaqueta el
   CSV en `model.tar.gz` y re-despliega el endpoint con el código viejo.
4. El endpoint vuelve a leer del CSV. No hay state corrupto que limpiar (read-only).

## Dependencies

- Python: `pyathena>=3.0,<4` (a agregar a `requirements.txt`)
- AWS: rol IAM que el deployment ya use con permisos `athena:StartQueryExecution`,
  `athena:GetQueryResults`, `athena:GetQueryExecution`, `s3:GetObject`, `s3:PutObject`,
  `s3:ListBucket`, `glue:GetTable`, `glue:GetDatabase` sobre el bucket de staging y la
  tabla `dlh_gold_dough_dev.smart_budget_transactions`. (D1 resuelve detalles)
- **SageMaker execution role**: el rol que SageMaker asume al ejecutar el endpoint (devuelto
  por `get_execution_role()` en cell 4 del notebook) requiere los mismos permisos Athena/Glue/S3.
  Es un rol distinto del que se usa para deployar. Confirmar con infra antes del merge.
- Container Python 3.9 (`sklearn:1.2-1`): `pyathena>=3.0,<4` se instala sin conflictos
  (confirmado por dev vía D7 — mismo pin usado en `blossom-ml-safe-txns/endpoint/requirements.txt`
  en el mismo runtime SageMaker).

## Compliance notes

- NCUA / BSA/AML: N/A (read-only, no money movement, no decisiones automatizadas)
- PCI DSS: N/A (no tocan PAN/CVV)
- PII: la tabla Glue contiene `idmember` que es un identificador interno, no PII directa.
  Logs no exponen montos. Sin cambios al perfil de PII actual del endpoint.

## Audit / overrides

(none yet — populated if any trigger override happens during review)

## HLTC (Highlight-mode — only triggered blocks)

```yaml
ticket: DATA-1275
phase: plan
sub_phase: hltc
stack: py-agents
auto_accepted:
  - id: HLTC-1
    type: module
    action: NEW
    summary: "src/smart_budget/athena_loader.py — Athena-backed loader (load_history_by_member_athena, member_exists_athena, _get_connection, AthenaQueryError)"
    derived_from: A2, A5, A6, A10
  # HLTC-2 RETRACTED — no entrypoint.py is created (dev clarification: SageMaker already
  # deployed via smart_budget_sagemaker_endpoint.ipynb; ticket is data-source-swap only).
  - id: HLTC-3
    type: schema
    action: MODIFIED
    summary: "SuggestionItem: drop defaultcategory; add required category_id and category_name"
    derived_from: D4, A11
  - id: HLTC-4
    type: module
    action: MODIFIED
    summary: "aggregator.py and model.py renamed columns idcategory/defaultcategory → category_id/category_name"
    derived_from: D4, A3
  - id: HLTC-5
    type: route
    action: MODIFIED
    summary: "GET /smart-budget/suggestion swaps CSV loader for Athena loader; adds 503 mapping for AthenaQueryError; SuggestionItem schema updated per D4"
    derived_from: A4, A9
  - id: HLTC-6
    type: dependency
    action: NEW
    summary: "requirements.txt += pyathena>=3.0.0"
    derived_from: A1
blocks:
  - id: HLTC-7
    type: integration
    action: NEW
    mode: review
    plain_summary: "First-ever AWS Athena connection from the runtime. Requires IAM role + S3 staging bucket that didn't exist for this repo before."
    summary: "pyathena → Athena (read) + S3 staging (write). New external dependency on AWS at request path."
    preview: |
      Env vars introduced: ATHENA_S3_STAGING_DIR, ATHENA_REGION_NAME, ATHENA_DATABASE, ATHENA_TABLE
      Connection cached at module level (_CONN), lazy-init
      Errors wrapped in AthenaQueryError → 503 at router
      No retry / circuit-breaker (deferred — rollback is git revert per plan)
      Latency: 2-5s per query (expected p99)
    affected_files:
      - "src/smart_budget/athena_loader.py (CREATE)"
      - "src/api/router.py (MODIFIED)"
      - "requirements.txt (MODIFIED)"
    triggered_flag:
      hard: 29
      reason: "New 3rd-party integration (AWS Athena) at request path"

  - id: HLTC-8
    type: contract
    action: BREAKING
    mode: review
    plain_summary: "SuggestionItem loses the field defaultcategory. Any caller reading that field will break. Dev confirmed acceptable (D4) because SageMaker is the new target and FastAPI is deprecable."
    summary: "Breaking schema change: remove defaultcategory, add required category_id + category_name"
    preview: |
      Before: { defaultcategory: str, ... }
      After:  { category_id: str, category_name: str, ... }
      No alias, no coexistence (per D4 Option B)
      Downstream aggregator.py and model.py also rename internal columns
    affected_files:
      - "src/api/router.py (MODIFIED — schema)"
      - "src/smart_budget/aggregator.py (MODIFIED — groupby keys)"
      - "src/smart_budget/model.py (MODIFIED — column refs)"
      - "tests/unit/test_api.py (MODIFIED)"
    triggered_flag:
      hard: null
      soft: "public-contract-break"
      reason: "Breaking change to response schema (acknowledged by dev via D4)"

  # HLTC-9 RETRACTED by dev — the SageMaker deployment already exists via
  # smart_budget_sagemaker_endpoint.ipynb. This ticket is a data-source swap only,
  # not a surface change. No new public surface, no new entrypoint.py, no router redesign.

  - id: HLTC-10
    type: integration
    action: NEW
    mode: review
    plain_summary: "KEY architectural shift the dev flagged: the SageMaker endpoint stops carrying data inside its model artifact and instead queries Athena LIVE on every invocation. This changes the deployment shape (artifact is code-only) and the runtime shape (each request now pays the Athena latency)."
    summary: "Inference-time Athena query from SageMaker. model.tar.gz no longer contains CSVs. predict_fn queries Athena per request via the same athena_loader used by FastAPI."
    preview: |
      Before: model.tar.gz = smart_budget/ package + data/smart_budget_data.csv
              predict_fn → load_history_by_member(model_dir/data, csv_name=...)
              latency: <50ms (local disk)
              data freshness: stale until next manual redeploy
      After:  model.tar.gz = smart_budget/ package only (no CSV)
              predict_fn → load_history_by_member_athena(idmember)
              latency: 2-5s p99 (Athena + S3 staging round-trip)
              data freshness: real-time (the table is updated by DATA-1136/1140 upstream)
      New env vars passed to SKLearnModel(env=...): ATHENA_S3_STAGING_DIR,
              ATHENA_REGION_NAME, ATHENA_DATABASE, ATHENA_TABLE
      New IAM requirement on the SageMaker EXECUTION role (not the deploy role):
              athena:StartQueryExecution, GetQueryResults, GetQueryExecution
              glue:GetTable, glue:GetDatabase
              s3:GetObject, PutObject, ListBucket on the staging bucket
      Notebook cell 6 stops copying data/smart_budget_db_<env>.csv into staging.
      Notebook cell 8 adds env= kwarg to SKLearnModel.
      Container sklearn:1.2-1 (Python 3.9) installs pyathena>=3.0,<4 cleanly
              (confirmed by dev D7 — same pin used by blossom-ml-safe-txns).

      DEV ANSWERS (2026-06-22) to HLTC-10 questions:
        D5 — IAM: SageMaker execution role ALREADY has Athena+Glue+S3 staging perms.
             No infra ticket needed. Notebook adds markdown documenting the requirement.
        D6 — Notebook edits MUST be done programmatically (Python script reading the
             .ipynb JSON, mutating cell.source, writing back). Deterministic diff,
             grep-verifiable in V11. NO manual Jupyter edits.
        D7 — pyathena pin: >=3.0,<4 (taken from blossom-ml-safe-txns/endpoint/requirements.txt).
             Python 3.9 + sklearn:1.2-1 confirmed compatible.
    affected_files:
      - "src/sagemaker/inference.py (MODIFIED — swap loader, drop _DATA_CSV)"
      - "src/sagemaker/requirements.txt (MODIFIED — add pyathena)"
      - "notebooks/smart_budget_sagemaker_endpoint.ipynb (MODIFIED — drop CSV pkg, add env vars, add IAM markdown)"
      - "tests/unit/test_inference.py (MODIFIED — mock Athena loader)"
    triggered_flag:
      hard: 29
      soft: "perf-regression-acknowledged"
      reason: "New AWS dependency at SageMaker request path + p99 latency regression 50ms→3-6s + new IAM surface on execution role"
```

## Approval

| Field | Value |
|---|---|
| All human decisions closed | ✅ D1, D2, D3, D4 |
| HLTC reviewed | ✅ 3 triggered blocks closed (HLTC-7, HLTC-8, HLTC-10). HLTC-9 retracted. HLTC-10 sub-decisions D5/D6/D7 closed by dev (2026-06-22). |
| Spec regenerated | ✅ Reflects D4 clean break + Phase 4 (T5.1/T5.2/T5.3) for SageMaker live-Athena inference + new V10-V13. pyathena pin updated to `>=3.0,<4` (matches blossom-ml-safe-txns). |
| Approved by | lbetancourth-dev-blossom |
| Approved at | 2026-06-22 |
| Next step | `/execute` — runs `blossom-implementer` on this spec |
