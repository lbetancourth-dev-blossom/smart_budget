---
title: API · Public API
aliases: [router public surface, GET suggestion endpoint]
tags: [module, api, public-api]
type: api
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# API — Public API

## Endpoint

### `GET /smart-budget/suggestion`

Retorna la sugerencia de presupuesto para un miembro, categoría y período dados.

**Query params:**

| Param | Tipo | Valores válidos | Descripción |
|---|---|---|---|
| `idaccount` | `IdAccount` (Enum) | EXT1, EXT2, SYN1… / INT* | ID de cuenta del miembro |
| `category_id` | `int` | ID numérico de categoría | ID de categoría de gasto (de `smart_budget_transactions`) |
| `period_id` | `PeriodId` (Enum) | 2025-10, 2025-11 … 2026-05 | Período target en formato YYYY-MM |

**Respuestas:**

| Código | Condición | Body |
|---|---|---|
| `200` | Cuenta existe, sugerencia calculada | `SuggestionResponse` con `suggested_amount > 0` |
| `200` | Cuenta existe, historia insuficiente | `SuggestionResponse` con `suggested_amount=null` |
| `404` | `idaccount` desconocido | `{"detail": "Account not found"}` |
| `422` | Param inválido (enum mismatch) | Detail de validación de FastAPI |

## Pydantic schemas

### `SuggestionResponse`

```python
class SuggestionResponse(BaseModel):
    category_id: str
    suggested_amount: Optional[float]
    basis: Optional[BasisDetail]
    confidence: Optional[str]          # "high" | "medium" | "low" | None
    display_label: str
    model_version: str                 # "fase0-v1"
    amount_by_month: Optional[dict]    # {period: amount} — ventana de lookback
```

### `BasisDetail`

```python
class BasisDetail(BaseModel):
    months_analyzed: int
    method: str                        # "wma"
    data_points: int
    period_range: str                  # "2025-11 ~ 2026-01"
```

## Ejemplo de respuesta exitosa

```json
{
  "category_id": "Food",
  "suggested_amount": 420.00,
  "basis": {
    "months_analyzed": 3,
    "method": "wma",
    "data_points": 3,
    "period_range": "2025-11 ~ 2026-01"
  },
  "confidence": "medium",
  "display_label": "Basado en tus últimos 3 meses",
  "model_version": "fase0-v1",
  "amount_by_month": {
    "2025-11": 380.00,
    "2025-12": 450.00,
    "2026-01": 430.00
  }
}
```

## Ejemplo de respuesta null (historia insuficiente)

```json
{
  "category_id": "Travel",
  "suggested_amount": null,
  "basis": null,
  "confidence": null,
  "display_label": "No hay suficiente historial para esta categoría",
  "model_version": "fase0-v1",
  "amount_by_month": null
}
```

## Ejecución local

```bash
PYTHONPATH=src uvicorn src.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Backlinks

- [[04-api/README]]

#api #public-api #rest #contract
