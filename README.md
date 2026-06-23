# Smart Budget

Módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget suggests spending amounts per category based on the member's own transaction history — eliminating the "blank budget" problem.

---

## Dataset

Data is queried live from AWS Athena at request time — no local CSV files required.

| Environment | Athena Table | Members | Periods |
|-------------|-------------|---------|---------|
| `dev` | `dlh_gold_dough_dev.smart_budget_transactions` | 421+ | 2022-09 → present |
| `alpha` | `dlh_gold_dough_dev.smart_budget_transactions` | 2,929+ | 2019-06 → present |

### Schema (Athena table)

| Column | Type | Description |
|--------|------|-------------|
| `idmember` | string | Member identifier (primary grain) |
| `idclient` | string | Client identifier (multi-tenancy) |
| `idcompany` | string | Credit Union identifier |
| `idaccount` | string | Account identifier |
| `category_id` | string | Blossom category ID |
| `category_name` | string | Blossom category name (e.g. `"Groceries"`) |
| `type_category` | string | Category type (pre-filtered to expenditure) |
| `txn_month` | string (YYYY-MM) | Calendar month of the spend |
| `total_amount` | float | Net spend for that month and category (USD) |
| `year` | int | Year extracted from `txn_month` |
| `month` | int | Month extracted from `txn_month` |

### Filtering rules applied at extraction (never bypass)

- `status = 'Posted'` — never Pending, Failed, or Cancelled
- Category type `Expense` only — excludes Income and Others
- Excludes transaction types: `Internal`, `Member-to-Member`, `SIG`
- Excludes `Uncategorized` category
- Aggregation unit: `transactionSplit` (not `transaction`)
- Months with negative net spend (refunds > spend): clamped to 0

---

## Endpoint

### Request

```
GET /smart-budget/suggestion?idmember={id}&period_id={YYYY-MM}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `idmember` | string | ✅ | Member ID (must exist in the active environment dataset) |
| `period_id` | string (YYYY-MM) | ✅ | Budget reference month (e.g. `2026-05`) |

Active environment is controlled by `SB_ENV=dev|alpha` (default: `dev`).

### Response — With data (HTTP 200)

```json
{
  "idmember": "11393",
  "idclient": "1",
  "idcompany": "2050",
  "period_id": "2026-05",
  "total_suggested": 72.33,
  "suggestions": [
    {
      "category_id": "GAS",
      "category_name": "Gas",
      "suggested_amount": 15.00,
      "confidence": "low",
      "basis": {
        "months_analyzed": 1,
        "months_with_spend": 1,
        "period_range": "2026-04 ~ 2026-04"
      },
      "amount_by_month": {
        "2026-02": 0,
        "2026-03": 0,
        "2026-04": 15.00
      }
    },
    {
      "category_id": "OTHER",
      "category_name": "Other",
      "suggested_amount": 37.33,
      "confidence": "low",
      "basis": {
        "months_analyzed": 2,
        "months_with_spend": 2,
        "period_range": "2026-02 ~ 2026-03"
      },
      "amount_by_month": {
        "2026-02": 100.00,
        "2026-03": 6.00,
        "2026-04": 0
      }
    }
  ],
  "message": "Based on your last 3 months",
  "method": "wma",
  "treatment": "B",
  "model_version": "fase0-v1"
}
```

### Response — No data / insufficient history (HTTP 200)

```json
{
  "idmember": "99999",
  "idclient": "",
  "idcompany": "",
  "period_id": "2026-05",
  "total_suggested": null,
  "suggestions": null,
  "message": "Not enough history to calculate suggestions. At least 2 months of data required.",
  "method": "wma",
  "treatment": "B",
  "model_version": "fase0-v1"
}
```

### Response — Member not found (HTTP 404)

```json
{ "detail": "idmember not found" }
```

### HTTP status codes

| HTTP | Condition |
|------|-----------|
| `200` | Member found — returns suggestions or null if insufficient history |
| `404` | `idmember` not found in the active dataset |
| `422` | Invalid `period_id` format |

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `total_suggested` | float \| null | Sum of all `suggested_amount` values |
| `suggestions` | array \| null | Per-category suggestions; null when no history |
| `message` | string | `"Based on your last 3 months"` or no-history message |
| `confidence` | string \| null | `high` ≥6 months · `medium` 3–5 · `low` 2 months |
| `basis.months_analyzed` | int | Months in the lookback window |
| `basis.months_with_spend` | int | Months with spend > 0 used in the calculation |
| `basis.period_range` | string | Range of months analyzed (`YYYY-MM ~ YYYY-MM`) |
| `method` | string | Calculation method (`wma`) |
| `treatment` | string | WMA weight configuration (`B`) |
| `model_version` | string | Model version (`fase0-v1`) |

---

## Run locally

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

# Dev environment (port 8000)
SB_ENV=dev PYTHONPATH=$(pwd)/src uvicorn src.main:app --reload --port 8000

# Alpha environment (port 8001)
SB_ENV=alpha PYTHONPATH=$(pwd)/src uvicorn src.main:app --reload --port 8001
```

Swagger UI: `http://localhost:8000/docs` — member dropdown shows top-10 members for the active environment.

```bash
# Example request
curl "http://localhost:8000/smart-budget/suggestion?idmember=11393&period_id=2026-05"
```

---

## Run on SageMaker

Open `notebooks/smart_budget_sagemaker_endpoint.ipynb` and set the environment in **cell 2**:

```python
ENV = "dev"   # "dev" | "alpha"
```

| | dev | alpha |
|--|-----|-------|
| **S3 model path** | `smart_budget/endpoint/v1/dev/model.tar.gz` | `smart_budget/endpoint/v1/alpha/model.tar.gz` |
| **Endpoint name** | `smart-budget-suggestion-endpoint-dev` | `smart-budget-suggestion-endpoint-alpha` |
| **Data source** | Athena live query at inference time | Athena live query at inference time |

The SageMaker endpoint accepts the same request contract and returns the same response schema as the local endpoint. Data is **not bundled** in the model artifact — it is queried from Athena on every invocation.

---

## Tests

```bash
pytest tests/ -v --cov=src/smart_budget --cov-report=term-missing
# 97 passed, 1 skipped
```

---

## Model

**WMA Treatment B · lookback=3** — selected in DATA-1138 (CRWS=0.5372, MAE=$48.63).

- **Treatment B:** skips months with $0 spend — calculates only over months with real activity.
- **lookback=3:** uses the 3 complete calendar months before the budgeted month.
- **Gating:** minimum 2 months with data required to emit a suggestion; otherwise `suggestions: null`.

---

## Legal constraints

- **No robo-adviser (SEC):** suggests based on history only — never recommends what to do with money.
- **UDAAP / CFPB:** `message` must be neutral and descriptive. ❌ "You should spend less on X".
- **Multi-tenancy:** every operation filtered by `idclient / idcompany / idmember`. Never cross-tenant.
- **PII:** never log individual transaction amounts or unhashed member IDs (SHA-256 + `SB_LOG_SALT`).
