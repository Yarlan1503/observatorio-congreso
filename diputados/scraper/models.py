"""
models.py — Modelos Pydantic para datos parseados del SITL/INFOPAL.

Cada modelo representa una entidad extraída del HTML del sistema SITL.
Todos usan Pydantic v2 BaseModel.
"""

from pydantic import BaseModel

# --- Votaciones (listado por periodo) ---


class VotacionRecord(BaseModel):
    """Registro de una votación del listado general."""

    sitl_id: int
    numero_secuencial: int
    titulo: str
    fecha: str
    periodo: int


# --- Desglose estadístico por partido ---


class DesglosePartido(BaseModel):
    """Desglose de votos de un partido en una votación."""

    partido_nombre: str
    a_favor: int
    en_contra: int
    abstencion: int
    solo_asistencia: int
    ausente: int
    total: int


class DesgloseVotacion(BaseModel):
    """Desglose completo de una votación por partido."""

    sitl_id: int
    titulo: str
    fecha: str
    partidos: list[DesglosePartido]
    totales: DesglosePartido


# --- Votación nominal (listado por partido) ---


class VotoNominal(BaseModel):
    """Voto individual de un diputado en votación nominal."""

    numero: int
    nombre: str
    sentido: str
    diputado_sitl_id: int | None = None


class NominalVotacion(BaseModel):
    """Listado nominal de votos de un partido en una votación."""

    sitl_id: int
    partido_nombre: str
    votos: list[VotoNominal]
    resumen: dict[str, int]


# --- Ficha de diputado (curricula) ---


class FichaDiputado(BaseModel):
    """Ficha curricular de un diputado."""

    nombre: str
    principio_eleccion: str
    entidad: str | None = None
    distrito: str | None = None
    curul: str | None = None
    fecha_nacimiento: str | None = None
    email: str | None = None
    suplente: str | None = None
    partido: str | None = None
    sitl_id: int | None = None


# --- Composición del pleno ---


class DiputadoComposicion(BaseModel):
    """Diputado listado en la página de composición (info_diputados.php).

    Datos mínimos obtenibles desde la página de composición:
    nombre y sitl_id extraídos de los links a curricula.
    """

    nombre: str
    sitl_id: int | None = None


class ComposicionPartido(BaseModel):
    """Composición de un grupo parlamentario en el pleno."""

    partido_nombre: str
    total: int
    diputados: list[DiputadoComposicion] = []


class ComposicionPleno(BaseModel):
    """Composición completa del pleno legislativo."""

    legislatura: str
    partidos: list[ComposicionPartido]
