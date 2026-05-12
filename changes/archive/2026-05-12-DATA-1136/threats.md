# Threat Analysis — DATA-1136

**Reviewer:** blossom-security (automated)  
**Inputs:** changes/DATA-1136/plan.md, changes/DATA-1136/spec.md  
**Date:** 2026-05-11

---

## Overall risk level

**High**

Tres issues elevan el riesgo a High:

1. **T&C gate ausente.** La arquitectura de Fase 0 (plan_phase_0.md) requiere filtrar por `membertacacceptance` antes de cualquier procesamiento de Smart Budget. El spec de DATA-1136 (reglas A1–A8) omite este gate — el pipeline procesaría perfiles financieros de miembros que nunca consintieron Smart Budget. Exposición directa a UDAAP / CFPB Section 1033.

2. **idmember sin maskear en rutas de error.** El spec prohíbe loguear IDs sin hashear en logs explícitos, pero los tracebacks de Python/pandas pueden exponer `idmember` y montos a stdout/stderr sin ningún mask.

3. **Sin cifrado ni control de acceso especificado** para el CSV de output `smart_budget_prep.csv` — un perfil financiero por miembro vinculado a `idmember`.

---

## Categorías

| # | Categoría | Riesgo |
|---|-----------|--------|
| 1 | Autenticación | Low |
| 2 | Autorización | Medium |
| 3 | PII / PAN / CVV / SSN | High |
| 4 | Trust boundary | Medium |
| 5 | Persistencia | Medium |
| 6 | Audit trail | Medium |
| 7 | Idempotencia | Low |
| 8 | Secrets | Low |
| 9 | Rate limiting | Low |
| 10 | BSA/AML | High |

---

## Findings críticos (bloquean /execute hasta ser resueltos)

### F1 — T&C gate ausente [BSA/AML · High]

El pipeline debe filtrar `idmember` contra `membertacacceptance` **antes** de agregar transacciones. Sin este gate, miembros que no aceptaron T&C de Smart Budget tendrán perfiles generados.

**Acción requerida en spec.md:** Agregar regla A9 en `filter_transactions()`:
```python
# A9: solo miembros con T&C aceptado
df = df[df["idmember"].isin(accepted_members)]
```
`accepted_members` debe recibirse como parámetro o cargarse desde `membertacacceptance.csv`.

### F2 — PII en rutas de error [PII · High]

`run_smart_budget_prep.py` debe tener un exception handler global que capture todos los errores y los loguee de forma sanitizada antes de salir con código 1. Sin esto, tracebacks de pandas pueden exponer `idmember` y montos a stderr.

**Acción requerida en spec.md T5:** Agregar sección de error handling con ejemplo explícito.

---

## Controles obligatorios (planner actualiza spec antes de /execute)

- [ ] **F1** Agregar A9 T&C gate a `filter_transactions()` — parámetro `accepted_member_ids: set[str]` o carga desde CSV/tabla
- [ ] **F2** Global exception handler en `run_smart_budget_prep.py` — log sanitizado, exit 1
- [ ] **Validación de schema en startup** — assert que columnas requeridas existen; dtypes básicos; row count > 0
- [ ] **idmember uniqueness assertion en `zero_fill()`** — cada `idmember` debe mapear a un único `(idclient, idcompany)`; raise ValueError con count (no raw IDs) si se viola
- [ ] **Permisos del output** — `os.chmod(output_path, 0o600)` post-escritura
- [ ] **Atomic write** — escribir a `smart_budget_prep.csv.tmp`, luego `os.replace()` al path final
- [ ] **Run provenance en logs** — agregar `input_file_hash` (SHA-256 del input CSV) y `output_row_count` a los campos estructurados del log final
- [ ] **idmember en logs** — hashear con HMAC-SHA256 + salt configurable (`SB_LOG_SALT`) si aparece en cualquier campo de log; solo counts en texto plano

---

## Recomendaciones adicionales (no bloquean, deben documentarse)

- Definir retención de `smart_budget_prep.csv`: sobrescrito en cada run, no archivado, eliminar si mayor a N días
- Documentar que `membertacacceptance` debe actualizarse antes de cada run del pipeline
- Agregar nota sobre re-run post right-to-deletion: si un miembro solicita eliminación, regenerar desde fuente filtrada
- Separar tarea de seguridad para `--db-pass` CLI arg en `build_fact_transactions.py` (fuera de scope DATA-1136)
- Ventana temporal histórica: considerar si transactions pre-2022 deben incluirse en el cálculo (actualmente sin límite de fecha)

---

## Gate decision

**Riesgo: High → HUMAN GATE**

**F1 — T&C gate:** Deferido explícitamente para ambiente dev/alpha. En prod se requiere filtro por `membertacacceptance`. El implementador debe agregar un `TODO` comentario en `filter_transactions()` marcando este punto para producción.

**F2 — Error handler global:** Incluido en spec T5. Resuelto.

Antes de correr `/execute`, un revisor debe aprobar abajo:

---

## Approval (completar antes de /execute)

```
Decision: approved by <nombre> — <YYYY-MM-DD>
```

**Decision: approved by lbetancourth-dev-blossom — 2026-05-11**

F1 (T&C gate) removido del scope: los datos son de ambiente de prueba (dev/alpha), no de usuarios finales.
F2 (error handler) incluido en spec. Todos los demás controles son recomendaciones no bloqueantes.
