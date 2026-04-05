"""
scraper/senado — Scraper del portal del Senado (portal LXVI).

Portal: https://www.senado.gob.mx/66/votacion/{id}
Rango: IDs 1 a 5070+ (LX-LXVI)
"""

from .cli import SenadoCongresoPipeline
from .client import SenadoLXVIClient

__all__ = ["SenadoCongresoPipeline", "SenadoLXVIClient"]
