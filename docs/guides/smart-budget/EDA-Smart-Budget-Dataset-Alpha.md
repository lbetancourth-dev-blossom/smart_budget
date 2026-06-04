# EDA — Smart Budget Dataset (blossom-dough-consolidated-alpha)

> Exploración del dataset extraído directamente de la DB de producción (alpha).
> Origen: `scripts/extract_smart_budget_monthly.py` + query `smart_budget_monthly_spend.sql`.
> Archivo: `data/smart_budget_db.csv`

---

## 1. Origen y método de extracción

| Campo | Valor |
|---|---|
| **Base de datos** | `blossom-dough-consolidated-alpha` |
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
| **Total de filas** | 195,923 |
| **Columnas** | 8 |
| **Valores nulos** | 0 (en todas las columnas) |
| **Valores negativos en monthly_total** | 0 (clamp por GREATEST) |
| **Valores cero en monthly_total** | 0 |

---

## 3. Descripción de columnas

| Columna | Tipo | Descripción | Notas |
|---|---|---|---|
| `idclient` | int | ID del cliente Blossom (siempre `1` en esta DB) | Multi-tenancy layer 1 |
| `idcompany` | int | ID de la Credit Union | 18 CUs distintas en el dataset |
| `idmember` | string | ID del miembro (usuario) | 2,929 miembros únicos |
| `idaccount` | string | ID de la cuenta (prefijo `INT` = OLB) | **Solo prefijo `INT`** en esta DB (195,923 filas). No hay cuentas `EXT` (Plaid/Finicity). Puede haber múltiples cuentas por miembro |
| `idcategory` | string | Identificador de categoría | ⚠️ En esta DB es igual al nombre (`defaultcategory`). No hay ID numérico disponible en `fact_transactions`. |
| `defaultcategory` | string | Nombre de la categoría de gasto | 12 categorías únicas |
| `period_yyyymm` | string | Mes calendario del gasto (formato `YYYY-MM`) | Rango 2019-06 → 2026-06 |
| `monthly_total` | float | Gasto neto mensual en USD | Positivo siempre; clampeo a 0 si neto negativo |

### Nota sobre `idcategory`

En `blossom-dough-consolidated-alpha`, la tabla `fact_transactions` almacena la categoría como nombre (`defaultcategory`), no como ID numérico. El JOIN con `public.defaultcategory` no está disponible en esta DB. Por esta razón, **`idcategory` y `defaultcategory` son equivalentes** en este dataset.

---

## 4. Miembros (idmember)

| Métrica | Valor |
|---|---|
| **Miembros únicos** | 2,929 |
| **Filas por miembro (mediana)** | 19 |
| **Filas por miembro (media)** | 67 |
| **Filas por miembro (máx)** | 7,354 |
| **Meses con data por miembro (mediana)** | 15 |
| **Meses con data por miembro (media)** | 18 |
| **Categorías por miembro (mediana)** | 1 |
| **Categorías por miembro (media)** | 2.4 |
| **Categorías por miembro (máx)** | 12 |

**Observación:** El 50% de los miembros tiene datos en solo 1 categoría y en 15 meses o menos. La distribución es muy asimétrica — un grupo pequeño de miembros tiene historial extenso (hasta 40 meses, 12 categorías).

---

## 5. Categorías (defaultcategory)

12 categorías únicas. La categoría `Other` domina con ~94% de las filas.

| Categoría | Filas | % del total | Mediana monthly_total |
|---|---|---|---|
| Other | 183,477 | 93.6% | $4,513 |
| Taxes & fees | 3,680 | 1.9% | $33 |
| Transfers & payments | 3,196 | 1.6% | $23 |
| Shopping | 1,054 | 0.5% | $12 |
| Home & rent | 902 | 0.5% | $0.28 |
| Gas | 715 | 0.4% | $4 |
| Groceries | 700 | 0.4% | $99 |
| Auto & transport | 688 | 0.4% | $8 |
| Bills & utilities | 630 | 0.3% | $70 |
| Food & dining | 442 | 0.2% | $94 |
| Travel & trips | 328 | 0.2% | $6 |
| Entertainment & leisure | 111 | 0.1% | $60 |

**Observación crítica:** `Other` concentra el 93.6% de las filas y la mayor parte del monto total ($17.4B). Esto sugiere que la gran mayoría de las transacciones OLB no tienen categorización Ntropy activa (solo las CUs con RICH habilitado las enriquecen). Las sugerencias útiles para el usuario estarán principalmente en las 11 categorías restantes.

---

## 6. Periodos (period_yyyymm)

| Métrica | Valor |
|---|---|
| **Periodos únicos** | 40 |
| **Inicio de datos** | 2019-06 |
| **Fin de datos** | 2026-06 |
| **Rango con datos estables** | 2023-11 → 2026-04 |

**Distribución de filas por periodo:**

```
2019-06:      5 filas   ← dato aislado, no representativo
2023-04-10: ~1,591/mes  ← inicio de datos estables
2023-11:    4,876 filas ← salto significativo (más CUs onboarding)
2024-07:    6,390 filas ← otro incremento de cobertura
2025-04:    8,165 filas ← peak de datos
2025-05-09: ~3,500-4,900/mes ← caída (datos parciales o menos CUs activas)
2026-03:    7,293 filas
2026-06:    2,532 filas ← mes en curso (incompleto)
```

**Recomendación para el modelo:** Usar ventana de lookback sobre **meses calendario completos**. Excluir `2026-06` (mes en curso) y `2019-06` (dato aislado). El rango confiable es **2023-04 → 2026-05**.

---

## 7. Montos (monthly_total)

Todos los valores son positivos (el clamp `GREATEST(0, ...)` funcionó correctamente).

| Estadístico | Valor |
|---|---|
| **Mínimo** | $0.01 |
| **P25** | $700 |
| **Mediana (P50)** | $3,782 |
| **Media** | $88,744 |
| **P75** | $11,564 |
| **P90** | $25,482 |
| **P95** | $54,096 |
| **P99** | $584,843 |
| **Máximo** | $42,952,210 |

**Observación:** La media ($88K) está muy por encima de la mediana ($3,782) — la distribución tiene cola larga extrema hacia la derecha, principalmente por la categoría `Other` (pagos OLB masivos como nómina, transferencias internas de CU, etc.). Para el modelo de Smart Budget, la **mediana es la métrica correcta** para sugerencias; la media sería engañosa.

---

## 8. Credit Unions (idcompany)

18 CUs con datos. La CU `52` domina con el 91% de las filas.

| idcompany | Filas | % |
|---|---|---|
| 52 | 178,178 | 91.0% |
| 216 | 5,057 | 2.6% |
| 4 | 4,921 | 2.5% |
| 1953 | 2,683 | 1.4% |
| 315 | 1,461 | 0.7% |
| Otras 13 CUs | 3,623 | 1.8% |

---

## 9. Consideraciones para el modelo Smart Budget

| Hallazgo | Impacto en el modelo |
|---|---|
| 93.6% de filas son `Other` | Las sugerencias sobre `Other` serán poco útiles para el usuario; evaluar si excluirla del output |
| Mediana de categorías por miembro = 1 | La mayoría de miembros solo recibirá sugerencia en 1 categoría |
| 50% de miembros tiene ≥15 meses de data | El gating de 2 meses mínimo pasará para la mayoría |
| Montos con cola larga extrema | El modelo de **mediana** es robusto; WMA/EWMA serían afectados por outliers |
| `idcategory` = nombre (no ID numérico) | El endpoint debe aceptar el nombre como identificador hasta que se resuelva la clave numérica |
| 2026-06 incompleto | Excluir del cálculo de sugerencias (mes en curso) |
| CU `52` domina el dataset | Validar que el modelo funcione bien para CUs pequeñas (pocas filas) |

---

## 10. Cómo regenerar este análisis

```bash
# 1. Extraer datos frescos de la DB
export DB_USER=tu_usuario
export DB_PASS=tu_contraseña
python scripts/extract_smart_budget_monthly.py \
    --output data/smart_budget_db.csv

# 2. Correr el análisis EDA
python - << 'EOF'
import pandas as pd
df = pd.read_csv("data/smart_budget_db.csv", dtype={"idmember": str})
df["monthly_total"] = pd.to_numeric(df["monthly_total"], errors="coerce")
print(df.describe())
print(df.groupby("defaultcategory")["monthly_total"].agg(["count","median","mean"]))
EOF
```

---

## 11. Prefijos de idaccount

| Prefijo | Filas | % | Origen | Descripción |
|---|---|---|---|---|
| `INT` | 195,923 | 100% | OLB (Core Banking) | Cuentas nativas del core bancario de la CU |

**Observación:** Esta DB contiene **exclusivamente cuentas OLB** (prefijo `INT`). No existen cuentas externas `EXT` (Plaid/Finicity) en `blossom-dough-consolidated-alpha`. Esto es consistente con los resultados del diagnóstico de signos (§9): todos los `expenditure` son negativos — convención OLB.

Prefijos posibles en otros entornos (según `filters.py` y `build_fact_transactions.py`):

| Prefijo | Origen | Convención de signo |
|---|---|---|
| `INT` | OLB — cuentas internas del core | Gasto = **negativo** → `ABS()` obligatorio |
| `SUB` | OLB — subcuentas (granularidad fina) | Gasto = **negativo** → `ABS()` obligatorio |
| `EXT` | Plaid / Finicity — cuentas externas | Gasto = **positivo** → `ABS()` es no-op |
| `LOAN` | OLB — pagos de préstamos | **Excluidos** del modelo (no son gasto discrecional) |

---

*Documento generado: 2026-06-04 · Dataset: `data/smart_budget_db.csv` · Filas: 195,923*
