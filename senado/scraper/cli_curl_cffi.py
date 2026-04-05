"""
cli_curl_cffi.py — CLI para scraping de votaciones nominales del Senado.

Portal LXVI: https://www.senado.gob.mx/66/votacion/{id}
AJAX endpoint: /66/app/votaciones/functions/viewTableVot.php
Rango de IDs: 1 a 5070+ (LX-LXVI)

Escribe en el schema Popolo-Graph de congreso.db.

Uso:
    python -m senado.scraper --range 1 5070
    python -m senado.scraper --test-id 1
    python -m senado.scraper --test-id 5065
    python -m senado.scraper --init-schema
"""

import argparse
import hashlib
import logging
import pickle
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from curl_cffi.requests import Session

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Paths y configuración
# =============================================================================

PROJECT_DIR: Path = Path(__file__).resolve().parent.parent.parent
DB_PATH: Path = PROJECT_DIR / "db" / "congreso.db"
CACHE_DIR: Path = PROJECT_DIR / "cache" / "senado"
COOKIE_PATH: Path = CACHE_DIR / "senado_cookies.pkl"


# =============================================================================
# Configuración anti-WAF
# =============================================================================

WAF_MARKERS = [
    "incident_id",
    "waf block",
    "forbidden",
    "access denied",
]

WAF_MAX_SIZE = 5 * 1024  # 5KB — respuestas menores son sospechosas

MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # segundos


# =============================================================================
# URLs del portal LXVI
# =============================================================================

LXVI_VOTACION_URL_TEMPLATE = "https://www.senado.gob.mx/66/votacion/{id}"

LXVI_AJAX_URL = "https://www.senado.gob.mx/66/app/votaciones/functions/viewTableVot.php"

# Legacy URL (mantenida para referencia/fallback)
LEGACY_VOTACION_URL_TEMPLATE = (
    "https://www.senado.gob.mx/informacion/votaciones/vota/{id}"
)


# =============================================================================
# Imports del scraper del Senado
# =============================================================================

from .parsers.lxvi_portal import parse_lxvi_votacion
from .models import SenCountPorPartido, SenVotacionDetail, SenVotoNominal


# =============================================================================
# Imports del loader de congreso.db
# =============================================================================

from .congreso_loader import (
    CongresoLoader,
    CongresoVotacionRecord,
    CongresoVotoRecord,
)


# =============================================================================
# Helpers de fecha
# =============================================================================


def _parse_fecha_iso(fecha: str) -> str:
    """Convierte fecha de formato dd/mm/yyyy a yyyy-mm-dd.

    El portal del Senado usa formato dd/mm/yyyy pero la BD espera ISO.

    Args:
        fecha: Fecha en formato dd/mm/yyyy (ej: "31/03/2026").

    Returns:
        Fecha en formato yyyy-mm-dd (ej: "2026-03-31").
        Retorna cadena vacía si el formato no es reconocido.
    """
    import datetime

    if not fecha:
        return ""

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            dt = datetime.datetime.strptime(fecha, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning(f"Formato de fecha no reconocido: '{fecha}', usando cadena vacía")
    return ""


# =============================================================================
# Cliente HTTP para el portal LXVI
# =============================================================================


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
        """Persiste cookies de la sesión actual a disco.

        Extrae cookies como dict simple (no pickle de objeto CookieJar)
        para evitar problemas de serialización con curl_cffi.
        """
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

        El servidor declara UTF-8 en meta charset pero algunos CDN
        envían headers con charset=ISO-8859-1. Probar UTF-8 primero.

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


# =============================================================================
# Pipeline principal
# =============================================================================


class SenadoCongresoPipeline:
    """Pipeline que scraper votaciones del Senado (portal LXVI) y escribe en congreso.db.

    Transforma los datos del formato interno del scraper del Senado
    (SenVotacionDetail, SenVotoNominal) al formato CongresoVotacionRecord
    antes de insertar en la BD via CongresoLoader.
    """

    # ID de la organización del Senado en la BD Popolo-Graph
    SENADO_ORG_ID = "O09"  # "Senado de la República"

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = 2.0,
        db_path: Optional[str] = None,
    ):
        """Inicializa el pipeline.

        Args:
            use_cache: Si True, usa caché file-based para los requests.
            delay: Delay mínimo entre requests en segundos.
            db_path: Path a la BD. Si None, usa DB_PATH por defecto.
        """
        self.client = SenadoLXVIClient(use_cache=use_cache, delay=delay)
        self.db_path = db_path or str(DB_PATH)
        self.loader = CongresoLoader(db_path=self.db_path)

    def scrape_one(self, votacion_id: int) -> dict:
        """Procesa un solo ID para testing.

        Args:
            votacion_id: ID de la votación en el portal del Senado.

        Returns:
            Dict con estadísticas del procesamiento.
        """
        logger.info(
            f"Scrapeando votacion {votacion_id}: {LXVI_VOTACION_URL_TEMPLATE.format(id=votacion_id)}"
        )

        try:
            # 1. Fetch HTML (página + AJAX)
            page_html, ajax_html = self.client.get_votacion(votacion_id)

            if not page_html or len(page_html) < 100:
                logger.warning(f"HTML vacío o muy corto para ID {votacion_id}")
                return {"status": "empty_html", "votacion_id": votacion_id}

            if not ajax_html or len(ajax_html) < 50:
                logger.warning(f"AJAX vacío o muy corto para ID {votacion_id}")
                return {"status": "empty_ajax", "votacion_id": votacion_id}

            # 2. Parsear
            detail, votos = parse_lxvi_votacion(page_html, ajax_html, votacion_id)
            logger.info(
                f"  Legislature: {detail.periodo}, "
                f"Fecha: {detail.fecha}, "
                f"Votos: pro={detail.pro_count}, contra={detail.contra_count}, "
                f"abst={detail.abstention_count}, "
                f"senadores={len(votos)}, "
                f"partidos={len(detail.counts_por_partido)}"
            )

            # 3. Transformar a formato CongresoVotacionRecord
            votacion_record = self._transform_to_congreso_record(
                votacion_id, detail, votos
            )

            # 4. Upsert con el loader
            stats = self.loader.upsert_votacion(votacion_record)
            stats["status"] = stats.get("status", "success")
            stats["votacion_id"] = votacion_id

            if stats["status"] == "already_exists":
                logger.info(f"  ⊘ Ya existe: VE={stats['votacion_id']}")
                return stats

            logger.info(
                f"  ✓ Insertado: VE={stats['votacion_id']}, "
                f"votos={stats['votos']}, "
                f"personas_nuevas={stats['personas_nuevas']}"
            )
            return stats

        except Exception as e:
            logger.error(f"Error procesando votacion {votacion_id}: {e}")
            return {"status": "error", "votacion_id": votacion_id, "error": str(e)}

    def scrape_range(self, start: int, end: int) -> dict:
        """Itera IDs de start a end, procesando cada votación.

        Args:
            start: ID inicial (inclusive).
            end: ID final (inclusive).

        Returns:
            Dict con estadísticas agregadas del procesamiento.
        """
        total = end - start + 1
        logger.info(f"Iniciando scrapeo de range [{start}, {end}] ({total} IDs)")

        stats_agg = {
            "total": total,
            "exitosos": 0,
            "errores": 0,
            "ya_existen": 0,
            "votos_insertados": 0,
            "personas_nuevas": 0,
        }

        errores = []

        try:
            for i, votacion_id in enumerate(range(start, end + 1), start=1):
                if i % 100 == 0 or i == 1 or i == total:
                    logger.info(f"Procesando {votacion_id} ({i}/{total})")

                result = self.scrape_one(votacion_id)

                if result.get("status") == "already_exists":
                    stats_agg["ya_existen"] += 1
                elif result.get("status") == "success":
                    stats_agg["exitosos"] += 1
                    stats_agg["votos_insertados"] += result.get("votos", 0)
                    stats_agg["personas_nuevas"] += result.get("personas_nuevas", 0)
                elif result.get("status") == "error":
                    error_msg = result.get("error", "")
                    stats_agg["errores"] += 1
                    errores.append(result)
                    if len(errores) <= 5:
                        logger.error(f"  ✗ Error ID {votacion_id}: {error_msg}")

        finally:
            # Cerrar sesión al final del batch
            self.client.close()

        logger.info(
            f"Completado: {stats_agg['exitosos']} exitosos, "
            f"{stats_agg['ya_existen']} ya existían, "
            f"{stats_agg['errores']} errores"
        )

        return stats_agg

    def _transform_to_congreso_record(
        self,
        votacion_id: int,
        detail: SenVotacionDetail,
        votos: list[SenVotoNominal],
    ) -> CongresoVotacionRecord:
        """Transforma datos del parser LXVI al formato CongresoVotacionRecord.

        Args:
            votacion_id: ID de la votación en el portal.
            detail: Datos parseados de la votación.
            votos: Lista de votos nominales.

        Returns:
            CongresoVotacionRecord listo para insertar en congreso.db.
        """
        # --- Fecha ---
        fecha_iso = _parse_fecha_iso(detail.fecha)

        # --- Convertir votos ---
        votos_records: list[CongresoVotoRecord] = []
        personas_nuevas: list[dict] = []
        membresias_nuevas: list[dict] = []

        # Track de nombres ya procesados
        nombres_procesados: set[str] = set()

        for voto in votos:
            nombre = voto.nombre.strip()
            grupo = voto.grupo_parlamentario.strip()

            # Solo agregar personas y membresías nuevas (una vez por persona)
            if nombre and nombre not in nombres_procesados:
                nombres_procesados.add(nombre)

                # Infierir género del nombre
                genero = self._inferir_genero(nombre)

                personas_nuevas.append(
                    {
                        "nombre": nombre,
                        "genero": genero,
                    }
                )

                # Membresía solo si hay grupo
                if grupo:
                    membresias_nuevas.append(
                        {
                            "persona_id": nombre,  # El loader resolverá por nombre
                            "organizacion_id": grupo,
                            "rol": "senador",
                            "start_date": fecha_iso,
                        }
                    )

            votos_records.append(
                CongresoVotoRecord(
                    nombre=nombre,
                    grupo_parlamentario=grupo,
                    voto=voto.voto,  # Raw: PRO/CONTRA/ABSTENCIÓN
                )
            )

        # --- Build counts_por_partido ---
        counts_por_partido = [
            {
                "partido": cp.partido,
                "a_favor": cp.a_favor,
                "en_contra": cp.en_contra,
                "abstencion": cp.abstencion,
            }
            for cp in detail.counts_por_partido
        ]

        return CongresoVotacionRecord(
            senado_id=votacion_id,
            legislature=detail.periodo or "",  # LX, LXI, etc.
            fecha_iso=fecha_iso,
            descripcion=detail.descripcion,
            pro_count=detail.pro_count,
            contra_count=detail.contra_count,
            abstention_count=detail.abstention_count,
            votos=votos_records,
            voto_personas_nuevas=personas_nuevas,
            voto_membresias_nuevas=membresias_nuevas,
            counts_por_partido=counts_por_partido,
        )

    @staticmethod
    def _inferir_genero(nombre: str) -> Optional[str]:
        """Infiere el género de un legislador a partir del nombre.

        Args:
            nombre: Nombre completo del legislador.

        Returns:
            "M", "F" o ``None``.
        """
        if not nombre:
            return None

        # Nombres femeninos comunes en México
        nombres_femeninos = {
            "maría",
            "ana",
            "patricia",
            "leticia",
            "verónica",
            "gabriela",
            "cristina",
            "mónica",
            "silvia",
            "luz",
            "rosa",
            "carmen",
            "margarita",
            "elena",
            "sara",
            "laura",
            "andrea",
            "valentina",
            "sofia",
            "diana",
            "cecilia",
            "beatriz",
            "isabel",
            "raquel",
            "susana",
            "minerva",
            "nora",
            "claudia",
            "guadalupe",
            "alejandra",
            "nayeli",
            "antonia",
            "mariana",
            "irene",
            "adela",
            "ramona",
        }

        # Strip prefijo "Sen. " si existe
        nombre_limpio = nombre.replace("Sen.", "").replace("sen.", "").strip()
        nombre_lower = nombre_limpio.lower()

        partes = nombre_lower.replace(",", "").split()
        for parte in partes:
            if parte in nombres_femeninos:
                return "F"

        return None


# =============================================================================
# CLI principal
# =============================================================================


def main() -> None:
    """Entry point del CLI."""
    parser = argparse.ArgumentParser(
        description="Scraper del Senado (LX-LXVI) → congreso.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m senado.scraper --range 1 5070
  python -m senado.scraper --test-id 1
  python -m senado.scraper --test-id 5065
  python -m senado.scraper --init-schema
        """,
    )
    parser.add_argument(
        "--range",
        type=int,
        nargs=2,
        metavar=("START", "END"),
        help="Rango de IDs a procesar (inicio y fin inclusivos)",
    )
    parser.add_argument(
        "--test-id",
        type=int,
        help="Procesar un solo ID para testing",
    )
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Inicializar schema de congreso.db si no existe",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Desactivar caché de requests HTTP",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay entre requests en segundos (default: 2.0)",
    )

    args = parser.parse_args()

    # Validar argumentos
    if not args.range and not args.test_id and not args.init_schema:
        parser.error("Se requiere --range, --test-id o --init-schema")

    if args.range and args.range[0] > args.range[1]:
        parser.error(f"Rango inválido: start={args.range[0]} > end={args.range[1]}")

    # Inicializar pipeline
    use_cache = not args.no_cache
    pipeline = SenadoCongresoPipeline(use_cache=use_cache, delay=args.delay)

    # Ejecutar acción
    if args.init_schema:
        logger.info("Inicializando schema de congreso.db...")
        pipeline.loader.init_schema()
        print("Schema inicializado correctamente.")
        return

    if args.test_id:
        logger.info(f"Testeando ID: {args.test_id}")
        result = pipeline.scrape_one(args.test_id)
        print(f"Resultado: {result}")
        pipeline.client.close()
        return

    if args.range:
        start, end = args.range
        logger.info(f"Iniciando scrapeo de [{start}, {end}]...")
        result = pipeline.scrape_range(start, end)
        print(f"\nResumen:")
        print(f"  Total IDs:        {result['total']}")
        print(f"  Exitosos:         {result['exitosos']}")
        print(f"  Ya existían:      {result['ya_existen']}")
        print(f"  Errores:          {result['errores']}")
        print(f"  Votos insertados: {result['votos_insertados']}")
        print(f"  Personas nuevas:  {result['personas_nuevas']}")


if __name__ == "__main__":
    main()
