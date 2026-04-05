"""
text_utils.py — Utilidades de texto compartidas entre scrapers del Congreso.

Provee funciones de normalización para comparación de nombres,
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
