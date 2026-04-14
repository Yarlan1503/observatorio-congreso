"""
loader.py — Carga datos Popolo a SQLite con upsert inteligente.

Inserta datos transformados (VotacionCompleta) en la BD de forma
idempotente usando INSERT OR IGNORE. Todo un vote_event se inserta
en una sola transacción para garantizar consistencia.
"""

from typing import ClassVar

from scraper_congreso.utils.base_loader import BaseLoader

from .config import DB_PATH
from .transformers import (
    VotacionCompleta,
)


class Loader(BaseLoader):
    """Carga datos Popolo a SQLite con upsert inteligente.

    Idempotente: INSERT OR IGNORE para no duplicar datos.
    Transaccional: todo un vote_event se inserta en una sola transacción.
    """

    TABLES: ClassVar[list[str]] = [
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

    def __init__(self, db_path: str | None = None) -> None:
        """Inicializa el Loader.

        Args:
            db_path: Path a la BD. Si es None, usa DB_PATH de config.
        """
        super().__init__(db_path or str(DB_PATH))

    def upsert_votacion(self, votacion: VotacionCompleta) -> dict[str, int | str]:
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
            self.logger.info(
                f"Upsert completado: VE={ve.id}, "
                f"{stats['votes']} votos, {stats['new_persons']} personas nuevas, "
                f"{stats['counts']} counts"
            )

        except Exception as e:
            conn.execute("ROLLBACK")
            self.logger.error(f"Error en upsert de votación {votacion.vote_event.id}: {e}")
            raise
        finally:
            conn.close()

        return stats
