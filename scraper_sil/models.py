"""
models.py — Modelos dataclass para datos estructurados del portal SIL.

Cada modelo representa una entidad extraída del HTML del portal
sil.gobernacion.gob.mx. Todos usan dataclass para mantener consistencia
con los parsers y loaders.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SILVotacionIndex:
    """Registro de una votación en los resultados de búsqueda.

    Datos mínimos del listado: clave de asunto, título, legislature,
    fecha y resultado.
    """

    clave_asunto: str
    clave_tramite: str
    titulo: str
    legislature: str
    fecha: str
    resultado: str
    tipo_asunto: str
    num_votos: Optional[int] = None


@dataclass
class SILVotacionDetail:
    """Metadata completa de una votacion del SIL.

    Incluye todos los campos del detalle: asunto, tramite, quorum,
    resultados por grupo, etc.
    """

    clave_asunto: str
    clave_tramite: str
    titulo: str
    legislature: str
    fecha: str
    tipo_asunto: str
    resultado: str
    tipo_votacion: str
    quorum: str
    # Conteo general
    a_favor: int = 0
    en_contra: int = 0
    abstencion: int = 0
    ausente: int = 0
    # Conteo por partido
    votos_por_grupo: dict[str, dict[str, int]] = field(default_factory=dict)
    fuente_url: str = ""

    @property
    def total_presentes(self) -> int:
        """Retorna el total de presentes (calculado)."""
        return self.a_favor + self.en_contra + self.abstencion + self.ausente


@dataclass
class SILVotoLegislador:
    """Voto individual de un legislador en una votación.

    Datos extraídos de la página de detalle de votos.
    """

    nombre: str
    partido: str
    estado: Optional[str]
    curul: Optional[str]
    voto: str  # a_favor, en_contra, abstencion, ausente
    tipo_voto: str  # F, C, A, N


@dataclass
class SILVotosCompletos:
    """Conjunto completo de votos de una votación.

    Incluye todos los grupos (Favor, Contra, Abstención, Ausentes)
    """

    clave_asunto: str
    clave_tramite: str
    votos: list[SILVotoLegislador] = field(default_factory=list)
    # Totales por grupo
    totales: dict[str, int] = field(default_factory=dict)


@dataclass
class SILBusquedaParams:
    """Parámetros de búsqueda para el formulario del SIL.

    Todos los parámetros posibles para filtrar votaciones.
    """

    legislature: str = "LXXVI"
    tipo_asunto: list[str] = field(default_factory=list)
    resultado: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    paginas: int = 50  # Resultados por página


@dataclass
class SILSession:
    """Sesión del portal SIL.

    El SID es necesario para mantener estado entre páginas.
    """

    sid: str
    legislature: str
    search_url: str = ""
    resultados_url: str = ""


@dataclass
class SILLoadResult:
    """Resultado de cargar una votación a la BD.

    Contiene estadísticas del proceso de inserción.
    """

    vote_event_id: str
    motion_id: str
    votos_insertados: int = 0
    votos_actualizados: int = 0
    legislators_new: int = 0
    organizations_new: int = 0
    success: bool = True
    error: Optional[str] = None
