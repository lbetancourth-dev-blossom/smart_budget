# Spec — DATA-1139
**DS - Extraer datasets de test por fuente (test_internal / test_external)**

- **Plan:** `changes/DATA-1139/plan.md` ✓ approved
- **Método de merge:** Squash and merge → `development`
- **Estrategia TDD:** tests primero (RED) → implementación mínima (GREEN) → refactor

---

## Task 1 — Tests unitarios `tests/unit/test_extract_test_datasets.py`

**Descripción:** Escribir todos los tests antes de crear el script. Los tests deben fallar
(RED) hasta que la implementación en Task 2 esté completa.

**Archivo a crear:** `tests/unit/test_extract_test_datasets.py`

### Test contracts

```python
# Setup del módulo en tests — mismo patrón que test_eval_runner.py
_SCRIPTS_DIR = str(pathlib.Path(__file__).parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from extract_test_datasets import split_by_source, write_atomic, REQUIRED_COLUMNS
```

#### TC-1 — Split básico: SUB → internal, EXT → external

```python
def test_split_sub_goes_to_internal():
    # Arrange
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None, None, 100.0),
        ("EXT001", "expenditure", "DINING",    None, "POSTED", 50.0),
    ])
    # Act
    internal, external, n_unknown = split_by_source(df)
    # Assert
    assert len(internal) == 1
    assert internal.iloc[0]["idtransaction"] == "SUB001"
    assert len(external) == 1
    assert external.iloc[0]["idtransaction"] == "EXT001"
    assert n_unknown == 0
```

#### TC-2 — Prefijo LOAN → internal

```python
def test_split_loan_goes_to_internal():
    # Arrange
    df = _make_fact_df([
        ("LOAN001", "expenditure", "AUTO", None, None, 200.0),
        ("LOAN002", "expenditure", "AUTO", None, None, 300.0),
    ])
    # Act
    internal, external, n_unknown = split_by_source(df)
    # Assert
    assert len(internal) == 2
    assert len(external) == 0
    assert n_unknown == 0
```

#### TC-3 — Miembro con txns OLB y EXT aparece en ambos CSVs

```python
def test_member_in_both_files_when_has_olb_and_ext():
    # Arrange — mismo idaccount en SUB y EXT
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None,    None,     100.0, "ACC1"),
        ("EXT001", "expenditure", "DINING",    None,    "POSTED",  50.0, "ACC1"),
    ])
    # Act
    internal, external, _ = split_by_source(df)
    # Assert
    assert "ACC1" in internal["idaccount"].values
    assert "ACC1" in external["idaccount"].values
```

#### TC-4 — Prefijo desconocido excluido de ambos, n_unknown > 0

```python
def test_unknown_prefix_excluded_from_both():
    # Arrange
    df = _make_fact_df([
        ("XYZ001", "expenditure", "DINING", None, "POSTED", 75.0),
        ("SUB001", "expenditure", "DINING", None, None,    100.0),
    ])
    # Act
    internal, external, n_unknown = split_by_source(df)
    # Assert
    assert n_unknown == 1
    assert len(internal) == 1
    assert len(external) == 0
    assert "XYZ001" not in internal["idtransaction"].values
    assert "XYZ001" not in external["idtransaction"].values
```

#### TC-5 — filter_transactions aplicado: OLB PENDING excluido

```python
def test_filter_applied_pending_olb_excluded():
    # Arrange — SUB con status PENDING debe ser excluido por filter_transactions
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None, "PENDING", 100.0),
        ("SUB002", "expenditure", "GROCERIES", None, None,      80.0),
    ])
    # Act — pasar por filter antes de split (como hace el script main)
    from smart_budget.filters import filter_transactions
    filtered = filter_transactions(df)
    internal, external, _ = split_by_source(filtered)
    # Assert
    assert len(internal) == 1
    assert internal.iloc[0]["idtransaction"] == "SUB002"
```

#### TC-6 — Source vacía post-filtro: split devuelve DataFrame vacío, no excepción

```python
def test_empty_source_returns_empty_df_not_exception():
    # Arrange — solo SUB rows, ningún EXT
    df = _make_fact_df([
        ("SUB001", "expenditure", "GROCERIES", None, None, 100.0),
    ])
    # Act
    internal, external, _ = split_by_source(df)
    # Assert
    assert len(external) == 0
    assert isinstance(external, pd.DataFrame)  # no excepción, DataFrame vacío
```

#### TC-7 — write_atomic escribe CSV y aplica chmod 600

```python
def test_write_atomic_creates_file_with_restricted_permissions(tmp_path):
    # Arrange
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    out = tmp_path / "test.csv"
    # Act
    write_atomic(df, out)
    # Assert
    assert out.exists()
    assert not (tmp_path / "test.csv.tmp").exists()  # tmp limpiado
    import stat
    mode = stat.S_IMODE(out.stat().st_mode)
    assert mode == 0o600
```

#### TC-8 — write_atomic aplica chmod 600 al .tmp antes de os.replace

```python
def test_write_atomic_tmp_file_has_restricted_permissions_before_replace(tmp_path, monkeypatch):
    # Arrange — interceptar os.replace para inspeccionar el .tmp antes de que desaparezca
    import stat, os as real_os
    captured_tmp_mode = {}

    original_replace = real_os.replace
    def mock_replace(src, dst):
        captured_tmp_mode["mode"] = stat.S_IMODE(real_os.stat(src).st_mode)
        original_replace(src, dst)
    monkeypatch.setattr("os.replace", mock_replace)

    df = pd.DataFrame({"a": [1], "b": [2]})
    out = tmp_path / "out.csv"
    # Act
    write_atomic(df, out)
    # Assert — .tmp tenía permisos 600 antes de rename
    assert captured_tmp_mode["mode"] == 0o600
```

#### TC-9 — output contiene solo OUTPUT_COLUMNS (data minimization, SC-1)

```python
def test_split_output_uses_only_output_columns():
    # Arrange — DataFrame con columnas extra (description, note, balance)
    df = _make_fact_df([("SUB001", "expenditure", "GROCERIES", None, None, 100.0)])
    df["description"] = "Walmart purchase"
    df["note"] = "user note"
    df["balance"] = 500.0
    from smart_budget.filters import filter_transactions
    filtered = filter_transactions(df)
    # Act
    internal, _, _ = split_by_source(filtered)
    # Assert — columnas extra no deben aparecer en el output
    from extract_test_datasets import OUTPUT_COLUMNS
    for col in internal.columns:
        assert col in OUTPUT_COLUMNS, f"Columna inesperada en output: {col}"
```

```python
def _make_fact_df(rows, idaccount="ACC1"):
    """rows: list of (idtransaction, incomeexpenditure, defaultcategory, deletedat, status, amount[, idaccount])"""
    return pd.DataFrame([
        {
            "idtransaction": r[0],
            "incomeexpenditure": r[1],
            "defaultcategory": r[2],
            "deletedat": r[3],
            "status": r[4],
            "amount": r[5],
            "idaccount": r[6] if len(r) > 6 else idaccount,
            "idclient": "CLI1",
            "idcompany": "CO1",
            "date": "2025-06-15",
            "currency": "USD",
        }
        for r in rows
    ])
```

---

## Task 2 — Script `scripts/extract_test_datasets.py`

**Descripción:** Implementar el script CLI que produce `test_internal.csv` y `test_external.csv`.
Todos los tests del Task 1 deben pasar (GREEN) al terminar esta tarea.

**Archivo a crear:** `scripts/extract_test_datasets.py`

### Columnas de output (data minimization — security control SC-1)

Los CSVs de output emiten **solo las columnas necesarias para eval_runner.py**.
No usar CANONICAL_COLS completo (32 cols con `description`, `note`, `balance`, `enrichment`
que contienen PII innecesario para este uso).

```python
OUTPUT_COLUMNS = [
    "idtransaction", "idclient", "idcompany", "idaccount",
    "defaultcategory", "incomeexpenditure", "amount", "date",
    "status", "deletedat",
]
```

### Funciones públicas a implementar

```python
REQUIRED_COLUMNS: frozenset[str]
# Mismo conjunto que run_smart_budget_prep.py REQUIRED_COLUMNS:
# idtransaction, idclient, idcompany, idaccount, defaultcategory,
# incomeexpenditure, amount, date, status, deletedat

def split_by_source(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    Separa un DataFrame en transacciones internas (OLB) y externas (DOUGH/Plaid).

    Args:
        df: DataFrame filtrado con esquema de fact_transactions.

    Returns:
        Tuple (internal_df, external_df, n_unknown):
        - internal_df: filas con idtransaction que empieza con 'SUB' o 'LOAN'
        - external_df: filas con idtransaction que empieza con 'EXT'
        - n_unknown: cantidad de filas excluidas por prefijo desconocido
    """

def write_atomic(df: pd.DataFrame, path: Path) -> None:
    """
    Escribe df como CSV en path de forma atómica (tmp → os.replace → chmod 600).

    Seguridad (SC-2, SC-3):
    - El .tmp usa suffix con PID para evitar race condition en ejecuciones concurrentes.
    - chmod 0o600 aplicado al .tmp ANTES de os.replace (no solo al destino final).

    Args:
        df: DataFrame a escribir.
        path: Destino final del CSV.
    """

def main() -> None:
    """CLI entry point. Parsea args, ejecuta pipeline, escribe outputs."""
```

### CLI args

```
--input      PATH   Input fact_transactions.csv
                    (default: data/dough/fact_transactions.csv relativo a repo root)
--output-dir PATH   Directorio de output
                    (default: data/dough/test/)
```

### Logging estructurado (structlog)

```python
logger.info("job_start", input_path=str(input_path))
logger.info("filter_applied", rows_before=N, rows_after=M)
logger.warning("unknown_prefix_skipped", n_unknown=K)   # solo si K > 0
logger.info("write_complete", file="test_internal.csv", rows=N_int, path=str(p))
logger.info("write_complete", file="test_external.csv", rows=N_ext, path=str(p))
logger.info("job_done",
    n_internal_rows=N_int,
    n_external_rows=N_ext,
    n_unknown_skipped=K,
    n_internal_accounts=len(internal["idaccount"].unique()),
    n_external_accounts=len(external["idaccount"].unique()),
)
```

### Error handling

| Condición | Comportamiento |
|-----------|---------------|
| `--input` no existe | `logger.error("input_not_found", path=...)` + `sys.exit(1)` |
| Columnas requeridas faltantes | `logger.error("schema_error", missing=list(...))` + `sys.exit(1)` |
| DataFrame vacío post-filtro | Log warning, escribir ambos CSVs vacíos (0 filas), exit 0 |
| Source vacía (ej. sin EXT) | Log warning, escribir CSV de 0 filas, continuar con la otra source |
| `--output-dir` fuera de `data/` | `logger.warning("output_outside_data_dir", path=...)` — no abortar |

### Patrón de `_write_atomic` (implementación exacta — SC-2, SC-3)

```python
def write_atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = Path(str(path) + f".{os.getpid()}.tmp")   # SC-2: PID evita race condition
    df[OUTPUT_COLUMNS].to_csv(tmp, index=False)
    os.chmod(tmp, 0o600)                              # SC-3: permisos en .tmp ANTES de replace
    os.replace(tmp, path)
    os.chmod(path, 0o600)                             # doble seguridad en destino final
```

### Patrón de imports (seguir run_smart_budget_prep.py)

```python
import sys, os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
import structlog
from smart_budget.filters import filter_transactions
```

---

## Verificación de completitud

Después de cada tarea, verificar:

```bash
# Task 1 — tests deben estar en RED (ImportError o NameError esperado)
cd .worktrees/DATA-1139 && python -m pytest tests/unit/test_extract_test_datasets.py -v

# Task 2 — todos los tests deben estar en GREEN
cd .worktrees/DATA-1139 && python -m pytest tests/unit/test_extract_test_datasets.py -v
python -m pytest tests/ -v --cov=src/smart_budget --cov-report=term-missing  # suite completa

# Smoke test del script
python scripts/extract_test_datasets.py --help
```

---

## Consideraciones de seguridad

- Nunca loguear IDs individuales de miembros ni montos de transacciones
- `data/dough/test/` está cubierto por `.gitignore` (regla `data/`) — confirmar con `git status`
- `chmod 600` aplicado por `write_atomic` en ambos outputs
- Sin credenciales hardcodeadas; sin llamadas a S3 en este script
