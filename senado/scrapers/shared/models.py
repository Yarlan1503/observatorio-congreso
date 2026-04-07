"""
models.py — Modelos dataclass para datos parseados del portal del Senado.

Portal legacy (LX-LXV): https://www.senado.gob.mx/informacion/votaciones/vota/{id}

Cada modelo representa una entidad extraída del HTML del portal.
Todos usan dataclass para mantener consistencia con los parsers.
"""

from dataclasses import dataclass, field


@dataclass
class SenCountPorPartido:
    """Conteo de votos desglosado por partido político.

    Extraído de la primera tabla HTML del portal legacy que muestra
    el desglose por grupo parlamentario.
    """

    partido: str  # Abreviatura del partido (PRI, PAN, MORENA, etc.)
    a_favor: int = 0
    en_contra: int = 0
    abstencion: int = 0


@dataclass
class SenVotoNominal:
    """Voto individual de un senador en una votación nominal.

    Datos tal como aparecen en la tabla de votos del portal:
    número de lista, nombre completo, grupo parlamentario y
    sentido del voto.
    """

    numero: int
    nombre: str
    grupo_parlamentario: str
    voto: str


@dataclass
class SenVotacionDetail:
    """Detalle de una votación del Senado (sin votos nominales).

    Incluye metadata extraída del HTML: fecha, legislature, ejercicio,
    descripción, conteos agregados y desglose por partido.
    """

    fecha: str  # Formato dd/mm/yyyy (portal legacy)
    año_ejercicio: int  # 1, 2 o 3
    periodo: str  # LX, LXI, ..., LXV
    descripcion: str  # Texto de la iniciativa
    pro_count: int
    contra_count: int
    abstention_count: int
    counts_por_partido: list[SenCountPorPartido] = field(default_factory=list)
