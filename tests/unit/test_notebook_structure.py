"""tests/unit/test_notebook_structure.py — Structural checks for the SageMaker endpoint notebook (DATA-1275 T5.3).

These tests JSON-load the notebook and verify the required changes per spec.
"""
from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_PATH = Path(__file__).parent.parent.parent / "notebooks" / "smart_budget_sagemaker_endpoint.ipynb"


def _load_notebook():
    with open(NOTEBOOK_PATH) as f:
        return json.load(f)


def _all_sources(nb) -> list[str]:
    return ["".join(cell["source"]) for cell in nb["cells"]]


def test_notebook_has_no_data_csv_packaging():
    """
    Assert: no cell source contains 'DATA_CSV_SRC' or 'smart_budget_data.csv'.
    """
    nb = _load_notebook()
    sources = _all_sources(nb)
    for src in sources:
        assert "DATA_CSV_SRC" not in src, f"Found 'DATA_CSV_SRC' in cell: {src[:100]!r}"
        assert "smart_budget_data.csv" not in src, f"Found 'smart_budget_data.csv' in cell: {src[:100]!r}"


def test_notebook_has_athena_env_vars():
    """
    Assert: at least one cell contains all four Athena env var names.
    """
    nb = _load_notebook()
    sources = _all_sources(nb)
    required = ["ATHENA_S3_STAGING_DIR", "ATHENA_REGION_NAME", "ATHENA_DATABASE", "ATHENA_TABLE"]
    combined = "\n".join(sources)
    for var in required:
        assert var in combined, f"Missing Athena env var '{var}' in notebook"


def test_notebook_sklearn_model_passes_env():
    """
    Assert: the SKLearnModel constructor cell contains 'env=' referencing ATHENA_S3_STAGING_DIR.
    """
    nb = _load_notebook()
    sources = _all_sources(nb)
    sklearn_cells = [s for s in sources if "SKLearnModel(" in s]
    assert len(sklearn_cells) >= 1, "No SKLearnModel( found in notebook"
    sklearn_src = sklearn_cells[0]
    assert "env=" in sklearn_src, "SKLearnModel( does not contain 'env='"
    assert "ATHENA_S3_STAGING_DIR" in sklearn_src, "env= does not reference ATHENA_S3_STAGING_DIR"


def test_notebook_documents_iam_requirements():
    """
    Assert: a markdown cell contains both 'athena:StartQueryExecution' and 'execution role' (case-insensitive).
    """
    nb = _load_notebook()
    markdown_cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown"]
    for src in markdown_cells:
        if "athena:StartQueryExecution".lower() in src.lower() and "execution role" in src.lower():
            return
    raise AssertionError(
        "No markdown cell found containing both 'athena:StartQueryExecution' and 'execution role'"
    )
