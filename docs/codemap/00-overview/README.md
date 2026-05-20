---
title: Codemap Overview
aliases: [MOC, Map of Content, Index]
tags: [overview, moc]
type: overview
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# Smart Budget — Codemap

> Módulo de presupuesto inteligente del producto **Dough** (PFM de Blossom para Credit Unions americanas). Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual. Actualmente en **Fase 0 (El Reflejo)**: el modelo refleja comportamiento pasado mediante métodos estadísticos simples sin ML complejo.

## Módulos

| # | Módulo | Path | Propósito |
|---|---|---|---|
| 01 | [[01-core-model/README\|Core Model]] | `src/smart_budget/` | Filtros, agregación y métodos de sugerencia (WMA, EWMA, Median, Holt-Winters). **Método seleccionado Fase 0: Median-B lb=6** |
| 02 | [[02-scripts/README\|Scripts ETL & CLI]] | `scripts/` | Extracción S3, construcción de `fact_transactions`, pipeline preparación, CLI de métodos, evaluación |
| 03 | [[03-tests/README\|Tests]] | `tests/` | Suite pytest: 107+ tests cubriendo filtros, agregador, modelo, API, SageMaker, loader |
| 04 | [[04-api/README\|API FastAPI]] | `src/api/` | Endpoint REST `GET /smart-budget/suggestion` con validación Enum y pipeline orchestration |
| 05 | [[05-sagemaker/README\|SageMaker Inference]] | `src/sagemaker/` | Script `SKLearnModel` para AWS SageMaker (imagen `sklearn:1.2-1`) |

## Conceptos transversales

- [[Architecture]] — capas de datos, flujo batch + serving, contrato JSON de output
- [[Tech-Stack]] — dependencias y versiones (incluye FastAPI, SageMaker SDK)
- [[Module-Map]] — directorio a módulo mapping
- [[Glossary]] — términos de dominio (fact_transactions, gating, treatment, etc.)
- [[Data-Pipeline]] — flujo S3 → silver → preparación → sugerencia
- [[SDD-Workflow]] — ciclo SDD+TDD usado para desarrollar este repo

## Cómo usar este codemap

- **¿Buscás un módulo?** Empezá en la tabla de arriba.
- **¿Buscás un concepto de dominio?** Revisá la lista de conceptos transversales.
- **¿Cómo ejecuto el pipeline?** Mirá [`docs/guides/`](../guides/README.md) — guías paso a paso.
- **¿Agregando una nueva feature?** Leé [[SDD-Workflow]] y arrancá con `/blossom-workflow:feature <TICKET>`.
- **¿Actualizando el codemap?** Después de un refactor: `/blossom-codemap --update`.

## Estado del proyecto

| Fase | Estado | Rama principal |
|---|---|---|
| Fase 0 — El Reflejo (mediana / WMA / EWMA / HW) | ✅ Implementado | `development` |
| Fase 1 — Ajuste por intención | 🔄 Pendiente | — |
| Fase 2 — Estacionalidad y outliers | 🔄 Pendiente | — |

## Backlinks

_None yet — este es el punto de entrada del vault._

#overview #moc
