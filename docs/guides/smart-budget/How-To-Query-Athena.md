---
title: How-To-Query-Athena
aliases: [Athena, PyAthena, Consultar Athena, Smart Budget Athena]
tags: [guide, athena, data-source, pyathena]
type: guide
audience: ds-ml
ticket: DATA-1275
last_updated: 2026-06-23
---

# Cómo consultar datos de Smart Budget via Athena

Guía para consultar la tabla Glue que alimenta el modelo Smart Budget. Post-DATA-1275,
Athena reemplaza el pipeline batch de S3/PostgreSQL como fuente de datos para el endpoint.

---

## Tabla fuente

| Campo | Valor |
|---|---|
| Catálogo | AWS Glue |
| Base de datos | `dlh_gold_dough_dev` |
| Tabla | `smart_budget_transactions` |
| URI completo | `dlh_gold_dough_dev.smart_budget_transactions` |

### Columnas disponibles

| Columna | Tipo | Descripción |
|---|---|---|
| `idclient` | `string` | ID del cliente (multi-tenancy top level) |
| `idcompany` | `string` | ID de la Credit Union |
| `idmember` | `string` | ID del miembro |
| `idaccount` | `string` | ID de la cuenta del miembro |
| `category_id` | `string` | ID de categoría (reemplaza `idcategory` del schema legacy) |
| `category_name` | `string` | Nombre de categoría (reemplaza `defaultcategory` del schema legacy) |
| `type_category` | `string` | Tipo de categoría |
| `txn_month` | `string` | Mes de la transacción (formato `YYYY-MM`) |
| `total_amount` | `double` | Monto total agregado del mes |
| `year` | `int` | Año (partición) |
| `month` | `int` | Mes numérico (partición) |

> **Nota sobre el schema:** `category_id` y `category_name` reemplazan los campos `idcategory` /
> `defaultcategory` del pipeline legacy. La tabla ya viene pre-filtrada y agregada por mes.

---

## Variables de entorno necesarias

| Variable | Requerida | Default | Descripción |
|---|---|---|---|
| `ATHENA_S3_STAGING_DIR` | ✅ Sí | — | Bucket S3 para resultados temporales de Athena |
| `ATHENA_REGION_NAME` | No | `us-east-2` | Región AWS |
| `ATHENA_DATABASE` | No | `dlh_gold_dough_dev` | Base de datos Glue |
| `ATHENA_TABLE` | No | `smart_budget_transactions` | Tabla Glue |

```bash
export ATHENA_S3_STAGING_DIR=s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/
export ATHENA_REGION_NAME=us-east-2
```

---

## Conexión directa con pyathena

Para consultas ad-hoc o exploración del dataset:

```python
from pyathena import connect
import pandas as pd

conn = connect(
    s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/',
    region_name='us-east-2'
)

df = pd.read_sql(
    "SELECT * FROM dlh_gold_dough_dev.smart_budget_transactions "
    "WHERE idmember='18973' AND txn_month='2026-04'",
    conn
)
```

---

## Usando el loader del módulo (recomendado para el endpoint)

El módulo `smart_budget.athena_loader` expone helpers que manejan la conexión,
normalización de columnas, y manejo de errores. Es la forma recomendada para el endpoint.

```python
from smart_budget.athena_loader import load_history_by_member_athena, member_exists_athena

# Verificar si un miembro tiene historial en Athena
exists = member_exists_athena("18973")

# Cargar historial completo del miembro
df = load_history_by_member_athena(idmember="18973")

# El loader retorna columnas normalizadas:
# idmember, idclient, idcompany, idaccount, category_id, category_name,
# period_yyyymm, monthly_total
```

### Columnas del DataFrame retornado

| Columna | Tipo | Descripción |
|---|---|---|
| `idmember` | `string` | ID del miembro |
| `idclient` | `string` | ID del cliente |
| `idcompany` | `string` | ID de la Credit Union |
| `idaccount` | `string` | ID de la cuenta |
| `category_id` | `string` | ID de categoría |
| `category_name` | `string` | Nombre de categoría |
| `period_yyyymm` | `string` | Mes en formato `YYYY-MM` |
| `monthly_total` | `float` | Gasto total del mes |

---

## Filtros pre-aplicados en la tabla

La tabla `smart_budget_transactions` ya viene pre-filtrada por el pipeline de Data Engineering.
**No aplicar filtros adicionales** — hacerlo produce resultados incorrectos.

Los filtros aplicados upstream son:

- Solo gastos (`expenditure`) — ingresos excluidos
- Transacciones LOAN excluidas
- Transacciones PENDING excluidas
- Sin soft deletes

> Para entender la lógica de filtrado completa, ver [[How-To-Extract-Data]] — Reglas de filtrado (sección legacy).

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `NoCredentialsError` | Sesión AWS expirada | `aws sso login --profile blossom-dev` |
| `ATHENA_S3_STAGING_DIR not set` | Variable de entorno faltante | Exportar `ATHENA_S3_STAGING_DIR` |
| `EntityNotFoundException` | Base de datos o tabla no existe en Glue | Verificar nombre `dlh_gold_dough_dev.smart_budget_transactions` |
| `AccessDeniedException` en S3 staging | Sin permisos en el bucket de staging | Verificar permisos IAM: `s3:PutObject` en el bucket de staging |
| `AccessDeniedException` en Athena | Sin permisos para ejecutar queries | Verificar política IAM: `athena:StartQueryExecution`, `glue:GetTable` |
| DataFrame vacío para un miembro | El miembro no tiene transacciones en la tabla | Verificar con `member_exists_athena(idmember)` primero |
| `timeout` en query | Query sin filtro de partición — escanea toda la tabla | Agregar `WHERE year=... AND month=...` o usar el loader |

---

## Backlinks

- [[How-To-Extract-Data]] — pipeline legacy batch (S3/PostgreSQL) para referencia histórica
- [[How-To-Run-Pipeline]] — pipeline offline de sugerencias sobre CSVs
- `src/smart_budget/athena_loader.py` — implementación del loader
