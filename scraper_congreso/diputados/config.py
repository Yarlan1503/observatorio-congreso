"""
config.py — Configuración central del scraper SITL/INFOPAL.

Contiene constantes, paths, mapeos de partidos y datos de legislaturas
usados por todos los módulos del scraper.
"""

from db.constants import CAMARA_DIPUTADOS_ID
from scraper_congreso.utils.config import (
    CACHE_DIR,
    DB_PATH,
    DEFAULT_DELAY,
    MAX_RETRIES,
    PROJECT_ROOT,
    REQUEST_TIMEOUT,
)

__all__ = [
    "BASE_URL",
    "CACHE_DIR",
    "CAMARA_DIPUTADOS_ID",
    "DB_PATH",
    "DEFAULT_DELAY",
    "DEFAULT_HEADERS",
    "LEGISLATURAS",
    "MAX_RETRIES",
    "PARTY_IMAGE_MAP",
    "PARTY_SITL_IDS",
    "PROJECT_ROOT",
    "REQUEST_DELAY",
    "REQUEST_TIMEOUT",
    "SITL_PARTY_BY_ID",
    "USER_AGENT",
]

# Alias para compatibilidad con imports existentes
REQUEST_DELAY: float = DEFAULT_DELAY

# --- URL base del SITL ---
BASE_URL: str = "https://sitl.diputados.gob.mx"

# --- HTTP ---
USER_AGENT: str = "ObservatorioCongreso/1.0 (+https://github.com/observatorio-congreso)"
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

# --- Mapa partido → SITL partidot ID (para URLs) ---
# Verificado contra HTML real: listados_votacionesnplxvi.php?partidot=14 (MORENA), etc.
PARTY_SITL_IDS: dict[str, int] = {
    "MORENA": 14,
    "PAN": 3,
    "PVEM": 5,
    "PT": 4,
    "PRI": 1,
    "MC": 6,
    "PRD": 2,
    "IND": 9,
}

# --- Mapa inverso: SITL partidot ID → nombre partido ---
SITL_PARTY_BY_ID: dict[int, str] = {v: k for k, v in PARTY_SITL_IDS.items()}

# --- Mapa filename de imagen de partido → nombre partido (para curricula) ---
PARTY_IMAGE_MAP: dict[str, str] = {
    "morena.webp": "MORENA",
    "pan.webp": "PAN",
    "pvem.webp": "PVEM",
    "pt.webp": "PT",
    "pri.webp": "PRI",
    "mc.webp": "MC",
    "prd.webp": "PRD",
}

# --- Legislaturas con datos para construcción de URLs ---
# LX-LXIII: subdominios propios (sitllx, sitllxi, etc.)
# LXIV-LXVI: mismo dominio con path prefix (/LXIV_leg/, /LXV_leg/, etc.)
LEGISLATURAS: dict[str, dict] = {
    "LX": {
        "num": 60,
        "periodo": "2006-2009",
        "base_url": "http://sitllx.diputados.gob.mx",
        "php_suffix": "np",
        "start": "2006-09-01",
        "end": "2009-08-31",
        "parties": {
            "PAN": 3,
            "PRD": 2,
            "PRI": 1,
            "CONV": 6,
            "PVEM": 5,
            "PT": 4,
            "NA": 12,
            "ALT": 13,
            "IND": 9,
        },
    },
    "LXI": {
        "num": 61,
        "periodo": "2009-2012",
        "base_url": "http://sitllxi.diputados.gob.mx",
        "php_suffix": "nplxi",
        "start": "2009-09-01",
        "end": "2012-08-31",
        "parties": {
            "PRI": 1,
            "PAN": 3,
            "PRD": 2,
            "PVEM": 5,
            "PT": 4,
            "NA": 12,
            "MC": 6,
            "IND": 9,
        },
    },
    "LXII": {
        "num": 62,
        "periodo": "2012-2015",
        "base_url": "http://sitllxii.diputados.gob.mx",
        "php_suffix": "nplxii",
        "start": "2012-09-01",
        "end": "2015-08-31",
        "parties": {
            "PRI": 1,
            "PAN": 3,
            "PRD": 2,
            "PVEM": 5,
            "MC": 6,
            "PT": 4,
            "NA": 12,
        },
    },
    "LXIII": {
        "num": 63,
        "periodo": "2015-2018",
        "base_url": "http://sitllxiii.diputados.gob.mx",
        "php_suffix": "nplxiii",
        "start": "2015-09-01",
        "end": "2018-08-31",
        "parties": {
            "PRI": 1,
            "PAN": 3,
            "PRD": 2,
            "MORENA": 14,
            "PVEM": 5,
            "MC": 6,
            "NA": 12,
            "PES": 15,
            "IND": 9,
            "SP": 16,
        },
    },
    "LXIV": {
        "num": 64,
        "periodo": "2018-2021",
        "base_url": "http://sitl.diputados.gob.mx/LXIV_leg",
        "php_suffix": "nplxiv",
        "start": "2018-09-01",
        "end": "2021-08-31",
        "parties": {
            "MORENA": 14,
            "PAN": 3,
            "PRI": 1,
            "PT": 4,
            "MC": 6,
            "PES": 15,
            "PRD": 2,
            "PVEM": 5,
            "SP": 16,
        },
    },
    "LXV": {
        "num": 65,
        "periodo": "2021-2024",
        "base_url": "http://sitl.diputados.gob.mx/LXV_leg",
        "php_suffix": "nplxv",
        "start": "2021-09-01",
        "end": "2024-08-31",
        "parties": {
            "MORENA": 14,
            "PAN": 3,
            "PRI": 1,
            "PVEM": 5,
            "PT": 4,
            "MC": 6,
            "PRD": 2,
        },
    },
    "LXVI": {
        "num": 66,
        "periodo": "2024-2027",
        "base_url": "https://sitl.diputados.gob.mx/LXVI_leg",
        "php_suffix": "nplxvi",
        "start": "2024-09-01",
        "end": "2027-08-31",
        "parties": {
            "MORENA": 14,
            "PAN": 3,
            "PVEM": 5,
            "PT": 4,
            "PRI": 1,
            "MC": 6,
            "PRD": 2,
            "IND": 9,
        },
    },
}
