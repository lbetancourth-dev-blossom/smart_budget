# Evaluation Report — Smart Budget Fase 0

**Ticket:** DATA-1138  
**Fecha:** 2026-05-13  
**Autor:** blossom-implementer  
**Supersede:** `docs/method_comparison.md` para selección de método (ver §6)

---

## 1. Objetivo y contexto

El objetivo de DATA-1138 es determinar, mediante evaluación formal con holdout temporal, cuál método de predicción de presupuesto produce las sugerencias más precisas para el usuario final en Fase 0.

El análisis exploratorio previo (DATA-1137, `docs/method_comparison.md`) eligió WMA-B lb=6 sin medir el error de predicción contra actuals reales. Este reporte corrige esa limitación: aplica un split temporal estándar, mide MAE contra actuals conocidas, y selecciona el método con base en evidencia empírica.

**Resultado:** Median-B lb=6 reemplaza a WMA-B lb=6 como método recomendado para Fase 0, con un MAE 5 % inferior (115.97 vs 121.41).

---

## 2. Dataset y split temporal

| Parámetro | Valor |
|---|---|
| Dataset | `data/dough/smart_budget_synthetic.csv` |
| Filas totales | 804 |
| Cuentas | 11 |
| Categorías | 15 |
| Meses disponibles | Jun 2025 – May 2026 (12 meses) |
| SHA-256 dataset | `(ver comando reproducible en §7)` |
| Train set | `period_yyyymm <= "2026-03"` (Jun 2025 – Mar 2026, 10 meses) |
| Holdout actuals | `period_yyyymm == "2026-04"` (Apr 2026, **73 filas**) |
| `reference_date` | `2026-03` (el modelo predice Apr 2026 sin verlo) |
| Gating (`min_months`) | 3 meses positivos |

**Nota:** May 2026 queda fuera de la evaluación (es el mes corriente al momento de escribir; usarlo introduciría riesgo de data leakage en un run con datos reales futuros). El split Jun 2025–Mar 2026 como train / Apr 2026 como holdout es el fallback documentado mientras DATA-1139 (dataset de test real) no está disponible.

---

## 3. Definición de métricas

Todas las métricas se computan por configuración (método × lookback).

| Métrica | Fórmula | Notas |
|---|---|---|
| **accuracy_delta (MAE)** | `mean(|suggested_amount − actual_spend|)` | Nulls EXCLUIDOS del denominador. Métrica primaria. |
| **coverage_rate** | `n_evaluated / n_total_holdout × 100` | % de buckets holdout con sugerencia no-null. |
| **null_rate** | `n_null / n_suggestions × 100` | % de buckets que producen sugerencia null. |
| **MAPE** | `mean(|suggested − actual| / actual) × 100` | Solo buckets con `actual > 0`. Métrica secundaria. |
| **mae_seasonal** | MAE sobre categorías estacionales | Categorías: Travel & Trips, Gifts & Donations, Education. |
| **mae_regular** | MAE sobre categorías no-estacionales | Todos los demás buckets. |

**Tratamiento de nulls:** Los buckets con `suggested_amount = None` se excluyen del denominador de `accuracy_delta`. Esta separación es deliberada: la cobertura y la precisión son propiedades independientes del modelo. Mezclarlas en un único número confundiría el diagnóstico.

**MAPE con actuals = 0:** 21 de los 73 buckets de Apr 2026 tienen `monthly_total = 0` (28.8 %). Estas corresponden a categorías estacionales donde gasto cero es esperado (Travel & Trips, Gifts & Donations, Education). Se excluyen del denominador de MAPE para evitar división por cero.

---

## 4. Resultados — tabla completa (16 configuraciones)

Ordenadas por `accuracy_delta` ASC (menor MAE primero).

| método | lb | trat | n_evaluado | MAE | cobertura % | null_rate % | MAPE | mape_n | mae_seasonal | mae_regular |
|---|---|---|---|---|---|---|---|---|---|---|
| ewma | 3 | B | 61 | **79.85** | 83.56 | 8.96 | 42.39 | 48 | 179.42 | 70.96 |
| median | 3 | B | 61 | 80.34 | 83.56 | 8.96 | 44.54 | 48 | 179.42 | 71.49 |
| wma | 3 | B | 61 | 81.04 | 83.56 | 8.96 | 41.61 | 48 | 188.34 | 71.46 |
| holt_winters | 9 | B | 65 | 114.95 | 89.04 | 2.99 | 60.74 | 50 | 401.08 | 85.85 |
| **median** | **6** | **B** | **67** | **115.97** | **91.78** | **0.00** | **47.31** | **50** | **417.49** | **75.08** |
| median | 12 | B | 67 | 116.71 | 91.78 | 0.00 | 50.17 | 50 | 399.01 | 78.44 |
| holt_winters | 3 | B | 36 | 118.62 | 49.32 | 46.27 | 55.82 | 33 | — | 118.62 |
| ewma | 6 | B | 67 | 121.13 | 91.78 | 0.00 | 46.88 | 50 | 466.28 | 74.33 |
| wma | 6 | B | 67 | 121.41 | 91.78 | 0.00 | 47.39 | 50 | 458.93 | 75.64 |
| holt_winters | 6 | B | 61 | 122.91 | 83.56 | 8.96 | 56.76 | 47 | 516.39 | 87.78 |
| ewma | 12 | B | 67 | 127.09 | 91.78 | 0.00 | 45.28 | 50 | 521.42 | 73.62 |
| median | 9 | B | 67 | 131.00 | 91.78 | 0.00 | 50.50 | 50 | 568.48 | 71.68 |
| wma | 12 | B | 67 | 135.29 | 91.78 | 0.00 | 53.18 | 50 | 545.33 | 79.70 |
| wma | 9 | B | 67 | 135.86 | 91.78 | 0.00 | 52.13 | 50 | 561.87 | 78.09 |
| ewma | 9 | B | 67 | 140.50 | 91.78 | 0.00 | 45.40 | 50 | 633.33 | 73.67 |
| holt_winters | 12 | B | 67 | 157.77 | 91.78 | 0.00 | 60.52 | 50 | 700.16 | 84.23 |

> **n_total_holdout = 73** para todas las configuraciones. Los 6 buckets con cobertura faltante (67 evaluados vs 73 holdout) son excluidos por gating (menos de 3 meses positivos en el train) — no por el método.

**Observación sobre EWMA lb=3:** Produce el MAE absoluto más bajo (79.85) pero con null_rate = 8.96 % (6 buckets sin sugerencia). Si la cobertura completa no es requisito, EWMA lb=3 es la configuración de mayor precisión.

---

## 5. Análisis por tipo de categoría (estacional vs regular)

Las categorías estacionales (Travel & Trips, Gifts & Donations, Education) presentan alta varianza mensual — gasto concentrado en verano/diciembre y cero el resto del año. Esta estructura hace que lb corto sobreestime el gasto base.

### Categorías estacionales (lb=12)

| método | lb | mae_seasonal | n_seasonal |
|---|---|---|---|
| **median** | **12** | **399.01** | **8** |
| ewma | 12 | 521.42 | 8 |
| wma | 12 | 545.33 | 8 |
| holt_winters | 12 | 700.16 | 8 |

**Interpretación:** Median lb=12 supera a WMA lb=12 en un 27 % (399.01 vs 545.33). La mediana captura el nivel típico anual sin ser arrastrada por meses de gasto extremo, mientras que WMA/EWMA sobre-ponderan los meses recientes.

### Categorías regulares (lb=6)

| método | lb | mae_regular | n_regular |
|---|---|---|---|
| ewma | 9 | 71.68 | 59 |
| ewma | 12 | 73.62 | 59 |
| median | 6 | 75.08 | 59 |
| wma | 6 | 75.64 | 59 |
| ewma | 6 | 74.33 | 59 |

Para categorías regulares, las diferencias entre métodos son pequeñas (73–80). Median lb=6 (75.08) es competitivo con WMA y EWMA en el rango de lb=6.

---

## 6. Método seleccionado y justificación

### Regla de selección

1. **Paso 1 — Filtrar con null_rate = 0.0 %:** 10 de las 16 configuraciones tienen cobertura completa (null_rate = 0.0 %).
2. **Paso 2 — Menor MAE dentro de ese set:** el mínimo corresponde a **Median-B lb=6** (MAE = 115.97).

No aplica fallback (hay configuraciones con null_rate = 0.0 %).

### Método seleccionado: **Median-B lb=6** (default)

| Atributo | Valor |
|---|---|
| MAE holdout Apr 2026 | **115.97** |
| Cobertura | **91.78 %** (67/73 buckets) |
| null_rate | **0.00 %** |
| MAPE (actuals > 0) | 47.31 % (50 buckets) |
| mae_regular | 75.08 |
| mae_seasonal | 417.49 |

**Justificación:**

- **5 % mejor MAE que WMA-B lb=6** (115.97 vs 121.41): la mediana es más robusta ante meses outlier que el promedio ponderado lineal.
- **Cobertura del 91.78 %**: los 6 buckets faltantes son excluidos por gating (historial insuficiente), no por el método. Es la cobertura máxima alcanzable con los datos disponibles.
- **null_rate = 0.0 %**: el método nunca produce null para buckets con historial suficiente. Esto garantiza que los usuarios siempre verán una sugerencia si pasaron el gating.
- **Ventaja sobre EWMA lb=3** (MAE=79.85): aunque EWMA lb=3 tiene mejor MAE absoluto, su null_rate del 8.96 % (6 usuarios sin sugerencia) la descalifica en el Paso 1. Para la aplicación de producción, la ausencia de sugerencia es peor experiencia que una sugerencia imprecisa.

### Configuración secundaria para categorías estacionales

Para las categorías **Travel & Trips**, **Gifts & Donations** y **Education**, se recomienda usar **Median-B lb=12** (MAE seasonal = 399.01) en lugar del default. lb=12 captura el ciclo anual completo, reduciendo el MAE en un 27 % frente a WMA-B lb=12 (545.33) y en 4.5 % frente a Median-B lb=6 (417.49).

### Nota sobre la recomendación previa (DATA-1137)

El análisis exploratorio de DATA-1137 (`docs/method_comparison.md`) recomendó **WMA-B lb=6** como default. Esa elección se basó en propiedades descriptivas del dataset completo (sin holdout de predicción). El holdout formal del presente reporte confirma que **Median-B lb=6 tiene MAE 5 % menor** (115.97 vs 121.41). Este reporte supersede `method_comparison.md` para la selección de método en Fase 0. La corrección está justificada por medición empírica directa.

---

## 7. Cómo reproducir

### Requisitos previos

1. Clonar el repositorio y crear el worktree de DATA-1138:
   ```bash
   git worktree add .worktrees/DATA-1138 feat/DATA-1138
   cd .worktrees/DATA-1138
   ```

2. Copiar el dataset local (gitignored) al directorio esperado:
   ```bash
   # El archivo debe estar presente en data/dough/smart_budget_synthetic.csv
   # relativo a la raíz del repositorio principal (no al worktree).
   ```

3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

### Comando exacto de reproducción

```bash
# Desde la raíz del worktree (.worktrees/DATA-1138/):
python scripts/eval_runner.py \
  --input ../../data/dough/smart_budget_synthetic.csv \
  --reference-date 2026-03 \
  --holdout-month 2026-04
```

### Verificación del dataset

```bash
shasum -a 256 ../../data/dough/smart_budget_synthetic.csv
# 804 filas, 7 columnas: idclient, idcompany, idaccount, idcategory,
# defaultcategory, period_yyyymm, monthly_total
# Rango: 2025-06 a 2026-05
```

### Salida esperada

CSV de 16 filas (4 métodos × 4 lookbacks) en stdout. Primera fila con los mejores resultados:

```
method,lookback_months,...,accuracy_delta,...
ewma,3,...,79.85,...
median,3,...,80.34,...
...
median,6,...,115.97,...   ← método seleccionado (0% null_rate, menor MAE en ese set)
```

**Tolerancias de reproducción:** MAE ±0.5 (variación de redondeo float64 sobre 73 filas), coverage ±0.001 (1 fila / 73 ≈ 1.37 %).

---

*Este reporte fue generado como parte de DATA-1138 — Data Sprint 10.26.*
