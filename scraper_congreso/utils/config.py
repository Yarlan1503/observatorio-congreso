"""
config.py — Configuración centralizada del Observatorio Congreso.

Lee variables de entorno con defaults sensatos. Sin dependencia python-dotenv.
"""

import os
from pathlib import Path

# --- Paths del proyecto ---
# utils/config.py → scraper_congreso/ → observatorio-congreso/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent


def _get_path(env_var: str, default: Path) -> Path:
    """Lee un path de variable de entorno o usa default."""
    val = os.environ.get(env_var)
    if val:
        return Path(val)
    return default


def _get_float(env_var: str, default: float) -> float:
    """Lee un float de variable de entorno o usa default."""
    val = os.environ.get(env_var)
    if val:
        try:
            return float(val)
        except ValueError:
            return default
    return default


def _get_int(env_var: str, default: int) -> int:
    """Lee un int de variable de entorno o usa default."""
    val = os.environ.get(env_var)
    if val:
        try:
            return int(val)
        except ValueError:
            return default
    return default


# --- Paths centralizados ---
DB_PATH: Path = _get_path("OBSERVATORIO_DB_PATH", PROJECT_ROOT / "db" / "congreso.db")
CACHE_DIR: Path = _get_path("OBSERVATORIO_CACHE_DIR", PROJECT_ROOT / "cache")
LOG_DIR: Path = _get_path("OBSERVATORIO_LOG_DIR", PROJECT_ROOT / "logs")

# --- HTTP ---
DEFAULT_DELAY: float = _get_float("OBSERVATORIO_DELAY", 2.0)
REQUEST_TIMEOUT: float = _get_float("OBSERVATORIO_TIMEOUT", 30.0)
MAX_RETRIES: int = _get_int("OBSERVATORIO_MAX_RETRIES", 3)
BASE_BACKOFF: float = _get_float("OBSERVATORIO_BACKOFF", 2.0)

# --- Batch ---
BATCH_SIZE: int = _get_int("OBSERVATORIO_BATCH_SIZE", 100)
