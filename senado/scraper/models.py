"""
models.py — Modelos dataclass para datos parseados del portal del Senado.

Cada modelo representa una entidad extraída del HTML o JSON del
portal senado.gob.mx. Todos usan dataclass para mantener consistencia
con los parsers.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SenVotoNominal:
    """Voto individual de un senador en una votación nominal.

    Datos tal como aparecen en la tabla AJAX del portal:
    número de lista, nombre completo, grupo parlamentario y
    sentido del voto.
    """

    numero: int
    nombre: str
    grupo_parlamentario: str
    voto: str


@dataclass
class SenVotacionDetail:
    """Detalle de una votación del Senado (sin votos nominales)."""

    fecha: str
    año_ejercicio: int
    periodo: str
    descripcion: str
    pro_count: int
    contra_count: int
    abstention_count: int


@dataclass
class SenVotacionRaw:
    """Metadatos completos de una votación individual.

    Incluye conteos de votos, periodo legislativo y lista de votos nominales.
    """

    senado_id: int
    fecha: str
    año_ejercicio: int
    periodo: str
    descripcion: str
    pro_count: int
    contra_count: int
    abstention_count: int
    votos: list[SenVotoNominal]


@dataclass
class SenFechaIndexRecord:
    """Registro de una fecha en el índice de votaciones del Senado.

    El índice principal (/66/votaciones/) lista fechas con enlaces
    a páginas individuales: /66/votaciones/YYYY_MM_DD
    """

    fecha_url: str  # Path relativo, ej: "/66/votaciones/2024_09_03"
    fecha_label: str  # Label completo, ej: "Martes 03 de septiembre de 2024"


@dataclass
class SenVotacionIndexRecord:
    """Registro de una votación del listado por fecha.

    Datos mínimos del listado general de votaciones:
    ID del portal, título y fecha de la sesión.
    """

    senado_id: int
    titulo: str
    fecha: str
    fecha_label: Optional[str] = None  # Label de la fecha, si está disponible


@dataclass
class Senador:
    """Información de un senador.

    Puede no estar registrado en el portal (senado_id es Optional).
    """

    senado_id: Optional[int]
    nombre: str
    partido: str
    estado: Optional[str]


@dataclass
class GrupoParlamentario:
    """Grupo parlamentario (partido, coalición, etc.)."""

    abbr: str
    nombre_completo: str
    tipo: str  # 'partido', 'coalicion', etc.


@dataclass
class SenadoVotacionRecord:
    """Registro completo de una votación para la BD.

    Contiene todos los campos que ``loader.py`` necesita para insertar
    en la tabla ``senado_votacion``.
    """

    id: int
    titulo: str
    descripcion: str
    fecha: str
    fecha_iso: str
    periodo: str
    anio_ejercicio: str
    total_pro: int
    total_contra: int
    total_abstencion: int
    total_votos: int
    fuente_url: str
    legislature: str = "LXVI"  # Legislature (LXVI default, legacy usa LX-LXV)


@dataclass
class SenadoVotoRecord:
    """Voto individual de un senador para la BD.

    Campos que ``loader.py`` y ``transformers.py`` usan directamente.
    """

    nombre: str
    grupo_parlamentario: str
    voto: str
