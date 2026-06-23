# Refinement — DATA-1275

**Date:** 2026-06-22 09:43
**Mode:** feature
**Risk:** medium
**Published:** yes · https://blossomtechnology.atlassian.net/browse/DATA-1275?focusedCommentId=296718

## Applied simplifications
- (ninguna)

## Created subtasks
- (ninguno)

## AC edits applied
- (no aplicados — quedaron como recomendación)

### AC edit sugerido (no aplicado)
- AC 2: agregar "Los resultados se validan contra una muestra conocida de al menos 1 miembro con historial en la tabla Glue."

## Full comment

**Análisis previo — Blossom Refinement**

**Riesgo: medio.** El cambio está bien acotado, pero hay ambigüedades técnicas importantes sobre el schema de la nueva fuente y el comentario en el ticket agrega alcance no reflejado en los ACs.

**Advertencias**
• El comentario de Landneyker dice "Add category id + name to output" y "sesión pendiente con DE/Dough sobre categorías". Ninguno de estos puntos está en los ACs. Aclarar con Product si forman parte de este ticket antes de iniciar.
• Schema de `dlh_gold_dough_dev.smart_budget_transactions` no documentado. Confirmar columnas antes de escribir código.
• La query actual usa sintaxis PostgreSQL. Migración a Athena requiere adaptar al dialecto Presto y cambiar el cliente de conexión.
• `awswrangler` o `pyathena` no están en `requirements.txt` — nueva dependencia necesaria.

**Estimación**
• Tamaño realista: S (3-4h) — asume schema Glue compatible con output actual.
• Si hay que adaptar columnas o agregar category_id+name: sube a M (6-8h).
• Histórico del equipo: mediana 4pts, rango P25-P75 3-8h, n=20 similares, confianza media.
• Diferencia ~1x — alineado.

**Escenarios de prueba sugeridos**
• PR #10: verificar que la tabla Glue aplique reglas de signos OLB + exclusión LOAN o que el pipeline no las duplique.
• PR #18 (DATA-1179): confirmar que `load_history_by_member()` sigue funcionando con la nueva fuente.
• Miembro sin transacciones en Glue: endpoint debe retornar 200 con sugerencia nula, no 500.
• Athena timeout: el error debe propagarse claramente, sin retornar data stale del CSV anterior.
• Columna de categoría con nombre diferente en Glue vs schema actual: el pipeline no debe silenciar la discrepancia.

**Dependencias detectadas**
• Schema de `dlh_gold_dough_dev.smart_budget_transactions`: no documentado. Confirmar antes de implementar.
• Sesión de alineación con DE/Dough sobre categorías: si es prerequisito, mapear como bloqueador en Jira.

## Raw analysis (JSON)

```json
{
  "status": "completed",
  "risk": "medium",
  "estimation": {
    "bottom_up_hours": 4,
    "bottom_up_bucket": "S",
    "historical_median_hours": 4,
    "historical_p25": 3,
    "historical_p75": 8,
    "historical_sample_size": 20,
    "historical_confidence": "medium",
    "delta_multiplier": 1.0,
    "notes": "Bottom-up asume schema Glue compatible con output actual. Si hay que adaptar columnas o agregar category_id+name, sube a M (6-8h)."
  },
  "simplifications": [],
  "proposed_subtasks": [],
  "proposed_ac_edits": [
    {
      "target": "ac_2",
      "from": "El endpoint retorna resultados correctos tras el cambio de conexión.",
      "to": "El endpoint retorna resultados correctos tras el cambio de conexión. Los resultados se validan contra una muestra conocida de al menos 1 miembro con historial en la tabla Glue."
    }
  ],
  "published_comment_id": "296718"
}
```
