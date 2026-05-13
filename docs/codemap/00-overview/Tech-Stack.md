---
title: Tech Stack
aliases: [Dependencias, Dependencies, Stack]
tags: [overview, tech-stack]
type: overview
last_mapped_at: 2026-05-13T10:20:00Z
last_commit: fc0547f
---

# Tech Stack

## Runtime

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.9+ (recomendado 3.11+) |
| Data processing | `pandas >= 1.5.0` |
| Time-series forecasting | `statsmodels` (ExponentialSmoothing para Holt-Winters) |
| AWS / S3 | `boto3`, `pyarrow` (lectura de Parquet en el datalake) |
| Logging | `structlog >= 21.0.0` (logs estructurados, nunca `print`) |

## Testing

| Herramienta | Versión mínima | Uso |
|---|---|---|
| `pytest` | 7.0.0 | Test runner principal |
| `pytest-cov` | — | Cobertura de código (mínimo 80% en `filters.py` y `aggregator.py`) |

## Dev / CI

| Herramienta | Uso |
|---|---|
| `black` (línea 100) | Formateo de código |
| `ruff` | Linting |
| `git` | Control de versiones |
| `gh` CLI | PRs, issues, GitHub Actions |
| AWS SSO profile `blossom-dev` | Acceso a S3 dev/alpha |

## Infraestructura (Fase 0 → Fase 1+)

| Capa | Tecnología |
|---|---|
| Warehouse fuente | AWS Redshift / S3 Parquet |
| Pipeline ETL | Python scripts (Fase 0) → dbt + Airflow (Fase 1+) |
| Serving | BlossomAPI (REST) |
| Output DB | PostgreSQL (`blossom-dough-consolidated-dev`) |
| Frontend | Dough UI (repo separado) |

## requirements.txt

```
pandas>=1.5.0
pytest>=7.0.0
structlog>=21.0.0
```

> Nota: `statsmodels`, `boto3`, `pyarrow`, `numpy` se instalan localmente pero no están en `requirements.txt` de producción aún. Se agregarán en Fase 1 cuando el pipeline sea el source-of-truth.

## Convenciones de código

- Type hints obligatorios en funciones públicas
- Docstrings estilo Google
- Comentarios en español
- `snake_case` para variables y funciones
- `UPPER_SNAKE_CASE` para constantes
- `black` + `ruff` antes de cada PR

## Backlinks

- [[README]]
- [[Architecture]]

#tech-stack #python #pandas
