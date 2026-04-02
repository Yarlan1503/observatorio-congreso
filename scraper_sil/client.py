"""
client.py — Cliente HTTP con SSL bypass, retry, cache y rate limiting.

Para el portal sil.gobernacion.gob.mx que tiene problemas de SSL
y requiere manejo específico de sesiones.
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

from scraper_sil.config import (
    SIL_BASE_URL,
    SIL_HEADERS,
    SIL_CACHE_DIR,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    SIL_ENCODING,
)

logger = logging.getLogger(__name__)


class SILClient:
    """Cliente HTTP para el portal SIL.

    Características:
    - SSL bypass (verify=False por problemas de certificado en nsil.gobernacion.gob.mx)
    - Rate limiting configurable (default 1.5s entre requests)
    - Retry con backoff exponencial (hasta MAX_RETRIES)
    - Cache file-based con hash SHA256
    - Encoding iso-8859-1 (latin-1) del portal
    - Manejo de SID de sesión
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY,
        max_retries: int = MAX_RETRIES,
        cache_dir: Optional[Path] = None,
        verify_ssl: bool = False,  # Default False para evitar problemas de SSL
    ):
        self.use_cache = use_cache
        self.delay = delay
        self.max_retries = max_retries
        self._cache_dir = cache_dir or SIL_CACHE_DIR
        self._last_request_time: float = 0.0
        self._sid: Optional[str] = None
        self._verify_ssl = verify_ssl

        # Crear sesión HTTP con headers por defecto
        self._session = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers=SIL_HEADERS,
            follow_redirects=True,
            verify=verify_ssl,  # SSL bypass
        )

        # Diccionario para almacenar cookies de sesión por SID
        self._session_cookies: dict[str, dict] = {}

    @property
    def sid(self) -> Optional[str]:
        """SID de sesión actual."""
        return self._sid

    @sid.setter
    def sid(self, value: str) -> None:
        """Establece el SID de sesión y limpia cookies anteriores."""
        self._sid = value
        logger.debug(f"SID establecido: {value}")

    def set_sid(self, sid: str) -> None:
        """Establece el SID de sesión externamente (ej: desde SessionManager).

        Args:
            sid: SID de sesión obtenido de Playwright/Selenium.
        """
        self._sid = sid
        logger.info(f"SID establecido externamente: {sid}")

    def _cache_path(self, url: str, sid: Optional[str] = None) -> Path:
        """Genera path de caché para una URL usando SHA256.

        Args:
            url: URL completa o relativa.
            sid: SID de sesión para separar cachés por sesión.

        Returns:
            Path al archivo de caché.
        """
        # Incluir SID en el hash si está disponible
        cache_key = f"{sid or 'no_sid'}:{url}"
        h = hashlib.sha256(cache_key.encode()).hexdigest()
        return self._cache_dir / f"{h}.html"

    def _rate_limit(self) -> None:
        """Espera si es necesario para respetar el rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            wait_time = self.delay - elapsed
            logger.debug(f"Rate limit: esperando {wait_time:.2f}s")
            time.sleep(wait_time)

    def _fetch_with_retry(
        self, url: str, method: str = "GET", **kwargs
    ) -> httpx.Response:
        """Realiza un request con retry y backoff exponencial.

        Args:
            url: URL a solicitar.
            method: Método HTTP (GET o POST).
            **kwargs: Argumentos adicionales para el request.

        Returns:
            Response de httpx.

        Raises:
            httpx.HTTPStatusError: Si todos los intentos fallan.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"{method} {url} (intento {attempt}/{self.max_retries})")

                if method.upper() == "POST":
                    resp = self._session.post(url, **kwargs)
                else:
                    resp = self._session.get(url, **kwargs)

                resp.raise_for_status()
                return resp

            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 2**attempt  # Backoff exponencial: 2, 4, 8, ...
                    logger.warning(
                        f"Error en intento {attempt}: {exc}. Reintentando en {wait}s..."
                    )
                    time.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def get_html(
        self,
        url: str,
        force_refresh: bool = False,
        params: Optional[dict] = None,
    ) -> str:
        """Obtiene HTML de una URL, con caché opcional.

        Args:
            url: URL completa a obtener.
            force_refresh: Si True, ignora la caché y hace request fresco.
            params: Parámetros de query string.

        Returns:
            HTML como string decodificado con iso-8859-1.
        """
        # Incluir SID en clave de caché
        cache_file = self._cache_path(url, self._sid)

        # Intentar caché
        if self.use_cache and not force_refresh and cache_file.exists():
            logger.debug(f"Cache HIT: {url}")
            return cache_file.read_text(encoding=SIL_ENCODING)

        # Rate limit antes del request
        self._rate_limit()

        # Fetch con retry
        resp = self._fetch_with_retry(url, params=params)
        # Fix encoding: forzar iso-8859-1 para el portal SIL
        raw = resp.content
        try:
            html = raw.decode("iso-8859-1")
        except UnicodeDecodeError:
            html = raw.decode("cp1252", errors="replace")
        self._last_request_time = time.time()

        # Guardar en caché
        if self.use_cache:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(html, encoding=SIL_ENCODING)

        return html

    def post_html(
        self,
        url: str,
        data: Optional[dict] = None,
        force_refresh: bool = False,
    ) -> str:
        """Envía POST y retorna HTML, con caché opcional.

        Args:
            url: URL completa a solicitar.
            data: Datos del formulario.
            force_refresh: Si True, ignora la caché.

        Returns:
            HTML como string decodificado.
        """
        cache_key = f"POST:{url}:{str(data)}"
        cache_file = (
            self._cache_dir / f"{hashlib.sha256(cache_key.encode()).hexdigest()}.html"
        )

        if self.use_cache and not force_refresh and cache_file.exists():
            logger.debug(f"POST Cache HIT: {url}")
            return cache_file.read_text(encoding=SIL_ENCODING)

        self._rate_limit()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": SIL_BASE_URL,
        }

        resp = self._fetch_with_retry(url, method="POST", data=data, headers=headers)
        # Fix encoding: forzar iso-8859-1 para el portal SIL
        raw = resp.content
        try:
            html = raw.decode("iso-8859-1")
        except UnicodeDecodeError:
            html = raw.decode("cp1252", errors="replace")
        self._last_request_time = time.time()

        if self.use_cache:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(html, encoding=SIL_ENCODING)

        return html

    def extract_sid(self, html: str) -> Optional[str]:
        """Extrae el SID de una página HTML del portal.

        Args:
            html: HTML de cualquier página del portal SIL.

        Returns:
            SID si se encuentra, None otherwise.
        """
        import re

        # Buscar SID en URLs del HTML
        # Pattern: SID=abc123
        pattern = r"[?&]SID=([A-Za-z0-9]+)"
        match = re.search(pattern, html)
        if match:
            sid = match.group(1)
            logger.debug(f"SID extraído: {sid}")
            return sid

        # Buscar en el URL del action del formulario
        pattern = r'action=["\']([^"\']*[?&]SID=([^"\']+))["\']'
        match = re.search(pattern, html)
        if match:
            sid = match.group(2)
            logger.debug(f"SID extraído del form action: {sid}")
            return sid

        return None

    def get_search_page(self, force_refresh: bool = False) -> tuple[str, Optional[str]]:
        """Obtiene la página del formulario de búsqueda.

        Args:
            force_refresh: Si True, ignora la caché.

        Returns:
            Tuple de (HTML, SID extraído).
        """
        url = f"{SIL_BASE_URL}/Busquedas/Votacion/ProcesoBusquedaAvanzada.php"
        html = self.get_html(url, force_refresh=force_refresh)
        sid = self.extract_sid(html)
        if sid:
            self._sid = sid
        return html, sid

    def search_votaciones(
        self,
        params: dict,
        force_refresh: bool = False,
    ) -> str:
        """Envía formulario de búsqueda y retorna página de resultados.

        Args:
            params: Parámetros del formulario POST.
            force_refresh: Si True, ignora la caché.

        Returns:
            HTML de resultados.
        """
        # Asegurar que tenemos SID
        if not self._sid:
            _, sid = self.get_search_page()
            if not sid:
                logger.warning("No se pudo obtener SID, usando vacío")
                self._sid = ""

        # URL con SID
        url = f"{SIL_BUSQUEDA_URL}?SID={self._sid}"
        logger.info(f"Buscando votaciones con params: {params}")

        html = self.post_html(url, data=params, force_refresh=force_refresh)
        return html

    def get_resultados(
        self,
        page: int = 1,
        force_refresh: bool = False,
    ) -> str:
        """Obtiene página de resultados con paginación.

        Args:
            page: Número de página (1-indexed).
            force_refresh: Si True, ignora la caché.

        Returns:
            HTML de resultados.
        """
        if not self._sid:
            logger.error("SID no establecido. Llamar get_search_page primero.")
            return ""

        url = f"{SIL_RESULTADOS_URL}?SID={self._sid}&Pagina={page}"
        return self.get_html(url, force_refresh=force_refresh)

    def get_detalle_votacion(
        self,
        clave_asunto: str,
        clave_tramite: Optional[str] = None,
        force_refresh: bool = False,
    ) -> str:
        """Obtiene página de detalle de una votación.

        Args:
            clave_asunto: Clave del asunto (ej: 1234).
            clave_tramite: Clave del trámite (ej: 1).
            force_refresh: Si True, ignora la caché.

        Returns:
            HTML del detalle.
        """
        if not self._sid:
            logger.error("SID no establecido")
            return ""

        url = f"{SIL_DETALLE_URL}?SID={self._sid}&ClaveAsunto={clave_asunto}"
        if clave_tramite:
            url += f"&ClaveTramite={clave_tramite}"

        return self.get_html(url, force_refresh=force_refresh)

    def get_votos_legislador(
        self,
        clave_asunto: str,
        clave_tramite: str,
        tipo_voto: str = "F",
        force_refresh: bool = False,
    ) -> str:
        """Obtiene página de votos por legislators para un grupo (F/C/A/N).

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.
            tipo_voto: Tipo de voto (F=a_favor, C=en_contra, A=abstencion, N=ausente).
            force_refresh: Si True, ignora la caché.

        Returns:
            HTML con lista de legisladores y sus votos.
        """
        if not self._sid:
            logger.error("SID no establecido")
            return ""

        url = (
            f"{SIL_VOTOS_URL}?SID={self._sid}"
            f"&ClaveAsunto={clave_asunto}"
            f"&ClaveTramite={clave_tramite}"
            f"&voto={tipo_voto}"
        )

        return self.get_html(url, force_refresh=force_refresh)

    def get_total_pages(self, html: str) -> int:
        """Extrae el número total de páginas de resultados.

        Args:
            html: HTML de la página de resultados.

        Returns:
            Número total de páginas, 1 si no hay paginación.
        """
        import re

        # Buscar patrón de paginación: "Página 1 de X" o "1 - 50 de X resultados"
        patterns = [
            r"páginas?\s*:?\s*</[^>]*>\s*<[^>]*>\s*(\d+)",
            r"Página\s+\d+\s+de\s+(\d+)",
            r"(\d+)\s+-\s+\d+\s+de\s+(\d+)\s+resultados",
            r"Registros\s+?\d+\s?-?\s*(\d+)\s+de\s+(\d+)",
            r'class="paginador"[^>]*>.*?(\d+)</a>\s*</li>\s*<li[^>]*><a',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                # Último grupo generalmente contiene el total
                total = int(match.group(len(match.groups())))
                logger.debug(f"Total páginas detectado: {total}")
                return max(1, total)

        return 1

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()

    def __enter__(self) -> "SILClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


# Alias para uso en código
SIL_BUSQUEDA_URL = (
    "http://sil.gobernacion.gob.mx/Busquedas/Votacion/ProcesoBusquedaAvanzada.php"
)
SIL_RESULTADOS_URL = (
    "http://sil.gobernacion.gob.mx/Busquedas/Votacion/ResultadosBusquedaAvanzada.php"
)
SIL_DETALLE_URL = (
    "http://sil.gobernacion.gob.mx/ActividadLegislativa/Votacion/DetalleVotacion.php"
)
SIL_VOTOS_URL = "http://sil.gobernacion.gob.mx/ActividadLegislativa/Votacion/LegisladoresVotacionAsunto.php"
