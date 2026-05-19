# Implementation Spec — DATA-1140: Endpoint Smart Budget (on-demand)

## Runtime

- **Implementer**: `blossom-implementer`
- **Routing rationale**: stack `py-agents`, no Figma, no componentes de UI nuevos — implementación backend Python pura.

---

## File Manifest

| Archivo | Operación | Notas |
|---|---|---|
| `requirements.txt` | **MODIFY** | Agregar 4 deps: fastapi, uvicorn, httpx, sagemaker |
| `src/api/__init__.py` | **CREATE** | Paquete vacío |
| `src/api/router.py` | **CREATE** | Router + schemas Pydantic + lógica endpoint |
| `src/sagemaker/inference.py` | **CREATE** | Script de inferencia SageMaker |
| `src/sagemaker/__init__.py` | **CREATE** | Paquete vacío |
| `src/sagemaker/requirements.txt` | **CREATE** | Pins de ABI para container: numpy==1.23.5, pandas==1.5.3, structlog |
| `src/main.py` | **CREATE** | FastAPI app entry point |
| `src/smart_budget/loader.py` | **CREATE** | Cargador unificado de datos |
| `notebooks/smart_budget_sagemaker_endpoint.ipynb` | **CREATE** | Notebook deploy/test SageMaker |
| `tests/unit/test_loader.py` | **CREATE** | Tests del cargador (7 contratos) |
| `tests/unit/test_api.py` | **CREATE** | Tests de integración (8 contratos) |
| `tests/unit/test_inference.py` | **CREATE** | Tests del script SageMaker (6 contratos) |
| `src/smart_budget/model.py` | **MODIFY** | Lazy import de `ExponentialSmoothing` dentro de `compute_holt_winters()` para evitar conflicto ABI numpy en container sklearn:1.2-1 |
| `src/smart_budget/filters.py` | **UNCHANGED** | Sin modificaciones |
| `src/smart_budget/aggregator.py` | **UNCHANGED** | Sin modificaciones |
| `conftest.py` | **UNCHANGED** | Sin modificaciones |

---

## T0 — Dependencias

**Archivo**: `requirements.txt`

**Cambio**: insertar después de la línea que contiene `pytest-cov`:

```
# API
fastapi>=0.100.0
uvicorn[standard]>=0.20.0
httpx>=0.23.0
sagemaker>=2.200.0
```

**Test contract:**
```yaml
- name: test_requirements_installable
  input: "pip install -r requirements.txt (en entorno limpio)"
  expected: "exit code 0, fastapi importable, uvicorn importable, httpx importable"
```

---

## T1 — Cargador unificado (`src/smart_budget/loader.py`)

### Cabecera y constantes

```python
"""src/smart_budget/loader.py — Cargador unificado de datos para Smart Budget (DATA-1140).

Estrategia de fuentes:
  - Si idaccount está en smart_budget_synthetic.csv → usar solo synthetic (pre-agregado).
  - Si no → cargar test/test_internal.csv + test/test_external.csv, aplicar
    filter_transactions(), normalización de signo OLB, aggregate_monthly().
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
import structlog

from smart_budget.aggregator import aggregate_monthly
from smart_budget.filters import filter_transactions

logger = structlog.get_logger()

_SYNTHETIC_CSV = "smart_budget_synthetic.csv"
_RAW_INTERNAL_CSV = "test/test_internal.csv"
_RAW_EXTERNAL_CSV = "test/test_external.csv"
```

### Funciones privadas

#### `_synthetic_accounts(base_dir: Path) -> frozenset[str]`

```python
@lru_cache(maxsize=None)  # C2-fix: evita re-read del CSV en cada request
def _synthetic_accounts(base_dir: Path) -> frozenset[str]:
    """
    Retorna el conjunto de idaccount presentes en smart_budget_synthetic.csv.
    Cacheado por proceso — lectura única.
    """
    path = base_dir / _SYNTHETIC_CSV
    if not path.exists():
        return frozenset()
    df = pd.read_csv(path, usecols=["idaccount"], dtype=str)
    return frozenset(df["idaccount"].dropna().unique())
```

#### `_load_synthetic_for_account(idaccount, defaultcategory, base_dir) -> pd.DataFrame`

```python
def _load_synthetic_for_account(
    idaccount: str,
    defaultcategory: str,
    base_dir: Path,
) -> pd.DataFrame:
    """
    Filtra smart_budget_synthetic.csv por (idaccount, defaultcategory).
    Retorna df con columnas: idclient, idcompany, idaccount, idcategory,
    defaultcategory, period_yyyymm, monthly_total.
    """
    path = base_dir / _SYNTHETIC_CSV
    df = pd.read_csv(path, dtype=str)
    df["monthly_total"] = df["monthly_total"].astype(float)
    mask = (df["idaccount"] == idaccount) & (df["defaultcategory"] == defaultcategory)
    return df[mask].reset_index(drop=True)
```

#### `_normalize_olb_amounts(df: pd.DataFrame) -> pd.DataFrame`

```python
def _normalize_olb_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte amounts negativos de OLB (SUB/LOAN prefix) a positivos.
    Las transacciones EXT ya vienen positivas — no se tocan.

    Contexto: build_fact_transactions.py:289-290 aplica abs() a EXT pero no a OLB.
    El loader debe compensar para que aggregate_monthly produzca totals positivos.
    """
    out = df.copy()
    if "idtransaction" not in out.columns or "amount" not in out.columns:
        return out
    is_olb = out["idtransaction"].str.startswith(("SUB", "LOAN"), na=False)
    out.loc[is_olb, "amount"] = out.loc[is_olb, "amount"].abs()
    return out
```

#### `_load_raw_for_account(idaccount, defaultcategory, base_dir) -> pd.DataFrame`

```python
def _load_raw_for_account(
    idaccount: str,
    defaultcategory: str,
    base_dir: Path,
) -> pd.DataFrame:
    """
    Carga test_internal.csv + test_external.csv, aplica el pipeline de filtrado
    y agregación, y retorna el historial mensual para (idaccount, defaultcategory).

    Pipeline:
        1. Cargar ambos CSV (si existen)
        2. Concatenar
        3. filter_transactions()
        4. _normalize_olb_amounts()
        5. Filtrar por idaccount + defaultcategory
        6. Añadir idcategory = defaultcategory (proxy — raw CSV no tiene esta col)
        7. aggregate_monthly()
        8. Retornar filtrado final
    """
    frames = []
    for rel_path in (_RAW_INTERNAL_CSV, _RAW_EXTERNAL_CSV):
        path = base_dir / rel_path
        if path.exists():
            frames.append(
                pd.read_csv(path, dtype=str, keep_default_na=False)
            )

    if not frames:
        return pd.DataFrame()

    raw = pd.concat(frames, ignore_index=True)

    # Convertir columnas numéricas
    raw["amount"] = pd.to_numeric(raw["amount"], errors="coerce").fillna(0.0)
    for col in ["deletedat", "status"]:
        if col in raw.columns:
            raw[col] = raw[col].replace("", None)

    # Paso 3: filtros de negocio
    filtered = filter_transactions(raw)

    # Paso 4: normalizar sign OLB
    filtered = _normalize_olb_amounts(filtered)

    # Paso 5: filtrar por cuenta y categoría solicitadas
    mask = (
        (filtered["idaccount"] == idaccount)
        & (filtered["defaultcategory"] == defaultcategory)
    )
    filtered = filtered[mask].reset_index(drop=True)

    if filtered.empty:
        return pd.DataFrame()

    # Paso 6: añadir idcategory sintético (aggregate_monthly lo requiere)
    filtered["idcategory"] = filtered["defaultcategory"]

    # Paso 7: agregación mensual
    aggregated = aggregate_monthly(filtered)

    return aggregated[
        ["idclient", "idcompany", "idaccount", "idcategory",
         "defaultcategory", "period_yyyymm", "monthly_total"]
    ].reset_index(drop=True)
```

### Función pública

#### `load_history(idaccount, defaultcategory, base_dir) -> pd.DataFrame`

```python
def load_history(
    idaccount: str,
    defaultcategory: str,
    base_dir: str | Path = "data/dough",
) -> pd.DataFrame:
    """
    Retorna el historial mensual pre-agregado para (idaccount, defaultcategory).

    Estrategia de fuentes (data/dough/smart_budget_synthetic.csv toma prioridad):
    - Si idaccount está en synthetic → _load_synthetic_for_account()
    - Si no → _load_raw_for_account() (test_internal + test_external)

    Returns:
        DataFrame con columnas: idclient, idcompany, idaccount, idcategory,
        defaultcategory, period_yyyymm, monthly_total.
        Vacío si no hay datos para la combinación solicitada.

    Raises:
        FileNotFoundError: si base_dir no existe.
    """
    base = Path(base_dir)
    if not base.exists():
        raise FileNotFoundError(f"base_dir no encontrado: {base}")

    log = logger.bind(idaccount=idaccount, defaultcategory=defaultcategory)

    known_accounts = _synthetic_accounts(base)
    if idaccount in known_accounts:
        log.info("loader.source", source="synthetic")
        return _load_synthetic_for_account(idaccount, defaultcategory, base)

    log.info("loader.source", source="raw_csv")
    return _load_raw_for_account(idaccount, defaultcategory, base)
```

### Test contracts — T1

```yaml
test_contracts:
  - name: test_load_history_synthetic_account_returns_monthly_df
    input: "idaccount='SYN001', defaultcategory=primer category de SYN001 en synthetic CSV"
    expected: "DataFrame no vacío con columnas [idclient, idcompany, idaccount, idcategory, defaultcategory, period_yyyymm, monthly_total]; todos monthly_total >= 0"

  - name: test_load_history_raw_account_returns_positive_amounts
    input: "idaccount='INT23', defaultcategory='GROCERIES', base_dir apunta a fixtures tmp_path con test_internal.csv mínimo"
    expected: "DataFrame no vacío; monthly_total >= 0 en todas las filas (OLB abs() aplicado)"
    # C3-fix: usar tmp_path en lugar de data/dough real (gitignored)

  - name: test_load_history_unknown_account_returns_empty
    input: "idaccount='NONEXISTENT_XYZ', defaultcategory='GROCERIES'"
    expected: "DataFrame vacío (no excepción)"

  - name: test_load_history_nonexistent_category_returns_empty
    input: "idaccount='SYN001', defaultcategory='CATEGORIA_QUE_NO_EXISTE'"
    expected: "DataFrame vacío"

  - name: test_normalize_olb_amounts_sub_prefix
    input: "DataFrame con idtransaction='SUB123', amount=-150.0"
    expected: "amount == 150.0 en output (abs aplicado)"

  - name: test_normalize_olb_amounts_ext_prefix_unchanged
    input: "DataFrame con idtransaction='EXT456', amount=75.0"
    expected: "amount == 75.0 en output (sin cambio)"

  - name: test_load_history_raises_on_missing_base_dir
    input: "base_dir='/ruta/que/no/existe'"
    expected: "FileNotFoundError raised"
```

---

## T2 — FastAPI endpoint (`src/api/router.py` + `src/main.py`)

### `src/api/router.py` — schemas Pydantic + router

```python
"""src/api/router.py — FastAPI router para Smart Budget (DATA-1140)."""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import pandas as pd
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from smart_budget.aggregator import apply_gating
from smart_budget.loader import load_history, account_exists
from smart_budget.model import compute_budget_suggestions

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Enums para Swagger UI — dropdowns en "Try it out"
# Nota: se usan Enums (no str + regex) para mejorar UX del Swagger en dev.
# En producción (alpha/beta) se puede ampliar el catálogo de valores.
# ---------------------------------------------------------------------------

class IdAccount(str, Enum):
    EXT2 = "EXT2"
    EXT22 = "EXT22"
    INT31880 = "INT31880"
    SYN001 = "SYN001"
    # ... (valores del dataset sintético/dev)


class Category(str, Enum):
    auto_transport = "Auto & Transport"
    bills_utilities = "Bills & Utilities"
    food_dining = "Food & Dining"
    groceries = "Groceries"
    # ... (15 categorías de defaultcategory)


class PeriodId(str, Enum):
    p_2025_09 = "2025-09"
    p_2026_05 = "2026-05"
    p_2026_06 = "2026-06"
    # ... (10 meses en ventana dev)


# ---------------------------------------------------------------------------
# Schemas de respuesta
# ---------------------------------------------------------------------------

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
    confidence: str | None
    basis: BasisDetail | None
    amount_by_month: dict[str, float | None] | None  # montos mensuales de la ventana
    display_label: str
    model_version: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/smart-budget", tags=["Smart Budget"])

_METHOD = "wma"
_TREATMENT = "B"
_LOOKBACK = 3
_MIN_MONTHS_GATING = 2


@router.get("/suggestion", response_model=SuggestionResponse)
def get_suggestion(
    idaccount: IdAccount = Query(..., description="ID de la cuenta del miembro"),
    defaultcategory: Category = Query(..., description="Categoría a presupuestar"),
    period_id: PeriodId = Query(..., description="Mes a presupuestar (YYYY-MM)"),
) -> SuggestionResponse:
    """
    Calcula y retorna una sugerencia de presupuesto mensual on-demand.

    El historial considerado es los 3 meses ANTERIORES a period_id (lookback=3,
    reference_date = period_id − 1 mes). Method=WMA, Treatment=B (DATA-1138).
    """
            status_code=422,
            detail=f"period_id debe tener formato YYYY-MM, recibido: {period_id!r}",
        )

    # Paso 2: reference_date = period_id − 1 mes
    reference_date = str(pd.Period(period_id, freq="M") - 1)

    log = logger.bind(
        idaccount=idaccount,
        defaultcategory=defaultcategory,
        period_id=period_id,
        reference_date=reference_date,
    )
    log.info("smart_budget.suggestion.start")

    # Paso 3: base_dir desde env var
    base_dir = Path(os.getenv("SMART_BUDGET_DATA_DIR", "data/dough"))

    # Paso 4: cargar historial
    try:
        history = load_history(idaccount, defaultcategory, base_dir)
    except FileNotFoundError:
        log.error("smart_budget.suggestion.base_dir_not_found", base_dir=str(base_dir))
        raise HTTPException(status_code=500, detail="data directory not configured")

    # Paso 5: cuenta no encontrada
    if history.empty:
        log.info("smart_budget.suggestion.not_found")
        raise HTTPException(status_code=404, detail="idaccount not found")

    # Paso 6: gating — mínimo 2 meses con gasto positivo
    gated = apply_gating(history, min_months=_MIN_MONTHS_GATING)

    if gated.empty:
        log.info("smart_budget.suggestion.null", reason="gating_min_months")
        return _build_null_response(idaccount, history, defaultcategory, period_id)

    # Paso 7: compute_budget_suggestions
    results = compute_budget_suggestions(
        gated,
        method=_METHOD,
        treatment=_TREATMENT,
        reference_date=reference_date,
        lookback_months=_LOOKBACK,
    )

    if not results:
        log.info("smart_budget.suggestion.null", reason="no_results_in_window")
        return _build_null_response(idaccount, history, defaultcategory, period_id)

    r = results[0]

    # Paso 8: null suggestion (treatment B all-zeros en ventana)
    if r.get("suggested_amount") is None:
        log.info("smart_budget.suggestion.null", reason="treatment_b_all_zeros")
        return _build_null_response(idaccount, history, defaultcategory, period_id)

    log.info(
        "smart_budget.suggestion.done",
        confidence=r.get("confidence"),
    )

    basis = r.get("basis") or {}
    return SuggestionResponse(
        idaccount=r["idaccount"],
        idclient=r["idclient"],
        idcompany=r["idcompany"],
        defaultcategory=r["defaultcategory"],
        period_id=period_id,
        suggested_amount=r["suggested_amount"],
        confidence=r.get("confidence"),
        basis=BasisDetail(
            months_analyzed=basis.get("months_analyzed", 0),
            months_with_positive_spend=basis.get("months_with_positive_spend", 0),
            period_range=basis.get("period_range", ""),
            method=basis.get("method", _METHOD),
            treatment=basis.get("treatment", _TREATMENT),
        ),
        display_label=r.get("display_label", ""),
        model_version=r.get("model_version", "fase0-v1"),
    )


def _build_null_response(
    idaccount: str,
    history: pd.DataFrame,
    defaultcategory: str,
    period_id: str,
) -> SuggestionResponse:
    """Construye una respuesta null (datos insuficientes) desde el historial disponible."""
    idclient = str(history["idclient"].iloc[0]) if not history.empty else ""
    idcompany = str(history["idcompany"].iloc[0]) if not history.empty else ""
    return SuggestionResponse(
        idaccount=idaccount,
        idclient=idclient,
        idcompany=idcompany,
        defaultcategory=defaultcategory,
        period_id=period_id,
        suggested_amount=None,
        confidence=None,
        basis=None,
        display_label="No hay suficiente historial para esta categoría",
        model_version="fase0-v1",
    )
```

### `src/main.py`

```python
"""src/main.py — FastAPI application entry point (DATA-1140)."""
from fastapi import FastAPI

from .api.router import router  # relative import — required for `uvicorn src.main:app`

app = FastAPI(
    title="Smart Budget API",
    description="Fase 0 — Sugerencias de presupuesto on-demand (DS-ML dev endpoint)",
    version="0.1.0",
)

app.include_router(router)
```

### `src/api/__init__.py`

Archivo vacío — paquete Python.

### Test contracts — T2

```yaml
test_contracts:
  - name: test_get_suggestion_synthetic_account_returns_200
    input: "GET /smart-budget/suggestion?idaccount=SYN001&defaultcategory=<primer category>&period_id=2026-05"
    expected: "HTTP 200; body tiene campos: idaccount, idclient, idcompany, defaultcategory, period_id, suggested_amount, confidence, basis, display_label, model_version"

  - name: test_get_suggestion_suggested_amount_non_negative
    input: "GET /smart-budget/suggestion con cuenta/category con suficiente historial"
    expected: "suggested_amount >= 0.0"

  - name: test_get_suggestion_basis_method_and_treatment
    input: "GET /smart-budget/suggestion con cuenta/category válida"
    expected: "basis.method == 'wma'; basis.treatment == 'B'"

  - name: test_get_suggestion_explanation_not_in_response
    input: "GET /smart-budget/suggestion con cuenta válida"
    expected: "campo 'explanation' ausente en response body (solo campo interno del modelo)"

  - name: test_get_suggestion_unknown_account_returns_404
    input: "GET /smart-budget/suggestion?idaccount=CUENTA_INEXISTENTE_ZZZ&defaultcategory=GROCERIES&period_id=2026-05"
    expected: "HTTP 404"

  - name: test_get_suggestion_invalid_period_id_returns_422
    input: "GET /smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2026/05"
    expected: "HTTP 422"

  - name: test_get_suggestion_insufficient_data_returns_null_200
    input: "Mocked: load_history retorna 1 mes de datos → gating falla → null response"
    expected: "HTTP 200; confidence == null; suggested_amount == null; basis == null"

  - name: test_get_suggestion_period_id_not_in_historical_window
    input: "GET /smart-budget/suggestion con period_id en el futuro lejano (ej: 2030-01)"
    expected: "HTTP 200 con null response (no hay datos para la ventana)"
```

---

## T3 — Tests detallados

### `tests/unit/test_loader.py`

**Fixture de apoyo:** crear un directorio temporal con un CSV sintético mínimo
(3 accounts × 1 category × 6 periods) para tests de carga sin depender de `data/`.
Usar `tmp_path` de pytest para el `base_dir`.

**Pattern**: seguir `tests/unit/test_aggregator.py` — DataFrame en línea con columnas explícitas,
sin archivos externos cuando sea posible.

### `tests/unit/test_api.py`

```python
from fastapi.testclient import TestClient
from src.main import app  # o from main import app si el sys.path lo permite

client = TestClient(app)
```

**Fixture de datos**: usar `monkeypatch` para fijar `SMART_BUDGET_DATA_DIR` al
directorio con datos de prueba (usar `data/dough/` real o crear fixtures mínimos
en `tests/fixtures/`).

Para los tests de `mock`, usar `unittest.mock.patch("src.api.router.load_history")`
para inyectar DataFrames controlados sin depender de archivos.

---

## T4 — Verificación final

### V1 — Tests pasan
```bash
pytest tests/ -v --cov=src/smart_budget --cov=src/api --cov-report=term-missing
```
Criterio: 0 failures; cobertura nuevos módulos ≥ 80%.

### V2 — Linting
```bash
ruff check src/smart_budget/loader.py src/api/router.py src/main.py
black --check src/smart_budget/loader.py src/api/router.py src/main.py
```
Criterio: 0 errores.

### V3 — Servidor arranca
```bash
SMART_BUDGET_DATA_DIR=data/dough uvicorn src.main:app --port 8001 --reload
```
Criterio: `Application startup complete.`

### V4 — Smoke test real
```bash
curl -s "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=2026-05" | python3 -m json.tool
```
Criterio: JSON con `suggested_amount` (número o null) y `model_version: "fase0-v1"`.

### V5 — OpenAPI schema accesible
```bash
curl -s "http://localhost:8001/openapi.json" | python3 -m json.tool | grep '"title"'
```
Criterio: `"title": "Smart Budget API"` presente.

### V6 — 404 para cuenta inexistente
```bash
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8001/smart-budget/suggestion?idaccount=FAKE_ZZZ&defaultcategory=GROCERIES&period_id=2026-05"
```
Criterio: `404`.

### V7 — 422 para period_id inválido
```bash
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8001/smart-budget/suggestion?idaccount=INT23&defaultcategory=GROCERIES&period_id=bad"
```
Criterio: `422`.

### V8 — Tests pre-existentes no regresionan
```bash
pytest tests/unit/test_model.py tests/unit/test_aggregator.py tests/unit/test_filters.py -v
```
Criterio: todos pasan (0 regresiones en código existente).

---

## Execution Report (completar al finalizar)

```
[ ] T0 — requirements.txt actualizado, deps instaladas sin conflictos
[ ] T1 — src/smart_budget/loader.py creado, 7/7 test contracts pasan
[ ] T2 — src/api/router.py + src/main.py creados, 8/8 test contracts pasan
[ ] T3 — tests/unit/test_loader.py + test_api.py creados
[ ] T4 — V1 a V8 verificados (FastAPI local)
[ ] T5 — src/sagemaker/inference.py + notebook SageMaker creados

Coverage nuevos módulos: ____%
Tests totales: ____ passed / ____ failed
```

---

## T5 — Endpoint SageMaker

### Archivos

| Archivo | Operación |
|---|---|
| `src/sagemaker/inference.py` | **CREATE** — entry_point SageMaker |
| `notebooks/smart_budget_sagemaker_endpoint.ipynb` | **CREATE** — notebook deploy/test |

### `src/sagemaker/inference.py` — contrato SageMaker

```python
"""src/sagemaker/inference.py — Script de inferencia para endpoint SageMaker (DATA-1140).

Contrato SageMaker SKLearnModel:
  model_fn(model_dir) → carga artefactos; retorna base_dir como "model"
  input_fn(input_data, content_type) → deserializa JSON request → dict
  predict_fn(data, model) → ejecuta pipeline WMA → dict de sugerencia
  output_fn(prediction, accept) → serializa a JSON string

Formato de request (application/json):
  {"idaccount": "INT23", "defaultcategory": "GROCERIES", "period_id": "2026-05"}

Formato de response (application/json):
  {ver schema acordado en plan.md}
"""
import json
import os
from pathlib import Path
import pandas as pd

def model_fn(model_dir: str):
    """Retorna base_dir con los CSVs bundleados en model.tar.gz."""
    ...

def input_fn(input_data: str, content_type: str) -> dict:
    """Deserializa el request JSON."""
    ...

def predict_fn(data: dict, model) -> dict:
    """Ejecuta load_history → apply_gating → compute_budget_suggestions."""
    ...

def output_fn(prediction: dict, accept: str) -> str:
    """Serializa la respuesta a JSON string."""
    ...
```

### `notebooks/smart_budget_sagemaker_endpoint.ipynb` — estructura de celdas

El notebook debe seguir el patrón de `safe-txn-enpoint (2).ipynb` (Descargas/):

1. **Celda markdown**: título + descripción del endpoint
2. **Celda code**: imports (boto3, sagemaker, tarfile, os, pathlib)
3. **Celda markdown**: `### Step 1: Preparar model.tar.gz`
4. **Celda code**: crea directorio temp, copia `src/smart_budget/` + `data/dough/` (CSVs) + `src/sagemaker/inference.py`, crea tarball
   ```python
   # Estructura: inference.py + smart_budget/ + data/
   # Output: notebooks/model_artifacts/model.tar.gz
   ```
5. **Celda markdown**: `### Step 2: Upload model.tar.gz a S3`
6. **Celda code**: upload a `s3://blossom-analytics-datalake-dev/smart_budget/endpoint/v1/model.tar.gz`
7. **Celda markdown**: `### Step 3: Deploy con SKLearnModel`
8. **Celda code**:
   ```python
   from sagemaker.sklearn.model import SKLearnModel
   from sagemaker import get_execution_role, Session
   import sagemaker

   sagemaker_session = sagemaker.Session()
   role = get_execution_role()

   sk_model = SKLearnModel(
       model_data="s3://blossom-analytics-datalake-dev/smart_budget/endpoint/v1/model.tar.gz",
       role=role,
       entry_point="inference.py",
       framework_version="1.2-1",
       sagemaker_session=sagemaker_session,
   )
   predictor = sk_model.deploy(
       initial_instance_count=1,
       instance_type="ml.m5.large",
       endpoint_name="smart-budget-suggestion-endpoint",
   )
   ```
9. **Celda markdown**: `### Step 4: Test del endpoint`
10. **Celda code**:
    ```python
    import boto3, json
    runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")
    payload = json.dumps({"idaccount": "INT23", "defaultcategory": "GROCERIES", "period_id": "2026-05"})
    response = runtime.invoke_endpoint(
        EndpointName="smart-budget-suggestion-endpoint",
        ContentType="application/json",
        Body=payload,
    )
    result = json.loads(response["Body"].read().decode("utf-8"))
    print(result)
    ```
11. **Celda markdown**: `### ! Borrar endpoint (genera costo)`
12. **Celda code** (marcada `# !`): `client.delete_endpoint(EndpointName="smart-budget-suggestion-endpoint")`

### Test contracts para T5

```yaml
- name: test_inference_model_fn
  file: tests/unit/test_inference.py
  input: "model_fn(tmp_dir con CSVs bundleados)"
  expected: "retorna un Path que contiene los 3 CSVs"

- name: test_inference_input_fn_valid
  input: '{"idaccount": "INT23", "defaultcategory": "GROCERIES", "period_id": "2026-05"}'
  expected: "dict con exactamente las 3 claves"

- name: test_inference_input_fn_invalid_json
  input: "not-json"
  expected: "ValueError o similar"

- name: test_inference_predict_fn_returns_valid_schema
  input: "data con cuenta SYN001 que tiene historial"
  expected: "dict con suggested_amount float >= 0, confidence in ['low','medium','high']"

- name: test_inference_predict_fn_gating
  input: "data con cuenta que tiene 1 mes de historial"
  expected: "dict con suggested_amount=null, confidence=null"

- name: test_inference_output_fn
  input: "dict de sugerencia válido"
  expected: "string JSON parseable que contiene los campos del schema"
```

### Verificación T5

```bash
# V9 — inference.py importable y funciones definidas
python3 -c "from src.api.inference import model_fn, input_fn, predict_fn, output_fn; print('ok')"

# V10 — notebook existe y tiene todas las celdas
jupyter nbconvert --to script notebooks/smart_budget_sagemaker_endpoint.ipynb --stdout 2>/dev/null | grep -E "(deploy|invoke_endpoint|delete_endpoint)"
```
