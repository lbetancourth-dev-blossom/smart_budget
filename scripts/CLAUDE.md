# Scripts ETL & CLI

> Per-module AI agent context. Companion to `docs/codemap/02-scripts/README.md`.

## Purpose

Scripts de extracción de datos del datalake S3, construcción de `fact_transactions`, preparación del dataset y CLI de métodos de sugerencia.

## Where things live

```
scripts/
├── extract_datalake_to_csv.py      → S3 Parquet → CSV local
├── build_fact_transactions.py      → OLB + DOUGH silver → fact_transactions.csv  [LEGACY — ver nota]
├── run_smart_budget_prep.py        → filter + aggregate + gating → smart_budget_prep.csv
├── run_methods.py                  → CLI: calcula sugerencias por método → results.json
└── generate_synthetic_dataset.py   → genera datos sintéticos para dev/testing
```

> **LEGACY (post-DATA-1275):** `extract_smart_budget_monthly.py` y `build_fact_transactions.py --source db`
> están deprecados tras la migración a Athena/Glue. El endpoint ahora consulta
> `dlh_gold_dough_dev.smart_budget_transactions` directamente via `src/smart_budget/athena_loader.py`.
> Estos scripts se mantienen solo para referencia y pipelines locales de desarrollo.

## Key files

- `run_methods.py` — CLI principal del modelo; acepta `--method wma|ewma|median|holt_winters`
- `build_fact_transactions.py` — une OLB (SUB/LOAN) + DOUGH (EXT) con categorías **(LEGACY post-DATA-1275)**
- `extract_datalake_to_csv.py` — autenticación SSO, descarga Parquet, escribe CSV con `chmod 600`
- `src/smart_budget/athena_loader.py` — **nuevo (DATA-1275)**: carga datos live desde Athena/Glue via pyathena

## Conventions

- Escritura atómica: `tmp_path` → `os.replace()` → `chmod(0o600)`
- Logs con `structlog` — nunca `print`
- Nunca loguear montos individuales ni member IDs sin hashear
- El logger de error nunca incluye contenido de filas del DataFrame

## Dependencies

- Imports from: `smart_budget.filters`, `smart_budget.aggregator`, `smart_budget.model`
- Imported by: ninguno (puntos de entrada del pipeline)
- External: `pandas`, `boto3`, `pyarrow`, `structlog`, `statsmodels`

## Tests

- Run: `pytest tests/unit/ -v` (los scripts son cubiertos indirectamente via integración)
- Integration: `pytest tests/integration/ -v` (requiere staging)

## Gotchas

- `run_methods.py --reference-date` acepta tanto `YYYY-MM` como `YYYY-MM-DD` — normaliza internamente
- AWS SSO debe estar activo antes de `extract_datalake_to_csv.py`: `aws sso login --profile blossom-dev`
- Algunas tablas DOUGH silver están pendientes de replicación (ver `docs/data_review.md §4`) — el script maneja `FileNotFoundError` con warning, no crash

## See also

- [Module overview](../docs/codemap/02-scripts/README.md)
- [Root project context](../CLAUDE.md)
