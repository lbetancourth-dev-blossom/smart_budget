# Tests

> Per-module AI agent context. Companion to `docs/codemap/03-tests/README.md`.

## Purpose

Suite de tests unitarios para los módulos core de Smart Budget. Cobertura ~93%.

## Where things live

```
tests/
├── conftest.py               → Fixtures compartidas (DataFrames sintéticos)
├── fixtures/
│   ├── sample_transactions.csv
│   └── golden_set.csv        → Golden set de referencia (sin PII)
└── unit/
    ├── test_filters.py       → 10 tests (Reglas 1-5 + edge cases)
    ├── test_aggregator.py    → 7 tests (aggregate, zero_fill, gating, idempotency)
    ├── test_model.py         → 38 tests (4 métodos, treatments, UDAAP, confidence)
    └── test_module_importable.py  → smoke test
```

## Key files

- `conftest.py` — fixtures base: `df_transactions_raw`, `df_filtered`, `df_aggregated`, `df_golden`
- `tests/fixtures/golden_set.csv` — ~100 casos con `expected_suggestion` para regression tests

## Conventions

- **Sin PII**: todos los datos son sintéticos (fakers o generados con `generate_synthetic_dataset.py`)
- Estructura Arrange-Act-Assert, sin comentarios de sección
- Nomenclatura: `test_<función>_<caso>` — e.g. `test_filter_transactions_excludes_pending_olb`
- Todo PR que toque `filters.py`, `aggregator.py` o queries SQL debe incluir un test nuevo o actualizar uno existente

## Dependencies

- Imports from: `smart_budget.filters`, `smart_budget.aggregator`, `smart_budget.model`
- External: `pytest`, `pytest-cov`, `pandas`, `numpy`

## Tests

- Run all: `pytest tests/ -v`
- Run with coverage: `pytest tests/ --cov=src/smart_budget --cov-report=term-missing`
- Cobertura mínima: 80% en `filters.py` y `aggregator.py`

## Gotchas

- El test de multi-tenancy anti-leak (`test_zero_fill_validates_no_cross_tenant_leak`) es crítico — nunca eliminar
- Los tests de golden set (`test_golden_set_regression`) toleran `±0.01` en `suggested_amount`
- `test_module_importable.py` falla si hay un import circular o dependencia faltante — es el canario

## See also

- [Module overview](../docs/codemap/03-tests/README.md)
- [Root project context](../CLAUDE.md)
