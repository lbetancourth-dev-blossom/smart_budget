# Smart Budget

Módulo **Smart Budget** del producto **Dough** (PFM de Blossom para Credit Unions).

> Smart Budget suggests spending amounts per category based on the member's own transaction history — eliminating the "blank budget" problem.

---

## Dataset

Data is extracted directly from the DB via SQL query (no S3).

| Environment | Dataset | Members | Periods |
|-------------|---------|---------|---------|
| `dev` | `data/dough/smart_budget_db_dev.csv` | 421 | 2022-09 → 2026-05 |
| `alpha` | `data/dough/smart_budget_db_alpha.csv` | 2,929 | 2019-06 → 2026-06 |

```bash
# Extract data (requires AWS SSO)
aws sso login --profile blossom-dev
python scripts/extract_smart_budget_monthly.py --env dev
python scripts/extract_smart_budget_monthly.py --env alpha
```

---

## Endpoint

### Input

```
GET /smart-budget/suggestion?idmember={id}&period_id={YYYY-MM}
```

| Parameter | Type | Example | Description |
|-----------|------|---------|-------------|
| `idmember` | string | `11393` | Member ID |
| `period_id` | string | `2026-05` | Budget month (YYYY-MM) |

### Output

```json
{
  "idmember": "11393",
  "period_id": "2026-05",
  "idclient": "1",
  "idcompany": "1",
  "total_suggested": 285.50,
  "suggestions": [
    {
      "defaultcategory": "Groceries",
      "suggested_amount": 185.50,
      "confidence": "medium",
      "display_label": "Based on your last 3 months",
      "basis": {
        "months_analyzed": 3,
        "data_points": 3,
        "method": "wma",
        "treatment": "B",
        "period_range": "2026-02~2026-04"
      },
      "model_version": "fase0-v1"
    }
  ]
}
```

**When there is not enough history (`suggested_amount: null`):**

```json
{
  "defaultcategory": "Travel & Trips",
  "suggested_amount": null,
  "confidence": null,
  "display_label": "Not enough history for this category",
  "basis": null
}
```

| HTTP | Condition |
|------|-----------|
| `200` | Member found — returns all categories (some may have `suggested_amount: null`) |
| `404` | `idmember` not found in the active dataset |
| `422` | Invalid `period_id` format |

**`confidence` levels:** `high` (≥6 months) · `medium` (3–5) · `low` (2) · `null` (insufficient data)

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

Swagger UI: `http://localhost:8000/docs` — member dropdown shows top-10 members with real suggestions.

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

That single cell controls everything:

| | dev | alpha |
|--|-----|-------|
| **S3 model path** | `smart_budget/endpoint/v1/dev/model.tar.gz` | `smart_budget/endpoint/v1/alpha/model.tar.gz` |
| **Endpoint name** | `smart-budget-suggestion-endpoint-dev` | `smart-budget-suggestion-endpoint-alpha` |
| **Data bundled** | `smart_budget_db_dev.csv` | `smart_budget_db_alpha.csv` |

The SageMaker endpoint accepts the same `{idmember, period_id}` contract and returns the same response schema as the local endpoint.

---

## Tests

```bash
pytest tests/ -v --cov=src/smart_budget --cov-report=term-missing
# 133 passed, 4 skipped
```

---

## Model

**WMA Treatment B · lookback=3** — selected in DATA-1138 (CRWS=0.5372, MAE=$48.63).

- **Treatment B:** skips months with $0 spend — calculates only over months with real activity.
- **lookback=3:** uses the 3 complete calendar months before the budgeted month.
- **Gating:** minimum 2 months with data to emit a suggestion; otherwise `suggested_amount: null`.

---

## Filtering rules (never bypass)

```python
# INCLUDE
status  == 'POSTED'   # Never Pending, Cancelled, Hold
type    == 'expense'  # Expenditures only — no income
deleted IS NULL

# EXCLUDE
defaultcategory IN ('Uncategorized', 'Income', 'Money Sent')
transaction_type IN ('Internal', 'Member-to-Member')
```

---

## Legal constraints

- **No robo-adviser (SEC):** suggests based on history only — never recommends what to do.
- **UDAAP / CFPB:** `display_label` must be neutral and descriptive. ❌ "You should spend less on X".
- **Multi-tenancy:** every operation filtered by `idClient / idCompany / idMember`.
- **PII:** never log individual amounts or unhashed member IDs (SHA-256 + `SB_LOG_SALT`).

