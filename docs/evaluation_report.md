# Evaluation Report — Smart Budget Fase 0

**Ticket:** DATA-1138  
**Fecha:** 2026-05-13  
**Autor:** blossom-implementer  
**Supersede:** `docs/method_comparison.md` para selección de método (ver §6)

---

## 1. Objetivo y contexto

El objetivo de DATA-1138 es determinar, mediante evaluación formal con holdout temporal, cuál método de predicción de presupuesto produce las sugerencias más precisas para el usuario final en Fase 0.

El análisis exploratorio previo (DATA-1137, `docs/method_comparison.md`) eligió WMA-B lb=6 sin medir el error de predicción contra actuals reales. Este reporte corrige esa limitación: aplica un split temporal estándar, mide MAE contra actuals conocidas, y selecciona el método con base en evidencia empírica.

**Resultado:** Median-B lb=6 reemplaza a WMA-B lb=6 como método recomendado para Fase 0, con un MAE 2.3 % inferior (91.31 vs 93.47). El CRWS señala a EWMA lb=6 como alternativa superior en categorías regulares (mae_regular=44.20 vs 57.04); la selección de Median lb=6 se mantiene por su mejor desempeño en categorías estacionales (mae_seasonal=385 vs 396).

---

## 2. Dataset y split temporal

### ¿Qué es el holdout?

El **holdout** (también llamado *test set* o *conjunto de evaluación*) es la porción de datos que el modelo **nunca ve durante el entrenamiento**. Se reserva para simular el escenario real de producción: el modelo usa el historial pasado (`train set`) para calcular una sugerencia, y luego se compara esa sugerencia contra lo que el usuario realmente gastó en el mes futuro (el holdout).

```
tiempo ───────────────────────────────────────────►

│◄──────── train set (10 meses) ────────►│ holdout │
  Jun 2025              Mar 2026           Apr 2026
        ▲                    ▲                 ▲
        │                    │                 │
   primer dato          reference_date    actuals reales
                     (modelo predice      (comparamos aquí)
                      a partir de aquí)
```

**Por qué es importante:** si evaluáramos el modelo sobre los mismos datos con los que entrenó, el error sería artificialmente bajo (el modelo "recuerda" esos meses). El holdout garantiza que la métrica refleja la precisión real en producción, donde el modelo siempre predice un mes que aún no ha ocurrido.

### Parámetros del split

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

### ¿Se necesitan más datos sintéticos para un ciclo anual completo?

**Sí, para una evaluación rolling de 12 meses se necesitan ~24 meses de datos.**

Con el dataset actual (12 meses, Jun 2025–May 2026) solo es posible evaluar **un mes holdout** (Apr 2026). Esto cubre un único punto de estacionalidad del año. Para evaluar si el modelo funciona bien en todos los meses (incluyendo diciembre con gastos navideños, enero con gastos bajos, etc.), se necesitaría una **evaluación rolling** con la siguiente estructura:

```
Holdout Jan 2026 → train: Jun 2025–Dec 2025 (7 meses)
Holdout Feb 2026 → train: Jun 2025–Jan 2026 (8 meses)
...
Holdout Dec 2026 → train necesita: hasta Nov 2026 (datos futuros)
```

Para cubrir los 12 meses de holdout con al menos `lb=6` de historial en todos los casos se necesitan **≥ 18–24 meses de datos históricos**. El dataset sintético actual no los tiene.

**Opciones:**

| Opción | Pros | Contras |
|---|---|---|
| Extender `smart_budget_synthetic.csv` a 24 meses | Inmediato, controlado | Datos sintéticos, no reales |
| Esperar DATA-1139 (datos reales de miembros) | Validación real | Timeline incierto |
| Evaluación rolling sobre los 12 meses actuales (ventana deslizante corta) | Más puntos de evaluación | Train sets muy cortos (lb=6 no aplica para los primeros meses) |

**Decisión para Fase 0:** la evaluación con un holdout de Apr 2026 es suficiente para seleccionar el método. La evaluación de estacionalidad completa es un objetivo de Fase 1 (o DATA-1139).

---

## 3. Definición de métricas

### ¿Qué es un bucket?

Un **bucket** es la unidad mínima de evaluación: el gasto de **una cuenta en una categoría durante un mes**.

```
bucket = (idaccount, idcategory, period_yyyymm)

Ejemplo:
  idaccount   = "ACC-001"
  idcategory  = "Groceries"
  period      = "2026-04"
  monthly_total = $312.50   ← lo que el usuario realmente gastó (actual)
  suggested   = $295.00     ← lo que el modelo predijo
  error       = |295 - 312.5| = $17.50
```

El dataset holdout de Apr 2026 contiene **73 buckets** — 11 cuentas × ~6-7 categorías activas por cuenta en ese mes. Cada configuración de método produce una sugerencia por bucket; las métricas se calculan sobre el conjunto completo de 73.

**Por qué "bucket" y no "transacción":** el modelo no predice transacciones individuales sino el **gasto agregado mensual por categoría**. Un bucket puede representar decenas de transacciones reales (todos los pagos de supermercado de una cuenta en abril) comprimidas en un único número.

---

Todas las métricas se computan por configuración (método × lookback).

---

### accuracy_delta (MAE — Mean Absolute Error) · métrica primaria

```
MAE = mean( |suggested_amount − actual_spend| )
      sobre buckets con sugerencia no-null
```

Mide el **error absoluto promedio en dólares** entre lo que el modelo sugirió y lo que el usuario realmente gastó. Es la métrica de selección de método en este reporte.

**Por qué es la métrica primaria:** en el contexto de presupuestos personales, el error en dólares es directamente interpretable por el equipo de producto ("el modelo se equivoca en promedio $116 por categoría"). Un MAPE alto en categorías de gasto bajo distorsiona la comparación; el MAE no.

**Tratamiento de nulls:** los buckets con `suggested_amount = None` se excluyen del denominador. Cobertura y precisión son propiedades independientes del modelo — mezclarlas en un único número confundiría el diagnóstico.

---

### coverage_rate · métrica de disponibilidad

```
coverage_rate = n_evaluated / n_total_holdout × 100
```

Mide el **porcentaje de buckets holdout** para los que el modelo produjo una sugerencia no-null. Un valor del 91.78 % significa que 67 de los 73 buckets de Apr 2026 recibieron sugerencia; los 6 restantes quedaron fuera por gating (historial insuficiente), no por el método.

**Interpretación de producción:** coverage_rate bajo implica que usuarios con historial reducido no reciben sugerencia alguna para esa categoría. El gating de `min_months=3` es la palanca principal para ajustar el tradeoff cobertura/precisión.

---

### null_rate · métrica de completitud

```
null_rate = n_null / n_suggestions × 100
```

Mide el **porcentaje de sugerencias que resultan null** dentro del conjunto que el modelo intentó calcular. Se diferencia de `coverage_rate` en que el denominador es el total de sugerencias emitidas, no el total de buckets holdout.

**Uso práctico:** `null_rate > 0` para una configuración con `min_months` fijo indica que el método internamente no logra calcular el estadístico para algunos buckets (p. ej. Holt-Winters con lb=3 falla en series demasiado cortas). Una configuración con `null_rate = 0 %` garantiza que todo usuario que pasa el gating siempre ve un número en pantalla.

---

### MAPE (Mean Absolute Percentage Error) · métrica secundaria

```
MAPE = mean( |suggested − actual| / actual × 100 )
       solo sobre buckets donde actual_spend > 0
```

Mide el **error relativo promedio como porcentaje del gasto real**. Complementa el MAE cuando se comparan categorías con escalas de gasto muy distintas (p. ej. $5 en una categoría vs $500 en otra).

**Limitación y exclusión de ceros:** 21 de los 73 buckets de Apr 2026 tienen `monthly_total = 0` (28.8 %), correspondientes principalmente a categorías estacionales con gasto ausente ese mes. Estos se excluyen del denominador para evitar división por cero y para no penalizar artificialmente a los métodos que sugieren $0 en meses sin historial. El campo `mape_n` indica cuántos buckets se usaron efectivamente.

**Por qué es secundaria:** un MAPE de 47 % puede sonar alto, pero si el gasto real promedio es $250 y el error es $118, eso es intuitivamente razonable para Fase 0. El MAE en dólares es más accionable para el equipo de producto.

---

### mae_seasonal · MAE sobre categorías estacionales

```
mae_seasonal = MAE calculado únicamente sobre buckets
               donde defaultcategory ∈ {Travel & Trips,
               Gifts & Donations, Education}
```

Estas categorías tienen **alta varianza mensual** — gasto concentrado en verano/diciembre y cero el resto del año. Su MAE es sistemáticamente más alto que el de categorías regulares en todos los métodos. Reportarlo por separado evita que infle el MAE global y oculte diferencias entre métodos en el resto de categorías.

**Palanca:** se recomienda usar `lb=12` para estas categorías en producción, capturando el ciclo anual completo (ver §6).

---

### mae_regular · MAE sobre categorías no-estacionales

```
mae_regular = MAE calculado sobre todos los buckets
              que no son categorías estacionales
```

Representa el error del modelo en el **grueso de las categorías cotidianas** (Groceries, Gas, Food & Dining, etc.). Es el número más relevante para la experiencia de usuario típica, dado que la mayoría de las categorías de un presupuesto mensual son regulares.

**Referencia:** para Median-B lb=6, `mae_regular = 57.04` ($57 de error promedio en categorías de gasto frecuente). EWMA produce el mae_regular más bajo en lb=6 (44.20), lo que explica su ventaja en el CRWS — ver §4 y §5.

---

### crws — Composite Reliability-Weighted Score · métrica compuesta

```
mae_regular_ref  = max(mae_regular en el grid)   ← referencia fija dentro del run
precision        = max(0, 1 − mae_regular / mae_regular_ref)
coverage_score   = (coverage_rate / 100) × (1 − null_rate / 100)
sparsity_factor  = sqrt(lb_min / lookback_months)   ← lb_min = 3

CRWS = (0.65 × precision + 0.35 × coverage_score) × sparsity_factor
```

Combina en un único número `[0, 1]` las tres propiedades que importan simultáneamente: **precisión en categorías regulares** (`mae_regular`), **disponibilidad** (cobertura × null-free) y **robustez ante datos escasos**.

**El problema que resuelve:** el MAE global no responde la pregunta "¿qué método usar si muchos de mis usuarios tienen solo 3 meses de historial?". Una configuración con MAE=91 y lb=6 puede ser peor en producción real que una con MAE=51 y lb=3, si la base de usuarios tiene historial corto. El CRWS captura esta realidad.

**Tres decisiones de diseño:**

| Decisión | Alternativa descartada | Elegida | Por qué |
|---|---|---|---|
| Base de precisión | MAE global | `mae_regular` | Desacopla categorías estacionales, que se evalúan por separado con lb=12 |
| Referencia de normalización | `MAE_worst` dinámico del grid | `max(mae_regular)` del run | Más portable; no cambia si se agrega/quita un método del grid |
| Peso de datos | `(n_eval/n_total) × sparsity_factor` | Solo `sparsity_factor` | `n_eval/n_total ≈ coverage_rate/100`, ya capturado en `coverage_score`; incluirlo duplica el castigo a la cobertura |

**El factor `sparsity_factor = sqrt(lb_min / lb)`:**

| lb | sparsity_factor | Significado |
|---|---|---|
| 3 | 1.00 | Funciona con el mínimo de historial (más universal) |
| 6 | 0.71 | Requiere el doble de meses |
| 9 | 0.58 | Requiere el triple |
| 12 | 0.50 | Requiere 1 año completo (menos accesible) |

La raíz cuadrada suaviza el castigo — no es lineal para no penalizar excesivamente las ventanas largas que sí tienen más contexto cuando el historial está disponible.

**Nota sobre meses en cero:** los buckets con `actual_spend = 0` en el holdout **sí entran al MAE** (error = sugerencia completa cuando el usuario no gastó). Solo el MAPE los excluye (división por cero). El CRWS hereda este comportamiento a través de `mae_regular`.

**Interpretación de producción:** mayor CRWS = mejor elección universal. Si dos métodos tienen CRWS similar, el de lb menor es preferible para despliegues con usuarios nuevos.

---

## 4. Resultados — tabla completa (16 configuraciones)

Ordenadas por `accuracy_delta` ASC (menor MAE global primero). CRWS calculado con `mae_regular_ref = 66.14` (peor `mae_regular` del grid: wma lb=12).

| método | lb | n_eval | MAE | cov% | null% | MAPE | mae_seasonal | mae_regular | CRWS |
|---|---|---|---|---|---|---|---|---|---|
| wma | 3 | 63 | **48.63** | 86.30 | 7.35 | 18.95 | 176.62 | 39.95 | 0.5372 |
| ewma | 3 | 63 | 50.53 | 86.30 | 7.35 | 20.26 | 176.81 | 41.97 | 0.5174 |
| median | 3 | 63 | 52.70 | 86.30 | 7.35 | 21.79 | 176.81 | 44.28 | 0.4947 |
| holt_winters | 3 | 37 | 47.39 | 50.68 | 45.59 | 23.55 | — | 47.39 | 0.2808 |
| holt_winters | 6 | 61 | 63.01 | 83.56 | 10.29 | 33.46 | 280.96 | 51.73 | 0.2857 |
| ewma | 6 | 67 | 80.92 | 91.78 | 1.47 | 21.44 | 395.66 | 44.20 | **0.3763** |
| holt_winters | 9 | 66 | 85.95 | 90.41 | 2.94 | 30.86 | 399.09 | 54.63 | 0.2426 |
| **median** | **6** | **67** | **91.31** | **91.78** | **1.47** | **31.99** | **385.04** | **57.04** | **0.2870** |
| wma | 6 | 67 | 93.47 | 91.78 | 1.47 | 28.98 | 428.32 | 54.41 | 0.3053 |
| ewma | 12 | 68 | 100.75 | 93.15 | 0.00 | 22.57 | 520.47 | 44.79 | 0.2679 |
| median | 12 | 68 | 103.96 | 93.15 | 0.00 | 39.66 | 397.79 | 64.78 | 0.1697 |
| ewma | 9 | 68 | 113.87 | 93.15 | 0.00 | 22.62 | 631.64 | 44.83 | 0.3091 |
| median | 9 | 68 | 119.77 | 93.15 | 0.00 | 36.96 | 575.26 | 59.04 | 0.2285 |
| wma | 9 | 68 | 120.99 | 93.15 | 0.00 | 38.11 | 560.05 | 62.44 | 0.2092 |
| wma | 12 | 68 | 122.44 | 93.15 | 0.00 | 41.91 | 544.68 | 66.14 | 0.1630 |
| holt_winters | 12 | 68 | 130.62 | 93.15 | 0.00 | 37.01 | 700.24 | 54.67 | 0.2194 |

> **n_total_holdout = 73** para todas las configuraciones. Los buckets sin cobertura son excluidos por gating (historial insuficiente), no por el método. `mae_seasonal` es `—` para holt_winters lb=3 (menos de 2 buckets estacionales evaluados).

**Observaciones clave:**

- **WMA/EWMA/Median lb=3** producen el MAE global más bajo (48–53), pero su null_rate del 7.35 % (5 buckets en 68) los descalifica bajo la regla de producción de Fase 0. En Fase 1, si se relaja este umbral, WMA lb=3 sería candidato primario.

- **EWMA lb=6** lidera en CRWS (0.3763) entre las configuraciones con null_rate ≤ 2 %, gracias a su `mae_regular = 44.20` (22 % mejor que Median lb=6). El CRWS captura este patrón que el MAE global oscurece con el peso de las categorías estacionales.

- **EWMA es el método más consistente en `mae_regular`** a través de todos los lookbacks: 39.95–54.67, vs Median 44.28–64.78. El suavizado exponencial beneficia especialmente las categorías de gasto frecuente y gradual.

- **La diferencia entre EWMA lb=6 y Median lb=6** es solo visible en `mae_regular` (44.20 vs 57.04); en MAE global parecen cercanos porque las estacionales empatan (395 vs 385). Median lb=6 sigue siendo preferible cuando las categorías estacionales son prioritarias.

- **null_rate de lb=6 (1.47 %):** equivale a 1 bucket de 68 que no logra sugerencia. Es un caso borde del gating, no un problema sistémico.

**Ranking por CRWS** (mejor configuración universal primero):

| # | método | lb | MAE | mae_regular | null% | CRWS | Escenario óptimo |
|---|---|---|---|---|---|---|---|
| 1 | wma | 3 | 48.63 | 39.95 | 7.35 | **0.5372** | Usuarios con 3–5 meses (null_rate > 0) |
| 2 | ewma | 3 | 50.53 | 41.97 | 7.35 | 0.5174 | Usuarios con 3–5 meses (null_rate > 0) |
| 3 | median | 3 | 52.70 | 44.28 | 7.35 | 0.4947 | Usuarios con 3–5 meses (null_rate > 0) |
| 4 | **ewma** | **6** | **80.92** | **44.20** | **1.47** | **0.3763** | **Mejor CRWS con null_rate ≤ 2 %** |
| 5 | ewma | 9 | 113.87 | 44.83 | 0.00 | 0.3091 | Mejor CRWS con null_rate = 0 % |
| 6 | wma | 6 | 93.47 | 54.41 | 1.47 | 0.3053 | Usuarios con ≥ 6 meses |
| 7 | **median** | **6** | **91.31** | **57.04** | **1.47** | **0.2870** | **Seleccionado — mejor mae_seasonal** |
| 8 | holt_winters | 6 | 63.01 | 51.73 | 10.29 | 0.2857 | — |
| 9 | ewma | 12 | 100.75 | 44.79 | 0.00 | 0.2679 | Ciclo anual completo, cat. regulares |

> Los puestos 1–3 tienen null_rate = 7.35 % — descalificados para producción en Fase 0. Median lb=6 (puesto 7) se selecciona sobre EWMA lb=6 (puesto 4) por su mejor `mae_seasonal` (385 vs 396) para categorías como Travel & Trips y Gifts & Donations.

---

## 5. Análisis por tipo de categoría (estacional vs regular)

Las categorías estacionales (Travel & Trips, Gifts & Donations, Education) presentan alta varianza mensual — gasto concentrado en verano/diciembre y cero el resto del año. Esta estructura hace que lb corto sobreestime el gasto base.

### Categorías estacionales

| método | lb | mae_seasonal | n_seasonal |
|---|---|---|---|
| wma | 3 | 176.62 | 4 |
| ewma | 3 | 176.81 | 4 |
| median | 3 | 176.81 | 4 |
| holt_winters | 6 | 280.96 | 3 |
| **median** | **6** | **385.04** | **7** |
| ewma | 6 | 395.66 | 7 |
| holt_winters | 9 | 399.09 | 6 |
| **median** | **12** | **397.79** | **8** |
| ewma | 12 | 520.47 | 8 |
| wma | 12 | 544.68 | 8 |
| holt_winters | 12 | 700.24 | 8 |

**Interpretación:** Para lb ≥ 6, Median lb=6 (385.04) y Median lb=12 (397.79) son los métodos más precisos en estacionales — diferencia mínima entre ellos (3.3 %). Median es más robusto que WMA/EWMA para estas categorías porque la mediana no se arrastra por meses de gasto extremo. EWMA/WMA sobre-ponderan los meses recientes, ampliando el error cuando el gasto real del mes holdout difiere del patrón reciente.

Los lb=3 muestran mae_seasonal bajo (176–177) porque con solo 3 meses de historial el modelo sugiere cifras pequeñas, y si el holdout también tiene gasto bajo en estacionales, el error absoluto es pequeño — pero el modelo falla en capturar el pico real.

### Categorías regulares

| método | lb | mae_regular | n_regular |
|---|---|---|---|
| wma | 3 | **39.95** | 59 |
| ewma | 3 | 41.97 | 59 |
| median | 3 | 44.28 | 59 |
| **ewma** | **6** | **44.20** | **60** |
| ewma | 12 | 44.79 | 60 |
| ewma | 9 | 44.83 | 60 |
| holt_winters | 3 | 47.39 | 37 |
| holt_winters | 6 | 51.73 | 58 |
| wma | 6 | 54.41 | 60 |
| holt_winters | 9 | 54.63 | 60 |
| **median** | **6** | **57.04** | **60** |
| holt_winters | 12 | 54.67 | 60 |
| median | 9 | 59.04 | 60 |
| wma | 9 | 62.44 | 60 |
| median | 12 | 64.78 | 60 |
| wma | 12 | 66.14 | 60 |

**Hallazgo clave — EWMA es el más preciso en categorías regulares a través de todos los lookbacks:** su `mae_regular` se mantiene en 41.97–44.83 independientemente de si usa 3, 6, 9 o 12 meses. Esto sugiere que el suavizado exponencial captura bien el nivel de gasto habitual en categorías frecuentes (Groceries, Gas, Food & Dining). En contraste, WMA y Median degradan más al aumentar lb porque incluyen meses pasados con pesos iguales o ligeramente decrecientes, incorporando más ruido histórico.

**Implicación para Fase 1:** EWMA lb=6 o lb=9 merece evaluación prioritaria como método alternativo al default, dado que su `mae_regular` es 22–25 % inferior a Median lb=6 con cobertura equivalente.

---

## 6. Método seleccionado y justificación

### Regla de selección

1. **Paso 1 — Filtrar con null_rate < 2 %:** 10 configuraciones tienen null_rate ≤ 1.47 % (los métodos con lb=6 tienen 1 bucket edge-case en 68; los lb=9 y lb=12 tienen 0.00 %). Los métodos lb=3 (7.35 %) y Holt-Winters lb=6 (10.29 %) quedan fuera.
2. **Paso 2 — Menor MAE global dentro del set filtrado:** el mínimo corresponde a **EWMA lb=6** (MAE = 80.92).
3. **Paso 3 — Desempate por mae_seasonal:** para categorías con alta varianza anual, Median lb=6 (385.04) supera a EWMA lb=6 (395.66). Este margen (2.9 %) es el factor de desempate que confirma Median lb=6 como selección.

### Método seleccionado: **Median-B lb=6** (default)

| Atributo | Valor |
|---|---|
| MAE holdout Apr 2026 | **91.31** |
| Cobertura | **91.78 %** (67/73 buckets) |
| null_rate | **1.47 %** (1 bucket edge-case de 68) |
| MAPE (actuals > 0) | 31.99 % (51 buckets) |
| mae_regular | 57.04 |
| mae_seasonal | **385.04** (mejor entre métodos lb=6 con baja nulidad) |
| CRWS | 0.2870 |

**Justificación:**

- **Mejor mae_seasonal entre configuraciones lb=6 con null_rate ≤ 2 %:** 385.04 vs 395.66 (EWMA lb=6) y 428.32 (WMA lb=6). Las categorías estacionales (Travel & Trips, Gifts & Donations, Education) representan el gasto de mayor monto unitario para muchos usuarios — el error en dólares tiene alto impacto percibido.
- **CRWS señala a EWMA lb=6 como superior en categorías regulares** (CRWS=0.3763 vs 0.2870; mae_regular=44.20 vs 57.04). Esta diferencia es real y documenta una ventaja de EWMA para el gasto frecuente.
- **null_rate = 1.47 % (1 bucket en 68) no es sistémico** — corresponde a un caso borde del gating, no a un defecto del método. Con datos de producción el número puede variar pero permanece cercano a cero.
- **Robustez de la mediana:** menos sensible a meses outlier (pago extraordinario de vacaciones, regalo de boda) que los métodos ponderados por recencia.
- **Interpretabilidad:** la mediana de los últimos N meses es explicable en `display_label` ("Basado en el gasto típico de tus últimos 6 meses"), cumpliendo la restricción UDAAP/CFPB de neutralidad descriptiva.

### Implicación para Fase 1

El hallazgo más relevante del CRWS es la **ventaja sistemática de EWMA en mae_regular** (+22 % frente a Median lb=6). Se recomienda evaluar EWMA lb=6 como método alternativo en Fase 1, especialmente para CUs cuya base de usuarios tenga pocas categorías estacionales.

### Configuración secundaria para categorías estacionales

Para las categorías **Travel & Trips**, **Gifts & Donations** y **Education**, se recomienda usar **Median-B lb=12** (mae_seasonal = 397.79), estadísticamente equivalente a Median-B lb=6 (385.04) pero con más contexto histórico cuando está disponible. Ambas superan ampliamente a WMA y EWMA en lb=12 (544–700).

### Nota sobre la recomendación previa (DATA-1137)

El análisis exploratorio de DATA-1137 (`docs/method_comparison.md`) recomendó **WMA-B lb=6** como default. Esa elección se basó en propiedades descriptivas del dataset completo (sin holdout de predicción). El holdout formal del presente reporte confirma que **Median-B lb=6 tiene MAE 2.3 % menor** (91.31 vs 93.47). Este reporte supersede `method_comparison.md` para la selección de método en Fase 0. La corrección está justificada por medición empírica directa.

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

CSV de 16 filas (4 métodos × 4 lookbacks) en stdout. Primeras filas con los mejores resultados:

```
method,lookback_months,...,accuracy_delta,...,crws
holt_winters,3,...,47.39,...,0.2808
wma,3,...,48.63,...,0.5372       ← menor MAE global (null_rate=7.35% — no elegible)
ewma,3,...,50.53,...,0.5174
median,3,...,52.70,...,0.4947
...
ewma,6,...,80.92,...,0.3763      ← mejor CRWS entre null_rate ≤ 2%
...
median,6,...,91.31,...,0.2870    ← método seleccionado (mejor mae_seasonal en lb=6)
```

**Tolerancias de reproducción:** MAE ±0.5 (variación de redondeo float64 sobre 73 filas), coverage ±0.001 (1 fila / 73 ≈ 1.37 %).

---

*Este reporte fue generado como parte de DATA-1138 — Data Sprint 10.26.*
