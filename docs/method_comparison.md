# Comparación de Métodos — Smart Budget Fase 0

**Ticket:** DATA-1137  
**Fecha de ejecución:** 2026-05-12  
**Dataset:** `data/dough/smart_budget_synthetic.csv` — 6 meses (2025-12 → 2026-05), 11 cuentas, 16 categorías  
**Lookback:** `--lookback-months 3` — ventana fija de 3 meses para cada ejecución  
**Ventanas:** 4 ventanas deslizantes (una por mes de referencia disponible)

---

## Parámetro `--reference-date`

Acepta **`YYYY-MM`** o `YYYY-MM-DD` (ambos válidos):

```bash
# Equivalentes:
python3 scripts/run_methods.py --method wma --treatment A --reference-date 2026-05
python3 scripts/run_methods.py --method wma --treatment A --reference-date 2026-05-01
```

> **¿Qué es `reference_date`?** El último mes (inclusive) que entra en el cálculo.  
> Para sugerir el presupuesto de **junio**, se usa `--reference-date 2026-05` (los 3 meses más recientes completos).

---

## Parámetro `--lookback-months`

Controla cuántos meses hacia atrás se usan, contando desde `reference_date` (inclusive).

| `--reference-date` | `--lookback-months` | Meses usados | Sugerencia para |
|---|---|---|---|
| `2026-02` | 3 | 2025-12, 2026-01, 2026-02 | marzo 2026 |
| `2026-03` | 3 | 2026-01, 2026-02, 2026-03 | abril 2026 |
| `2026-04` | 3 | 2026-02, 2026-03, 2026-04 | mayo 2026 |
| `2026-05` | 3 | 2026-03, 2026-04, 2026-05 | junio 2026 |
| `2026-05` | *(omitido)* | 2025-12 → 2026-05 (todos) | junio 2026 |

---

## Tratamientos de ceros (A / B / C)

Cuando un mes tiene `monthly_total = $0`, el modelo puede tratarlo de tres formas:

| Treatment | Nombre | Comportamiento | Cuándo usar |
|---|---|---|---|
| **A** | `include_zeros` | El $0 entra como dato real en la serie | Categorías de gasto regular; un mes sin gasto reduce la sugerencia |
| **B** | `exclude_zeros` | Se eliminan los meses con $0 — solo se promedian los meses con gasto real | Categorías ocasionales (viajes, regalos); un mes sin gasto es "ausencia", no "$0" |
| **C** | `epsilon_replace` | Los $0 se reemplazan por $0.01 (epsilon) | Técnico — mantiene la serie continua para métodos que requieren valores > 0; resultado casi igual a A |

> **Impacto en gating:** La gating (mínimo de meses con gasto positivo) siempre se evalúa con los datos **pre-treatment**. Si hay < 2 meses con gasto real, el modelo devuelve `null` para cualquier tratamiento.

**Regla `null`:**
- Treatment **B**: si al eliminar ceros quedan < 2 meses → `null`
- Treatment **A/C**: si todos los meses son $0 → sugerencia = **$0.00** (no null), porque los datos sí existen

---

## Métodos de cálculo

| Método | Cómo pondera los meses | Detecta tendencia | Mejor con |
|---|---|---|---|
| **WMA** | Pesos lineales crecientes: mes más reciente = peso mayor | No | Series estables, pocos datos |
| **EWMA** | Pesos exponenciales (decaimiento suave, `span=3`) | Parcialmente | Series con cambios graduales |
| **Holt-Winters (HW)** | Ajusta nivel + tendencia explícitamente | Sí | Series con dirección clara; necesita ≥ 4 meses |

---

## Resultados por ventana deslizante

> **Leyenda:**  
> `**$0** ⚠` = mes con gasto cero (afecta el cálculo según treatment)  
> `—` = `null` (gating: < 2 meses con gasto positivo en la ventana)  
> `*null*` = Treatment B excluyó todos los meses disponibles  
> **`$X.XX`** = sugerencia emitida

---

### Ventana 2025-12 → 2026-02  ·  Sugerencia para 2026-03 (marzo)

Meses analizados: `2025-12` | `2026-01` | `2026-02`

| Cuenta | Categoría | `2025-12` | `2026-01` | `2026-02` | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A |
|---|---|---|---|---|---|---|---|---|---|
| `EXT2` | Pets | $45 | $26 | **$0** ⚠ | **$16.11** | **$32.23** | **$16.12** | **$17.75** | **$0.00** |
| `EXT2` | Entertainment & Leisure | $54 | **$0** ⚠ | $61 | **$39.44** | **$58.59** | **$39.44** | **$43.94** | **$45.05** |
| `EXT22` | Travel & Trips | $1014 | $1182 | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Shopping | $247 | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Gas | $67 | $96 | $75 | **$81.03** | **$81.03** | **$81.03** | **$78.58** | **$87.91** |
| `SYN001` | Home & Rent | $1268 | **$0** ⚠ | $1127 | **$774.86** | **$1174.06** | **$774.86** | **$880.54** | **$657.19** |
| `SYN004` | Gas | **$0** ⚠ | **$0** ⚠ | $62 | **$30.93** | **$61.86** | **$30.93** | **$30.93** | **$82.48** |
| `INT31880` | Education | $251 | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `SYN003` | Food & Dining | $93 | $75 | $219 | **$150.09** | **$150.09** | **$150.09** | **$151.66** | **$255.06** |
| `SYN005` | Health & Fitness | $26 | $112 | **$0** ⚠ | **$41.67** | **$83.34** | **$41.67** | **$34.44** | **$20.41** |

---

### Ventana 2026-01 → 2026-03  ·  Sugerencia para 2026-04 (abril)

Meses analizados: `2026-01` | `2026-02` | `2026-03`

| Cuenta | Categoría | `2026-01` | `2026-02` | `2026-03` | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A |
|---|---|---|---|---|---|---|---|---|---|
| `EXT2` | Pets | $26 | **$0** ⚠ | $117 | **$62.69** | **$86.44** | **$62.69** | **$64.83** | **$138.63** |
| `EXT2` | Entertainment & Leisure | **$0** ⚠ | $61 | $99 | **$69.62** | **$86.07** | **$69.63** | **$64.56** | **$151.87** |
| `EXT22` | Travel & Trips | $1182 | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Shopping | **$0** ⚠ | **$0** ⚠ | $68 | — | — | — | — | — |
| `EXT22` | Gas | $96 | $75 | $50 | **$66.40** | **$66.40** | **$66.40** | **$68.17** | **$27.99** |
| `SYN001` | Home & Rent | **$0** ⚠ | $1127 | $608 | **$679.44** | **$780.70** | **$679.44** | **$585.52** | **$1185.73** |
| `SYN004` | Gas | **$0** ⚠ | $62 | $87 | **$64.18** | **$78.70** | **$64.18** | **$59.03** | **$136.78** |
| `INT31880` | Education | **$0** ⚠ | **$0** ⚠ | $213 | — | — | — | — | — |
| `SYN003` | Food & Dining | $75 | $219 | **$0** ⚠ | **$85.54** | **$171.08** | **$85.55** | **$73.47** | **$23.43** |
| `SYN005` | Health & Fitness | $112 | **$0** ⚠ | **$0** ⚠ | **$18.71** | **$112.25** | **$18.72** | **$28.06** | **$0.00** |

---

### Ventana 2026-02 → 2026-04  ·  Sugerencia para 2026-05 (mayo)

Meses analizados: `2026-02` | `2026-03` | `2026-04`

| Cuenta | Categoría | `2026-02` | `2026-03` | `2026-04` | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A |
|---|---|---|---|---|---|---|---|---|---|
| `EXT2` | Pets | **$0** ⚠ | $117 | $62 | **$70.12** | **$80.51** | **$70.12** | **$60.38** | **$122.09** |
| `EXT2` | Entertainment & Leisure | $61 | $99 | $146 | **$116.06** | **$116.06** | **$116.06** | **$112.91** | **$187.07** |
| `EXT22` | Travel & Trips | **$0** ⚠ | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Shopping | **$0** ⚠ | $68 | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Gas | $75 | $50 | **$0** ⚠ | **$29.36** | **$58.72** | **$29.36** | **$31.44** | **$0.00** |
| `SYN001` | Home & Rent | $1127 | $608 | $1138 | **$959.31** | **$959.31** | **$959.31** | **$1002.60** | **$968.42** |
| `SYN004` | Gas | $62 | $87 | $110 | **$94.27** | **$94.27** | **$94.27** | **$92.16** | **$134.25** |
| `INT31880` | Education | **$0** ⚠ | $213 | **$0** ⚠ | — | — | — | — | — |
| `SYN003` | Food & Dining | $219 | **$0** ⚠ | $51 | **$62.02** | **$107.07** | **$62.02** | **$80.30** | **$0.00** |
| `SYN005` | Health & Fitness | **$0** ⚠ | **$0** ⚠ | **$0** ⚠ | **$0.00** | *null* | **$0.01** | **$0.00** | **$0.00** |

---

### Ventana 2026-03 → 2026-05  ·  Sugerencia para 2026-06 (junio)

Meses analizados: `2026-03` | `2026-04` | `2026-05`

| Cuenta | Categoría | `2026-03` | `2026-04` | `2026-05` | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A |
|---|---|---|---|---|---|---|---|---|---|
| `EXT2` | Pets | $117 | $62 | **$0** ⚠ | **$40.26** | **$80.51** | **$40.26** | **$44.80** | **$0.00** |
| `EXT2` | Entertainment & Leisure | $99 | $146 | **$0** ⚠ | **$65.13** | **$130.26** | **$65.14** | **$61.18** | **$0.00** |
| `EXT22` | Travel & Trips | **$0** ⚠ | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Shopping | $68 | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `EXT22` | Gas | $50 | **$0** ⚠ | $41 | **$29.13** | **$44.44** | **$29.13** | **$33.33** | **$21.68** |
| `SYN001` | Home & Rent | $608 | $1138 | $1243 | **$1102.19** | **$1102.19** | **$1102.19** | **$1057.99** | **$1631.94** |
| `SYN004` | Gas | $87 | $110 | $47 | **$74.66** | **$74.66** | **$74.66** | **$72.76** | **$41.27** |
| `INT31880` | Education | $213 | **$0** ⚠ | **$0** ⚠ | — | — | — | — | — |
| `SYN003` | Food & Dining | **$0** ⚠ | $51 | $49 | **$41.27** | **$49.37** | **$41.27** | **$37.03** | **$81.76** |
| `SYN005` | Health & Fitness | **$0** ⚠ | **$0** ⚠ | $80 | **$39.80** | **$79.61** | **$39.81** | **$39.80** | **$106.15** |

---

## Análisis de casos con ceros

### Caso 1 — Zero al final: `EXT2 / Pets`

```
2025-12: $45   2026-01: $26   2026-02: $0 ⚠   →  sugerencia marzo
2026-01: $26   2026-02: $0 ⚠  2026-03: $117  →  sugerencia abril
2026-02: $0 ⚠  2026-03: $117  2026-04: $62   →  sugerencia mayo
2026-03: $117  2026-04: $62   2026-05: $0 ⚠   →  sugerencia junio
```

| Ventana | WMA-A | WMA-B | Diferencia A→B | Observación |
|---|---|---|---|---|
| dic/ene/feb | $16.11 | $32.23 | **+$16.12** | Feb=$0 recibe peso 50% en A, lo hunde a la mitad |
| ene/feb/mar | $62.69 | $86.44 | **+$23.75** | Feb=$0 en posición media; B sube notablemente |
| feb/mar/abr | $70.12 | $80.51 | +$10.39 | Feb=$0 en posición antigua (peso 17%); impacto menor |
| mar/abr/may | $40.26 | $80.51 | **+$40.25** | May=$0 en posición reciente (peso 50%); A cae a la mitad de B |

**Conclusión:** Un $0 en el mes más reciente (peso 50% en WMA) **parte la sugerencia a la mitad** vs Treatment B. Si el cero es un mes ocasional sin gasto (no ausencia de cuenta), Treatment B da la sugerencia más fiel al patrón real.

---

### Caso 2 — Categoría estacional: `EXT22 / Travel & Trips`

```
2025-12: $1014   2026-01: $1182   2026-02: $0 ⚠   2026-03: $0 ⚠   2026-04: $0 ⚠   2026-05: $0 ⚠
```

Resultado en **todas las ventanas**: `—` (null) en A, B y C.

**¿Por qué?** La cuenta gastó en viajes solo en dic y ene. Dentro de cualquier ventana de 3 meses que incluya feb en adelante, quedan < 2 meses con gasto positivo → **gating bloquea la sugerencia**. Esto es correcto: con una ventana de 3 meses no hay suficiente historia reciente para sugerir un presupuesto de viajes.

**Implicación de diseño:** Para categorías estacionales o de gasto esporádico, una ventana corta (lookback=3) produce más nulls. Usar `--lookback-months 6` o mayor para capturar el ciclo completo.

---

### Caso 3 — Zeros al inicio con tendencia creciente: `SYN004 / Gas`

```
2025-12: $0 ⚠   2026-01: $0 ⚠   2026-02: $62   2026-03: $87   2026-04: $110   2026-05: $47
```

| Ventana | Meses | WMA-A | WMA-B | HW-A | Observación |
|---|---|---|---|---|---|
| dic/ene/feb | $0/$0/$62 | $30.93 | $61.86 | $82.48 | B=A×2 (solo 1 mes real, peso completo); HW proyecta tendencia al alza |
| ene/feb/mar | $0/$62/$87 | $64.18 | $78.70 | $136.78 | Gas creció; HW sobre-proyecta con 2 puntos |
| feb/mar/abr | $62/$87/$110 | $94.27 | $94.27 | $134.25 | Sin zeros → A=B; HW sigue la tendencia alcista |
| mar/abr/may | $87/$110/$47 | $74.66 | $74.66 | $41.27 | Caída en mayo; HW proyecta tendencia bajista |

**Conclusión:** Cuando el usuario empieza a usar una categoría nueva (zeros al inicio), Treatment B da la sugerencia más realista. Holt-Winters con solo 2-3 puntos reales produce proyecciones extremas en ambas direcciones.

---

### Caso 4 — Zero intercalado en el último mes: `SYN003 / Food & Dining`

```
2026-01: $75   2026-02: $219   2026-03: $0 ⚠   2026-04: $51   2026-05: $49
```

| Ventana | Meses | WMA-A | WMA-B | Diferencia | Observación |
|---|---|---|---|---|---|
| dic/ene/feb | $93/$75/$219 | $150.09 | $150.09 | $0 | Sin zeros → idénticos |
| ene/feb/mar | $75/$219/$0 | $85.54 | $171.08 | **+$85.54** | Mar=$0 en posición reciente; B duplica a A |
| feb/mar/abr | $219/$0/$51 | $62.02 | $107.07 | +$45.05 | HW=$0 — descarta la tendencia y colapsa |
| mar/abr/may | $0/$51/$49 | $41.27 | $49.37 | +$8.10 | Mar=$0 en posición antigua; impacto menor |

---

### Caso 5 — Todos los meses en cero: `SYN005 / Health & Fitness`

```
Ventana feb/mar/abr: $0 ⚠ / $0 ⚠ / $0 ⚠
```

| Treatment | Resultado | Explicación |
|---|---|---|
| A | **$0.00** | Incluye los tres ceros; la media ponderada de $0 = $0 |
| B | **null** | Elimina todos los meses → serie vacía → null |
| C | **$0.01** | Reemplaza $0 por $0.01 → la serie existe pero el resultado es mínimo |

**Regla práctica:** Treatment B es el único que devuelve `null` cuando el usuario genuinamente no gastó nada en una categoría durante toda la ventana. Para los demás, recibe una sugerencia de $0 o $0.01 — que puede ser confusa en el UI.

---

## Guía de elección: treatment y método por caso de uso

| Situación | Treatment recomendado | Método recomendado | Razón |
|---|---|---|---|
| Gasto regular (supermercado, alquiler) | **A** | WMA | Zeros son reales; método estable |
| Categoría ocasional (viajes, regalos) | **B** | WMA | Zeros = "no viajé", no "$0 gastado" |
| Serie con tendencia clara (gas creciente) | **A** | EWMA o HW con ≥5 meses | HW proyecta bien con datos suficientes |
| Historial muy corto (1-2 meses reales) | **B** | WMA | Evita sugestiones infladas por zeros con peso alto |
| Todos los meses en cero | **B** → null | — | No emitir sugerencia; mostrar mensaje de falta de historial |

---

## Cómo reproducir

```bash
# Desde .worktrees/DATA-1137/

# Ventana para sugerir mayo (usando feb/mar/abr):
python3 scripts/run_methods.py \
  --method wma --treatment A \
  --reference-date 2026-04 --lookback-months 3

# Comparar treatments para una categoría con ceros:
for t in A B C; do
  echo "=== Treatment $t ==="
  python3 scripts/run_methods.py \
    --method wma --treatment $t \
    --reference-date 2026-04 --lookback-months 3 2>/dev/null \
  | python3 -c "
import json,sys
data=json.load(sys.stdin)
for r in data:
    if r['idaccount']=='EXT2' and r['defaultcategory']=='Pets':
        print(f'  suggested={r[\"suggested_amount\"]}  basis={r[\"basis\"]}')
"
done

# Todas las ventanas deslizantes, todos los métodos y treatments:
for ref in 2026-02 2026-03 2026-04 2026-05; do
  for method in wma ewma holt_winters; do
    for treatment in A B C; do
      python3 scripts/run_methods.py \
        --method $method --treatment $treatment \
        --reference-date $ref --lookback-months 3 \
        --output /tmp/sb_${ref}_${method}_${treatment}.json 2>/dev/null
    done
  done
done
```

---

## Próximos pasos (DATA-1138)

La **elección automática de treatment por categoría** — y la validación formal de cuál produce mayor `acceptance_rate` — está en scope de DATA-1138. Este documento es análisis exploratorio previo a la validación A/B.

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
