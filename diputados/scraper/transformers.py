"""
transformers.py — Transforma datos parseados del SITL a formato Popolo-Graph.

Convierte los modelos Pydantic (output de parsers) en dataclasses Popolo
listas para insertar en SQLite vía el Loader.

Proceso principal:
    VotacionRecord + DesgloseVotacion + list[NominalVotacion]
        → transformar_votacion() → VotacionCompleta
            → Loader.upsert_votacion() → SQLite
"""

import json
import logging
import re
import sqlite3

# ID generator compartido entre cámaras
import sys
from dataclasses import dataclass
from pathlib import Path

from utils.text_utils import MESES_ES, normalize_name

from .config import CAMARA_DIPUTADOS_ID
from .legislatura import url_estadistico
from .models import (
    DesgloseVotacion,
    NominalVotacion,
    VotacionRecord,
)

_db_module_path = str(Path(__file__).resolve().parent.parent.parent / "db")
if _db_module_path not in sys.path:
    sys.path.insert(0, _db_module_path)
from id_generator import get_next_id_batch, next_id

from db.helpers import get_or_create_organization

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
    source_id: str = ""  # ID original para deduplicación (SITL ID)
    legislatura: str = "LXVI"  # Legislatura a la que pertenece
    # Datos de motion (se insertan/actualizan junto con el vote_event)
    motion_text: str = ""
    motion_clasificacion: str = "otra"
    motion_requirement: str = "mayoria_simple"
    motion_result: str | None = None
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
    group: str | None  # "O01", "O04", etc.


@dataclass
class CountPopolo:
    """Datos de un count listo para insertar."""

    id: str  # C13, C14, etc.
    vote_event_id: str
    option: str
    value: int
    group_id: str | None  # "O01", etc.


@dataclass
class PersonPopolo:
    """Datos de una person lista para insertar (nueva)."""

    id: str  # P28, P29, etc.
    nombre: str
    identifiers_json: str  # {"sitl_id": 108}
    start_date: str = ""
    end_date: str = ""
    fecha_nacimiento: str | None = None
    genero: str | None = None
    curul_tipo: str | None = None


@dataclass
class MembershipPopolo:
    """Datos de una membership lista para insertar (nueva)."""

    id: str  # M64, M65, etc.
    person_id: str
    org_id: str  # ID del partido
    rol: str = "diputado"
    label: str = ""
    start_date: str = ""
    end_date: str | None = None
    on_behalf_of: str | None = None


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


def match_persona_por_nombre(nombre: str, conn: sqlite3.Connection) -> str | None:
    """Busca una persona existente por nombre normalizado.

    Retorna el ID (P01, P02, etc.) si encuentra match, None si no.
    Busca en la tabla person de congreso.db.

    Args:
        nombre: Nombre del diputado a buscar.
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


def siguiente_person_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para person (P00001, etc.).

    Usa el generador centralizado de IDs (db/id_generator.py).
    Person es global (sin prefijo de cámara).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "P00099").
    """
    return next_id(conn, "person")


def siguiente_vote_event_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para vote_event (VE_D00001, etc.).

    Usa el generador centralizado con prefijo VE_D (Diputados).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "VE_D00001").
    """
    return next_id(conn, "vote_event", camara="D")


def siguiente_vote_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para vote (V_D00001, etc.).

    Usa el generador centralizado con prefijo V_D (Diputados).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "V_D00001").
    """
    return next_id(conn, "vote", camara="D")


def siguiente_count_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para count (C00001, etc.).

    Usa el generador centralizado. Count es global.

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "C00001").
    """
    return next_id(conn, "count")


def siguiente_motion_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para motion (Y_D00001, etc.).

    Usa el generador centralizado con prefijo Y_D (Diputados).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "Y_D00001").
    """
    return next_id(conn, "motion", camara="D")


def siguiente_membership_id(conn: sqlite3.Connection) -> str:
    """Genera el siguiente ID disponible para membership (M_D00001, etc.).

    Usa el generador centralizado con prefijo M_D (Diputados).

    Args:
        conn: Conexión activa a SQLite.

    Returns:
        Siguiente ID disponible como string (ej: "M_D00001").
    """
    return next_id(conn, "membership", camara="D")


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
        mes_norm = normalize_name(mes_nombre)
        mes_num = MESES_ES.get(mes_norm)
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
    s = normalize_name(s)  # quitar acentos

    if "favor" in s:
        return "a_favor"
    elif "contra" in s:
        return "en_contra"
    elif "ausente" in s:
        return "ausente"
    elif "abstenc" in s or "abstencion" in s or "asistencia" in s or "solo" in s:
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
    # Alias: el SITL LXVI usa "IND" en URLs pero "INDEPENDIENTE" en el
    # HTML del desglose. Sin esta entrada, get_or_create_organization()
    # crearía una org duplicada.
    "INDEPENDIENTE": "IND",
}


def _partido_to_org_id(partido_nombre: str, conn: sqlite3.Connection) -> str | None:
    """Convierte nombre de partido a ID de organización via BD lookup/create.

    Soporta tanto nombres cortos ("MORENA", "PAN") como nombres completos
    del SITL ("Movimiento Regeneración Nacional", "Partido Acción Nacional").

    Usa get_or_create_organization() para crear la org dinámicamente
    si no existe. Los partidos ya no están hardcodeados en init_db.

    Args:
        partido_nombre: Nombre del partido (corto o completo).
        conn: Conexión activa a SQLite.

    Returns:
        ID de organización (ej: "O01") o None si no se puede resolver.
        NOTE: La conexión debe ser commiteada después para persistir
        las orgs creadas.
    """
    nombre_up = partido_nombre.upper().strip()
    nombre_norm = normalize_name(nombre_up)

    # Normalize to standard abbreviation using _PARTY_FULL_NAMES
    short_name = nombre_up  # default: use input as-is

    # Match against known full names
    for full_name, sn in _PARTY_FULL_NAMES.items():
        if normalize_name(full_name) == nombre_norm:
            short_name = sn
            break

    # Partial match (fallback): substring
    if short_name == nombre_up:
        for full_name, sn in _PARTY_FULL_NAMES.items():
            if normalize_name(full_name) in nombre_norm:
                short_name = sn
                break

    # Get or create org in DB (creates if doesn't exist)
    return get_or_create_organization(short_name, conn)


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
        source_id=str(votacion.sitl_id),
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

    # Generar batches de IDs para eficiencia (pre-allocar)
    # Contamos cuántos necesitaremos y generamos en batch
    total_nominales = sum(len(n.votos) for n in nominales)
    vote_ids = get_next_id_batch(conn, "vote", camara="D", count=total_nominales)
    _vote_id_idx = 0

    # Pre-allocar IDs para persons y memberships.
    # IMPORTANTE: No podemos usar siguiente_person_id() en el loop porque
    # consulta MAX(id) en la BD y las personas aún no están insertadas.
    # Todas las llamadas retornarían el mismo ID (ej: P00001).
    # Pre-allocamos el máximo posible (total_nominales) y usamos un índice.
    _person_id_pool = get_next_id_batch(conn, "person", count=total_nominales)
    _person_id_idx = 0
    _membership_id_pool = get_next_id_batch(conn, "membership", camara="D", count=total_nominales)
    _membership_id_idx = 0

    # Cache de nombres ya procesados en esta votación (evitar duplicar persona)
    _personas_creadas: dict[str, str] = {}  # nombre_norm → person_id

    for nominal in nominales:
        partido_nombre = nominal.partido_nombre
        org_id = _partido_to_org_id(partido_nombre, conn)

        for voto in nominal.votos:
            nombre_norm = normalize_name(voto.nombre)

            # Buscar persona existente (BD + ya creada en esta sesión)
            person_id = _personas_creadas.get(nombre_norm)

            if person_id is None:
                person_id = match_persona_por_nombre(voto.nombre, conn)

            if person_id is None:
                # Crear nueva persona (usar pool pre-allocado)
                person_id = _person_id_pool[_person_id_idx]
                _person_id_idx += 1

                identifiers = {}
                if voto.diputado_sitl_id:
                    identifiers["sitl_id"] = voto.diputado_sitl_id

                new_persons.append(
                    PersonPopolo(
                        id=person_id,
                        nombre=voto.nombre,
                        identifiers_json=json.dumps(identifiers) if identifiers else "{}",
                        start_date="",
                        end_date="",
                    )
                )

                # Crear membership al partido (usar pool pre-allocado)
                if org_id:
                    new_memberships.append(
                        MembershipPopolo(
                            id=_membership_id_pool[_membership_id_idx],
                            person_id=person_id,
                            org_id=org_id,
                            rol="diputado",
                            label=f"Diputado {partido_nombre}",
                            start_date="",
                            end_date=None,
                        )
                    )
                    _membership_id_idx += 1

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
                        m.person_id == person_id and m.org_id == org_id for m in new_memberships
                    )
                    if not existing_membership and not already_added:
                        new_memberships.append(
                            MembershipPopolo(
                                id=_membership_id_pool[_membership_id_idx],
                                person_id=person_id,
                                org_id=org_id,
                                rol="diputado",
                                label=f"Diputado {partido_nombre}",
                                start_date="",
                                end_date=None,
                            )
                        )
                        _membership_id_idx += 1
                        logger.debug(
                            f"Nueva membership {partido_nombre} para {person_id} "
                            f"(votó con partido diferente al de su membership original)"
                        )

            # Crear voto individual (usar batch ID)
            option = sentido_to_option(voto.sentido)

            votes.append(
                VotePopolo(
                    id=vote_ids[_vote_id_idx],
                    vote_event_id=ve_id,
                    voter_id=person_id,
                    option=option,
                    group=org_id,
                )
            )
            _vote_id_idx += 1

    # --- 4. Counts a partir del desglose ---
    counts: list[CountPopolo] = []

    opciones = ["a_favor", "en_contra", "abstencion", "ausente"]

    # Contar cuántos counts necesitaremos para generar batch
    count_needed = 0
    for partido in desglose.partidos:
        valores = {
            "a_favor": partido.a_favor,
            "en_contra": partido.en_contra,
            "abstencion": partido.abstencion,
            "ausente": partido.ausente + partido.solo_asistencia,
        }
        for opcion in opciones:
            if valores[opcion] > 0:
                count_needed += 1
    valores_totales = {
        "a_favor": desglose.totales.a_favor,
        "en_contra": desglose.totales.en_contra,
        "abstencion": desglose.totales.abstencion,
        "ausente": desglose.totales.ausente + desglose.totales.solo_asistencia,
    }
    for opcion in opciones:
        if valores_totales[opcion] > 0:
            count_needed += 1

    count_ids = get_next_id_batch(conn, "count", count=count_needed) if count_needed > 0 else []
    _count_id_idx = 0

    for partido in desglose.partidos:
        org_id = _partido_to_org_id(partido.partido_nombre, conn)
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
                counts.append(
                    CountPopolo(
                        id=count_ids[_count_id_idx],
                        vote_event_id=ve_id,
                        option=opcion,
                        value=val,
                        group_id=org_id if org_id else "O11",
                    )
                )
                _count_id_idx += 1

    # También agregar totales globales
    for opcion in opciones:
        val = valores_totales[opcion]
        if val > 0:
            counts.append(
                CountPopolo(
                    id=count_ids[_count_id_idx],
                    vote_event_id=ve_id,
                    option=opcion,
                    value=val,
                    group_id=None,  # Total global sin grupo
                )
            )
            _count_id_idx += 1

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
