"""
cli.py — CLI para scraping de votaciones nominales del Senado.

Portal LXVI: https://www.senado.gob.mx/66/votacion/{id}
AJAX endpoint: /66/app/votaciones/functions/viewTableVot.php
Rango de IDs: 1 a 5070+ (LX-LXVI)

Escribe en el schema Popolo-Graph de congreso.db.

Uso:
    python -m senado.scrapers.votaciones --range 1 5070
    python -m senado.scrapers.votaciones --test-id 1
    python -m senado.scrapers.votaciones --test-id 5065
    python -m senado.scrapers.votaciones --init-schema
    python -m senado.scrapers.votaciones --stats
"""

import argparse
import logging

from senado.scrapers.shared.client import SenadoLXVIClient
from senado.scrapers.shared.config import DB_PATH, LXVI_VOTACION_URL_TEMPLATE
from senado.scrapers.shared.models import SenVotacionDetail, SenVotoNominal

from .congreso_loader import (
    CongresoLoader,
    CongresoVotacionRecord,
    CongresoVotoRecord,
)
from .parsers.lxvi_portal import parse_lxvi_votacion
from .transformers import inferir_genero, parse_fecha_iso

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Pipeline principal
# =============================================================================


class SenadoCongresoPipeline:
    """Pipeline que scraper votaciones del Senado (portal LXVI) y escribe en congreso.db.

    Transforma los datos del formato interno del scraper del Senado
    (SenVotacionDetail, SenVotoNominal) al formato CongresoVotacionRecord
    antes de insertar en la BD via CongresoLoader.
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = 2.0,
        db_path: str | None = None,
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
        page_url = LXVI_VOTACION_URL_TEMPLATE.format(id=votacion_id)
        logger.info(f"Scrapeando votacion {votacion_id}: {page_url}")

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
            votacion_record = self._transform_to_congreso_record(votacion_id, detail, votos)

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

    def scrape_range(self, start: int, end: int, limit: int | None = None) -> dict:
        """Itera IDs de start a end, procesando cada votación.

        Args:
            start: ID inicial (inclusive).
            end: ID final (inclusive).
            limit: Máximo de votaciones a procesar (None = todas).

        Returns:
            Dict con estadísticas agregadas del procesamiento.
        """
        total = end - start + 1
        if limit and limit < total:
            effective_end = start + limit - 1
            logger.info(
                f"Iniciando scrapeo de range [{start}, {effective_end}] "
                f"(limit={limit} de {total} IDs)"
            )
        else:
            effective_end = end
            logger.info(f"Iniciando scrapeo de range [{start}, {end}] ({total} IDs)")

        stats_agg = {
            "total": effective_end - start + 1,
            "exitosos": 0,
            "errores": 0,
            "ya_existen": 0,
            "votos_insertados": 0,
            "personas_nuevas": 0,
        }

        errores = []

        try:
            for i, votacion_id in enumerate(range(start, effective_end + 1), start=1):
                if i % 100 == 0 or i == 1 or i == stats_agg["total"]:
                    logger.info(f"Procesando {votacion_id} ({i}/{stats_agg['total']})")

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

        # Verificar integridad al final del batch
        if self.loader.verificar_integridad():
            logger.info("✓ Integridad referencial OK")
        else:
            logger.warning("✗ Violaciones de integridad referencial detectadas")

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
        fecha_iso = parse_fecha_iso(detail.fecha)

        # --- Fuente URL ---
        fuente_url = LXVI_VOTACION_URL_TEMPLATE.format(id=votacion_id)

        # --- Convertir votos ---
        votos_records: list[CongresoVotoRecord] = []
        personas_nuevas: list[dict] = []
        membresias_nuevas: list[dict] = []

        nombres_procesados: set[str] = set()

        for voto in votos:
            nombre = voto.nombre.strip()
            grupo = voto.grupo_parlamentario.strip()

            if nombre and nombre not in nombres_procesados:
                nombres_procesados.add(nombre)

                genero = inferir_genero(nombre)

                personas_nuevas.append(
                    {
                        "nombre": nombre,
                        "genero": genero,
                    }
                )

                if grupo:
                    membresias_nuevas.append(
                        {
                            "persona_id": nombre,
                            "organizacion_id": grupo,
                            "rol": "senador",
                            "start_date": fecha_iso,
                        }
                    )

            votos_records.append(
                CongresoVotoRecord(
                    nombre=nombre,
                    grupo_parlamentario=grupo,
                    voto=voto.voto,
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
            legislature=detail.periodo or "",
            fecha_iso=fecha_iso,
            descripcion=detail.descripcion,
            pro_count=detail.pro_count,
            contra_count=detail.contra_count,
            abstention_count=detail.abstention_count,
            votos=votos_records,
            voto_personas_nuevas=personas_nuevas,
            voto_membresias_nuevas=membresias_nuevas,
            counts_por_partido=counts_por_partido,
            # Fase 1 gaps:
            identifiers_json="",  # El loader lo genera si está vacío
            requirement="",  # El loader lo infiere de la descripción
            fuente_url=fuente_url,
        )

    def print_stats(self) -> None:
        """Imprime estadísticas de la BD."""
        stats = self.loader.estadisticas()
        print("\n=== Estadísticas de la BD (Senado) ===")
        for tabla, count in stats.items():
            print(f"  {tabla}: {count}")

        # Detalle por legislatura
        conn = self.loader._get_conn()
        try:
            rows = conn.execute(
                """SELECT legislatura, COUNT(*), SUM(voter_count)
                   FROM vote_event
                   WHERE legislatura IS NOT NULL AND legislatura != ''
                   GROUP BY legislatura
                   ORDER BY legislatura"""
            ).fetchall()
            if rows:
                print("\n--- Por Legislatura ---")
                for leg, count, voters in rows:
                    print(f"  {leg}: {count} votaciones, {voters or 0} votos totales")
        finally:
            conn.close()

        # Desglose por resultado
        conn = self.loader._get_conn()
        try:
            rows = conn.execute(
                """SELECT result, COUNT(*)
                   FROM vote_event
                   GROUP BY result"""
            ).fetchall()
            if rows:
                print("\n--- Por Resultado ---")
                for result, count in rows:
                    print(f"  {result or 'NULL'}: {count}")
        finally:
            conn.close()


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
  python -m senado.scrapers.votaciones --range 1 5070
  python -m senado.scrapers.votaciones --range 1 100 --limit 10
  python -m senado.scrapers.votaciones --test-id 1
  python -m senado.scrapers.votaciones --test-id 5065
  python -m senado.scrapers.votaciones --init-schema
  python -m senado.scrapers.votaciones --stats
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
        "--stats",
        action="store_true",
        help="Mostrar estadísticas de la BD y salir",
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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de votaciones a procesar (default: todas)",
    )

    args = parser.parse_args()

    # Validar argumentos
    if not args.range and not args.test_id and not args.init_schema and not args.stats:
        parser.error("Se requiere --range, --test-id, --init-schema o --stats")

    if args.range and args.range[0] > args.range[1]:
        parser.error(f"Rango inválido: start={args.range[0]} > end={args.range[1]}")

    # Inicializar pipeline
    use_cache = not args.no_cache
    pipeline = SenadoCongresoPipeline(use_cache=use_cache, delay=args.delay)

    # Ejecutar acción
    if args.stats:
        pipeline.print_stats()
        return

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
        result = pipeline.scrape_range(start, end, limit=args.limit)

        print(f"\n{'=' * 50}")
        print("Resumen:")
        print(f"  Total IDs:        {result['total']}")
        print(f"  Exitosos:         {result['exitosos']}")
        print(f"  Ya existían:      {result['ya_existen']}")
        print(f"  Errores:          {result['errores']}")
        print(f"  Votos insertados: {result['votos_insertados']}")
        print(f"  Personas nuevas:  {result['personas_nuevas']}")
        print(f"{'=' * 50}")

        # Estadísticas finales
        pipeline.print_stats()


if __name__ == "__main__":
    main()
