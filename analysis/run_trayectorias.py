#!/usr/bin/env python3
"""
run_trayectorias.py — Pipeline de Trayectorias Individuales.

Usage:
    python -m analysis.run_trayectorias --camara diputados
    python -m analysis.run_trayectorias --camara senado
    python -m analysis.run_trayectorias --camara ambas
"""

import time

from analysis.runner_utils import (
    build_simple_parser,
    log_elapsed,
    run_for_cameras,
    setup_logging,
)
from analysis.trayectorias import run_trayectorias

logger = setup_logging()


def main():
    parser = build_simple_parser(
        "Análisis de Trayectorias Individuales del Congreso",
        camara_choices=["diputados", "senado", "ambas"],
        camara_default="ambas",
        output_help="Directorio de salida (default: analysis/analisis-{camara}/output/)",
    )
    args = parser.parse_args()

    t_start = time.time()
    run_for_cameras(args.camara, run_trayectorias, args.output_dir, logger, "TRAYECTORIAS")
    log_elapsed(logger, t_start)


if __name__ == "__main__":
    main()
