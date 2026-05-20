---
title: Glossary
aliases: [Glosario, Términos, Terms]
tags: [overview, glossary, domain]
type: overview
last_mapped_at: 2026-05-13T10:20:00Z
last_commit: fc0547f
---

# Glossary — Smart Budget

Definiciones de todos los términos de dominio usados en el código y la documentación.

## Términos del modelo

| Término | Definición |
|---|---|
| **fact_transactions** | Tabla central de transacciones. Unifica `OLBSubAccountTransaction` + `OLBLoanTransaction` + `externaltransaction` en un esquema canónico de 32 columnas. |
| **smart_budget_prep** | Output del pipeline de preparación: datos filtrados, agregados mensualmente y con gating aplicado. Input del modelo de sugerencias. |
| **bucket** | Una combinación única `(idaccount × idcategory × defaultcategory)`. La unidad de cálculo del modelo. |
| **gating** | Regla que descarta buckets con menos de N meses de datos positivos (default: 3). Un bucket sin suficiente historial no recibe sugerencia. |
| **treatment** | Estrategia para manejar meses con gasto cero: A (incluir ceros), B (excluir ceros), C (reemplazar ceros por epsilon=0.01). |
| **lookback_months** | Ventana de meses hacia atrás desde `reference_date` usada para calcular la sugerencia. Configurable por CU (default: 6, rango: 3–24). |
| **reference_date** | Mes para el cual se calcula la sugerencia (formato YYYY-MM). El mes en curso se excluye del cálculo. |
| **suggested_amount** | Monto sugerido por el modelo para un bucket en un período. Redondeado a 2 decimales. Null si no hay suficiente historial. |
| **confidence** | Nivel de confianza de la sugerencia: `high` (≥6 meses), `medium` (3–5), `low` (2). |
| **model_version** | Identificador de la versión del modelo. Actualmente `"fase0-v1"`. Parte de la clave única en `smartBudgetSuggestion`. |
| **snapshot freeze** | Una sugerencia emitida nunca se modifica. Si el modelo recalcula, inserta fila nueva con timestamp distinto. |
| **period_yyyymm** | Período mensual en formato `"YYYY-MM"` (ej: `"2026-05"`). Clave de agrupación temporal. |
| **monthly_total** | Suma mensual de montos de transacciones para un bucket, clampeada a 0 (nunca negativa). |
| **zero_fill** | Proceso de completar el grid (member × category × all_months) con ceros para meses sin actividad. Distingue ausencia de cuenta (excluir) de gasto cero (incluir). |
| **REF** | Reembolso. Transacción de crédito que reduce el gasto neto del mes. Si la suma neta es negativa, se clampea a 0. |

## Métodos de sugerencia

| Método | Abreviación | Descripción |
|---|---|---|
| Weighted Moving Average | WMA | Media ponderada con pesos lineales crecientes `[1, 2, ..., n]`. Meses recientes pesan más. |
| Exponentially Weighted Moving Average | EWMA | Media exponencialmente ponderada (`pandas.ewm(span=3)`). Decae exponencialmente hacia el pasado. |
| Mediana | Median | Mediana simple sobre la serie. Robusta a outliers y estacionalidad extrema. |
| Holt-Winters | HW | Suavizado exponencial con tendencia aditiva (`statsmodels.ExponentialSmoothing`). Requiere ≥3 observaciones. |

## Términos de datos / infraestructura

| Término | Definición |
|---|---|
| **silver** | Capa del datalake con datos limpios. Fuente de Smart Budget. |
| **bronze** | Capa raw CDC desde DMS. Nunca leer directamente. |
| **gold** | Capa de output DS-ML. Vacía en Fase 0 — destino de `smartBudgetSuggestion`. |
| **OLB** | Online Banking (sistema interno Blossom). Transacciones con prefijo `SUB`. Las transacciones `LOAN` se construyen en `fact_transactions` pero se excluyen del modelo presupuestal (Rule 4). |
| **EXT** | Transacciones externas via Plaid o Finicity (agregador Dough). Prefijo `EXT`. |
| **idtransaction** | ID único de transacción. Prefijo determina origen: `SUB` (OLB SubAccount, incluido en modelo), `LOAN` (OLB Loan, **excluido por Rule 4**), `EXT` (Dough externo). |
| **defaultcategory** | Categoría estándar de Blossom (string, ej: `"GROCERIES"`). Viene del catálogo `defaultcategory` o de Ntropy (RICH). |
| **RICH** | Enriquecimiento de Ntropy. Asigna `defaultcategory` a transacciones externas. No todas las CUs tienen RICH activo. |
| **MONEY_SENT** | Categoría legacy OLB equivalente a Internal Transfers. Excluida del modelo. |
| **incomeexpenditure** | Campo que indica si la transacción es `"expenditure"` (gasto) o `"income"` (ingreso). Smart Budget filtra solo `expenditure`. |
| **Posted** | Estado de transacción confirmada. Para EXT, solo `POSTED` se incluye. Para OLB, se excluyen `PENDING` y `HOLD`. |
| **CU** | Credit Union. Un `idcompany` en el sistema Blossom. |
| **idclient** | ID del cliente Blossom (siempre `1` en producción actual). |
| **idcompany** | ID de la Financial Institution (Credit Union). |
| **idmember** | ID del miembro de la Credit Union. En el modelo, equivale a `idaccount`. |

## Términos del ciclo de desarrollo

| Término | Definición |
|---|---|
| **SDD** | Solution-Driven Development. Ciclo plan → spec → execute → review → PR → done. Ver [[SDD-Workflow]]. |
| **TDD** | Test-Driven Development. Tests se escriben antes que el código de implementación. |
| **DCR** | Decision Closure Rule. Todas las decisiones de diseño deben cerrarse antes de ejecutar el spec. |
| **HLTC** | High-Level Test Contract. Describe qué probar, no cómo. Vive en `plan.md`. |

## Backlinks

- [[README]]
- [[Architecture]]
- [[01-core-model/README]]

#glossary #domain #terms
