#!/usr/bin/env python3
"""
run_evolucion_partidos.py — CLI runner para Evolución de Partidos.

Usage:
    python -m analysis.run_evolucion_partidos --camara diputados
    python -m analysis.run_evolucion_partidos --camara senado
    python -m analysis.run_evolucion_partidos --camara ambas
"""

import argparse
import logging
import time
from pathlib import Path

from analysis.evolucion_partidos import run_evolucion_partidos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


def main():
    parser = argparse.ArgumentParser(
        description="Análisis de Evolución de Partidos del Congreso",
    )
    parser.add_argument(
        "--camara",
        choices=["diputados", "senado", "ambas"],
        default="ambas",
        help="Cámara a analizar (default: ambas)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida (default: analysis/analisis-{camara}/output/)",
    )
    args = parser.parse_args()

    t_start = time.time()

    if args.camara == "ambas":
        for camara in ["diputados", "senado"]:
            logger.info("\n" + "=" * 60)
            logger.info("=== EVOLUCIÓN PARTIDOS — %s ===", camara.upper())
            logger.info("=" * 60)
            run_evolucion_partidos(camara, args.output_dir)
    else:
        logger.info("=" * 60)
        logger.info("=== EVOLUCIÓN PARTIDOS — %s ===", args.camara.upper())
        logger.info("=" * 60)
        run_evolucion_partidos(args.camara, args.output_dir)

    elapsed = time.time() - t_start
    logger.info("\nTiempo total: %.1f segundos", elapsed)


if __name__ == "__main__":
    main()
