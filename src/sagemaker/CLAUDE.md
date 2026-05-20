# SageMaker Inference

> Contexto por módulo para agentes AI. Complementa `docs/codemap/05-sagemaker/README.md`.

## Propósito

Script de inferencia para AWS SageMaker (`SKLearnModel`, imagen `sklearn:1.2-1`) que expone el pipeline WMA a través del protocolo de 4 funciones handler.

## Dónde vive cada cosa

```
src/sagemaker/
├── __init__.py        → marker de paquete (vacío)
├── inference.py       → model_fn, input_fn, predict_fn, output_fn
└── requirements.txt   → pins: numpy==1.23.5, pandas==1.5.3, structlog>=21.0.0
```

## Archivos clave

- `inference.py` — script principal que SageMaker ejecuta en el contenedor
  - Línea 133: `base_dir = Path(model) / "data"` — los CSVs están en subdirectorio `data/`
  - Línea 134: `reference_date = str(pd.Period(period_id, freq="M") - 1)` — CRÍTICO: deben ser líneas separadas
  - `_METHOD="wma"`, `_TREATMENT="B"`, `_LOOKBACK=3`, `_MIN_MONTHS_GATING=2` — constantes de configuración
- `requirements.txt` — dependencias a instalar en el contenedor

## Convenciones

- Seguir estrictamente el protocolo de 4 funciones de `SKLearnModel`
- Imports lazy dentro de `predict_fn` para evitar fallos en import-time
- `_synthetic_accounts.cache_clear()` en cada `predict_fn` para inferencia stateless
- NUNCA instalar `statsmodels` en este contenedor (ABI conflict con numpy 1.23.5)

## Dependencias

- Importa de: `smart_budget.aggregator`, `smart_budget.loader`, `smart_budget.model` (bundled en tarball)
- Importado por: SageMaker Runtime (via `source_dir=str(REPO_ROOT / "src" / "sagemaker")`)

## Tests

- Correr: `pytest tests/unit/test_inference.py -v`
- 6 tests: TC-T5.1 – TC-T5.6
- Los fixtures crean `tmp_path / "data" /` para simular la estructura del tarball

## Gotchas

- **NUNCA** fusionar las líneas `base_dir` y `reference_date` — el `NameError` anterior fue causado por esto
- El tarball debe contener `data/smart_budget_synthetic.csv`, `data/test_internal.csv`, `data/test_external.csv` y el paquete `smart_budget/`
- `source_dir` en el notebook debe apuntar a `src/sagemaker/` (no a `src/api/`)
- Si el contenedor falla con `ImportError: numpy.core.multiarray`, alguien instaló statsmodels — ver `requirements.txt`
- Para imagen `sagemaker-distribution:3.8.5`: correr `pip install sagemaker-core --force-reinstall` en Cell 1 del notebook

## See also

- [Module overview](../../docs/codemap/05-sagemaker/README.md)
- [Deploy guide](../../docs/guides/smart-budget/How-To-Use-Endpoint.md)
- [Notebook](../../notebooks/smart_budget_sagemaker_endpoint.ipynb)
- [Root project context](../../CLAUDE.md)
- [FastAPI equivalent](../api/CLAUDE.md)
