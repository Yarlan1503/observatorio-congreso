#!/usr/bin/env python3
"""
run_efecto_genero.py — Pipeline de Análisis de Efecto Género.

Usage:
    python -m analysis.run_efecto_genero --camara diputados
    python -m analysis.run_efecto_genero --camara senado
    python -m analysis.run_efecto_genero --camara ambas
"""

import time

from analysis.efecto_genero import run_efecto_genero
from analysis.runner_utils import (
    build_simple_parser,
    log_elapsed,
    run_for_cameras,
    setup_logging,
)

logger = setup_logging()


def main():
    parser = build_simple_parser(
        "Análisis de Efecto Género en el Congreso",
        camara_choices=["diputados", "senado", "ambas"],
        camara_default="ambas",
        output_help="Directorio de salida (default: analysis/analisis-{camara}/output/)",
    )
    args = parser.parse_args()

    t_start = time.time()
    run_for_cameras(args.camara, run_efecto_genero, args.output_dir, logger, "EFECTO GÉNERO")
    log_elapsed(logger, t_start)


if __name__ == "__main__":
    main()
