# Spec — DATA-1179: DS - Smart Budget Dataset & Model Changes

**Ticket:** https://blossomtechnology.atlassian.net/browse/DATA-1179  
**Plan aprobado:** `changes/DATA-1179/plan.md` — 2026-06-01  
**Branch:** `feat/DATA-1179`

---

## T1 — Agregar `idmember` a `build_fact_transactions.py`

**Archivo:** `scripts/build_fact_transactions.py`

**Descripción:**  
Agregar columna `idmember` via join dual en ambos modos (`--source s3` y `--source db`).
- **EXT**: strip `"EXT"` del `idaccount` → buscar en `memberaccount.idaccount` → obtener `memberaccount.idmember`
- **OLB** (`SUB...`, `INT...`): buscar `fact_transactions.idaccount` en `account.blossomdoughconsolidatedaccountid` → obtener `account.id` → buscar en `memberaccount.idaccount` → obtener `idmember`
- Cuentas sin match → `idmember = None`, log structlog warning
- Agregar `idmember` a `CANONICAL_COLS` (posición: después de `idcompany`)

**Test contracts:**

```python
# tests/unit/test_build_fact_transactions_idmember.py

# TC-T1-1: EXT account resuelve idmember
# Arrange: fact con idaccount="EXT2", memberaccount con idaccount=2, idmember=10
# Act: _resolve_idmember(fact, memberaccount, account)
# Assert: fact["idmember"].iloc[0] == 10

# TC-T1-2: OLB account resuelve idmember via blossomdoughconsolidatedaccountid
# Arrange: fact con idaccount="SUB8406", account con blossomdoughconsolidatedaccountid="SUB8406" y id=50,
#          memberaccount con idaccount=50, idmember=20
# Act: _resolve_idmember(fact, memberaccount, account)
# Assert: fact["idmember"].iloc[0] == 20

# TC-T1-3: Cuenta sin match → idmember es None/NaN
# Arrange: fact con idaccount="SUB9999" sin match en account ni memberaccount
# Act: _resolve_idmember(fact, memberaccount, account)
# Assert: pd.isna(fact["idmember"].iloc[0])

# TC-T1-4: idmember en CANONICAL_COLS y en output CSV
# Arrange: pipeline completo con datos sintéticos (EXT + 1 OLB)
# Act: build pipeline → save_outputs
# Assert: "idmember" in df.columns

# TC-T1-5: EXT strip con valor no-numérico → idmember = None, warning logged
# Arrange: fact con idaccount = "EXTABC" (no-numérico tras strip)
# Act: _resolve_idmember(...)
# Assert: pd.isna(row["idmember"]) AND structlog captured "invalid_ext_account"

# TC-T1-6: --source db usa queries parametrizadas (no concatenación de strings SQL)
# Arrange: mock de conexión DB que registra queries ejecutadas
# Act: build_fact_transactions pipeline --source db
# Assert: ningún string de JOIN contiene el valor de blossomdoughconsolidatedaccountid literal
```

---

## T2 — Actualizar `run_smart_budget_prep.py`

**Archivo:** `scripts/run_smart_budget_prep.py`

**Descripción:**  
- Agregar `"idmember"` a `REQUIRED_COLUMNS` con modo warning (no error fatal si falta — backward compat)
- Si `idmember` no está en el dataset: log structlog warning `"idmember column missing — suggestions will not be grouped by member"`
- Pass-through `idmember` al output sin modificación

**Test contracts:**

```python
# tests/unit/test_prep_idmember.py

# TC-T2-1: Dataset con idmember pasa validación
# Arrange: df con todas REQUIRED_COLUMNS incluyendo idmember
# Act: prep pipeline
# Assert: sin warnings de idmember, idmember en output

# TC-T2-2: Dataset sin idmember emite warning pero no falla
# Arrange: df sin columna idmember
# Act: prep pipeline
# Assert: log contiene "idmember column missing", pipeline completa sin excepción
```

---

## T3 — Actualizar `aggregator.py`

**Archivo:** `src/smart_budget/aggregator.py`

**Descripción:**

1. **`aggregate_monthly`**: agregar `idmember` al groupby:
   ```python
   group_keys = ["idclient", "idcompany", "idmember", "idaccount", "idcategory", "defaultcategory", "period_yyyymm"]
   ```
   Nota: `idaccount` se mantiene en el groupby de `aggregate_monthly` para preservar granularidad; el cambio de grain a `idmember` ocurre en `apply_gating` y `model.py`.

2. **`zero_fill`**: 
   - Cambiar validación de `idaccount` → `idmember`
   - Cambiar docstring: "each idmember must map to exactly one (idclient, idcompany) pair"
   - Preservar `idmember` en el full_grid (agregar a `member_cat`)

3. **`apply_gating`**: cambiar groupby de `(idaccount, idcategory, defaultcategory)` → `(idclient, idcompany, idmember, idcategory, defaultcategory)`  
   ⚠️ **Seguridad [AUTH-2]:** `idclient` e `idcompany` DEBEN incluirse para evitar cross-tenant mixing cuando hay miembros con mismo `idmember` en distintas CUs.

4. **`prepare_smart_budget_data`**: agregar `"idmember"` a `output_cols` (después de `"idcompany"`):
   ```python
   output_cols = [
       "idclient", "idcompany", "idmember", "idcategory", "defaultcategory",
       "period_yyyymm", "monthly_total",
   ]
   ```
   También actualizar docstring para incluir `idmember` en la lista de columnas retornadas.
   Nota: `idaccount` se elimina de `output_cols` aquí — el grain del modelo es `idmember`. Las filas con `idmember` nulo deben ser eliminadas en `prepare_smart_budget_data` con un log structlog warning antes de retornar.

**Test contracts:**

```python
# tests/unit/test_aggregator.py  (actualizar tests existentes)

# TC-T3-1: aggregate_monthly incluye idmember en output
# Arrange: df con idmember=10, idaccount="EXT2", 2 transacciones
# Act: aggregate_monthly(df)
# Assert: "idmember" in result.columns
# Assert: result["idmember"].iloc[0] == 10

# TC-T3-2: zero_fill valida idmember (no idaccount)
# Arrange: df donde idmember=10 tiene idclient=1 en algunos rows e idclient=2 en otros
# Act: zero_fill(df)
# Assert: raises ValueError con "idmember maps to multiple"

# TC-T3-3: zero_fill preserva idmember en grid expandido
# Arrange: df con 2 idmember, 2 categorías, 3 meses (algunos vacíos)
# Act: zero_fill(df)
# Assert: "idmember" in result.columns
# Assert: len(result) == 2 * 2 * 3  (miembros × categorías × meses)

# TC-T3-4: apply_gating agrupa por (idclient, idcompany, idmember) — no idaccount
# Arrange: idmember=10, idcompany=1 con 2 cuentas (EXT2, SUB8406), ambas con 3 meses de gasto en misma categoría
# Act: apply_gating(df, min_months=2)
# Assert: resultado tiene 1 fila por (idclient, idcompany, idmember, category), no 2

# TC-T3-5: apply_gating NO mezcla idmember=10 de idcompany=1 con idmember=10 de idcompany=2
# Arrange: df con idmember=10/idcompany=1 (4 meses) + idmember=10/idcompany=2 (1 mes)
# Act: apply_gating(df, min_months=2)
# Assert: solo idmember=10/idcompany=1 pasa gating; idmember=10/idcompany=2 excluido
```

---

## T4 — Actualizar `model.py`

**Archivo:** `src/smart_budget/model.py`

**Descripción:**

1. **`bucket_keys`**: cambiar de `["idaccount", "idcategory", "defaultcategory"]` → `["idmember", "idcategory", "defaultcategory"]`

2. **`_null_suggestion`**:
   - Eliminar campo `"idaccount"`
   - Agregar campo `"idmember"`

3. **`compute_budget_suggestions`** — output JSON:
   - Eliminar `"idaccount"` del dict resultado
   - Agregar `"idmember"` al dict resultado
   -    Antes del paso de `total_suggested`, agregar **SUM de `monthly_total` por `(idclient, idcompany, idmember, idcategory, defaultcategory, period_yyyymm)`** para colapsar múltiples cuentas de un mismo miembro. Un miembro con 2 cuentas ($200 + $150 en GROCERIES el mismo mes) → `monthly_total = 350` antes de entrar al método de estimación.

5. `compute_budget_suggestions` groupby para `total_suggested`: usar `(idclient, idcompany, idmember)` — nunca `idmember` solo.

6. `total_suggested` cuando todas las categorías son nulas → **`0.0`** (no `None`). Decisión de producto: mostrar $0 en UI, nunca ocultar el widget por falta de historial.

4. **Output final `compute_budget_suggestions`**: cambiar de `list[dict]` (plano) a dict con estructura:
   ```python
   {
       idmember: {
           "idmember": str,
           "period_id": str,
           "idclient": str,
           "idcompany": str,
           "total_suggested": float,  # suma de suggested_amount no nulos
           "suggestions": list[dict]  # por categoría
       }
   }
   ```
   O mantener lista plana y agregar `total_suggested` como campo de cada elemento — **elegir: mantener lista plana, agregar `total_suggested` como campo a nivel de idmember en un paso post-proceso.**

   **Decisión de implementación:** retornar `list[dict]` donde cada dict tiene todos los campos de categoría + `idmember` + `total_suggested` del miembro calculado al final. Así es backward-compatible con `run_methods.py`.

**Test contracts:**

```python
# tests/unit/test_model.py  (actualizar + nuevos)

# TC-T4-1: _null_suggestion contiene idmember (no idaccount)
# Arrange: bucket_meta con idmember="10", idcategory="cat1", etc.
# Act: _null_suggestion(bucket_meta)
# Assert: "idmember" in result
# Assert: "idaccount" not in result
# Assert: result["idmember"] == "10"

# TC-T4-2 (actualizar TC4_8): contrato JSON de output
# required_fields = {
#     "category_id", "defaultcategory", "idmember", "idclient", "idcompany",
#     "suggested_amount", "basis", "confidence", "display_label", "explanation",
#     "model_version", "total_suggested"
# }
# Assert: "idaccount" NOT in result keys
# Assert: "idmember" in result keys
# Assert: "total_suggested" in result keys

# TC-T4-3: total_suggested es suma de suggested_amount no nulos del idmember
# Arrange: idmember=10, 3 categorías con suggested_amount=[100.0, 50.0, None]
# Act: compute_budget_suggestions(df, ...)
# Assert: results[0]["total_suggested"] == 150.0
# Assert: results[1]["total_suggested"] == 150.0  (mismo idmember)
# Assert: results[2]["total_suggested"] == 150.0  (el nulo no suma)

# TC-T4-4: total_suggested == 0.0 (no None) cuando todas las categorías son nulas
# Arrange: miembro con 1 sola categoría y < 2 meses → suggested_amount = null
# Act: compute_budget_suggestions(df, ...)
# Assert: result["total_suggested"] == 0.0  (float, nunca None)# Arrange: idmember=10, todas las categorías sin historial suficiente
# Act: compute_budget_suggestions(df, ...)
# Assert: result["total_suggested"] == 0.0  (o None — aclarar en impl)

# TC-T4-5: dos idmember distintos tienen total_suggested independientes
# Arrange: idmember=10 con suggested=200, idmember=20 con suggested=300
# Act: compute_budget_suggestions(df, ...)
# Assert: resultados de member 10 tienen total_suggested == 200
# Assert: resultados de member 20 tienen total_suggested == 300
```

---

## T5 — Actualizar `run_methods.py`

**Archivo:** `scripts/run_methods.py`

**Descripción:**
- Actualizar output CSV/JSON para incluir `idmember` y `total_suggested`
- Eliminar `idaccount` del output (o mantenerlo como campo opcional para debug)
- Si `idmember` no está en el resultado, loguear warning

**Test contracts:**

```python
# tests/unit/test_run_methods_output.py

# TC-T5-1: output CSV contiene idmember y total_suggested
# Arrange: run pipeline completo con datos sintéticos que tienen idmember
# Act: correr run_methods
# Assert: "idmember" in output_df.columns
# Assert: "total_suggested" in output_df.columns
```

---

## T6 — Expandir dataset sintético

**Archivos:** `tests/fixtures/golden_set.csv`, `tests/fixtures/generate_golden_set.py` (crear)

**Descripción:**
- 6 meses: `2025-10` a `2026-03`
- ≥3 `idmember`: member 10, 20, 30
  - member 10: cuenta EXT (idaccount="EXT2")
  - member 20: cuenta EXT (idaccount="EXT22") + cuenta OLB vinculada (SUB8406 via blossomdoughconsolidatedaccountid)
  - member 30: cuenta EXT nueva (idaccount="EXT33") — sin datos en algunas categorías para testear gating
- ≥3 categorías por miembro
- Datos sintéticos determinísticos (sin random_state inconsistente)
- Re-freeze golden_set.csv con los nuevos valores esperados (WMA/A/2026-03)

**Test contracts:**

```python
# tests/unit/test_golden_set.py  (actualizar TC4_golden_set_matches_output)

# TC-T6-1: golden_set.csv tiene columna idmember
# Arrange: leer golden_set.csv
# Assert: "idmember" in df.columns

# TC-T6-2: golden_set.csv tiene al menos 3 idmember distintos
# Assert: df["idmember"].nunique() >= 3

# TC-T6-3: golden_set.csv tiene 6 periodos distintos
# Assert: df["period_yyyymm"].nunique() == 6

# TC-T6-4 (actualizado): WMA/A/2026-03 output matches golden_set.csv exactamente
# Misma lógica que TC4_golden_set_matches_output pero con nuevo schema
```

---

## T7 — Tests de multi-tenancy e `idmember`

**Archivo:** `tests/unit/test_multitenancy.py` (actualizar)

**Descripción:**
- Verificar que no hay cross-member leak en `compute_budget_suggestions`
- Verificar que `total_suggested` no mezcla miembros

**Test contracts:**

```python
# TC-T7-1: no cross-member leak en total_suggested
# Arrange: 2 idmember con misma categoría, amounts distintos
# Act: compute_budget_suggestions
# Assert: member A no ve datos de member B en total_suggested

# TC-T7-2: no cross-company leak — idmember mismo entero, distinta idcompany
# Arrange: idmember=10, idcompany=1 (4 meses) + idmember=10, idcompany=2 (1 mes)
# Act: compute_budget_suggestions(df, ...)
# Assert: raises ValueError("Cross-company idmember collision detected")
#         O: resultados separados con idcompany=1 (pasa gating) != idcompany=2 (no pasa)
#         Elegir: raises — es el contrato seguro. El ValueError debe propagarse al caller.

# TC-T7-3: pipeline emite audit log estructurado al finalizar batch
# Arrange: corrida completa con 2 miembros
# Act: run_methods.py --method wma --period 2026-05
# Assert: structlog captura evento con campos: job_id, model_version, n_members_processed,
#         n_null_idmember, started_at, finished_at
```

---

## Archivos impactados

| Archivo | Tipo de cambio |
|---------|---------------|
| `scripts/build_fact_transactions.py` | Agregar join dual para `idmember`, `CANONICAL_COLS` |
| `scripts/run_smart_budget_prep.py` | Agregar `idmember` a `REQUIRED_COLUMNS` |
| `src/smart_budget/aggregator.py` | `aggregate_monthly`, `zero_fill`, `apply_gating` |
| `src/smart_budget/model.py` | `bucket_keys`, `_null_suggestion`, `compute_budget_suggestions` |
| `scripts/run_methods.py` | Output con `idmember` + `total_suggested` |
| `tests/fixtures/golden_set.csv` | Re-freeze con nuevo schema |
| `tests/fixtures/generate_golden_set.py` | Crear script generador |
| `tests/unit/test_build_fact_transactions_idmember.py` | Crear |
| `tests/unit/test_prep_idmember.py` | Crear |
| `tests/unit/test_aggregator.py` | Actualizar TC-T3-1 a T3-4 |
| `tests/unit/test_model.py` | Actualizar TC4_8 + agregar T4-1 a T4-5 |
| `tests/unit/test_multitenancy.py` | **Crear** (no existe) — T7-1, T7-2, T7-3 |

---

## Orden de ejecución (TDD)

1. **T1** — `_resolve_idmember` helper + tests (base para todo lo demás)
2. **T3** — `aggregator.py` (depende de que `idmember` exista en el df)
3. **T4** — `model.py` (depende de T3)
4. **T2** — `run_smart_budget_prep.py` (validación de columna)
5. **T5** — `run_methods.py` output
6. **T6** — Golden set + re-freeze
7. **T7** — Tests de multi-tenancy

---

## Notas de implementación

- **Backward compat**: `idaccount` se puede mantener en `fact_transactions` (para trazabilidad), pero NO en el output de `compute_budget_suggestions`. El modelo opera en grain `idmember`.
- **`total_suggested`**: si un miembro tiene 0 sugerencias no-nulas → `total_suggested = 0.0` (no null).
- **PII**: `idmember` en logs siempre hasheado con SHA-256 + `SB_LOG_SALT`.
- **Golden set re-freeze**: es un cambio intencional de contrato — los tests de golden set quedarán en rojo hasta que se re-freeze con `python tests/fixtures/generate_golden_set.py`.
