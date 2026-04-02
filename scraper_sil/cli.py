#!/usr/bin/env python3
"""
cli.py — Interfaz CLI para el scraper SIL.

Comandos disponibles:
    --init-db              Inicializar schema de la BD
    --legislatura LGN      Scrapear una legislature específica
    --legislatura LGN --limit N    Limitar a N votaciones
    --legislatura LGN --resume      Reanudar desde último checkpoint
    --legislatura LGN --no-cache    Ignorar caché
    --all                  Scrapear todas las legislaturas
    --stats                Mostrar estadísticas de la BD
    --votacion-id CLAVE    Scrapear una votación específica
"""

import argparse
import logging
import sys
from pathlib import Path

# Añadir el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper_sil import __version__
from scraper_sil.config import LEGISLATURAS
from scraper_sil.loaders.sil_loader import SILLoader
from scraper_sil.pipelines.sil_pipeline import SILPipeline
from scraper_sil.pipelines.legislature_pipeline import LegislaturePipeline

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sil")


def cmd_init_db(args: argparse.Namespace) -> int:
    """Inicializa el schema de la base de datos.

    Args:
        args: Argumentos parseados.

    Returns:
        Código de salida (0 = éxito).
    """
    logger.info("Inicializando schema SIL...")
    loader = SILLoader(db_path=args.db_path)

    try:
        loader.init_db()
        logger.info("Schema SIL inicializado correctamente")

        # Mostrar estado de la BD
        stats = loader.estadisticas()
        logger.info("Estado de la BD:")
        for key, value in stats.items():
            if isinstance(value, dict):
                logger.info(f"  {key}:")
                for k, v in value.items():
                    logger.info(f"    {k}: {v}")
            else:
                logger.info(f"  {key}: {value}")

        return 0
    except Exception as e:
        logger.error(f"Error inicializando schema: {e}")
        return 1


def cmd_stats(args: argparse.Namespace) -> int:
    """Muestra estadísticas de la base de datos.

    Args:
        args: Argumentos parseados.

    Returns:
        Código de salida (0 = éxito).
    """
    logger.info("Estadísticas de la BD SIL...")
    loader = SILLoader(db_path=args.db_path)

    try:
        stats = loader.estadisticas()

        print("\n" + "=" * 60)
        print("ESTADÍSTICAS DEL SCRAPER SIL")
        print("=" * 60)

        # Tablas principales
        print("\nTablas sen_*:")
        for tabla in [
            "sen_organization",
            "sen_person",
            "sen_membership",
            "sen_vote_event",
            "sen_motion",
            "sen_vote",
            "sen_count",
        ]:
            count = stats.get(tabla, -1)
            print(f"  {tabla}: {count:,}" if count >= 0 else f"  {tabla}: (no existe)")

        # Estados de scrapeo
        print("\nEstados de scrapeo (sen_vote_event):")
        status_stats = stats.get("scrape_status", {})
        total = sum(status_stats.values())
        for status, count in sorted(status_stats.items()):
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {status or 'null'}: {count:,} ({pct:.1f}%)")
        print(f"  TOTAL: {total:,}")

        # Verificar integridad
        print("\nIntegridad referencial:")
        if loader.verificar_integridad():
            print("  ✓ Sin violaciones de FK")
        else:
            print("  ✗ Hay violaciones de FK")

        print("=" * 60 + "\n")

        return 0
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        return 1


def cmd_legislatura(args: argparse.Namespace) -> int:
    """Ejecuta scraping de una legislature específica.

    Args:
        args: Argumentos parseados.

    Returns:
        Código de salida (0 = éxito).
    """
    legislature = args.legislatura.upper()

    if legislature not in LEGISLATURAS:
        logger.error(f"Legislatura {legislature} no válida. Opciones: {LEGISLATURAS}")
        return 1

    logger.info(f"Iniciando scraping de {legislature}...")

    # Configurar delay según args
    delay = 0.5 if args.fast else 1.5

    # Configurar opciones de Playwright
    use_playwright = getattr(args, "use_playwright", False)
    session_timeout = getattr(args, "session_timeout", 25) * 60  # Convertir a segundos

    pipeline = LegislaturePipeline(
        legislature=legislature,
        use_cache=not args.no_cache,
        delay=delay,
        db_path=args.db_path,
        use_playwright=use_playwright,
        session_timeout=session_timeout,
    )

    try:
        stats = pipeline.run(
            limit_pages=args.limit,
            limit_per_page=args.per_page or 50,
            resume=args.resume,
            scrape_votes=not args.no_votes,
        )

        # Mostrar resultados
        print("\n" + "=" * 60)
        print(f"RESULTADOS DEL SCRAPING: {legislature}")
        print("=" * 60)
        print(f"  Páginas procesadas: {stats['pages_scraped']}")
        print(f"  Votaciones encontradas: {stats['votaciones_found']}")
        print(f"  Votaciones procesadas: {stats['votaciones_processed']}")
        print(f"  Votaciones fallidas: {stats['votaciones_failed']}")

        if stats["errors"]:
            print(f"\n  Errores ({len(stats['errors'])}):")
            for err in stats["errors"][:5]:
                print(f"    - {err}")
            if len(stats["errors"]) > 5:
                print(f"    ... y {len(stats['errors']) - 5} más")

        # Verificar integridad
        loader = SILLoader(db_path=args.db_path)
        print(
            f"\n  Integridad FK: {'✓ OK' if loader.verificar_integridad() else '✗ ERROR'}"
        )

        print("=" * 60 + "\n")

        return 0 if stats["votaciones_failed"] == 0 else 1

    except Exception as e:
        logger.error(f"Error en scraping: {e}")
        return 1


def cmd_all(args: argparse.Namespace) -> int:
    """Ejecuta scraping de todas las legislaturas.

    Args:
        args: Argumentos parseados.

    Returns:
        Código de salida (0 = éxito).
    """
    logger.info(f"Iniciando scraping de todas las legislaturas...")

    delay = 0.5 if args.fast else 1.5
    use_playwright = getattr(args, "use_playwright", False)
    session_timeout = getattr(args, "session_timeout", 25) * 60  # Convertir a segundos
    all_stats = {}

    for legislature in LEGISLATURAS:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"PROCESANDO: {legislature}")
        logger.info(f"{'=' * 60}")

        pipeline = LegislaturePipeline(
            legislature=legislature,
            use_cache=not args.no_cache,
            delay=delay,
            db_path=args.db_path,
            use_playwright=use_playwright,
            session_timeout=session_timeout,
        )

        try:
            stats = pipeline.run(
                limit_pages=args.limit,
                resume=args.resume,
                scrape_votes=not args.no_votes,
            )
            all_stats[legislature] = stats

            # Resumen rápido
            processed = stats.get("votaciones_processed", 0)
            failed = stats.get("votaciones_failed", 0)
            logger.info(
                f"[{legislature}] Completado: {processed} procesadas, {failed} fallidas"
            )

        except Exception as e:
            logger.error(f"[{legislature}] Error: {e}")
            all_stats[legislature] = {"error": str(e)}

    # Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN FINAL - TODAS LAS LEGISLATURAS")
    print("=" * 60)

    total_processed = 0
    total_failed = 0

    for leg, stats in all_stats.items():
        if "error" in stats:
            print(f"  {leg}: ERROR - {stats['error']}")
        else:
            processed = stats.get("votaciones_processed", 0)
            failed = stats.get("votaciones_failed", 0)
            found = stats.get("votaciones_found", 0)
            print(f"  {leg}: {processed}/{found} procesadas, {failed} fallidas")
            total_processed += processed
            total_failed += failed

    print(f"\n  TOTAL: {total_processed} procesadas, {total_failed} fallidas")
    print("=" * 60 + "\n")

    return 0 if total_failed == 0 else 1


def cmd_votacion(args: argparse.Namespace) -> int:
    """Scrapes una votación específica por su clave.

    Args:
        args: Argumentos parseados.

    Returns:
        Código de salida (0 = éxito).
    """
    clave = args.votacion_id

    # Parsear clave (formato: CLAVE-ASUNTO[/CLAVE-TRAMITE])
    parts = clave.split("-")
    if len(parts) < 2:
        logger.error("Formato de clave inválido. Usar: CLAVE-ASUNTO[/CLAVE-TRAMITE]")
        return 1

    clave_asunto = parts[0]
    clave_tramite = parts[1] if len(parts) > 1 else "1"

    logger.info(f"Scraping votación {clave_asunto}/{clave_tramite}...")

    pipeline = SILPipeline(
        use_cache=not args.no_cache,
        delay=0.5,
        db_path=args.db_path,
    )

    try:
        result = pipeline.run_votacion(clave_asunto, clave_tramite)

        if result["success"]:
            print("\n" + "=" * 60)
            print("RESULTADO DEL SCRAPING")
            print("=" * 60)
            print(f"  Clave: {clave_asunto}/{clave_tramite}")
            print(f"  Vote Event ID: {result.get('vote_event_id', 'N/A')}")
            print(f"  Votos insertados: {result.get('votos', 0)}")
            print("  Estado: ✓ ÉXITO")
            print("=" * 60 + "\n")
            return 0
        else:
            logger.error(f"Error: {result.get('error', 'Desconocido')}")
            return 1

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def main() -> int:
    """Punto de entrada principal del CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m scraper_sil.cli",
        description="Scraper del Sistema de Información Legislativa (SIL)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m scraper_sil.cli --init-db
  python -m scraper_sil.cli --legislatura LXXVI
  python -m scraper_sil.cli --legislatura LXXVI --limit 50
  python -m scraper_sil.cli --legislatura LXXVI --resume
  python -m scraper_sil.cli --legislatura LXXVI --no-cache
  python -m scraper_sil.cli --all
  python -m scraper_sil.cli --stats
  python -m scraper_sil.cli --votacion-id 1234-1
        """,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path a la base de datos (default: db/senado.db)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # --init-db
    subparsers.add_parser("init-db", help="Inicializar schema de la BD")

    # --stats
    subparsers.add_parser("stats", help="Mostrar estadísticas de la BD")

    # --legislatura
    parser_leg = subparsers.add_parser(
        "legislatura",
        help="Scrapear una legislature específica",
    )
    parser_leg.add_argument(
        "legislatura",
        type=str,
        help="Legislatura (ej: LXXVI, LXVI, etc.)",
    )
    parser_leg.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limitar a N páginas de resultados",
    )
    parser_leg.add_argument(
        "--per-page",
        type=int,
        default=None,
        metavar="N",
        help="Resultados por página (default: 50)",
    )
    parser_leg.add_argument(
        "--resume",
        action="store_true",
        help="Reanudar desde último checkpoint",
    )
    parser_leg.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignorar caché y hacer requests frescos",
    )
    parser_leg.add_argument(
        "--no-votes",
        action="store_true",
        help="Solo scrape índice, no votos individuales",
    )
    parser_leg.add_argument(
        "--fast",
        action="store_true",
        help="Modo rápido (delay 0.5s en vez de 1.5s)",
    )
    parser_leg.add_argument(
        "--use-playwright",
        action="store_true",
        help="Usar Playwright/Selenium para inicializar sesión JavaScript",
    )
    parser_leg.add_argument(
        "--session-timeout",
        type=int,
        default=25,
        metavar="MINUTOS",
        help="Timeout de sesión en minutos (default: 25)",
    )

    # --all
    parser_all = subparsers.add_parser(
        "all",
        help="Scrapear todas las legislaturas",
    )
    parser_all.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limitar a N páginas por legislature",
    )
    parser_all.add_argument(
        "--resume",
        action="store_true",
        help="Reanudar desde último checkpoint",
    )
    parser_all.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignorar caché y hacer requests frescos",
    )
    parser_all.add_argument(
        "--no-votes",
        action="store_true",
        help="Solo scrape índice, no votos individuales",
    )
    parser_all.add_argument(
        "--fast",
        action="store_true",
        help="Modo rápido (delay 0.5s en vez de 1.5s)",
    )
    parser_all.add_argument(
        "--use-playwright",
        action="store_true",
        help="Usar Playwright/Selenium para inicializar sesión JavaScript",
    )
    parser_all.add_argument(
        "--session-timeout",
        type=int,
        default=25,
        metavar="MINUTOS",
        help="Timeout de sesión en minutos (default: 25)",
    )

    # --votacion-id
    parser_vot = subparsers.add_parser(
        "votacion",
        help="Scrapear una votación específica",
    )
    parser_vot.add_argument(
        "votacion_id",
        type=str,
        help="Clave de la votación (formato: CLAVE-ASUNTO[/CLAVE-TRAMITE])",
    )
    parser_vot.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignorar caché y hacer requests frescos",
    )

    # Parsear argumentos
    args = parser.parse_args()

    # Si no hay subcommand, mostrar ayuda
    if not args.command:
        parser.print_help()
        return 0

    # Ejecutar comando correspondiente
    commands = {
        "init-db": cmd_init_db,
        "stats": cmd_stats,
        "legislatura": cmd_legislatura,
        "all": cmd_all,
        "votacion": cmd_votacion,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
