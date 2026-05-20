---
title: SageMaker · Public API
aliases: [inference handlers, SageMaker contract, model_fn input_fn predict_fn output_fn]
tags: [module, sagemaker, public-api]
type: api
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# SageMaker — Public API

Las cuatro funciones del contrato `SKLearnModel` en `src/sagemaker/inference.py`.

## `model_fn(model_dir: str) -> str`

Carga el artifact y parchea `sys.path` para que el paquete `smart_budget` sea importable.

```python
def model_fn(model_dir: str) -> str:
    """Retorna model_dir como handle (los CSVs se cargan en predict_fn)."""
```

## `input_fn(input_data: str, content_type: str) -> dict`

Deserializa el payload JSON y valida `defaultcategory`.

**Input (JSON string):**
```json
{
  "idaccount": "EXT2",
  "defaultcategory": "Food",
  "period_id": "2026-05"
}
```

**Raises:** `ValueError` si `defaultcategory` no está en el catálogo de 15 categorías válidas.

## `predict_fn(data: dict, model: str) -> dict`

Corre el pipeline completo y retorna la sugerencia.

**Flujo:**
1. Verifica que `idaccount` existe (`account_exists`) — raise `ValueError` si no
2. Carga historia (`load_history`)
3. Calcula `reference_date = period_id − 1 mes`
4. Aplica gating (`apply_gating`)
5. Calcula sugerencia (`compute_budget_suggestions`)
6. Construye respuesta con `_build_amount_by_month`

**Output dict:**
```python
{
    "category_id": "Food",
    "suggested_amount": 420.00,        # None si gating falla
    "basis": {
        "months_analyzed": 3,
        "method": "wma",
        "data_points": 3,
        "period_range": "2025-11 ~ 2026-01"
    },
    "confidence": "medium",            # None si gating falla
    "display_label": "Basado en tus últimos 3 meses",
    "model_version": "fase0-v1",
    "amount_by_month": {"2025-11": 380.0, "2025-12": 450.0, "2026-01": 430.0}
}
```

## `output_fn(prediction: dict, accept: str) -> str`

Serializa el dict a JSON string.

```python
def output_fn(prediction: dict, accept: str) -> str:
    return json.dumps(prediction)
```

## Payload de invocación (notebook/BlossomAPI)

```python
import json

payload = json.dumps({
    "idaccount": "EXT2",
    "defaultcategory": "Food",
    "period_id": "2026-05"
})

response = predictor.predict(payload)
result = json.loads(response)
```

## Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `ValueError: idaccount not found` | `idaccount` no existe en los CSVs cargados | Verificar que el tarball incluye el account en `data/` |
| `ValueError: invalid category` | `defaultcategory` fuera del catálogo | Usar una de las 15 categorías válidas |
| `ImportError: numpy.core.multiarray` | `statsmodels` instalado con numpy incorrecto | Nunca instalar statsmodels en `sklearn:1.2-1` |
| `NameError: reference_date` | Bug en inference.py (líneas fusionadas) | Verificar líneas 133-134 son statements separados |

## Backlinks

- [[05-sagemaker/README]]

#sagemaker #public-api #inference #contract
