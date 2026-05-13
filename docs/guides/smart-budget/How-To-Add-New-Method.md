---
title: How to Add a New Method
aliases: [New Method, Add Estimation Method, Extend model.py]
tags: [guide, smart-budget, model, extensibility]
type: guide
audience: ds-ml-engineer
last_mapped_at: 2026-05-13T10:20:00Z
---

# How to Add a New Estimation Method

## What this does

Agrega un nuevo método de sugerencia (e.g. MAD, percentil 75, regresión simple) al pipeline de Smart Budget.

## Before you start

- Entender la estructura del pipeline — leer [[01-core-model/Model]]
- Tests existentes pasando: `pytest tests/unit/test_model.py -v`

## Steps

### 1. Implementar la función en `model.py`

```python
# src/smart_budget/model.py

def compute_my_method(monthly_amounts: list[float]) -> float:
    """Calcula la sugerencia usando <nombre del método>.
    
    Args:
        monthly_amounts: Montos mensuales (ya con treatment aplicado, > 0).
                         Orden cronológico: [más_antiguo, ..., más_reciente].
    
    Returns:
        Monto sugerido en USD, redondeado a 2 decimales.
        Retorna 0.0 si la lista está vacía.
    """
    if not monthly_amounts:
        return 0.0
    
    # ... tu lógica aquí ...
    result = ...
    return round(result, 2)
```

**Reglas de la función:**
- Acepta una `list[float]` con Treatment ya aplicado (nunca recibe ceros si Treatment B)
- Retorna un `float` redondeado a 2 decimales
- Retorna `0.0` si la lista está vacía (no raise)
- Sin logs de montos individuales

### 2. Registrar en `compute_budget_suggestions()`

```python
# src/smart_budget/model.py — dentro de compute_budget_suggestions()

METHOD_DISPATCH: dict[str, Callable] = {
    "wma": compute_wma,
    "ewma": compute_ewma,
    "median": compute_median,
    "holt_winters": compute_holt_winters,
    "my_method": compute_my_method,    # ← agregar aquí
}
```

### 3. Registrar en el CLI (`run_methods.py`)

```python
# scripts/run_methods.py — argparse

parser.add_argument(
    "--method",
    choices=["wma", "ewma", "median", "holt_winters", "my_method"],  # ← agregar
    default="wma",
)
```

### 4. Escribir los tests

```python
# tests/unit/test_model.py

class TestMyMethod:
    def test_basic_case(self):
        result = compute_my_method([100.0, 200.0, 300.0])
        assert result == <expected>
    
    def test_empty_returns_zero(self):
        assert compute_my_method([]) == 0.0
    
    def test_single_value(self):
        assert compute_my_method([150.0]) == 150.0
    
    def test_rounds_to_two_decimals(self):
        result = compute_my_method([100.333, 200.666])
        assert result == round(result, 2)
```

### 5. Correr los tests

```bash
pytest tests/unit/test_model.py -v
pytest tests/ --cov=src/smart_budget --cov-report=term-missing
# Cobertura mínima esperada: 80%
```

### 6. Probar en CLI

```bash
python scripts/run_methods.py \
  --method my_method \
  --treatment B \
  --reference-date 2026-05 \
  --lookback-months 6 \
  --input data/dough/smart_budget_prep.csv \
  --output /tmp/my_method_results.json
```

## What you'll see when it works

El JSON de salida tendrá `"method": "my_method"` en el campo `basis` de cada sugerencia.

## Common problems

| Problem | Fix |
|---|---|
| `KeyError: 'my_method'` en dispatch | Verificar que el nombre en `METHOD_DISPATCH` coincide exactamente con `--method` |
| Sugerencias todas `null` con Treatment B | El método retorna `0.0` para lista vacía — revisar que el gating ya filtró esos casos |
| `round()` inconsistente | Usar siempre `round(result, 2)` al final — no truncar |

## FAQ

**¿Puedo usar statsmodels u otras librerías?** Sí, pero agregar a `requirements.txt`. Para la dependencia condicional (como Holt-Winters), puedes usar `try/except ImportError`.

**¿Qué hace `compute_confidence()`?** Se calcula sobre los meses con positive spend antes del treatment — no necesitas modificarla.

## Related guides

- [[How-To-Run-Pipeline]]
- [[01-core-model/Model]]
