"""
session_manager.py — Manager de sesiones JavaScript con Playwright para el portal SIL.

El portal sil.gobernacion.gob.mx requiere JavaScript para inicializar sesiones de búsqueda.
Esta clase usa Playwright para:
1. Inicializar una sesión JavaScript
2. Extraer el SID de la sesión
3. Monitorear el tiempo de vida de la sesión (~30 min)
4. Recrear automáticamente la sesión si expira

Si Playwright no está disponible, usa Selenium como fallback.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Constants for session management
SESSION_TIMEOUT_SECONDS = 25 * 60  # 25 minutes (expires in ~30)
PLAYWRIGHT_TIMEOUT_MS = 30000  # 30 seconds
PLAYWRIGHT_HEADLESS = True

# User agent for browser
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class SessionInfo:
    """Información de una sesión JavaScript."""

    sid: str
    created_at: float
    expires_at: float
    # Additional parameters from the form action
    serial: Optional[str] = None
    reg: Optional[str] = None
    origen: Optional[str] = None
    referencia: Optional[str] = None

    def is_expired(self) -> bool:
        """Verifica si la sesión ha expirado."""
        return time.time() >= self.expires_at

    def time_remaining(self) -> float:
        """Tiempo restante en segundos antes de expirar."""
        return max(0, self.expires_at - time.time())


class PlaywrightNotAvailableError(Exception):
    """Raised cuando ni Playwright ni Selenium están disponibles."""

    pass


class SessionManager:
    """Manager de sesiones JavaScript con Playwright.

    Usa Playwright (o Selenium como fallback) para inicializar sesiones
    JavaScript en el portal SIL y extraer el SID de sesión.

    Attributes:
        headless: Si True, el navegador corre en modo headless.
        timeout: Timeout para operaciones del navegador en ms.
        _session: Información de la sesión actual.
        _browser: Instancia del navegador (si está inicializado).
        _context: Contexto del navegador (si está inicializado).
        _page: Página activa (si está inicializado).
    """

    def __init__(
        self,
        headless: bool = PLAYWRIGHT_HEADLESS,
        timeout: int = PLAYWRIGHT_TIMEOUT_MS,
        user_agent: str = BROWSER_USER_AGENT,
    ):
        """Inicializa el SessionManager.

        Args:
            headless: Si True, el navegador corre sin interfaz gráfica.
            timeout: Timeout para operaciones del navegador en ms.
            user_agent: User agent para el navegador.
        """
        self.headless = headless
        self.timeout = timeout
        self.user_agent = user_agent

        # Playwright components
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        # Selenium fallback
        self._selenium_driver = None
        self._using_selenium = False

        # Session info
        self._session: Optional[SessionInfo] = None

        # Try to import playwright
        self._playwright_available = self._check_playwright()
        if not self._playwright_available:
            self._selenium_available = self._check_selenium()
        else:
            self._selenium_available = False

    def _check_playwright(self) -> bool:
        """Verifica si Playwright está disponible."""
        try:
            import playwright

            return True
        except ImportError:
            logger.debug("Playwright no está instalado")
            return False

    def _check_selenium(self) -> bool:
        """Verifica si Selenium está disponible."""
        try:
            from selenium import webdriver

            return True
        except ImportError:
            logger.debug("Selenium no está instalado")
            return False

    @property
    def is_available(self) -> bool:
        """Retorna True si hay alguna herramienta de browser disponible."""
        return self._playwright_available or self._selenium_available

    @property
    def session(self) -> Optional[SessionInfo]:
        """Retorna la información de la sesión actual."""
        return self._session

    def get_sid(self) -> Optional[str]:
        """Retorna el SID actual si existe y no ha expirado."""
        if self._session and not self._session.is_expired():
            return self._session.sid
        return None

    def is_expired(self) -> bool:
        """Verifica si la sesión actual ha expirado."""
        if self._session is None:
            return True
        return self._session.is_expired()

    def time_remaining(self) -> float:
        """Tiempo restante en segundos antes de expirar."""
        if self._session is None:
            return 0
        return self._session.time_remaining()

    def initialize(self) -> str:
        """Inicializa el navegador y navega al portal para obtener SID.

        Returns:
            El SID extraído de la sesión JavaScript.

        Raises:
            PlaywrightNotAvailableError: Si ningún browser driver está disponible.
        """
        if not self.is_available:
            raise PlaywrightNotAvailableError(
                "Ni Playwright ni Selenium están disponibles. "
                "Instale uno con: pip install playwright && playwright install chromium"
            )

        # Check if we need to refresh an expired session
        if self._session and not self._session.is_expired():
            logger.debug("Sesión aún válida, reutilizando SID: %s", self._session.sid)
            return self._session.sid

        # Clean up any existing session
        self.cleanup()

        try:
            if self._playwright_available:
                return self._initialize_playwright()
            else:
                return self._initialize_selenium()
        except Exception as e:
            logger.error("Error inicializando sesión: %s", e)
            self.cleanup()
            raise

    def _initialize_playwright(self) -> str:
        """Inicializa sesión usando Playwright."""
        from playwright.sync_api import sync_playwright
        import re

        logger.info("Inicializando sesión con Playwright...")

        # Launch Playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            ignore_https_errors=True,
        )
        self._page = self._context.new_page()

        # Navigate to Votacion index page (not ProcesoBusqueda directly)
        # The index page has the form with SID already in action
        search_url = "http://sil.gobernacion.gob.mx/Busquedas/Votacion/"
        logger.info("Navegando a: %s", search_url)

        self._page.goto(search_url, wait_until="networkidle", timeout=self.timeout)

        # Wait for JavaScript to initialize
        self._page.wait_for_timeout(3000)

        # Try to extract SID after form submission
        # The SID is only created when the form is submitted
        sid = self._try_get_sid_with_form_submit()

        if not sid:
            # Fallback: try to extract from page content or cookies
            sid = self._extract_sid_from_page()

        if not sid:
            sid = self._extract_sid_from_cookies()

        if not sid:
            raise RuntimeError("No se pudo extraer SID del portal")

        return sid

    def _extract_sid_from_page(self) -> Optional[str]:
        """Extrae el SID de la URL actual de la página."""
        import re

        # Check URL for SID
        url = self._page.url
        match = re.search(r"[?&]SID=([A-Za-z0-9]+)", url)
        if match:
            return match.group(1)

        # Check if page has loaded with form action containing SID
        try:
            # Look for form action with SID
            form_action = self._page.eval_on_selector(
                "form[action*='SID']", "el => el.action || el.getAttribute('action')"
            )
            if form_action:
                match = re.search(r"[?&]SID=([A-Za-z0-9]+)", form_action)
                if match:
                    return match.group(1)
        except Exception:
            pass

        # Check page content for SID
        try:
            content = self._page.content()
            match = re.search(r"[?&]SID=([A-Za-z0-9]+)", content)
            if match:
                return match.group(1)
        except Exception:
            pass

        return None

    def _extract_sid_from_cookies(self) -> Optional[str]:
        """Extrae el SID de las cookies del navegador."""
        try:
            cookies = self._context.cookies()
            for cookie in cookies:
                if "sid" in cookie.get("name", "").lower():
                    return cookie.get("value")
        except Exception as e:
            logger.debug("Error extrayendo SID de cookies: %s", e)
        return None

    def _try_get_sid_with_form_submit(self) -> Optional[str]:
        """Intenta enviar el formulario de búsqueda y extraer el SID del resultado.

        El portal SIL crea el SID solo cuando el formulario de búsqueda se envía.
        El formulario tiene target="_blank" así que abre una nueva ventana/tab.

        Returns:
            El SID extraído si tiene éxito, None otherwise.
        """
        import re

        try:
            # Wait for the page to be fully loaded
            self._page.wait_for_load_state("networkidle", timeout=10000)

            # Check if LEGISLATURA select exists
            leg_select = self._page.query_selector("select[name='LEGISLATURA']")
            if not leg_select:
                logger.debug("No se encontró select LEGISLATURA")
                return None

            # Select LXVI (default, most recent with data)
            logger.info("Seleccionando LEGISLATURA LXVI...")
            leg_select.select_option("LXVI")

            # Wait a moment for JS to update
            self._page.wait_for_timeout(500)

            # Find and click the search button
            # The form has an image input (not a submit button)
            buscar_btn = self._page.query_selector("input[type='image']")

            if not buscar_btn:
                logger.debug("No se encontró botón de búsqueda (input image)")
                return None

            # Set up a promise to capture the new window
            new_page_promise = self._context.expect_page(timeout=30000)

            # Click the submit button
            logger.info("Enviando formulario de búsqueda...")
            buscar_btn.click()

            # Wait for the new page to open
            logger.info("Esperando ventana de resultados...")
            new_page = new_page_promise.value

            # Wait for the new page to load
            new_page.wait_for_load_state("networkidle", timeout=30000)

            # Extract SID from the new page's URL
            new_url = new_page.url
            logger.info("Nueva ventana URL: %s", new_url)

            match = re.search(r"[?&]SID=([A-Za-z0-9]+)", new_url)
            if match:
                sid = match.group(1)
                logger.info("SID extraído: %s", sid)

                # Extract all parameters from the results URL
                serial_match = re.search(r"Serial=([A-Za-z0-9]+)", new_url)
                serial = serial_match.group(1) if serial_match else None
                reg_match = re.search(r"Reg=(\d+)", new_url)
                reg = reg_match.group(1) if reg_match else None
                origen_match = re.search(r"Origen=([A-Z]+)", new_url)
                origen = origen_match.group(1) if origen_match else None
                referencia_match = re.search(r"Referencia=(\d+)", new_url)
                referencia = referencia_match.group(1) if referencia_match else None

                logger.info(
                    "Parámetros extraídos - Serial: %s, Reg: %s, Origen: %s, Referencia: %s",
                    serial,
                    reg,
                    origen,
                    referencia,
                )

                # Store session info with all parameters
                now = time.time()
                self._session = SessionInfo(
                    sid=sid,
                    created_at=now,
                    expires_at=now + SESSION_TIMEOUT_SECONDS,
                    serial=serial,
                    reg=reg,
                    origen=origen,
                    referencia=referencia,
                )

                # Store reference to the new page (we'll use it for subsequent requests)
                self._page = new_page

                return sid

            # If no SID in URL, check page content
            content = new_page.content()
            match = re.search(r"[?&]SID=([A-Za-z0-9]+)", content)
            if match:
                sid = match.group(1)
                logger.info("SID extraído del contenido: %s", sid)
                self._page = new_page
                return sid

            logger.debug("No se encontró SID en la nueva ventana")
            new_page.close()
            return None

        except Exception as e:
            logger.debug("Error enviando formulario: %s", e)
            return None

    def _initialize_selenium(self) -> str:
        """Inicializa sesión usando Selenium como fallback."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import re

        logger.info("Inicializando sesión con Selenium...")

        # Setup Chrome options
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={self.user_agent}")
        options.add_argument("--ignore-certificate-errors")

        # Create driver
        self._selenium_driver = webdriver.Chrome(options=options)
        self._selenium_driver.implicitly_wait(10)

        # Navigate to search page
        search_url = "http://sil.gobernacion.gob.mx/Busquedas/Votacion/ProcesoBusquedaAvanzada.php"
        logger.info("Navegando a: %s", search_url)

        self._selenium_driver.get(search_url)

        # Wait for page to load
        WebDriverWait(self._selenium_driver, self.timeout / 1000).until(
            EC.presence_of_element_located((By.TAG_NAME, "form"))
        )

        # Extract SID from URL
        url = self._selenium_driver.current_url
        match = re.search(r"[?&]SID=([A-Za-z0-9]+)", url)
        sid = match.group(1) if match else None

        if not sid:
            # Try from page source
            page_source = self._selenium_driver.page_source
            match = re.search(r"[?&]SID=([A-Za-z0-9]+)", page_source)
            sid = match.group(1) if match else None

        if not sid:
            raise RuntimeError("No se pudo extraer SID con Selenium")

        # Store session info
        now = time.time()
        self._session = SessionInfo(
            sid=sid,
            created_at=now,
            expires_at=now + SESSION_TIMEOUT_SECONDS,
        )

        logger.info("Sesión Selenium inicializada con SID: %s", sid)
        return sid

    def refresh_session(self) -> str:
        """Reinicializa la sesión si expiró o si se solicita refresh.

        Returns:
            El nuevo SID.
        """
        logger.info("Refrescando sesión...")
        self.cleanup()
        return self.initialize()

    def ensure_valid_session(self) -> str:
        """Asegura que hay una sesión válida, creando una si es necesario.

        Returns:
            El SID válido.

        Raises:
            PlaywrightNotAvailableError: Si ningún browser está disponible.
        """
        sid = self.get_sid()
        if sid and not self.is_expired():
            # Check if close to expiring (less than 5 minutes)
            if self.time_remaining() > 5 * 60:
                return sid
            logger.info("Sesión próxima a expirar, refrescando preventivamente")

        return self.initialize()

    def cleanup(self) -> None:
        """Cierra todos los recursos del navegador."""
        # Close Playwright
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        # Close Selenium
        if self._selenium_driver:
            try:
                self._selenium_driver.quit()
            except Exception:
                pass
            self._selenium_driver = None

        self._session = None
        logger.debug("Recursos de sesión limpiados")

    def __enter__(self) -> "SessionManager":
        """Contexto de entrada."""
        return self

    def __exit__(self, *args) -> None:
        """Contexto de salida."""
        self.cleanup()

    def __del__(self) -> None:
        """Destructor."""
        self.cleanup()


def create_session_manager(
    headless: bool = PLAYWRIGHT_HEADLESS,
    timeout: int = PLAYWRIGHT_TIMEOUT_MS,
) -> SessionManager:
    """Factory function para crear un SessionManager.

    Args:
        headless: Si el navegador debe correr en modo headless.
        timeout: Timeout en ms para operaciones del navegador.

    Returns:
        Una instancia de SessionManager (o subclass si hay error).

    Raises:
        PlaywrightNotAvailableError: Si ningún browser driver está disponible.
    """
    return SessionManager(headless=headless, timeout=timeout)
