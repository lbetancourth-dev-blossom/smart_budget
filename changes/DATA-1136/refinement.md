# Refinement — DATA-1136

**Date:** 2026-05-11 15:19  
**Mode:** feature  
**Risk:** medium  
**Published:** yes

## Applied simplifications
- Cap P90 sobre totales mensuales (no transacciones individuales)

## Created subtasks
_None_

## AC edits applied
_None (recomendaciones incluidas en el comentario de Jira)_

## Full comment

### Análisis previo — Blossom Refinement · DATA-1136

**Resumen del ticket**
Como DS engineer, preparar y validar los datos transaccionales para Smart Budget, de modo que los inputs del modelo estén limpios, correctamente agregados y listos para estimación.

**Riesgo:** Medio  
**Tamaño estimado:** M (9–12h) · 4 SP es consistente con la estimación del equipo (12h en phase0_remaining_tasks.md)

---

#### ⚠️ Preguntas abiertas (responder antes de implementar)

1. **"bucket" no está definido** — el ticket usa el término 8 veces sin definirlo. ¿Es `defaultcategory`? ¿Un Dough category ID? ¿Categoría custom?

2. **Conflicto zero-fill vs excluir** — el ticket dice "meses sin transacciones → 0" pero las instrucciones del proyecto dicen "mes sin cuenta activa → excluir (ausencia, no cero)". ¿Cuál aplica?

3. **Método P90 sub-especificado** — ¿P90 global o por usuario×categoría? ¿Cap o exclusión? (Simplificación aplicada: cap sobre totales mensuales, P90 global.)

4. **deletedat ausente en ACs** — el 26% de fact_transactions tiene soft delete. Los ACs no lo mencionan. La implementación filtrará `deletedat IS NULL`.

5. **Gating en data prep vs modelo** — ¿es intencional mover el gating (< 3 meses) a esta capa?

6. **Clave de usuario** — "user × bucket × month" usa `idmember` o `(idClient, idCompany, idMember)`?

---

#### Simplificación aplicada
- **P90 cap sobre totales mensuales** (no sobre transacciones individuales) — más simple, testeable, equivalente para el MVP.

---

#### Escenarios de test prioritarios
- Usuario con 2 meses en un bucket → excluido del output
- Mes con total negativo (REF > gastos) → clampear a 0
- P90 cap: mes extremo → capado al percentil global
- deletedat IS NOT NULL → excluido antes de agregar
- UNCATEGORIZED y income → excluidos del agregado
- SUM correcto con múltiples accounts por usuario×categoría×mes

---

#### Notas técnicas
- Tabla fuente: `fact_transactions` (1,413,948 rows · 32 cols · schema en docs/fact_transactions_README.md)
- Filtros obligatorios: `deletedat IS NULL`, `incomeexpenditure = 'expenditure'`, `defaultcategory != 'UNCATEGORIZED'`, `status IS NULL OR status != 'PENDING'`
- Output esperado: `data/dough/smart_budget_prep.csv` con columnas `(idclient, idcompany, idmember, defaultcategory, period_yyyymm, monthly_total, capped)`
- Referencia: docs/plan/plan_phase_0.md · Step 4

_Generado por Blossom Refinement · 2026-05-11_

## Raw analysis (JSON)
```json
{
  "status": "completed",
  "ticket": "DATA-1136",
  "mode": "feature",
  "risk": "medium",
  "estimation": {
    "bottom_up_hours": 9.5,
    "bucket": "M",
    "team_historical_hours": 12,
    "delta_x": 1.3,
    "confidence": "medium"
  },
  "simplifications": [
    {
      "applied": true,
      "description": "Cap P90 sobre totales mensuales (no transacciones individuales)",
      "hours_saved": 0.5
    },
    {
      "applied": false,
      "description": "P90 global (no por usuario)"
    },
    {
      "applied": false,
      "description": "Omitir zero-fill por ahora"
    }
  ],
  "proposed_subtasks": [],
  "proposed_ac_edits": [
    "Agregar: 'Rows with deletedat IS NOT NULL are excluded before aggregation'",
    "Clarificar: bucket = defaultcategory (o confirmar con DE)",
    "Clarificar: P90 computed globally over monthly totals; months exceeding P90 capped at P90"
  ],
  "open_questions": [
    "bucket definition",
    "zero-fill vs exclude for months without active account",
    "P90 scope (global vs per-user)",
    "deletedat filter in ACs",
    "gating placement (data prep vs model layer)",
    "user key: idmember or full multi-tenancy tuple"
  ]
}
```
