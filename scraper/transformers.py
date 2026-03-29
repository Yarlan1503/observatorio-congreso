"""
transformers.py — Transforma datos parseados del SITL a formato Popolo-Graph.

Convierte los modelos Pydantic (output de parsers) en dataclasses Popolo
listas para insertar en SQLite vía el Loader.

Proceso principal:
    VotacionRecord + DesgloseVotacion + list[NominalVotacion]
        → transformar_votacion() → VotacionCompleta
            → Loader.upsert_votacion() → SQLite
"""

import sqlite3
import unicodedata
import re
import json
import logging
from typing import Optional
from dataclasses import dataclass, field

from scraper.models import (
    VotacionRecord,
    DesgloseVotacion,
    NominalVotacion,
    VotoNominal,
    DesglosePartido,
)
from scraper.config import PARTY_SITL_MAP, CAMARA_DIPUTADOS_ID
from scraper.legislatura import url_estadistico

logger = logging.getLogger(__name__)


# ============================================================
# Dataclasses Popolo — Estructura intermedia transformer→loader
# ============================================================


@dataclass
class VoteEventPopolo:
    """Datos de un vote_event listo para insertar."""

    id: str  # VE03, VE04, etc.
    motion_id: str  # Y03, Y04, etc.
    start_date: str  # ISO 8601
    organization_id: str  # O08
    result: str  # "aprobada", "rechazada", "empate"
    sitl_id: int
    voter_count: int
    legislatura: str = "LXVI"  # Legislatura a la que pertenece
    # Datos de motion (se insertan/actualizan junto con el vote_event)
    motion_text: str = ""
    motion_clasificacion: str = "otra"
    motion_requirement: str = "mayoria_simple"
    motion_result: Optional[str] = None
    motion_date: str = ""
    motion_legislative_session: str = ""
    motion_fuente_url: str = ""


@dataclass
class VotePopolo:
    """Datos de un vote individual listo para insertar."""

    id: str  # V25, V26, etc.
    vote_event_id: str
    voter_id: str  # P01, P28, etc.
    option: str  # "a_favor", "en_contra", "abstencion", "ausente"
    group: Optional[str]  # "O01", "O04", etc.


@dataclass
class CountPopolo:
    """Datos de un count listo para insertar."""

    id: str  # C13, C14, etc.
    vote_event_id: str
    option: str
    value: int
    group_id: Optional[str]  # "O01", etc.


@dataclass
class PersonPopolo:
    """Datos de una person lista para insertar (nueva)."""

    id: str  # P28, P29, etc.
    nombre: str
    identifiers_json: str  # {"sitl_id": 108}
    start_date: str = ""
    end_date: str = ""
    fecha_nacimiento: Optional[str] = None
    genero: Optional[str] = None
    curul_tipo: Optional[str] = None


@dataclass
class MembershipPopolo:
    """Datos de una membership lista para insertar (nueva)."""

    id: str  # M64, M65, etc.
    person_id: str
    org_id: str  # ID del partido
    rol: str = "diputado"
    label: str = ""
    start_date: str = ""
    end_date: Optional[str] = None
    on_behalf_of: Optional[str] = None


@dataclass
class VotacionCompleta:
    """Resultado completo de procesar una votación."""

    vote_event: VoteEventPopolo
    votes: list[VotePopolo]
    counts: list[CountPopolo]
    new_persons: list[PersonPopolo]
    new_memberships: list[MembershipPopolo]


# ============================================================
# Funciones auxiliares
# ============================================================


def normalizar_nombre(nombre: str) -> str:
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


def match_persona_por_nombre(nombre: str, conn: sqlite3.Connection) -> Optional[str]:
    """Busca una persona existente por nombre normalizado.

    Retorna el ID (P01, P02, etc.) si encuentra match, None si no.
    Busca en la tabla person de congreso.db.

    Args:
        nombre: Nombre del diputado a buscar.
        conn: Conexión activa a SQLite.

    Returns:
        ID de la persona si hay match, None si no se encuentra.
    """
    nombre_norm = normalizar_nombre(nombre)

    rows = conn.execute("SELECT id, nombre FROM person").fetchall()
    for person_id, person_nombre in rows:
        if normalizar_nombre(person_nombre) == nombre_norm:
            return person_id

    return None


def siguiente_person_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para person (P28, P29, etc.).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "P28").
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM person"
    ).fetchone()
    max_num = row[0] if row[0] is not None else 0
    return f"P{max_num + 1:02d}"


def siguiente_vote_event_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para vote_event (VE03, VE04, etc.).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "VE03").
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 3) AS INTEGER)) FROM vote_event"
    ).fetchone()
    max_num = row[0] if row[0] is not None else 0
    return f"VE{max_num + 1:02d}"


def siguiente_vote_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para vote (V25, V26, etc.).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "V25").
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM vote"
    ).fetchone()
    max_num = row[0] if row[0] is not None else 0
    return f"V{max_num + 1:02d}"


def siguiente_count_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para count (C13, C14, etc.).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "C13").
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM count"
    ).fetchone()
    max_num = row[0] if row[0] is not None else 0
    return f"C{max_num + 1:02d}"


def siguiente_motion_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para motion (Y03, Y04, etc.).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "Y03").
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM motion"
    ).fetchone()
    max_num = row[0] if row[0] is not None else 0
    return f"Y{max_num + 1:02d}"


def siguiente_membership_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para membership (M64, M65, etc.).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "M64").
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM membership"
    ).fetchone()
    max_num = row[0] if row[0] is not None else 0
    return f"M{max_num + 1:02d}"


# ============================================================
# Funciones de clasificación
# ============================================================


def determinar_resultado_votacion(
    desglose: DesgloseVotacion, requirement: str = "mayoria_simple"
) -> str:
    """Determina si una votación fue aprobada o rechazada según el tipo de mayoría.

    Modos de cálculo:
    - mayoria_simple: aprobada si a_favor > en_contra, empate si iguales,
      rechazada si a_favor < en_contra.
    - mayoria_calificada (Art. 135 CPEUM): aprobada si a_favor >= 2/3 de los
      presentes (presentes = a_favor + en_contra + abstenciones, sin ausentes).
      Rechazada en caso contrario.
    - unanime: se trata como mayoria_simple (no hay casos en DB aún).
    - Cualquier otro valor: fallback a mayoria_simple.

    Args:
        desglose: Desglose completo de la votación.
        requirement: Tipo de mayoría requerida ("mayoria_simple",
            "mayoria_calificada", "unanime"). Default "mayoria_simple".

    Returns:
        "aprobada", "rechazada" o "empate".
    """
    favor = desglose.totales.a_favor
    contra = desglose.totales.en_contra
    abstenciones = desglose.totales.abstencion

    if requirement == "mayoria_calificada":
        presentes = favor + contra + abstenciones
        if presentes == 0:
            return "rechazada"  # nadie presente → no puede aprobar
        umbral = (2 / 3) * presentes
        if favor >= umbral:
            return "aprobada"
        else:
            return "rechazada"
    else:
        # mayoria_simple, unanime, o fallback
        if favor > contra:
            return "aprobada"
        elif favor < contra:
            return "rechazada"
        else:
            return "empate"


def determinar_tipo_motion(titulo: str) -> str:
    """Infiere el tipo de motion del título.

    Clasificación:
    - 'reforma_constitucional' si contiene "CONSTITUCIÓN" o "CONSTITUCIONAL"
    - 'ley_secundaria' si contiene "LEY" pero no "CONSTITUCIÓN"
    - 'ordinaria' si contiene "PRESUPUESTO" o "DECRETO" con "INGRESOS/EGRESOS"
    - 'otra' en otro caso

    Args:
        titulo: Título de la votación/motion.

    Returns:
        Clasificación del tipo de motion.
    """
    titulo_up = titulo.upper()

    if "CONSTITUCI" in titulo_up or "CONSTITUCIONAL" in titulo_up:
        return "reforma_constitucional"

    if "LEY" in titulo_up:
        return "ley_secundaria"

    if "PRESUPUESTO" in titulo_up:
        return "ordinaria"

    if "DECRETO" in titulo_up and ("INGRESO" in titulo_up or "EGRESO" in titulo_up):
        return "ordinaria"

    return "otra"


def determinar_requirement(titulo: str) -> str:
    """Infiere el tipo de mayoría requerida del título.

    - 'mayoria_calificada' si contiene "CONSTITUCIÓN" (reformas const. necesitan 2/3)
    - 'mayoria_simple' en otro caso

    Args:
        titulo: Título de la votación/motion.

    Returns:
        Tipo de mayoría requerida.
    """
    titulo_up = titulo.upper()
    if "CONSTITUCI" in titulo_up or "CONSTITUCIONAL" in titulo_up:
        return "mayoria_calificada"
    return "mayoria_simple"


# ============================================================
# Conversión de formatos
# ============================================================

# Mapa de meses en español
_MESES_ES: dict[str, str] = {
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


def parsear_fecha_sitl(fecha_str: str) -> str:
    """Convierte fecha del SITL ("10 Diciembre 2024") a ISO 8601 ("2024-12-10").

    Meses en español: Enero, Febrero, Marzo, Abril, Mayo, Junio,
                      Julio, Agosto, Septiembre, Octubre, Noviembre, Diciembre

    Args:
        fecha_str: Fecha en formato SITL (ej: "10 Diciembre 2024").

    Returns:
        Fecha en formato ISO 8601 (ej: "2024-12-10"), o string vacío si no se puede parsear.
    """
    if not fecha_str or not fecha_str.strip():
        return ""

    # Normalizar espacios
    fecha_str = re.sub(r"\s+", " ", fecha_str.strip())

    # Intentar formato ISO directo primero (antes de normalizar guiones)
    match_iso = re.match(r"(\d{4}-\d{2}-\d{2})", fecha_str)
    if match_iso:
        return match_iso.group(1)

    # Normalizar guiones a espacios para formato "DD-Mes-AAAA"
    fecha_str = fecha_str.replace("-", " ")
    fecha_str = re.sub(r"\s+", " ", fecha_str.strip())

    # Patrón: "DD Mes AAAA"
    match = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", fecha_str)
    if match:
        dia = match.group(1).zfill(2)
        mes_nombre = match.group(2).lower().strip()
        anio = match.group(3)

        # Normalizar mes (sin acentos)
        mes_norm = normalizar_nombre(mes_nombre)
        mes_num = _MESES_ES.get(mes_norm)
        if mes_num:
            return f"{anio}-{mes_num}-{dia}"

    # Intentar formato DD/MM/YYYY (no tocar guiones — ya normalizados arriba)
    match_slash = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", fecha_str)
    if match_slash:
        dia = match_slash.group(1).zfill(2)
        mes = match_slash.group(2).zfill(2)
        anio = match_slash.group(3)
        return f"{anio}-{mes}-{dia}"

    logger.warning(f"No se pudo parsear fecha: '{fecha_str}'")
    return fecha_str


def sentido_to_option(sentido: str) -> str:
    """Convierte sentido del voto del SITL al formato Popolo.

    "A favor" → "a_favor"
    "En contra" → "en_contra"
    "Ausente" → "ausente"
    "Abstencion" / "Abstención" → "abstencion"
    "Solo asistencia" → "abstencion"  (asistencia sin voto tratada como abstención)

    Args:
        sentido: Sentido del voto en formato SITL.

    Returns:
        Opción en formato Popolo (a_favor, en_contra, abstencion, ausente).
    """
    s = sentido.strip().lower()
    s = normalizar_nombre(s)  # quitar acentos

    if "favor" in s:
        return "a_favor"
    elif "contra" in s:
        return "en_contra"
    elif "ausente" in s:
        return "ausente"
    elif "abstenc" in s or "abstencion" in s:
        return "abstencion"
    elif "asistencia" in s or "solo" in s:
        return "abstencion"
    else:
        logger.warning(f"Sentido de voto no reconocido: '{sentido}', usando 'ausente'")
        return "ausente"


# Mapa de nombres completos de partido → nombre corto para matching
# El SITL usa nombres completos en las páginas nominales:
#   "Movimiento Regeneración Nacional", "Partido Acción Nacional", etc.
_PARTY_FULL_NAMES: dict[str, str] = {
    "MORENA": "MORENA",
    "MOVIMIENTO REGENERACION NACIONAL": "MORENA",
    "PAN": "PAN",
    "PARTIDO ACCION NACIONAL": "PAN",
    "PVEM": "PVEM",
    "PARTIDO VERDE ECOLOGISTA DE MEXICO": "PVEM",
    "PARTIDO VERDE": "PVEM",
    "PT": "PT",
    "PARTIDO DEL TRABAJO": "PT",
    "PRI": "PRI",
    "PARTIDO REVOLUCIONARIO INSTITUCIONAL": "PRI",
    "MC": "MC",
    "MOVIMIENTO CIUDADANO": "MC",
    "PRD": "PRD",
    "PARTIDO DE LA REVOLUCION DEMOCRATICA": "PRD",
    # Partidos adicionales (LX-LXIV):
    "CONV": "CONV",
    "CONVERGENCIA": "CONV",
    "CONVERGENCIA POR LA DEMOCRACIA": "CONV",
    "NA": "NA",
    "NUEVA ALIANZA": "NA",
    "ALT": "ALT",
    "ALTERNATIVA": "ALT",
    "ALTERNATIVA SOCIALDEMOCRATA": "ALT",
    "PES": "PES",
    "PARTIDO ENCUENTRO SOCIAL": "PES",
    "SP": "SP",
    "SIN PARTIDO": "SP",
}


def _partido_to_org_id(partido_nombre: str) -> Optional[str]:
    """Convierte nombre de partido a ID de organización en la BD.

    Soporta tanto nombres cortos ("MORENA", "PAN") como nombres completos
    del SITL ("Movimiento Regeneración Nacional", "Partido Acción Nacional").

    Args:
        partido_nombre: Nombre del partido.

    Returns:
        ID de organización (ej: "O01") o None si no se encuentra.
    """
    nombre_up = partido_nombre.upper().strip()
    nombre_norm = normalizar_nombre(nombre_up)

    # Match directo contra nombres cortos
    if nombre_up in PARTY_SITL_MAP:
        return PARTY_SITL_MAP[nombre_up]

    # Match contra nombres completos normalizados
    for full_name, short_name in _PARTY_FULL_NAMES.items():
        if normalizar_nombre(full_name) == nombre_norm:
            return PARTY_SITL_MAP.get(short_name)

    # Match parcial (ej: "MORENA/PT" o "PT-MORENA")
    for key, org_id in PARTY_SITL_MAP.items():
        if key in nombre_up:
            return org_id

    # Buscar por substring normalizado
    for full_name, short_name in _PARTY_FULL_NAMES.items():
        if normalizar_nombre(full_name) in nombre_norm:
            return PARTY_SITL_MAP.get(short_name)

    return None


# ============================================================
# Función principal de transformación
# ============================================================


def transformar_votacion(
    votacion: VotacionRecord,
    desglose: DesgloseVotacion,
    nominales: list[NominalVotacion],
    conn: sqlite3.Connection,
    legislatura: str = "LXVI",
) -> VotacionCompleta:
    """Transforma datos parseados de una votación completa a formato Popolo.

    Proceso:
    1. Crear o reutilizar motion
    2. Crear vote_event
    3. Para cada voto nominal:
       a. Buscar person existente por nombre normalizado
       b. Si no existe → crear nueva person + membership
       c. Crear vote individual
    4. Crear counts a partir del desglose
    5. Retornar VotacionCompleta con todos los datos listos para insertar

    Deduplicación: Match por nombre normalizado + partido.
    Si no hay match → nueva persona con siguiente ID.

    Args:
        votacion: Registro de la votación del listado.
        desglose: Desglose por partido de la votación.
        nominales: Lista de votos nominales por partido.
        conn: Conexión activa a SQLite (solo lectura para buscar IDs).
        legislatura: Clave de legislatura (ej: "LXVI").

    Returns:
        VotacionCompleta con todos los datos listos para insertar.

    Raises:
        ValueError: Si ya existe un vote_event con este sitl_id en la BD.
    """
    # --- 0b. Verificar que no exista ya (idempotencia por legislatura) ---
    existing = conn.execute(
        "SELECT id FROM vote_event WHERE sitl_id = ? AND legislatura = ?",
        (votacion.sitl_id, legislatura),
    ).fetchone()
    if existing:
        raise ValueError(
            f"Votación SITL {votacion.sitl_id} de {legislatura} ya existe como {existing[0]}. "
            f"Saltando para evitar duplicados."
        )

    # --- 0. Datos base ---
    titulo = votacion.titulo or desglose.titulo or f"Votación SITL {votacion.sitl_id}"
    fecha_raw = votacion.fecha or desglose.fecha or ""
    fecha_iso = parsear_fecha_sitl(fecha_raw)
    clasificacion = determinar_tipo_motion(titulo)
    requirement = determinar_requirement(titulo)
    resultado = determinar_resultado_votacion(desglose, requirement)

    # --- 1. Motion ---
    motion_id = siguiente_motion_id(conn)
    fuente_url = url_estadistico(legislatura, votacion.sitl_id)

    # --- 2. Vote Event ---
    ve_id = siguiente_vote_event_id(conn)

    # Calcular voter_count: total de votos nominales o el total del desglose
    voter_count = desglose.totales.total

    vote_event = VoteEventPopolo(
        id=ve_id,
        motion_id=motion_id,
        start_date=fecha_iso,
        organization_id=CAMARA_DIPUTADOS_ID,
        result=resultado,
        sitl_id=votacion.sitl_id,
        voter_count=voter_count,
        legislatura=legislatura,
        motion_text=titulo,
        motion_clasificacion=clasificacion,
        motion_requirement=requirement,
        motion_result=resultado,
        motion_date=fecha_iso,
        motion_legislative_session=f"{legislatura} Legislatura",
        motion_fuente_url=fuente_url,
    )

    # --- 3. Votos nominales + personas nuevas ---
    votes: list[VotePopolo] = []
    new_persons: list[PersonPopolo] = []
    new_memberships: list[MembershipPopolo] = []

    # Track de IDs ya generados en esta ejecución para no duplicar
    # Usamos números enteros y formateamos con zero-padding al generar IDs
    _next_vote_num = _get_max_vote_num(conn)
    _next_person_num = _get_max_person_num(conn)
    _next_membership_num = _get_max_membership_num(conn)
    _next_count_num = _get_max_count_num(conn)

    # Cache de nombres ya procesados en esta votación (evitar duplicar persona)
    _personas_creadas: dict[str, str] = {}  # nombre_norm → person_id

    for nominal in nominales:
        partido_nombre = nominal.partido_nombre
        org_id = _partido_to_org_id(partido_nombre)

        for voto in nominal.votos:
            nombre_norm = normalizar_nombre(voto.nombre)

            # Buscar persona existente (BD + ya creada en esta sesión)
            person_id = _personas_creadas.get(nombre_norm)

            if person_id is None:
                person_id = match_persona_por_nombre(voto.nombre, conn)

            if person_id is None:
                # Crear nueva persona
                _next_person_num += 1
                person_id = f"P{_next_person_num:02d}"

                identifiers = {}
                if voto.diputado_sitl_id:
                    identifiers["sitl_id"] = voto.diputado_sitl_id

                new_persons.append(
                    PersonPopolo(
                        id=person_id,
                        nombre=voto.nombre,
                        identifiers_json=json.dumps(identifiers)
                        if identifiers
                        else "{}",
                        start_date="",
                        end_date="",
                    )
                )

                # Crear membership al partido
                if org_id:
                    _next_membership_num += 1
                    new_memberships.append(
                        MembershipPopolo(
                            id=f"M{_next_membership_num:02d}",
                            person_id=person_id,
                            org_id=org_id,
                            rol="diputado",
                            label=f"Diputado {partido_nombre}",
                            start_date="",
                            end_date=None,
                        )
                    )

                _personas_creadas[nombre_norm] = person_id
            else:
                _personas_creadas[nombre_norm] = person_id

                # Verificar si la persona ya tiene membership al partido actual
                # Si vota con un partido diferente al de su membership existente,
                # crear membership adicional (puede cambiar de bancada)
                if org_id:
                    existing_membership = conn.execute(
                        "SELECT id FROM membership WHERE person_id = ? AND org_id = ?",
                        (person_id, org_id),
                    ).fetchone()
                    # También verificar memberships ya creadas en esta sesión
                    already_added = any(
                        m.person_id == person_id and m.org_id == org_id
                        for m in new_memberships
                    )
                    if not existing_membership and not already_added:
                        _next_membership_num += 1
                        new_memberships.append(
                            MembershipPopolo(
                                id=f"M{_next_membership_num:02d}",
                                person_id=person_id,
                                org_id=org_id,
                                rol="diputado",
                                label=f"Diputado {partido_nombre}",
                                start_date="",
                                end_date=None,
                            )
                        )
                        logger.debug(
                            f"Nueva membership {partido_nombre} para {person_id} "
                            f"(votó con partido diferente al de su membership original)"
                        )

            # Crear voto individual
            _next_vote_num += 1
            option = sentido_to_option(voto.sentido)

            votes.append(
                VotePopolo(
                    id=f"V{_next_vote_num:02d}",
                    vote_event_id=ve_id,
                    voter_id=person_id,
                    option=option,
                    group=org_id,
                )
            )

    # --- 4. Counts a partir del desglose ---
    counts: list[CountPopolo] = []

    opciones = ["a_favor", "en_contra", "abstencion", "ausente"]

    for partido in desglose.partidos:
        org_id = _partido_to_org_id(partido.partido_nombre)
        # Usar el org_id directamente (IND → O11, otros → O01-O07, None no debería ocurrir)

        valores = {
            "a_favor": partido.a_favor,
            "en_contra": partido.en_contra,
            "abstencion": partido.abstencion,
            "ausente": partido.ausente + partido.solo_asistencia,
        }

        for opcion in opciones:
            val = valores[opcion]
            if val > 0:
                _next_count_num += 1
                counts.append(
                    CountPopolo(
                        id=f"C{_next_count_num:02d}",
                        vote_event_id=ve_id,
                        option=opcion,
                        value=val,
                        group_id=org_id if org_id else "O11",
                    )
                )

    # También agregar totales globales
    valores_totales = {
        "a_favor": desglose.totales.a_favor,
        "en_contra": desglose.totales.en_contra,
        "abstencion": desglose.totales.abstencion,
        "ausente": desglose.totales.ausente + desglose.totales.solo_asistencia,
    }
    for opcion in opciones:
        val = valores_totales[opcion]
        if val > 0:
            _next_count_num += 1
            counts.append(
                CountPopolo(
                    id=f"C{_next_count_num:02d}",
                    vote_event_id=ve_id,
                    option=opcion,
                    value=val,
                    group_id=None,  # Total global sin grupo
                )
            )

    logger.info(
        f"Votación {votacion.sitl_id}: {len(votes)} votos, "
        f"{len(new_persons)} personas nuevas, {len(counts)} counts"
    )

    return VotacionCompleta(
        vote_event=vote_event,
        votes=votes,
        counts=counts,
        new_persons=new_persons,
        new_memberships=new_memberships,
    )


# ============================================================
# Helpers internos para cálculo de IDs
# ============================================================


def _get_max_vote_num(conn: sqlite3.Connection) -> int:
    """Obtiene el máximo número de vote ID en la BD."""
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM vote"
    ).fetchone()
    return row[0] if row[0] is not None else 0


def _get_max_person_num(conn: sqlite3.Connection) -> int:
    """Obtiene el máximo número de person ID en la BD."""
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM person"
    ).fetchone()
    return row[0] if row[0] is not None else 0


def _get_max_membership_num(conn: sqlite3.Connection) -> int:
    """Obtiene el máximo número de membership ID en la BD."""
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM membership"
    ).fetchone()
    return row[0] if row[0] is not None else 0


def _get_max_count_num(conn: sqlite3.Connection) -> int:
    """Obtiene el máximo número de count ID en la BD."""
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM count"
    ).fetchone()
    return row[0] if row[0] is not None else 0
