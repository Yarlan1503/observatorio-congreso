"""
scraper/senado — Scraper del portal del Senado (sistema legacy LX-LXV).

Portal: https://www.senado.gob.mx/informacion/votaciones/vota/{id}
Rango: IDs 1 a 4690
"""

from .cli import SenadoCongresoPipeline, SenateClientWithLegacyHeaders

__all__ = ["SenadoCongresoPipeline", "SenateClientWithLegacyHeaders"]
