"""
config.py — Configuración central del scraper del Senado.

Constantes, paths y configuración anti-WAF usadas por todos
los módulos del scraper del Senado.
"""

from pathlib import Path

from scraper_congreso.utils.config import (
    BASE_BACKOFF,
    DB_PATH,
    DEFAULT_DELAY,
    MAX_RETRIES,
    PROJECT_ROOT,
    REQUEST_TIMEOUT,
)
from scraper_congreso.utils.config import (
    CACHE_DIR as _CACHE_DIR,
)

__all__ = [
    "BASE_BACKOFF",
    "BASE_URL_LXVI",
    "CACHE_DIR",
    "COOKIE_PATH",
    "DB_PATH",
    "DEFAULT_DELAY",
    "LXVI_AJAX_URL",
    "LXVI_VOTACION_URL_TEMPLATE",
    "MAX_RETRIES",
    "PROJECT_ROOT",
    "REQUEST_TIMEOUT",
    "SENADO_ORG_ID",
    "WAF_MARKERS",
    "WAF_MAX_SIZE",
]

# Paths específicos del Senado (relativos al CACHE_DIR centralizado)
CACHE_DIR: Path = _CACHE_DIR / "senado"
COOKIE_PATH: Path = CACHE_DIR / "senado_cookies.pkl"

# --- URLs del portal LXVI ---
BASE_URL_LXVI: str = "https://www.senado.gob.mx"
LXVI_VOTACION_URL_TEMPLATE: str = f"{BASE_URL_LXVI}/66/votacion/{{id}}"
LXVI_AJAX_URL: str = f"{BASE_URL_LXVI}/66/app/votaciones/functions/viewTableVot.php"

# --- ID de la organización del Senado ---
SENADO_ORG_ID: str = "O09"  # "Senado de la República"

# --- Configuración anti-WAF ---
WAF_MARKERS: list[str] = [
    "incident_id",
    "waf block",
    "forbidden",
    "access denied",
]

WAF_MAX_SIZE: int = 5 * 1024  # 5KB — respuestas menores son sospechosas

# --- HTTP (importados de config centralizada) ---
# MAX_RETRIES, BASE_BACKOFF, DEFAULT_DELAY, REQUEST_TIMEOUT vienen del import arriba
