"""Parsers para el scraper legacy del Senado (LX-LXV)."""

from .legacy import parse_legacy_votacion

__all__ = [
    "parse_legacy_votacion",
]
