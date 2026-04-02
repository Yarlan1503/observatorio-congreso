"""
parsers/__init__.py — Módulo de parsers para el scraper SIL.
"""

from scraper_sil.parsers.busqueda import parse_busqueda_form
from scraper_sil.parsers.resultados import (
    parse_resultados,
    parse_paginacion,
)
from scraper_sil.parsers.detalle import parse_detalle_votacion
from scraper_sil.parsers.votos import parse_votos_grupo

__all__ = [
    "parse_busqueda_form",
    "parse_resultados",
    "parse_paginacion",
    "parse_detalle_votacion",
    "parse_votos_grupo",
]
