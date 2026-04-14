"""Fixtures compartidas para tests del Observatorio Congreso."""

import sqlite3
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"


@pytest.fixture
def db_connection():
    """Conexión a la BD de test (solo lectura)."""
    if not DB_PATH.exists():
        pytest.skip("BD de congreso no disponible")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
