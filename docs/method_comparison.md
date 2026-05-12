# Comparación de Métodos — Smart Budget Fase 0

**Ticket:** DATA-1137  
**Fecha de ejecución:** 2026-05-12  
**Objetivo:** Sugerencia para **mayo 2026** con lookback variable (3, 4, 5, 6 meses)  
**Reference date:** `2026-04` — último mes completo antes de mayo  
**Dataset:** `data/dough/smart_budget_synthetic.csv` — 6 meses (2025-12 → 2026-05), 11 cuentas

---

## Datos disponibles para el cálculo (dic 2025 → abr 2026)

```
2025-12  2026-01  2026-02  2026-03  2026-04   ← meses usados para sugerir mayo
────────────────────────────────────────────
lb=3:                      ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓
lb=4:             ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓
lb=5:    ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓
lb=6:    ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓  ← igual a lb=5 (nov-25 no existe)
```

> **lb=6 produce resultados idénticos a lb=5.** El dataset comienza en dic-2025 (5 meses hasta abr-2026). Pedirle lb=6 no da error — el modelo usa los meses que existen dentro de la ventana.

---

## Tratamientos de ceros

| Treatment | Comportamiento cuando `monthly_total = $0` |
|---|---|
| **A** | Incluye el $0 como dato real — reduce el promedio ponderado |
| **B** | Elimina el mes con $0 — solo promedia meses con gasto real; si quedan < 2 meses → `null` |
| **C** | Reemplaza $0 por $0.01 (epsilon) — resultado casi idéntico a A |

**Leyenda de tablas:** 🟢 = high (≥6 meses positivos) · 🟡 = medium (3-5) · 🔴 = low (2) · `—` = null (gating)

---

## Métodos comparados

| | WMA | EWMA | HW (Holt-Winters) |
|---|---|---|---|
| **Ponderación** | Lineal creciente | Exponencial (`span=3`) | Nivel + tendencia |
| **Sensibilidad último mes** | Media | Alta | Muy alta |
| **Con series cortas (3m)** | Estable | Estable | Volátil |
| **Con ceros en serie** | Baja la sugerencia | Baja la sugerencia | Puede colapsar a $0 |

---

## Resultados por bucket — Mayo 2026

---

#### `EXT2` / Pets
Historial: `2025-12`=$45 · `2026-01`=$26 · `2026-02`=**$0**⚠ · `2026-03`=$117 · `2026-04`=$62

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (1 cero) | $70.12 | $80.51 | $70.12 | $60.38 | $122.09 | 🔴 low |
| 4m | ene/feb/mar/abr (1 cero) | $62.56 | $74.40 | $62.56 | $63.60 | $107.92 | 🟡 medium |
| 5m | dic/ene/feb/mar/abr (1 cero) | $58.38 | $69.66 | $58.39 | $64.82 | $87.61 | 🟡 medium |
| 6m→5m | *(idéntico a lb=5)* | $58.38 | $69.66 | $58.39 | $64.82 | $87.61 | 🟡 medium |

**Análisis:** El cero de feb-2026 siempre está en la ventana (lb≥3). Con lb=3 recibe peso 17% (posición más antigua) y la sugerencia sube respecto a lb=4 donde entra ene ($26). WMA-B da ~$10-12 más alto al ignorar el mes sin gasto. HW sobreestima en todos los lookbacks.

---

#### `EXT2` / Entertainment & Leisure
Historial: `2025-12`=$54 · `2026-01`=**$0**⚠ · `2026-02`=$61 · `2026-03`=$99 · `2026-04`=$146

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (0 ceros) | $116.06 | $116.06 | $116.06 | $112.91 | $187.07 | 🟡 medium |
| 4m | ene/feb/mar/abr (1 cero) | $100.20 | $116.06 | $100.20 | $105.30 | $195.40 | 🟡 medium |
| 5m | dic/ene/feb/mar/abr (1 cero) | $90.78 | $105.61 | $90.78 | $108.68 | $156.71 | 🟡 medium |
| 6m→5m | *(idéntico a lb=5)* | $90.78 | $105.61 | $90.78 | $108.68 | $156.71 | 🟡 medium |

**Análisis:** lb=3 excluye el cero de ene → todos los tratamientos dan lo mismo ($116). Con lb≥4 el cero entra y separa A de B. La tendencia es claramente **creciente** ($54→$146), por lo que lb=3 captura mejor el momento actual. HW proyecta la tendencia demasiado al alza ($187-195).

---

#### `EXT22` / Travel & Trips
Historial: `2025-12`=$1,014 · `2026-01`=$1,182 · `2026-02`=**$0**⚠ · `2026-03`=**$0**⚠ · `2026-04`=**$0**⚠

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 4m | ene/feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 5m | dic/ene/feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 6m→5m | *(idéntico a lb=5)* | — | — | — | — | — | — |

**Análisis:** Solo 2 meses con gasto en cualquier ventana disponible. Gating bloquea correctamente: < 2 meses positivos en los últimos 3-5 meses. Esta es una **categoría estacional** — el usuario viajó solo en dic/ene. Para sugerirle presupuesto de viaje se necesita un lookback de 12+ meses. Con datos actuales: **`null` es la respuesta correcta**.

---

#### `EXT22` / Shopping
Historial: `2025-12`=$247 · `2026-01`=**$0**⚠ · `2026-02`=**$0**⚠ · `2026-03`=$68 · `2026-04`=**$0**⚠

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (2 ceros) | — | — | — | — | — | — |
| 4m | ene/feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 5m | dic/ene/feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 6m→5m | *(idéntico a lb=5)* | — | — | — | — | — | — |

**Análisis:** Solo 2 meses con gasto positivo en todo el historial (dic y mar), nunca consecutivos. Gating bloquea en todos los lookbacks. Patrón de **compra esporádica** — no hay suficiente regularidad para sugerir. `null` correcto.

---

#### `EXT22` / Gas
Historial: `2025-12`=$67 · `2026-01`=$96 · `2026-02`=$75 · `2026-03`=$50 · `2026-04`=**$0**⚠

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (1 cero) | $29.36 | $58.72 | $29.36 | $31.44 | **$0.00** | 🔴 low |
| 4m | ene/feb/mar/abr (1 cero) | $39.84 | $66.40 | $39.85 | $34.08 | **$0.00** | 🟡 medium |
| 5m | dic/ene/feb/mar/abr (1 cero) | $45.85 | $68.78 | $45.86 | $32.25 | **$0.00** | 🟡 medium |
| 6m→5m | *(idéntico a lb=5)* | $45.85 | $68.78 | $45.86 | $32.25 | **$0.00** | 🟡 medium |

**Análisis:** Abr-2026=$0 entra siempre con peso alto (mes más reciente). WMA-A cae a ~la mitad de WMA-B porque pondera el $0 con peso 50% (lb=3) o 40% (lb=4). El historial real ($67-$96) sugiere gasto real. HW proyecta $0 (detecta tendencia bajista hacia el cero). **WMA-B lb=5 ($68.78) es el más fiel al patrón histórico real.**

---

#### `SYN001` / Home & Rent
Historial: `2025-12`=$1,268 · `2026-01`=**$0**⚠ · `2026-02`=$1,127 · `2026-03`=$608 · `2026-04`=$1,138

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (0 ceros) | $959.31 | $959.31 | $959.31 | $1,002.60 | $968.42 | 🟡 medium |
| 4m | ene/feb/mar/abr (1 cero) | $862.83 | $959.31 | $862.83 | $861.72 | $1,441.69 | 🟡 medium |
| 5m | dic/ene/feb/mar/abr (1 cero) | $851.26 | $989.65 | $851.27 | $940.98 | $932.23 | 🟡 medium |
| 6m→5m | *(idéntico a lb=5)* | $851.26 | $989.65 | $851.27 | $940.98 | $932.23 | 🟡 medium |

**Análisis:** Ene-2026=$0 es anómalo (posiblemente mes sin pago registrado). lb=3 lo excluye → todos los tratamientos coinciden en ~$959. Con lb≥4 el cero entra y baja WMA-A a ~$862. HW con 4 puntos sobreestima ($1,441). **WMA-B lb=5 ($989) captura bien el comportamiento: alquiler cercano a $1,000/mes.**

---

#### `SYN004` / Gas
Historial: `2025-12`=**$0**⚠ · `2026-01`=**$0**⚠ · `2026-02`=$62 · `2026-03`=$87 · `2026-04`=$110

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (0 ceros) | $94.27 | $94.27 | $94.27 | $92.16 | $134.25 | 🟡 medium |
| 4m | ene/feb/mar/abr (1 cero) | $82.44 | $94.27 | $82.45 | $84.43 | $153.40 | 🟡 medium |
| 5m | dic/ene/feb/mar/abr (2 ceros) | $72.22 | $94.27 | $72.22 | $84.43 | $143.80 | 🟡 medium |
| 6m→5m | *(idéntico a lb=5)* | $72.22 | $94.27 | $72.22 | $84.43 | $143.80 | 🟡 medium |

**Análisis:** El usuario empezó a gastar en gas en feb-2026. Los ceros de dic y ene son **ausencia de la categoría** (no ceros reales) → Treatment B es el correcto. WMA-B da $94.27 en todos los lookbacks ≥3 porque excluye los ceros y siempre usa los mismos 3 meses con datos. La tendencia es creciente ($62→$87→$110); HW la amplifica demasiado ($134-153).

---

#### `INT31880` / Education
Historial: `2025-12`=$251 · `2026-01`=**$0**⚠ · `2026-02`=**$0**⚠ · `2026-03`=$213 · `2026-04`=**$0**⚠

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (2 ceros) | — | — | — | — | — | — |
| 4m | ene/feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 5m | dic/ene/feb/mar/abr (3 ceros) | — | — | — | — | — | — |
| 6m→5m | *(idéntico a lb=5)* | — | — | — | — | — | — |

**Análisis:** Solo 2 meses con gasto (dic y mar) en 5 meses. Gasto **trimestral/semestral** (matrícula, cuotas). Con lookback=3 solo hay 1 mes positivo (mar). Con lb≥4 hay 2, pero separados por 3 meses sin datos → gating bloquea. **`null` correcto**: para categorías educativas se recomienda lookback=12 o ventana de año fiscal.

---

#### `SYN003` / Food & Dining
Historial: `2025-12`=$93 · `2026-01`=$75 · `2026-02`=$219 · `2026-03`=**$0**⚠ · `2026-04`=$51

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (1 cero) | $62.02 | $107.07 | $62.02 | $80.30 | **$0.00** | 🔴 low |
| 4m | ene/feb/mar/abr (1 cero) | $71.69 | $111.00 | $71.70 | $62.20 | $13.66 | 🟡 medium |
| 5m | dic/ene/feb/mar/abr (1 cero) | $77.01 | $110.42 | $77.01 | $63.38 | $39.80 | 🟡 medium |
| 6m→5m | *(idéntico a lb=5)* | $77.01 | $110.42 | $77.01 | $63.38 | $39.80 | 🟡 medium |

**Análisis:** Mar-2026=$0 es el mes más reciente (peso 50% en lb=3). WMA-A lo penaliza severamente: $62 vs WMA-B $107. El pico de feb ($219) distorsiona WMA-B hacia arriba. El patrón real ($75-$93 sin el outlier de feb) sugiere un gasto de ~$70-80. **WMA-A lb=5 ($77) o EWMA-A lb=5 ($63) son los más estables.** HW colapsa a $0 con lb=3 (detecta falsa tendencia bajista).

---

#### `SYN005` / Health & Fitness
Historial: `2025-12`=$26 · `2026-01`=$112 · `2026-02`=**$0**⚠ · `2026-03`=**$0**⚠ · `2026-04`=**$0**⚠

| Lookback | Meses | WMA-A | WMA-B | WMA-C | EWMA-A | HW-A | Confianza |
|---|---|---|---|---|---|---|---|
| 3m | feb/mar/abr (3 ceros) | **$0.00** | — | $0.01 | **$0.00** | **$0.00** | 🔴 low |
| 4m | ene/feb/mar/abr (3 ceros) | $11.22 | $112.25 | $11.23 | $14.03 | **$0.00** | 🔴 low |
| 5m | dic/ene/feb/mar/abr (3 ceros) | $16.67 | $83.34 | $16.68 | $8.61 | **$0.00** | 🔴 low |
| 6m→5m | *(idéntico a lb=5)* | $16.67 | $83.34 | $16.68 | $8.61 | **$0.00** | 🔴 low |

**Análisis:** 3 meses consecutivos en $0 (feb-abr). El usuario dejó de gastar en salud. WMA-B lb=4 da $112 (solo usa ene, el único mes positivo en 4m) — **sobreestima** porque hay un solo dato. WMA-A lb=5 ($16.67) refleja mejor la realidad: el usuario gastó en dic y ene, pero lleva 3 meses a $0. Confianza 🔴 en todos los casos. La sugerencia más honesta: **null o $0** — el usuario probablemente canceló el gym.

---

## Resumen comparativo — Mayo 2026

| Bucket | lb=3 WMA-A | lb=4 WMA-A | lb=5 WMA-A | lb=5 WMA-B | Recomendado |
|---|---|---|---|---|---|
| EXT2 / Pets | $70.12 🔴 | $62.56 🟡 | $58.38 🟡 | $69.66 🟡 | WMA-B lb=5 |
| EXT2 / Entertainment | $116.06 🟡 | $100.20 🟡 | $90.78 🟡 | $105.61 🟡 | WMA-A lb=3 (tendencia ↑) |
| EXT22 / Travel | — | — | — | — | null (lookback ≥12) |
| EXT22 / Shopping | — | — | — | — | null (compra esporádica) |
| EXT22 / Gas | $29.36 🔴 | $39.84 🟡 | $45.85 🟡 | $68.78 🟡 | WMA-B lb=5 |
| SYN001 / Home & Rent | $959.31 🟡 | $862.83 🟡 | $851.26 🟡 | $989.65 🟡 | WMA-B lb=5 |
| SYN004 / Gas | $94.27 🟡 | $82.44 🟡 | $72.22 🟡 | $94.27 🟡 | WMA-B lb=3 (cat nueva) |
| INT31880 / Education | — | — | — | — | null (lookback ≥12) |
| SYN003 / Food & Dining | $62.02 🔴 | $71.69 🟡 | $77.01 🟡 | $110.42 🟡 | WMA-A lb=5 |
| SYN005 / Health | $0.00 🔴 | $11.22 🔴 | $16.67 🔴 | $83.34 🔴 | null (gasto cesado) |

---

## Recomendación de método — Fase 0

### Veredicto: **WMA + Treatment B + lookback=5**

Este es el mejor default para Fase 0, con las excepciones detalladas abajo.

| Dimensión | Evaluación |
|---|---|
| **Estabilidad** | WMA es el más predecible: pesos lineales, sin parámetros ocultos |
| **Ceros** | Treatment B ignora meses sin gasto → sugerencia más fiel al patrón real de gasto |
| **Lookback** | lb=5 usa toda la historia disponible hoy (5 meses); lb=6 es idéntico con estos datos |
| **Explicabilidad** | "Basado en tus últimos N meses con gasto en esta categoría" — claro para el usuario |
| **Confianza** | lb≥4 eleva la mayoría de buckets de 🔴 low a 🟡 medium |

### Excepciones por patrón de gasto

| Patrón detectado | Treatment | Lookback | Razón |
|---|---|---|---|
| Gasto **regular, sin ceros** | A o B (idéntico) | 5m | Sin diferencia; A es más simple |
| Gasto **con ceros ocasionales** | **B** | 5m | Cero = "no gasté ese mes", no dato real |
| Categoría **nueva** (ceros al inicio) | **B** | 3m | Solo usar los meses con actividad real |
| Tendencia **creciente clara** (≥3 meses seguidos ↑) | A | 3m | Ventana corta captura el momento actual |
| Categoría **estacional** (viajes, regalos) | B | ≥12m | Necesita un año completo de historia |
| **Todos los meses en $0** (gasto cesado) | B | cualquiera | → null; no emitir sugerencia |

### ¿Por qué no EWMA ni Holt-Winters como default?

| Método | Problema en Fase 0 |
|---|---|
| EWMA | Produce sugerencias similares a WMA con 3-5 meses. El decaimiento exponencial solo diferencia con 6+ meses. No agrega valor suficiente para justificar la complejidad de explicación al usuario |
| Holt-Winters | **No recomendado con lb < 6.** Con 3-4 puntos, proyecta tendencias extremas: colapsa a $0 ante un cero al final de la serie (Gas EXT22, Food SYN003) o sobreestima agresivamente (Entertainment +$70). Reservar para Fase 2 con 12+ meses de historia |

---

## Cómo reproducir

```bash
# Desde .worktrees/DATA-1137/

# Configuración recomendada (mayo, WMA-B, 5 meses):
python3 scripts/run_methods.py \
  --method wma --treatment B \
  --reference-date 2026-04 --lookback-months 5

# Comparar lookbacks para un bucket específico:
for lb in 3 4 5 6; do
  echo "=== lb=$lb ==="
  python3 scripts/run_methods.py \
    --method wma --treatment B \
    --reference-date 2026-04 --lookback-months $lb 2>/dev/null \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
for r in data:
    if r['idaccount'] == 'EXT22' and r['defaultcategory'] == 'Gas':
        b = r['basis']
        print(f'  {r[\"suggested_amount\"]}  conf={r[\"confidence\"]}  rango={b[\"period_range\"]}')
"
done

# Todas las combinaciones para análisis:
for lb in 3 4 5 6; do
  for method in wma ewma holt_winters; do
    for treatment in A B C; do
      python3 scripts/run_methods.py \
        --method $method --treatment $treatment \
        --reference-date 2026-04 --lookback-months $lb \
        --output /tmp/may_lb${lb}_${method}_${treatment}.json 2>/dev/null
    done
  done
done
```

---

## Próximos pasos (DATA-1138)

La **validación formal** de WMA-B lb=5 vs alternativas — midiendo `acceptance_rate` real en usuarios — está en scope de DATA-1138. Este documento es el análisis exploratorio pre-A/B que justifica la elección del método default.
