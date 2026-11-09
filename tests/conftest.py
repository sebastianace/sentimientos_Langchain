"""Configuración común de pytest.

- Añade la raíz del proyecto al path para poder hacer `import almacenamiento`.
- Borra OPENAI_API_KEY del entorno: ningún test debe poder llamar a la API real.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sin_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
