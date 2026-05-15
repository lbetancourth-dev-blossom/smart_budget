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

# Credenciales AWS (solo para extracción S3 o SageMaker)
aws sso login --profile blossom-dev
```

---

## Endpoint local (FastAPI)

### Levantar el servidor

```bash
# Desde la raíz del repo
export SMART_BUDGET_DATA_DIR="data/dough"

uvicorn src.main:app --reload --port 8000
```

El servidor queda disponible en `http://localhost:8000`.

### Documentación interactiva

Abrir en el browser:

```
http://localhost:8000/docs      ← Swagger UI (recomendado para explorar)
http://localhost:8000/redoc     ← ReDoc
```

### Contrato del endpoint

```
GET /suggestion

Query params:
  idaccount        string  requerido  ID de la cuenta del miembro
  defaultcategory  string  requerido  Categoría a presupuestar
  period_id        string  requerido  Mes a presupuestar (formato YYYY-MM)
```

**Respuesta con sugerencia:**

```json
{
  "idaccount": "EXT2",
  "defaultcategory": "Food & Dining",
  "period_id": "2026-05",
  "suggested_amount": 312.50,
  "basis": {
    "months_analyzed": 6,
    "method": "wma",
    "data_points": 6,
    "period_range": "2025-11 ~ 2026-04"
  },
  "confidence": "high",
  "display_label": "Basado en tus últimos 6 meses",
  "model_version": "fase0-v1"
}
```

**Respuesta sin sugerencia** (< 2 meses de historial):

```json
{
  "idaccount": "EXT2",
  "defaultcategory": "Entertainment & Leisure",
  "period_id": "2026-05",
  "suggested_amount": null,
  "basis": null,
  "confidence": null,
  "display_label": "No hay suficiente historial para esta categoría",
  "model_version": "fase0-v1"
}
```

### Ejemplos con `curl`

```bash
# Cuenta con historial completo (synthetic)
curl "http://localhost:8000/suggestion?idaccount=EXT2&defaultcategory=Food+%26+Dining&period_id=2026-05"

# Otra cuenta — categoría diferente
curl "http://localhost:8000/suggestion?idaccount=SYN007&defaultcategory=Groceries&period_id=2026-05"

# Cuenta OLB test_internal
curl "http://localhost:8000/suggestion?idaccount=INT31880&defaultcategory=Gas&period_id=2026-05"

# Caso null — categoría sin suficiente historial
curl "http://localhost:8000/suggestion?idaccount=SYN001&defaultcategory=Pets&period_id=2026-05"

# Pretty print con jq
curl -s "http://localhost:8000/suggestion?idaccount=EXT2&defaultcategory=Groceries&period_id=2026-05" | jq .
```

### Cuentas y categorías disponibles en los datos de prueba

| idaccount | Fuente | Categorías con historial |
|---|---|---|
| `EXT2` | smart_budget_synthetic | Auto & Transport, Bills & Utilities, Food & Dining, Gas, Groceries, + más |
| `SYN007` | smart_budget_synthetic | ídem |
| `SYN002` | smart_budget_synthetic | ídem |
| `EXT22` | smart_budget_synthetic | ídem |
| `INT31880` | smart_budget_synthetic / test_internal | ídem |

Categorías disponibles: `Auto & Transport`, `Bills & Utilities`, `Entertainment & Leisure`,
`Food & Dining`, `Gas`, `Groceries`, `Health & Fitness`, `Home & Rent`, `Pets`, `Shopping`.

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
