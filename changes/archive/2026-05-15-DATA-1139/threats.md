# Threat Analysis — DATA-1139

**Overall risk level: Medium**
**Gate: ninguno — proceder a /execute**
**Date:** 2026-05-15
**Reviewer:** blossom-security (automated)

---

## Resumen ejecutivo

Sin nueva superficie de red, sin autenticación, sin secretos. El riesgo se concentra en
**scope de datos y ciclo de vida**: los outputs contienen datos transaccionales reales de miembros
(todos los CUs del CSV fuente). Tres items deben resolverse en la spec antes de ejecutar:

1. **Scope de columnas (A5):** plan dice "32 CANONICAL_COLS" pero eval_runner necesita solo 6-8.
   Reducir a columnas necesarias (data minimization) o documentar justificación.
2. **`_write_atomic` race condition:** usar suffix con PID (`f"{path}.{os.getpid()}.tmp"`) no fijo.
3. **chmod en `.tmp`:** aplicar `0o600` al `.tmp` ANTES de `os.replace`, no solo al destino final.

---

## Por categoría

| # | Categoría | Nivel | Notas |
|---|-----------|-------|-------|
| 1 | Authentication | Low | CLI local, sin red, sin tokens |
| 2 | Authorization | Medium | Output scope = todos los CUs del CSV fuente |
| 3 | PII/PAN/CVV | Medium | `description`+`note`+`balance`+`enrichment` en CANONICAL_COLS |
| 4 | Trust boundary | Low | Local filesystem only; warning si `--output-dir` fuera de `data/` |
| 5 | Persistence | Medium | Sin retention policy para test CSVs |
| 6 | Audit trail | Low | Logging plan correcto (A9/A10) |
| 7 | Idempotency | Low | Race condition menor en `.tmp` con nombre fijo |
| 8 | Secrets | Low | Sin credenciales en runtime |
| 9 | Rate limiting | Low | N/A — CLI local |
| 10 | BSA/AML | Low | Sin lógica de monitoring, sin artifacts de compliance |

---

## Controles obligatorios para la implementación

- [ ] **Columnas output:** emitir solo las necesarias para eval_runner:
      `idtransaction, idclient, idcompany, idaccount, defaultcategory, incomeexpenditure, amount, date, status, deletedat`
      (o documentar en spec por qué se incluyen `description`, `note`, `balance`, `enrichment`)
- [ ] **`_write_atomic` tmp suffix:** `f"{path}.{os.getpid()}.tmp"` — no el fijo `path + ".tmp"`
- [ ] **chmod en tmp ANTES de replace:** `os.chmod(tmp_path, 0o600)` antes de `os.replace()`
- [ ] **`--output-dir` warning:** log `WARNING` si path no está bajo `data/` del repo
- [ ] **Logs sin contenido de fila:** nunca loguear `idaccount`, `amount`, `description` individuales
- [ ] **Fixtures sintéticas en tests:** sin CSVs derivados de `data/dough/` real
- [ ] **Confirmar gitignore:** `git status` no debe mostrar ningún `.csv` tras correr el script
- [ ] **Sin `print()`:** todo output via `structlog`

---

## Recomendaciones para el spec

1. Resolver scope de columnas explícitamente (preferir data minimization)
2. Agregar log `INFO` de lifecycle reminder: `"These files contain real member data. Delete before offboarding."`
3. Especificar modo de creación del `.tmp` (`0o600` desde el inicio)
4. Aclarar validación de `--output-dir`
5. Agregar TC-8: verificar que el archivo final tenga permisos `0o600`

---

## Compliance

- **NCUA:** sin operaciones reportables. Si se corre en staging con datos reales, inventariar copies.
- **BSA/AML:** no aplica — sin transaction monitoring ni SAR/CTR.
- **PCI DSS:** no aplica — sin PAN/CVV en el schema.
