# Plan — DATA-1139
**DS - Tests de resultados: Extraer datasets de test por fuente (internal / external)**

- **Fecha:** 2026-05-15
- **Riesgo:** medium
- **Estimación:** S (~5h)
- **Método de merge:** Squash and merge → `development`

---

## Problema

`fact_transactions.csv` mezcla transacciones internas OLB (SUB/LOAN) con transacciones externas
DOUGH (EXT/Plaid-Finicity). Para evaluar si el modelo se comporta diferente según la fuente de
datos, necesitamos dos datasets filtrados y separados: `test_internal.csv` y `test_external.csv`.
Ambos aplican las mismas 5 reglas de filtrado del pipeline principal.

**N de miembros:** todos los disponibles post-filtro (sin sampling — población completa).

---

## Decisiones — DCR

| ID | Dimensión | Decisión | Evidencia |
|----|-----------|----------|-----------|
| A1 | Input | `data/dough/fact_transactions.csv` (CLI arg `--input`, default a este path) | `run_smart_budget_prep.py` línea 8 |
| A2 | Filtrado | Usar `filter_transactions()` de `src/smart_budget/filters.py` tal como está | `filters.py` línea 6 — sin reimplementar |
| A3 | Split por fuente | Prefijo de `idtransaction`: `SUB*/LOAN*` → internal; `EXT*` → external; otros → log warning + skip | `filters.py` líneas 43-44 — mismos prefijos |
| A4 | Muestra | Todos los miembros disponibles post-filtro (N = total, sin sampling) | Decisión del equipo DS |
| A5 | Schema output | Mismas columnas que `fact_transactions.csv` (CANONICAL_COLS) — subset filtrado y partido por fuente | `build_fact_transactions.py` líneas 391-410 |
| A6 | Escritura | Atomic write: `tmp → os.replace → chmod 600` en `data/dough/test/` | `run_smart_budget_prep.py` líneas 189-192 |
| A7 | Error — input no existe | Fail fast con `sys.exit(1)` + mensaje con instrucción | `extract_datalake_to_csv.py` línea 251 |
| A8 | Error — fuente vacía post-filtro | Log warning + escribir CSV vacío (0 filas) + continuar (no abortar) | `build_fact_transactions.py` línea 78-80 |
| A9 | Logging | structlog: `job_start`, `filter_applied`, `split_complete`, `write_complete` × 2, `job_done` | Patrón global del repo |
| A10 | PII en logs | Solo contar filas y miembros — nunca loguear IDs individuales ni montos | CLAUDE.md §Security |
| A11 | Gitignore | `data/dough/test/` cubierto por regla `data/` existente — sin nueva entrada | `.gitignore` línea 1 |
| A12 | Idempotencia | Re-ejecución sobrescribe (atomic write) — sin duplicados | Diseño por defecto |

**Decisiones humanas:** 0 (todas cerradas por evidencia en código)

---

## HLTC — Arquitectura delta

### Bloques auto-aceptados

- Nuevo script `scripts/extract_test_datasets.py` — sigue patrón de `run_smart_budget_prep.py` exactamente
- Nuevos tests `tests/unit/test_extract_test_datasets.py` — sigue patrón de `test_eval_runner.py`
- Nuevo directorio de output `data/dough/test/` — cubierto por `.gitignore`, `mkdir -p` en runtime

### Bloques revisados

| ID | Bloque | Decisión |
|----|--------|----------|
| HLTC-1 | PII data at rest en `test_internal.csv` / `test_external.csv` | **Aceptado** — misma protección que `fact_transactions.csv` (gitignored + chmod 600). Sin nueva superficie de riesgo. |

---

## Diseño técnico

### Script: `scripts/extract_test_datasets.py`

```
CLI args:
  --input      PATH   (default: data/dough/fact_transactions.csv)
  --output-dir PATH   (default: data/dough/test/)

Flujo:
  1. Validar que --input existe → sys.exit(1) si no
  2. Cargar CSV con pd.read_csv(), normalizar columnas a lowercase
  3. Validar REQUIRED_COLUMNS presentes (mismas que run_smart_budget_prep.py)
  4. Aplicar filter_transactions(df)
  5. Split:
       mask_internal = df["idtransaction"].str.startswith(("SUB", "LOAN"))
       mask_external = df["idtransaction"].str.startswith("EXT")
       mask_unknown  = ~(mask_internal | mask_external)
  6. Si mask_unknown.any() → log warning con count
  7. Atomic write test_internal.csv  (df[mask_internal])
  8. Atomic write test_external.csv  (df[mask_external])
  9. Log job_done: n_internal_rows, n_external_rows, n_unknown_skipped,
                   n_internal_members, n_external_members
```

### Atomic write helper (inline, no nueva función pública):
```python
def _write_atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = str(path) + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, str(path))
    os.chmod(str(path), 0o600)
```

### Tests: `tests/unit/test_extract_test_datasets.py`

| ID | Caso | Fixture |
|----|------|---------|
| TC-1 | Rows con prefijo SUB van a internal, EXT a external | 3 SUB + 2 EXT rows |
| TC-2 | Rows con prefijo LOAN van a internal | 2 LOAN rows |
| TC-3 | Miembro con txns OLB y EXT aparece en ambos CSVs | 1 account con SUB + EXT |
| TC-4 | Prefijo desconocido (XYZ) excluido de ambos CSVs | 1 XYZ row |
| TC-5 | filter_transactions() aplicado: status PENDING OLB excluido | SUB row con status=PENDING |
| TC-6 | Source vacía post-filtro: CSV de 0 filas escrito, no excepción | solo SUB rows, ningún EXT |
| TC-7 | Script importable y parse de args correcto | import + argparse |

---

## Archivos a crear/modificar

| Archivo | Operación |
|---------|-----------|
| `scripts/extract_test_datasets.py` | **CREAR** |
| `tests/unit/test_extract_test_datasets.py` | **CREAR** |
| `data/dough/test/` | Directorio — creado en runtime por script (gitignored) |

Sin cambios a archivos existentes.

---

## Criterios de aceptación (actualizados)

1. ✅ Criterios de selección de miembros documentados: todos los miembros post-filtro (población completa)
2. ✅ `test_internal.csv` generado: transacciones OLB (SUB + LOAN) post-`filter_transactions()`
3. ✅ `test_external.csv` generado: transacciones EXT (Plaid/Finicity) post-`filter_transactions()`
4. ✅ Ambos archivos escritos atómicamente en `data/dough/test/` con chmod 600
5. ✅ Tests unitarios pasan sin S3 ni fixtures reales
6. ✅ Script reutilizable como `--input` para `eval_runner.py`

---

---

**Decision: approved by lbetancourth-dev-blossom — 2026-05-15**

All DCR decisions closed, HLTC blocks reviewed. Ready for security + spec generation.

---

## Fuera de scope

- ❌ Aggregation (smart_budget_prep) de los datasets de test — eso es un paso separado
- ❌ Sampling de N miembros — usar población completa
- ❌ Conexión a S3 en runtime — el script lee del CSV local generado por build_fact_transactions.py
- ❌ Modificar eval_runner.py o el pipeline existente
