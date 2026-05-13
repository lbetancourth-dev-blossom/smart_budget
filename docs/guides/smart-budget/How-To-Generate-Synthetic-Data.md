---
title: How to Generate Synthetic Data
aliases: [Synthetic Data, Fake Data, Test Data, generate_synthetic_dataset]
tags: [guide, smart-budget, testing, synthetic-data]
type: guide
audience: ds-ml-engineer
last_mapped_at: 2026-05-13T10:20:00Z
---

# How to Generate Synthetic Data

## What this does

Genera un CSV de `fact_transactions` sintético con datos ficticios para desarrollo, testing y validación del pipeline. Sin PII real.

## Before you start

- Python env activo: `pip install -r requirements.txt`
- Nunca usar datos reales de miembros en fixtures de tests

## Steps

### Generación básica (default)

```bash
python scripts/generate_synthetic_dataset.py \
  --members 20 \
  --months 12 \
  --seed 42 \
  --output data/dough/smart_budget_synthetic.csv
```

Genera 20 miembros sintéticos con 12 meses de historial cada uno.

### Para testing de edge cases

```bash
# Dataset con pocos meses (probar gating)
python scripts/generate_synthetic_dataset.py \
  --members 10 \
  --months 3 \
  --seed 99 \
  --output data/dough/test/edge_few_months.csv

# Dataset con gaps (probar zero_fill)
python scripts/generate_synthetic_dataset.py \
  --members 10 \
  --months 12 \
  --gap-probability 0.3 \
  --seed 77 \
  --output data/dough/test/edge_with_gaps.csv
```

### Para comparación de métodos

```bash
python scripts/generate_synthetic_dataset.py \
  --members 50 \
  --months 12 \
  --seed 42 \
  --output data/dough/smart_budget_synthetic.csv
```

Luego correr el pipeline completo:

```bash
python scripts/run_smart_budget_prep.py \
  --input data/dough/smart_budget_synthetic.csv \
  --output data/dough/smart_budget_prep_synthetic.csv

python scripts/run_methods.py \
  --method wma --treatment B \
  --reference-date 2026-05 \
  --input data/dough/smart_budget_prep_synthetic.csv \
  --output data/dough/test/query/wma_synthetic.json
```

## Parámetros

| Flag | Descripción | Default |
|---|---|---|
| `--members` | Número de miembros sintéticos | `20` |
| `--months` | Meses de historial (desde hoy hacia atrás) | `12` |
| `--seed` | Semilla para reproducibilidad | `42` |
| `--gap-probability` | Probabilidad de omitir un mes (0.0–1.0) | `0.0` |
| `--output` | Ruta del CSV de salida | `data/dough/smart_budget_synthetic.csv` |

## Schema del CSV generado

Coincide con el schema de `fact_transactions`:

```
idtransaction, idclient, idcompany, idaccount, idcategory, defaultcategory,
date, amount, incomeexpenditure, status, deletedat
```

- `idtransaction`: prefijo `SUB`, `LOAN`, o `EXT` aleatorio
- `idclient/idcompany`: valores fijos `CLIENT001` / `COMPANY001` (single tenant para dev)
- `idaccount`: `MEMBER_001`, `MEMBER_002`, ...
- `amount`: float positivo (los gastos son positivos en el schema)
- `status`: `POSTED` o `CLEARED` (todos válidos para el pipeline)
- `deletedat`: siempre `None` (todos activos)

## What you'll see when it works

```bash
ls -la data/dough/smart_budget_synthetic.csv
# -rw------- 1 ... 245K ... smart_budget_synthetic.csv

head -2 data/dough/smart_budget_synthetic.csv
# idtransaction,idclient,idcompany,...
# SUB00001,CLIENT001,COMPANY001,...
```

## Common problems

| Problem | Fix |
|---|---|
| `FileNotFoundError: data/dough/test/` | `mkdir -p data/dough/test/query/` |
| Todas las sugerencias null con `--months 3` | Normal — muy pocos meses. Bajar `--min-months 2` en `run_smart_budget_prep.py` |

## Related guides

- [[How-To-Run-Pipeline]]
- [[How-To-Extract-From-S3]]
