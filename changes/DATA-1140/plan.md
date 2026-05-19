# Plan — DATA-1140: Disponibilizar endpoint para Smart Budget

**Estado:** ✅ Listo para implementar  
**Sprint:** Data Sprint 10.26 — 6 pts  
**Implementer:** `blossom-implementer`  
**Stack:** `py-agents` (Python + FastAPI)

---

## Contexto

El endpoint expone inferencia **on-demand** (no batch + serve desde tabla): recibe
`idaccount + defaultcategory + period_id`, carga historial de las 3 fuentes CSV,
ejecuta WMA + Treatment B + lookback=3 y retorna la sugerencia. La tabla
`smartBudgetSuggestion` se crea en Fase 1 — este ticket es el paso previo que
valida el contrato de datos antes de integrar con BlossomAPI.

---

## Decisiones cerradas por IA (audit trail)

| ID | Dimensión | Decisión | Anclaje |
|---|---|---|---|
| A1 | scope | Inferencia on-demand (sin tabla): carga CSV → pipeline → retorna JSON | Diseño acordado con dev (contexto del ticket) |
| A2 | api | `GET /smart-budget/suggestion?idaccount=&defaultcategory=&period_id=` | Diseño acordado |
| A3 | api | `reference_date = period_id − 1 mes` (el mes de presupuesto NO se incluye en el historial) | Output de ejemplo acordado: period_id=2026-05, period_range=2026-02~2026-04 |
| A4 | data | Estrategia de fuentes: si `idaccount` está en `smart_budget_synthetic.csv` → usar **solo** synthetic; si no → usar raw CSVs. Evita doble conteo (synthetic fue construido desde los mismos datos que los raw) | `data/dough/smart_budget_synthetic.csv` contiene EXT2, EXT22, INT31880, SYN001-SYN008; test_internal contiene INT23 etc. — la intersección confirma que son la misma data procesada en etapas distintas |
| A5 | data | Normalización de signo OLB: los CVS raw de transacciones internas tienen amounts negativos (convención contable). Aplicar `abs()` a rows con `idtransaction.startswith(("SUB","LOAN"))` antes de `aggregate_monthly` | `scripts/build_fact_transactions.py:289-290` — "Normalizar amount a positivo para gastos (valor absoluto del débito)" — EXT ya viene con abs() aplicado, OLB no |
| A6 | data | Para raw CSVs que no tienen columna `idcategory`, sintetizarla con `df["idcategory"] = df["defaultcategory"]` antes de llamar `aggregate_monthly` | `src/smart_budget/aggregator.py:16` — `group_keys` requiere `idcategory`; raw CSVs tienen solo `defaultcategory` |
| A7 | model | WMA + Treatment B + lookback=3 fijados | DATA-1138, PR #7 — método ya seleccionado |
| A8 | model | Gating en endpoint: `apply_gating(min_months=2)` antes de `compute_budget_suggestions`. Si resultado vacío → null response (200, `confidence=null`) | Spec acordada: `<2 meses → null (gating)` |
| A9 | api | Null response: HTTP 200 con `suggested_amount=null, confidence=null` (no 404) | Esquema acordado incluye `confidence: "low\|medium\|high\|null"` como valor válido |
| A10 | api | 404 solo si `idaccount` no tiene datos en ninguna fuente | Consistente con semántica REST — "cuenta no encontrada" es una condición de negocio |
| A11 | api | Sin autenticación — endpoint dev/DS-ML, no producción BlossomAPI | `AGENTS.md` — sin infraestructura de auth en este repo |
| A12 | infra | `SMART_BUDGET_DATA_DIR` env var, default `data/dough/` relativo a la raíz del proyecto | Patrón de paths en `scripts/run_methods.py:8` — usa paths relativos desde raíz |
| A13 | infra | Dependencias nuevas: `fastapi>=0.100.0`, `uvicorn[standard]>=0.20.0`, `httpx>=0.23.0` — agregar a `requirements.txt` (el único archivo de deps del repo) | `requirements.txt` en raíz — único archivo de deps confirmado por `ls` |
| A14 | testing | TestClient de FastAPI (via `starlette.testclient`) para tests de integración; `httpx` para async. Arrange-Act-Assert sin PII | `tests/unit/test_model.py` — patrón AAA + datos sintéticos |
| A15 | logging | `structlog` para todos los logs; nunca loguear montos ni IDs en texto plano | `AGENTS.md` security rules — "nunca loguear montos" + "Member IDs: hashear con SHA-256" |
| A16 | compliance | `display_label` ya es neutral ("Basado en tus últimos N meses") — UDAAP/CFPB compliant | `src/smart_budget/model.py:332` — string literal verificado |
| A17 | placement | Nuevo módulo API: `src/api/__init__.py` + `src/api/router.py` + `src/main.py` | Estructura estándar FastAPI; `src/smart_budget/` ya sigue el patrón de módulo Python |

---

## Bloques DCR (decisiones que requieren input humano)

> **Total: 0 bloques.** Todas las decisiones se cerraron con anclaje en el código.

El scope está bien delimitado por el diseño acordado, los datos son sintéticos, no hay
componentes de producción en este ticket, y todos los patrones existen en el repo.

---

## Arquitectura de la solución

```
GET /smart-budget/suggestion
    │  query: idaccount, defaultcategory, period_id (YYYY-MM)
    ▼
src/api/router.py
    │  validate params (FastAPI/Pydantic)
    │  compute reference_date = period_id − 1 mes
    ▼
src/smart_budget/loader.py :: load_history(idaccount, defaultcategory, base_dir)
    │  ¿idaccount en synthetic CSV?
    │   ├─ SÍ → filtrar smart_budget_synthetic.csv por (idaccount, defaultcategory)
    │   └─ NO → cargar test_internal.csv + test_external.csv
    │            → filter_transactions()
    │            → abs() en amounts OLB (SUB/LOAN prefix)
    │            → add idcategory = defaultcategory
    │            → aggregate_monthly()
    │            → filtrar por (idaccount, defaultcategory)
    ▼
aggregator.apply_gating(df, min_months=2)
    │  ¿vacío? → 200 null response
    ▼
model.compute_budget_suggestions(df, method="wma", treatment="B",
                                  reference_date=reference_date, lookback_months=3)
    │  results[0] (single bucket guaranteed after filtering)
    ▼
Serializar → response JSON (schema acordado)
```

---

## Flujo de datos por cuenta

| Cuenta | Fuente activa | Procesamiento necesario |
|---|---|---|
| `INT23`, `INT428`, `INT527`, etc. | `test/test_internal.csv` (raw OLB) | filter_transactions → abs() → add idcategory → aggregate_monthly |
| `EXT22` (raw), otros EXT sin synthetic | `test/test_external.csv` (raw EXT) | filter_transactions (sin abs, ya positivo) → add idcategory → aggregate_monthly |
| `EXT2`, `EXT22`, `INT31880` | `smart_budget_synthetic.csv` (priority) | Cargar directo — ya pre-agregado con idcategory real |
| `SYN001`–`SYN008` | `smart_budget_synthetic.csv` | Cargar directo |

---

## Schema de response

```json
{
  "idaccount": "INT23",
  "idclient": "1",
  "idcompany": "1",
  "defaultcategory": "GROCERIES",
  "period_id": "2026-05",
  "suggested_amount": 420.00,
  "confidence": "low|medium|high|null",
  "basis": {
    "months_analyzed": 3,
    "months_with_positive_spend": 2,
    "period_range": "2026-02 ~ 2026-04",
    "method": "wma",
    "treatment": "B"
  },
  "display_label": "Basado en tus últimos 3 meses",
  "model_version": "fase0-v1"
}
```

**Diferencias respecto al output raw de `compute_budget_suggestions`:**
- `period_id` añadido (no está en el output del modelo — viene del request)
- `explanation` eliminado del response HTTP (era campo interno del modelo, no acordado para el API)
- `category_id` / `idcategory` eliminados del response (el contrato acordado usa solo `defaultcategory`)
- `basis.months_with_zero` no incluido en response (campo interno del modelo, no en schema acordado)

---

## Manejo de errores

| Caso | HTTP | Body |
|---|---|---|
| Cuenta no encontrada en ninguna fuente | 404 | `{"detail": "idaccount not found"}` |
| Params inválidos (period_id mal formateado, campo faltante) | 422 | FastAPI auto-generated |
| Datos insuficientes (< 2 meses positivos en ventana) | 200 | `{"suggested_amount": null, "confidence": null, "basis": null, ...}` |

---

## Manifest de archivos

| Archivo | Operación | Propósito |
|---|---|---|
| `requirements.txt` | **MODIFY** | Agregar fastapi, uvicorn, httpx |
| `src/api/__init__.py` | **CREATE** | Paquete vacío |
| `src/api/router.py` | **CREATE** | FastAPI router + endpoint lógica |
| `src/main.py` | **CREATE** | FastAPI app + include_router |
| `src/smart_budget/loader.py` | **CREATE** | Cargador unificado de datos |
| `tests/unit/test_loader.py` | **CREATE** | Tests unitarios del cargador |
| `tests/unit/test_api.py` | **CREATE** | Tests de integración del endpoint |

Archivos **sin cambio**: `src/smart_budget/model.py`, `filters.py`, `aggregator.py`, `conftest.py`, todos los tests existentes.

---

## Tareas de implementación

### T0 — Dependencias (requirements.txt)
Agregar después de la línea que contiene `pytest-cov`:
```
fastapi>=0.100.0
uvicorn[standard]>=0.20.0
httpx>=0.23.0
```
Verificar que `pytest` sigue funcionando con las nuevas deps instaladas.

---

### T1 — Cargador unificado (`src/smart_budget/loader.py`)

**Función pública principal:**
```python
def load_history(
    idaccount: str,
    defaultcategory: str,
    base_dir: str | Path,
) -> pd.DataFrame:
    """
    Retorna historial mensual pre-agregado para (idaccount, defaultcategory).

    Estrategia de fuentes:
    - Si idaccount está en smart_budget_synthetic.csv → usar solo synthetic.
    - Si no → cargar test_internal.csv + test_external.csv, aplicar
      filter_transactions, normalización de signo OLB, aggregate_monthly.

    Returns:
        DataFrame con columnas: idclient, idcompany, idaccount, idcategory,
        defaultcategory, period_yyyymm, monthly_total.
        Puede ser vacío si no hay datos para la combinación solicitada.

    Raises:
        FileNotFoundError: si ninguna fuente CSV existe en base_dir.
    """
```

**Funciones internas (privadas, todas con type hints + docstrings Google):**
- `_synthetic_accounts(base_dir: Path) -> set[str]` — carga synthetic CSV, retorna `set(df["idaccount"])`. Cacheable (lectura única por proceso).
- `_load_synthetic_for_account(idaccount, defaultcategory, base_dir) -> pd.DataFrame` — filtra synthetic por los dos params.
- `_normalize_olb_amounts(df: pd.DataFrame) -> pd.DataFrame` — aplica `abs()` a rows con `idtransaction.str.startswith(("SUB","LOAN"))`.
- `_load_raw_for_account(idaccount, defaultcategory, base_dir) -> pd.DataFrame` — carga ambos raw CSVs, aplica `filter_transactions`, `_normalize_olb_amounts`, agrega `idcategory = defaultcategory`, llama `aggregate_monthly`, filtra por (idaccount, defaultcategory).

**Paths de datos (dentro de `base_dir`):**
- `smart_budget_synthetic.csv`
- `test/test_internal.csv`
- `test/test_external.csv`

---

### T2 — FastAPI app (`src/api/router.py` + `src/main.py`)

**router.py** — contiene el router y el endpoint:

```python
router = APIRouter(prefix="/smart-budget", tags=["Smart Budget"])

@router.get("/suggestion", response_model=SuggestionResponse)
def get_suggestion(
    idaccount: str = Query(..., description="ID de la cuenta del miembro"),
    defaultcategory: str = Query(..., description="Nombre de la categoría (ej: GROCERIES)"),
    period_id: str = Query(..., description="Mes a presupuestar (YYYY-MM)"),
) -> SuggestionResponse:
```

**Lógica interna del endpoint (en orden):**
1. Validar formato `period_id` → regex `^\d{4}-\d{2}$`; si no cumple → 422
2. `reference_date = str(pd.Period(period_id, freq="M") - 1)` → YYYY-MM
3. `base_dir = Path(os.getenv("SMART_BUDGET_DATA_DIR", "data/dough"))`
4. `history = load_history(idaccount, defaultcategory, base_dir)` → DataFrame
5. Si `history.empty` → `raise HTTPException(status_code=404, detail="idaccount not found")`
6. `gated = apply_gating(history, min_months=2)` → si vacío → retornar null response (200)
7. `results = compute_budget_suggestions(gated, method="wma", treatment="B", reference_date=reference_date, lookback_months=3)`
8. Si `not results` → retornar null response (200)
9. Seleccionar `r = results[0]` (único bucket — filtrado por idaccount + defaultcategory)
10. Mapear al schema de response (eliminar `explanation`, `category_id`; añadir `period_id`)
11. Si `r["suggested_amount"] is None` → retornar null response con campos de `r`
12. Retornar `SuggestionResponse`

**Modelos Pydantic (en router.py o en `src/api/schemas.py`):**

```python
class BasisDetail(BaseModel):
    months_analyzed: int
    months_with_positive_spend: int
    period_range: str
    method: str
    treatment: str

class SuggestionResponse(BaseModel):
    idaccount: str
    idclient: str
    idcompany: str
    defaultcategory: str
    period_id: str
    suggested_amount: float | None
    confidence: str | None        # "high" | "medium" | "low" | None
    basis: BasisDetail | None
    display_label: str
    model_version: str
```

**main.py:**
```python
app = FastAPI(
    title="Smart Budget API",
    description="Fase 0 — Sugerencias de presupuesto on-demand",
    version="0.1.0",
)
app.include_router(router)
```

---

### T3 — Tests

**`tests/unit/test_loader.py`** — cubre:
- `load_history` con cuenta sintética (SYN001) → retorna df con columnas correctas
- `load_history` con cuenta OLB (INT23) → ruta raw, amounts positivos en output
- `load_history` con cuenta inexistente → retorna df vacío (no excepción)
- `_normalize_olb_amounts` → SUB prefix cambia a abs(), EXT prefix no cambia
- `load_history` con `defaultcategory` que no existe para esa cuenta → df vacío

**`tests/unit/test_api.py`** — cubre con `TestClient`:
- `GET /smart-budget/suggestion?idaccount=SYN001&defaultcategory=...&period_id=2026-05` → 200, todos los campos presentes
- `suggested_amount >= 0.0` en respuesta exitosa
- Cuenta inexistente → 404
- `period_id` mal formateado (ej: "2026/05") → 422
- Cuenta con datos insuficientes (mock: history con 1 mes) → 200, `confidence=null`, `suggested_amount=null`
- Campo `explanation` NO presente en response (solo para uso interno del modelo)
- `basis.method == "wma"` y `basis.treatment == "B"` en toda respuesta exitosa

---

### T4 — Validación FastAPI local

1. `pip install -r requirements.txt` — verificar que fastapi + uvicorn instalan sin conflictos
2. `pytest tests/ -v --cov=src/smart_budget --cov=src/api --cov-report=term-missing` — 0 failures, ≥85% coverage en nuevos módulos
3. `uvicorn src.main:app --reload --port 8001` — arrancar server localmente
4. `curl "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=2026-05"` — verificar response
5. `curl "http://localhost:8001/openapi.json"` — verificar OpenAPI schema generado por FastAPI

---

### T5 — Endpoint SageMaker (notebook)

**Archivo:** `notebooks/smart_budget_sagemaker_endpoint.ipynb`

**Guía de referencia:** `~/Downloads/safe-txn-enpoint (2).ipynb` (patrón SAFE con `SKLearnModel`)

**Artefactos necesarios:**

| Archivo | Descripción |
|---|---|
| `src/api/inference.py` | Script de inferencia SageMaker (`model_fn`, `input_fn`, `predict_fn`, `output_fn`) |
| `notebooks/smart_budget_sagemaker_endpoint.ipynb` | Notebook de deploy/test (patrón SAFE) |

**`src/api/inference.py` — contrato SageMaker:**

```python
def model_fn(model_dir: str):
    """Carga los artefactos del modelo desde model_dir.
    Para Smart Budget: retorna base_dir (path a los CSVs bundleados en model.tar.gz).
    """

def input_fn(input_data: str, content_type: str) -> dict:
    """Deserializa el request. Content-type: application/json.
    Esperado: {"idaccount": "...", "defaultcategory": "...", "period_id": "YYYY-MM"}
    """

def predict_fn(data: dict, model) -> dict:
    """Ejecuta el pipeline WMA y retorna el dict de sugerencia."""

def output_fn(prediction: dict, accept: str) -> str:
    """Serializa la respuesta a JSON string."""
```

**Estructura del `model.tar.gz`:**
```
model.tar.gz
├── inference.py                 ← entry_point de SageMaker
├── smart_budget/                ← copia del paquete src/smart_budget/
│   ├── __init__.py
│   ├── loader.py
│   ├── model.py
│   ├── aggregator.py
│   └── filters.py
└── data/
    ├── smart_budget_synthetic.csv
    ├── test_internal.csv
    └── test_external.csv
```

**Notebook — celdas principales:**
1. **Preparar `model.tar.gz`**: copiar src/ + data CSVs en directorio temp, crear tarball
2. **Upload a S3**: `s3://blossom-analytics-datalake-dev/smart_budget/endpoint/v1/model.tar.gz`
3. **Deploy con SKLearnModel**:
   ```python
   sk_model = SKLearnModel(
       model_data=model_artifact_uri,
       role=role,
       entry_point="inference.py",
       framework_version="1.2-1",
       sagemaker_session=sagemaker_session
   )
   predictor = sk_model.deploy(
       initial_instance_count=1,
       instance_type="ml.m5.large",
       endpoint_name="smart-budget-suggestion-endpoint"
   )
   ```
4. **Test del endpoint**: invocar via `sagemaker-runtime.invoke_endpoint` con JSON payload
5. **Verificar response**: campos esperados (suggested_amount, confidence, basis)
6. **Celda de delete endpoint** (marcada como `# ! Borrar cuando no se use — genera costo`)

**Decisiones del T5 (auto-cerradas):**

| Decisión | Elección | Razón |
|---|---|---|
| Bucket S3 | `blossom-analytics-datalake-dev` | Mismo bucket del datalake — perfil `blossom-dev` |
| Contenedor | `SKLearnModel` framework 1.2-1 | Patrón SAFE — mismo stack Python/pandas |
| Bundling de datos | CSVs dentro de `model.tar.gz` | Endpoint dev/test — no requiere S3 read en tiempo de inference |
| Instance type | `ml.m5.large` | Mismo que SAFE — suficiente para pandas + WMA |
| Input format | `application/json` | Más descriptivo que CSV para params estructurados |
| AWS profile | `blossom-dev` | Único perfil de dev disponible |

---

## Notas de diseño importantes

### ¿Por qué `reference_date = period_id − 1`?

El endpoint recibe `period_id = 2026-05` (mes a presupuestar). El historial debe
ser de meses **anteriores** al mes en cuestión. `lookback_months=3` con
`reference_date=2026-04` usa: 2026-02, 2026-03, 2026-04. Esto coincide con el
output de ejemplo acordado: `period_range: "2026-02 ~ 2026-04"`.

Si pasáramos `period_id` directo como `reference_date`, incluiríamos 2026-05 en
el historial — un mes que aún no tiene transacciones completas.

### ¿Por qué abs() solo en OLB y no en EXT?

`build_fact_transactions.py:289-290` ya aplica `abs()` a Plaid/EXT amounts antes de
guardarlos. Las transacciones OLB (SUB/LOAN) siguen la convención contable con
débitos negativos y se dejan as-is en el CSV. El loader debe compensar esta
asimetría para que `aggregate_monthly` produzca totals positivos correctos.

### ¿Por qué min_months=2 (no 3) en el endpoint?

El batch pipeline usa `min_months=3` (AGENTS.md run_methods.py default). Pero el
endpoint tiene una ventana fija de 3 meses (lookback). Con min_months=3, cualquier
bucket con un mes a cero quedaría gateado — demasiado restrictivo para on-demand.
El spec acordado dice: `<2 meses → null (gating)`. Ergo min_months=2.

---

## Cómo arrancar el server localmente

```bash
# Desde la raíz del repo (o del worktree)
pip install -r requirements.txt
SMART_BUDGET_DATA_DIR=data/dough uvicorn src.main:app --reload --port 8001

# Probar:
curl "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=2026-05"
curl "http://localhost:8001/docs"  # Swagger UI
```

---

## Backlinks

- `src/smart_budget/model.py` — `compute_budget_suggestions()` (función central, sin cambios)
- `src/smart_budget/aggregator.py` — `apply_gating()`, `aggregate_monthly()` (reusados directamente)
- `src/smart_budget/filters.py` — `filter_transactions()` (reusado en ruta raw)
- `changes/DATA-1140/refinement.md` — análisis de riesgo previo
- DATA-1138 — método WMA + Treatment B + lookback=3 (prerequisito cerrado)

---

**Decision: approved by Landneyker Betancourth — 2026-05-15**

All 17 DCR decisions AI-closed, HLTC blocks reviewed. T5 (SageMaker) manually
appended and confirmed in session. Ready for security + preflight + execute.
