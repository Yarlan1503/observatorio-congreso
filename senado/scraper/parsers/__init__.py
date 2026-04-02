"""Parsers para el scraper del Senado."""

from .directorio import (
    SenadorDirectorioRecord,
    ESTADO_TO_ABBR,
    ESTADOS_VALIDOS,
    parse_directorio_senadores,
    parse_senador_perfil,
    enrich_directorio_con_perfiles,
)
from .legacy import parse_legacy_votacion
from ..parsers_lxvi import (
    parse_votaciones_index,
    parse_votaciones_fecha,
    parse_votacion_detalle,
    parse_ajax_table,
)

__all__ = [
    # Directorio
    "SenadorDirectorioRecord",
    "ESTADO_TO_ABBR",
    "ESTADOS_VALIDOS",
    "parse_directorio_senadores",
    "parse_senador_perfil",
    "enrich_directorio_con_perfiles",
    # Legacy
    "parse_legacy_votacion",
    # LXVI
    "parse_votaciones_index",
    "parse_votaciones_fecha",
    "parse_votacion_detalle",
    "parse_ajax_table",
]
