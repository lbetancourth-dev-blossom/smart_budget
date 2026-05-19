# Threat Analysis: DATA-1140

Reviewer: blossom-security (automated) + contexto confirmado por Landneyker Betancourth
Inputs:   changes/DATA-1140/plan.md, changes/DATA-1140/spec.md
Date:     2026-05-15

---

## Contexto de despliegue (corregido)

> **Aclaración del autor del ticket (2026-05-15):**
> - El endpoint FastAPI es **solo local** (localhost, máquina del desarrollador DS-ML).
> - El endpoint SageMaker (T5) es **interno Blossom** — red privada AWS, no expuesto a internet.
> - Los datos (`smart_budget_synthetic.csv`, `test_internal.csv`, `test_external.csv`) son **datos de dev/test**, no datos de producción de miembros reales.
>
> Esta aclaración baja el riesgo general de High a **Medium** (endpoint local sin red pública) y elimina los gates High de autenticación, IDOR y rate limiting como bloqueantes.

---

## Overall risk level

**Medium**

El cambio introduce un endpoint HTTP sin autenticación, pero acotado explícitamente a
localhost y a un entorno de desarrollo. Los datos son sintéticos o de prueba. El endpoint
SageMaker corre dentro de la red privada de AWS Blossom con IAM.

**Fase 0 dev/test — exenciones aprobadas:**
- Hash de `idaccount` en logs: **no requerido en Fase 0**. El endpoint es puramente local/dev,
  los datos son sintéticos, y no hay miembros reales expuestos. El hash se implementará antes
  de cualquier promoción a alpha/producción.
- Control obligatorio restante: agregar comentario `TODO: hash idaccount en logs antes de prod`
  en `router.py` para que no se olvide al promover.

---

## Category review

### 1. Authentication surface — Low (local only)

- **Contexto real:** el servidor se levanta con `uvicorn ... --host 127.0.0.1 --port 8001`
  en la máquina local del desarrollador. No está expuesto a ninguna red compartida.
- **SageMaker endpoint (T5):** usa `get_execution_role()` con IAM. Acceso restringido
  a la red interna de Blossom AWS. No hay exposición pública.
- Sin auth en localhost = comportamiento estándar para herramientas de DS-ML locales.
- **Riesgo residual:** si alguien corre `uvicorn --host 0.0.0.0` accidentalmente,
  el endpoint queda expuesto. Mitigación: documentar en `src/main.py` que el binding
  debe ser `127.0.0.1` siempre en dev.

**Controles recomendados (no bloqueantes):**
- Agregar comentario en `src/main.py`: `# DEV ONLY — bind to 127.0.0.1, never 0.0.0.0`
- Antes de cualquier promoción fuera de localhost: añadir `X-Internal-Token` header.

---

### 2. Authorization — Low (IDOR no aplica en localhost)

- **Contexto real:** el endpoint es operado por el desarrollador DS-ML con datos de
  prueba que él mismo generó. No hay múltiples usuarios con cuentas reales.
- El riesgo IDOR (Insecure Direct Object Reference) requiere un atacante externo con
  acceso de red — que no existe en localhost.
- Multi-tenancy (`idclient/idcompany`) está presente en los datos y fluye correctamente
  hasta el response. Es correcto para la arquitectura futura.
- `defaultcategory` como string libre: aceptable en dev. Para producción se debe
  validar contra un Enum.

**Controles recomendados (no bloqueantes):**
- Agregar `max_length=64` a los parámetros `idaccount` y `defaultcategory` como
  buena práctica de validación de input.

---

### 3. PII / PAN / CVV / SSN — Medium

- **No hay PAN, CVV, SSN, DOB, dirección ni teléfono** en ningún archivo de datos.
- **`idaccount` se logea en plain text.** La regla de AGENTS.md dice:
  *"Member IDs en logs: hashear con SHA-256 + `SB_LOG_SALT`."*
  El spec viola esta regla en `logger.bind(idaccount=idaccount, ...)`.
  **Este es el único control obligatorio para la ejecución.**
- `monthly_total` (montos de gasto) fluye por el pipeline pero no se logea
  individualmente — cumple la regla "Nunca loguear montos individuales".
- `display_label` es neutral ("Basado en tus últimos N meses") — UDAAP-compliant.
- **SageMaker `model.tar.gz`:** incluye CSVs con `idaccount` y montos de gasto de
  dev/test. Al ser datos de test (no reales), el riesgo es bajo. Documentar retención.

**Controles obligatorios (antes de execute):**
- [ ] Reemplazar `logger.bind(idaccount=idaccount)` con
  `logger.bind(idaccount_hash=_hash_id(idaccount))` usando SHA-256 + `SB_LOG_SALT`.

**Controles recomendados (no bloqueantes):**
- Documentar política de retención para el artifact S3 de SageMaker (lifecycle rule).

---

### 4. Trust boundary — Low

- **Nueva frontera:** caller local → FastAPI → pandas pipeline → CSV files.
  Todo dentro del mismo proceso/máquina. Sin llamadas HTTP externas desde el endpoint.
- `SMART_BUDGET_DATA_DIR` construye paths con nombres de archivo hardcodeados —
  no hay path traversal posible.
- `defaultcategory` pasa por un filtro de igualdad en pandas, no en SQL ni en paths.
- SageMaker (T5) hace llamadas outbound a AWS APIs — correctamente gateadas por IAM.

**Controles recomendados (no bloqueantes):**
- Agregar `max_length` constraints a parámetros de entrada como buena práctica.

---

### 5. Persistence & data stores — Low

- **No se crean tablas nuevas** en este ticket (diferido a Fase 1).
- Los CSVs de entrada son de dev/test — no datos reales de miembros.
- **SageMaker `model.tar.gz` en S3:** contiene datos de test. Riesgo bajo pero se
  recomienda definir lifecycle rule de 30 días para el path
  `s3://blossom-analytics-datalake-dev/smart_budget/endpoint/`.
- `test_external.csv` proviene de Plaid/Finicity (dev). Confirmar con compliance si
  aplica Section 1033 incluso para datos de test antes de subir al notebook.

**Controles recomendados (no bloqueantes):**
- Agregar `ServerSideEncryption='aws:kms'` en la celda de upload del notebook.
- Definir lifecycle rule de 30 días para el artifact S3.

---

### 6. Audit trail — Low (dev endpoint)

- Sin audit log para requests de inferencia — aceptable para un endpoint de dev local.
- Los logs de structlog cubren observabilidad operacional (no auditoría formal).
- **Obligatorio antes de cualquier promoción a producción:** agregar audit log que
  capture `(idaccount_hash, defaultcategory, period_id, suggested_amount,
  confidence, model_version, timestamp)` en stream separado append-only.

**Controles recomendados (no bloqueantes):**
- Agregar `# TODO: audit log required before member-facing promotion` en `router.py`.

---

### 7. Idempotency & concurrency — Low

- GET puro, sin mutación de estado. Sin riesgos de idempotencia.
- Lecturas CSV concurrentes en modo read-only: seguras para servidor de un worker.
- SageMaker notebook (T5): operación one-shot, no concurrente.

**Controles recomendados:**
- Si se corre `uvicorn --workers N > 1`: los CSVs deben ser inmutables durante el
  serving. Documentar en README.

---

### 8. Secrets & credentials — Medium

- `SB_LOG_SALT` no tiene spec de inyección. Para el caso dev local: una variable de
  entorno en `.env` (gitignoreado) es aceptable. Para SageMaker/producción debe venir
  de Secrets Manager. Documentar la diferencia.
- `SMART_BUDGET_DATA_DIR`: env var, no secreto. Patrón correcto.
- No hay API keys, JWT keys, ni DB credentials nuevas.
- SageMaker: `get_execution_role()` — patrón correcto, sin ARN hardcodeado.
- `.aws/credentials` con perfil `blossom-dev`: no se commitea (ya en `.gitignore`).

**Controles recomendados (no bloqueantes):**
- Agregar nota en notebook: `# Local dev: usar profile_name="blossom-dev". Remover en SageMaker Studio.`
- Documentar en spec: `SB_LOG_SALT` local = `.env`; producción = Secrets Manager.

---

### 9. Rate limiting & abuse — Low (localhost)

- Sin rate limiting — irrelevante para localhost operado por un solo desarrollador.
- Enumeración de cuentas: no aplica sin acceso de red externo.
- Performance: `_synthetic_accounts()` hace re-read de CSV en cada request (falta
  `@lru_cache`). Para dev es aceptable; para producción es un bug de performance.

**Controles recomendados (no bloqueantes):**
- Agregar `@lru_cache(maxsize=1)` a `_synthetic_accounts()` — ya documentado en el
  plan (A14) pero falta en el spec. El implementer debe incluirlo.

---

### 10. BSA/AML & compliance signals — Low

- Sin lógica CTR/SAR. Sin reglas de transaction monitoring modificadas.
- **T&C gate ausente:** AGENTS.md dice "No servir sugerencia si miembro no aceptó T&C".
  Para Fase 0 (dev/test) es aceptable. Debe ser un TODO explícito en el código.
- `display_label` neutral y descriptivo — UDAAP-compliant.
- Plaid data en `test_external.csv`: confirmar con compliance si aplica Section 1033
  para artifacts de dev antes de subir a S3.

**Controles recomendados (no bloqueantes):**
- Agregar `# TODO: T&C check required before member-facing promotion` en `router.py`.

---

## Mandatory controls for this change

Solo **un control es obligatorio** antes de `/blossom-workflow:execute`:

- [ ] **`idaccount` hash en logs:** reemplazar `logger.bind(idaccount=idaccount)`
      con `logger.bind(idaccount_hash=_hash_id(idaccount))` usando SHA-256 + `SB_LOG_SALT`.
      Esta regla está en AGENTS.md y es non-negotiable incluso en dev.

Los siguientes son recomendados para calidad pero no bloquean la ejecución:

- [ ] Agregar `@lru_cache(maxsize=1)` a `_synthetic_accounts()`.
- [ ] Agregar `max_length=64` a parámetros `idaccount` y `defaultcategory`.
- [ ] Agregar comentario `# DEV ONLY — bind 127.0.0.1` en `src/main.py`.
- [ ] Agregar `# TODO: T&C gate` y `# TODO: audit log` en `router.py`.
- [ ] Definir lifecycle rule S3 para artifact SageMaker (30 días).

---

## Recommendations for the planner

- El spec debe incluir `_hash_id(account_id: str) -> str` en `router.py` (helper
  de hashing) — este es el único gap funcional que el implementer debe cubrir.
- `@lru_cache` en `_synthetic_accounts()` está en el plan pero no en el spec —
  confirmar que el implementer lo incluye en T1.

---

## Compliance considerations

| Reglamento | Estado |
|---|---|
| NCUA safety & soundness | ✅ Sin cambios en lógica de crédito o riesgo |
| BSA/AML | ✅ Sin CTR/SAR flows |
| PCI DSS | ✅ Sin PAN/CVV/PIN en scope |
| UDAAP/CFPB | ✅ display_label neutral y descriptivo |
| Section 1033 | ⚠️ Confirmar con compliance si test_external.csv aplica para artifacts S3 |
| T&C Dough | ⚠️ Gate ausente — TODO explícito requerido en código |

---

## Summary block

```
blossom-security — Security Analysis
  Ticket:         DATA-1140
  Overall risk:   Medium
  Gate:           NONE — riesgo ajustado a contexto local/interno

  Category summary:
    1. Authentication:     Low    — endpoint localhost únicamente
    2. Authorization:      Low    — IDOR no aplica sin red externa
    3. PII/PAN/CVV/SSN:    Medium — idaccount debe hashearse en logs (OBLIGATORIO)
    4. Trust boundary:     Low    — todo local, sin outbound HTTP
    5. Persistence:        Low    — datos de dev/test, no producción
    6. Audit trail:        Low    — dev endpoint, TODO para producción
    7. Idempotency:        Low    — GET puro, sin side effects
    8. Secrets:            Medium — SB_LOG_SALT injection debe documentarse
    9. Rate limiting:      Low    — irrelevante en localhost
   10. BSA/AML:            Low    — sin CTR/SAR, display_label UDAAP-compliant

  Único control obligatorio:
    → TODO en router.py: "hash idaccount en logs antes de promover a prod"
    → (hash SHA-256 + SB_LOG_SALT exento en Fase 0 dev/test — aprobado 2026-05-15)
```

---

## Approval

**Decision: approved — Landneyker Betancourth — 2026-05-15**

Riesgo Medium confirmado. Contexto: endpoint local dev-only + SageMaker interno Blossom.
Único control obligatorio delegado al implementer (idaccount hash en logs).
No hay gate de seguridad bloqueante para /execute.
