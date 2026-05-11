# Smart Budget

Repositorio del módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual.

## Estado actual

**Fase 0 (El Reflejo)** — rama `DATA-1041`

| Step | Estado | Resultado |
|------|--------|-----------|
| Step 1 — Extracción DOUGH | ✅ | 30 tablas dev + 23 alpha → `data/dough/*/silver/` |
| Step 2 — Extracción OLB | ✅ | 7 tablas → `data/olb/dev/silver/` (1.06M txns) |
| Step 3 — `fact_transactions` | ✅ | **1,413,914 filas** (OLB SUB + LOAN + Dough EXT), rango 2022–2026 |
| Step 4 — Preparación datos (DATA-1136) | ✅ | 180 filas limpias → `data/dough/smart_budget_prep.csv` |
| Step 5 — Modelo mediana | 🔄 | Pendiente |
| Step 6 — Output BD | 🔄 | Pendiente: escribir a `budget` + `budgetcategory` |

**Arquitectura de datos:**
```
OLBSubAccountTransaction ─┐
OLBLoanTransaction        ├──→ fact_transactions ──→ Smart Budget
externaltransaction       ─┘
```

## Catálogo de categorías

Las categorías provienen de la tabla `defaultcategory` y están organizadas en 4 grupos.
Smart Budget **solo opera sobre el Grupo 1 (Expenses)**.

### Grupo 1 — Expenses ✅ (usadas por Smart Budget)

| ID | Categoría |
|---|---|
| 1 | Auto & Transport |
| 2 | Bills & Utilities |
| 3 | Business Services |
| 4 | Education |
| 5 | Entertainment & Leisure |
| 6 | Financial Services |
| 7 | Food & Dining |
| 8 | Groceries |
| 9 | Gifts & Donations |
| 10 | Health & Fitness |
| 11 | Home & Rent |
| 12 | Kids & Family |
| 13 | Personal Care & Beauty |
| 14 | Pets |
| 15 | Shopping |
| 16 | Subscriptions |
| 17 | Taxes & Fees |
| 18 | Travel & Trips |
| 27 | Gas |
| 28 | Transfers & payments |
| 29 | Transfers & Payments |

### Grupo 2 — Incomes ❌ (excluidas del modelo)

| ID | Categoría |
|---|---|
| 19 | Business Income |
| 20 | Income |

### Grupo 3 — Excluded ❌ (excluidas del modelo)

| ID | Categoría |
|---|---|
| 21 | Internal Transfers |
| 22 | Credit Card Payment |
| 23 | Loan Payment |
| 24 | ATM & Cash |
| 25 | Savings & Investments |

### Grupo 4 — Other

| ID | Categoría | Visible |
|---|---|---|
| 26 | Other | No (`shouldshow = false`) |

> **Nota:** El catálogo es plano — no hay subcategorías en el schema actual de Dough.
> Las CUs con RICH (Ntropy) tienen categorías custom adicionales mapeadas en `companyntropycategory`.

## Estructura del repo

```
smart_budget/
├── README.md
├── .github/
│   └── copilot-instructions.md         Convenciones y reglas para GitHub Copilot.
├── data/                               Gitignored — datos locales.
│   ├── dough/
│   │   ├── dev/silver/*.csv            30 tablas DOUGH (dev)
│   │   ├── alpha/silver/*.csv          23 tablas DOUGH (alpha)
│   │   ├── fact_transactions.csv       Tabla central: 1,413,914 filas
│   │   ├── fact_transactions_expenditure.csv   Solo gastos — apto para Excel
│   │   └── fact_transactions_sample.csv        Muestra 50k filas
│   └── olb/dev/silver/*.csv            7 tablas OLB dev
├── docs/
│   ├── plan/
│   │   ├── plan_phase_0.md             Plan de implementación con resultados por step.
│   │   └── phase0_remaining_tasks.md   Tareas pendientes para producción.
│   ├── fact_transactions_README.md     Schema y documentación de fact_transactions.
│   └── glosario.md                     Glosario de términos del proyecto.
└── scripts/
    ├── extract_datalake_to_csv.py         Extrae cualquier tabla del datalake S3 → CSV local.
    └── build_fact_transactions.py      Construye fact_transactions (OLB + DOUGH).
```

## Pipeline de preparación Smart Budget (DATA-1136)

El script `run_smart_budget_prep.py` toma `fact_transactions.csv` y produce un
dataset limpio con el gasto mensual por `(miembro × categoría)`, listo para
que el modelo de mediana calcule sugerencias.

**Pasos internos:**
1. **Filtrado** — descarta Pending, Uncategorized, Income, transferencias internas.
2. **Agregación mensual** — suma gasto real por `(idmember, defaultcategory, YYYY-MM)`.
3. **Zero-fill** — rellena meses sin actividad con `$0` para preservar el historial completo.
4. **Cap P90** — clampea outliers al percentil 90 de los meses con gasto real.
5. **Gating** — elimina pares `(miembro, categoría)` con menos de N meses con gasto.

```bash
# Requiere: pip install pandas structlog
python scripts/run_smart_budget_prep.py \
  --input  data/dough/fact_transactions.csv \
  --output data/dough/smart_budget_prep.csv \
  --min-months 3        # mínimo de meses con gasto para incluir el par
```

**Ejemplo de output (`smart_budget_prep.csv`):**

| idclient | idcompany | idmember | defaultcategory | period_yyyymm | monthly_total | capped |
|---|---|---|---|---|---|---|
| 1 | 1 | INT31880 | GROCERIES | 2024-09 | 10.00 | False |
| 1 | 1 | INT31880 | GROCERIES | 2024-10 | 22.50 | False |
| 1 | 1 | INT31880 | GROCERIES | 2024-11 | 12.50 | False |
| 1 | 1 | INT428 | FEES | 2025-07 | 13.00 | False |
| 1 | 1 | INT428 | FEES | 2025-09 | 13.00 | False |
| 1 | 1 | INT428 | FEES | 2025-10 | 13.00 | False |

> En dev/alpha la mayoría de transacciones son `UNCATEGORIZED`, por lo que el
> dataset resultante es pequeño (~180 filas, 3 miembros). En producción el
> volumen es significativamente mayor.

---

## Cómo refrescar los datos locales

Requiere AWS CLI con perfil `blossom-dev` y SSO activo.

```bash
# Login SSO
aws sso login --profile blossom-dev

# Instalar dependencias
pip install boto3 pandas pyarrow

# 1. Extraer tablas DOUGH (dev o alpha)
python scripts/extract_datalake_to_csv.py --source DOUGH --env dev

# Ver todas las fuentes disponibles en el datalake
python scripts/extract_datalake_to_csv.py --list

# 2. Construir fact_transactions
python scripts/build_fact_transactions.py --env dev
# Output: data/dough/fact_transactions.csv  (1.4M filas)
#         data/dough/fact_transactions_expenditure.csv  (solo gastos, apto Excel)
#         data/dough/fact_transactions_sample.csv       (50k filas para exploración)
```

## Documentación clave

| Documento | Para qué |
|---|---|
| [`docs/plan/plan_phase_0.md`](docs/plan/plan_phase_0.md) | Plan Fase 0 con resultados por step. |
| [`docs/plan/phase0_remaining_tasks.md`](docs/plan/phase0_remaining_tasks.md) | Tareas pendientes hasta producción (testing, BD, API, compliance). |
| [`docs/fact_transactions_README.md`](docs/fact_transactions_README.md) | Schema completo de `fact_transactions`: columnas, ids, fuentes. |
| [`docs/glosario.md`](docs/glosario.md) | Definiciones de términos del proyecto (Dough, Plaid, OLB, RICH, etc.). |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Stack, convenciones, restricciones legales, casos edge. |

## Referencias externas

- **PRD Smart Budget** (Notion / Drive — David Segovia, Analytics).
- **Modelo de datos Dough** (`base-de-datos-modelo.pdf` en Drive).
- **Roadmap por fases** (PRD §11): Fase 0 (Reflejo) → 1 (Intención) → 2 (Contexto) → 3 (Coach).

## Restricciones legales (recordatorio)

- **No robo-adviser (SEC):** el sistema sugiere, no recomienda.
- **UDAAP / CFPB:** lenguaje neutral, nunca prescriptivo.
- **Multi-tenancy estricta:** toda query filtrada por `idClient/idCompany/idMember`.
- **Section 1033:** los datos de Plaid/Finicity tienen reglas de portabilidad y retención.

## Contacto

- **Producto:** David Segovia (Analytics).
- **DS-ML:** Landneyker.
