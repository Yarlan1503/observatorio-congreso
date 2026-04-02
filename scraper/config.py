"""scraper.config - backward compatibility wrapper.

Este módulo re-exporta DB_PATH desde diputados.scraper.config
para mantener compatibilidad con migrations que usan
`from scraper.config import DB_PATH`.
"""

from diputados.scraper.config import DB_PATH

__all__ = ["DB_PATH"]
