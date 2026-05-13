# Plan — DATA-1137: DS - Implementación de múltiples métodos

**Ticket:** https://blossomtechnology.atlassian.net/browse/DATA-1137  
**Branch:** `feat/DATA-1137`  
**Base:** `development`  
**Risk:** Medium  
**Estimate:** ~18h (M)  

---

## Problema y enfoque

El pipeline de Smart Budget (DATA-1136) calcula sugerencias con mediana simple. Este ticket
implementa tres métodos alternativos — WMA, EWMA, Holt-Winters — cada uno con tres variantes
de tratamiento de ceros (A/B/C). El output es JSON por bucket (member × category), compatible
con el contrato del endpoint `/smart-budget/suggestion` (DATA-1140).

La comparación cuantitativa entre métodos (MAE/RMSE/SMAPE) es scope de DATA-1138.

---

## DCR — Decisiones cerradas

### AI-closeable (10)

| # | Dimensión | Decisión | Fundamento |
|---|---|---|---|
| D-01 | Input | `prepare_smart_budget_data()` de `aggregator.py` — sin nueva ETL | `src/smart_budget/aggregator.py:96` |
| D-02 | Métodos en scope | WMA + EWMA + Holt-Winters. Prophet + Gradient Boosting = OUT (→ DATA-1139) | Jira 278741: "prioridad" |
| D-03 | EPSILON_DEFAULT | `EPSILON_DEFAULT = 0.01` — constante de módulo | Jira 278756 |
| D-04 | Basis fields | `months_with_zero` + `months_with_positive_spend` calculados sobre df PRE-treatment | Jira 278756 |
| D-05 | HW componentes | `ExponentialSmoothing(trend='add', seasonal=None)` — sin estacionalidad (gating mínimo=3 meses, insuficiente para seasonal=12) | `aggregator.py:apply_gating` |
| D-06 | Lookback window | Todos los meses del dataset hasta `reference_date` (inclusive), sin ventana fija | Jira 278741 |
| D-07 | WMA weights | Lineal creciente `[1, 2, ..., n]` normalizados sobre todos los meses disponibles | Definición estándar WMA |
| D-08 | statsmodels | Agregar `statsmodels>=0.14.0,<1.0.0` y `pytest-cov>=4.0.0` a `requirements.txt` | Necesario para `ExponentialSmoothing`; pin upper bound evita regresiones silenciosas |
| D-09 | Test reference_date | `2026-03-01` fijo para reproducibilidad del golden_set | Jira 278741 |
| D-10 | CLI | `scripts/run_methods.py` con argparse | Convención `scripts/` del repo |

### Human-confirmed (2)

| # | Decisión | Elegido |
|---|---|---|
| D-11 | EWMA span | `span=3` (reactivo, ~últimos 3 meses con mayor peso) |
| D-12 | Treatment B + all-zeros | `suggested_amount: null` + `reason: "No hay suficiente historial para calcular el monto sugerido"` — mismo comportamiento que gating fallido |

---

## HLTC — Delta arquitectural

### Nuevo: `src/smart_budget/model.py`

```python
EPSILON_DEFAULT: float = 0.01
EWMA_SPAN_DEFAULT: int = 3

def apply_treatment(df: pd.DataFrame, treatment: str, epsilon: float = EPSILON_DEFAULT) -> pd.DataFrame:
    """
    Variantes de tratamiento de ceros sobre la serie mensual.
    Aplica DESPUÉS de prepare_smart_budget_data() y ANTES del cálculo del modelo.
    Basis fields se extraen del df PRE-treatment.
    """
    # A: include_zeros — sin cambio
    # B: exclude_zeros — filtra filas con monthly_total == 0
    # C: epsilon_replace — reemplaza 0 por EPSILON_DEFAULT

def compute_wma(series: pd.Series) -> float:
    """WMA con pesos lineales crecientes [1..n] normalizados."""

def compute_ewma(series: pd.Series, span: int = EWMA_SPAN_DEFAULT) -> float:
    """EWMA con pandas.ewm(span=span).mean(), último valor."""

def compute_holt_winters(series: pd.Series) -> float:
    """
    ExponentialSmoothing(trend='add', seasonal=None).
    Retorna el primer forecast (1 paso hacia adelante).
    Mínimo 3 observaciones; levanta ValueError si series < 3.
    """

def compute_confidence(data_points: int) -> str:
    """high >= 6 | medium 3-5 | low = 2."""

def compute_budget_suggestions(
    df: pd.DataFrame,
    method: str,           # "wma" | "ewma" | "holt_winters"
    treatment: str,        # "A" | "B" | "C"
    reference_date: str,   # "YYYY-MM-DD" — punto de corte (inclusive)
    ewma_span: int = EWMA_SPAN_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
) -> list[dict]:
    """
    Pipeline principal:
    1. Filtrar meses <= reference_date month
    2. Extraer basis (months_with_zero, months_with_positive_spend) PRE-treatment
    3. apply_treatment()
    4. Si treatment B y series vacía: devolver null suggestion + reason
    5. Calcular suggested_amount con el método indicado
    6. Redondear a 2 decimales
    7. Construir JSON por bucket (idaccount × idcategory)
    """
```

### Nuevo: `scripts/run_methods.py`

```
args:
  --method       wma | ewma | holt_winters
  --treatment    A | B | C  (default: A)
  --reference-date  YYYY-MM-DD
  --input        CSV path (default: data/dough/test/query/smart_budget_synthetic.csv)
  --output       JSON file path (default: stdout)
  --min-months   int (default: 3)

output: lista JSON de suggestions → archivo o stdout
```

### Nuevo: `tests/unit/test_model.py`

Test cases TC-4.1–TC-4.8 (ver sección Testing).

### Nuevo: `tests/fixtures/golden_set.csv`

Generado con `data/dough/test/query/smart_budget_synthetic.csv`, `reference_date=2026-03-01`, `method=wma`, `treatment=A`.
Commiteado en el repo (no gitignored) para reproducibilidad.

### Modificado: `requirements.txt`

Agrega `statsmodels>=0.14.0`.

### JSON contract — extensión a DATA-1140

Se agregan dos campos respecto al contrato original de DATA-1140: `reason` (cuando null) y `explanation` (siempre presente).

**`explanation` — template:**

| Confidence | Template |
|---|---|
| `high` | `"En {months_with_positive_spend} de tus últimos {months_analyzed} meses tuviste gastos en esta categoría. Esta sugerencia tiene alta confiabilidad."` |
| `medium` | `"En {months_with_positive_spend} de tus últimos {months_analyzed} meses tuviste gastos en esta categoría. Esta sugerencia tiene confiabilidad media."` |
| `low` | `"En {months_with_positive_spend} de tus últimos {months_analyzed} meses tuviste gastos en esta categoría. Esta sugerencia está basada en pocos datos — revísala antes de confirmarla."` |
| null (sin sugerencia) | `"No hay datos históricos suficientes para calcular una sugerencia en esta categoría."` |

**Reglas de copy:** neutral y descriptiva (UDAAP/CFPB). Nunca menciona montos individuales. Nunca usa "deberías", "tienes que", ni comparativos contra otros usuarios.

Cuando `suggested_amount` es null:

```json
{
  "category_id": "string",
  "suggested_amount": null,
  "basis": null,
  "confidence": null,
  "display_label": "No hay suficiente historial para esta categoría",
  "explanation": "No hay datos históricos suficientes para calcular una sugerencia en esta categoría.",
  "reason": "No hay suficiente historial para calcular el monto sugerido",
  "model_version": "fase0-v1"
}
```

Cuando hay sugerencia:

```json
{
  "category_id": "string",
  "suggested_amount": 420.00,
  "basis": {
    "months_analyzed": 6,
    "months_with_zero": 2,
    "months_with_positive_spend": 4,
    "period_range": "2025-11 ~ 2026-01",
    "method": "wma",
    "treatment": "A"
  },
  "confidence": "high",
  "display_label": "Basado en tus últimos 6 meses",
  "explanation": "En 4 de tus últimos 6 meses tuviste gastos en esta categoría. Esta sugerencia tiene alta confiabilidad.",
  "model_version": "fase0-v1"
}
```

> ⚠ **DATA-1140 requiere enmienda** — los campos `explanation` y `reason` no están en el contrato original.
> Notificar a Backend antes de activar el endpoint.

---

## HLTC blocks reviewed

| Block | Tipo | Status |
|---|---|---|
| `src/smart_budget/model.py` — nuevo módulo | Auto-aceptado (patrón aggregator.py) | ✅ |
| `tests/unit/test_model.py` — nuevos tests | Auto-aceptado (patrón test_aggregator.py) | ✅ |
| `scripts/run_methods.py` — CLI | Auto-aceptado (convención scripts/) | ✅ |
| `tests/fixtures/golden_set.csv` — generado y commiteado | Auto-aceptado | ✅ |
| Pipeline order (gating → basis → treatment → model) | Auto-aceptado | ✅ |
| `statsmodels>=0.14.0` — nueva dep externa | **Triggereado** — aprobado por dev | ✅ |
| Campo `reason` en JSON null — extiende DATA-1140 | **Triggereado** — aprobado, DATA-1140 necesita enmienda | ✅ |

---

## Testing

| TC | Descripción | Método / Treatment |
|---|---|---|
| TC-4.1 | WMA treatment A — baseline con ceros incluidos | wma / A |
| TC-4.2 | WMA treatment B — excluye ceros, bucket mixto | wma / B |
| TC-4.3 | Treatment C — epsilon_replace convierte 0 → 0.01 | cualquiera / C |
| TC-4.4 | Treatment B + bucket all-zeros → null + reason | wma / B |
| TC-4.5 | Confidence levels (high≥6, medium 3-5, low=2) | cualquiera |
| TC-4.6 | HW con 6+ meses de datos — retorna float válido | holt_winters / A |
| TC-4.7 | Gating < 3 meses con datos → no suggestion | wma / A |
| TC-4.8 | Golden set: output WMA/A/2026-03-01 == golden_set.csv | wma / A |

---

## Restricciones de implementación

- `apply_treatment()` NUNCA modifica el df original — usar `.copy()`
- `compute_budget_suggestions()` NUNCA llama directamente a `aggregate_monthly()` — usa `prepare_smart_budget_data()` como entrada (responsabilidad del caller)
- Todos los `suggested_amount` redondeados a 2 decimales: `round(value, 2)`
- Negativos clampados a 0.0 antes de redondear (HW puede generar forecasts negativos)
- Multi-tenancy: el df de entrada ya tiene `idclient/idcompany/idaccount` — model.py los propaga en el JSON output sin filtrar
- Logging con `structlog`, nunca `print()`. Loguear: `method`, `treatment`, `n_buckets`, `n_suggestions`, `n_null_suggestions`

---

**Decision: approved by lbetancourth-dev-blossom — 2026-05-12**

All DCR decisions closed, HLTC blocks reviewed. Ready for security + spec generation.
