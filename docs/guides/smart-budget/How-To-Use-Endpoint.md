---
title: How-To-Use-Endpoint
aliases: [Endpoint Smart Budget, API Local, SageMaker Endpoint]
tags: [guide, endpoint, api, sagemaker, inference]
type: guide
audience: ds-ml
ticket: DATA-1275
last_updated: 2026-06-22
---

# Cómo usar el endpoint Smart Budget

Guía para levantar el endpoint local (FastAPI) y opcionalmente desplegarlo en SageMaker.

> **Fuente de datos:** Athena (`dlh_gold_dough_dev.smart_budget_transactions`).
> Los datos se consultan en tiempo real — no se empaquetan en el modelo.
> No tiene autenticación. No apuntar a datos de producción sin revisión de PII.

---

## Prerequisitos

```bash
# Desde la raíz del repo
cd /ruta/a/smart_budget

# Instalar dependencias en el virtualenv del repo
.venv/bin/pip install -r requirements.txt

# Credenciales AWS (solo para extracción S3 o SageMaker)
aws sso login --profile blossom-dev
```

> **Nota:** este repo no tiene `pyproject.toml` — `pip install -e .` fallará.
> El módulo `smart_budget` se expone via `PYTHONPATH=src` al levantar el servidor.

---

## Endpoint local (FastAPI)

### Levantar el servidor

```bash
# Desde la raíz del repo — variables requeridas:
#   PYTHONPATH=src             → expone smart_budget al import
#   ATHENA_S3_STAGING_DIR      → bucket S3 para resultados temporales de Athena
#   ATHENA_REGION_NAME         → región AWS (default: us-east-2)

PYTHONPATH=src \
ATHENA_S3_STAGING_DIR=s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/ \
ATHENA_REGION_NAME=us-east-2 \
.venv/bin/uvicorn src.main:app --reload --port 8000
```

> **Nota:** `smart_budget` vive en `src/smart_budget/`. Sin `PYTHONPATH=src` se lanza
> `ModuleNotFoundError: No module named 'smart_budget'`.
> Sin `ATHENA_S3_STAGING_DIR` la conexión a Athena fallará con `AthenaQueryError`.

El servidor queda disponible en `http://localhost:8000`.

### Documentación interactiva

Abrir en el browser:

```
http://localhost:8000/docs      ← Swagger UI con dropdowns (recomendado)
http://localhost:8000/redoc     ← ReDoc
```

> Los parámetros `idaccount`, `defaultcategory` y `period_id` aparecen como **listas
> desplegables** en el Swagger "Try it out" — solo los valores válidos son seleccionables.

---

### Contrato del endpoint

```
GET /smart-budget/suggestion

Query params (todos requeridos):
  idmember   string   ID del miembro (consultado contra Athena)
  period_id  string   Mes a presupuestar (formato YYYY-MM)
```

**Respuesta con sugerencia** (≥ 2 meses de historial):

```json
{
  "idmember": "18973",
  "idclient": "1",
  "idcompany": "2050",
  "period_id": "2026-05",
  "total_suggested": 312.50,
  "suggestions": [
    {
      "category_id": "FOOD_DINING",
      "category_name": "Food & Dining",
      "suggested_amount": 312.50,
      "confidence": "high",
      "basis": {
        "months_analyzed": 6,
        "months_with_spend": 6,
        "method": "wma",
        "treatment": "B",
        "period_range": "2025-11 ~ 2026-04"
      },
      "amount_by_month": {
        "2025-11": 290.00,
        "2025-12": 310.00,
        "2026-01": 305.00,
        "2026-02": 320.00,
        "2026-03": 330.00,
        "2026-04": 315.00
      },
      "display_label": "Basado en tus últimos 6 meses",
      "model_version": "fase0-v1"
    }
  ],
  "message": "Based on your last 3 months",
  "method": "wma",
  "treatment": "B",
  "model_version": "fase0-v1"
}
```

**Respuesta sin sugerencia** (< 2 meses de historial o sin datos):

```json
{
  "idmember": "99999",
  "idclient": "",
  "idcompany": "",
  "period_id": "2026-05",
  "total_suggested": null,
  "suggestions": null,
  "message": "Not enough history to calculate suggestions. At least 2 months of data required.",
  "method": "wma",
  "treatment": "B",
  "model_version": "fase0-v1"
}
```

#### Detalle de campos

| Campo | Tipo | Descripción |
|---|---|---|
| `total_suggested` | `float \| null` | Suma de todos los `suggested_amount` |
| `suggestions` | `array \| null` | Sugerencias por categoría; `null` si no hay historial suficiente |
| `suggestions[].category_id` | `string` | ID de la categoría desde Athena |
| `suggestions[].category_name` | `string` | Nombre de la categoría desde Athena |
| `suggestions[].suggested_amount` | `float \| null` | Sugerencia redondeada a 2 decimales |
| `confidence` | `"high" \| "medium" \| "low" \| null` | `high` ≥ 6 meses, `medium` 3–5, `low` 2 |
| `basis.months_analyzed` | `int` | Meses en la ventana de lookback (default: 3) |
| `basis.months_with_spend` | `int` | Meses con gasto > 0 usados para calcular el WMA |
| `basis.method` | `string` | Siempre `"wma"` en Fase 0 |
| `basis.treatment` | `string` | Siempre `"B"` (treatment del modelo) |
| `basis.period_range` | `string` | Rango analizado, e.g. `"2025-11 ~ 2026-04"` |
| `amount_by_month` | `dict \| null` | Gasto mensual por mes de la ventana |

#### Códigos de respuesta HTTP

| Código | Cuándo ocurre |
|---|---|
| `200` con datos | Miembro encontrado con ≥ 2 meses de historial |
| `200` con `null` | Miembro existe en Athena pero sin historial suficiente |
| `404` | `idmember` no existe en la tabla Athena |
| `422` | Formato de `period_id` inválido |
| `500` | Error de conexión a Athena (`AthenaQueryError`) |

---

### Valores válidos

#### `idmember`

Cualquier `idmember` existente en `dlh_gold_dough_dev.smart_budget_transactions`. El endpoint retorna `404` si el miembro no existe en Athena.

Para verificar si un miembro existe:
```python
from smart_budget.athena_loader import member_exists_athena
member_exists_athena("18973")  # → True / False
```

#### `period_id`

Cualquier mes en formato `YYYY-MM` (e.g. `2026-05`). El lookback usa los 3 meses previos al `period_id` indicado.

---

### Reglas de validación

El endpoint aplica 3 reglas en orden antes de calcular la sugerencia:

| # | Regla | Condición | Respuesta |
|---|---|---|---|
| 1 | Miembro no existe | `idmember` no está en Athena | `404 Not Found` |
| 2 | Sin historial para el período | Miembro existe pero sin datos en la ventana | `200` con `suggestions: null` |
| 3 | Historial insuficiente | Miembro con datos, pero < 2 meses con gasto > 0 | `200` con `suggestions: null` |

> **Regla 3 en detalle:** gating mínimo de 2 meses con gasto positivo para emitir una sugerencia confiable.

---

### Escenarios de prueba (TC-T2.1 – TC-T2.8)

| TC | Regla | Descripción | HTTP | `suggested_amount` |
|---|---|---|---|---|
| T2.1 | — | Happy path — cuenta con historial completo | `200` | valor > 0 |
| T2.2 | — | `suggested_amount` nunca negativo | `200` | ≥ 0.0 |
| T2.3 | — | `basis.method == "wma"`, `treatment == "B"` | `200` | valor > 0 |
| T2.4 | — | Campo `explanation` ausente en la respuesta | `200` | — |
| T2.5 | **Regla 1** | Cuenta **no existe** en los datos | `404` | — |
| T2.6 | **Regla 2** | Categoría **no reconocida** (fuera del catálogo) | `422` | — |
| T2.7 | **Regla 3a** | Cuenta y categoría existen, **sin datos** para esa combinación | `200` | `null` |
| T2.8 | **Regla 3b** | Cuenta y categoría existen, historial **< 2 meses** (gating) | `200` | `null` |

---

#### TC-T2.1 — Happy path: cuenta con historial completo → 200

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Food+%26+Dining&period_id=2026-05" | jq .
# Esperado: HTTP 200, suggested_amount > 0, confidence in ["high","medium","low"]
```

#### TC-T2.2 — `suggested_amount` siempre ≥ 0

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Pets&period_id=2026-05" | jq '.suggested_amount'
# SYN001 tiene datos de Pets; esperado: número >= 0.0, nunca negativo
```

#### TC-T2.3 — Método y treatment correctos

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN002&defaultcategory=Groceries&period_id=2026-05" | jq '.basis'
# Esperado: { "method": "wma", "treatment": "B", ... }
```

#### TC-T2.4 — El campo `explanation` NO debe aparecer en la respuesta

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Food+%26+Dining&period_id=2026-05" | jq 'has("explanation")'
# Esperado: false
```

#### TC-T2.5 — Regla 1: Cuenta no existe → 404

La cuenta `idaccount` no está en ningún CSV de datos.

> **Nota:** El Swagger UI solo muestra los accounts del dropdown (todos existen en el CSV),
> por lo que el 404 no es alcanzable desde la UI. Para probarlo en curl, hay que enviar
> un valor que **no está en el enum** — FastAPI retornará 422 (validación de enum primero).
> La única forma de disparar el 404 real es bypasear la validación del enum:

```bash
# Opción A — Con un account fuera del enum: FastAPI retorna 422 (validación antes del negocio)
curl -s -w "\nHTTP %{http_code}\n" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=CUENTA_INEXISTENTE&defaultcategory=Groceries&period_id=2026-05"
# Resultado: HTTP 422 (el enum rechaza el valor antes de llegar a la lógica)

# Opción B — Bypasear el enum con el flag --no-enum-validation (solo dev/test):
# Agrega temporalmente el account al enum en router.py, borra el CSV, y prueba:
curl -s -w "\nHTTP %{http_code}\n" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=CUENTA_SIN_CSV&defaultcategory=Groceries&period_id=2026-05"
# Resultado esperado: HTTP 404
# { "detail": "idaccount not found" }

# Opción C — Reproducción directa en tests (recomendada):
# pytest tests/unit/test_api.py::test_get_suggestion_account_not_found_returns_404 -v
# El mock pone account_exists=False y confirma que router devuelve 404.
```

#### TC-T2.6 — Regla 2: Categoría no reconocida → 422

FastAPI valida `defaultcategory` contra el catálogo de categorías antes de ejecutar cualquier
lógica. Si el valor no está en el catálogo → 422.

```bash
# Categoría que no existe en el catálogo
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=CategoriaInexistente&period_id=2026-05"
# Esperado: 422

# También aplica a period_id fuera del rango válido
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2099-01"
# Esperado: 422
```

#### TC-T2.7 — Regla 3a: Cuenta y categoría existen, sin datos → 200 null

SYN001 **existe** en el CSV sintético, `Groceries` **es una categoría válida**, pero SYN001
no tiene transacciones de Groceries (sus categorías son: `Auto & Transport`, `Bills & Utilities`,
`Entertainment & Leisure`, `Home & Rent`, `Pets`).

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2026-05" \
  | jq '{suggested_amount, confidence, basis, display_label}'
# Esperado:
# {
#   "suggested_amount": null,
#   "confidence": null,
#   "basis": null,
#   "display_label": "No hay suficiente historial para esta categoría"
# }
```

Otros ejemplos con la misma respuesta: `SYN008 + Groceries`, `SYN001 + Education`.

#### TC-T2.8 — Regla 3b: Cuenta y categoría existen, historial < 2 meses → 200 null

La cuenta y la categoría tienen datos, pero la cantidad de meses con gasto positivo en la
ventana de lookback es menor a 2 (mínimo requerido para una sugerencia confiable).
Se verifica vía test unitario (mock `n_months=1`).

```bash
# Buscar un account+categoría con muy poco historial en los CSVs de prueba
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN008&defaultcategory=Gas&period_id=2025-09" \
  | jq '{suggested_amount, confidence, basis}'
# Si hay < 2 meses en esa ventana:
# { "suggested_amount": null, "confidence": null, "basis": null }
# Nota: el resultado concreto depende del historial disponible en los CSVs.
```

#### Caso extra — Ver desglose mensual (`amount_by_month`)

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Groceries&period_id=2026-05" | jq '.amount_by_month'
# Esperado: objeto con claves YYYY-MM y valores float, e.g. {"2025-11": 200.5, "2025-12": 180.0, ...}
```

---

### Variables de entorno

| Variable | Default | Requerida | Descripción |
|---|---|---|---|
| `ATHENA_S3_STAGING_DIR` | — | ✅ | Bucket S3 para resultados temporales de Athena |
| `ATHENA_REGION_NAME` | `us-east-2` | — | Región AWS del workgroup Athena |
| `ATHENA_DATABASE` | `dlh_gold_dough_dev` | — | Base de datos Glue |
| `ATHENA_TABLE` | `smart_budget_transactions` | — | Tabla Glue |
| `SB_ENV` | `dev` | — | Entorno activo (`dev` \| `alpha`) — controla el dropdown de idmember en Swagger |

---

## Endpoint SageMaker (interno Blossom)

> **Prerequisito:** acceso al AWS account de Blossom (perfil `blossom-dev`).
> El endpoint corre en la red privada de AWS — no está expuesto a internet.

### Reglas de validación

El endpoint SageMaker aplica las mismas 3 reglas que el endpoint local FastAPI:

| # | Regla | Condición | Comportamiento SageMaker |
|---|---|---|---|
| 1 | Cuenta no existe | `idaccount` no está en los datos | Error 400 — `ValueError: idaccount not found` |
| 2 | Categoría no válida | `defaultcategory` no reconocida | Error 400 — `ValueError: invalid defaultcategory` |
| 3 | Sin datos para el período | Cuenta y categoría existen, sin historial | Respuesta válida con `suggested_amount: null` |

> En SageMaker no hay códigos HTTP 404/422 como en FastAPI — los errores de validación
> llegan como excepciones que SageMaker retorna como error 400 (`ModelError`).

### ⚠️ Compatibilidad de imagen de SageMaker Studio

> **Nota:** "3.8.5" se refiere a la **imagen de distribución de SageMaker Studio**
> (`sagemaker-distribution:3.8.5`), no a la versión de la librería `sagemaker`.

| Imagen (`sagemaker-distribution`) | Funciona | Notas |
|---|---|---|
| `3.8.5` | ✅ | `SKLearnModel`, `get_execution_role()` funcionan sin configuración adicional |
| `4.0.x` | ⚠️ | `sagemaker_core` instalado vía conda pero no en el path de pip — requiere fix |
| `4.1.x` | ⚠️ | Mismo comportamiento que 4.0 |

Si usas imagen `4.x`, la primera celda del notebook instala `sagemaker-core` vía pip
para ponerlo en el path correcto del kernel. **Reiniciar el kernel después de correr esa celda.**

### Deploy completo

El notebook `notebooks/smart_budget_sagemaker_endpoint.ipynb` guía el proceso end-to-end:

```bash
# Abrir Jupyter desde la raíz del repo
jupyter notebook notebooks/smart_budget_sagemaker_endpoint.ipynb
```

El notebook ejecuta 4 pasos:

| Step | Qué hace |
|---|---|
| 1 — Empaquetar | Crea `model.tar.gz` con `inference.py` + código del modelo (sin CSV) |
| 2 — Subir a S3 | `s3://blossom-analytics-safe-dev-nv/smart_budget/endpoint/v1/{ENV}/model.tar.gz` |
| 3 — Deploy | `SKLearnModel.deploy()` con env vars Athena → instancia `ml.m5.large` |
| 4 — Test | Invoca el endpoint y verifica la respuesta |

> **Nota:** Los datos **no se empaquetan** en el tarball. El endpoint consulta Athena en cada invocación usando las env vars `ATHENA_*` que se pasan al `SKLearnModel`.

⚠️ **Ejecutar la celda de limpieza al terminar** — el endpoint genera costo por hora mientras esté activo.

### Invocar el endpoint desde Python (sin notebook)

```python
import boto3, json

# Requiere: aws sso login --profile blossom-dev
runtime = boto3.client('sagemaker-runtime', region_name='us-east-2')

ENDPOINT_NAME = 'smart-budget-suggestion-endpoint-dev'  # o -alpha

def invoke(idmember: str, period_id: str) -> dict:
    payload = json.dumps({'idmember': idmember, 'period_id': period_id})
    try:
        response = runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType='application/json',
            Body=payload,
        )
        return json.loads(response['Body'].read().decode('utf-8'))
    except runtime.exceptions.ModelError as e:
        # Miembro no existe en Athena → ModelError
        print(f"Error: {e}")
        return None

# Happy path — miembro con historial
result = invoke('18973', '2026-05')
print(result['total_suggested'])    # → float > 0
print(result['suggestions'][0]['category_name'])  # → "Groceries"

# Miembro sin historial suficiente → suggestions null
result = invoke('18973', '2026-05')
print(result['suggestions'])   # → None si < 2 meses

# Miembro no existe → ModelError (capturado arriba)
result = invoke('INEXISTENTE', '2026-05')   # → None
```

### Invocar con AWS CLI

```bash
# Happy path → total_suggested > 0
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint-dev \
  --content-type application/json \
  --body '{"idmember":"18973","period_id":"2026-05"}' \
  --region us-east-2 \
  --profile blossom-dev \
  /tmp/sm_response.json && cat /tmp/sm_response.json | jq .

# Miembro no existe → ModelError 400
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint-dev \
  --content-type application/json \
  --body '{"idmember":"INEXISTENTE","period_id":"2026-05"}' \
  --region us-east-2 \
  --profile blossom-dev \
  /tmp/sm_err.json
# Body: {"error": "ValueError: idmember not found: 'INEXISTENTE'"}

# Sin historial → suggestions null
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint-dev \
  --content-type application/json \
  --body '{"idmember":"18973","period_id":"2019-01"}' \
  --region us-east-2 \
  --profile blossom-dev \
  /tmp/sm_response.json && cat /tmp/sm_response.json | jq '{total_suggested, suggestions}'
# → { "total_suggested": null, "suggestions": null }
```

### Verificar estado del endpoint

```bash
aws sagemaker describe-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint-dev \
  --region us-east-2 \
  --profile blossom-dev \
  --query 'EndpointStatus'
# → "InService" si está activo
```

### Borrar el endpoint (evitar costos)

```bash
aws sagemaker delete-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint-dev \
  --region us-east-2 \
  --profile blossom-dev
```

---

## Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Dependencias no instaladas | `.venv/bin/pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'smart_budget'` | `PYTHONPATH` no apunta a `src/` | Usar `PYTHONPATH=src` al inicio del comando uvicorn |
| `AthenaQueryError` en logs | `ATHENA_S3_STAGING_DIR` no configurado o credenciales AWS inactivas | Verificar env vars + `aws sso login --profile blossom-dev` |
| `404 Not Found` en `/suggestion` | `idmember` no existe en la tabla Athena | Verificar con `member_exists_athena(idmember)` |
| `ModelError` en SageMaker | Miembro no existe o Athena inaccesible | Verificar credenciales IAM del execution role |
| SageMaker: `EndpointNotFound` | El endpoint no está desplegado | Correr el notebook completo (Steps 1-3) |
| SageMaker: `AccessDeniedException` | Sin credenciales AWS activas | `aws sso login --profile blossom-dev` |

---

## Backlinks

- [[How-To-Run-Pipeline]] — pipeline batch (alternativo al endpoint)
- `src/api/router.py` — implementación del endpoint FastAPI
- `src/api/inference.py` — script de inferencia SageMaker
- `notebooks/smart_budget_sagemaker_endpoint.ipynb` — deploy notebook completo
