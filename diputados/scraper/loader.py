"""
loader.py — Carga datos Popolo a SQLite con upsert inteligente.

Inserta datos transformados (VotacionCompleta) en la BD de forma
idempotente usando INSERT OR IGNORE. Todo un vote_event se inserta
en una sola transacción para garantizar consistencia.
"""

import sqlite3
import json
import logging
from typing import Optional

from .transformers import (
    VotacionCompleta,
    VoteEventPopolo,
    VotePopolo,
    CountPopolo,
    PersonPopolo,
    MembershipPopolo,
)
from .config import DB_PATH

logger = logging.getLogger(__name__)


class Loader:
    """Carga datos Popolo a SQLite con upsert inteligente.

    Idempotente: INSERT OR IGNORE para no duplicar datos.
    Transaccional: todo un vote_event se inserta en una sola transacción.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Inicializa el Loader.

        Args:
            db_path: Path a la BD. Si es None, usa DB_PATH de config.
        """
        self.db_path = db_path or str(DB_PATH)

    def _get_conn(self) -> sqlite3.Connection:
        """Obtiene conexión a la BD con foreign keys habilitadas.

        Returns:
            Conexión SQLite configurada con FK y WAL mode.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def upsert_votacion(self, votacion: VotacionCompleta) -> dict:
        """Inserta una votación completa en la BD.

        Proceso (dentro de una transacción):
        1. INSERT OR IGNORE motion
        2. INSERT OR IGNORE vote_event
        3. INSERT OR IGNORE person (solo las nuevas)
        4. INSERT OR IGNORE membership (solo las nuevas)
        5. INSERT OR IGNORE vote (todos)
        6. INSERT OR IGNORE count (todos)
        7. Commit

        Args:
            votacion: VotacionCompleta con todos los datos a insertar.

        Returns:
            Dict con estadísticas:
            {
                "vote_event": "VE03",
                "votes": 250,
                "counts": 40,
                "new_persons": 15,
                "new_memberships": 15
            }
        """
        conn = self._get_conn()
        stats = {
            "vote_event": votacion.vote_event.id,
            "votes": 0,
            "counts": 0,
            "new_persons": 0,
            "new_memberships": 0,
        }

        try:
            conn.execute("BEGIN TRANSACTION")

            # 1. Motion
            ve = votacion.vote_event
            conn.execute(
                """INSERT OR IGNORE INTO motion
                   (id, texto, clasificacion, requirement, result, date, legislative_session, fuente_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ve.motion_id,
                    ve.motion_text,
                    ve.motion_clasificacion,
                    ve.motion_requirement,
                    ve.motion_result,
                    ve.motion_date,
                    ve.motion_legislative_session,
                    ve.motion_fuente_url,
                ),
            )

            # 2. Vote Event
            conn.execute(
                """INSERT OR IGNORE INTO vote_event
                   (id, motion_id, start_date, organization_id, result, sitl_id, voter_count, legislatura, requirement, source_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ve.id,
                    ve.motion_id,
                    ve.start_date,
                    ve.organization_id,
                    ve.result,
                    ve.sitl_id,
                    ve.voter_count,
                    ve.legislatura,
                    ve.motion_requirement,
                    ve.source_id,
                ),
            )

            # 3. Person (solo las nuevas)
            for person in votacion.new_persons:
                conn.execute(
                    """INSERT OR IGNORE INTO person
                       (id, nombre, curul_tipo, start_date, end_date, identifiers_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        person.id,
                        person.nombre,
                        person.curul_tipo,
                        person.start_date,
                        person.end_date,
                        person.identifiers_json,
                    ),
                )
                stats["new_persons"] += 1

            # 4. Membership (solo las nuevas)
            for membership in votacion.new_memberships:
                conn.execute(
                    """INSERT OR IGNORE INTO membership
                       (id, person_id, org_id, rol, label, start_date, end_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        membership.id,
                        membership.person_id,
                        membership.org_id,
                        membership.rol,
                        membership.label,
                        membership.start_date,
                        membership.end_date,
                    ),
                )
                stats["new_memberships"] += 1

            # 5. Vote (todos)
            for vote in votacion.votes:
                conn.execute(
                    """INSERT OR IGNORE INTO vote
                       (id, vote_event_id, voter_id, option, "group")
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        vote.id,
                        vote.vote_event_id,
                        vote.voter_id,
                        vote.option,
                        vote.group,
                    ),
                )
                stats["votes"] += 1

            # 6. Count (todos)
            for count in votacion.counts:
                conn.execute(
                    """INSERT OR IGNORE INTO count
                       (id, vote_event_id, option, value, group_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        count.id,
                        count.vote_event_id,
                        count.option,
                        count.value,
                        count.group_id,
                    ),
                )
                stats["counts"] += 1

            conn.execute("COMMIT")
            logger.info(
                f"Upsert completado: VE={ve.id}, "
                f"{stats['votes']} votos, {stats['new_persons']} personas nuevas, "
                f"{stats['counts']} counts"
            )

        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Error en upsert de votación {votacion.vote_event.id}: {e}")
            raise
        finally:
            conn.close()

        return stats

    def verificar_integridad(self) -> bool:
        """Verifica integridad referencial de la BD.

        Returns:
            True si no hay violaciones de FK, False si las hay.
        """
        conn = self._get_conn()
        try:
            # PRAGMA foreign_key_check retorna filas por cada violación
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                for v in violations:
                    logger.error(
                        f"Violación FK: tabla={v[0]}, rowid={v[1]}, "
                        f"parent={v[2]}, fkid={v[3]}"
                    )
                return False
            return True
        finally:
            conn.close()

    def estadisticas(self) -> dict:
        """Retorna conteos actuales de todas las tablas.

        Returns:
            Dict con nombre de tabla → número de registros.
        """
        conn = self._get_conn()
        try:
            tablas = [
                "person",
                "organization",
                "membership",
                "post",
                "motion",
                "vote_event",
                "vote",
                "count",
                "area",
                "actor_externo",
                "relacion_poder",
                "evento_politico",
            ]
            stats = {}
            for tabla in tablas:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()
                    stats[tabla] = row[0]
                except sqlite3.OperationalError:
                    stats[tabla] = -1  # Tabla no existe
            return stats
        finally:
            conn.close()
