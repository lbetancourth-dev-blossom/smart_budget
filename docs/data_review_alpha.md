# Revisión de datos — Entorno **ALPHA**

**Fecha:** 2026-05-08
**Autor:** Landneyker (DS-ML)
**Alcance:** Revisión del snapshot del datalake **alpha** disponible en `data/dough/alpha/`.
**Documento padre:** [`data_review.md`](data_review.md) (índice multi-entorno).

---

## 1. Origen del snapshot

```
S3 bucket:    s3://blossom-analytics-datalake-alpha/datalake/{bronze,silver}/DOUGH/
AWS profile:  blossom-dev
Path local:   data/dough/alpha/{bronze,silver}/
```

Confirmación por configuración en datos:

| Componente | URL en `client.csv` / `company.csv` | Entorno |
|---|---|---|
| OLB API | `https://blossom-olb-api-alpha.blossomalpha.com` | alpha |
| Viewer (Clarity) | `https://viewer.clarity.blossombeta.com` | beta |
| Viewer (Wasatch) | `https://viewer.wp.blossombeta.com` | beta |
| Assets dev | `https://devolbassets.static-content.blossomdev.com` | dev |

---

## 2. Diferencias entre capas (alpha)

| Capa | Estado | Filas vs. silver | Columnas vs. silver | Qué contiene |
|---|---|---|---|---|
| **bronze** | Activa (23 tablas) | Iguales en 22/23 tablas; 1 tabla con más filas | **+5 columnas** (`_dms_operation`, `_dms_timestamp`, `_ingested_at`, `_run_id`, `_load_type`) | Stream CDC crudo desde AWS DMS, incluye eventos `insert`/`delete` y metadata. |
| **silver** | Activa (23 tablas) | Estado actual reconciliado | Solo columnas de negocio | Datos limpios, listos para análisis. |
| **gold** | **Vacía** (0 archivos) | — | — | No existe. Smart Budget materializaría aquí. |

**Hallazgos:**
- Bronze ≈ Silver en contenido. La diferencia es estructural (5 columnas DMS) y en una sola tabla por dedup CDC.
- `membertypeaccountorder`: bronze 46 → silver 28. Silver aplica los `delete` del CDC.
- 4 tablas silver retienen `_last_cdc_timestamp` para auditoría: `member`, `membertacacceptance`, `membertypeaccountorder`, `termandcondition`.

> **Para Smart Budget en alpha: usar silver. Bronze añade ruido sin valor para el modelo.**

---

## 3. Volumen del entorno alpha

| Tipo | Conteo |
|---|---|
| Clients | 1 (Blossom) |
| Companies (CUs) | 2 (Clarity CU, Wasatch Peaks CU) |
| Members | 14 |
| Manualaccounts | 1 |
| Manualtransactions | 1 |
| Transacciones reales (Plaid/Finicity) | 0 (la tabla no existe en alpha) |

> Volumen consistente con un entorno de pruebas seedeado, no con tráfico productivo.

---

## 4. Tablas presentes en alpha (silver, 23 tablas)

Agrupadas por dominio funcional:

### 4.1 Multi-tenancy y miembros (5)
- `client` (1) · `company` (2) · `member` (14) · `termandcondition` (3) · `membertacacceptance` (16)

### 4.2 Provider externo (1)
- `provider` (2) — FINICITY activo, PLAID inactivo

### 4.3 Taxonomía de cuentas — global (3)
- `accountclassification` (3) · `defaulttypeaccount` (9) · `defaultaccountsubtype` (19)

### 4.4 Taxonomía de cuentas — por CU (2)
- `companytypeaccount` (18) · `companyaccountsubtype` (38)

### 4.5 Orden custom por miembro (1)
- `membertypeaccountorder` (27)

### 4.6 Cuentas y transacciones manuales (2)
- `manualaccount` (1) · `manualtransaction` (1)

### 4.7 Categorías (3)
- `categorygroup` (4) · `defaultcategory` (29) · `companyntropycategory` (208)

### 4.8 Sistema de diseño (6)
- `colorgroup` (7) · `color` (20) · `icongroup` (9) · `icon` (76) · `iconkeyword` (269) · `iconiconkeyword` (287)

> Diccionario detallado de cada tabla: ver `data_review.md` §3 (común con dev).

---

## 5. ⚠️ Tablas faltantes en alpha (críticas para Smart Budget)

| Tabla esperada | Estado en alpha | Disponibilidad |
|---|---|---|
| `account` | ❌ Ausente | ✅ Presente en **dev** |
| `externaltransaction` | ❌ Ausente | ✅ Presente en **dev** |
| `budget` | ❌ Ausente | ✅ Presente en **dev** |
| `budgetcategory` | ❌ Ausente | ✅ Presente en **dev** |
| `memberaccount` | ❌ Ausente | ✅ Presente en **dev** |
| `memberproviderlink` | ❌ Ausente | ✅ Presente en **dev** |
| `period` | ❌ Ausente | ✅ Presente en **dev** |
| `transactionSplit` (PRD) | ❌ Ausente | ⚠️ Tampoco en dev (existe `issplit` flag, no tabla separada) |
| `userCategoryTransaction` (PRD) | ❌ Ausente | ⚠️ Tampoco en dev |
| `category` (custom user) | ❌ Ausente — solo `defaultcategory` | ⚠️ Tampoco en dev |

### Implicaciones para alpha

- **No se puede calcular Smart Budget en alpha** — falta toda la capa transaccional.
- Sí sirve para validar:
  - Catálogo global de categorías (`defaultcategory + categorygroup`).
  - Mapping Ntropy → canónica (`companyntropycategory`).
  - Multi-tenancy (`client → company → member`).
  - Compliance (T&C aceptados antes de servir).
- **Acción:** para iterar el modelo, pivotar a **dev** mientras Data Engineering replica las tablas transaccionales a alpha (ver `data_review_dev.md`).

---

## 6. Comandos para refrescar el snapshot de alpha

```bash
python scripts/extract_dough_to_csv.py --env alpha
```

El script lee de `s3://blossom-analytics-datalake-alpha/datalake/{bronze,silver}/DOUGH/` con perfil `blossom-dev` y escribe a `data/dough/alpha/{bronze,silver}/`.

---

## 7. Próximos pasos para alpha

1. Solicitar a Data Engineering la replicación de tablas transaccionales (`account`, `externaltransaction`, `budget`, `budgetcategory`, `memberaccount`, `memberproviderlink`, `period`) al lake alpha — coherente con lo ya disponible en dev.
2. Confirmar si `transactionSplit`, `userCategoryTransaction` y `category` (custom) existen en la BD operativa o si se manejan via flags (`issplit`).
3. Mantener alpha como entorno de validación final una vez completo el pipeline en dev.
