---
title: Tech Stack
aliases: [Dependencias, Dependencies, Stack]
tags: [overview, tech-stack]
type: overview
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# Tech Stack

## Runtime

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.9+ (recomendado 3.11+) |
| Data processing | `pandas >= 1.5.0` |
| Time-series forecasting | `statsmodels` (ExponentialSmoothing para Holt-Winters) |
| REST API | `fastapi`, `uvicorn`, `pydantic` |
| AWS / S3 | `boto3`, `pyarrow` (lectura de Parquet en el datalake) |
| AWS SageMaker | `sagemaker` SDK, imagen `sklearn:1.2-1` (Python 3.9, numpy 1.23.5, pandas 1.5.3) |
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
| Serving Fase 0 | FastAPI (`src/api/`) + SageMaker `SKLearnModel` (`src/sagemaker/`) |
| Serving Fase 1+ | BlossomAPI (REST) leyendo tabla pre-calculada |
| Output DB | PostgreSQL (`blossom-dough-consolidated-dev`) |
| Frontend | Dough UI (repo separado) |
| S3 modelo | `s3://blossom-analytics-safe-dev-nv/smart_budget/endpoint/v1/model.tar.gz` |

## requirements.txt

```
pandas>=1.5.0
fastapi
uvicorn
pydantic
pytest>=7.0.0
structlog>=21.0.0
```

### SageMaker container pins (`src/sagemaker/requirements.txt`)

```
numpy==1.23.5
pandas==1.5.3
structlog>=21.0.0
```

> **Nota**: `statsmodels` NO se instala en el contenedor SageMaker (ABI conflict). Import lazy en `model.py` dentro de `compute_holt_winters()`. `boto3`, `pyarrow` para extracción local, no en producción.

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
