# Smart Budget

Repositorio del módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget sugiere al miembro montos por categoría de gasto basándose en su propio historial transaccional, eliminando el "punto de partida en blanco" del presupuesto manual.

## Estado actual

- **Fase 0 (El Reflejo):** en discovery / diseño técnico.
- Modelo: mediana del gasto histórico mensual por `member × category`.
- Lectura desde data lake **alpha** de Blossom (`s3://blossom-analytics-datalake-alpha/datalake/{bronze,silver}/DOUGH/`).
- Escritura propuesta en BlossomAPI / capa gold (pendiente de creación).

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
