# Smart Budget

Repositorio del módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual.

## Estado actual

**Fase 0 (El Reflejo)** — rama `DATA-1041`

| Step | Estado | Resultado |
|------|--------|-----------|
| Step 1 — Extracción DOUGH | ✅ | 30 tablas dev + 23 alpha → `data/dough/*/silver/` |
| Step 2 — Extracción OLB | ✅ | 7 tablas → `data/olb/dev/silver/` (1.06M txns) |
| Step 3 — `fact_transactions` | ✅ | **1,413,914 filas** (OLB SUB + LOAN + Dough EXT), rango 2022–2026, incluye `idcategory` |
| Step 4 — Preparación datos (`DATA-1136`) | ✅ | `smart_budget_prep.csv`: **504 filas**, 5 cuentas, 11 categorías (post-filtros y gating) |
| Step 5 — Modelo mediana | 🔄 | Pendiente |
| Step 6 — Output BD | 🔄 | Pendiente |

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

## Schema del output — `smart_budget_prep.csv`

El pipeline genera `data/dough/smart_budget_prep.csv` con las siguientes columnas:

| Columna | Tipo | Descripción |
|---|---|---|
| `idclient` | string | ID del cliente (Credit Union owner) |
| `idcompany` | string | ID de la compañía (Credit Union) |
| `idaccount` | string | ID de la cuenta del miembro. Prefijo `INT` = OLB, `EXT` = Plaid/Finicity |
| `idcategory` | string | ID numérico de la categoría en `defaultcategory` (FK). Ej: `"8"` = Groceries |
| `defaultcategory` | string | Nombre de la categoría. Ej: `"Groceries"` |
| `period_yyyymm` | string | Mes del período. Formato `"YYYY-MM"` |
| `monthly_total` | float | Suma de gastos del mes, normalizada a valor positivo. `0.0` si no hubo gasto ese mes (zero-fill) |

### Ejemplo de output

```
idclient,idcompany,idaccount,idcategory,defaultcategory,period_yyyymm,monthly_total
1,1,EXT2,1,Auto & Transport,2025-11,45.50
1,1,EXT2,1,Auto & Transport,2025-12,0.0
1,1,EXT2,8,Groceries,2025-11,120.00
1,1,INT31880,8,Groceries,2025-10,87.50
```


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
│   │   ├── smart_budget_prep.csv       Output pipeline: datos listos para el modelo
│   │   └── smart_budget_synthetic.csv  Dataset sintético para testing
│   └── olb/dev/silver/*.csv            7 tablas OLB dev
├── docs/
│   └── fact_transactions_README.md     Schema y documentación de fact_transactions.
├── scripts/
│   ├── extract_datalake_to_csv.py      Extrae cualquier tabla del datalake S3 → CSV local.
│   ├── build_fact_transactions.py      Construye fact_transactions (OLB + DOUGH).
│   ├── run_smart_budget_prep.py        Pipeline: filtra, agrega y aplica gating.
│   └── generate_synthetic_dataset.py  Genera dataset sintético para pruebas.
├── src/smart_budget/
│   ├── filters.py                      Reglas de filtrado (Posted, Expense, exclusiones).
│   └── aggregator.py                   Lógica de agregación mensual y gating.
└── tests/
    ├── fixtures/fact_transactions_test.csv
    └── unit/
        ├── test_filters.py
        └── test_aggregator.py
```
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
| [`docs/fact_transactions_README.md`](docs/fact_transactions_README.md) | Schema completo de `fact_transactions`: columnas, ids, fuentes. |
| [`changes/DATA-1136/plan.md`](changes/DATA-1136/plan.md) | Plan DATA-1136: decisiones, edge cases, fixes de datos aplicados. |
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
