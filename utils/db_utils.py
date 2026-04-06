"""
db_utils.py — Utilidades de base de datos compartidas entre scrapers del Congreso.

Funciones que necesitan una conexión BD pero son comunes a ambas cámaras.
Las utilidades de texto puro van en text_utils.py.
"""

import sqlite3

from utils.text_utils import normalize_name


def match_persona_por_nombre(
    nombre: str, conn: sqlite3.Connection, tabla: str = "person"
) -> str | None:
    """Busca una persona existente por nombre normalizado.

    Retorna el ID (P01, P02, etc.) si encuentra match, None si no.
    Compara normalizando ambos nombres (lowercase, sin acentos, sin
    espacios extra).

    Args:
        nombre: Nombre del legislador a buscar.
        conn: Conexión activa a SQLite.
        tabla: Tabla donde buscar (default "person").

    Returns:
        ID de la persona si hay match, None si no se encuentra.
    """
    nombre_norm = normalize_name(nombre)

    rows = conn.execute(f"SELECT id, nombre FROM {tabla}").fetchall()
    for person_id, person_nombre in rows:
        if normalize_name(person_nombre) == nombre_norm:
            return person_id

    return None
