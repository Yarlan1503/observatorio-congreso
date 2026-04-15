#!/usr/bin/env python3
"""run_efecto_curul_tipo.py — CLI para análisis de efecto curul_tipo."""

import time

from analysis.efecto_curul_tipo import run_efecto_curul_tipo
from analysis.runner_utils import (
    build_simple_parser,
    log_elapsed,
    run_for_cameras,
    setup_logging,
)

logger = setup_logging()


def main():
    parser = build_simple_parser(
        "Análisis de Efecto Curul Tipo",
        camara_choices=["diputados", "senado", "ambas"],
        camara_default="ambas",
    )
    args = parser.parse_args()

    t_start = time.time()
    run_for_cameras(
        args.camara, run_efecto_curul_tipo, args.output_dir, logger, "EFECTO CURUL TIPO"
    )
    log_elapsed(logger, t_start)


if __name__ == "__main__":
    main()
