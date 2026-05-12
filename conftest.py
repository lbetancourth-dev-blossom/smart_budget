"""Root conftest.py — adds src/ and project root to sys.path."""
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
# Add src/ so `from smart_budget import ...` works
sys.path.insert(0, str(ROOT / "src"))
# Add project root so `from tests.conftest import _load_fixture` works
sys.path.insert(0, str(ROOT))
