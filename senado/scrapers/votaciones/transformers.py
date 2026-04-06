"""
transformers.py — Funciones de transformación para el scraper del Senado.

Lógica de transformación separada del loader y CLI:
- determinar_resultado(): determina aprobada/rechazada/empate
- inferir_genero(): infiere género del nombre
- parse_fecha_iso(): convierte fechas del portal a ISO
- normalize_voto(): normaliza sentido del voto
- match_persona_por_nombre(): búsqueda por nombre normalizado

NOTE: determinar_requirement() y determinar_tipo_motion() están en
utils/text_utils.py (compartidas entre cámaras).
"""

import datetime
import logging
import sqlite3
import unicodedata

from utils.text_utils import normalize_name

logger = logging.getLogger(__name__)


# =============================================================================
# Funciones de clasificación de motion
#
# NOTE: determinar_requirement() y determinar_tipo_motion() están en
# utils/text_utils.py (compartidas entre cámaras). Importarlas desde ahí.
# =============================================================================


def determinar_resultado(
    pro_count: int,
    contra_count: int,
    requirement: str = "mayoria_simple",
    abstention_count: int = 0,
) -> str:
    """Determina el resultado de una votación según el tipo de mayoría.

    - mayoria_simple: aprobada si a_favor > en_contra, empate si iguales.
    - mayoria_calificada (Art. 135 CPEUM): aprobada si a_favor >= 2/3 de
      los presentes (presentes = a_favor + en_contra + abstenciones).
      Rechazada en caso contrario. Si no hay datos de abstención
      (abstention_count == 0), fallback a mayoría simple.

    Args:
        pro_count: Votos a favor.
        contra_count: Votos en contra.
        requirement: Tipo de mayoría requerida.
        abstention_count: Votos en abstención (default 0).

    Returns:
        "aprobada", "rechazada" o "empate".
    """
    if requirement == "mayoria_calificada":
        presentes = pro_count + contra_count + abstention_count
        if presentes == 0:
            return "rechazada"  # nadie presente → no puede aprobar
        if abstention_count == 0:
            # Fallback a mayoría simple si no hay datos de abstención
            if pro_count > contra_count:
                return "aprobada"
            elif pro_count < contra_count:
                return "rechazada"
            else:
                return "empate"
        umbral = (2 / 3) * presentes
        if pro_count >= umbral:
            return "aprobada"
        else:
            return "rechazada"
    else:
        if pro_count > contra_count:
            return "aprobada"
        elif pro_count < contra_count:
            return "rechazada"
        else:
            return "empate"


# =============================================================================
# Funciones de normalización
# =============================================================================


def parse_fecha_iso(fecha: str) -> str:
    """Convierte fecha de formato dd/mm/yyyy a yyyy-mm-dd.

    El portal del Senado usa formato dd/mm/yyyy pero la BD espera ISO.

    Args:
        fecha: Fecha en formato dd/mm/yyyy (ej: "31/03/2026").

    Returns:
        Fecha en formato yyyy-mm-dd (ej: "2026-03-31").
        Retorna cadena vacía si el formato no es reconocido.
    """
    if not fecha:
        return ""

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            dt = datetime.datetime.strptime(fecha, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning(f"Formato de fecha no reconocido: '{fecha}', usando cadena vacía")
    return ""


def voto_to_option(voto: str) -> str:
    """Convierte el sentido del voto del portal al formato de la BD.

    PRO → a_favor
    CONTRA → en_contra
    ABSTENCIÓN (o variantes) → abstencion
    AUSENTE → ausente

    Args:
        voto: Sentido del voto del portal (PRO, CONTRA, ABSTENCIÓN, AUSENTE).

    Returns:
        Opción en formato BD (a_favor, en_contra, abstencion, ausente).
    """
    s = voto.strip().upper()

    # Normalizar acentos para comparación
    nfkd = unicodedata.normalize("NFKD", s)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))

    if "PRO" in sin_acentos and "ABSTEN" not in sin_acentos:
        return "a_favor"
    if "CONTRA" in sin_acentos:
        return "en_contra"
    if "ABSTENCION" in sin_acentos or "ABSTEN" in sin_acentos:
        return "abstencion"
    if "AUSENTE" in sin_acentos:
        return "ausente"

    logger.warning(f"Sentido de voto no reconocido: '{voto}', usando 'abstencion'")
    return "abstencion"


# =============================================================================
# Matching de personas
# =============================================================================


def match_persona_por_nombre(nombre: str, conn: sqlite3.Connection) -> str | None:
    """Busca una persona existente por nombre normalizado.

    Retorna el ID (P01, P02, etc.) si encuentra match, None si no.
    Busca en la tabla person de congreso.db.

    Args:
        nombre: Nombre del senador a buscar.
        conn: Conexión activa a SQLite.

    Returns:
        ID de la persona si hay match, None si no se encuentra.
    """
    nombre_norm = normalize_name(nombre)

    rows = conn.execute("SELECT id, nombre FROM person").fetchall()
    for person_id, person_nombre in rows:
        if normalize_name(person_nombre) == nombre_norm:
            return person_id

    return None


# =============================================================================
# Inferencia de género
# =============================================================================


# Nombres femeninos comunes en México
_NOMBRES_FEMENINOS = frozenset(
    {
        "maría",
        "ana",
        "patricia",
        "leticia",
        "verónica",
        "gabriela",
        "cristina",
        "mónica",
        "silvia",
        "luz",
        "rosa",
        "carmen",
        "margarita",
        "elena",
        "sara",
        "laura",
        "andrea",
        "valentina",
        "sofia",
        "diana",
        "cecilia",
        "beatriz",
        "isabel",
        "raquel",
        "susana",
        "minerva",
        "nora",
        "claudia",
        "guadalupe",
        "alejandra",
        "nayeli",
        "antonia",
        "mariana",
        "irene",
        "adela",
        "ramona",
    }
)


def inferir_genero(nombre: str) -> str | None:
    """Infiere el género de un legislador a partir del nombre.

    Args:
        nombre: Nombre completo del legislador.

    Returns:
        "M", "F" o None.
    """
    if not nombre:
        return None

    # Strip prefijo "Sen. " si existe
    nombre_limpio = nombre.replace("Sen.", "").replace("sen.", "").strip()
    nombre_lower = nombre_limpio.lower()

    partes = nombre_lower.replace(",", "").split()
    for parte in partes:
        if parte in _NOMBRES_FEMENINOS:
            return "F"

    return None
