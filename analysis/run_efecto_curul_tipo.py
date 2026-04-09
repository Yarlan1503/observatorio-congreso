#!/usr/bin/env python3
"""run_efecto_curul_tipo.py — CLI para análisis de efecto curul_tipo."""

import argparse
import logging
import time
from pathlib import Path

from analysis.efecto_curul_tipo import run_efecto_curul_tipo

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


def main():
    parser = argparse.ArgumentParser(description="Análisis de Efecto Curul Tipo")
    parser.add_argument("--camara", choices=["diputados", "senado", "ambas"], default="ambas")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    t_start = time.time()
    if args.camara == "ambas":
        for camara in ["diputados", "senado"]:
            logger.info("\n" + "=" * 60)
            logger.info("=== EFECTO CURUL TIPO — %s ===", camara.upper())
            logger.info("=" * 60)
            run_efecto_curul_tipo(camara, args.output_dir)
    else:
        run_efecto_curul_tipo(args.camara, args.output_dir)

    elapsed = time.time() - t_start
    logger.info("\nTiempo total: %.1f segundos", elapsed)


if __name__ == "__main__":
    main()
