"""
sil_pipeline.py — Pipeline principal del scraper SIL.

Orquesta el flujo completo de 4 niveles:
1. Legislaturas (LVI-LXXVI)
2. Resultados de búsqueda (paginados)
3. Detalle de votacion (metadata + totals)
4. Votos por legislador (por grupo F/C/A/N)

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
    VOTO_MAP,
    PLAYWRIGHT_HEADLESS,
    PLAYWRIGHT_TIMEOUT,
    SESSION_TIMEOUT,
)
from scraper_sil.loaders.sil_loader import SILLoader
from scraper_sil.models import (
    SILBusquedaParams,
    SILVotacionIndex,
)
from scraper_sil.parsers.busqueda import build_search_params
from scraper_sil.parsers.detalle import parse_detalle_votacion
from scraper_sil.parsers.resultados import parse_resultados, parse_paginacion
from scraper_sil.parsers.votos import parse_votos_completos

logger = logging.getLogger(__name__)


class SILPipeline:
    """Pipeline principal para scraping del SIL.

    Coordina cliente HTTP, parsers, loader y maneja el flujo completo.

    Soporta dos modos de sesión:
    - use_playwright=True: Usa Playwright/Selenium para inicializar sesión JS
    - use_playwright=False: Extrae SID del HTML (modo tradicional)
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY,
        db_path: Optional[str] = None,
        use_playwright: bool = False,
        session_timeout: Optional[int] = None,
    ):
        """Inicializa el pipeline.

        Args:
            use_cache: Si True, usa caché para requests.
            delay: Delay entre requests en segundos.
            db_path: Path a la BD (None = default).
            use_playwright: Si True, usa Playwright/Selenium para sesión JS.
            session_timeout: Timeout de sesión en segundos (default: 25 min).
        """
        self.client = SILClient(use_cache=use_cache, delay=delay)
        self.loader = SILLoader(db_path=db_path)
        self.use_playwright = use_playwright
        self.session_timeout = session_timeout or SESSION_TIMEOUT
        self._session_manager = None

        # Lazy import para evitar dependencia obligatoria
        if self.use_playwright:
            self._init_session_manager()

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

    def run_full(
        self,
        legislature: str = "LXXVI",
        tipo_asunto: Optional[list[str]] = None,
        resultado: Optional[str] = None,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        limit_pages: Optional[int] = None,
        limit_per_page: int = 50,
        resume: bool = True,
    ) -> dict:
        """Ejecuta el pipeline completo de scraping.

        Args:
            legislature: Legislature a scrapear (LVI-LXXVI).
            tipo_asunto: Lista de tipos de asunto a filtrar.
            resultado: Filtrar por resultado (A=aprobado, D=desechado).
            fecha_inicio: Fecha inicial (dd/mm/yyyy).
            fecha_fin: Fecha final (dd/mm/yyyy).
            limit_pages: Límite de páginas de resultados (None = todas).
            limit_per_page: Resultados por página.
            resume: Si True, solo scrapea votaciones pendientes.

        Returns:
            Dict con estadísticas del scraping.
        """
        stats = {
            "legislature": legislature,
            "pages_scraped": 0,
            "votaciones_found": 0,
            "votaciones_processed": 0,
            "votaciones_failed": 0,
            "errors": [],
        }

        try:
            # 1. Obtener página de búsqueda y SID
            logger.info(f"Iniciando pipeline SIL para {legislature}")

            # Usar Playwright si está habilitado, o fallback a httpx
            if not self._ensure_session():
                raise RuntimeError("No se pudo obtener SID del portal")

            # 2. Enviar formulario de búsqueda
            params = SILBusquedaParams(
                legislature=legislature,
                tipo_asunto=tipo_asunto or [],
                resultado=resultado,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                paginas=limit_per_page,
            )

            form_options = {"legislaturas": LEGISLATURAS}
            session_info = (
                self._session_manager.session
                if self.use_playwright and self._session_manager
                else None
            )
            post_params = build_search_params(params, form_options, session_info)

            html_resultados = self.client.search_votaciones(post_params)

            # 3. Parsear primera página de resultados
            votaciones, total = parse_resultados(html_resultados)
            pag_info = parse_paginacion(html_resultados)

            stats["votaciones_found"] = total or len(votaciones)
            logger.info(
                f"Encontradas {stats['votaciones_found']} votaciones "
                f"(página 1/{pag_info['total_pages']})"
            )

            # 4. Procesar cada votación del índice
            if resume:
                # Obtener votaciones pendientes
                pending = self.loader.get_pending_votaciones(limit=1000)
                pending_keys = {(v[0], v[1]) for v in pending}
                votaciones = [
                    v
                    for v in votaciones
                    if (v.clave_asunto, v.clave_tramite) in pending_keys
                ]
                logger.info(f"Reanudando: {len(votaciones)} votaciones pendientes")

            for i, votacion in enumerate(votaciones):
                try:
                    self._process_votacion(votacion)
                    stats["votaciones_processed"] += 1

                    if (i + 1) % 10 == 0:
                        logger.info(f"Procesadas {i + 1}/{len(votaciones)} votaciones")

                except Exception as e:
                    logger.error(f"Error procesando {votacion.clave_asunto}: {e}")
                    stats["votaciones_failed"] += 1
                    stats["errors"].append(
                        {
                            "clave": f"{votacion.clave_asunto}/{votacion.clave_tramite}",
                            "error": str(e),
                        }
                    )

            stats["pages_scraped"] = 1

            # 5. Procesar páginas adicionales si hay paginación
            if limit_pages:
                max_pages = min(limit_pages, pag_info["total_pages"])
            else:
                max_pages = pag_info["total_pages"]

            for page in range(2, max_pages + 1):
                try:
                    html = self.client.get_resultados(page=page)
                    page_votaciones, _ = parse_resultados(html)
                    stats["pages_scraped"] += 1

                    for votacion in page_votaciones:
                        if resume:
                            status = self.loader.get_status(
                                votacion.clave_asunto,
                                votacion.clave_tramite,
                            )
                            if status == "completed":
                                continue

                        self._process_votacion(votacion)
                        stats["votaciones_processed"] += 1

                except Exception as e:
                    logger.error(f"Error en página {page}: {e}")
                    stats["errors"].append(
                        {
                            "page": page,
                            "error": str(e),
                        }
                    )

        except Exception as e:
            logger.error(f"Error en pipeline: {e}")
            stats["errors"].append({"pipeline_error": str(e)})

        finally:
            self.client.close()
            if self._session_manager:
                self._session_manager.cleanup()

        logger.info(
            f"Pipeline completado: {stats['votaciones_processed']} procesadas, "
            f"{stats['votaciones_failed']} fallidas"
        )

        return stats

    def _process_votacion(self, votacion: SILVotacionIndex) -> None:
        """Procesa una votación completa (índice + detalle + votos).

        Args:
            votacion: Datos del índice de la votación.
        """
        clave_asunto = votacion.clave_asunto
        clave_tramite = votacion.clave_tramite

        # Marcar como en proceso
        self.loader.update_status(clave_asunto, clave_tramite, "processing")

        # Insertar/actualizar índice
        self.loader.upsert_votacion_index(votacion, self.client.sid or "")

        # Obtener detalle
        html_detalle = self.client.get_detalle_votacion(clave_asunto, clave_tramite)
        detalle = parse_detalle_votacion(html_detalle, clave_asunto, clave_tramite)

        if detalle:
            # Obtener votos de todos los grupos
            votos = self._scrape_votos(clave_asunto, clave_tramite)

            # Guardar detalle y votos
            self.loader.upsert_votacion_detail(
                clave_asunto, clave_tramite, detalle, votos
            )
        else:
            # Solo guardar el índice sin detalle
            self.loader.update_status(clave_asunto, clave_tramite, "completed")

    def _scrape_votos(
        self,
        clave_asunto: str,
        clave_tramite: str,
    ):
        """Obtiene los votos completos de una votación.

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.

        Returns:
            SILVotosCompletos o None si falla.
        """
        try:
            # Obtener cada grupo de votos
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

    def run_votacion(
        self,
        clave_asunto: str,
        clave_tramite: str = "1",
    ) -> dict:
        """Scrapea una votación específica por su clave.

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.

        Returns:
            Dict con resultado del scraping.
        """
        result = {
            "success": False,
            "clave_asunto": clave_asunto,
            "clave_tramite": clave_tramite,
            "error": None,
        }

        try:
            # Asegurar SID (usa Playwright si está habilitado)
            self._ensure_session()

            # Obtener detalle
            html_detalle = self.client.get_detalle_votacion(clave_asunto, clave_tramite)
            detalle = parse_detalle_votacion(html_detalle, clave_asunto, clave_tramite)

            if not detalle:
                result["error"] = "No se pudo parsear el detalle"
                return result

            # Obtener votos
            votos = self._scrape_votos(clave_asunto, clave_tramite)

            # Guardar
            load_result = self.loader.upsert_votacion_detail(
                clave_asunto, clave_tramite, detalle, votos
            )

            result["success"] = load_result.success
            result["vote_event_id"] = load_result.vote_event_id
            result["votos"] = load_result.votos_insertados

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error en run_votacion {clave_asunto}: {e}")

        finally:
            self.client.close()

        return result
