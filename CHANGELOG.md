# Changelog

## Fase 0 — El Reflejo (2025-12 → 2026-05)

Implementación MVP del módulo Smart Budget para el producto Dough de Blossom.
El modelo refleja el comportamiento pasado del usuario sin inventar ni recomendar.

---

### Pipeline de datos

- Extracción desde S3 (datalake alpha/dev, capas bronze/silver) para fuentes OLB y Dough
- Construcción de `fact_transactions` unificando OLBSubAccountTransaction, OLBLoanTransaction y externaltransaction
- Scripts de preparación: extracción por capa/fuente, build de la tabla central, prep para el modelo
- Corrección de convención de signo en transacciones OLB (amounts normalizados a positivos)
- Exclusión de transacciones LOAN del modelo presupuestal (obligaciones fijas, no gasto discrecional)

### Modelo de sugerencias

- 6 reglas de filtrado obligatorias (soft delete, solo gastos, categorías válidas, LOAN exclusion, status SUB, status EXT)
- Agregación mensual por `(member, category)` con zero-fill y clamp a cero
- 4 métodos de cálculo evaluados: WMA, EWMA, mediana, Holt-Winters
- Método seleccionado: **WMA tratamiento B, lookback 3 meses** (CRWS = 0.5372)
- Gating: mínimo 2 meses con data para emitir sugerencia
- Confidence levels: `high` (≥6 meses), `medium` (3–5), `low` (2)

### API y serving

- Endpoint FastAPI: `GET /smart-budget/suggestion` con parámetros enum (Swagger dropdowns)
- Respuesta con `suggested_amount`, `basis`, `confidence`, `display_label`, `amount_by_month`
- 3 reglas de validación: cuenta existente, período válido, categoría presente en datos
- `POST /smart-budget/decision` para captura del loop de retroalimentación
- Deploy en SageMaker (inference.py + notebook de deploy)

### Testing

- Suite pytest con cobertura ~93%
- Golden set de regresión (65 sugerencias sintéticas)
- Tests unitarios: filtros, agregador, edge cases, idempotencia, multi-tenancy
- Tests de contrato API (TC-T2.1–T2.9)
- Datasets de test separados por fuente (internal/external)

### Documentación

- Codemap completo (`docs/codemap/`) — arquitectura, módulos, glosario, pipeline de datos
- Guías paso a paso (`docs/guides/`) — extracción, build, API local, SageMaker, datos sintéticos
- Evaluation report con comparación de los 4 métodos y justificación de selección
- AGENTS.md y CLAUDE.md con contexto para agentes AI
