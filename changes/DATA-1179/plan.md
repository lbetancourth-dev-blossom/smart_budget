# Plan — DATA-1179: DS - Smart Budget Dataset & Model Changes

**Ticket:** https://blossomtechnology.atlassian.net/browse/DATA-1179  
**Branch:** `feat/DATA-1179`  
**Model version:** `fase0-v1`  
**Riesgo:** Medium (PII: idmember en logs, multi-tenancy sensible)

---

## Context

Smart Budget Fase 0 calcula sugerencias de presupuesto por categoría. El dataset actual opera al nivel de `idaccount`, pero el producto necesita operar al nivel de `idmember` (el usuario de la CU). Además, el pipeline debe agregar un campo `total_suggested` por miembro y expandir el dataset sintético de prueba.

**Jerarquía de identidad (crítica):**
```
idclient (producto Blossom, ej. id=1 "Blossom", id=2 "Davivienda")
  → idcompany (Credit Union)
    → idmember (miembro/usuario de la CU — el input del modelo)
      → idaccount (cuenta individual)
```

`idclient` e `idcompany` son **filtros de multi-tenancy**, no inputs del modelo.  
`idmember` es el identificador del usuario final — el grain correcto del modelo.

---

## DCR — Decisiones cerradas

### D1 — Input del modelo: `idmember` [CERRADO]

**Decisión:** El input del modelo es `(idmember, period_id)`. `idclient` e `idcompany` son filtros de seguridad (multi-tenancy), no parámetros de entrada.

**Evidencia:** `client.csv` muestra `idclient=1="Blossom"`, `idclient=2="Davivienda"` — es el tenant del producto, no el usuario.

### D2 — Join para obtener `idmember` desde `idaccount` [CERRADO — auto]

**Decisión:** Estrategia dual en `build_fact_transactions.py`:

- **Cuentas EXT** (`EXT2`, `EXT22`): strip prefix `"EXT"` → `account.id` → `memberaccount.idmember`
- **Cuentas OLB** (`SUB8406`, `INT...`): `fact_transactions.idaccount` = `account.blossomdoughconsolidatedaccountid` → `account.id` → `memberaccount.idmember`
- Cuentas sin enlace: `idmember = null`, log warning, excluidas del modelo

**Evidencia:** `account.blossomdoughconsolidatedaccountid` es el puente entre cuenta Dough y su contraparte OLB. Solo 3 filas en `memberaccount.csv` en dev.

### D3 — `total_suggested` por miembro [CERRADO]

**Decisión:** Agregar campo `total_suggested` en el output = suma de todos los `suggested_amount` no nulos de las categorías del miembro en ese periodo.

**Shape de output:**
```json
{
  "idmember": "...",
  "period_id": "2026-05",
  "total_suggested": 1250.00,
  "suggestions": [
    { "category_id": "...", "suggested_amount": 420.00, ... },
    { "category_id": "...", "suggested_amount": null, ... }
  ]
}
```

### D4 — Expansión del dataset sintético [CERRADO]

**Decisión:** 6 meses (`2025-10` a `2026-03`), ≥3 `idmember` con cuentas EXT + 1 cuenta OLB vinculada via `blossomdoughconsolidatedaccountid`. Re-freeze del golden set tras los cambios.

---

## HLTC — Bloques arquitecturales

### HLTC-1 — Nuevo campo `idmember` en `fact_transactions` [ACEPTADO]

Cuentas sin enlace resultan en `idmember = null`. El modelo solo calcula sugerencias para miembros con ≥1 cuenta vinculada. Log warning para cuentas sin enlace.

Archivos impactados: `build_fact_transactions.py`, `run_smart_budget_prep.py`, `aggregator.py`, `model.py`.

### HLTC-2 — `total_suggested` en output [ACEPTADO]

`total_suggested` = suma solo de categorías con `suggested_amount` no nulo. Categorías con null (sin historial suficiente) no se incluyen en el total.

---

## Scope — Cambios por módulo

### T1 — `scripts/build_fact_transactions.py`
- Agregar lógica de join dual para `idmember`
- Leer `memberaccount.csv` y `account.csv` en modo `--source s3`
- Agregar `idmember` a `CANONICAL_COLS`
- Modo `--source db`: agregar JOIN a la query SQL

### T2 — `scripts/run_smart_budget_prep.py`
- Agregar `idmember` a `REQUIRED_COLUMNS` (warning si no está, no error fatal — backward compat)

### T3 — `src/smart_budget/aggregator.py`
- `aggregate_monthly`: agregar `idmember` al groupby (passthrough)
- `zero_fill`: cambiar validación de `idaccount` → `idmember`; fix docstring
- `apply_gating`: cambiar groupby de `(idaccount, idcategory, defaultcategory)` → `(idmember, idcategory, defaultcategory)`

### T4 — `src/smart_budget/model.py`
- `bucket_keys`: cambiar `["idaccount", ...]` → `["idmember", ...]`
- `_null_suggestion`: agregar campo `idmember`, eliminar `idaccount`
- `compute_budget_suggestions`: después de calcular sugerencias, agregar `total_suggested` por miembro
- Actualizar contrato JSON de output

### T5 — `scripts/run_methods.py`
- Output handling: incluir `total_suggested` en el CSV/JSON de salida

### T6 — Dataset sintético expandido
- Re-generar `tests/fixtures/golden_set.csv`: 6 meses, ≥3 `idmember`, 1 cuenta OLB vinculada
- Script en `tests/fixtures/generate_golden_set.py` (o inline en conftest)

### T7 — Tests
- `test_aggregator.py`: corregir tests de `zero_fill` para grain `idmember`
- `test_model.py`: actualizar `test_TC4_8_json_contract_fields`, `bucket_keys`, `_null_suggestion`
- Agregar tests de join dual en `test_idmember_join.py`
- Re-freeze golden set tras cambios

---

## Out of scope

- AC2 (`--category` flag) — ya implementado, no hay cambios
- Multi-moneda (Fase 0)
- Cálculo on-demand desde API
- Modo `--source db` en test de integración (staging Redshift)

---

## Riesgos

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Solo 3 filas en `memberaccount.csv` (dev) | Tests con pocos miembros | Dataset sintético cubre esto en D4 |
| `blossomdoughconsolidatedaccountid` nulo en muchas cuentas | `idmember = null` masivo | Log warning + métricas de cobertura |
| Golden set se rompe intencionalmente | Tests rojos hasta re-freeze | AC esperado; documentado |
| PII: `idmember` en logs | Compliance | Hash SHA-256 + `SB_LOG_SALT` (ya existe) |

---

**Decision: approved by lbetancourth-dev-blossom — 2026-06-01**

All DCR decisions closed, HLTC blocks reviewed. Ready for security + spec generation.
