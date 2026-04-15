#!/usr/bin/env python3
"""
run_evolucion_partidos.py — CLI runner para Evolución de Partidos.

Usage:
    python -m analysis.run_evolucion_partidos --camara diputados
    python -m analysis.run_evolucion_partidos --camara senado
    python -m analysis.run_evolucion_partidos --camara ambas
"""

import time

from analysis.evolucion_partidos import run_evolucion_partidos
from analysis.runner_utils import (
    build_simple_parser,
    log_elapsed,
    run_for_cameras,
    setup_logging,
)

logger = setup_logging()


def main():
    parser = build_simple_parser(
        "Análisis de Evolución de Partidos del Congreso",
        camara_choices=["diputados", "senado", "ambas"],
        camara_default="ambas",
        output_help="Directorio de salida (default: analysis/analisis-{camara}/output/)",
    )
    args = parser.parse_args()

    t_start = time.time()
    run_for_cameras(
        args.camara, run_evolucion_partidos, args.output_dir, logger, "EVOLUCIÓN PARTIDOS"
    )
    log_elapsed(logger, t_start)


if __name__ == "__main__":
    main()
