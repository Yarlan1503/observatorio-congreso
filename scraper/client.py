"""
client.py — Cliente HTTP con caché para el SITL/INFOPAL.

Maneja requests con rate limiting, caché file-based con SHA256,
retry con backoff exponencial, y decodificación automática Latin-1/UTF-8.
"""

import time
import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from scraper.config import (
    CACHE_DIR,
    DEFAULT_HEADERS,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
)

logger = logging.getLogger(__name__)


class SITLClient:
    """Cliente HTTP con caché file-based y rate limiting para el SITL.

    Características:
    - Caché en archivos con hash SHA256
    - Rate limiting configurable (default 2s entre requests)
    - Retry con backoff exponencial (hasta MAX_RETRIES)
    - Decodificación automática UTF-8 / Latin-1
    - Header Referer configurable (SITL lo requiere para algunas páginas)
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY,
        timeout: float = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        cache_dir: Optional[Path] = None,
    ):
        self.use_cache = use_cache
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._cache_dir = cache_dir or CACHE_DIR
        self._last_request_time: float = 0.0
        self._session = httpx.Client(
            timeout=self.timeout,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )

    def _cache_path(self, url: str) -> Path:
        """Genera path de caché para una URL usando SHA256."""
        h = hashlib.sha256(url.encode()).hexdigest()
        return self._cache_dir / f"{h}.html"

    def _rate_limit(self) -> None:
        """Espera si es necesario para respetar el rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    @staticmethod
    def _decode_content(content: bytes) -> str:
        """Decodifica bytes a string probando UTF-8 primero, luego Latin-1.

        El SITL mezcla encodings: algunas páginas declaran UTF-8 pero tienen
        bytes inválidos (ej: 0xed en CSS). Se usa errors='replace' para UTF-8
        como primer intento, lo que reemplaza bytes inválidos sin romper los
        caracteres acentuados. Solo se usa Latin-1 como fallback extremo.
        """
        try:
            return content.decode("utf-8", errors="replace")
        except Exception:
            return content.decode("latin-1")

    def _fetch_with_retry(
        self, url: str, headers: dict, referer: Optional[str] = None
    ) -> bytes:
        """Realiza un GET con retry y backoff exponencial."""
        req_headers = dict(headers)
        if referer:
            req_headers["Referer"] = referer

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"GET {url} (intento {attempt}/{self.max_retries})")
                resp = self._session.get(url, headers=req_headers)
                resp.raise_for_status()
                return resp.content
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 2**attempt
                    logger.warning(
                        f"Error en intento {attempt}: {exc}. Reintentando en {wait}s..."
                    )
                    time.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def get_html(
        self, url: str, referer: Optional[str] = None, force_refresh: bool = False
    ) -> str:
        """Obtiene HTML de una URL, con caché opcional.

        Args:
            url: URL completa a obtener.
            referer: Header Referer (SITL lo requiere para algunas páginas).
            force_refresh: Si True, ignora la caché y hace request fresco.

        Returns:
            HTML decodificado como string.
        """
        cache_file = self._cache_path(url)

        # Intentar caché
        if self.use_cache and not force_refresh and cache_file.exists():
            logger.debug(f"Cache HIT: {url}")
            return cache_file.read_text(encoding="utf-8")

        # Rate limit antes del request
        self._rate_limit()

        # Fetch con retry
        content = self._fetch_with_retry(url, DEFAULT_HEADERS, referer=referer)
        html = self._decode_content(content)
        self._last_request_time = time.time()

        # Guardar en caché
        if self.use_cache:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(html, encoding="utf-8")

        return html

    def get_soup(
        self, url: str, referer: Optional[str] = None, force_refresh: bool = False
    ) -> BeautifulSoup:
        """Obtiene BeautifulSoup de una URL usando parser lxml."""
        html = self.get_html(url, referer=referer, force_refresh=force_refresh)
        return BeautifulSoup(html, "lxml")

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()

    def __enter__(self) -> "SITLClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
