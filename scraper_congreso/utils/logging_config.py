"""logging_config.py — Configuración centralizada de logging.

Proporciona RotatingFileHandler para logs persistentes con rotación
automática, y console handler para feedback en tiempo real.

Uso:
    from scraper_congreso.utils.logging_config import setup_logging
    setup_logging("diputados")
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
)


def setup_logging(name: str, log_dir: str | None = None) -> logging.Logger:
    """Configura logging con RotatingFileHandler y console handler.

    Args:
        name: Nombre del logger (usado como prefijo del archivo de log).
        log_dir: Directorio para logs. Default: directorio 'logs' del proyecto.

    Returns:
        Logger configurado para el módulo llamador.
    """
    if log_dir is None:
        log_dir = LOG_DIR

    os.makedirs(log_dir, exist_ok=True)

    # Root logger — evitar duplicate handlers si se llama múltiples veces
    root = logging.getLogger()
    if root.handlers:
        # Ya configurado — solo retornar el logger del módulo
        return logging.getLogger(name)

    root.setLevel(logging.DEBUG)

    # Console handler — WARNING mínimo
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(console)

    # File handler — DEBUG, con rotación (10MB, 5 backups)
    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(file_handler)

    return logging.getLogger(name)
