"""
runner_utils.py — Utilidades compartidas para los runners de análisis.

Centraliza setup común: logging, paths, argparse base y patrones de ejecución.
Los runners importan lo que necesitan, sin side effects al importar este módulo.
"""

import argparse
import logging
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths del proyecto
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).parent.parent
DB_PATH: Path = PROJECT_ROOT / "db" / "congreso.db"
DEFAULT_OUTPUT_DIR: Path = Path(__file__).parent / "analisis-diputados" / "output"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configurar logging básico y devolver logger con nombre del módulo llamador.

    Args:
        level: Nivel de logging (default: INFO).

    Returns:
        Logger configurado (usar ``logging.getLogger(__name__)`` directamente
        si se prefiere; esta función solo asegura basicConfig).
    """
    logging.basicConfig(level=level, format=_LOG_FORMAT)
    return logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argparse — builders reutilizables
# ---------------------------------------------------------------------------


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    camara_choices: list[str] | None = None,
    camara_default: str | None = None,
    output_help: str | None = None,
) -> None:
    """Agregar argumentos CLI comunes a un parser existente.

    Args:
        parser: Parser al que se le agregan los argumentos.
        camara_choices: Lista de choices para --camara.
            Default: ``["diputados", "senado"]``.
        camara_default: Valor por defecto de --camara.
            ``None`` significa que es obligatorio o sin default.
        output_help: Texto de ayuda para --output-dir.
    """
    parser.add_argument(
        "--camara",
        choices=camara_choices or ["diputados", "senado"],
        default=camara_default,
        help="Filtrar por cámara",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=output_help or "Directorio de salida",
    )


def build_simple_parser(
    description: str,
    *,
    camara_choices: list[str] | None = None,
    camara_default: str | None = None,
    output_help: str | None = None,
) -> argparse.ArgumentParser:
    """Construir un ArgumentParser con los argumentos comunes ya incluidos.

    Args:
        description: Descripción del parser.
        camara_choices: Choices para --camara.
        camara_default: Default de --camara.
        output_help: Help de --output-dir.

    Returns:
        Parser listo para usar o extender.
    """
    parser = argparse.ArgumentParser(description=description)
    add_common_args(
        parser,
        camara_choices=camara_choices,
        camara_default=camara_default,
        output_help=output_help,
    )
    return parser


# ---------------------------------------------------------------------------
# Banner y timing
# ---------------------------------------------------------------------------


def log_banner(logger: logging.Logger, title: str) -> None:
    """Imprimir banner de inicio de análisis.

    Args:
        logger: Logger a usar.
        title: Título del banner (se imprime entre líneas de ``=``).
    """
    sep = "=" * 60
    logger.info(sep)
    logger.info("=== %s ===", title)
    logger.info(sep)


def log_elapsed(logger: logging.Logger, start_time: float, label: str = "Tiempo total") -> None:
    """Registrar tiempo transcurrido desde *start_time*.

    Args:
        logger: Logger a usar.
        start_time: Timestamp de inicio (de ``time.time()``).
        label: Etiqueta para el mensaje (default: "Tiempo total").
    """
    elapsed = time.time() - start_time
    logger.info("\n%s: %.1f segundos", label, elapsed)


# ---------------------------------------------------------------------------
# Ejecución para cámaras "ambas"
# ---------------------------------------------------------------------------


def run_for_cameras(
    camara: str,
    run_fn,
    output_dir: str | None,
    logger: logging.Logger,
    title_prefix: str,
) -> None:
    """Ejecutar una función de análisis para una o ambas cámaras.

    Si *camara* es ``"ambas"``, ejecuta *run_fn* para ``"diputados"`` y
    ``"senado"`` secuencialmente. Si no, ejecuta solo la cámara indicada.

    Args:
        camara: ``"diputados"``, ``"senado"`` o ``"ambas"``.
        run_fn: Función que recibe ``(camara: str, output_dir: str | None)``.
        output_dir: Directorio de salida (pasado directo a *run_fn*).
        logger: Logger para imprimir banners.
        title_prefix: Prefijo del banner (ej: ``"EVOLUCIÓN PARTIDOS"``).
    """
    if camara == "ambas":
        for c in ["diputados", "senado"]:
            log_banner(logger, f"{title_prefix} — {c.upper()}")
            run_fn(c, output_dir)
    else:
        log_banner(logger, f"{title_prefix} — {camara.upper()}")
        run_fn(camara, output_dir)
