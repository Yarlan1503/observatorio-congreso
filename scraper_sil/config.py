"""
config.py — Configuración central del scraper SIL.

URLs, headers, paths, constantes y mapeos para el portal
sil.gobernacion.gob.mx (SEGOB).
"""

from pathlib import Path

# --- Paths del proyecto ---
PROJECT_DIR: Path = Path(__file__).resolve().parent.parent.parent
SIL_DB_PATH: Path = PROJECT_DIR / "db" / "senado.db"  # Reusa BD del Senado
SIL_CACHE_DIR: Path = PROJECT_DIR / "cache" / "sil"

# --- URLs del portal SIL ---
SIL_BASE_URL: str = "http://sil.gobernacion.gob.mx"
SIL_BUSQUEDA_URL: str = f"{SIL_BASE_URL}/Busquedas/Votacion/ProcesoBusquedaAvanzada.php"
SIL_RESULTADOS_URL: str = (
    f"{SIL_BASE_URL}/Busquedas/Votacion/ResultadosBusquedaAvanzada.php"
)
SIL_DETALLE_URL: str = (
    f"{SIL_BASE_URL}/ActividadLegislativa/Votacion/DetalleVotacion.php"
)
SIL_VOTOS_URL: str = (
    f"{SIL_BASE_URL}/ActividadLegislativa/Votacion/LegisladoresVotacionAsunto.php"
)

# --- Headers HTTP para el portal SIL ---
SIL_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",  # Solicitar compresión
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# --- Parámetros por defecto para el formulario POST ---
DEFAULT_FORM_PARAMS: dict[str, str | int] = {
    "LEGISLATURA": "LXVI",
    "PAGINAS": 50,  # Resultados por página
}

# --- Legislaturas disponibles ---
LEGISLATURAS: list[str] = [
    "LVI",  # 1994-1997
    "LVII",  # 1997-2000
    "LVIII",  # 2000-2003
    "LIX",  # 2003-2006
    "LX",  # 2006-2009
    "LXI",  # 2009-2012
    "LXII",  # 2012-2015
    "LXIII",  # 2015-2018
    "LXIV",  # 2018-2021
    "LXV",  # 2021-2024
    "LXVI",  # 2024-2027
]

# --- Tipos de asunto ---
TIPO_ASUNTO_MAP: dict[str, str] = {
    "1": "Reforma Constitucional",
    "2": "Ley o Decreto",
    "3": "Punto de Acuerdo",
    "4": "Convocatoria",
    "5": "Nombramiento",
    "6": "Dictamen",
    "7": "Iniciativa",
    "8": "Propuesta",
}

# --- Resultados de votación ---
RESULTADO_MAP: dict[str, str] = {
    "A": "Aprobado",
    "D": "Desechado",
    "E": "Empate",
    "S": "Sin Definir",
}

# --- Votos ---
VOTO_MAP: dict[str, str] = {
    "F": "a_favor",
    "C": "en_contra",
    "A": "abstencion",
    "N": "ausente",
}

VOTO_REVERSE_MAP: dict[str, str] = {v: k for k, v in VOTO_MAP.items()}

# --- HTTP ---
REQUEST_DELAY: float = 1.5  # Segundos entre requests (rate limit)
REQUEST_TIMEOUT: float = 30.0  # Timeout por request
MAX_RETRIES: int = 3  # Intentos máximos con backoff exponencial

# --- Encoding del portal ---
# El portal SIL usa iso-8859-1 (latin-1), NO UTF-8
SIL_ENCODING: str = "iso-8859-1"

# --- Mapeo de partidos ---
PARTY_NAMES: dict[str, str] = {
    "MORENA": "Morena",
    "PAN": "Partido Acción Nacional",
    "PRI": "Partido Revolucionario Institucional",
    "PVEM": "Partido Verde Ecologista de México",
    "PT": "Partido del Trabajo",
    "MC": "Movimiento Ciudadano",
    "PRD": "Partido de la Revolución Democrática",
    "NA": "Nueva Alianza",
    "SP": "Sin Partido",
    "SG": "Sin Grupo",
}

# --- Scrape status ---
STATUS_PENDING: str = "pending"
STATUS_PROCESSING: str = "processing"
STATUS_COMPLETED: str = "completed"
STATUS_FAILED: str = "failed"
STATUS_SKIPPED: str = "skipped"

# --- Playwright Configuration ---
PLAYWRIGHT_HEADLESS: bool = True
PLAYWRIGHT_TIMEOUT: int = 30000  # ms
PLAYWRIGHT_USER_AGENT: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# --- Session Management ---
SESSION_TIMEOUT: int = 25 * 60  # 25 minutos (expira en ~30)
SESSION_REFRESH_BEFORE_EXPIRY: int = 5 * 60  # Refrescar 5 min antes de expirar
