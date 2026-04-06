"""
client.py — Cliente HTTP para el portal LXVI del Senado.

Extraído de cli_curl_cffi.py para separar lógica HTTP del parsing y CLI.
Usa curl_cffi con impersonate="chrome" para evadir WAF Incapsula.

Portal: https://www.senado.gob.mx/66/votacion/{id}
AJAX: POST /66/app/votaciones/functions/viewTableVot.php
"""

import contextlib
import hashlib
import logging
import pickle
import time
from pathlib import Path
from urllib.parse import urlencode

from curl_cffi.requests import BrowserTypeLiteral, Session

from .config import (
    BASE_BACKOFF,
    CACHE_DIR,
    COOKIE_PATH,
    LXVI_AJAX_URL,
    LXVI_VOTACION_URL_TEMPLATE,
    MAX_RETRIES,
    WAF_MARKERS,
    WAF_MAX_SIZE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Excepciones específicas
# =============================================================================


class SessionBurnedError(RuntimeError):
    """La sesión fue quemada por el WAF — múltiples bloqueos consecutivos.

    El caller debe pausar y reanudar en vez de seguir golpeando.
    """

    pass


class SenadoLXVIClient:
    """Cliente HTTP del Senado para el portal LXVI (/66/votacion/).

    Portal: https://www.senado.gob.mx/66/votacion/{id}
    AJAX: POST /66/app/votaciones/functions/viewTableVot.php

    Usa curl_cffi con impersonate de Chrome para evadir WAF Incapsula.
    Rota entre versiones de Chrome (JA3 fingerprints diferentes) al recrear
    sesiones para evitar correlación por TLS fingerprint.
    """

    # Targets de impersonate con JA3 hashes diferentes
    # NOTA: La rotación de JA3 es CONTRAPRODUCENTE con Incapsula —
    # un cliente que cambia su TLS fingerprint se ve MÁS sospechoso.
    # Usar solo 'chrome' (fijo) como el scraper de votaciones original.
    _IMPERSONATE_TARGETS: tuple[BrowserTypeLiteral, ...] = ("chrome",)

    # Circuit breaker: después de N WAFs consecutivos, declarar sesión quemada
    WAF_CONSECUTIVE_THRESHOLD = 2

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = 2.0,
        cache_dir: Path | None = None,
        cookie_path: Path | None = None,
    ):
        """Inicializa el cliente.

        Args:
            use_cache: Si True, usa caché file-based.
            delay: Delay mínimo entre requests en segundos.
            cache_dir: Directorio de caché. Si None, usa CACHE_DIR.
            cookie_path: Path del archivo de cookies. Si None, usa COOKIE_PATH.
                        Usar paths diferentes para scrapers diferentes para evitar
                        que se corrompan las cookies entre sí.
        """
        self.use_cache = use_cache
        self.delay = delay
        self.cache_dir = cache_dir or CACHE_DIR
        self._cookie_path = cookie_path or COOKIE_PATH
        self._last_request_time = 0.0
        self._impersonate_idx = 0
        self._consecutive_wafs = 0

        # Crear directorio de caché si es necesario
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Crear sesión con impersonate de Chrome
        self._session = self._create_session()

    def _create_session(self, impersonate: BrowserTypeLiteral | None = None) -> Session:
        """Crea una nueva sesión curl_cffi con impersonate de Chrome.

        Args:
            impersonate: Target específico. Si None, usa el actual del ciclo.

        Returns:
            Sesión configurada con headers y cookies.
        """
        target = impersonate or self._IMPERSONATE_TARGETS[self._impersonate_idx]
        session = Session(impersonate=target)
        logger.debug(f"Sesión creada con impersonate={target}")

        # Cargar cookies persistidas si existen
        if self._cookie_path.exists():
            try:
                with open(self._cookie_path, "rb") as f:
                    cookies_dict = pickle.load(f)
                for name, value in cookies_dict.items():
                    session.cookies.set(name, value)
                logger.debug(f"Cookies cargadas desde {self._cookie_path.name}")
            except Exception as e:
                logger.warning(f"Error cargando cookies: {e}")

        return session

    def _save_cookies(self) -> None:
        """Persiste cookies de la sesión actual a disco."""
        try:
            self._cookie_path.parent.mkdir(parents=True, exist_ok=True)
            cookies_dict = dict(self._session.cookies)
            with open(self._cookie_path, "wb") as f:
                pickle.dump(cookies_dict, f)
            logger.debug(f"Cookies guardadas en {self._cookie_path.name}")
        except Exception as e:
            logger.warning(f"Error guardando cookies: {e}")

    def _is_waf_response(self, html: str, status_code: int) -> bool:
        """Detecta si la respuesta es un bloqueo del WAF Incapsula.

        Criterios:
        1. Status codes de bloqueo (403, 406, 429, 503)
        2. Tamaño < 5KB CON marcadores de WAF

        También actualiza el circuit breaker de WAFs consecutivos.

        Args:
            html: Contenido HTML de la respuesta.
            status_code: Código HTTP de la respuesta.

        Returns:
            True si se detecta bloqueo WAF.
        """
        is_waf = False

        # Criterio 1: Status codes de bloqueo
        if status_code in (403, 406, 429, 503):
            logger.warning(f"Status code de bloqueo: {status_code}")
            is_waf = True

        # Criterio 2: Página pequeña CON marcadores de bloqueo real
        if not is_waf and len(html) < WAF_MAX_SIZE:
            html_lower = html.lower()
            for marker in WAF_MARKERS:
                if marker.lower() in html_lower:
                    logger.warning(f"WAF bloqueo detectado: {marker} ({len(html)} bytes)")
                    is_waf = True
                    break
            if not is_waf:
                logger.debug(f"Página pequeña ({len(html)} bytes) pero sin marcadores WAF")

        # Circuit breaker
        if is_waf:
            self._consecutive_wafs += 1
            if self._consecutive_wafs >= self.WAF_CONSECUTIVE_THRESHOLD:
                logger.error(f"Session burned: {self._consecutive_wafs} WAFs consecutivos")
                raise SessionBurnedError(
                    f"Sesión quemada: {self._consecutive_wafs} WAFs consecutivos"
                )
        else:
            # Reset contador en respuesta exitosa
            if self._consecutive_wafs > 0:
                logger.debug(f"WAF counter reset (era {self._consecutive_wafs})")
            self._consecutive_wafs = 0

        return is_waf

    def _backoff(self, attempt: int) -> None:
        """Aplica backoff exponencial.

        Args:
            attempt: Número de intento actual (0-indexed).
        """
        wait_time = BASE_BACKOFF * (2**attempt)
        logger.info(f"Backoff: esperando {wait_time:.1f}s (intento {attempt + 1})")
        time.sleep(wait_time)

    def _recreate_session(self) -> None:
        """Recrea la sesión HTTP con el siguiente impersonate del ciclo.

        Rota entre versiones de Chrome para cambiar el TLS fingerprint (JA3)
        y evitar que el WAF nos correlacione por fingerprint.
        """
        # Avanzar al siguiente target en el ciclo
        self._impersonate_idx = (self._impersonate_idx + 1) % len(self._IMPERSONATE_TARGETS)
        target = self._IMPERSONATE_TARGETS[self._impersonate_idx]
        logger.info(f"Recreando sesión con impersonate={target}...")
        with contextlib.suppress(Exception):
            self._session.close()
        self._session = self._create_session(impersonate=target)
        # Reset circuit breaker al crear nueva sesión
        self._consecutive_wafs = 0

    def reset_waf_counter(self) -> None:
        """Reinicia el circuit breaker de WAFs consecutivos.

        Útil después de una pausa prolongada para dar tiempo al WAF
        a expirar el bloqueo de sesión.
        """
        self._consecutive_wafs = 0
        logger.debug("WAF circuit breaker reset")

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
                        raise RuntimeError(f"WAF bloqueó después de {MAX_RETRIES} intentos: {url}")

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
                logger.debug(f"Excepción no-curl en attempt {attempt + 1}: {type(e).__name__}: {e}")
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
            return cache_page.read_text(encoding="utf-8"), cache_ajax.read_text(encoding="utf-8")

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

    def get(self, url: str, cache_key: str | None = None) -> str:
        """GET genérico con anti-WAF, rate limiting y caché.

        Método reutilizable para cualquier URL del portal del Senado.
        Usa la misma maquinaria anti-WAF que get_votacion().

        Args:
            url: URL completa a fetchear.
            cache_key: Clave opcional para caché file-based. Si None, no cachea.

        Returns:
            Contenido HTML decodificado.

        Raises:
            RuntimeError: Si se agotan los reintentos por WAF.
        """
        # Cache check
        if cache_key and self.use_cache:
            cp = self._cache_path(cache_key)
            if cp.exists():
                logger.debug(f"Cache hit: {cache_key}")
                return cp.read_text(encoding="utf-8")

        self._rate_limit()
        html = self._fetch_with_retry("GET", url)

        # Guardar cache
        if cache_key and self.use_cache:
            self._cache_path(cache_key).write_text(html, encoding="utf-8")

        return html

    def close(self) -> None:
        """Cierra la sesión HTTP y persiste cookies."""
        self._save_cookies()
        try:
            self._session.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión: {e}")
