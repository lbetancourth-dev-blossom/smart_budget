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

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `idTransaction` | string | ID único prefijado (`SUB`, `LOAN`, `EXT`) |
| `idClient` | int | ID del cliente Blossom (siempre `1`) |
| `idCompany` | string | ID de la Financial Institution (idfi) |
| `idAccount` | string | Número de cuenta prefijado con `INT` (OLB) o `EXT` (Dough) |
| `idSubAccount` | string | Subcuenta (`SUB{id}` o `LOAN{id}`); NULL para EXT |
| `amount` | decimal(18,2) | Monto de la transacción |
| `currency` | string | Moneda (siempre `USD`) |
| `originalAmount` | decimal(18,2) | Monto original (NULL si no aplica) |
| `timestamp` | timestamp | Fecha/hora de la transacción |
| `date` | date | Fecha de la transacción |
| `incomeExpenditure` | string | `"expenditure"` o `"income"` |
| `status` | string | Estado (`NULL`, `CLEARED`, `HOLD`, etc.) — nunca `HOLD` en esta tabla |
| `description` | string | Descripción/memo de la transacción |
| `balance` | decimal(18,2) | Balance después de la transacción |
| `isEnriched` | boolean | Si la transacción tiene enriquecimiento de Ntropy |
| `enrichment` | json | JSON completo de enriquecimiento (NULL si no disponible en S3) |
| `enrichmentLogo` | string | URL del logo del comercio (de DynamoDB enrichment) |
| `enrichmentName` | string | Nombre del comercio enriquecido |
| `enrichmentLocation` | string | Metadatos de localización |
| `enrichmentUrl` | string | Sitio web del comercio |
| `defaultCategory` | string | Categoría OLB nativa (de `olbtransactioncategory.name`) |
| `idOLBTransactionInfo` | string | ID de la info de transacción OLB |
| `transactionComplete` | string | ID para lookup de enriquecimiento DynamoDB |
| `note` | string | Nota del usuario |
| `checkNumber` | string | Número de cheque (solo SUB) |
| `isSplit` | boolean | Si la transacción está dividida |
| `splitedTransactions` | string | JSON de sub-transacciones (NULL en Fase 0) |
| `createdAt` | timestamp | Fecha de creación del registro |
| `deletedAt` | timestamp | Fecha de eliminación lógica (soft delete) |
| `doughId` | string | ID en el sistema Dough (para transacciones EXT) |
| `source` | string | Origen: `OLB_SUB`, `OLB_LOAN`, `DOUGH_EXT` |

---

## Convenciones de id

```
idTransaction:  SUB123456    → OLB SubAccount txn id=123456
                LOAN789      → OLB Loan txn id=789
                EXT456       → Dough External txn id=456

idAccount:      INT10001     → OLB account number 10001
                EXT10002     → Dough external account id=10002

idSubAccount:   SUB5001      → OLB SubAccount id=5001
                LOAN2001     → OLB Loan id=2001
```

---

## Filtros aplicados

- `status != 'HOLD'` — Transacciones en estado HOLD son excluidas (no posted)
- `deletedAt IS NULL` — Se puede filtrar para excluir registros eliminados

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
    (fact["incomeExpenditure"] == "expenditure") &
    (fact["deletedAt"].isna())
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
# Primero extraer las tablas OLB del datalake:
python3 scripts/extract_dough_to_csv.py --env dev  # extrae DOUGH silver

# Luego construir fact_transactions:
python3 scripts/build_fact_transactions.py --env dev
# Output: data/dough/fact_transactions.csv
```
