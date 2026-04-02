"""transformers.py — Transforma datos parseados del Senado para la BD.

Convierte los modelos dataclass (output de parsers) en datos listos
para insertar en SQLite vía el SenadoLoader.

Proceso principal:
    SenVotacionIndexRecord + SenVotacionDetail + list[SenVotoNominal]
        → transformar_votacion() → SenadoVotacionCompleta
            → SenadoLoader.upsert_votacion() → SQLite
"""

import re
import unicodedata
import logging
from typing import Optional
from dataclasses import dataclass, field

from .models import (
    SenVotacionIndexRecord,
    SenVotacionDetail,
    SenVotacionRaw,
    SenVotoNominal,
    SenadoVotacionRecord,
    SenadoVotoRecord,
)
from .config import PARTY_NAMES, SENADO_VOTACION_URL_TEMPLATE
from scraper.utils.text_utils import normalize_name

logger = logging.getLogger(__name__)


# ============================================================
# Dataclass resultado — Estructura intermedia transformer→loader
# ============================================================


@dataclass
class SenadoVotacionCompleta:
    """Resultado completo de procesar una votación.

    Contiene la votación lista para la BD, los votos individuales y las
    entidades nuevas (senadores y membresías) que deben insertarse.
    """

    votacion: SenadoVotacionRecord
    votos: list[SenadoVotoRecord]
    senadores_nuevos: list[dict] = field(default_factory=list)
    membresias_nuevas: list[dict] = field(default_factory=list)


# ============================================================
# Funciones auxiliares
# ============================================================


def normalizar_nombre(nombre: str) -> str:
    """Normaliza un nombre de senador para comparación y almacenamiento.

    Strip del prefijo "Sen. ", normaliza acentos (NFKD), convierte a
    lowercase y colapsa espacios.

    Ej: "Sen. Álvarez Lima, José Antonio Cruz" → "alvarez lima, jose antonio cruz"

    Args:
        nombre: Nombre del legislador tal como aparece en el portal.

    Returns:
        Nombre normalizado listo para comparación y almacenamiento.
    """
    # Strip prefijo "Sen. " o "Sen. "
    nombre = re.sub(r"^Sen\.?\s*", "", nombre, flags=re.IGNORECASE).strip()
    # Usar función compartida para normalización
    return normalize_name(nombre)


def match_persona_por_nombre(nombre_norm: str, conn) -> Optional[int]:
    """Busca una persona existente por nombre normalizado.

    Busca en la tabla ``sen_person`` de la BD del Senado.

    Args:
        nombre_norm: Nombre normalizado del legislador.
        conn: Conexión activa a SQLite.

    Returns:
        ID de la persona si hay match, ``None`` si no se encuentra.
    """
    # Buscar por nombre exacto (el loader normaliza antes de insertar)
    row = conn.execute(
        "SELECT id FROM sen_person WHERE nombre = ?",
        (nombre_norm,),
    ).fetchone()
    return row[0] if row else None


def _inferir_genero(nombre: str) -> Optional[str]:
    """Infiere el género de un senador a partir del nombre.

    Heurísticas:
    - Si el nombre contiene indicador femenino → "F"
    - Si no contiene indicador → "M" (por defecto masculino en Senado)
    - Si no se puede determinar → ``None``

    Args:
        nombre: Nombre completo del senador (sin prefijo "Sen. ").

    Returns:
        "M", "F" o ``None``.
    """
    if not nombre:
        return None

    # El prefijo "Sen. " (sin "a") indica masculino en el portal
    # Pero después de strip, revisamos el nombre original
    nombre_lower = nombre.lower()

    # Nombres femeninos comunes en México
    nombres_femeninos = {
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
        "sophie",
        "clelia",
        "guadalupe",
        "alejandra",
        "nayeli",
        "antonia",
        "mariana",
        "irene",
        "adela",
        "ramona",
    }

    # Verificar si el nombre de pila es femenino
    partes = nombre_lower.replace(",", "").split()
    for parte in partes:
        if parte in nombres_femeninos:
            return "F"

    # Si no se puede determinar, no asumir
    return None


def voto_to_option(voto: str) -> str:
    """Convierte el sentido del voto del portal al formato de la BD.

    "PRO" → "a_favor"
    "CONTRA" → "en_contra"
    "ABSTENCIÓN" (o variantes con acentos/entities) → "abstencion"

    Args:
        voto: Sentido del voto del portal (PRO, CONTRA, ABSTENCIÓN).

    Returns:
        Opción en formato BD (a_favor, en_contra, abstencion).
    """
    s = voto.strip().upper()

    # Normalizar acentos para comparación
    nfkd = unicodedata.normalize("NFKD", s)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))

    if "PRO" in sin_acentos and "ABSTEN" not in sin_acentos:
        # Evitar false positive: "PRO" dentro de "ABSTENCIÓN"
        # PRO standalone
        if sin_acentos == "PRO":
            return "a_favor"
        # "EN PRO" u otra variante
        if sin_acentos.startswith("PRO") or sin_acentos.endswith("PRO"):
            return "a_favor"
    if "CONTRA" in sin_acentos:
        return "en_contra"
    if "ABSTENCION" in sin_acentos or "ABSTEN" in sin_acentos:
        return "abstencion"

    # Fallback: si contiene "pro" literalmente y no es abstención
    if "PRO" in s and "ABSTEN" not in s:
        return "a_favor"

    logger.warning(f"Sentido de voto no reconocido: '{voto}', usando 'abstencion'")
    return "abstencion"


def _parse_fecha_iso(fecha: str) -> str:
    """Convierte fecha de formato dd/mm/yyyy a yyyy-mm-dd.

    El portal del Senado usa formato dd/mm/yyyy pero la BD espera ISO.

    Args:
        fecha: Fecha en formato dd/mm/yyyy (ej: "31/03/2026").

    Returns:
        Fecha en formato yyyy-mm-dd (ej: "2026-03-31").
        Retorna cadena vacía si el formato no es reconocido.
    """
    import datetime

    if not fecha:
        return ""

    # Intentar varios formatos comunes
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            dt = datetime.datetime.strptime(fecha, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning(f"Formato de fecha no reconocido: '{fecha}', usando cadena vacía")
    return ""


# ============================================================
# Función principal de transformación
# ============================================================


def transformar_votacion(
    vot_index: SenVotacionIndexRecord,
    vot_detail: SenVotacionDetail,
    votos: list[SenVotoNominal],
    conn,
) -> SenadoVotacionCompleta:
    """Transforma datos parseados de una votación completa.

    Construye un ``SenadoVotacionRecord`` con todos los campos necesarios
    para la BD a partir de:
    - SenVotacionIndexRecord (senado_id, titulo, fecha)
    - SenVotacionDetail (fecha, año_ejercicio, periodo, descripcion, conteos)
    - list[SenVotoNominal] (votos individuales)

    Proceso:
    1. Verificar que la votación no exista ya (SELECT por id)
    2. Construir SenadoVotacionRecord con todos los campos BD
    3. Convertir SenVotoNominal → SenadoVotoRecord
    4. Para cada voto:
       a. Normalizar nombre del senador
       b. Buscar persona existente por nombre_normalizado
       c. Si no existe → agregar a senadores_nuevos
       d. Registrar membresía al partido (si no existe ya)
    5. Retornar SenadoVotacionCompleta

    Args:
        vot_index: Registro del índice con senado_id, titulo y fecha.
        vot_detail: Detalle de la votación con periodo, descripción y conteos.
        votos: Lista de votos individuales del portal.
        conn: Conexión activa a SQLite (solo lectura para buscar IDs).

    Returns:
        :class:`SenadoVotacionCompleta` con todos los datos listos para insertar.

    Raises:
        ValueError: Si la votación ya existe en la BD.
    """
    votacion_id = vot_index.senado_id

    # --- 1. Verificar que no exista ya (idempotencia) ---
    existing = conn.execute(
        "SELECT id FROM sen_vote_event WHERE senado_id = ?",
        (votacion_id,),
    ).fetchone()
    if existing:
        raise ValueError(
            f"Votación {votacion_id} ya existe en la BD. "
            f"Saltando para evitar duplicados."
        )

    # --- 2. Construir SenadoVotacionRecord con todos los campos BD ---
    # fecha_iso: convertir fecha a ISO (dd/mm/yyyy → yyyy-mm-dd)
    fecha_iso = _parse_fecha_iso(vot_detail.fecha)

    # total_votos = suma de los conteos
    total_pro = vot_detail.pro_count
    total_contra = vot_detail.contra_count
    total_abstencion = vot_detail.abstention_count
    total_votos = total_pro + total_contra + total_abstencion

    # fuente_url: construir de template
    fuente_url = SENADO_VOTACION_URL_TEMPLATE.format(id=votacion_id)

    senado_votacion_record = SenadoVotacionRecord(
        id=votacion_id,
        titulo=vot_index.titulo,
        descripcion=vot_detail.descripcion,
        fecha=vot_detail.fecha,
        fecha_iso=fecha_iso,
        periodo=vot_detail.periodo,
        anio_ejercicio=str(vot_detail.año_ejercicio),
        total_pro=total_pro,
        total_contra=total_contra,
        total_abstencion=total_abstencion,
        total_votos=total_votos,
        fuente_url=fuente_url,
    )

    # --- 3. Convertir SenVotoNominal → SenadoVotoRecord ---
    votos_records = [
        SenadoVotoRecord(
            nombre=v.nombre,
            grupo_parlamentario=v.grupo_parlamentario,
            voto=voto_to_option(v.voto),
        )
        for v in votos
    ]

    # --- 4. Procesar votos y detectar senadores nuevos ---
    senadores_nuevos: list[dict] = []
    membresias_nuevas: list[dict] = []

    # Cache de nombres ya procesados en esta votación
    _senadores_creados: dict[str, int] = {}  # nombre_norm → persona_id

    # Cache de membresías ya registradas en esta votación
    _membresias_registradas: set[tuple[str, str]] = set()  # (nombre_norm, grupo)

    for voto in votos:
        nombre_norm = normalizar_nombre(voto.nombre)
        grupo = voto.grupo_parlamentario.strip()

        # Buscar persona existente (BD + ya creada en esta sesión)
        persona_id = _senadores_creados.get(nombre_norm)

        if persona_id is None:
            persona_id = match_persona_por_nombre(nombre_norm, conn)

        if persona_id is None:
            # Inferir género
            nombre_sin_prefix = re.sub(
                r"^Sen\.?\s*", "", voto.nombre, flags=re.IGNORECASE
            ).strip()
            genero = _inferir_genero(nombre_sin_prefix)

            # Crear nuevo senador
            senadores_nuevos.append(
                {
                    "nombre": voto.nombre,
                    "nombre_norm": nombre_norm,
                    "grupo": grupo,
                    "genero": genero,
                }
            )
            # Marcar como "por crear" — el loader asignará el ID
            _senadores_creados[nombre_norm] = -1  # placeholder
        else:
            _senadores_creados[nombre_norm] = persona_id

        # Registrar membresía al partido (si no existe)
        clave_membresia = (nombre_norm, grupo)
        if clave_membresia not in _membresias_registradas:
            # Verificar si la membresía ya existe en la BD (solo si persona_id es real)
            if persona_id is not None and persona_id > 0:
                existing_mem = conn.execute(
                    "SELECT id FROM sen_membership "
                    "WHERE person_id = ? AND org_id = ("
                    "  SELECT id FROM sen_organization WHERE abbr = ?"
                    ")",
                    (persona_id, grupo),
                ).fetchone()
                if not existing_mem:
                    membresias_nuevas.append(
                        {
                            "persona_id": persona_id,
                            "organizacion_id": grupo,  # El loader resolverá a ID
                            "rol": "senador",
                        }
                    )
            else:
                # Senador nuevo — siempre crear membresía
                membresias_nuevas.append(
                    {
                        "persona_id": nombre_norm,  # El loader resolverá a ID
                        "organizacion_id": grupo,
                        "rol": "senador",
                    }
                )
            _membresias_registradas.add(clave_membresia)

    logger.info(
        f"Votación {votacion_id}: {len(votos)} votos, "
        f"{len(senadores_nuevos)} senadores nuevos, "
        f"{len(membresias_nuevas)} membresías nuevas"
    )

    return SenadoVotacionCompleta(
        votacion=senado_votacion_record,
        votos=votos_records,
        senators_nuevos=senadores_nuevos,
        membresias_nuevas=membresias_nuevas,
    )
