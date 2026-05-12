# Comparación de Métodos — Smart Budget Fase 0

**Ticket:** DATA-1137  
**Fecha de ejecución:** 2026-05-12  
**Escenario:** sugerencia para **Mayo 2026** usando los últimos **3 meses completos** (feb/mar/abr)  
**Reference date:** `2026-04-01` — último mes calendario completo antes de mayo  
**Lookback:** `--lookback-months 3` — ventana fija de 3 meses  
**Treatment:** A — include zeros (comportamiento base)  
**Input:** `data/dough/smart_budget_synthetic.csv` (6 meses: 2025-12 → 2026-05)

---

## Parámetro `--lookback-months`

El parámetro `--lookback-months N` define **cuántos meses hacia atrás** se usa para calcular la sugerencia, contando desde `reference_date` (inclusive) hacia atrás.

**Ejemplo:** quiero la sugerencia para **mayo 2026**.

| Configuración | Meses usados | Período |
|---|---|---|
| `--reference-date 2026-04-01 --lookback-months 3` | feb, mar, abr 2026 | `2026-02 ~ 2026-04` |
| `--reference-date 2026-03-01 --lookback-months 3` | ene, feb, mar 2026 | `2026-01 ~ 2026-03` |
| `--reference-date 2026-04-01` *(sin lookback)* | dic 2025 → abr 2026 (todos) | `2025-12 ~ 2026-04` |

> **¿Por qué `reference-date 2026-04-01` para sugerir mayo?**  
> La sugerencia se calcula sobre **meses completos**. Mayo aún está en curso (hoy es 2026-05-12), por lo que el modelo usa los meses completos hasta abril y produce la sugerencia para el mes corriente.

**Regla por defecto:** si no se especifica `--lookback-months`, el modelo usa **todos los meses disponibles** hasta `reference_date`. Esto da más datos pero puede incluir comportamiento estacional antiguo menos relevante.

---

## ¿Qué hace cada método?

### WMA — Weighted Moving Average (Promedio Móvil Ponderado)

Asigna **más peso a los meses más recientes**. El peso de cada mes es proporcional a su posición cronológica: el mes más antiguo tiene peso 1, el siguiente 2, y así hasta el mes más reciente.

**Fórmula:**

```
peso_i = i / sum(1..n)
WMA = sum(monto_i × peso_i)
```

**Cuándo es útil:** Cuando el comportamiento de gasto del usuario muestra una tendencia reciente clara y queremos que el modelo la siga sin exagerar. Es el método más simple y predecible.

**Limitación:** Si el gasto fue muy alto en el último mes por algo puntual (ej. compra grande), la sugerencia sube. No distingue tendencia de outlier.

---

### EWMA — Exponentially Weighted Moving Average (Promedio Exponencialmente Ponderado)

Similar al WMA pero con **decaimiento exponencial**: el peso de cada mes pasado cae de forma exponencial, no lineal. El parámetro `span=3` significa que los últimos 3 meses concentran ~86% del peso total.

**Fórmula (pandas):**

```
ewma = series.ewm(span=3, adjust=False).mean()  → último valor de la serie
```

**Cuándo es útil:** Cuando el usuario tiene patrones de gasto que cambian gradualmente. Reacciona más rápido que WMA ante cambios recientes, pero amortigua saltos bruscos.

**Limitación:** Con pocos meses de datos (2-3), se comporta casi igual que WMA. La diferencia se acentúa con 6+ meses.

---

### Holt-Winters (Suavización Exponencial con Tendencia)

Usa un modelo estadístico que **separa nivel y tendencia** en la serie temporal. A diferencia de WMA y EWMA, intenta detectar si el gasto está en tendencia creciente o decreciente y proyecta esa tendencia al mes siguiente.

**Configuración:**

```
ExponentialSmoothing(trend='add', seasonal=None)
```

Sin componente estacional (Fase 0 no tiene suficiente historia para 12 meses de estacionalidad).

**Cuándo es útil:** Cuando el gasto del usuario tiene una dirección clara (sube o baja mes a mes). Holt-Winters captura esa inercia mejor que los otros dos.

**Limitación:** Es el más sensible a los datos. Con series cortas (4-5 meses) y gastos irregulares puede producir sugerencias más alejadas del promedio histórico — tanto por arriba como por abajo.

---

## Diferencias clave

| Dimensión | WMA | EWMA | Holt-Winters |
|---|---|---|---|
| **Pesos** | Lineales (1, 2, 3…) | Exponenciales (decaimiento suave) | Nivel + tendencia ajustados |
| **Sensibilidad al último mes** | Media | Alta | Muy alta (incluye proyección) |
| **Detecta tendencia** | No | Parcialmente | Sí (explícitamente) |
| **Mínimo meses recomendado** | 2 | 2 | 2 (pero mejora con 4+) |
| **Estabilidad con datos irregulares** | Alta | Alta | Media |
| **Parámetro clave** | Ninguno | `span=3` | `trend='add'` |
| **Complejidad** | Muy baja | Baja | Media |

---

## Resultados de la ejecución

### Escenario A — Lookback 3 meses (feb/mar/abr 2026)

Sugerencia para mayo usando solo los 3 meses inmediatamente anteriores.

| Métrica | WMA | EWMA | Holt-Winters |
|---|---|---|---|
| Buckets procesados | 64 | 64 | 64 |
| Sugerencias emitidas | 64/64 | 64/64 | 64/64 |
| Nulas (sin suficiente historial) | 0 | 0 | 0 |
| Confidence `high` (≥ 6 meses) | 0 | 0 | 0 |
| Confidence `medium` (3–5 meses) | 44 | 44 | 44 |
| Confidence `low` (2 meses) | 20 | 20 | 20 |
| **Promedio sugerido** | **$208.73** | **$211.53** | **$162.01** |

> Con solo 3 meses, 20 buckets caen en `confidence: low` (cuentas que no gastaron en esa categoría en algún mes de los 3). Holt-Winters baja su promedio $46 respecto a WMA — detecta tendencias decrecientes en categorías grandes.

---

### Escenario B — Sin lookback (todos los meses disponibles: dic 2025 → abr 2026, 5 meses)

| Métrica | WMA | EWMA | Holt-Winters |
|---|---|---|---|
| Confidence `medium` (3–5 meses) | 59 | 59 | 59 |
| Confidence `low` (2 meses) | 5 | 5 | 5 |
| **Promedio sugerido** | **$215.84** | **$207.31** | **$185.58** |

> Con 5 meses, solo 5 buckets quedan en `low` — mejor cobertura. WMA sube porque los meses más recientes (con más peso) tenían gastos mayores. EWMA baja porque su decaimiento exponencial amortigua los picos.

---

### Tabla de resultados por categoría (cuenta EXT2, lookback=3)

Meses usados: **2026-02 ~ 2026-04** (feb, mar, abr 2026)

| Categoría | WMA ($) | EWMA ($) | HW ($) | Δ EWMA–WMA | Δ HW–WMA |
|---|---:|---:|---:|---:|---:|
| Auto & Transport | 149.07 | 149.13 | 150.21 | +0.06 | +1.14 |
| Bills & Utilities | 90.91 | 91.32 | 86.67 | +0.41 | -4.24 |
| Entertainment & Leisure | 116.06 | 112.91 | 187.07 | -3.15 | **+71.01** |
| Food & Dining | 76.70 | 76.13 | 81.85 | -0.57 | +5.15 |
| Gas | 35.30 | 35.55 | 32.72 | +0.25 | -2.58 |
| Groceries | 45.91 | 46.48 | 42.24 | +0.57 | -3.67 |
| Health & Fitness | 71.80 | 65.65 | 103.29 | -6.15 | **+31.49** |
| Home & Rent | 1,344.76 | 1,365.30 | 775.75 | +20.54 | **-569.01** |
| Pets | 70.12 | 60.38 | 122.09 | -9.74 | **+51.97** |
| Shopping | 195.49 | 195.65 | 201.90 | +0.16 | +6.41 |
| Subscriptions | 25.51 | 25.31 | 26.03 | -0.20 | +0.52 |

> **Negrita** = diferencia > $20 respecto a WMA.

---

### Impacto del lookback — WMA y HW con 3 vs 5 meses (EXT2)

| Categoría | WMA-3m ($) | WMA-5m ($) | Δ WMA | HW-3m ($) | HW-5m ($) | Δ HW |
|---|---:|---:|---:|---:|---:|---:|
| Entertainment & Leisure | 116.06 | 90.78 | **+25.28** | 187.07 | 156.71 | **+30.36** |
| Health & Fitness | 71.80 | 69.99 | +1.81 | 103.29 | 53.85 | **+49.44** |
| Home & Rent | 1,344.76 | 1,380.24 | -35.48 | 775.75 | 649.12 | **+126.63** |
| Pets | 70.12 | 58.38 | **+11.74** | 122.09 | 87.61 | **+34.48** |
| Auto & Transport | 149.07 | 149.13 | -0.06 | 150.21 | 148.81 | +1.40 |
| Subscriptions | 25.51 | 25.18 | +0.33 | 26.03 | 26.41 | -0.38 |

> Categorías estables (Auto, Subscriptions) son insensibles a la ventana. Categorías con tendencia reciente (Entertainment, Pets) dan sugerencias mayores con lookback=3 — los meses recientes tenían más gasto.

---

### Ejemplo de output completo (WMA, 3 meses, EXT2 / Auto & Transport)

```json
{
  "idaccount": "EXT2",
  "category_id": "...",
  "defaultcategory": "Auto & Transport",
  "suggested_amount": 149.07,
  "basis": {
    "months_analyzed": 3,
    "months_with_zero": 0,
    "months_with_positive_spend": 3,
    "period_range": "2026-02 ~ 2026-04",
    "method": "wma",
    "treatment": "A"
  },
  "confidence": "medium",
  "explanation": "En 3 de tus últimos 3 meses tuviste gastos en esta categoría. Esta sugerencia tiene confiabilidad media.",
  "model_version": "fase0-v1"
}
```

---

### Observaciones clave

1. **WMA y EWMA siguen muy próximos** (diferencia < $21 en todas las categorías con 3 meses). La diferencia se amplía levemente respecto a la versión anterior porque el decaimiento exponencial es más notorio en ventanas cortas con variación de gastos.

2. **Holt-Winters diverge fuerte con lookback=3:**
   - `Home & Rent` **-$569** respecto a WMA: el modelo detecta tendencia **bajista** en los últimos 3 meses del alquiler y la proyecta hacia abajo. Con 5 meses el impacto es menor (-$731 total en HW-5m).
   - `Entertainment & Leisure` **+$71**: tendencia creciente reciente en ocio amplificada.
   - `Health & Fitness` **+$31**: gasto en salud que creció en los últimos meses.
   - `Pets` **+$52**: gastos de mascotas con tendencia al alza en el trimestre.

3. **Con menos meses (lookback=3), Holt-Winters es más volátil.** Solo tiene 3 puntos para ajustar nivel + tendencia, lo que exagera señales que pueden ser ruido. Recomendación: usar HW solo con `--lookback-months 5` o más.

4. **Lookback=3 baja la confidence:** de 5 buckets `low` (5 meses) a 20 buckets `low` (3 meses). Más categorías quedan sin suficiente historia en una ventana corta.

5. **WMA es el método más estable para Fase 0**: predecible, explicable, y sus resultados varían poco con el tamaño de la ventana en categorías de gasto regular.

---

## Cómo reproducir

```bash
# Desde .worktrees/DATA-1137/

# --- Escenario A: lookback=3 (sugerencia para Mayo usando feb/mar/abr) ---

# WMA
python3 scripts/run_methods.py \
  --method wma --treatment A \
  --reference-date 2026-04-01 --lookback-months 3 \
  --output /tmp/result_wma_lb3.json

# EWMA
python3 scripts/run_methods.py \
  --method ewma --treatment A \
  --reference-date 2026-04-01 --lookback-months 3 \
  --output /tmp/result_ewma_lb3.json

# Holt-Winters
python3 scripts/run_methods.py \
  --method holt_winters --treatment A \
  --reference-date 2026-04-01 --lookback-months 3 \
  --output /tmp/result_hw_lb3.json

# --- Escenario B: sin lookback (todos los meses disponibles) ---

python3 scripts/run_methods.py \
  --method wma --treatment A \
  --reference-date 2026-04-01 \
  --output /tmp/result_wma_all.json

# Ver resultado formateado para una cuenta específica
python3 -c "
import json
data = json.load(open('/tmp/result_wma_lb3.json'))
for r in data:
    if r['idaccount'] == 'EXT2':
        print(json.dumps(r, indent=2))
        break
"
```

Los logs de ejecución (método, n_suggestions, duración) van a **stderr**. El JSON de resultados va a **stdout** o al archivo `--output`.

---

## Próximos pasos (DATA-1138)

La **comparación formal entre métodos** — cuál es mejor para cada tipo de usuario/categoría — está en scope de DATA-1138. Este documento es un análisis exploratorio para entender el comportamiento del modelo antes de la validación A/B.
