"""
sil_loader.py — Loader para insertar datos del SIL en SQLite.

Usa el schema sen_* existente con extensiones para campos SIL.
Maneja el schema completo del scraper SIL incluyendo checkpoints.
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scraper_sil.models import (
    SILVotacionDetail,
    SILVotosCompletos,
    SILLoadResult,
    SILVotacionIndex,
)
from scraper_sil.config import (
    SIL_DB_PATH,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_SKIPPED,
)

logger = logging.getLogger(__name__)


@dataclass
class SILIdCounters:
    """Contadores para generar IDs con prefijo en el schema sen_*."""

    vote_event: int = 0  # SVE01, SVE02, ...
    motion: int = 0  # SM01, SM02, ...
    person: int = 0  # SN01, SN02, ...
    membership: int = 0  # SMB01, SMB02, ...
    vote: int = 0  # SV01, SV02, ...
    count: int = 0  # SC01, SC02, ...
    organization: int = 0  # SO01, SO02, ...

    def next_id(self, prefix: str) -> str:
        """Genera el siguiente ID para un prefijo dado."""
        counters_map = {
            "SVE": "vote_event",
            "SM": "motion",
            "SN": "person",
            "SMB": "membership",
            "SV": "vote",
            "SC": "count",
            "SO": "organization",
        }
        key = counters_map[prefix]
        count = getattr(self, key) + 1
        setattr(self, key, count)
        return f"{prefix}{count:05d}"


class SILLoader:
    """Loader para datos del scraper SIL.

    Usa el schema sen_* existente con extensiones SIL:
    - sen_vote_event: sil_clave_asunto, sil_clave_tramite, sil_legislatura,
      sil_sid, scrape_status
    - sen_motion: sil_tipo_asunto, sil_camara

    Idempotente: INSERT OR REPLACE para actualizar datos existentes.
    Transaccional: toda una votación se procesa en una sola transacción.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Inicializa el SILLoader.

        Args:
            db_path: Path a la BD. Si es None, usa SIL_DB_PATH de config.
        """
        self.db_path = db_path or str(SIL_DB_PATH)
        self._counters = SILIdCounters()
        self._init_counters_from_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Obtiene conexión a la BD con foreign keys y WAL mode."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_counters_from_db(self) -> None:
        """Inicializa contadores desde los IDs existentes en BD."""
        conn = self._get_conn()
        try:
            tables_prefixes = [
                ("sen_vote_event", "SVE"),
                ("sen_motion", "SM"),
                ("sen_person", "SN"),
                ("sen_membership", "SMB"),
                ("sen_vote", "SV"),
                ("sen_count", "SC"),
                ("sen_organization", "SO"),
            ]
            prefix_to_key = {
                "SVE": "vote_event",
                "SM": "motion",
                "SN": "person",
                "SMB": "membership",
                "SV": "vote",
                "SC": "count",
                "SO": "organization",
            }
            for table, prefix in tables_prefixes:
                try:
                    row = conn.execute(
                        f"SELECT id FROM {table} ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if row:
                        num = int(row[0][len(prefix) :])
                        key = prefix_to_key[prefix]
                        setattr(self._counters, key, num)
                except Exception:
                    pass
        finally:
            conn.close()

    # ---- Schema ----

    def init_db(self) -> None:
        """Ejecuta las migraciones para agregar columnas SIL al schema."""
        conn = self._get_conn()
        try:
            # Agregar columnas SIL a sen_vote_event
            columns_vote_event = [
                ("sil_clave_asunto", "TEXT"),
                ("sil_clave_tramite", "TEXT"),
                ("sil_legislatura", "TEXT"),
                ("sil_sid", "TEXT"),
                ("scrape_status", "TEXT DEFAULT 'pending'"),
            ]

            for col_name, col_type in columns_vote_event:
                try:
                    conn.execute(
                        f"ALTER TABLE sen_vote_event ADD COLUMN {col_name} {col_type}"
                    )
                    logger.info(f"Columna {col_name} agregada a sen_vote_event")
                except sqlite3.OperationalError as e:
                    if "duplicate column" in str(e).lower():
                        logger.debug(f"Columna {col_name} ya existe")
                    else:
                        raise

            # Agregar columnas SIL a sen_motion
            columns_motion = [
                ("sil_tipo_asunto", "TEXT"),
                ("sil_camara", "TEXT DEFAULT 'Senado'"),
            ]

            for col_name, col_type in columns_motion:
                try:
                    conn.execute(
                        f"ALTER TABLE sen_motion ADD COLUMN {col_name} {col_type}"
                    )
                    logger.info(f"Columna {col_name} agregada a sen_motion")
                except sqlite3.OperationalError as e:
                    if "duplicate column" in str(e).lower():
                        logger.debug(f"Columna {col_name} ya existe")
                    else:
                        raise

            # Crear índices
            indices = [
                ("idx_sen_vote_sil_legislatura", "sen_vote_event", "sil_legislatura"),
                ("idx_sen_vote_sil_clave", "sen_vote_event", "sil_clave_asunto"),
            ]

            for idx_name, table, column in indices:
                try:
                    conn.execute(f"CREATE INDEX {idx_name} ON {table}({column})")
                    logger.info(f"Índice {idx_name} creado")
                except sqlite3.OperationalError as e:
                    if "already exists" in str(e).lower():
                        logger.debug(f"Índice {idx_name} ya existe")
                    else:
                        raise

            conn.commit()
            logger.info("Schema SIL inicializado correctamente")

        finally:
            conn.close()

    def get_status(self, clave_asunto: str, clave_tramite: str) -> Optional[str]:
        """Obtiene el estado de scrapeo de una votación.

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.

        Returns:
            Status actual o None si no existe.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT scrape_status FROM sen_vote_event
                   WHERE sil_clave_asunto = ? AND sil_clave_tramite = ?
                   LIMIT 1""",
                (clave_asunto, clave_tramite),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def update_status(
        self,
        clave_asunto: str,
        clave_tramite: str,
        status: str,
    ) -> bool:
        """Actualiza el estado de scrapeo de una votación.

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.
            status: Nuevo estado.

        Returns:
            True si se actualizó, False si no se encontró.
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE sen_vote_event
                   SET scrape_status = ?
                   WHERE sil_clave_asunto = ? AND sil_clave_tramite = ?""",
                (status, clave_asunto, clave_tramite),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ---- Entidades base ----

    def get_or_create_organization(
        self,
        abbr: str,
        nombre: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        """Obtiene o crea una organización (partido/bancada).

        Args:
            abbr: Abreviatura del partido.
            nombre: Nombre completo (si no se proporciona, usa abbr).
            conn: Conexión activa (crea nueva si None).

        Returns:
            ID de la organización (formato SO*).
        """
        close_conn = conn is None
        conn = conn or self._get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM sen_organization WHERE abbr = ?",
                (abbr,),
            ).fetchone()

            if row:
                return row[0]

            org_id = self._counters.next_id("SO")
            nombre_final = nombre or abbr
            conn.execute(
                """INSERT OR IGNORE INTO sen_organization
                   (id, nombre, clasificacion, abbr)
                   VALUES (?, ?, 'partido', ?)""",
                (org_id, nombre_final, abbr),
            )
            return org_id
        finally:
            if close_conn:
                conn.close()

    def get_or_create_person(
        self,
        nombre: str,
        genero: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> tuple[str, bool]:
        """Obtiene o crea una persona (senador).

        Args:
            nombre: Nombre completo del legislador.
            genero: Género inferido ("M", "F", "NB" o None).
            conn: Conexión activa.

        Returns:
            Tuple de (ID de la persona, True si fue creada nueva).
        """
        close_conn = conn is None
        conn = conn or self._get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM sen_person WHERE nombre = ?",
                (nombre,),
            ).fetchone()

            if row:
                return row[0], False

            person_id = self._counters.next_id("SN")
            conn.execute(
                """INSERT OR IGNORE INTO sen_person
                   (id, nombre, genero)
                   VALUES (?, ?, ?)""",
                (person_id, nombre, genero),
            )
            return person_id, True
        finally:
            if close_conn:
                conn.close()

    # ---- Carga de votaciones ----

    def upsert_votacion_index(
        self,
        votacion: SILVotacionIndex,
        sid: str,
    ) -> SILLoadResult:
        """Inserta o actualiza una votación desde el índice de resultados.

        Args:
            votacion: Datos de la votación del índice.
            sid: SID de sesión.

        Returns:
            SILLoadResult con estadísticas.
        """
        conn = self._get_conn()
        result = SILLoadResult(
            vote_event_id="",
            motion_id="",
            success=True,
        )

        try:
            conn.execute("BEGIN TRANSACTION")

            # Verificar si ya existe
            existing = conn.execute(
                """SELECT id FROM sen_vote_event
                   WHERE sil_clave_asunto = ? AND sil_clave_tramite = ?""",
                (votacion.clave_asunto, votacion.clave_tramite),
            ).fetchone()

            if existing:
                vote_event_id = existing[0]
                motion_id = conn.execute(
                    "SELECT motion_id FROM sen_vote_event WHERE id = ?",
                    (vote_event_id,),
                ).fetchone()[0]
            else:
                # Generar IDs
                motion_id = self._counters.next_id("SM")
                vote_event_id = self._counters.next_id("SVE")

                # Insertar motion
                conn.execute(
                    """INSERT INTO sen_motion
                       (id, text, result, date, sil_tipo_asunto, sil_camara)
                       VALUES (?, ?, ?, ?, ?, 'Senado')""",
                    (
                        motion_id,
                        votacion.titulo,
                        votacion.resultado,
                        votacion.fecha,
                        votacion.tipo_asunto,
                    ),
                )

                # Insertar vote_event
                conn.execute(
                    """INSERT INTO sen_vote_event
                       (id, motion_id, start_date, result, sil_clave_asunto,
                        sil_clave_tramite, sil_legislatura, sil_sid, scrape_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        vote_event_id,
                        motion_id,
                        votacion.fecha,
                        votacion.resultado,
                        votacion.clave_asunto,
                        votacion.clave_tramite,
                        votacion.legislature,
                        sid,
                        STATUS_PENDING,
                    ),
                )

            result.vote_event_id = vote_event_id
            result.motion_id = motion_id

            conn.execute("COMMIT")

        except Exception as e:
            conn.execute("ROLLBACK")
            result.success = False
            result.error = str(e)
            logger.error(f"Error upserting votacion: {e}")
        finally:
            conn.close()

        return result

    def upsert_votacion_detail(
        self,
        clave_asunto: str,
        clave_tramite: str,
        detalle: SILVotacionDetail,
        votos: Optional[SILVotosCompletos] = None,
    ) -> SILLoadResult:
        """Inserta o actualiza el detalle de una votación con votos.

        Args:
            clave_asunto: Clave del asunto.
            clave_tramite: Clave del trámite.
            detalle: Metadata de la votación.
            votos: Votos individuales (opcional).

        Returns:
            SILLoadResult con estadísticas.
        """
        conn = self._get_conn()
        result = SILLoadResult(
            vote_event_id="",
            motion_id="",
            success=True,
        )

        try:
            conn.execute("BEGIN TRANSACTION")

            # Obtener vote_event y motion existentes
            row = conn.execute(
                """SELECT ve.id, ve.motion_id FROM sen_vote_event ve
                   WHERE ve.sil_clave_asunto = ? AND ve.sil_clave_tramite = ?""",
                (clave_asunto, clave_tramite),
            ).fetchone()

            if not row:
                # Crear desde cero si no existe
                motion_id = self._counters.next_id("SM")
                vote_event_id = self._counters.next_id("SVE")

                conn.execute(
                    """INSERT INTO sen_motion
                       (id, text, result, date, sil_tipo_asunto, sil_camara)
                       VALUES (?, ?, ?, ?, ?, 'Senado')""",
                    (
                        motion_id,
                        detalle.titulo,
                        detalle.resultado,
                        detalle.fecha,
                        detalle.tipo_asunto,
                    ),
                )

                conn.execute(
                    """INSERT INTO sen_vote_event
                       (id, motion_id, start_date, result, sil_clave_asunto,
                        sil_clave_tramite, sil_legislatura, scrape_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        vote_event_id,
                        motion_id,
                        detalle.fecha,
                        detalle.resultado,
                        clave_asunto,
                        clave_tramite,
                        detalle.legislature,
                        STATUS_PENDING,
                    ),
                )
            else:
                vote_event_id = row[0]
                motion_id = row[1]

                # Actualizar motion con nuevo detalle
                conn.execute(
                    """UPDATE sen_motion
                       SET text = ?, result = ?, date = ?, sil_tipo_asunto = ?
                       WHERE id = ?""",
                    (
                        detalle.titulo,
                        detalle.resultado,
                        detalle.fecha,
                        detalle.tipo_asunto,
                        motion_id,
                    ),
                )

            result.vote_event_id = vote_event_id
            result.motion_id = motion_id

            # Actualizar conteos en sen_count
            self._upsert_counts(conn, vote_event_id, detalle)

            # Insertar votos individuales si se proporcionaron
            if votos:
                self._upsert_votes(conn, vote_event_id, votos, result)

            # Marcar como completado
            conn.execute(
                """UPDATE sen_vote_event
                   SET scrape_status = ?
                   WHERE id = ?""",
                (STATUS_COMPLETED, vote_event_id),
            )

            conn.execute("COMMIT")
            logger.info(
                f"Votación {clave_asunto}/{clave_tramite} upserted: {vote_event_id}"
            )

        except Exception as e:
            conn.execute("ROLLBACK")
            result.success = False
            result.error = str(e)
            logger.error(f"Error upserting detail: {e}")
        finally:
            conn.close()

        return result

    def _upsert_counts(
        self,
        conn: sqlite3.Connection,
        vote_event_id: str,
        detalle: SILVotacionDetail,
    ) -> None:
        """Inserta o actualiza conteos agregados."""
        counts = [
            ("a_favor", detalle.a_favor),
            ("en_contra", detalle.en_contra),
            ("abstencion", detalle.abstencion),
            ("ausente", detalle.ausente),
        ]

        for option, value in counts:
            if value > 0:
                # Verificar si existe
                existing = conn.execute(
                    """SELECT id FROM sen_count
                       WHERE vote_event_id = ? AND option = ?""",
                    (vote_event_id, option),
                ).fetchone()

                if existing:
                    conn.execute(
                        """UPDATE sen_count SET value = ? WHERE id = ?""",
                        (value, existing[0]),
                    )
                else:
                    count_id = self._counters.next_id("SC")
                    conn.execute(
                        """INSERT INTO sen_count
                           (id, vote_event_id, option, value)
                           VALUES (?, ?, ?, ?)""",
                        (count_id, vote_event_id, option, value),
                    )

    def _upsert_votes(
        self,
        conn: sqlite3.Connection,
        vote_event_id: str,
        votos: SILVotosCompletos,
        result: SILLoadResult,
    ) -> None:
        """Inserta votos individuales de legisladores."""
        for voto in votos.votos:
            # Obtener o crear persona
            person_id, is_new = self.get_or_create_person(
                voto.nombre,
                conn=conn,
            )
            if is_new:
                result.legislators_new += 1

            # Obtener o crear organización (partido)
            if voto.partido:
                self.get_or_create_organization(voto.partido, conn=conn)

            # Verificar si el voto ya existe
            existing = conn.execute(
                """SELECT id FROM sen_vote
                   WHERE vote_event_id = ? AND voter_id = ?""",
                (vote_event_id, person_id),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE sen_vote
                       SET option = ?, "group" = ?
                       WHERE id = ?""",
                    (voto.voto, voto.partido, existing[0]),
                )
                result.votos_actualizados += 1
            else:
                vote_id = self._counters.next_id("SV")
                conn.execute(
                    """INSERT INTO sen_vote
                       (id, vote_event_id, voter_id, option, "group")
                       VALUES (?, ?, ?, ?, ?)""",
                    (vote_id, vote_event_id, person_id, voto.voto, voto.partido),
                )
                result.votos_insertados += 1

    # ---- Utilidades ----

    def get_pending_votaciones(self, limit: int = 100) -> list[tuple]:
        """Obtiene votaciones pendientes de scrapeo.

        Args:
            limit: Número máximo de votaciones a retornar.

        Returns:
            Lista de tuples (clave_asunto, clave_tramite, vote_event_id).
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT sil_clave_asunto, sil_clave_tramite, id
                   FROM sen_vote_event
                   WHERE scrape_status IN (?, ?)
                   ORDER BY sil_legislatura, sil_clave_asunto
                   LIMIT ?""",
                (STATUS_PENDING, STATUS_FAILED, limit),
            ).fetchall()
            return rows
        finally:
            conn.close()

    def estadisticas(self) -> dict:
        """Retorna conteos actuales de todas las tablas sen_* y estados SIL.

        Returns:
            Dict con estadísticas.
        """
        conn = self._get_conn()
        try:
            stats: dict = {}

            # Tablas sen_*
            tablas = [
                "sen_organization",
                "sen_person",
                "sen_membership",
                "sen_vote_event",
                "sen_motion",
                "sen_vote",
                "sen_count",
            ]
            for tabla in tablas:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()
                    stats[tabla] = row[0]
                except sqlite3.OperationalError:
                    stats[tabla] = -1

            # Estados de scrapeo
            status_counts = conn.execute(
                """SELECT scrape_status, COUNT(*) as cnt
                   FROM sen_vote_event
                   WHERE scrape_status IS NOT NULL
                   GROUP BY scrape_status"""
            ).fetchall()
            stats["scrape_status"] = {row[0]: row[1] for row in status_counts}

            return stats
        finally:
            conn.close()

    def verificar_integridad(self) -> bool:
        """Verifica integridad referencial de la BD.

        Returns:
            True si no hay violaciones de FK, False si las hay.
        """
        conn = self._get_conn()
        try:
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
