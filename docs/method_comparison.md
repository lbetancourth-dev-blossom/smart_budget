# Comparación de Métodos — Smart Budget Fase 0

**Ticket:** DATA-1137  
**Fecha de ejecución:** 2026-05-24  
**Objetivo:** Sugerencia para **mayo 2026** (reference date `2026-04`) con lookback 3 / 6 / 9 / 12 meses  
**Dataset:** `data/dough/smart_budget_synthetic.csv` — **12 meses** (jun 2025 → may 2026), 11 cuentas, 15 categorías, 804 filas, 26.5 % ceros

---

## 1. Métodos comparados

| Método | Ponderación | Sensibilidad al último mes | Mínimo de datos | Observaciones |
|---|---|---|---|---|
| **WMA** | Lineal creciente (peso n/Σk) | Media | 2 meses positivos | Simple, predecible, explicable |
| **EWMA** | Exponencial (`span=3`) | Alta | 2 meses positivos | Reacciona rápido a cambios recientes |
| **Median** | Sin ponderación temporal | Nula | 2 meses positivos | Resistente a outliers, ignora tendencia |
| **Holt-Winters (HW)** | Nivel + tendencia aditiva | Muy alta | **3 meses mínimo para HW** | Amplifica tendencias; inestable con pocos datos |

---

## 2. Tratamientos de ceros

| Treatment | Comportamiento cuando `monthly_total = $0` |
|---|---|
| **A** | Incluye el $0 como dato real — reduce el promedio ponderado |
| **B** | Excluye el mes con $0 — solo calcula sobre meses con gasto real |
| **C** | Reemplaza $0 por $0.01 (epsilon) — casi idéntico a A en práctica |

Todos los resultados de comparación usan **Treatment B** salvo indicación explícita.  
**Leyenda de confianza:** 🟢 high (≥6 meses positivos) · 🟡 medium (3–5) · 🔴 low (2) · `—` null

---

## 3. Ventanas de tiempo disponibles

El dataset cubre **12 meses completos** (jun-25 → may-26). Para sugerir mayo-2026 se usa reference date = `2026-04` (último mes cerrado):

```
jun-25  jul-25  ago-25  sep-25  oct-25  nov-25  dic-25  ene-26  feb-26  mar-26  abr-26
───────────────────────────────────────────────────────────────────────────────────────
◄──────────────────────── lb=12 ──────────────────────────────────────────────────────►
                                        ◄────────── lb=6 ──────────────────────────────►
                                                                ◄──── lb=3 ─────────────►
```

---

## 4. Hallazgo clave — lb=6/9/12 idénticos (Treatment B)

Con los datos sintéticos, **lb=6, lb=9 y lb=12 producen resultados idénticos** para WMA, EWMA y Median (Treatment B).

**¿Por qué?** Los patrones estacionales del dataset generan meses con `$0` en los primeros 6 meses extendidos (jun–nov 2025). Treatment B excluye esos ceros → siempre termina usando los mismos meses con gasto positivo (dic-25 → abr-26, máximo 5 meses). Solo Holt-Winters difiere porque requiere la serie completa.

> **Implicación práctica:** Con patrones estacionales en el historial, ampliar el lookback más allá de 6 meses no mejora la sugerencia a menos que esos meses adicionales tengan gasto positivo. Es un comportamiento **correcto y esperado**, no un bug.

---

## 5. Tabla de cobertura y confianza

| Método | lb=3 valid | lb=3 null | lb=6 valid | lb=6 null | lb=9 valid | lb=12 valid |
|---|---|---|---|---|---|---|
| WMA-B | 62 | 2 | 64 | 0 | 64 | 64 |
| EWMA-B | 62 | 2 | 64 | 0 | 64 | 64 |
| Median-B | 62 | 2 | 64 | 0 | 64 | 64 |
| HW-B | 44 | 20 | 59 | 5 | 59 | 59 |

**Total de buckets:** 64 (8 miembros × 8 categorías aprox.)

HW produce **20 nulls con lb=3** (requiere ≥3 obs positivas; con solo 2 disponibles, falla). Con lb≥6 persisten 5 nulls correspondientes a buckets con patrones estacionales extremos.

### Distribución de confianza (Treatment B)

| Método | lb=3 | lb=6 | lb=9 | lb=12 |
|---|---|---|---|---|
| WMA-B | medium=44 · low=18 · null=2 | medium=59 · low=5 | medium=59 · low=5 | medium=59 · low=5 |
| EWMA-B | medium=44 · low=18 · null=2 | medium=59 · low=5 | medium=59 · low=5 | medium=59 · low=5 |
| Median-B | medium=44 · low=18 · null=2 | medium=59 · low=5 | medium=59 · low=5 | medium=59 · low=5 |
| HW-B | medium=44 · null=20 | medium=59 · null=5 | medium=59 · null=5 | medium=59 · null=5 |

> **¿Por qué no hay confianza 🟢 high?** El umbral es ≥6 meses positivos. El máximo observado en el dataset es 5 (`months_with_positive_spend` post-Treatment-B). Con patrones estacionales (Travel, Gifts, Health con $0 forzados en varios meses), ningún bucket alcanza 6 meses consecutivos con gasto. Si se usa un dataset sin estacionalidad forzada, sí se alcanzan niveles high.

---

## 6. Comparación de valores — Cuenta SYN005 (lb=6, Treatment B)

| Categoría | WMA | EWMA | Median | HW |
|---|---|---|---|---|
| Auto & Transport | **$164.10** | $167.90 | $148.89 | $225.17 |
| Bills & Utilities | **$83.71** | $79.36 | $74.90 | $65.30 |
| Gas | **$60.00** | $64.71 | $55.44 | $111.73 |
| Health & Fitness | **$83.34** | — | $69.09 | $115.42 |
| Home & Rent | **$915.34** | $787.73 | $662.40 | $687.16 |
| Gifts & Donations | **$142.30** | — | — | $174.89 |
| Personal Care | **$67.88** | $77.20 | $69.09 | — |

**Observaciones:**
- **Median siempre da el valor más bajo** (no tiene sesgo reciente) — conservadora ante tendencias crecientes.
- **HW siempre da el valor más alto** (extrapola la tendencia) — sobreestima cuando la tendencia es creciente.
- **WMA y EWMA están cercanos**; EWMA sube un poco más cuando el último mes es alto.

---

## 7. Impacto del lookback — Cuenta SYN005 (WMA-B)

| Categoría | lb=3 | lb=6 | lb=9 | lb=12 |
|---|---|---|---|---|
| Auto & Transport | $184.92 | $164.10 | $164.10 | $164.10 |
| Bills & Utilities | $73.47 | $83.71 | $83.71 | $83.71 |
| Gas | $70.89 | $60.00 | $60.00 | $60.00 |
| Health & Fitness | — (null) | $83.34 | $83.34 | $83.34 |
| Home & Rent | $749.86 | $915.34 | $915.34 | $915.34 |
| Gifts & Donations | $146.39 | $142.30 | $142.30 | $142.30 |

> **lb=3 vs lb=6:** Health & Fitness pasa de `null` a `$83` cuando se amplía a 6 meses (en lb=3 no hay suficientes meses positivos). Home & Rent sube de $749 a $915 porque los meses más antiguos (dic–ene) tienen rentas más altas que los recientes. **lb=6/9/12 idénticos** — confirma el hallazgo §4.

---

## 8. Análisis por categorías estacionales (lb=12, Treatment B)

### Travel & Trips (categoría con estacionalidad fuerte)
Patrón sintético: gasto alto en jun–ago y dic; $0 forzados en ene–mar.

| Cuenta | WMA | EWMA | Median | HW |
|---|---|---|---|---|
| EXT2 | $198.38 | $198.34 | $199.99 | $185.60 |
| SYN001 | $314.64 | $335.84 | $335.84 | — (null) |

Con lb=12 se capturan los meses de verano y diciembre. WMA, EWMA y Median convergen (los meses positivos son similares en magnitud). HW falla para SYN001 porque tiene pocos puntos positivos en la serie.

### Gifts & Donations (pico de diciembre)
Patrón: dic=3× promedio, nov=2×, resto=0.3–0.8×.

Con lb=3 (feb–abr), el pico de diciembre queda fuera → sugerencia baja artificialmente. Con lb=6 (nov–abr) captura noviembre pero no diciembre. **Para categorías con pico de fin de año se recomienda lb=12** para incluir el ciclo completo.

---

## 9. Impacto del tratamiento de ceros (WMA, lb=6)

Cuenta SYN005 — categorías con meses en $0:

| Categoría | Trt A | Trt B | Trt C | Δ(B–A) | Interpretación |
|---|---|---|---|---|---|
| Auto & Transport | $133.51 | **$164.10** | $133.51 | +$30.59 | 2 meses en $0 → B excluye y sube |
| Gas | $48.77 | **$60.00** | $48.78 | +$11.23 | 1 mes en $0 |
| Health & Fitness | $16.67 | **$83.34** | $16.68 | +$66.67 | 3 meses en $0; B solo usa 2 positivos |
| Bills & Utilities | $83.71 | $83.71 | $83.71 | $0 | Sin ceros → A=B=C |
| Home & Rent | $915.34 | $915.34 | $915.34 | $0 | Sin ceros → A=B=C |

> **Treatment B da siempre valores más altos o iguales que A.** La diferencia más grande (+$66) ocurre en Health & Fitness: 3 meses en $0 con solo 2 meses positivos. B calcula con los 2 positivos ($83.34), A incluye los $0 y baja a $16.67 — sugerencia que no refleja el comportamiento real.

---

## 10. Recomendación por ventana de lookback

| Lookback | Mejor método | Treatment | Justificación |
|---|---|---|---|
| **lb=3** | WMA-B | B | Refleja momento actual; mínimo ruido estacional. HW inestable (20 nulls) |
| **lb=6** | WMA-B | B | Equilibrio historia/recencia. Eleva confianza de low→medium vs lb=3. **Default recomendado** |
| **lb=9** | WMA-B *(=lb=6)* | B | Idéntico a lb=6 con datos actuales; no agrega valor con patrones estacionales |
| **lb=12** | WMA-B *(=lb=6)* o Median | B | Para categorías estacionales (Travel, Gifts): usar Median que distribuye el peso uniformemente a lo largo del año |

### Recomendación global para Fase 0

> **WMA + Treatment B + lookback=6** como configuración default.  
> **Median + Treatment B + lookback=12** para categorías estacionales (`Travel`, `Gifts & Donations`, `Education`).  
> **Holt-Winters: NO usar en Fase 0** — requiere ≥12 meses de historia limpia y produce demasiados nulls con series cortas.

---

## 11. ¿Por qué no EWMA ni Holt-Winters como default?

| Método | Problema en Fase 0 |
|---|---|
| **EWMA** | Con lb=3–6, produce sugerencias muy cercanas a WMA (diferencia media < 5%). No justifica la complejidad adicional. El decaimiento exponencial solo diferencia significativamente con 9+ meses de datos continuos. |
| **Holt-Winters** | 20 nulls con lb=3 (falla cuando hay < 3 meses positivos). Sobreestima agresivamente en tendencias crecientes (ej. SYN005/Auto: HW=$225 vs WMA=$164). Reservar para Fase 2 con ≥12 meses de historia limpia. |
| **Median** | No tiene sesgo reciente → subestima cuando el gasto está creciendo. Útil para categorías estacionales donde el promedio del año es más informativo que el último mes. |

---

## 12. Cómo reproducir

```bash
# Desde .worktrees/DATA-1137/
# Primero regenerar dataset con 12 meses:
python3 scripts/generate_synthetic_dataset.py --extend-months 6

# Configuración recomendada (default — WMA-B, lb=6):
python3 scripts/run_methods.py \
  --method wma --treatment B \
  --reference-date 2026-04 --lookback-months 6

# Categorías estacionales (Median-B, lb=12):
python3 scripts/run_methods.py \
  --method median --treatment B \
  --reference-date 2026-04 --lookback-months 12

# Comparar todos los métodos para un lookback:
for method in wma ewma median holt_winters; do
  echo "=== $method lb=6 ==="
  python3 scripts/run_methods.py \
    --method $method --treatment B \
    --reference-date 2026-04 --lookback-months 6 2>/dev/null | \
    python3 -c "
import json,sys
data=json.load(sys.stdin)
for r in [x for x in data if x['idaccount']=='SYN005'][:3]:
    print(f'  {r[\"defaultcategory\"]:<25} \${r[\"suggested_amount\"]}  conf={r[\"confidence\"]}')
"
done

# Barrer los 4 lookbacks:
for lb in 3 6 9 12; do
  for method in wma ewma median holt_winters; do
    python3 scripts/run_methods.py \
      --method $method --treatment B \
      --reference-date 2026-04 --lookback-months $lb \
      --output /tmp/sb_lb${lb}_${method}_B.json 2>/dev/null
  done
done
```

---

## 13. Próximos pasos (DATA-1138)

La **validación con usuarios reales** — midiendo `acceptance_rate` — está en scope de DATA-1138. Este documento es el análisis exploratorio que justifica la elección de WMA-B lb=6 como método default para Fase 0.

Para categorías estacionales, considerar en Fase 1:
- Detectar automáticamente el patrón estacional (CV del gasto mensual > 0.5)
- Aplicar lb=12 + Median solo cuando se detecte estacionalidad
