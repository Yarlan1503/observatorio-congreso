"""
config.py — Configuración central del scraper del Senado.

Constantes, paths y configuración anti-WAF usadas por todos
los módulos del scraper del Senado.
"""

from pathlib import Path

# --- Paths del proyecto ---
# parent.parent.parent: senado/scraper/ → senado/ → observatorio-congreso/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DB_PATH: Path = PROJECT_ROOT / "db" / "congreso.db"
CACHE_DIR: Path = PROJECT_ROOT / "cache" / "senado"
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

# --- HTTP ---
MAX_RETRIES: int = 3
BASE_BACKOFF: float = 2.0  # segundos
DEFAULT_DELAY: float = 2.0  # segundos entre requests
REQUEST_TIMEOUT: float = 30.0
