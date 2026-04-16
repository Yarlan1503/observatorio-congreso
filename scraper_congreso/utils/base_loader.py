"""base_loader.py — Clase base para loaders de datos al schema Popolo-Graph."""

import logging
import sqlite3
from pathlib import Path
from typing import ClassVar

from db.constants import apply_pragmas


class BaseLoader:
    """Base class for Popolo-Graph loaders.

    Provee conexión a BD con PRAGMAs, verificación de integridad
    y estadísticas por tabla. Heredado por loaders de Diputados y Senado.
    """

    # Subclasses override with their table list
    TABLES: ClassVar[list[str]] = []

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(self.__class__.__module__)

    def _get_conn(self) -> sqlite3.Connection:
        """Obtiene conexión a la BD con foreign keys y WAL mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        apply_pragmas(conn, busy_timeout=30000)
        return conn

    def verificar_integridad(self) -> bool:
        """Verifica integridad referencial de la BD."""
        conn = self._get_conn()
        try:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                for v in violations:
                    self.logger.error(
                        f"Violación FK: tabla={v[0]}, rowid={v[1]}, parent={v[2]}, fkid={v[3]}"
                    )
                return False
            return True
        finally:
            conn.close()

    def estadisticas(self) -> dict[str, int]:
        """Retorna conteos actuales de las tablas definidas en TABLES."""
        conn = self._get_conn()
        try:
            stats: dict[str, int] = {}
            for tabla in self.TABLES:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()
                    stats[tabla] = row[0]
                except sqlite3.OperationalError:
                    stats[tabla] = -1
            return stats
        finally:
            conn.close()
