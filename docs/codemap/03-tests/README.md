---
title: Tests
aliases: [Test suite, pytest, Unit tests, Integration tests]
tags: [module, tests, pytest, tdd]
type: module
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# Tests — `tests/`

**Path:** `tests/`
**Coverage:** ~93% (unit)

## Estructura

```
tests/
├── conftest.py               → Fixtures compartidas (DataFrames sintéticos, paths)
├── fixtures/                 → Archivos de datos para tests
│   ├── sample_transactions.csv
│   └── golden_set.csv        → Golden set de referencia (no PII)
└── unit/
    ├── test_filters.py       → 10 tests (Reglas 1-5 + edge cases)
    ├── test_aggregator.py    → 7 tests (aggregate, zero_fill, gating, idempotency)
    ├── test_model.py         → 38 tests (4 métodos, treatments, UDAAP, confidence)
    └── test_module_importable.py  → smoke test de importación
```

## Cómo correr los tests

```bash
# Todos los tests
pytest tests/ -v

# Solo un módulo
pytest tests/unit/test_filters.py -v
pytest tests/unit/test_aggregator.py -v
pytest tests/unit/test_model.py -v

# Con coverage
pytest tests/ --cov=src/smart_budget --cov-report=term-missing

# Marker específico (cuando se agreguen)
pytest tests/ -m "not integration"
```

## Convenciones

- **Fixtures en `conftest.py`**: DataFrames con datos sintéticos (sin PII). Nomenclatura: `df_<descripción>`.
- **Nomenclatura de tests**: `test_<función>_<caso>` — e.g. `test_filter_transactions_excludes_pending_olb`.
- **Datos de test**: nunca datos reales. Usar `generate_synthetic_dataset.py` o fakers.
- **Estructura**: Arrange-Act-Assert, sin comentarios de sección.

## Tests de regresión (golden set)

`tests/fixtures/golden_set.csv` contiene ~100 casos con `expected_suggestion`. El test en `test_model.py` corre el pipeline completo y verifica que `suggested_amount` coincide dentro de `±0.01`.

```python
def test_golden_set_regression(df_golden):
    results = compute_budget_suggestions(df_golden, method="wma", treatment="B")
    for r in results:
        expected = df_golden[...]["expected_suggestion"]
        assert abs(r["suggested_amount"] - expected) <= 0.01
```

## Multi-tenancy tests (anti-leak)

```bash
pytest tests/unit/test_aggregator.py::test_zero_fill_validates_no_cross_tenant_leak -v
```

El test crea un DataFrame con un mismo `idaccount` en dos `idcompany` diferentes y verifica que `zero_fill()` lance `ValueError` con mensaje claro.

## Backlinks

- [[README]]
- [[01-core-model/README]]

#tests #pytest #tdd #coverage
