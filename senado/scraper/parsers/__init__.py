"""Parsers para el scraper del Senado.

- legacy.py: Portal legacy (LX-LXV) — /informacion/votaciones/vota/{id}
- lxvi_portal.py: Portal LXVI (LX-LXVI) — /66/votacion/{id} + AJAX endpoint
"""

from .legacy import parse_legacy_votacion
from .lxvi_portal import parse_lxvi_votacion, parse_votacion_ajax, parse_votacion_page

__all__ = [
    "parse_legacy_votacion",
    "parse_lxvi_votacion",
    "parse_votacion_page",
    "parse_votacion_ajax",
]
