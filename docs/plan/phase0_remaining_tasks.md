# Fase 0 — Tareas restantes para implementación completa

**Fecha:** 2026-05-08
**Branch:** `DATA-1041`
**Documento padre:** [`plan_phase_0.md`](plan_phase_0.md)

> Este documento lista lo que falta para considerar Fase 0 **lista para producción** (pilot CU). Las tareas están agrupadas por área y priorizadas. La sección **A** es bloqueante para cualquier release; las secciones **D-K** se pueden trabajar en paralelo o secuenciar según capacidad del equipo.

---

## ✅ Estado actual (lo que ya está en `DATA-1041`)

- [x] **Step 1** — Extracción DOUGH: 30 tablas dev + 23 alpha → `data/dough/*/silver/`
- [x] **Step 2** — Extracción OLB: 7 tablas (1M+ txns) → `data/olb/dev/silver/`
- [x] **Step 3** — `fact_transactions.csv`: 1,413,914 filas unificadas (OLB_SUB + OLB_LOAN + DOUGH_EXT)
- [x] **Modelo de mediana + gating** (`aggregator.calculate_suggestions`)
- [x] **Confidence** (`high/medium/low`) + display_label
- [x] **Builders de output** `budget` y `budgetcategory`
- [x] **T&C gate** (`filter_members_with_tac`)

> **`fact_transactions` construida y verificada.** Steps 4-5 (aplicar modelo sobre fact_transactions y escribir a BD) son el siguiente bloque de trabajo.

---

## A. Validación y testing  🔥 **Prioridad 1 — bloqueante**

- [ ] **A1.** Tests unitarios para `filters.py`:
   - `get_expense_category_ids` (incluye solo grupo 1, excluye `shouldshow=false`).
   - `filter_manual_transactions` (ventana N, `deletedat IS NULL`, `idcategory` válido).
   - `filter_members_with_tac` (member sin aceptación → excluido).
- [ ] **A2.** Tests unitarios para `aggregator.py`:
   - `aggregate_monthly_spend` (suma correcta por member × cat × mes).
   - `calculate_suggestions` (mediana, gating <2 meses, redondeo 2 decimales).
   - Confidence (`high ≥6`, `medium 3-5`, `low =2`).
   - Edge: meses con $0, mes en curso excluido, suma neta negativa → clamp a 0.
- [ ] **A3.** Tests de **multi-tenancy leak**: ningún member ve sugerencias de otro member o CU.
- [ ] **A4.** Tests de **idempotencia**: re-ejecutar `run_phase0.py` el mismo día no duplica filas en `budget`/`budgetcategory`.
- [ ] **A5.** **Golden set** sintético en `tests/fixtures/golden_set.csv`: 50-100 members con histórico variado (full data, gating, low confidence, joint accounts) y resultado esperado calculado a mano.
- [ ] **A6.** Test de integración contra dev real (no test data) — al menos un smoke test que conecte y agregue.
- [ ] **A7.** Cobertura mínima 80% en `filters.py` + `aggregator.py` (configurar `pytest-cov`).

## B. Persistencia real (de CSV → BD)  🔥 **Prioridad 1**

- [ ] **B1.** Decidir destino: ¿extender `budgetcategory` con columnas DS-ML (`suggested_amount`, `confidence`, `model_version`) o crear tabla nueva `smartBudgetSuggestion`? **Decision Record requerido.**
- [ ] **B2.** Schema final de `smartBudgetSuggestion` (si se elige nueva): UNIQUE `(id_member, category_id, period_id, model_version)`, índice `(id_client, id_company, id_member, period_id)`.
- [ ] **B3.** Crear schema de `smartBudgetSuggestionLog` (append-only, captura del loop). Definir punto de inserción (frontend Dough o BlossomAPI).
- [ ] **B4.** Reemplazar la escritura a CSV por `INSERT ... ON CONFLICT DO UPDATE` (Postgres) o `MERGE` (Redshift).
- [ ] **B5.** Implementar **snapshot freeze**: si recalculamos para un período ya emitido, insertar fila nueva con timestamp distinto, no actualizar.
- [ ] **B6.** Conexión: ¿escribimos a Dough DB operativa via BlossomAPI, o a Redshift/gold y un job sincroniza? **Decision Record requerido.**

## C. Robustez del modelo y casos edge

- [ ] **C1.** Integrar `externaltransaction` cuando Backend confirme cómo llega `idcategory` (UNION con `manualtransaction` antes del agregado).
- [ ] **C2.** Manejo de `joint accounts` (`memberaccount` con `role`): ¿se calcula a nivel member o se reparte? — confirmar con Producto.
- [ ] **C3.** Excluir transacciones de cuentas con `memberproviderlink.status='inactive'`.
- [ ] **C4.** Reembolsos / `type='credit'` en `externaltransaction`: restar del gasto del mes; clamp a 0 si la suma neta queda negativa.
- [ ] **C5.** `issplit=true`: documentar comportamiento esperado (hoy no aparece en dev) y dejar test pendiente para cuando exista.
- [ ] **C6.** Moneda distinta a USD: skip + log warning (pendiente en aggregator).
- [ ] **C7.** Time zone: confirmar política — UTC vs `company.configuration.timeZone`. Aplicar consistente en `processdate`.
- [ ] **C8.** Categorías con un único gasto muy alto: documentar que Fase 0 no excluye outliers; se ataca en Fase 2.

## D. Orquestación (Airflow)

- [ ] **D1.** Diseñar DAG con cadencia (¿mensual día 1, o nocturno?). **Decision Record.**
- [ ] **D2.** Tasks separadas: `extract → aggregate → calculate → write → notify`.
- [ ] **D3.** Idempotencia del DAG: marcar `model_version` por corrida y permitir re-ejecución manual.
- [ ] **D4.** Manejo de fallos: retries con backoff, dead-letter queue.
- [ ] **D5.** Fallback: si el DAG falla, BlossomAPI sirve la última corrida válida (no devolver vacío).
- [ ] **D6.** Logging estructurado (`structlog`) con `job_id`, `model_version`, `n_members_processed`, `n_suggestions_emitted`, `started_at`, `finished_at`.
- [ ] **D7.** Member ID hasheado en logs (PII) — `SHA-256 + SB_LOG_SALT`.

## E. API / Serving (coordinación con BlossomAPI)

- [ ] **E1.** Definir contrato REST con BlossomAPI:
   - `GET /smart-budget/suggestion?member_id=...&period_id=YYYY-MM`
   - `POST /smart-budget/decision` (captura del loop).
- [ ] **E2.** Versionar el JSON contract en `docs/DATA_CONTRACT.md`.
- [ ] **E3.** SLA de latencia para servir sugerencia (target propuesto: p95 < 200ms).
- [ ] **E4.** Manejo de errores: 200 con array vacío si no hay sugerencias; 404 solo si member no existe; nunca 500 por falta de data.
- [ ] **E5.** Idempotencia del POST: mismo `(member, category, period, ts_presented)` → 200 sin duplicar.

## F. Loop de retroalimentación

- [ ] **F1.** Tabla `smartBudgetSuggestionLog` creada y poblada desde el primer release.
- [ ] **F2.** Captura del frontend Dough: `original_suggested_amount`, `final_user_amount`, `accepted_without_change`, `ts_presented`, `ts_confirmed`.
- [ ] **F3.** Job mensual de **reconciliación** con gasto real al cierre del período (cruce con `budgetcategory.allocatedamount` y suma real de `manualtransaction`/`externaltransaction`).
- [ ] **F4.** Métrica `accuracy_delta` calculada en gold y expuesta en dashboard.

## G. Métricas y monitoreo

- [ ] **G1.** Definir queries de las 5 métricas Fase 0:
   - `acceptance_rate` = aceptadas sin cambio / presentadas
   - `edit_rate` = modificadas / presentadas
   - `abandonment_rate` = inician y no completan / inician
   - `time_to_budget` = ts(setup completo) − ts(inicio flujo)
   - `coverage` = categorías con sugerencia / categorías del member
- [ ] **G2.** Dashboard (Looker / Metabase / lo que use Blossom Analytics).
- [ ] **G3.** Alertas operativas:
   - Coverage cae bajo X%.
   - Tasa de error del DAG > Y% en 24h.
   - Drift en distribución de `confidence` (low se dispara).
- [ ] **G4.** Reporte semanal automatizado al equipo de Producto durante el piloto.

## H. Compliance y copy

- [ ] **H1.** Revisión legal de los `display_label` con compliance/legal (UDAAP/CFPB).
- [ ] **H2.** Documento `docs/COPY_GUIDELINES.md` con frases válidas vs inválidas.
- [ ] **H3.** Disclaimer "no asesoría financiera" — confirmar dónde se muestra (T&C de Dough o en cada pantalla de Smart Budget).
- [ ] **H4.** Política de retención y borrado (Section 1033) cuando un member desconecta Plaid/Finicity.

## I. Datos en dev → alpha → prod

- [ ] **I1.** Confirmar con Backend Dough cómo llega `idcategory` a `externaltransaction` (runtime via Ntropy, o tabla pendiente de replicar).
- [ ] **I2.** Solicitar a Data Engineering la replicación de las tablas transaccionales (`account`, `externaltransaction`, `budget`, `budgetcategory`, `memberaccount`, `memberproviderlink`, `period`) al lake **alpha** — coherente con dev.
- [ ] **I3.** Confirmar existencia de `blossom-analytics-datalake-prod` y plan de acceso.
- [ ] **I4.** Política de credenciales: ¿se trabaja con `blossom-dev` siempre, o se necesita perfil read-only de prod para validación final?

## J. Documentación pendiente

- [ ] **J1.** `docs/ARCHITECTURE.md` — diagrama del pipeline DS-ML (Mermaid).
- [ ] **J2.** `docs/DECISIONS.md` — Decision Log con el Top 12 cerrado (de `Fase0_Analisis_y_Workflow_DS-ML.md`).
- [ ] **J3.** `docs/DATA_CONTRACT.md` — schema JSON versionado del output.
- [ ] **J4.** `docs/COPY_GUIDELINES.md` — UDAAP-compliant phrasing.
- [ ] **J5.** `docs/runbook.md` — operación: cómo correr, debug, rollback.
- [ ] **J6.** Actualizar `README.md` con badges (CI, coverage) cuando estén.

## K. Pre-launch / Pilot CU

- [ ] **K1.** Seleccionar CU piloto (Clarity o Wasatch Peaks) con Producto.
- [ ] **K2.** Encuestas internas H0-1 a H0-4 a colaboradores Blossom (ver PRD §4) — ¿corren antes o durante el pilot?
- [ ] **K3.** **Shadow mode:** correr el modelo y persistir sugerencias sin exponerlas al usuario; medir qué habría sugerido vs qué pone manualmente.
- [ ] **K4.** Plan de rollout: shadow → soft launch (10% members) → general.
- [ ] **K5.** Plan de rollback: feature flag para apagar Smart Budget sin redeploy.
- [ ] **K6.** Performance / load testing del endpoint de serving.
- [ ] **K7.** War room para las primeras 2 semanas post-launch.

---

## Roadmap propuesto (orden recomendado)

```
Semana 1-2:  A1-A7 (testing) + B1-B6 (persistencia real)        ← bloqueante
Semana 2-3:  C1-C8 (robustez) + D1-D7 (Airflow)                  ← paralelo
Semana 3-4:  E1-E5 (API) + F1-F4 (loop) + I1-I4 (data)          ← coordinación cruzada
Semana 4-5:  G1-G4 (métricas) + H1-H4 (compliance)               ← previo a launch
Semana 5-6:  J1-J6 (docs) + K1-K7 (pre-launch)                   ← release
```

> Tiempos referenciales — ajustar según ancho de banda real del equipo.

---

## Decisiones bloqueantes (Top 5 a resolver YA)

1. **B1:** ¿`smartBudgetSuggestion` nueva o extender `budgetcategory`?
2. **B6:** ¿Escribimos a Dough DB via BlossomAPI o a gold/Redshift?
3. **C2:** ¿Cómo se calcula Smart Budget en joint accounts?
4. **C7:** ¿Time zone UTC global o el de cada CU?
5. **K1:** ¿Cuál CU es la piloto?

Estas cinco bloquean varias tareas posteriores. **Recomendación: workshop de 60 minutos con Producto + Backend Dough esta semana** para cerrarlas.
