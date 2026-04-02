"""scraper.utils.text_utils - backward compatibility wrapper.

Este módulo re-exporta normalize_name desde su nueva ubicación en
diputados.scraper.utils.text_utils para mantener compatibilidad
con imports como `from scraper.utils.text_utils import normalize_name`.
"""

from diputados.scraper.utils.text_utils import normalize_name

__all__ = ["normalize_name"]
