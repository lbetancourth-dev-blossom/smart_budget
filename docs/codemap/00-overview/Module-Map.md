---
title: Module Map
aliases: [Module Directory, Directorios]
tags: [overview, module-map]
type: overview
last_mapped_at: 2026-05-19T23:57:00Z
last_commit: 9c0a1dc
---

# Module Map

Mapeo completo de directorios a módulos documentados.

| Módulo | Path | Páginas del codemap |
|---|---|---|
| [[01-core-model/README\|Core Model]] | `src/smart_budget/` | README, Public-API, Filters, Aggregator, Model |
| [[02-scripts/README\|Scripts ETL & CLI]] | `scripts/` | README, Public-API |
| [[03-tests/README\|Tests]] | `tests/` | README |
| [[04-api/README\|API FastAPI]] | `src/api/` | README, Public-API |
| [[05-sagemaker/README\|SageMaker Inference]] | `src/sagemaker/` | README, Public-API |

## Directorios no documentados (no son módulos)

| Directorio | Razón |
|---|---|
| `data/` | Gitignored. Datos locales descargados de S3. No forman parte del código. |
| `changes/` | Artefactos SDD del ciclo de desarrollo (ver [[SDD-Workflow]]). No es código del producto. |
| `docs/` | Documentación (este codemap y guías). |
| `.worktrees/` | Git worktrees temporales de tickets activos. |

## Archivos raíz

| Archivo | Propósito |
|---|---|
| `README.md` | Onboarding al repo, estado del proyecto, catálogo de categorías |
| `requirements.txt` | Dependencias Python de producción |
| `.gitignore` | Excluye `data/`, `__pycache__/`, `.env`, etc. |
| `CLAUDE.md` | Contexto para agentes AI — generado por este codemap |
| `AGENTS.md` | Instrucciones breves para agentes AI — generado por este codemap |
| `src/api/CLAUDE.md` | Contexto para agentes AI trabajando en el endpoint FastAPI |
| `src/sagemaker/CLAUDE.md` | Contexto para agentes AI trabajando en el script SageMaker |

## Backlinks

- [[README]]

#module-map #directory
