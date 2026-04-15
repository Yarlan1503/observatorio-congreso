"""
constants.py — Constantes compartidas de visualización y análisis del Observatorio Congreso.

Centraliza colores, mapeos y órdenes canónicos usados en los módulos de analysis/
para evitar duplicación y garantizar consistencia visual.

Constantes principales:
    PARTY_COLORS: Colores matplotlib por partido (key = nombre corto uppercase).
    DEFAULT_COLOR: Color fallback para partidos no reconocidos.
    ORG_TO_SHORT: Mapeo org_id → nombre corto para display.
    PARTY_ORDER: Orden canónico de partidos en visualizaciones.
    CAMARA_MAP: Mapeo nombre_cámara → código corto.
    COLORES_WEB: Colores para export JSON/CachorroSpace (ECharts).
    PARTIDO_MAP: Mapeo nombre completo → sigla para export JSON.
"""

# ---------------------------------------------------------------------------
# Esquema de colores por partido (matplotlib)
# Key: nombre corto UPPERCASE — consistente con db.constants._ORG_TO_SHORT
# ---------------------------------------------------------------------------
PARTY_COLORS: dict[str, str] = {
    "MORENA": "#8B0000",  # rojo oscuro
    "PT": "#FF6600",  # naranja
    "PVEM": "#228B22",  # verde
    "PAN": "#003399",  # azul
    "PRI": "#008833",  # verde PRI
    "MC": "#FF8C00",  # naranja MC
    "PRD": "#FFD700",  # amarillo
    "Independientes": "#808080",  # gris
}

DEFAULT_COLOR: str = "#CCCCCC"

# ---------------------------------------------------------------------------
# Mapeo org_id → nombre corto (UPPERCASE, consistente con PARTY_COLORS)
# Duplicado intencionalmente de db.constants._ORG_TO_SHORT para no crear
# dependencia circular analysis → db en scripts standalone.
# ---------------------------------------------------------------------------
ORG_TO_SHORT: dict[str, str] = {
    "O01": "MORENA",
    "O02": "PT",
    "O03": "PVEM",
    "O04": "PAN",
    "O05": "PRI",
    "O06": "MC",
    "O07": "PRD",
    "O11": "Independientes",
}

# ---------------------------------------------------------------------------
# Orden canónico de partidos para visualizaciones
# ---------------------------------------------------------------------------
PARTY_ORDER: list[str] = ["MORENA", "PT", "PVEM", "PRI", "PAN", "MC", "PRD"]

# Partidos comunes para comparaciones bicamerales
COMMON_PARTIES: list[str] = ["MORENA", "PAN", "PRI", "PVEM", "PT", "MC", "PRD"]

# ---------------------------------------------------------------------------
# Mapeo de cámara → código corto
# ---------------------------------------------------------------------------
CAMARA_MAP: dict[str, str] = {"diputados": "D", "senado": "S"}

# ---------------------------------------------------------------------------
# Colores para export JSON (CachorroSpace / ECharts)
# Diferentes de PARTY_COLORS porque ECharts usa paleta distinta.
# Key: nombre corto (mixed case para display web).
# ---------------------------------------------------------------------------
COLORES_WEB: dict[str, str] = {
    "PAN": "#0055A4",
    "PRI": "#00A651",
    "PRD": "#F7B219",
    "PT": "#D8272E",
    "PVEM": "#579E33",
    "MC": "#F47920",
    "Morena": "#8B2D8B",
    "Independientes": "#888888",
}

# Mapeo nombre completo → sigla (para export JSON)
PARTIDO_MAP: dict[str, str] = {
    "Partido Acción Nacional (PAN)": "PAN",
    "Partido Revolucionario Institucional (PRI)": "PRI",
    "Partido de la Revolución Democrática (PRD)": "PRD",
    "Partido del Trabajo (PT)": "PT",
    "Partido Verde Ecologista de México (PVEM)": "PVEM",
    "Movimiento Ciudadano (MC)": "MC",
    "Morena": "Morena",
    "Independientes": "Independientes",
}
