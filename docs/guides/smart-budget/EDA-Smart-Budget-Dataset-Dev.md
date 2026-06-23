# EDA — Smart Budget Dataset DEV (blossom-dough-consolidated-dev)

> ⚠️ HISTÓRICO: Este EDA documenta el dataset extraído de PostgreSQL (blossom-dough-consolidated-dev).
> Post-DATA-1275, los datos se consultan en tiempo real desde Athena (dlh_gold_dough_dev.smart_budget_transactions).
> Este documento se conserva como referencia histórica y para entender la evolución del schema.

> Exploración del dataset extraído directamente de la DB de desarrollo (dev).
> Origen: `scripts/extract_smart_budget_monthly.py` + query `smart_budget_monthly_spend.sql`.
> Archivo: `data/smart_budget_db_dev.csv`
>
> Ver también: [EDA Alpha](./EDA-Smart-Budget-Dataset.md) — dataset de referencia con mayor cobertura.

---

## 1. Origen y método de extracción

| Campo | Valor |
|---|---|
| **Base de datos** | `blossom-dough-consolidated-dev` |
| **Schema** | `public` |
| **Tabla fuente** | `fact_transactions` |
| **Tabla bridge** | `bridge_member_account` (resuelve `idaccount → idmember`) |
| **Grain de salida** | `(idmember, defaultcategory, period_yyyymm)` |
| **Filtros aplicados** | 6 reglas Smart Budget (ver `filters.py`) |
| **Agregación** | `GREATEST(0, SUM(ABS(amount)))` por mes |

La query completa está en `src/smart_budget/queries/smart_budget_monthly_spend.sql`.

---

## 2. Dimensiones del dataset

| Métrica | Valor |
|---|---|
| **Total de filas** | 26,417 |
| **Columnas** | 8 |
| **Valores nulos** | 0 (en todas las columnas) |
| **Valores negativos en monthly_total** | 0 (clamp por GREATEST) |
| **Valores cero en monthly_total** | 0 |

---

## 3. Descripción de columnas

| Columna | Tipo | Descripción | Notas |
|---|---|---|---|
| `idclient` | int | ID del cliente Blossom (siempre `1` en esta DB) | Multi-tenancy layer 1 |
| `idcompany` | int | ID de la Credit Union | 3 CUs en dev: `1`, `2`, `2050` |
| `idmember` | string | ID del miembro (usuario) | 421 miembros únicos |
| `idaccount` | string | ID de la cuenta | Solo prefijo `INT` (OLB). Ej: `INT24`, `INT791` |
| `idcategory` | string | Identificador de categoría | ⚠️ Igual al nombre (`defaultcategory`). Sin ID numérico disponible en `fact_transactions` dev. |
| `defaultcategory` | string | Nombre de la categoría de gasto | 10 categorías únicas |
| `period_yyyymm` | string | Mes calendario del gasto (formato `YYYY-MM`) | Rango 2022-09 → 2026-05 |
| `monthly_total` | float | Gasto neto mensual en USD | Positivo siempre; clampeo a 0 si neto negativo |

### Nota sobre `idcategory`
Igual que en alpha: `idcategory` = `defaultcategory` (nombre). No hay catálogo numérico disponible en esta DB.

---

## 4. Miembros (idmember)

| Métrica | Valor |
|---|---|
| **Miembros únicos** | 421 |
| **Filas por miembro (mediana)** | 34 |
| **Filas por miembro (media)** | 63 |
| **Filas por miembro (máx)** | 403 |
| **Meses con data por miembro (mediana)** | 33 |
| **Meses con data por miembro (media)** | 26 |
| **Categorías por miembro (mediana)** | 1 |
| **Categorías por miembro (media)** | 1.9 |
| **Categorías por miembro (máx)** | 6 |

**Observación:** Los miembros de dev tienen en promedio más meses de historial (mediana 33 vs 15 en alpha), pero menos categorías por miembro (máx 6 vs 12 en alpha). Son datos más "limpios" y representativos del flujo OLB puro.

---

## 5. Categorías (defaultcategory)

10 categorías únicas (2 menos que alpha). La categoría `Other` domina con ~97% de las filas.

| Categoría | Filas | % del total | Mediana monthly_total |
|---|---|---|---|
| Other | 25,749 | 97.5% | $5,352 |
| Taxes & fees | 143 | 0.5% | $40 |
| Transfers & payments | 141 | 0.5% | $2 |
| Groceries | 124 | 0.5% | $23 |
| Gas | 96 | 0.4% | $23 |
| Shopping | 90 | 0.3% | $20 |
| Home & rent | 39 | 0.1% | $3 |
| Bills & utilities | 13 | 0.05% | $10 |
| Auto & transport | 12 | 0.05% | $40 |
| Entertainment & leisure | 10 | 0.04% | $1 |

**Ausentes vs alpha:** `Food & dining` y `Travel & trips` no tienen datos en dev.

**Observación:** `Other` es aún más dominante que en alpha (97.5% vs 93.6%). El entorno dev refleja CUs sin enriquecimiento Ntropy activo — casi toda la actividad categorizada es OLB nativo.

---

## 6. Periodos (period_yyyymm)

| Métrica | Valor |
|---|---|
| **Periodos únicos** | 45 |
| **Inicio de datos** | 2022-09 |
| **Fin de datos** | 2026-05 |
| **Rango con datos estables** | 2023-01 → 2026-02 |

**Distribución por periodo:**

```
2022-09:   92 filas  ← inicio, datos parciales
2022-10:  268 filas  ← rampa de carga
2023-01:  359 filas
2023-06:  812 filas  ← peak histórico
2024-03:  802 filas
2025-04:  571 filas  ← caída hacia 2025
2025-08:  765 filas
2026-01:  610 filas
2026-03:   79 filas  ← caída abrupta (datos incompletos)
2026-04:  235 filas
2026-05:   74 filas  ← mes más reciente, muy incompleto
```

**Recomendación para el modelo:** Los periodos `2026-03`, `2026-04` y `2026-05` muestran caídas abruptas — posiblemente datos incompletos en dev. Usar con precaución en la ventana de lookback. El rango confiable es **2022-10 → 2026-02**.

---

## 7. Montos (monthly_total)

Todos los valores son positivos (clamp `GREATEST(0, ...)` funcionó correctamente).

| Estadístico | Valor |
|---|---|
| **Mínimo** | $0.77 |
| **P25** | $1,452 |
| **Mediana (P50)** | $5,040 |
| **Media** | $1,575,419 |
| **P75** | $53,184 |
| **P90** | $607,128 |
| **P95** | $1,790,120 |
| **P99** | $25,486,230 |
| **Máximo** | $507,610,600 |

**Observación:** La media ($1.57M) está completamente distorsionada por `Other` — valores máximos de hasta $507M corresponden a transacciones de nómina/ACH masivas de CUs que procesan pagos corporativos. La **mediana ($5,040)** es la única estadística representativa del gasto real de un miembro individual.

---

## 8. Credit Unions (idcompany)

Solo 3 CUs en dev (vs 18 en alpha).

| idcompany | Filas | % |
|---|---|---|
| 1 | 25,347 | 95.9% |
| 2050 | 995 | 3.8% |
| 2 | 75 | 0.3% |

**Observación:** Dev es un entorno muy limitado en diversidad de CUs. No es representativo del comportamiento multi-tenant de producción. Alpha es más adecuado para pruebas de cobertura.

---

## 9. Prefijos de idaccount

| Prefijo | Filas | % | Origen |
|---|---|---|---|
| `INT` | 26,417 | 100% | OLB (Core Banking) |

Igual que en alpha: **solo cuentas OLB** (`INT`). Sin cuentas externas `EXT` (Plaid/Finicity). Todos los `expenditure` son negativos en la DB — `ABS()` es obligatorio en la query.

---

## 10. Comparación dev vs alpha

| Métrica | DEV | ALPHA |
|---|---|---|
| Total filas | 26,417 | 195,923 |
| Miembros únicos | 421 | 2,929 |
| Categorías únicas | 10 | 12 |
| Periodos únicos | 45 | 40 |
| Inicio de datos | 2022-09 | 2019-06 |
| CUs (idcompany) | 3 | 18 |
| Mediana monthly_total | $5,040 | $3,782 |
| Prefijos idaccount | INT | INT |
| % filas en "Other" | 97.5% | 93.6% |
| Categorías ausentes | Food & dining, Travel & trips | — |

**Conclusión:** Dev es útil para pruebas de pipeline y endpoint, pero **alpha es la fuente de referencia** para validar el modelo Smart Budget por su mayor diversidad de CUs, categorías y miembros.

---

## 11. Consideraciones para el modelo Smart Budget

| Hallazgo | Impacto |
|---|---|
| 97.5% de filas en `Other` | Aún más concentrado que alpha — mayoría de miembros solo recibirán sugerencia en `Other` |
| 33 meses de historial (mediana) | El gating de 2 meses mínimo pasará para casi todos los miembros en dev |
| Máx 6 categorías por miembro | Cobertura muy baja — dev no es ideal para probar diversidad de sugerencias |
| 2026-03/04/05 incompletos | Excluir del cálculo o usar con ventana anterior a 2026-03 |
| Solo 3 CUs | No probar multi-tenancy cross-CU con este dataset |

---

## 12. Cómo regenerar este análisis

```bash
# Extraer datos frescos de dev
export DB_HOST=<host-dev>
export DB_USER=tu_usuario
export DB_PASS=tu_contraseña
export DB_NAME=blossom-dough-consolidated-dev

python scripts/extract_smart_budget_monthly.py \
    --dbname blossom-dough-consolidated-dev \
    --output data/smart_budget_db_dev.csv
```

---

*Documento generado: 2026-06-04 · Dataset: `data/smart_budget_db_dev.csv` · Filas: 26,417*
