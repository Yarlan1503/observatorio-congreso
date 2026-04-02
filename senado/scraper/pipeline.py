"""pipeline.py — Orquestador del scraper del Senado con CLI.

Coordina el flujo completo:
    client → parsers → transformers → loader → SQLite

Flujo de 2 niveles:
    1. Índice de fechas (/66/votaciones/)
    2. Página de fecha (/66/votaciones/YYYY_MM_DD)
    3. Detalle de votación (/66/votacion/{id})
    4. Tabla AJAX de votos (POST)

Uso:
    python -m scraper.senado.pipeline --limit 5
    python -m scraper.senado.pipeline --votacion-id 4712
    python -m scraper.senado.pipeline --stats
    python -m scraper.senado.pipeline --init-db
    python -m scraper.senado.pipeline --no-cache
"""

import logging
import sys
import argparse
import sqlite3
from typing import Optional
from urllib.parse import urljoin

from .config import (
    SENADO_VOTACIONES_URL,
    SENADO_VOTACION_URL_TEMPLATE,
    SENADO_AJAX_TABLE_URL,
    SENADO_DB_PATH,
    SENADO_BASE_URL,
    REQUEST_DELAY,
)
from .client import SenadoClient
from .parsers import (
    parse_votaciones_index,
    parse_votaciones_fecha,
    parse_votacion_detalle,
    parse_ajax_table,
)
from .transformers import transformar_votacion
from .congreso_loader import CongresoLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class SenadoPipeline:
    """Orquesta el scraping completo de votaciones del Senado.

    Flujo:
    1. Obtener índice de votaciones (parse_senado_votaciones_indice)
    2. Para cada votación:
       a. Obtener detalle (parse_senado_votacion)
       b. Obtener tabla AJAX de votos individuales (parse_senado_votos)
       c. Transformar datos
       d. Insertar en SQLite
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY,
    ):
        """Inicializa el pipeline.

        Args:
            use_cache: Si ``True``, usa caché file-based para HTML.
            delay: Segundos entre requests HTTP.
        """
        self.client = SenadoClient(use_cache=use_cache, delay=delay)
        self.loader = CongresoLoader()

    def scrape_all(self, limit: Optional[int] = None) -> list[dict]:
        """Scrapea todas las votaciones disponibles, respetando el límite.

        Flujo de 2 niveles:
        1. Obtener índice de fechas (/66/votaciones/)
        2. Para cada fecha, obtener página de votaciones
        3. Para cada votación: detalle + AJAX + insertar

        Args:
            limit: Máximo número de votaciones a procesar
                (``None`` = todas). Se cuenta por votaciones, no por fechas.

        Returns:
            Lista de dicts con estadísticas de cada votación procesada.
        """
        results: list[dict] = []
        votaciones_procesadas = 0

        # NIVEL 1: Obtener índice de fechas
        logger.info(f"Obteniendo índice de fechas: {SENADO_VOTACIONES_URL}")
        try:
            html_index = self.client.get_html(SENADO_VOTACIONES_URL)
        except Exception as e:
            logger.error(f"Error obteniendo índice de fechas: {e}")
            return results

        fechas = parse_votaciones_index(html_index)
        logger.info(f"Encontradas {len(fechas)} fechas en el índice")

        if not fechas:
            logger.warning("No se encontraron fechas en el índice")
            return results

        # Acumular votaciones de todas las fechas
        all_votaciones: list = []
        total_fechas = len(fechas)

        # Procesar fechas en orden reversed (más recientes primero)
        for i_fecha, fecha_rec in enumerate(reversed(fechas), 1):
            if limit and len(all_votaciones) >= limit:
                break

            fecha_url = urljoin(SENADO_BASE_URL, fecha_rec.fecha_url)
            logger.info(
                f"[{i_fecha}/{total_fechas}] Procesando fecha: {fecha_rec.fecha_label}"
            )

            try:
                html_fecha = self.client.get_html(fecha_url)
                votaciones_fecha = parse_votaciones_fecha(
                    html_fecha, fecha_rec.fecha_label
                )
                all_votaciones.extend(votaciones_fecha)
                logger.info(f"  → {len(votaciones_fecha)} votaciones encontradas")
            except Exception as e:
                logger.warning(f"  → Error procesando {fecha_rec.fecha_label}: {e}")
                continue

        logger.info(f"Total votaciones acumuladas: {len(all_votaciones)}")

        if not all_votaciones:
            logger.warning("No se encontraron votaciones en ninguna fecha")
            return results

        # NIVEL 2: Procesar cada votación
        total_votaciones = len(all_votaciones)
        for i_vot, vot_rec in enumerate(all_votaciones, 1):
            if limit and votaciones_procesadas >= limit:
                logger.info(f"Límite de {limit} votaciones alcanzado")
                break

            votaciones_procesadas += 1
            titulo_corto = (
                vot_rec.titulo[:60] + "..."
                if len(vot_rec.titulo) > 60
                else vot_rec.titulo
            )
            logger.info(
                f"[{i_vot}/{total_votaciones}] Procesando votación "
                f"{vot_rec.senado_id}: {titulo_corto}"
            )

            try:
                stats = self._scrape_single_votacion(vot_rec)
                results.append(stats)
                logger.info(
                    f"    ✓ {stats.get('votos', 0)} votos, "
                    f"{stats.get('senadores_nuevos', 0)} senadores nuevos"
                )
            except ValueError as e:
                # Votación ya existe — info, no error
                logger.info(f"    ⊘ {e}")
                results.append({"votacion_id": vot_rec.senado_id, "info": str(e)})
            except Exception as e:
                logger.error(
                    f"    ✗ Error procesando votación {vot_rec.senado_id}: {e}"
                )
                results.append({"error": str(e), "votacion_id": vot_rec.senado_id})

        return results

    def _scrape_single_votacion(self, vot_rec) -> dict:
        """Procesa una votación individual completa.

        1. Obtiene la página individual del detalle
        2. Obtiene la tabla AJAX de votos individuales
        3. Transforma y carga

        Args:
            vot_rec: SenVotacionIndexRecord con senado_id, titulo y fecha.

        Returns:
            Dict con estadísticas del upsert.

        Raises:
            ValueError: Si la votación no tiene datos suficientes o ya existe.
        """
        votacion_id = vot_rec.senado_id

        # 1. Obtener detalle de la votación (establece cookies Incapsula)
        logger.debug(f"Obteniendo detalle: votación {votacion_id}")

        html_detalle = self.client.get_votacion_detail(votacion_id)
        vot_detail = parse_votacion_detalle(html_detalle, votacion_id)

        if vot_detail is None:
            raise ValueError(
                f"Votación {votacion_id}: datos insuficientes en la página"
            )

        # 2. Obtener tabla AJAX de votos
        logger.debug(f"Obteniendo tabla AJAX: votación {votacion_id}")
        html_ajax = self.client.get_ajax_table(votacion_id)
        votos = parse_ajax_table(html_ajax)

        if not votos:
            raise ValueError(
                f"Votación {votacion_id}: sin votos individuales en la tabla AJAX"
            )

        # 3. Transformar (conexión temporal para búsqueda de IDs)
        conn = sqlite3.connect(str(SENADO_DB_PATH))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            votacion_completa = transformar_votacion(vot_rec, vot_detail, votos, conn)
        finally:
            conn.close()

        # 4. Cargar en BD
        stats = self.loader.upsert_votacion(votacion_completa)
        return stats

    def scrape_votacion_by_id(self, votacion_id: int) -> dict:
        """Scrapea una votación específica por su ID del portal.

        Útil para pruebas y debugging.

        Args:
            votacion_id: ID de la votación en senado.gob.mx.

        Returns:
            Dict con estadísticas del upsert.
        """
        logger.info(f"Scrapeando votación ID {votacion_id}")

        # Crear un objeto mock con senado_id para compatibilidad con _scrape_single_votacion
        class VotRecord:
            def __init__(self, senado_id):
                self.senado_id = senado_id
                self.titulo = f"Votación {senado_id}"
                self.fecha = ""

        return self._scrape_single_votacion(VotRecord(votacion_id))

    def close(self) -> None:
        """Cierra la sesión HTTP del cliente."""
        self.client.close()

    def __enter__(self) -> "SenadoPipeline":
        return self

    def __exit__(self, *args) -> None:
        self.close()


# ============================================================
# CLI
# ============================================================


def main():
    """CLI básico para el scraper del Senado."""
    parser = argparse.ArgumentParser(
        description="Scraper del Senado para el Observatorio del Congreso"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo votaciones a procesar (default: todas)",
    )
    parser.add_argument(
        "--votacion-id",
        type=int,
        default=None,
        help="Scrapear solo esta votación por ID del portal",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Mostrar estadísticas de la BD y salir",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Inicializar/crear el schema de la BD",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Desactivar caché HTML",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay entre requests en segundos [default: 2.0]",
    )

    args = parser.parse_args()

    pipeline = SenadoPipeline(
        use_cache=not args.no_cache,
        delay=args.delay,
    )

    try:
        # --- Modo init DB ---
        if args.init_db:
            pipeline.loader.init_db()
            print("✓ Schema de la BD inicializado correctamente")
            return

        # --- Modo estadísticas ---
        if args.stats:
            stats = pipeline.loader.estadisticas()
            print("\n=== Estadísticas de la BD (Senado) ===")
            for tabla, count in stats.items():
                print(f"  {tabla}: {count}")
            return

        # --- Modo votación individual ---
        if args.votacion_id:
            try:
                result = pipeline.scrape_votacion_by_id(args.votacion_id)
                print(f"\nResultado: {result}")
            except ValueError as e:
                print(f"\nInfo: {e}")
            except Exception as e:
                print(f"\nError: {e}")
            return

        # --- Modo batch ---
        results = pipeline.scrape_all(limit=args.limit)

        # Resumen
        exitosas = sum(1 for r in results if "error" not in r)
        errores = sum(1 for r in results if "error" in r)
        total_votes = sum(r.get("votos", 0) for r in results if "error" not in r)
        total_senadores = sum(
            r.get("senadores_nuevos", 0) for r in results if "error" not in r
        )

        print(f"\n{'=' * 50}")
        print(f"TOTAL: {exitosas} exitosas, {errores} errores")
        print(f"Total votos insertados: {total_votes}")
        print(f"Senadores nuevos: {total_senadores}")
        print(f"{'=' * 50}")

        # Verificar integridad
        if pipeline.loader.verificar_integridad():
            print("✓ Integridad referencial OK")
        else:
            print("✗ Violaciones de integridad referencial detectadas")

        # Mostrar estadísticas finales
        stats = pipeline.loader.estadisticas()
        print("\nEstadísticas finales:")
        for tabla, count in stats.items():
            print(f"  {tabla}: {count}")

    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
