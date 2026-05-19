# DATA-1140 — Refinement Audit Trail
Generated: 2026-05-15 (Data Sprint 10.26)
Mode: FEATURE_MODE | Risk: HIGH | Status: completed

---

## Comment (published to Jira: ✅ comment ID 280266 · 2026-05-15)

**Análisis previo — Blossom Refinement**

**Riesgo: alto.** El ticket mezcla responsabilidades de dos repos distintos (smart_budget DS-ML y BlossomAPI/banca), hay tres desajustes entre el schema del ticket y el contrato DS-ML, y una dependencia bloqueante de infraestructura no resuelta.

**Advertencias**

• **[BLOQUEANTE] La tabla `smartBudgetSuggestion` no existe aún.** Architecture.md la marca explícitamente como "A crear en Fase 1". El endpoint no puede servir datos hasta que esta tabla esté creada y populada por el pipeline. Este trabajo no aparece en los ACs.

• **[SCHEMA] `subcategory_id` no existe en el modelo DS-ML.** El schema de output del ticket incluye `subcategory_id` pero `model.py`, la tabla `smartBudgetSuggestion` y todos los docs internos usan únicamente `category_id`. ¿Es un requisito nuevo o un error de copiado del PRD?

• **[SCHEMA] `confidence` está en el contrato DS-ML pero ausente del ticket.** El modelo siempre genera `confidence: high | medium | low`, la tabla tiene la columna, los docs la definen. El ticket no la incluye en el output schema. Si es omisión intencional, el equipo de BlossomAPI no la va a incluir y Dough pierde una señal clave de UX.

• **[SCHEMA] `basis.data_points` en el ticket ≠ `basis.months_with_positive_spend` en el modelo.** Los nombres de campo no coinciden — antes de implementar hay que definir cuál es el canónico.

• **[OWNERSHIP] Ambigüedad de ownership.** El ticket está asignado al sprint DATA/DS-ML, pero el deliverable (endpoint REST) vive en BlossomAPI (área banca). No queda claro qué produce DS-ML en este ticket: ¿solo la spec/contrato? ¿la migración de tabla? ¿coordinación con el equipo de BlossomAPI?

• **[AC] AC 1 y AC 5 se superponen.** AC 1 dice "documented" y AC 5 dice "documented for Dough team integration" — dos ACs pidiendo lo mismo sin distinguir formato ni destinatario.

• **[SEGURIDAD] Autenticación y multi-tenancy ausentes de los ACs.** La arquitectura requiere filtrar toda query por `idClient/idCompany/idMember`. No está especificado en los ACs — ¿es responsabilidad de BlossomAPI (lo más probable) o de DS-ML?

• **[UX] `display_label` en idioma incorrecto.** El ticket muestra el ejemplo en inglés ("Based on your last 3 months") pero el modelo genera texto en español ("Basado en tus últimos N meses"). Si la UI de Dough es en inglés, hay un gap de localización.

---

**Estimación**

• Tamaño realista (DS-ML scope): **S (~6h)** — data contract + spec para BlossomAPI + alineación de schema + documentación
• Tamaño si DS-ML también crea la tabla: **M (~10h)**
• Tamaño si DS-ML es responsable del endpoint completo: **M (~15h)** — este escenario requiere aclaración urgente antes de comenzar
• Histórico del equipo: sin muestras comparables vía JQL en este contexto (n=0)
• Story points actuales: 6 pts = 6h (escala 2025-10). Consistente con scope DS-ML-only. Inflado si la tabla no está creada.

---

**Subtasks sugeridos**

1. Alinear schema de output con Product/Dough: resolver `subcategory_id`, `confidence`, y `basis.data_points` antes de escribir una línea de código
2. Crear migración de tabla `smartBudgetSuggestion` (prerequisito bloqueante — puede ser ticket separado o subtask aquí)
3. Escribir data contract / spec para BlossomAPI (OpenAPI YAML o Confluence — confirmar formato con Dough)
4. Crear ticket o subtask en BlossomAPI para la implementación del endpoint (asignar al equipo de banca)

---

**Escenarios de prueba sugeridos**

• Miembro sin ningún bucket que califique gating → respuesta `[]` vacía (no null, no error 500)
• Miembro con buckets parciales → solo los calificados en la respuesta; los no calificados ausentes (verifica AC 3)
• Query cross-tenant: request para memberA no devuelve datos de memberB — aislamiento por `idClient/idCompany/idMember`
• Carrera entre upsert del batch nocturno y lectura del endpoint durante la ventana de escritura
• `calculated_at` stale (batch no corrió en N semanas) — ¿hay SLA de frescura de datos? No está en los ACs

---

**Dependencias detectadas**

• **DATA-1138** (selección de método WMA-B lb=3) — referenciado pero no linkeado como "depends on" en Jira
• **Tabla `smartBudgetSuggestion`** — no existe; queda por definir quién la crea y en qué ticket
• **Equipo BlossomAPI** — necesita un ticket propio para la implementación del endpoint; no hay evidencia de que ese ticket exista

---

**Recomendaciones**

1. **Resolver las ambigüedades de schema antes de implementar.** Los tres desajustes (`subcategory_id`, `confidence`, `basis.data_points`) deben aclararse con Product y Dough en refinement — una vez BlossomAPI implementa contra un schema incorrecto, el fix es costoso.
2. **Dividir el trabajo en dos tickets.** Ticket DS-ML: data contract + table migration. Ticket BlossomAPI (área banca): endpoint REST + authn + docs para Dough.
3. **Linkear DATA-1138 como bloqueante.** Si el método cambia post-evaluación, el schema de output puede cambiar.
4. **Confirmar ownership de la tabla.** Clarificar si la creación de `smartBudgetSuggestion` es responsabilidad de DS-ML (migration script) o del equipo de base de datos.

---

**Positivo**

• La descripción tiene contexto claro, un schema de output propuesto y referencias al PRD — poco usual y muy útil para el equipo de BlossomAPI.
• El pipeline DS-ML (filter → aggregate → gate → model) ya está implementado y testeado (PRs #3-#8). El trabajo DS-ML restante es principalmente coordinación y documentación.
• Los ACs 2, 3, y 4 son específicos y verificables.

_Notas técnicas: `model.py:compute_budget_suggestions()` produce `category_id`, `defaultcategory`, `idaccount`, `idclient`, `idcompany`, `suggested_amount`, `basis{months_analyzed, months_with_zero, months_with_positive_spend, period_range, method, treatment}`, `confidence`, `display_label`, `explanation`, `model_version`. La tabla `smartBudgetSuggestion` en `docs/codemap/00-overview/Data-Pipeline.md` tiene columnas: `id_client`, `id_company`, `id_member`, `category_id`, `period_id`, `suggested_amount`, `months_analyzed`, `data_points`, `period_range`, `confidence`, `display_label`, `model_version`. El método seleccionado es WMA + Treatment B + lookback=3 (DATA-1138, PR #7). BlossomAPI está en el área `banca` del jira-repo-map.yml (repo: `homecu/BlossomApi`). `smart_budget` no está registrado en jira-repo-map.yml bajo ningún área — considerar agregarlo bajo `data`._

---

## JSON Result

```jsonc
{
  "status": "completed",
  "risk": "high",
  "area": {
    "id": "data",
    "name": "Data & Analytics",
    "matched_on": "prefix",
    "hint": ""
  },
  "relevant_repos": {
    "candidates": [
      "blossom-datalake",
      "BlossomDataLakeInfra",
      "BlossomDataMigrationApi",
      "blossom-know-lakehouse",
      "blossom-data-queries-report",
      "blossom-ml",
      "blossom-core-ai",
      "BlossomApi"
    ],
    "current_repo": "smart_budget",
    "in_scope": false,
    "advice": "El repo actual (smart_budget) no está registrado en el área DATA de jira-repo-map.yml. El endpoint vive en BlossomApi (área banca). Para trabajo DS-ML (data contract, migración de tabla) este repo es correcto. Para la implementación del endpoint, clonar homecu/BlossomApi. Considerar agregar smart_budget al mapa bajo el área data."
  },
  "warnings": [
    "[BLOQUEANTE] La tabla smartBudgetSuggestion no existe (Architecture.md: 'A crear en Fase 1'). El endpoint no puede servir datos hasta que sea creada.",
    "[SCHEMA] subcategory_id aparece en el output schema del ticket pero no existe en model.py, la tabla smartBudgetSuggestion, ni en ningún doc interno.",
    "[SCHEMA] confidence está en el contrato DS-ML (model.py, Data-Pipeline.md) pero ausente del output schema del ticket.",
    "[SCHEMA] basis.data_points en el ticket ≠ basis.months_with_positive_spend en el modelo — nombres de campo no coinciden.",
    "[OWNERSHIP] Ambigüedad: ticket en sprint DATA pero deliverable (endpoint) vive en BlossomAPI (área banca). Deliverable DS-ML no está claro.",
    "[AC] AC 1 y AC 5 se superponen — ambos piden documentación sin distinguir formato ni destinatario.",
    "[SEGURIDAD] Autenticación y multi-tenancy (idClient/idCompany/idMember) ausentes de los ACs.",
    "[UX] display_label en el ticket muestra ejemplo en inglés pero el modelo genera texto en español."
  ],
  "edge_cases": [
    {
      "source": "generic",
      "reference": "",
      "text": "Miembro sin ningún bucket que califique gating → respuesta vacía [] (no null, no error 500)"
    },
    {
      "source": "generic",
      "reference": "",
      "text": "Miembro con buckets parciales → solo los calificados en la respuesta; los excluidos ausentes por completo (verifica AC 3)"
    },
    {
      "source": "generic",
      "reference": "",
      "text": "Query cross-tenant: request para memberA no devuelve datos de memberB — aislamiento por idClient/idCompany/idMember"
    },
    {
      "source": "generic",
      "reference": "",
      "text": "Carrera entre upsert del batch nocturno y lectura del endpoint durante la ventana de escritura"
    },
    {
      "source": "generic",
      "reference": "",
      "text": "Datos stale: batch no corrió en N semanas — ¿hay SLA de frescura? No figura en los ACs"
    }
  ],
  "estimation": {
    "bottom_up_hours": 6,
    "bottom_up_bucket": "S",
    "historical_median_hours": null,
    "historical_p25": null,
    "historical_p75": null,
    "historical_sample_size": 0,
    "historical_confidence": "low",
    "delta_multiplier": null,
    "notes": "Estimación basada en scope DS-ML-only (data contract + alineación schema + docs). Si DS-ML también crea la tabla: ~10h (M). Si DS-ML es responsable del endpoint completo: ~15h (M). Sin muestras históricas comparables vía JQL en este contexto (n=0). Story points actuales del ticket: 6 (= 6h en escala 2025-10)."
  },
  "simplifications": [
    {
      "kind": "scope_reduction",
      "text": "Separar el ticket en dos: (1) DS-ML: data contract + migración de tabla, (2) BlossomAPI: implementación del endpoint. Elimina ambigüedad de ownership y permite paralelizar.",
      "estimated_savings_hours": 3
    },
    {
      "kind": "reuse",
      "text": "El pipeline DS-ML ya genera el JSON de output completo (model.py:compute_budget_suggestions). El data contract para BlossomAPI puede derivarse directamente de docs/codemap/00-overview/Data-Pipeline.md sin escribirlo desde cero.",
      "estimated_savings_hours": 2
    }
  ],
  "proposed_subtasks": [
    {
      "title": "Alinear schema de output: resolver subcategory_id, confidence y basis field names con Product/Dough",
      "summary": "Prerequisito para todo lo demás. Confirmar si subcategory_id es requisito nuevo, si confidence va en la respuesta, y qué nombre usa basis.data_points."
    },
    {
      "title": "Crear migración de tabla smartBudgetSuggestion (prerequisito bloqueante)",
      "summary": "La tabla no existe aún (Architecture.md: Fase 1). Escribir y ejecutar la migration. Puede ser subtask aquí o ticket separado."
    },
    {
      "title": "Escribir data contract / spec para BlossomAPI",
      "summary": "OpenAPI YAML o página Confluence — confirmar formato preferido con Dough. Incluir schema de request (idMember), response, y authn requirements."
    },
    {
      "title": "Crear ticket en BlossomAPI para implementación del endpoint REST",
      "summary": "Asignar al equipo banca. Incluir el data contract como attachment. Este ticket DATA-1140 no puede cerrarse hasta que el endpoint de BlossomAPI esté deployado."
    }
  ],
  "proposed_ac_edits": [
    {
      "target": "ac_1",
      "from": "Endpoint available, documented, and accessible via BlossomAPI",
      "to": "Endpoint implementado y accesible en BlossomAPI (GET /smart-budget/suggestion), con autenticación y filtrado multi-tenant por idClient/idCompany/idMember"
    },
    {
      "target": "ac_4",
      "from": "Response matches the defined output schema",
      "to": "Response del endpoint coincide con el data contract acordado (schema alineado entre ticket, model.py y smartBudgetSuggestion) — incluyendo decisión explícita sobre subcategory_id y confidence"
    },
    {
      "target": "ac_5",
      "from": "Endpoint documented for Dough team integration",
      "to": "Data contract publicado en formato acordado (OpenAPI YAML o Confluence) y revisado por al menos un engineer de Dough antes del cierre del ticket"
    }
  ],
  "comment_language": "es",
  "comment_markdown": "**Análisis previo — Blossom Refinement**\n\n**Riesgo: alto.** El ticket mezcla responsabilidades de dos repos distintos (smart_budget DS-ML y BlossomAPI/banca), hay tres desajustes entre el schema del ticket y el contrato DS-ML, y una dependencia bloqueante de infraestructura no resuelta.\n\n**Advertencias**\n• [BLOQUEANTE] La tabla `smartBudgetSuggestion` no existe aún (Architecture.md: 'A crear en Fase 1'). El endpoint no puede servir datos hasta que sea creada y populada.\n• [SCHEMA] `subcategory_id` en el output schema del ticket no existe en model.py, la tabla smartBudgetSuggestion, ni en ningún doc interno. ¿Requisito nuevo o error de copiado?\n• [SCHEMA] `confidence` está en el contrato DS-ML pero ausente del output schema del ticket. Si es intencional, BlossomAPI no lo incluirá y Dough pierde una señal clave de UX.\n• [SCHEMA] `basis.data_points` en el ticket ≠ `basis.months_with_positive_spend` en el modelo — hay que alinear antes de implementar.\n• [OWNERSHIP] El deliverable (endpoint REST) vive en BlossomAPI (área banca), pero el ticket está en el sprint DATA. No queda claro qué produce DS-ML aquí.\n• [AC] AC 1 y AC 5 se superponen — ambos piden documentación sin distinguir formato ni destinatario.\n• [SEGURIDAD] Autenticación y multi-tenancy (idClient/idCompany/idMember) ausentes de los ACs.\n• [UX] Ejemplo de display_label en inglés pero el modelo genera texto en español.\n\n**Estimación**\n• Tamaño realista (DS-ML scope): S (~6h) — data contract + alineación schema + docs\n• Si DS-ML también crea la tabla: M (~10h)\n• Si DS-ML es responsable del endpoint completo: M (~15h) — requiere aclaración urgente\n• Histórico: sin muestras comparables (n=0)\n• Story points actuales (6 pts = 6h) son consistentes con scope DS-ML-only únicamente\n\n**Subtasks sugeridos**\n• Alinear schema de output con Product/Dough (prerequisito para todo)\n• Crear migración de tabla smartBudgetSuggestion (bloqueante)\n• Escribir data contract / spec para BlossomAPI\n• Crear ticket en BlossomAPI para implementación del endpoint\n\n**Escenarios de prueba sugeridos**\n• Miembro sin buckets que califiquen gating → respuesta [] vacía (no null, no error)\n• Miembro con buckets parciales → solo los calificados en respuesta (verifica AC 3)\n• Query cross-tenant: memberA no devuelve datos de memberB (aislamiento multi-tenant)\n• Carrera entre upsert del batch y lectura del endpoint\n• Datos stale: batch sin correr en semanas — ¿hay SLA de frescura?\n\n**Dependencias detectadas**\n• DATA-1138 (método WMA-B lb=3) — referenciado pero no linkeado como bloqueante en Jira\n• Tabla smartBudgetSuggestion — sin ticket asignado para su creación\n• Equipo BlossomAPI — sin ticket visible para la implementación del endpoint\n\n**Recomendaciones**\n• Resolver los tres desajustes de schema antes de implementar — son difíciles de corregir post-deploy\n• Dividir en dos tickets: DS-ML (data contract + table migration) y BlossomAPI (endpoint + authn + docs)\n• Linkear DATA-1138 como bloqueante en Jira\n\n**Positivo**\n• La descripción tiene contexto, schema propuesto y referencias al PRD — muy útil para BlossomAPI.\n• El pipeline DS-ML (filter → aggregate → gate → model) ya está implementado y testeado (PRs #3-#8).\n• ACs 2, 3 y 4 son específicos y verificables.\n\n_Notas técnicas: `model.py:compute_budget_suggestions()` produce `{category_id, defaultcategory, idaccount, idclient, idcompany, suggested_amount, basis{months_analyzed, months_with_zero, months_with_positive_spend, period_range, method, treatment}, confidence, display_label, explanation, model_version}`. La tabla `smartBudgetSuggestion` (docs/codemap/00-overview/Data-Pipeline.md) tiene columnas `{id_client, id_company, id_member, category_id, period_id, suggested_amount, months_analyzed, data_points, period_range, confidence, display_label, model_version}`. Método seleccionado: WMA + Treatment B + lookback=3 (DATA-1138, PR #7). BlossomApi está en área `banca` del jira-repo-map.yml. `smart_budget` no está registrado en jira-repo-map.yml — considerar agregarlo bajo el área `data`._",
  "published_comment_id": ""
}
```
