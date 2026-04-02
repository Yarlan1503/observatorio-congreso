"""
legislature_pipeline.py — Pipeline por legislature para scraping incremental.

Maneja el scraping de una legislature específica con soporte para
reanudación, checkpoints y estadísticas.

Soporta dos modos de inicialización de sesión:
- Modo httpx puro: Extrae SID del HTML (puede fallar si JS es requerido)
- Modo Playwright: Usa JavaScript para inicializar sesión (más robusto)
"""

import logging
from typing import Optional

from scraper_sil.client import SILClient
from scraper_sil.config import (
    LEGISLATURAS,
    REQUEST_DELAY,
    PLAYWRIGHT_HEADLESS,
    PLAYWRIGHT_TIMEOUT,
    SESSION_TIMEOUT,
)
from scraper_sil.loaders.sil_loader import SILLoader
from scraper_sil.models import SILVotacionIndex
from scraper_sil.parsers.busqueda import build_search_params
from scraper_sil.parsers.detalle import parse_detalle_votacion
from scraper_sil.parsers.resultados import parse_resultados

logger = logging.getLogger(__name__)


class LegislaturePipeline:
    """Pipeline para scraping de una legislature específica.

    Provee funcionalidades de:
    - Scraping incremental con checkpoints
    - Resume desde el último punto de fallo
    - Estadísticas por legislature
    - Manejo de errores robusto
    - Soporte para Playwright/Selenium (opcional)
    """

    def __init__(
        self,
        legislature: str,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY,
        db_path: Optional[str] = None,
        use_playwright: bool = False,
        session_timeout: Optional[int] = None,
    ):
        """Inicializa el pipeline.

        Args:
            legislature: Legislature a scrapear (ej: "LXXVI").
            use_cache: Si True, usa caché para requests.
            delay: Delay entre requests en segundos.
            db_path: Path a la BD (None = default).
            use_playwright: Si True, usa Playwright/Selenium para sesión JS.
            session_timeout: Timeout de sesión en segundos (default: 25 min).
        """
        self.legislature = legislature.upper()
        if self.legislature not in LEGISLATURAS:
            raise ValueError(
                f"Legislatura {legislature} no válida. Usar una de: {LEGISLATURAS}"
            )

        self.client = SILClient(use_cache=use_cache, delay=delay)
        self.loader = SILLoader(db_path=db_path)
        self.use_playwright = use_playwright
        self.session_timeout = session_timeout or SESSION_TIMEOUT
        self._session_manager = None

        # Lazy import para evitar dependencia obligatoria
        if self.use_playwright:
            self._init_session_manager()

        # Estado del checkpoint
        self._checkpoint_page: int = 1
        self._checkpoint_votacion_index: int = 0

    def _init_session_manager(self) -> None:
        """Inicializa el SessionManager de Playwright/Selenium."""
        try:
            from scraper_sil.session_manager import SessionManager

            self._session_manager = SessionManager(
                headless=PLAYWRIGHT_HEADLESS,
                timeout=PLAYWRIGHT_TIMEOUT,
            )
            logger.info("SessionManager de Playwright inicializado")
        except ImportError as e:
            logger.warning(
                "Playwright no está disponible: %s. Usando modo httpx puro para SID.", e
            )
            self.use_playwright = False
            self._session_manager = None

    def _ensure_session(self) -> bool:
        """Asegura que hay una sesión válida.

        Returns:
            True si se obtuvo SID válido.
        """
        if self.use_playwright and self._session_manager:
            try:
                sid = self._session_manager.ensure_valid_session()
                if sid:
                    self.client.set_sid(sid)
                    logger.info("SID obtenido de SessionManager: %s", sid)
                    return True
            except Exception as e:
                logger.warning("Error con SessionManager, cayendo a modo httpx: %s", e)
                self.use_playwright = False

        # Fallback: obtener SID del HTML
        html, sid = self.client.get_search_page()
        if sid:
            logger.info("SID obtenido de HTML: %s", sid)
            return True

        logger.warning("No se pudo obtener SID")
        return False

    def _check_session_expiry(self) -> None:
        """Verifica si la sesión está por expirar y la renueva si es necesario."""
        if self.use_playwright and self._session_manager:
            if self._session_manager.is_expired():
                logger.info("Sesión expirada, renovando con Playwright...")
                try:
                    sid = self._session_manager.refresh_session()
                    self.client.set_sid(sid)
                except Exception as e:
                    logger.error("Error renovando sesión: %s", e)

    def run(
        self,
        limit_pages: Optional[int] = None,
        limit_per_page: int = 50,
        resume: bool = True,
        scrape_votes: bool = True,
    ) -> dict:
        """Ejecuta el pipeline para la legislature.

        Args:
            limit_pages: Límite de páginas (None = todas).
            limit_per_page: Resultados por página.
            resume: Si True, reanuda desde el último checkpoint.
            scrape_votes: Si True, obtiene también los votos individuales.

        Returns:
            Dict con estadísticas del scraping.
        """
        stats = {
            "legislature": self.legislature,
            "started": True,
            "pages_scraped": 0,
            "votaciones_found": 0,
            "votaciones_processed": 0,
            "votaciones_failed": 0,
            "errors": [],
        }

        try:
            # Obtener SID (usa Playwright si está habilitado)
            if not self._ensure_session():
                raise RuntimeError("No se pudo obtener SID")

            # Enviar búsqueda
            from scraper_sil.models import SILBusquedaParams

            params = SILBusquedaParams(
                legislature=self.legislature,
                paginas=limit_per_page,
            )
            from scraper_sil.parsers.busqueda import build_search_params

            post_params = build_search_params(params)

            html = self.client.search_votaciones(post_params)
            votaciones, total = parse_resultados(html)

            stats["votaciones_found"] = total or len(votaciones)
            logger.info(
                f"[{self.legislature}] {stats['votaciones_found']} votaciones encontradas"
            )

            # Filtrar por resume
            if resume:
                votaciones = self._filter_pending(votaciones)
                logger.info(f"[{self.legislature}] {len(votaciones)} pendientes")

            # Procesar votaciones
            for i, votacion in enumerate(votaciones):
                try:
                    self._process_votacion(votacion, scrape_votes=scrape_votes)
                    stats["votaciones_processed"] += 1

                    if (i + 1) % 10 == 0:
                        logger.info(
                            f"[{self.legislature}] Progreso: {i + 1}/{len(votaciones)}"
                        )

                except Exception as e:
                    logger.error(
                        f"[{self.legislature}] Error en {votacion.clave_asunto}: {e}"
                    )
                    stats["votaciones_failed"] += 1
                    stats["errors"].append(
                        {
                            "clave": f"{votacion.clave_asunto}/{votacion.clave_tramite}",
                            "error": str(e),
                        }
                    )

            stats["pages_scraped"] = 1

        except Exception as e:
            logger.error(f"[{self.legislature}] Error en pipeline: {e}")
            stats["errors"].append({"pipeline_error": str(e)})

        finally:
            self.client.close()
            if self._session_manager:
                self._session_manager.cleanup()

        logger.info(
            f"[{self.legislature}] Completado: "
            f"{stats['votaciones_processed']} procesadas, "
            f"{stats['votaciones_failed']} fallidas"
        )

        return stats

    def _filter_pending(
        self, votaciones: list[SILVotacionIndex]
    ) -> list[SILVotacionIndex]:
        """Filtra votaciones para solo procesar las pendientes.

        Args:
            votaciones: Lista de votaciones.

        Returns:
            Lista filtrada de votaciones pendientes.
        """
        pending = []
        for v in votaciones:
            status = self.loader.get_status(v.clave_asunto, v.clave_tramite)
            if status != "completed":
                pending.append(v)
        return pending

    def _process_votacion(
        self,
        votacion: SILVotacionIndex,
        scrape_votes: bool = True,
    ) -> None:
        """Procesa una votación individual.

        Args:
            votacion: Datos de la votación.
            scrape_votes: Si True, obtiene los votos individuales.
        """
        clave_asunto = votacion.clave_asunto
        clave_tramite = votacion.clave_tramite

        # Marcar como processing
        self.loader.update_status(clave_asunto, clave_tramite, "processing")

        # Upsert índice
        self.loader.upsert_votacion_index(votacion, self.client.sid or "")

        # Obtener y upsert detalle
        html = self.client.get_detalle_votacion(clave_asunto, clave_tramite)
        detalle = parse_detalle_votacion(html, clave_asunto, clave_tramite)

        if detalle and scrape_votes:
            # Obtener votos
            votos = self._scrape_votos(clave_asunto, clave_tramite)
            self.loader.upsert_votacion_detail(
                clave_asunto, clave_tramite, detalle, votos
            )
        elif detalle:
            self.loader.upsert_votacion_detail(clave_asunto, clave_tramite, detalle)
        else:
            self.loader.update_status(clave_asunto, clave_tramite, "failed")

    def _scrape_votos(self, clave_asunto: str, clave_tramite: str):
        """Obtiene los votos de una votación.

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.

        Returns:
            SILVotosCompletos o None si falla.
        """
        try:
            from scraper_sil.parsers.votos import parse_votos_completos

            html_f = self.client.get_votos_legislador(clave_asunto, clave_tramite, "F")
            html_c = self.client.get_votos_legislador(clave_asunto, clave_tramite, "C")
            html_a = self.client.get_votos_legislador(clave_asunto, clave_tramite, "A")
            html_n = self.client.get_votos_legislador(clave_asunto, clave_tramite, "N")

            return parse_votos_completos(
                html_f,
                html_c,
                html_a,
                html_n,
                clave_asunto,
                clave_tramite,
            )
        except Exception as e:
            logger.warning(f"Error scraping votos {clave_asunto}: {e}")
            return None

    def get_stats(self) -> dict:
        """Obtiene estadísticas de la legislature en la BD.

        Returns:
            Dict con estadísticas.
        """
        conn = self.loader._get_conn()
        try:
            stats = conn.execute(
                """SELECT scrape_status, COUNT(*) as cnt
                   FROM sen_vote_event
                   WHERE sil_legislatura = ?
                   GROUP BY scrape_status""",
                (self.legislature,),
            ).fetchall()

            return {row[0] or "null": row[1] for row in stats}
        finally:
            conn.close()
