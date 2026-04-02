"""
client.py — Cliente HTTP con caché para el portal del Senado LXVI.

Maneja requests con rate limiting, caché file-based con SHA256,
retry con backoff exponencial, y parsing BeautifulSoup.
"""

import time
import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .config import (
    SENADO_HEADERS,
    SENADO_AJAX_HEADERS,
    SENADO_AJAX_TABLE_URL,
    SENADO_VOTACION_URL_TEMPLATE,
    SENADO_CACHE_DIR,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
)

logger = logging.getLogger(__name__)


class SenadoClient:
    """Cliente HTTP con caché file-based y rate limiting para el Senado LXVI.

    Características:
    - Caché en archivos con hash SHA256
    - Rate limiting configurable (default 2s entre requests)
    - Retry con backoff exponencial (hasta MAX_RETRIES)
    - Headers defensivos Chromium-like con Accept-Language es-MX
    - Header Referer al sitio del Senado
    - Soporte para endpoints AJAX con headers específicos
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY,
        max_retries: int = MAX_RETRIES,
        cache_dir: Optional[Path] = None,
    ):
        self.use_cache = use_cache
        self.delay = delay
        self.max_retries = max_retries
        self._cache_dir = cache_dir or SENADO_CACHE_DIR
        self._last_request_time: float = 0.0
        self._session = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers=SENADO_HEADERS,
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

    def _fetch_with_retry(self, url: str) -> httpx.Response:
        """Realiza un GET con retry y backoff exponencial."""
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"GET {url} (intento {attempt}/{self.max_retries})")
                resp = self._session.get(url)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 2**attempt
                    logger.warning(
                        f"Error en intento {attempt}: {exc}. Reintentando en {wait}s..."
                    )
                    time.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def _fetch_ajax_with_retry(self, votacion_id: int) -> httpx.Response:
        """Realiza un POST AJAX con retry y backoff exponencial."""
        last_exc: Optional[Exception] = None
        url = SENADO_AJAX_TABLE_URL
        # POST con form-data (NO GET con params)
        data = {
            "action": "ajax",
            "cell": "1",
            "order": "DESC",
            "votacion": str(votacion_id),
            "q": "",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"POST AJAX {url} (votacion={votacion_id}) "
                    f"(intento {attempt}/{self.max_retries})"
                )
                resp = self._session.post(
                    url,
                    data=data,
                    headers=SENADO_AJAX_HEADERS,
                )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 2**attempt
                    logger.warning(
                        f"Error AJAX en intento {attempt}: {exc}. "
                        f"Reintentando en {wait}s..."
                    )
                    time.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def get_votacion_detail(self, votacion_id: int, force_refresh: bool = False) -> str:
        """
        Obtiene el HTML de detalle de una votación.

        IMPORTANTE: Debe llamarse ANTES de get_ajax_table() para establecer
        las cookies de Incapsula/WAF en la sesión.

        Args:
            votacion_id: ID de la votación.
            force_refresh: Si True, ignora la caché y hace request fresco.

        Returns:
            HTML del detalle.
        """
        url = SENADO_VOTACION_URL_TEMPLATE.format(id=votacion_id)
        return self.get_html(url, force_refresh=force_refresh)

    def get_html(self, url: str, force_refresh: bool = False) -> str:
        """Obtiene HTML de una URL, con caché opcional.

        Args:
            url: URL completa a obtener.
            force_refresh: Si True, ignora la caché y hace request fresco.

        Returns:
            HTML como string.
        """
        cache_file = self._cache_path(url)

        # Intentar caché
        if self.use_cache and not force_refresh and cache_file.exists():
            logger.debug(f"Cache HIT: {url}")
            return cache_file.read_text(encoding="utf-8")

        # Rate limit antes del request
        self._rate_limit()

        # Fetch con retry
        resp = self._fetch_with_retry(url)
        html = resp.text
        self._last_request_time = time.time()

        # Guardar en caché
        if self.use_cache:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(html, encoding="utf-8")

        return html

    def get_soup(self, url: str, force_refresh: bool = False) -> BeautifulSoup:
        """Obtiene BeautifulSoup de una URL usando parser lxml."""
        html = self.get_html(url, force_refresh=force_refresh)
        return BeautifulSoup(html, "lxml")

    def get_ajax_table(self, votacion_id: int, force_refresh: bool = False) -> str:
        """Obtiene la tabla AJAX de votaciones para un votacion_id dado.

        IMPORTANTE: Requiere que se haya llamado get_votacion_detail() primero
        para establecer las cookies de sesión (Incapsula/WAF).

        Args:
            votacion_id: ID de la votación a consultar.
            force_refresh: Si True, ignora la caché y hace request fresco.

        Returns:
            HTML de la tabla AJAX como string.
        """
        # URL única por votacion_id para el caché
        cache_key = f"{SENADO_AJAX_TABLE_URL}?votacion={votacion_id}"
        cache_file = self._cache_path(cache_key)

        # Intentar caché
        if self.use_cache and not force_refresh and cache_file.exists():
            logger.debug(f"AJAX Cache HIT: idVot={votacion_id}")
            return cache_file.read_text(encoding="utf-8")

        # Rate limit antes del request
        self._rate_limit()

        # Fetch AJAX con retry
        resp = self._fetch_ajax_with_retry(votacion_id)
        html = resp.text
        self._last_request_time = time.time()

        # Guardar en caché
        if self.use_cache:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(html, encoding="utf-8")

        return html

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()

    def __enter__(self) -> "SenadoClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
