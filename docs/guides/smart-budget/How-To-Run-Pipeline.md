---
title: How to Run the Pipeline
aliases: [Run Smart Budget, Execute Pipeline, run_methods, run_smart_budget_prep]
tags: [guide, pipeline, smart-budget]
type: guide
audience: ds-ml-engineer
last_mapped_at: 2026-05-13T10:20:00Z
---

# How to Run the Smart Budget Pipeline

> ⚠️ **LEGACY / Batch pipeline:** Este pipeline opera sobre CSVs locales extraídos de S3/PostgreSQL.
> Post-DATA-1275, la fuente de datos del endpoint es Athena directamente — no requiere CSVs ni este pipeline.
> Ver [[How-To-Query-Athena]] para el flujo recomendado.

## What this does

Ejecuta el pipeline batch de Smart Budget Fase 0: desde el CSV de `fact_transactions` (legacy) hasta el JSON de sugerencias de presupuesto por categoría. Útil para experimentos offline y validación de métodos.

## Before you start

- AWS SSO activo: `aws sso login --profile blossom-dev`
- CSV de `fact_transactions` disponible en `data/dough/fact_transactions.csv` (o correr el paso de extracción primero — ver [[How-To-Extract-Data]])
- Python env activo con dependencias instaladas: `pip install -r requirements.txt`

## Steps

### 1. Preparar el dataset

```bash
python scripts/run_smart_budget_prep.py \
  --input data/dough/fact_transactions.csv \
  --output data/dough/smart_budget_prep.csv \
  --min-months 3
```

Aplica `filter_transactions` + `prepare_smart_budget_data`. El CSV resultante tiene una fila por `(idaccount, idcategory, period_yyyymm)` con `monthly_total` ya agregado y bucket con gating aplicado.

### 2. Calcular sugerencias

```bash
python scripts/run_methods.py \
  --method wma \
  --treatment B \
  --reference-date 2026-05 \
  --lookback-months 6 \
  --input data/dough/smart_budget_prep.csv \
  --output data/dough/test/query/results.json
```

### 3. Ver el resultado

```bash
# Sugerencias producidas
python -c "
import json
with open('data/dough/test/query/results.json') as f:
    data = json.load(f)
    print(f'Total sugerencias: {len(data)}')
    non_null = [d for d in data if d['suggested_amount'] is not None]
    print(f'Con sugerencia: {len(non_null)}')
    print(f'Null (sin historial): {len(data) - len(non_null)}')
"

# Ver primeras 5
python -c "
import json
with open('data/dough/test/query/results.json') as f:
    data = json.load(f)[:5]
    print(json.dumps(data, indent=2, default=str))
"
```

## What you'll see when it works

El JSON de salida tiene una entrada por `(idaccount, idcategory)`. Campos clave:
- `suggested_amount`: monto sugerido en USD, 2 decimales (ej. `437.82`)
- `confidence`: `high | medium | low`
- `display_label`: texto neutral para UI (ej. `"Basado en tus últimos 5 meses con gastos"`)

## Common problems

| Problem | Fix |
|---|---|
| `No module named 'smart_budget'` | `pip install -e .` o `export PYTHONPATH=src` |
| `File not found: fact_transactions.csv` | Correr primero el paso de extracción (ver [[How-To-Extract-From-S3]]) |
| `ValueError: idaccount maps to multiple companies` | Hay un problema de multi-tenancy en el input — revisar el script de build |
| `statsmodels not found` (Holt-Winters) | `pip install statsmodels` |
| Todas las sugerencias son `null` | El `--lookback-months` es muy pequeño o `--min-months` es muy alto — bajar `--min-months 2` |

## FAQ

**¿Con qué método empezar?** WMA + Treatment B + lookback=6 es la combinación más balanceada (ver `docs/method_comparison.md`).

**¿Cuándo usar Median?** Para categorías estacionales (Travel, Gifts) con 12 meses de historial.

**¿Qué significa `confidence: low`?** El bucket tiene solo 2 meses con gasto positivo dentro de la ventana. La sugerencia es válida pero menos confiable.

## Related guides

- [[How-To-Extract-From-S3]]
- [[How-To-Build-Fact-Transactions]]
- [[How-To-Add-New-Method]]
