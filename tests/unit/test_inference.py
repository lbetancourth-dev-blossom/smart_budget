"""tests/unit/test_inference.py — Unit tests for src/sagemaker/inference.py (DATA-1140).

Test contracts: TC-T5.1 – TC-T5.6
"""
from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# TC-T5.1 — model_fn: returns a path with CSV files
# ---------------------------------------------------------------------------

def test_inference_model_fn(tmp_path):
    """
    Arrange: tmp_dir with the 3 bundled CSVs (synthetic, internal, external).
    Act: model_fn(str(tmp_dir)).
    Assert: returns a Path that contains the 3 CSV files.
    """
    import pandas as pd
    from src.sagemaker.inference import model_fn

    # Create bundled CSV structure (like inside model.tar.gz)
    (tmp_path / "smart_budget_synthetic.csv").write_text(
        "idclient,idcompany,idaccount,idcategory,defaultcategory,period_yyyymm,monthly_total\n"
        "1,1,SYN001,5,Groceries,2026-02,300.0\n"
    )
    (tmp_path / "test_internal.csv").write_text(
        "idclient,idcompany,idaccount,idtransaction,defaultcategory,date,amount,"
        "incomeexpenditure,deletedat,status\n"
    )
    (tmp_path / "test_external.csv").write_text(
        "idclient,idcompany,idaccount,idtransaction,defaultcategory,date,amount,"
        "incomeexpenditure,deletedat,status\n"
    )

    result = model_fn(str(tmp_path))

    from pathlib import Path
    result_path = Path(result)
    assert result_path.exists()
    assert (result_path / "smart_budget_synthetic.csv").exists()


# ---------------------------------------------------------------------------
# TC-T5.2 — input_fn: valid JSON → dict with 3 keys
# ---------------------------------------------------------------------------

def test_inference_input_fn_valid():
    """
    Arrange: valid JSON payload.
    Act: input_fn(json_str, "application/json").
    Assert: dict with exactly the 3 expected keys.
    """
    from src.sagemaker.inference import input_fn

    payload = json.dumps({
        "idaccount": "INT23",
        "defaultcategory": "Groceries",
        "period_id": "2026-05",
    })

    result = input_fn(payload, "application/json")

    assert isinstance(result, dict)
    assert "idaccount" in result
    assert "defaultcategory" in result
    assert "period_id" in result
    assert result["idaccount"] == "INT23"
    assert result["defaultcategory"] == "Groceries"
    assert result["period_id"] == "2026-05"


# ---------------------------------------------------------------------------
# TC-T5.3 — input_fn: invalid JSON → ValueError
# ---------------------------------------------------------------------------

def test_inference_input_fn_invalid_json():
    """
    Arrange: non-JSON string.
    Act: input_fn("not-json", "application/json").
    Assert: ValueError (or json.JSONDecodeError) raised.
    """
    from src.sagemaker.inference import input_fn

    with pytest.raises((ValueError, json.JSONDecodeError, Exception)):
        input_fn("not-json", "application/json")


# ---------------------------------------------------------------------------
# TC-T5.4 — predict_fn: returns valid schema dict
# ---------------------------------------------------------------------------

def test_inference_predict_fn_returns_valid_schema(tmp_path):
    """
    Arrange: SYN001/GROCERIES with 3 months of synthetic history.
    Act: predict_fn(data, model_dir).
    Assert: dict with suggested_amount >= 0 (or null) and confidence in expected set.
    """
    import pandas as pd
    from src.sagemaker.inference import predict_fn

    # Build synthetic CSV
    synth_rows = [
        {"idclient": "1", "idcompany": "1", "idaccount": "SYN001",
         "idcategory": "5", "defaultcategory": "Groceries",
         "period_yyyymm": "2026-02", "monthly_total": "300.0"},
        {"idclient": "1", "idcompany": "1", "idaccount": "SYN001",
         "idcategory": "5", "defaultcategory": "Groceries",
         "period_yyyymm": "2026-03", "monthly_total": "320.0"},
        {"idclient": "1", "idcompany": "1", "idaccount": "SYN001",
         "idcategory": "5", "defaultcategory": "Groceries",
         "period_yyyymm": "2026-04", "monthly_total": "340.0"},
    ]
    pd.DataFrame(synth_rows).to_csv(tmp_path / "smart_budget_synthetic.csv", index=False)
    (tmp_path / "test_internal.csv").write_text(
        "idclient,idcompany,idaccount,idtransaction,defaultcategory,date,amount,"
        "incomeexpenditure,deletedat,status\n"
    )
    (tmp_path / "test_external.csv").write_text(
        "idclient,idcompany,idaccount,idtransaction,defaultcategory,date,amount,"
        "incomeexpenditure,deletedat,status\n"
    )

    data = {"idaccount": "SYN001", "defaultcategory": "Groceries", "period_id": "2026-05"}

    result = predict_fn(data, str(tmp_path))

    assert isinstance(result, dict)
    assert "suggested_amount" in result
    if result["suggested_amount"] is not None:
        assert result["suggested_amount"] >= 0.0
        assert result.get("confidence") in {"low", "medium", "high", None}


# ---------------------------------------------------------------------------
# TC-T5.5 — predict_fn: 1 month → gating → null response
# ---------------------------------------------------------------------------

def test_inference_predict_fn_gating(tmp_path):
    """
    Arrange: account with only 1 month of data (below gating threshold of 2).
    Act: predict_fn(data, model_dir).
    Assert: suggested_amount == null; confidence == null.
    """
    import pandas as pd
    from src.sagemaker.inference import predict_fn

    # Only 1 month — gating min_months=2 will filter it out
    synth_rows = [
        {"idclient": "1", "idcompany": "1", "idaccount": "GATED001",
         "idcategory": "5", "defaultcategory": "Groceries",
         "period_yyyymm": "2026-02", "monthly_total": "300.0"},
    ]
    pd.DataFrame(synth_rows).to_csv(tmp_path / "smart_budget_synthetic.csv", index=False)
    (tmp_path / "test_internal.csv").write_text(
        "idclient,idcompany,idaccount,idtransaction,defaultcategory,date,amount,"
        "incomeexpenditure,deletedat,status\n"
    )
    (tmp_path / "test_external.csv").write_text(
        "idclient,idcompany,idaccount,idtransaction,defaultcategory,date,amount,"
        "incomeexpenditure,deletedat,status\n"
    )

    data = {"idaccount": "GATED001", "defaultcategory": "Groceries", "period_id": "2026-05"}

    result = predict_fn(data, str(tmp_path))

    assert result["suggested_amount"] is None
    assert result["confidence"] is None


# ---------------------------------------------------------------------------
# TC-T5.6 — output_fn: serializes to parseable JSON string
# ---------------------------------------------------------------------------

def test_inference_output_fn():
    """
    Arrange: valid suggestion dict.
    Act: output_fn(prediction, "application/json").
    Assert: string JSON that can be parsed and contains schema fields.
    """
    from src.sagemaker.inference import output_fn

    prediction = {
        "idaccount": "INT23",
        "idclient": "1",
        "idcompany": "1",
        "defaultcategory": "Groceries",
        "period_id": "2026-05",
        "suggested_amount": 300.0,
        "confidence": "medium",
        "basis": {
            "months_analyzed": 3,
            "months_with_positive_spend": 3,
            "period_range": "2026-02 ~ 2026-04",
            "method": "wma",
            "treatment": "B",
        },
        "display_label": "Basado en tus últimos 3 meses",
        "model_version": "fase0-v1",
    }

    result = output_fn(prediction, "application/json")

    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "suggested_amount" in parsed
    assert "confidence" in parsed
    assert "basis" in parsed
