# Smart Budget

Repositorio del módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual.

## Estado actual

- **Fase 0 (El Reflejo):** en desarrollo — rama `DATA-1041`.
- Modelo: mediana del gasto histórico mensual por `member × category`.
- Pipeline implementado: `scripts/run_phase0.py` (filtros → agregación → mediana → output).
- Datos de test disponibles en `data/dough/test/` (5 members, 6 meses de historial).

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
├── README.md                       Este archivo.
├── .github/
│   └── copilot-instructions.md     Convenciones de código y reglas para GitHub Copilot.
├── data/
│   └── dough/
│       ├── bronze/                 Snapshots crudos del lake (incluye metadata DMS).
│       ├── silver/                 Snapshots limpios (capa de análisis).
│       └── gold/                   (Vacía hoy; destino de los outputs DS-ML.)
├── docs/
│   ├── data_review.md              Revisión de datos disponibles, capas y hallazgos.
│   ├── glosario.md                 Glosario de términos del proyecto.
│   └── (futuro) ARCHITECTURE.md, DECISIONS.md, DATA_CONTRACT.md
└── scripts/
    └── extract_dough_to_csv.py     Script de extracción S3 → CSV local.
```

## Cómo refrescar los datos locales

El script lee parquet desde S3 y escribe CSV en `data/dough/{bronze,silver}/`. Requiere AWS CLI configurado con perfil `blossom-dev`.

```bash
# Configurar perfil (solo la primera vez)
aws configure --profile blossom-dev

# Instalar dependencias
pip install boto3 pandas pyarrow

# Ejecutar la extracción
python scripts/extract_dough_to_csv.py
```

## Documentación clave

| Documento | Para qué |
|---|---|
| [`docs/data_review.md`](docs/data_review.md) | Estado y diferencias de bronze/silver/gold, diccionario de tablas, diagrama ER, gaps de data. |
| [`docs/glosario.md`](docs/glosario.md) | Definiciones alfabéticas de términos del proyecto (Dough, Plaid, Finicity, Ntropy, RICH, etc.). |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Reglas para GitHub Copilot: stack, convenciones, restricciones legales, casos edge. |

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
