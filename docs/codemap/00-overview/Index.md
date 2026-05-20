---
title: Codemap Index
aliases: [Catalog, Catálogo, Vault Index]
tags: [overview, index]
type: overview
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# Codemap Index

Catálogo completo de todas las páginas en `docs/codemap/`. Para el punto de entrada narrativo, ver [[README]].

## Páginas de overview

| Página | One-liner |
|---|---|
| [[Architecture]] | Capas de datos, flujo batch, restricciones legales |
| [[Data-Pipeline]] | Fases ETL completas: extracción S3 → fact_transactions → prep → sugerencias |
| [[Glossary]] | Todos los términos de dominio (bucket, gating, treatment, WMA, etc.) |
| [[Index]] | Esta página |
| [[Module-Map]] | Tabla directorio → módulo con archivos raíz |
| [[README]] | Punto de entrada del vault |
| [[Schema]] | Convenciones del codemap (frontmatter, wiki-links, edición manual) |
| [[SDD-Workflow]] | Ciclo SDD+TDD, branching, commits, tickets completados |
| [[Tech-Stack]] | Python 3.9+, pandas, statsmodels, pytest, structlog |

## Módulos

| Página | One-liner |
|---|---|
| [[01-core-model/README\|Core Model README]] | Módulo central: filtros, agregación y 4 métodos de sugerencia |
| [[01-core-model/Public-API\|Core Model · Public API]] | Funciones públicas exportadas por `src/smart_budget/` |
| [[01-core-model/Filters\|Core Model · Filters]] | `filter_transactions()` — 6 reglas de filtrado |
| [[01-core-model/Aggregator\|Core Model · Aggregator]] | `aggregate_monthly()`, `zero_fill()`, `apply_gating()` |
| [[01-core-model/Model\|Core Model · Model]] | `compute_budget_suggestions()` y 4 métodos (WMA, EWMA, Median, HW) |
| [[02-scripts/README\|Scripts README]] | ETL scripts + CLI runners + evaluación holdout |
| [[02-scripts/Public-API\|Scripts · Public API]] | CLI flags de cada script |
| [[03-tests/README\|Tests README]] | Suite pytest: 107+ tests, fixtures, cobertura ~93% |
| [[04-api/README\|API FastAPI README]] | Endpoint REST `GET /smart-budget/suggestion` |
| [[04-api/Public-API\|API · Public API]] | Schemas Pydantic, ejemplos de request/response |
| [[05-sagemaker/README\|SageMaker README]] | Script `SKLearnModel` para AWS SageMaker |
| [[05-sagemaker/Public-API\|SageMaker · Public API]] | Contrato de las 4 funciones handler |

## Guías (docs/guides/)

| Guía | Area |
|---|---|
| [[../guides/smart-budget/How-To-Run-Pipeline\|Cómo ejecutar el pipeline]] | Smart Budget |
| [[../guides/smart-budget/How-To-Add-New-Method\|Cómo agregar un nuevo método]] | Smart Budget |
| [[../guides/smart-budget/How-To-Generate-Synthetic-Data\|Cómo generar datos sintéticos]] | Smart Budget |
| [[../guides/smart-budget/How-To-Use-Endpoint\|Cómo usar el endpoint]] | Smart Budget |

## Backlinks

_None — esta página es el catálogo._

#index #catalog
