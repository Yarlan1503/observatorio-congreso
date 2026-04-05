"""Parsers para el scraper del Senado.

- lxvi_portal.py: Portal LXVI (LX-LXVI) — /66/votacion/{id} + AJAX endpoint
"""

from .lxvi_portal import parse_lxvi_votacion, parse_votacion_ajax, parse_votacion_page

__all__ = [
    "parse_lxvi_votacion",
    "parse_votacion_page",
    "parse_votacion_ajax",
]
