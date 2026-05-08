# fact_transactions — Tabla de Transacciones Unificadas

## ¿Qué es?

`fact_transactions.csv` es la **tabla central de transacciones** del proyecto Smart Budget. Unifica tres fuentes de datos en un único esquema canónico:

| Fuente | Prefijo `idTransaction` | Descripción |
|--------|------------------------|-------------|
| OLB SubAccount | `SUB{id}` | Transacciones de cuentas de ahorro/cheques (OLB interno) |
| OLB Loan | `LOAN{id}` | Transacciones de préstamos (OLB interno) |
| Dough External | `EXT{id}` | Transacciones externas via Plaid/Finicity (agregador Dough) |

---

## Origen

Construida por `scripts/build_fact_transactions.py` siguiendo la lógica del equipo de DE en `ref_fact_transactions_olb.py` (PySpark → pandas).

**Fuentes S3:**
- OLB: `blossom-analytics-datalake-dev/datalake/silver/OLB/`
- Dough: `blossom-analytics-datalake-dev/datalake/silver/DOUGH/`

---

## Esquema de columnas

32 columnas en orden canónico (idéntico a `public.fact_transactions` en `blossom-dough-consolidated-dev`). Todos los nombres en **lowercase**.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `idtransaction` | string | ID único prefijado (`SUB`, `LOAN`, `MANT`) |
| `idclient` | int | ID del cliente Blossom (siempre `1`) |
| `idcompany` | int | ID de la Financial Institution (`idfi`) |
| `idaccount` | string | Número de cuenta prefijado con `INT` (OLB) |
| `idsubaccount` | string | Subcuenta (`SUB{id}` o `LOAN{id}`) |
| `date` | date | Fecha de la transacción (`YYYY-MM-DD`) |
| `amount` | decimal | Monto de la transacción |
| `currency` | string | Moneda (siempre `USD`) |
| `originalamount` | decimal | Monto original (NULL — sin implementar en Fase 0) |
| `timestamp` | timestamp | Fecha/hora de la transacción (`YYYY-MM-DD HH:MM:SS.000`) |
| `incomeexpenditure` | string | `"expenditure"` o `"income"` |
| `status` | string | Estado (`NULL`, `CLEARED`, `HOLD`, etc.) — `HOLD` excluido |
| `description` | string | Descripción/memo de la transacción |
| `balance` | decimal | Balance después de la transacción |
| `isenriched` | boolean | Si la transacción tiene enriquecimiento de Ntropy |
| `enrichment` | json | JSON completo de enriquecimiento (NULL sin DynamoDB) |
| `enrichmentlogo` | string | URL del logo del comercio |
| `enrichmentname` | string | Nombre del comercio enriquecido |
| `enrichmentlocation` | string | Metadatos de localización |
| `enrichmenturl` | string | Sitio web del comercio |
| `defaultcategory` | string | Categoría OLB nativa (de `olbtransactioncategory.name`) |
| `idolbtransactioninfo` | string | ID de la info de transacción OLB |
| `transactioncomplete` | string | ID para lookup de enriquecimiento DynamoDB |
| `note` | string | Nota del usuario |
| `checknumber` | int | Número de cheque (solo SUB, nullable) |
| `issplit` | boolean | Si la transacción está dividida |
| `splitedtransactions` | string | JSON de sub-transacciones (NULL — sin splits en Fase 0) |
| `createdat` | timestamp | Fecha de creación del registro (`YYYY-MM-DD HH:MM:SS.000`) |
| `deletedat` | timestamp | Fecha de eliminación lógica (soft delete) |
| `doughid` | string | ID en el sistema Dough |
| `firstuploaded` | timestamp | Primera vez cargado (`YYYY-MM-DD HH:MM:SS.000 -0500`) |
| `lastuploaded` | timestamp | Última vez cargado (`YYYY-MM-DD HH:MM:SS.000`) |

---

## Convenciones de id

```
idtransaction:  SUB123456    → OLB SubAccount txn id=123456
                LOAN789      → OLB Loan txn id=789
                MANT42       → Manual transaction Dough id=42

idaccount:      INT10001     → OLB account number 10001

idsubaccount:   SUB5001      → OLB SubAccount id=5001
                LOAN2001     → OLB Loan id=2001
```

---

## Filtros aplicados

- `status != 'HOLD'` — Transacciones en estado HOLD son excluidas (no posted)
- `deletedat IS NULL` — Se puede filtrar para excluir registros eliminados lógicamente

---

## Nota sobre enriquecimiento

Las columnas `enrichment*` provienen de **DynamoDB** (no del datalake S3). En el pipeline local, estas columnas son `NULL`. El enriquecimiento real (logo, merchantName, URL) está disponible en el ambiente productivo del equipo de DE vía el Glue job que hace el scan de DynamoDB.

---

## Uso en Smart Budget Fase 0

```python
import pandas as pd

fact = pd.read_csv("data/dough/fact_transactions.csv")

# Filtrar solo gastos activos
gastos = fact[
    (fact["incomeexpenditure"] == "expenditure") &
    (fact["deletedat"].isna())
]

# Agregar por member, categoría, mes
# (requiere join con defaultcategory para idcategory)
```

---

## Arquitectura de referencia

Según el documento *High Level Architecture DOUGH* (pág. 15):

```
OLBSubAccountTransaction ─┐
OLBLoanTransaction       ─┼──→ fact_transactions ──→ fact_labels ──→ Smart Budget
externaltransaction      ─┘         (esta tabla)
```

`fact_labels` es la capa que aplica las etiquetas de categoría (via `companyntropycategory` o categoría OLB nativa) sobre `fact_transactions`.

---

## Generación

```bash
# Login SSO (si no está activo)
aws sso login --profile blossom-dev

# Modo DB (recomendado) — lee directo de blossom-dough-consolidated-dev
python3 scripts/build_fact_transactions.py --source db --db-user lbetancourth --db-pass <password>

# Modo S3 (offline fallback) — requiere datos locales en data/olb/ y data/dough/dev/silver/
python3 scripts/build_fact_transactions.py --source s3

# Outputs generados en data/dough/:
#   fact_transactions.csv              → 1,413,948 filas, 32 cols (completo)
#   fact_transactions_expenditure.csv  → 722,370 filas (solo gastos, apto Excel)
#   fact_transactions_sample.csv       → 50,000 filas (muestra aleatoria)
```
