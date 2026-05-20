---
title: Scripts — Public API (CLI)
aliases: [CLI flags, Script arguments, run_methods, extract_datalake, build_fact_transactions]
tags: [module, scripts, cli, api]
type: api
last_mapped_at: 2026-05-13T10:20:00Z
last_commit: fc0547f
---

# Scripts — Public API

## `extract_datalake_to_csv.py`

Descarga tablas Parquet desde S3 (DOUGH, OLB, SAFE…) y las guarda como CSV local.

```bash
python scripts/extract_datalake_to_csv.py \
  --layer silver \
  --source DOUGH \
  --profile blossom-dev \
  --output-dir data/dough/silver/
```

| Flag | Descripción | Default |
|---|---|---|
| `--layer` | `bronze`, `silver`, `gold` | — |
| `--source` | `DOUGH`, `OLB`, `SAFE`, etc. | — |
| `--profile` | AWS SSO profile | `blossom-dev` |
| `--output-dir` | Directorio destino | `data/` |
| `--tables` | Tablas específicas (comma-separated) | todas |

---

## `build_fact_transactions.py`

Construye `fact_transactions` uniendo tablas OLB + DOUGH (equivalente a `ref_fact_transactions_olb.py` en PySpark, pero en pandas).

```bash
python scripts/build_fact_transactions.py \
  --dough-dir data/dough/silver/ \
  --olb-dir data/olb/silver/ \
  --output data/dough/fact_transactions.csv
```

| Flag | Descripción | Default |
|---|---|---|
| `--dough-dir` | Directorio con CSVs de DOUGH silver | `data/dough/silver/` |
| `--olb-dir` | Directorio con CSVs de OLB silver | `data/olb/silver/` |
| `--output` | Ruta del CSV de salida | `data/dough/fact_transactions.csv` |

---

## `run_smart_budget_prep.py`

Aplica `filter_transactions` → `prepare_smart_budget_data` y guarda el resultado. Output listo para `run_methods.py`.

```bash
python scripts/run_smart_budget_prep.py \
  --input data/dough/fact_transactions.csv \
  --output data/dough/smart_budget_prep.csv \
  --min-months 3
```

| Flag | Descripción | Default |
|---|---|---|
| `--input` | CSV de fact_transactions | — |
| `--output` | CSV de salida | `data/dough/smart_budget_prep.csv` |
| `--min-months` | Mínimo de meses positivos para gating | `3` |

---

## `run_methods.py`

CLI para calcular sugerencias de presupuesto usando distintos métodos. Acepta el CSV de `run_smart_budget_prep.py`.

```bash
# Sugerencias de mayo 2026 con WMA-B, 6 meses lookback
python scripts/run_methods.py \
  --method wma \
  --treatment B \
  --reference-date 2026-05 \
  --lookback-months 6 \
  --input data/dough/smart_budget_prep.csv \
  --output data/dough/test/query/results.json
```

| Flag | Descripción | Opciones | Default |
|---|---|---|---|
| `--method` | Método de estimación | `wma`, `ewma`, `median`, `holt_winters` | `wma` |
| `--treatment` | Tratamiento de ceros | `A`, `B`, `C` | `B` |
| `--reference-date` | Mes de sugerencia | `YYYY-MM` | mes actual |
| `--lookback-months` | Ventana histórica | int ≥ 1 | `6` |
| `--min-months` | Mínimo meses positivos | int ≥ 1 | `3` |
| `--input` | CSV de entrada | path | `data/dough/smart_budget_prep.csv` |
| `--output` | JSON de salida | path | `data/dough/test/query/results.json` |

**Output JSON:**

```json
[
  {
    "category_id": "GROCERIES",
    "suggested_amount": 437.82,
    "basis": {
      "months_analyzed": 6,
      "months_with_positive_spend": 5,
      "method": "wma",
      "treatment": "B",
      "data_points": [320.0, 480.0, 510.0, 390.0, 0.0, 450.0],
      "period_range": "2025-12 ~ 2026-05"
    },
    "confidence": "medium",
    "display_label": "Basado en tus últimos 5 meses con gastos",
    "explanation": "En 5 de tus últimos 6 meses tuviste gastos en esta categoría.",
    "model_version": "fase0-v1"
  }
]
```

---

## `generate_synthetic_dataset.py`

Genera un CSV sintético con datos ficticios de `fact_transactions` para desarrollo y testing. Sin PII real.

```bash
python scripts/generate_synthetic_dataset.py \
  --members 20 \
  --months 12 \
  --seed 42 \
  --output data/dough/smart_budget_synthetic.csv
```

| Flag | Descripción | Default |
|---|---|---|
| `--members` | Número de miembros sintéticos | `20` |
| `--months` | Meses de historial generados | `12` |
| `--seed` | Semilla para reproducibilidad | `42` |
| `--output` | CSV de salida | `data/dough/smart_budget_synthetic.csv` |

## Backlinks

- [[02-scripts/README]]

#scripts #cli #api #run-methods
