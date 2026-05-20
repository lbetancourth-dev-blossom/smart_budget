# smart_budget (Core Model)

> Per-module AI agent context. Companion to `docs/codemap/01-core-model/README.md`.

## Purpose

Pipeline de sugerencias de presupuesto mensual por categoría. Transforma transacciones históricas en sugerencias usando medianas ponderadas o suavizado exponencial.

## Where things live

```
src/smart_budget/
├── __init__.py         → exports públicos del módulo
├── filters.py          → 6 reglas de filtrado (never_bypass)
├── aggregator.py       → aggregate_monthly, zero_fill, apply_gating
└── model.py            → 4 métodos + compute_budget_suggestions()
```

## Key files

- `filters.py` — filtros no negociables: deletedat, expenditure, categoría válida, status OLB/EXT
- `aggregator.py` — pipeline: suma mensual → zero_fill → gating por bucket
- `model.py` — WMA, EWMA, Median, Holt-Winters + dispatch → JSON de sugerencia

## Conventions

- Type hints obligatorios en funciones públicas
- Docstrings estilo Google
- Comentarios en español
- Logs con `structlog` — nunca `print` ni log de montos individuales
- `from __future__ import annotations` en model.py (compat Python 3.9)

## Dependencies

- Imports from: ninguno (módulo raíz)
- Imported by: `scripts/run_smart_budget_prep.py`, `scripts/run_methods.py`
- External: `pandas`, `numpy`, `statsmodels` (solo para Holt-Winters), `structlog`

## Tests

- Run: `pytest tests/unit/ -v`
- Coverage: ~93%
- Files: `tests/unit/test_filters.py`, `tests/unit/test_aggregator.py`, `tests/unit/test_model.py`

## Gotchas

- **Nunca bypassear filtros de multi-tenancy** — toda función que procesa datos debe recibir y filtrar `idclient/idcompany/idaccount`
- **snapshot freeze**: la sugerencia emitida NUNCA se modifica retroactivamente — insertar nueva fila con timestamp distinto
- **confidence** se calcula sobre datos PRE-treatment (antes de aplicar A/B/C)
- **Treatment B con todos ceros** → retornar null suggestion, no error
- `compute_holt_winters` requiere `statsmodels` — si no está instalado, levanta `ImportError` con mensaje claro

## See also

- [Module overview](../../docs/codemap/01-core-model/README.md)
- [Root project context](../../CLAUDE.md)
