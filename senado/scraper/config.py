"""
config.py — Configuración central del scraper del Senado.

Contiene constantes, paths, URLs del portal, mapeos de partidos
y parámetros HTTP usados por todos los módulos del scraper.
"""

from pathlib import Path

# --- Paths del proyecto ---
PROJECT_DIR: Path = Path(__file__).resolve().parent.parent.parent
SENADO_DB_PATH: Path = PROJECT_DIR / "db" / "senado.db"
SENADO_CACHE_DIR: Path = PROJECT_DIR / "cache" / "senado"

# --- URLs del portal del Senado ---
SENADO_BASE_URL: str = "https://www.senado.gob.mx"
SENADO_LEGISLATURA: str = "66"
SENADO_VOTACIONES_URL: str = f"{SENADO_BASE_URL}/{SENADO_LEGISLATURA}/votaciones/"
SENADO_VOTACION_URL_TEMPLATE: str = (
    f"{SENADO_BASE_URL}/{SENADO_LEGISLATURA}/votacion/{{id}}"
)
SENADO_AJAX_TABLE_URL: str = (
    f"{SENADO_BASE_URL}/{SENADO_LEGISLATURA}/app/votaciones/functions/viewTableVot.php"
)

# --- Headers para páginas normales del portal ---
SENADO_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Referer": f"{SENADO_BASE_URL}/{SENADO_LEGISLATURA}/votacion/",
}

# --- Headers para peticiones AJAX (endpoint viewTableVot.php) ---
SENADO_AJAX_HEADERS: dict[str, str] = {
    **SENADO_HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "Referer": f"{SENADO_BASE_URL}/{SENADO_LEGISLATURA}/votacion/",
}

# --- HTTP ---
REQUEST_DELAY: float = 2.0
REQUEST_TIMEOUT: float = 30.0
MAX_RETRIES: int = 3

# --- Mapeo de partidos: abreviatura → nombre completo ---
PARTY_NAMES: dict[str, str] = {
    "MORENA": "Morena",
    "PAN": "Partido Acción Nacional",
    "PRI": "Partido Revolucionario Institucional",
    "PVEM": "Partido Verde Ecologista de México",
    "PT": "Partido del Trabajo",
    "MC": "Movimiento Ciudadano",
    "SG": "Sin Grupo Parlamentario",
}

# --- Mapeo inverso: nombre completo → abreviatura ---
PARTY_BY_ABBR: dict[str, str] = {v: k for k, v in PARTY_NAMES.items()}

# --- Mapeo de partidos a IDs de organización (usando prefijos O01-O07) ---
# Coincide con el schema de la cámara de Diputados
PARTY_TO_ORG_ID: dict[str, str] = {
    "MORENA": "O01",
    "PAN": "O02",
    "PRI": "O03",
    "PVEM": "O04",
    "PT": "O05",
    "MC": "O06",
    "SG": "O07",
}

# --- Mapeo de sentido de voto del portal a formato interno ---
SENTIDO_MAP: dict[str, str] = {
    "PRO": "a_favor",
    "CONTRA": "en_contra",
    "ABSTENCIÓN": "abstencion",
}
