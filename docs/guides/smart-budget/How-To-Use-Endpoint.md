---
title: How-To-Use-Endpoint
aliases: [Endpoint Smart Budget, API Local, SageMaker Endpoint]
tags: [guide, endpoint, api, sagemaker, inference]
type: guide
audience: ds-ml
ticket: DATA-1140
last_updated: 2026-05-15
---

# Cómo usar el endpoint Smart Budget

Guía para levantar el endpoint local (FastAPI) y opcionalmente desplegarlo en SageMaker.

> **Fase 0 — dev/test only.** El endpoint usa datos sintéticos y de prueba.
> No tiene autenticación. No apuntar a datos de producción sin revisión de PII.

---

## Prerequisitos

```bash
# Desde la raíz del repo (o worktree)
pip install -r requirements.txt
pip install -e .

# Si no hay pyproject.toml, usar PYTHONPATH en su lugar:
export PYTHONPATH="$(pwd)/src"

# Credenciales AWS (solo para extracción S3 o SageMaker)
aws sso login --profile blossom-dev
```

---

## Endpoint local (FastAPI)

### Levantar el servidor

```bash
# Desde la raíz del repo
export SMART_BUDGET_DATA_DIR="data/dough"
export PYTHONPATH="$(pwd)/src"    # si no tienes pip install -e .

uvicorn src.main:app --reload --port 8000
```

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

Query params (todos requeridos, validados por enum):
  idaccount        string   ID de la cuenta del miembro
  defaultcategory  string   Categoría a presupuestar
  period_id        string   Mes a presupuestar (formato YYYY-MM)
```

**Respuesta con sugerencia** (≥ 2 meses de historial):

```json
{
  "idaccount": "EXT2",
  "idclient": "1",
  "idcompany": "1",
  "defaultcategory": "Food & Dining",
  "period_id": "2026-05",
  "suggested_amount": 312.50,
  "confidence": "high",
  "basis": {
    "months_analyzed": 6,
    "months_with_positive_spend": 6,
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
```

**Respuesta sin sugerencia** (< 2 meses de historial o ventana sin datos):

```json
{
  "idaccount": "SYN001",
  "idclient": "1",
  "idcompany": "1",
  "defaultcategory": "Pets",
  "period_id": "2026-05",
  "suggested_amount": null,
  "confidence": null,
  "basis": null,
  "amount_by_month": null,
  "display_label": "No hay suficiente historial para esta categoría",
  "model_version": "fase0-v1"
}
```

#### Detalle de campos

| Campo | Tipo | Descripción |
|---|---|---|
| `suggested_amount` | `float \| null` | Sugerencia redondeada a 2 decimales; `null` si no hay suficiente historial |
| `confidence` | `"high" \| "medium" \| "low" \| null` | `high` ≥ 6 meses, `medium` 3–5, `low` 2 |
| `basis.months_analyzed` | `int` | Meses en la ventana de lookback (default: 3) |
| `basis.months_with_positive_spend` | `int` | Meses con gasto > 0 usados para calcular el WMA |
| `basis.method` | `string` | Siempre `"wma"` en Fase 0 |
| `basis.treatment` | `string` | Siempre `"B"` (treatment del modelo) |
| `basis.period_range` | `string` | Rango analizado, e.g. `"2025-11 ~ 2026-04"` |
| `amount_by_month` | `dict \| null` | Gasto mensual por mes de la ventana; `null` si no hay sugerencia |

#### Códigos de respuesta HTTP

| Código | Cuándo ocurre |
|---|---|
| `200` con datos | Solicitud válida y ≥ 2 meses de historial en la ventana |
| `200` con `null` | Cuenta existe pero: sin datos para esa categoría, o < 2 meses, o ventana sin solapamiento |
| `404` | `idaccount` no existe en ningún CSV de datos |
| `422` | Parámetro con valor fuera del enum (e.g. `period_id=2099-01`, `idaccount=INVALIDO`) |

---

### Valores válidos (enums)

#### `idaccount`

| Valor | Fuente de datos |
|---|---|
| `EXT2` | smart_budget_synthetic |
| `EXT22` | smart_budget_synthetic |
| `INT31880` | smart_budget_synthetic / test_internal |
| `SYN001` – `SYN008` | smart_budget_synthetic |

#### `defaultcategory`

`Auto & Transport` · `Bills & Utilities` · `Education` · `Entertainment & Leisure` ·
`Food & Dining` · `Gas` · `Gifts & Donations` · `Groceries` · `Health & Fitness` ·
`Home & Rent` · `Personal Care & Beauty` · `Pets` · `Shopping` · `Subscriptions` · `Travel & Trips`

#### `period_id`

`2025-09` · `2025-10` · `2025-11` · `2025-12` · `2026-01` · `2026-02` · `2026-03` · `2026-04` · `2026-05` · `2026-06`

---

### Escenarios de prueba

Los siguientes comandos `curl` cubren todos los casos de uso del endpoint (equivalentes a los test contracts TC-T2.1 – TC-T2.9):

#### TC-T2.1 — Happy path: cuenta con historial completo → 200 con sugerencia

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Food+%26+Dining&period_id=2026-05" | jq .
# Esperado: HTTP 200, suggested_amount > 0, confidence in ["high","medium","low"]
```

#### TC-T2.2 — `suggested_amount` siempre ≥ 0

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2026-05" | jq '.suggested_amount'
# Esperado: número >= 0.0, nunca negativo
```

#### TC-T2.3 — Método y treatment correctos

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN002&defaultcategory=Groceries&period_id=2026-05" | jq '.basis'
# Esperado: { "method": "wma", "treatment": "B", ... }
```

#### TC-T2.4 — El campo `explanation` NO debe aparecer en la respuesta

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Groceries&period_id=2026-05" | jq 'has("explanation")'
# Esperado: false
```

#### TC-T2.5 — Cuenta que no existe en ningún CSV → 404

```bash
# Esta cuenta está en el enum pero si no tiene datos en ningún CSV → 404
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=SYN008&defaultcategory=Groceries&period_id=2026-05"
# Esperado: 404 (la cuenta no tiene registros en los CSVs disponibles)
```

#### TC-T2.6 — Cuenta existe pero sin datos para esa categoría → 200 null

```bash
# La cuenta SYN001 existe, pero puede no tener historial en "Pets"
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Pets&period_id=2026-05" \
  | jq '{suggested_amount, display_label}'
# Esperado: { "suggested_amount": null, "display_label": "No hay suficiente historial para esta categoría" }
# → La cuenta EXISTE; simplemente no hay datos para esa categoría específica
```

#### TC-T2.7 — `period_id` fuera del enum → 422

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2099-01"
# Esperado: 422 (valor no listado en el enum PeriodId)
```

#### TC-T2.8 — Formato de fecha inválido → 422

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2026%2F05"
# Esperado: 422 (2026/05 no está en el enum — separador slash inválido)
```

#### TC-T2.9 — Ventana de lookback sin datos (período muy antiguo) → 200 null

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=SYN001&defaultcategory=Groceries&period_id=2025-09" | jq '{suggested_amount, confidence, basis}'
# Esperado: { "suggested_amount": null, "confidence": null, "basis": null }
# (ventana 2025-06~2025-08 está antes del historial disponible)
```

#### Caso extra — Ver desglose mensual (`amount_by_month`)

```bash
curl -s "http://localhost:8000/smart-budget/suggestion?idaccount=EXT2&defaultcategory=Groceries&period_id=2026-05" | jq '.amount_by_month'
# Esperado: objeto con claves YYYY-MM y valores float, e.g. {"2025-11": 200.5, "2025-12": 180.0, ...}
```

---

### Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `SMART_BUDGET_DATA_DIR` | `data/dough` | Directorio raíz donde buscar los CSVs |

El loader busca los CSVs en este orden de prioridad:

1. `$SMART_BUDGET_DATA_DIR/smart_budget_synthetic.csv` — datos pre-agregados (prioridad)
2. `$SMART_BUDGET_DATA_DIR/test/test_internal.csv` — transacciones OLB raw
3. `$SMART_BUDGET_DATA_DIR/test/test_external.csv` — transacciones Plaid raw

---

## Endpoint SageMaker (interno Blossom)

> **Prerequisito:** acceso al AWS account de Blossom (perfil `blossom-dev`).
> El endpoint corre en la red privada de AWS — no está expuesto a internet.

### Deploy completo

El notebook `notebooks/smart_budget_sagemaker_endpoint.ipynb` guía el proceso end-to-end:

```bash
# Abrir Jupyter desde la raíz del repo
jupyter notebook notebooks/smart_budget_sagemaker_endpoint.ipynb
```

El notebook ejecuta 4 pasos:

| Step | Qué hace |
|---|---|
| 1 — Empaquetar | Crea `model.tar.gz` con inference.py + CSVs de prueba |
| 2 — Subir a S3 | `s3://blossom-analytics-datalake-dev/smart_budget/endpoint/v1/model.tar.gz` |
| 3 — Deploy | `SKLearnModel.deploy()` → instancia `ml.m5.large` |
| 4 — Test | Invoca el endpoint y verifica la respuesta |

⚠️ **Ejecutar la celda de limpieza al terminar** — el endpoint genera costo por hora mientras esté activo.

### Invocar el endpoint desde Python (sin notebook)

```python
import boto3, json

# Requiere: aws sso login --profile blossom-dev
runtime = boto3.client(
    'sagemaker-runtime',
    region_name='us-east-1',
)

payload = json.dumps({
    'idaccount': 'EXT2',
    'defaultcategory': 'Food & Dining',
    'period_id': '2026-05',
})

response = runtime.invoke_endpoint(
    EndpointName='smart-budget-suggestion-endpoint',
    ContentType='application/json',
    Body=payload,
)

result = json.loads(response['Body'].read().decode('utf-8'))
print(result)
```

### Invocar con AWS CLI

```bash
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint \
  --content-type application/json \
  --body '{"idaccount":"EXT2","defaultcategory":"Groceries","period_id":"2026-05"}' \
  --profile blossom-dev \
  /tmp/sm_response.json

cat /tmp/sm_response.json | jq .
```

### Verificar estado del endpoint

```bash
aws sagemaker describe-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint \
  --profile blossom-dev \
  --query 'EndpointStatus'
# → "InService" si está activo
```

### Borrar el endpoint (evitar costos)

```bash
aws sagemaker delete-endpoint \
  --endpoint-name smart-budget-suggestion-endpoint \
  --profile blossom-dev
```

---

## Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Dependencias no instaladas | `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'smart_budget'` | Paquete no instalado en modo editable | `pip install -e .` |
| `404 Not Found` en `/suggestion` | El `idaccount` no existe en ningún CSV | Usar cuentas de la tabla de cuentas disponibles |
| `Base dir not found` en logs | `SMART_BUDGET_DATA_DIR` apunta a un path que no existe | Verificar que `data/dough/` existe y tiene los CSVs |
| SageMaker: `EndpointNotFound` | El endpoint no está desplegado | Correr el notebook completo (Steps 1-3) |
| SageMaker: `AccessDeniedException` | Sin credenciales AWS activas | `aws sso login --profile blossom-dev` |

---

## Backlinks

- [[How-To-Run-Pipeline]] — pipeline batch (alternativo al endpoint)
- `src/api/router.py` — implementación del endpoint FastAPI
- `src/api/inference.py` — script de inferencia SageMaker
- `notebooks/smart_budget_sagemaker_endpoint.ipynb` — deploy notebook completo
