"""
client.py — Cliente HTTP para el portal LXVI del Senado.

Extraído de cli_curl_cffi.py para separar lógica HTTP del parsing y CLI.
Usa curl_cffi con impersonate="chrome" para evadir WAF Incapsula.

Portal: https://www.senado.gob.mx/66/votacion/{id}
AJAX: POST /66/app/votaciones/functions/viewTableVot.php
"""

import hashlib
import logging
import pickle
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from curl_cffi.requests import Session

from .config import (
    CACHE_DIR,
    COOKIE_PATH,
    LXVI_AJAX_URL,
    LXVI_VOTACION_URL_TEMPLATE,
    MAX_RETRIES,
    BASE_BACKOFF,
    WAF_MARKERS,
    WAF_MAX_SIZE,
)

logger = logging.getLogger(__name__)


class SenadoLXVIClient:
    """Cliente HTTP del Senado para el portal LXVI (/66/votacion/).

    Portal: https://www.senado.gob.mx/66/votacion/{id}
    AJAX: POST /66/app/votaciones/functions/viewTableVot.php

    Usa curl_cffi con impersonate="chrome" para evadir WAF Incapsula.
    Flujo:
    1. GET página principal (cookies + metadata HTML)
    2. POST AJAX endpoint (tabla de votos nominales)
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = 2.0,
        cache_dir: Optional[Path] = None,
    ):
        """Inicializa el cliente.

        Args:
            use_cache: Si True, usa caché file-based.
            delay: Delay mínimo entre requests en segundos.
            cache_dir: Directorio de caché. Si None, usa CACHE_DIR.
        """
        self.use_cache = use_cache
        self.delay = delay
        self.cache_dir = cache_dir or CACHE_DIR
        self._last_request_time = 0.0

        # Crear directorio de caché si es necesario
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Crear sesión con impersonate de Chrome
        self._session = self._create_session()

    def _create_session(self) -> Session:
        """Crea una nueva sesión curl_cffi con impersonate de Chrome.

        Returns:
            Sesión configurada con headers y cookies.
        """
        session = Session(
            impersonate="chrome",  # TLS fingerprint de Chrome latest
        )

        # Cargar cookies persistidas si existen
        if COOKIE_PATH.exists():
            try:
                with open(COOKIE_PATH, "rb") as f:
                    cookies_dict = pickle.load(f)
                for name, value in cookies_dict.items():
                    self._session.cookies.set(name, value)
                logger.debug("Cookies cargadas desde disco")
            except Exception as e:
                logger.warning(f"Error cargando cookies: {e}")

        return session

    def _save_cookies(self) -> None:
        """Persiste cookies de la sesión actual a disco."""
        try:
            COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cookies_dict = dict(self._session.cookies)
            with open(COOKIE_PATH, "wb") as f:
                pickle.dump(cookies_dict, f)
            logger.debug("Cookies guardadas en disco")
        except Exception as e:
            logger.warning(f"Error guardando cookies: {e}")

    def _is_waf_response(self, html: str, status_code: int) -> bool:
        """Detecta si la respuesta es un bloqueo del WAF Incapsula.

        Criterios:
        1. Status codes de bloqueo (403, 406, 429, 503)
        2. Tamaño < 5KB CON marcadores de WAF

        Args:
            html: Contenido HTML de la respuesta.
            status_code: Código HTTP de la respuesta.

        Returns:
            True si se detecta bloqueo WAF.
        """
        # Criterio 1: Status codes de bloqueo
        if status_code in (403, 406, 429, 503):
            logger.warning(f"Status code de bloqueo: {status_code}")
            return True

        # Criterio 2: Página pequeña CON marcadores de bloqueo real
        if len(html) < WAF_MAX_SIZE:
            html_lower = html.lower()
            for marker in WAF_MARKERS:
                if marker.lower() in html_lower:
                    logger.warning(
                        f"WAF bloqueo detectado: {marker} ({len(html)} bytes)"
                    )
                    return True
            logger.debug(f"Página pequeña ({len(html)} bytes) pero sin marcadores WAF")

        return False

    def _backoff(self, attempt: int) -> None:
        """Aplica backoff exponencial.

        Args:
            attempt: Número de intento actual (0-indexed).
        """
        wait_time = BASE_BACKOFF * (2**attempt)
        logger.info(f"Backoff: esperando {wait_time:.1f}s (intento {attempt + 1})")
        time.sleep(wait_time)

    def _recreate_session(self) -> None:
        """Recrea la sesión HTTP (nuevo TLS handshake)."""
        logger.info("Recreando sesión HTTP...")
        try:
            self._session.close()
        except Exception:
            pass
        self._session = self._create_session()

    def _cache_path(self, key: str) -> Path:
        """Genera path SHA256 para caché basado en una key."""
        h = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{h}.html"

    def _rate_limit(self) -> None:
        """Aplica delay mínimo entre requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def _decode_response(self, content: bytes) -> str:
        """Decodifica bytes de respuesta a string.

        Args:
            content: Bytes de la respuesta HTTP.

        Returns:
            String decodificado.
        """
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            logger.debug("UTF-8 decode failed, using iso-8859-1 fallback")
            return content.decode("iso-8859-1")

    def _fetch_with_retry(self, method: str, url: str, **kwargs) -> str:
        """Ejecuta un request HTTP con reintentos anti-WAF.

        Args:
            method: 'GET' o 'POST'.
            url: URL a fetchear.
            **kwargs: Argumentos adicionales para session.get/post.

        Returns:
            Contenido HTML decodificado.

        Raises:
            RuntimeError: Si se agotan los reintentos por WAF.
        """
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"{method}: {url} (intento {attempt + 1})")

                if method.upper() == "POST":
                    response = self._session.post(
                        url,
                        timeout=30.0,
                        http_version="v1",
                        **kwargs,
                    )
                else:
                    response = self._session.get(
                        url,
                        timeout=30.0,
                        http_version="v1",
                        **kwargs,
                    )

                html = self._decode_response(response.content)

                # Verificar si es bloqueo WAF
                if self._is_waf_response(html, response.status_code):
                    if attempt < MAX_RETRIES - 1:
                        self._backoff(attempt)
                        self._recreate_session()
                        continue
                    else:
                        raise RuntimeError(
                            f"WAF bloqueó después de {MAX_RETRIES} intentos: {url}"
                        )

                # Verificar status code
                if response.status_code != 200:
                    response.raise_for_status()

                # Guardar cookies
                self._save_cookies()

                return html

            except KeyboardInterrupt:
                logger.warning("Interrumpido por usuario")
                raise
            except RuntimeError:
                raise
            except Exception as e:
                if "curl" in str(type(e).__name__).lower():
                    logger.error(f"Error curl_cffi: {e}")
                    if attempt < MAX_RETRIES - 1:
                        self._backoff(attempt)
                        self._recreate_session()
                        continue
                raise

        raise RuntimeError(f"Falló después de {MAX_RETRIES} intentos: {url}")

    def get_votacion(self, senado_id: int) -> tuple[str, str]:
        """Obtiene la página principal y la tabla AJAX de una votación.

        Args:
            senado_id: ID de la votación en el portal.

        Returns:
            Tuple de (page_html, ajax_html).

        Raises:
            RuntimeError: Si se agotan los reintentos por WAF.
        """
        page_url = LXVI_VOTACION_URL_TEMPLATE.format(id=senado_id)

        # --- Cache ---
        cache_page = self._cache_path(f"lxvi_page_{senado_id}")
        cache_ajax = self._cache_path(f"lxvi_ajax_{senado_id}")

        page_html = ""
        ajax_html = ""

        if self.use_cache and cache_page.exists() and cache_ajax.exists():
            logger.debug(f"Cache hit: votacion {senado_id}")
            return cache_page.read_text(encoding="utf-8"), cache_ajax.read_text(
                encoding="utf-8"
            )

        # --- 1. GET página principal (cookies + metadata) ---
        self._rate_limit()
        page_html = self._fetch_with_retry("GET", page_url)

        if not page_html or len(page_html) < 100:
            logger.warning(f"HTML vacío o muy corto para ID {senado_id}")

        # Guardar cache de página
        if self.use_cache:
            cache_page.write_text(page_html, encoding="utf-8")

        # --- 2. POST AJAX endpoint (tabla de votos) ---
        self._rate_limit()

        ajax_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": page_url,
        }

        ajax_data = urlencode(
            {
                "action": "ajax",
                "cell": "1",
                "order": "DESC",
                "votacion": str(senado_id),
                "q": "",
            }
        )

        ajax_html = self._fetch_with_retry(
            "POST",
            LXVI_AJAX_URL,
            headers=ajax_headers,
            data=ajax_data.encode("utf-8"),
        )

        # Guardar cache de AJAX
        if self.use_cache:
            cache_ajax.write_text(ajax_html, encoding="utf-8")

        return page_html, ajax_html

    def close(self) -> None:
        """Cierra la sesión HTTP y persiste cookies."""
        self._save_cookies()
        try:
            self._session.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión: {e}")
