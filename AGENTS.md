# AI Agent Instructions

> Read this before making any changes to this repo.

## Module map

| Module | Path | Purpose |
|---|---|---|
| Core Model | `src/smart_budget/` | Filtros, agregación y modelo de sugerencias |
| Scripts ETL | `scripts/` | Extracción S3, build, CLI de métodos |
| Tests | `tests/` | pytest — cobertura ~93% |

## Critical files

- `src/smart_budget/filters.py` — 5 reglas de filtrado **nunca bypassear**
- `src/smart_budget/aggregator.py` — aggregate_monthly, zero_fill, apply_gating
- `src/smart_budget/model.py` — 4 métodos + compute_budget_suggestions() — punto de escritura del output
- `scripts/run_methods.py` — CLI principal del pipeline
- `tests/fixtures/golden_set.csv` — golden set de regresión

## Architecture rules

- **Batch-only**: nunca calcular sugerencias en tiempo de request — siempre pre-calcular en pipeline
- **Snapshot freeze**: sugerencia emitida = inmutable. Nuevos datos → nueva fila, nunca UPDATE
- **Multi-tenancy**: toda función que procesa datos filtra `idclient/idcompany/idaccount`. Nunca cross-tenant
- **Idempotencia**: el pipeline puede repetirse N veces el mismo día sin duplicar filas (`UPSERT` por clave única)
- `smartBudgetSuggestionLog` es **APPEND-ONLY** — nunca UPDATE ni DELETE

## Security considerations

- Nunca loguear montos individuales de transacciones
- Member IDs en logs: hashear con SHA-256 + `SB_LOG_SALT`
- Nunca commitear CSVs con datos reales (`data/` está en `.gitignore`)
- Toda escritura de archivo usa `chmod 600` automáticamente
- Nunca apuntar credenciales a producción sin revisión de PII

## Patterns to follow

- `structlog` para todos los logs (nunca `print`)
- Type hints en funciones públicas
- Docstrings estilo Google
- Comentarios en español
- Escritura atómica: `tmp_path → os.replace() → chmod(0o600)`
- Tests: Arrange-Act-Assert, sin PII, datos sintéticos

## Patterns to avoid

- ❌ `print()` en lugar de `structlog`
- ❌ `UPDATE` o `DELETE` sobre `smartBudgetSuggestionLog`
- ❌ Hardcodear `N` (ventana de meses) — leer de configuración por CU
- ❌ Copy prescriptiva: "deberías", "tienes que", "gastas más que el promedio"
- ❌ Mezclar `Pending` con `Posted` en el agregado
- ❌ Sugerencias negativas (clampear a 0)
- ❌ `round()` con método no documentado — usar siempre `round(x, 2)`

## Where to find context

- Project overview → `CLAUDE.md`
- Per-module context → `<module>/CLAUDE.md`
- Architecture deep-dive → `docs/codemap/00-overview/Architecture.md`
- Data pipeline detail → `docs/codemap/00-overview/Data-Pipeline.md`
- "¿Cómo corro X?" → `docs/guides/`
