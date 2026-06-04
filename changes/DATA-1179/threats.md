# Threat Analysis: DATA-1179

Reviewer: blossom-security (automated)  
Inputs:   changes/DATA-1179/plan.md, changes/DATA-1179/spec.md  
Date:     2026-06-01

---

## Overall risk level

**High**

Esta ticket promueve `idmember` de anotación incidental al grain primario de todo el pipeline. Cinco riesgos compuestos: (1) `apply_gating` pierde `idclient`/`idcompany` de su groupby → apertura de cross-tenant mixing; (2) `idmember` fluye por todos los logs sin test que verifique SHA-256+SB_LOG_SALT; (3) API sigue aceptando `idaccount` mientras el pipeline output es `idmember`-grain; (4) `total_suggested` sin UDAAP review; (5) append-only en `smartBudgetSuggestionLog` sin enforcement mecánico.

---

## Category review

### 1. Authentication — Low
- Sin nuevos endpoints públicos. Sin nuevos flows de autenticación.
- **Observación (no bloqueante):** API endpoint aún autenticado con `idaccount`. La migración a `idmember` como query param es dependencia bloqueante no rastreada.

### 2. Authorization — **High**

- **GAP CRÍTICO: `apply_gating` elimina `idclient`/`idcompany` de su groupby.** Si dos CUs tienen miembros con mismo `idmember` numérico, sus decisiones de gating se mezclan silenciosamente. Viola el invariante: "Toda query filtrada por `(idClient, idCompany, idMember)`".
- **Fix requerido:** `apply_gating` groupby debe incluir `idclient` + `idcompany`:  
  `groupby(["idclient", "idcompany", "idmember", "idcategory", "defaultcategory"])`
- **TC-T7-2 deja el guard como "o" ambiguo.** Debe especificar exactamente qué función eleva excepción y qué error.
- `compute_budget_suggestions` groupby para `total_suggested` también debe incluir `idclient` + `idcompany`.

### 3. Input Validation — Medium

- **EXT strip sin validación.** Si `idaccount = "EXTABC"` → strip produce no-numérico → falla silenciosa o excepción. Agregar validación numérica post-strip.
- **SQL injection en `--source db`.** Nuevos JOINs con `blossomdoughconsolidatedaccountid` (valor externo de Plaid/Finicity) DEBEN usar queries parametrizadas, nunca concatenación.
- **idmember null silencioso.** Si `idmember` falta en el DataFrame, `compute_budget_suggestions` podría escribir a `smartBudgetSuggestion` con `id_member = null`, violando constraint NOT NULL.

### 4. PII / Data Protection — **High**

- **`idmember` es PII de primer nivel en todo el pipeline.** No existe ningún test contract que verifique que los logs hayan aplicado SHA-256 + `SB_LOG_SALT`. El requisito es solo nota en prosa.
- **`total_suggested` + `idmember` + `period_id` = perfil financiero sensible.** Si se logea a nivel DEBUG, se expone el perfil completo.
- **`SB_LOG_SALT` sin historia de rotación documentada.** `idmember` son enteros pequeños → rainbow table trivial con salt conocido.
- **`generate_golden_set.py` debe tener guard** que impida ejecución con `--source db` o en entorno producción.

### 5. Audit Trail — Medium

- **Upsert vs. snapshot-freeze contradiction.** `INSERT ... ON CONFLICT DO UPDATE` con mismo `model_version` sobreescribe sugerencias ya presentadas. Resolución: cambiar a `DO NOTHING` o incrementar `model_version` por corrida.
- **Sin audit event de pipeline-run.** No hay log estructurado de: quién disparó la corrida, cuándo, con qué parámetros, cuántos miembros procesados, cuántos `idmember = null`.
- **`smartBudgetSuggestionLog` append-only sin enforcement mecánico.** Solo declarado arquitecturalmente; sin DB trigger ni REVOKE.

### 6. Business Logic — **High**

- **`monthly_total` a grain `idmember` no especificado.** Un miembro con 2 cuentas ($200 + $150 en GROCERIES el mismo mes): ¿se suma a $350 o se usa el primero? La spec no define este paso.
- **`total_suggested` null/zero ambiguo.** TC-T4-4 dice "0.0 (o None — aclarar en impl)". `0.0` muestra "$0 total budget"; `None` oculta el widget. Debe cerrarse antes de implementar.
- **API/model grain mismatch es cambio rompedor.** `GET /smart-budget/suggestion` usa `idaccount` como parámetro. T4 elimina `idaccount` del output. Sin API update, el serving producirá 404s para todos los miembros.

### 7. External Dependencies — Low
- Sin nuevas dependencias externas. `boto3`, `pandas`, `structlog` pre-existen.

### 8. Infrastructure — Medium

- **Falta índice DB en `blossomdoughconsolidatedaccountid`.** Sin índice, el JOIN OLB será full-scan por cada batch run.
- **Paths IAM para S3 silver no especificados.** `memberaccount.csv` y `account.csv` deben estar en el scope de la política `blossom-dev`.

### 9. Compliance — **High**

- **`total_suggested` sin UDAAP review.** La copy asociada podría ser prescriptiva. Legal/compliance debe aprobar antes del merge.
- **`smartBudgetSuggestionLog` sin enforcement a nivel DB.** No sirve como artefacto de compliance ante NCUA si puede modificarse.
- **Section 1033 gap.** Agregar datos EXT (Plaid/Finicity) a grain `idmember` crea perfil financiero más rico. Confirmar que cae dentro del acuerdo de uso de Plaid/Finicity.

### 10. Operational Security — Medium

- **`SB_LOG_SALT` sin rotación documentada** (ver PII-4).
- **`generate_golden_set.py` sin source guard.**
- **Sin alerting de cobertura** si porcentaje de `idmember = null` supera umbral.

---

## Mandatory controls (12) — deben implementarse antes del merge

- [ ] **[AUTH-2]** `apply_gating` groupby: agregar `idclient` + `idcompany`
- [ ] **[AUTH-2]** `compute_budget_suggestions` groupby de `total_suggested`: agregar `idclient` + `idcompany`
- [ ] **[AUTH-2]** TC-T7-2: especificar exactamente función + excepción (eliminar "o")
- [ ] **[PII-4]** Test contracts de log masking en T1, T3, T4: assert no raw `idmember` en logs
- [ ] **[PII-4]** Documentar ubicación de `SB_LOG_SALT` (Secrets Manager/SSM, no `.env`)
- [ ] **[BL-6]** Especificar paso SUM en spec T3/T4 para colapsar `monthly_total` a grain `idmember`
- [ ] **[BL-6]** TC-T4-4: cerrar ambigüedad `0.0` vs `None` definitivamente
- [ ] **[INPUT-3]** `_resolve_idmember`: validar que EXT strip produce valor numérico; agregar TC-T1-5
- [ ] **[INPUT-3]** `--source db` JOINs: confirmar queries parametrizadas (TC-T1-6)
- [ ] **[AUDIT-5]** Resolver upsert-vs-snapshot-freeze: `DO NOTHING` o bump de `model_version`
- [ ] **[COMPLIANCE-9]** UDAAP review + `total_suggested_display_label` con copy neutral aprobada
- [ ] **[COMPLIANCE-9]** `smartBudgetSuggestionLog`: agregar `REVOKE UPDATE, DELETE` en migration o DB trigger

---

## Gate Decision

**HUMAN GATE.** Un security reviewer (o TL) debe revisar este archivo y agregar la línea de aprobación antes de que el implementer corra `/blossom-workflow:execute`.

Los items más críticos que requieren juicio humano:
1. Multi-tenant groupby gap en `apply_gating` — riesgo de autorización
2. UDAAP sign-off para `total_suggested` — riesgo de compliance
3. `smartBudgetSuggestionLog` append-only enforcement — riesgo de auditoría
4. API/model grain mismatch — riesgo de integración

---

## Approval

```
Decision: approved by lbetancourth-dev-blossom — 2026-06-01
```
