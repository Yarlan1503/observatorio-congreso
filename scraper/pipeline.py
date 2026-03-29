"""
pipeline.py — Orquestador del scraper SITL/INFOPAL con CLI.

Coordina el flujo completo:
    client → parsers → transformers → loader → SQLite

Uso:
    python -m scraper.pipeline --leg LXVI --periodo 1 --limit 5
    python -m scraper.pipeline --sitl-id 1234
    python -m scraper.pipeline --stats
"""

import logging
import sys
import re
import argparse
import sqlite3
from typing import Optional

from bs4 import BeautifulSoup

from scraper.config import PARTY_SITL_IDS, CACHE_DIR, DB_PATH
from scraper.client import SITLClient
from scraper.legislatura import (
    url_votaciones_por_periodo,
    url_estadistico,
    url_nominal,
    url_sistema,
    get_legislatura_data,
    _base,
    _suffix,
)
from scraper.parsers.votaciones import parse_votaciones
from scraper.parsers.desglose import parse_desglose
from scraper.parsers.nominal import parse_nominal
from scraper.transformers import transformar_votacion
from scraper.loader import Loader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ScraperPipeline:
    """Orquesta el scraping completo de votaciones.

    Flujo:
    1. Obtener listado de votaciones del periodo
    2. Para cada votación:
       a. Obtener desglose por partido
       b. Para cada partido: obtener listado nominal
       c. Transformar datos a formato Popolo
       d. Insertar en SQLite
    """

    def __init__(
        self,
        legislatura: str = "LXVI",
        use_cache: bool = True,
        delay: float = 2.0,
    ):
        """Inicializa el pipeline.

        Args:
            legislatura: Clave de legislatura (ej: "LXVI").
            use_cache: Si True, usa caché file-based para HTML.
            delay: Segundos entre requests HTTP.
        """
        self.legislatura = legislatura
        self.leg_data = get_legislatura_data(legislatura)
        self.party_sitl_ids: dict[str, int] = self.leg_data.get(
            "parties", PARTY_SITL_IDS
        )
        self.client = SITLClient(use_cache=use_cache, delay=delay)
        self.loader = Loader()

    def scrape_votaciones_periodo(
        self,
        periodo: int,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Scrapea todas las votaciones de un periodo legislativo.

        Args:
            periodo: Número de periodo (1, 2, 3...).
            limit: Máximo número de votaciones a procesar (None = todas).

        Returns:
            Lista de dicts con estadísticas de cada votación procesada.
        """
        results: list[dict] = []

        # 1. Obtener listado
        url = url_votaciones_por_periodo(self.legislatura, periodo)
        logger.info(f"Obteniendo listado de votaciones: {url}")
        html = self.client.get_html(url, referer=url_sistema(self.legislatura))
        votaciones = parse_votaciones(html, periodo)
        logger.info(f"Encontradas {len(votaciones)} votaciones en periodo {periodo}")

        if limit:
            votaciones = votaciones[:limit]
            logger.info(f"Limitando a {limit} votaciones")

        # 2. Procesar cada votación
        for i, vot in enumerate(votaciones, 1):
            titulo_corto = vot.titulo[:60] if vot.titulo else "(sin título)"
            logger.info(
                f"[{i}/{len(votaciones)}] Procesando votación SITL "
                f"{vot.sitl_id}: {titulo_corto}..."
            )
            try:
                stats = self._scrape_single_votacion(vot)
                results.append(stats)
                logger.info(
                    f"  ✓ {stats['votes']} votos, "
                    f"{stats['new_persons']} personas nuevas"
                )
            except Exception as e:
                logger.error(f"  ✗ Error procesando votación {vot.sitl_id}: {e}")
                results.append({"error": str(e), "sitl_id": vot.sitl_id})

        return results

    def _scrape_single_votacion(self, votacion) -> dict:
        """Procesa una votación individual completa.

        1. Obtiene desglose por partido
        2. Obtiene listado nominal de cada partido
        3. Transforma y carga

        Args:
            votacion: VotacionRecord con los datos de la votación.

        Returns:
            Dict con estadísticas del upsert.

        Raises:
            ValueError: Si la votación no tiene datos de desglose.
        """
        # 1. Desglose
        url_desg = url_estadistico(self.legislatura, votacion.sitl_id)
        html_desg = self.client.get_html(
            url_desg, referer=url_sistema(self.legislatura)
        )
        desglose = parse_desglose(html_desg, votacion.sitl_id)

        if desglose is None:
            raise ValueError(f"Votación {votacion.sitl_id} sin datos de desglose")

        # 2. Nominales de cada partido
        nominales = []
        for party_name, party_sitl_id in self.party_sitl_ids.items():
            # Solo scrapeamos partidos que tengan diputados en esta votación
            partido_data = None
            for p in desglose.partidos:
                if p.partido_nombre == party_name:
                    partido_data = p
                    break

            if partido_data is None or partido_data.total == 0:
                continue

            url_nom = url_nominal(self.legislatura, party_sitl_id, votacion.sitl_id)
            html_nom = self.client.get_html(url_nom, referer=url_desg)
            nominal = parse_nominal(html_nom, votacion.sitl_id, party_name)
            nominales.append(nominal)

            logger.debug(f"    {party_name}: {len(nominal.votos)} votos")

        # 3. Transformar (conexión temporal para búsqueda de IDs)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            votacion_completa = transformar_votacion(
                votacion, desglose, nominales, conn, self.legislatura
            )
        finally:
            conn.close()

        # 4. Cargar
        stats = self.loader.upsert_votacion(votacion_completa)
        return stats

    def scrape_votacion_by_sitl_id(self, sitl_id: int, periodo: int = 1) -> dict:
        """Scrapea una votación específica por su SITL ID.

        Útil para pruebas y debugging.

        Args:
            sitl_id: ID SITL de la votación.
            periodo: Número de periodo (default: 1).

        Returns:
            Dict con estadísticas del upsert.
        """
        # Crear un VotacionRecord artificial
        from scraper.models import VotacionRecord

        vot = VotacionRecord(
            sitl_id=sitl_id,
            numero_secuencial=0,
            titulo="",
            fecha="",
            periodo=periodo,
        )
        return self._scrape_single_votacion(vot)

    def discover_periods(self) -> list[int]:
        """Descubre los periodos disponibles desde la página índice de la legislatura.

        Lee la página de votaciones por periodo y extrae todos los links
        que contienen el parámetro `pert=`. Los periodos no son continuos
        (pueden tener gaps), por lo que este discovery step es necesario.

        Returns:
            Lista ordenada de números de periodo disponibles.
        """
        sfx = _suffix(self.legislatura)
        url = f"{_base(self.legislatura)}/votaciones_por_periodo{sfx}.php"
        logger.info(f"Descubriendo periodos desde: {url}")
        html = self.client.get_html(url, referer=url_sistema(self.legislatura))
        soup = BeautifulSoup(html, "lxml")
        periods: set[int] = set()
        for a_tag in soup.find_all("a", href=True):
            match = re.search(r"pert=(\d+)", a_tag["href"])
            if match:
                periods.add(int(match.group(1)))
        return sorted(periods)


def main():
    """CLI básico para el scraper."""
    parser = argparse.ArgumentParser(
        description="Scraper SITL/INFOPAL para el Observatorio del Congreso"
    )
    parser.add_argument(
        "--leg",
        default="LXVI",
        help="Legislatura (LX, LXI, ..., LXVI) [default: LXVI]",
    )
    parser.add_argument(
        "--periodo",
        type=int,
        default=1,
        help="Periodo legislativo [default: 1]",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo votaciones a procesar (default: todas)",
    )
    parser.add_argument(
        "--sitl-id",
        type=int,
        default=None,
        help="Scrapear solo esta votación por SITL ID",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Desactivar caché HTML",
    )
    parser.add_argument(
        "--all-periods",
        action="store_true",
        help="Descubrir y scrapear todos los periodos de la legislatura",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay entre requests en segundos [default: 2.0]",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Mostrar estadísticas de la BD y salir",
    )

    args = parser.parse_args()

    pipeline = ScraperPipeline(
        legislatura=args.leg,
        use_cache=not args.no_cache,
        delay=args.delay,
    )

    # --- Modo estadísticas ---
    if args.stats:
        stats = pipeline.loader.estadisticas()
        print("\n=== Estadísticas de la BD ===")
        for tabla, count in stats.items():
            print(f"  {tabla}: {count}")
        return

    # --- Modo votación individual ---
    if args.sitl_id:
        logger.info(f"Scrapeando votación SITL ID {args.sitl_id}")
        result = pipeline.scrape_votacion_by_sitl_id(args.sitl_id, args.periodo)
        print(f"\nResultado: {result}")
        return

    # --- Modo batch: todos los periodos ---
    if args.all_periods:
        periods = pipeline.discover_periods()
        print(f"\nPeriodos descubiertos para {args.leg}: {periods}")
        print(f"Total: {len(periods)} periodos\n")

        all_results: list[dict] = []
        for p in periods:
            print(f"--- Periodo {p} ---")
            results = pipeline.scrape_votaciones_periodo(p, limit=args.limit)
            all_results.extend(results)

            exitosas = sum(1 for r in results if "error" not in r)
            errores = sum(1 for r in results if "error" in r)
            print(f"  Periodo {p}: {exitosas} exitosas, {errores} errores")

        # Resumen global
        total_exitosas = sum(1 for r in all_results if "error" not in r)
        total_errores = sum(1 for r in all_results if "error" in r)
        total_votes = sum(r.get("votes", 0) for r in all_results if "error" not in r)
        total_persons = sum(
            r.get("new_persons", 0) for r in all_results if "error" not in r
        )

        print(f"\n{'=' * 50}")
        print(f"TOTAL: {total_exitosas} exitosas, {total_errores} errores")
        print(f"Total votos insertados: {total_votes}")
        print(f"Personas nuevas: {total_persons}")
        print(f"{'=' * 50}")

        if pipeline.loader.verificar_integridad():
            print("✓ Integridad referencial OK")
        else:
            print("✗ Violaciones de integridad referencial detectadas")

        stats = pipeline.loader.estadisticas()
        print("\nEstadísticas finales:")
        for tabla, count in stats.items():
            print(f"  {tabla}: {count}")
        return

    # --- Modo batch por periodo ---
    results = pipeline.scrape_votaciones_periodo(args.periodo, limit=args.limit)

    # Resumen
    exitosas = sum(1 for r in results if "error" not in r)
    errores = sum(1 for r in results if "error" in r)
    total_votes = sum(r.get("votes", 0) for r in results if "error" not in r)
    total_persons = sum(r.get("new_persons", 0) for r in results if "error" not in r)

    print(f"\n{'=' * 50}")
    print(f"Procesadas: {exitosas} exitosas, {errores} errores")
    print(f"Total votos insertados: {total_votes}")
    print(f"Personas nuevas: {total_persons}")
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


if __name__ == "__main__":
    main()
