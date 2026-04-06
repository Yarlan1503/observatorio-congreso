"""
text_utils.py — Utilidades de texto compartidas entre scrapers del Congreso.

Provee funciones de normalización para comparación de nombres,
clasificación de motions y requisitos de mayoría,
utilizada tanto por Diputados como por Senado.
"""

import re
import unicodedata


def normalize_name(nombre: str) -> str:
    """Normaliza un nombre para comparación: lowercase, sin acentos, sin espacios extra.

    Ej: "Álvarez Villaseñor Raúl" → "alvarez villasenor raul"

    Args:
        nombre: Nombre completo en formato original.

    Returns:
        Nombre normalizado listo para comparación.
    """
    # Eliminar acentos/diacríticos
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase y colapsar espacios
    return re.sub(r"\s+", " ", sin_acentos.lower().strip())


# Mapa de meses en español → número (con zero-padding)
MESES_ES: dict[str, str] = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


# =============================================================================
# Funciones de clasificación de motions (compartidas entre cámaras)
# =============================================================================


def determinar_requirement(titulo: str) -> str:
    """Infiere el tipo de mayoría requerida del título/descripción.

    Reglas:
    - 'mayoria_calificada' si contiene "CONSTITUCIÓN" o "CONSTITUCIONAL"
    - 'mayoria_simple' en otro caso

    Args:
        titulo: Título o descripción de la votación/motion.

    Returns:
        Tipo de mayoría requerida.
    """
    titulo_up = titulo.upper()
    if "CONSTITUCI" in titulo_up:
        return "mayoria_calificada"
    return "mayoria_simple"


def determinar_tipo_motion(titulo: str) -> str:
    """Infiere el tipo de motion del título/descripción.

    Reglas:
    - 'reforma_constitucional' si contiene "CONSTITUCIÓN" o "CONSTITUCIONAL"
    - 'ley_secundaria' si contiene "LEY" pero no "CONSTITUCIÓN"
    - 'ordinaria' si contiene "PRESUPUESTO" o "DECRETO" con "INGRESOS/EGRESOS"
    - 'otra' en otro caso

    Args:
        titulo: Título o descripción de la votación/motion.

    Returns:
        Clasificación del tipo de motion.
    """
    titulo_up = titulo.upper()

    if "CONSTITUCI" in titulo_up:
        return "reforma_constitucional"

    if "LEY" in titulo_up:
        return "ley_secundaria"

    if "PRESUPUESTO" in titulo_up:
        return "ordinaria"

    if "DECRETO" in titulo_up and ("INGRESO" in titulo_up or "EGRESO" in titulo_up):
        return "ordinaria"

    return "otra"
