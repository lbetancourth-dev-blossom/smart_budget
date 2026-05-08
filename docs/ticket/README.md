# Tickets — Smart Budget Fase 0

Esta carpeta consolida los tickets de Jira relacionados con la Fase 0 de Smart Budget para que el contexto esté disponible offline en el repo.

## Tickets en esta carpeta

| Ticket | Estado | Tipo | Asignado | Resumen |
|---|---|---|---|---|
| [`DATA-1041.md`](DATA-1041.md) | IN PROGRESS | User Story | Landneyker Betancourth | DS - Smart Budget — Fase 0: modelo de sugerencia de presupuesto por subcategoría |
| [`DATA-1066.md`](DATA-1066.md) | TO DO | User Story | (sin asignar) | DS - Define Smart Budget baseline and data structure (prerequisito de DATA-1041) |

## Relación entre tickets

```
DATA-1066 (TO DO)        DATA-1041 (IN PROGRESS)
    │                            │
    │  prerequisito              │
    └────────────────────────────┘
        define la lógica         implementa el modelo
        baseline + dataset       sobre la base definida
```

## Hallazgo importante

El ticket prerequisito **DATA-1066 está en TO DO**, pero buena parte de sus Acceptance Criteria ya están cubiertos por los entregables del repo:

| Criterio DATA-1066 | Cobertura actual |
|---|---|
| Business objective documentado | `README.md` + `docs/plan_phase_0.md` |
| Baseline model logic definida (median-based) | `src/smart_budget/aggregator.py` |
| Dataset user/category/month preparado | `src/smart_budget/queries/monthly_spend.sql` |
| Output structure definida | `build_budget_rows` + `build_budgetcategory_rows` |

> **Recomendación:** cerrar DATA-1066 referenciando estos entregables, o moverlo a "Ready for review".

## Discrepancias entre el ticket DATA-1041 y la implementación actual

| Aspecto | Implementado | Ticket DATA-1041 | Acción |
|---|---|---|---|
| Ventana N default | 6 meses | **3 meses** | Cambiar default |
| Gating mínimo | < 2 meses | **< 3 meses** | Subir umbral |
| Outliers | Sin tratamiento | **Suavizar (smoothing)** | Implementar (winsorización u otro) |
| Granularidad | `category_id` | `category_id` + **`subcategory_id`** | Confirmar con Producto |
| Output JSON | Incluye `confidence` | NO menciona confidence | Decidir si mantener como nice-to-have |
| Persistencia | `budget` + `budgetcategory` | "API o query directa al warehouse" | El ticket no obliga escribir a budget |

Detalles del análisis: ver `docs/phase0_remaining_tasks.md` y la conversación de discovery del proyecto.

## Cómo refrescar el contenido de los tickets

Los archivos en esta carpeta son snapshots del estado de los tickets en la fecha indicada en cada uno. Para volverlos a sincronizar con Jira (cuando haya cambios), pedir a Claude:

> *"Refresca el contenido de los tickets DATA-1041 y DATA-1066 desde Jira."*

Esto requiere que el conector **Atlassian Rovo** esté conectado en la sesión.
