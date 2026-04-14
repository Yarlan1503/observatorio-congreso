"""loader.py — Carga datos al schema unificado de congreso.db.

Schema unificado con prefijos de ID:
    VE_S (vote_event Senado), Y_S (motion Senado), V_S (vote Senado),
    M_S (membership Senado), P (person global)

Recibe ``CongresoVotacionRecord`` (construido por cli.py a partir de
``parse_lxvi_votacion``) y lo inserta en el schema unificado.

Idempotente: INSERT OR IGNORE para no duplicar datos.
Transaccional: toda una votación se inserta en una sola transacción.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from scraper_congreso.senadores.config import LXVI_VOTACION_URL_TEMPLATE, SENADO_ORG_ID
from scraper_congreso.utils.base_loader import BaseLoader
from scraper_congreso.utils.db_helpers import get_or_create_organization
from scraper_congreso.utils.db_utils import match_persona_por_nombre
from scraper_congreso.utils.id_generator import next_id
from scraper_congreso.utils.text_utils import determinar_requirement, determinar_tipo_motion

from .transformers import (
    determinar_resultado,
    voto_to_option,
)

# ============================================================
# Dataclasses para el schema unificado
# ============================================================


@dataclass
class CongresoVotoRecord:
    """Voto individual para el schema unificado.

    El campo ``voto`` viene del portal como PRO/CONTRA/ABSTENCIÓN
    y se mapea a a_favor/en_contra/abstencion en upsert.
    """

    nombre: str
    grupo_parlamentario: str
    voto: str  # PRO, CONTRA, ABSTENCIÓN (raw del portal)


@dataclass
class CongresoVotacionRecord:
    """Registro de votación para el schema unificado.

    Estructura que recibe ``CongresoLoader.upsert_votacion``.
    """

    senado_id: int  # ID original del portal (1-5070)
    fecha_iso: str  # yyyy-mm-dd
    descripcion: str  # Texto de la iniciativa
    pro_count: int
    contra_count: int
    abstention_count: int
    legislature: str = ""  # LX, LXI, ..., LXVI
    votos: list[CongresoVotoRecord] = field(default_factory=list)
    voto_personas_nuevas: list[dict] = field(default_factory=list)
    voto_membresias_nuevas: list[dict] = field(default_factory=list)
    counts_por_partido: list[dict] = field(default_factory=list)
    # Each dict: {"partido": str, "a_favor": int, "en_contra": int, "abstencion": int}
    # New fields for Fase 1 gaps:
    identifiers_json: str = ""  # JSON identifiers for vote_event
    requirement: str = ""  # mayoria_simple, mayoria_calificada, etc.
    fuente_url: str = ""  # URL fuente de la votación


# ============================================================
# CongresoLoader
# ============================================================


class CongresoLoader(BaseLoader):
    """Carga datos al schema unificado de congreso.db.

    Idempotente: INSERT OR IGNORE para no duplicar datos.
    Transaccional: toda una votación se inserta en una sola transacción.

    Args:
        db_path: Path a la BD. Por defecto ``db/congreso.db`` relativo
            al workspace root.
    """

    TABLES: ClassVar[list[str]] = [
        "vote_event",
        "motion",
        "person",
        "membership",
        "vote",
    ]

    def __init__(self, db_path: str = "db/congreso.db") -> None:
        super().__init__(self._resolve_db_path(db_path))

    def _resolve_db_path(self, db_path: str) -> Path:
        """Resuelve el path de la BD.

        Args:
            db_path: Path absoluto o relativo a la BD.

        Returns:
            Path absoluto a la BD.
        """
        p = Path(db_path)
        if p.is_absolute():
            return p
        project_root = Path(__file__).resolve().parent.parent.parent
        return project_root / p

    # ---- Entidades ----

    def get_or_create_person(
        self, nombre: str, genero: str | None, conn: sqlite3.Connection
    ) -> tuple[str, bool]:
        """Busca persona por nombre normalizado. Si no existe, crea nueva con ID P*.

        Busca por ``normalize_name()`` para evitar duplicados por variantes
        de acentos o espacios.

        Args:
            nombre: Nombre completo del legislador.
            genero: Género ("M", "F", "NB" o None).
            conn: Conexión activa a SQLite.

        Returns:
            Tuple de (ID de la persona, True si fue creada nueva).
        """
        # Primero buscar por nombre exacto
        row = conn.execute(
            "SELECT id FROM person WHERE nombre = ?",
            (nombre,),
        ).fetchone()

        if row:
            return row[0], False

        # Segundo: buscar por nombre normalizado (variantes con acentos)
        from scraper_congreso.utils.text_utils import normalize_name

        nombre_norm = normalize_name(nombre)
        rows = conn.execute("SELECT id, nombre FROM person").fetchall()
        for person_id, person_nombre in rows:
            if normalize_name(person_nombre) == nombre_norm:
                return person_id, False

        # No encontró: crear nueva
        person_id = next_id(conn, "person")
        conn.execute(
            """INSERT OR IGNORE INTO person
               (id, nombre, genero)
               VALUES (?, ?, ?)""",
            (person_id, nombre, genero),
        )
        return person_id, True

    def get_or_create_membership(
        self,
        person_id: str,
        org_id: str,
        rol: str,
        start_date: str,
        conn: sqlite3.Connection,
        label: str = "",
        end_date: str | None = None,
    ) -> tuple[str, bool]:
        """Crea membership si no existe."""
        row = conn.execute(
            """SELECT id FROM membership
               WHERE person_id = ? AND org_id = ? AND rol = ?""",
            (person_id, org_id, rol),
        ).fetchone()

        if row:
            return row[0], False

        memb_id = next_id(conn, "membership", camara="S")
        conn.execute(
            """INSERT OR IGNORE INTO membership
               (id, person_id, org_id, rol, label, start_date, end_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (memb_id, person_id, org_id, rol, label, start_date, end_date),
        )
        return memb_id, True

    # ---- Upsert principal ----

    def upsert_votacion(self, votacion: CongresoVotacionRecord) -> dict[str, int | str]:
        """Inserta votación completa. Retorna estadísticas.

        Proceso (dentro de una transacción):
        0. Verificar unicidad por source_id (deduplicación)
        1. Generar IDs: VE_S* para vote_event, Y_S* para motion
        2. INSERT OR IGNORE personas nuevas con IDs P*
        3. INSERT OR IGNORE membresías nuevas con IDs M_S*
        4. INSERT INTO vote_event y motion (con requirement, identifiers, fuente_url)
        5. INSERT OR IGNORE votos individuales con IDs V_S*
        6. INSERT counts
        7. COMMIT

        Args:
            votacion: CongresoVotacionRecord con todos los datos.

        Returns:
            Dict con estadísticas.
        """
        conn = self._get_conn()

        stats = {
            "votacion_id": "",
            "motion_id": "",
            "votos": 0,
            "personas_nuevas": 0,
            "membresias_nuevas": 0,
            "counts": 0,
            "status": "",
        }

        # --- 0. Deduplicación por source_id ---
        existing_ve = conn.execute(
            "SELECT id FROM vote_event WHERE source_id = ?",
            (str(votacion.senado_id),),
        ).fetchone()

        if existing_ve:
            self.logger.info(
                f"Votación senado_id={votacion.senado_id} ya existe "
                f"(vote_event={existing_ve[0]}), saltando."
            )
            conn.close()
            stats["status"] = "already_exists"
            stats["votacion_id"] = existing_ve[0]
            return stats

        # Cache local: nombre → persona_id (P*)
        _persona_ids: dict[str, str] = {}

        try:
            conn.execute("BEGIN TRANSACTION")

            # --- Generar IDs para vote_event y motion ---
            motion_id = next_id(conn, "motion", camara="S")
            vote_event_id = next_id(conn, "vote_event", camara="S")

            # --- 1. Personas nuevas ---
            for persona_data in votacion.voto_personas_nuevas:
                nombre = persona_data["nombre"]
                genero = persona_data.get("genero")

                person_id, was_created = self.get_or_create_person(nombre, genero, conn)
                _persona_ids[nombre] = person_id
                if was_created:
                    stats["personas_nuevas"] += 1

            # --- 2. Membresías nuevas ---
            for memb_data in votacion.voto_membresias_nuevas:
                persona_ref = memb_data["persona_id"]
                org_abbr = memb_data["organizacion_id"]
                rol = memb_data["rol"]

                # Resolver persona_id
                if isinstance(persona_ref, str):
                    persona_id = _persona_ids.get(persona_ref)
                    if persona_id is None:
                        persona_id = match_persona_por_nombre(persona_ref, conn)
                else:
                    persona_id = persona_ref

                if persona_id is None:
                    self.logger.warning(f"No se encontró persona para membresía: {memb_data}")
                    continue

                # Resolver org_id — crear si no existe
                org_id = get_or_create_organization(org_abbr, conn)

                # start_date: usar la fecha de la votación como default
                start_date = memb_data.get("start_date", votacion.fecha_iso)
                label = memb_data.get("label", f"Senador, {org_abbr}")
                end_date = memb_data.get("end_date")

                _, was_created = self.get_or_create_membership(
                    persona_id,
                    org_id,
                    rol,
                    start_date,
                    conn,
                    label=label,
                    end_date=end_date,
                )
                if was_created:
                    stats["membresias_nuevas"] += 1

            # --- 3. Motion con datos dinámicos ---
            # Determinar requirement y tipo del título
            requirement = votacion.requirement or determinar_requirement(votacion.descripcion)
            clasificacion = determinar_tipo_motion(votacion.descripcion)
            resultado = determinar_resultado(
                votacion.pro_count,
                votacion.contra_count,
                requirement,
                votacion.abstention_count,
            )

            # Fuente URL
            fuente_url = votacion.fuente_url
            if not fuente_url:
                fuente_url = LXVI_VOTACION_URL_TEMPLATE.format(id=votacion.senado_id)

            conn.execute(
                """INSERT OR IGNORE INTO motion
                   (id, texto, clasificacion, requirement, result, date, legislative_session, fuente_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    motion_id,
                    votacion.descripcion,
                    clasificacion,
                    requirement,
                    resultado,
                    votacion.fecha_iso,
                    votacion.legislature,
                    fuente_url,
                ),
            )

            # --- 4. Vote_event con identifiers_json y requirement ---
            # Asegurar que la organización del Senado exista
            get_or_create_organization(SENADO_ORG_ID, conn)

            # identifiers_json: formato estándar Popolo
            identifiers = votacion.identifiers_json
            if not identifiers:
                identifiers = json.dumps(
                    [{"scheme": "senado_gob_mx", "identifier": str(votacion.senado_id)}]
                )

            conn.execute(
                """INSERT OR IGNORE INTO vote_event
                   (id, motion_id, start_date, organization_id, result,
                    voter_count, legislatura, source_id, requirement, identifiers_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    vote_event_id,
                    motion_id,
                    votacion.fecha_iso,
                    SENADO_ORG_ID,
                    resultado,
                    votacion.pro_count + votacion.contra_count + votacion.abstention_count,
                    votacion.legislature or "",
                    str(votacion.senado_id),
                    requirement,
                    identifiers,
                ),
            )

            # --- 5. Votos individuales ---
            for voto in votacion.votos:
                nombre = voto.nombre

                # Resolver persona_id (por nombre normalizado)
                persona_id = _persona_ids.get(nombre)
                if persona_id is None:
                    persona_id = match_persona_por_nombre(nombre, conn)

                if persona_id is None:
                    self.logger.warning(f"Voto de '{nombre}' ignorado: persona no encontrada")
                    continue

                vote_id = next_id(conn, "vote", camara="S")
                option = voto_to_option(voto.voto)

                # Resolver vote.group: buscar org_id via membership
                group_id = voto.grupo_parlamentario
                if not group_id or group_id.strip() == "":
                    group_id = self._resolve_group_from_membership(
                        persona_id, votacion.fecha_iso, conn
                    )
                else:
                    group_id = get_or_create_organization(group_id.strip(), conn)

                conn.execute(
                    """INSERT OR IGNORE INTO vote
                       (id, vote_event_id, voter_id, option, "group")
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        vote_id,
                        vote_event_id,
                        persona_id,
                        option,
                        group_id,
                    ),
                )
                stats["votos"] += 1

            # --- 6. Counts ---
            counts_inserted = self._insert_counts(vote_event_id, votacion, conn)
            stats["counts"] = counts_inserted

            stats["votacion_id"] = vote_event_id
            stats["motion_id"] = motion_id
            stats["status"] = "success"

            conn.execute("COMMIT")
            self.logger.info(
                f"Upsert completado: vote_event={vote_event_id}, "
                f"motion={motion_id}, {stats['votos']} votos, "
                f"{stats['personas_nuevas']} personas nuevas, "
                f"{stats['membresias_nuevas']} membresías nuevas, "
                f"requirement={requirement}"
            )

        except Exception as e:
            conn.execute("ROLLBACK")
            self.logger.error(f"Error en upsert de votación {votacion.senado_id}: {e}")
            raise
        finally:
            conn.close()

        return stats

    # ---- Resolver vote.group desde memberships ----

    def _resolve_group_from_membership(
        self,
        person_id: str,
        fecha_iso: str,
        conn: sqlite3.Connection,
    ) -> str | None:
        """Resuelve el org_id de un legislador via su membership activa."""
        row = conn.execute(
            """SELECT org_id FROM membership
               WHERE person_id = ? AND rol = 'senador'
               AND start_date <= ?
               AND (end_date IS NULL OR end_date >= ?)
               ORDER BY start_date DESC
               LIMIT 1""",
            (person_id, fecha_iso, fecha_iso),
        ).fetchone()

        if row:
            return row[0]

        # Fallback: buscar la membership más cercana
        row = conn.execute(
            """SELECT org_id, ABS(julianday(start_date) - julianday(?)) as diff
               FROM membership
               WHERE person_id = ? AND rol = 'senador'
               ORDER BY diff ASC
               LIMIT 1""",
            (fecha_iso, person_id),
        ).fetchone()

        if row:
            return row[0]

        return None

    # ---- Insertar counts ----

    def _insert_counts(
        self,
        vote_event_id: str,
        votacion: "CongresoVotacionRecord",
        conn: sqlite3.Connection,
    ) -> int:
        """Inserta conteos por partido en la tabla count."""
        counts_inserted = 0

        if votacion.counts_por_partido:
            for cp in votacion.counts_por_partido:
                partido = cp["partido"]
                org_id = get_or_create_organization(partido, conn)

                options = [
                    ("a_favor", cp.get("a_favor", 0)),
                    ("en_contra", cp.get("en_contra", 0)),
                    ("abstencion", cp.get("abstencion", 0)),
                ]

                for option, value in options:
                    if value > 0:
                        count_id = next_id(conn, "count")
                        conn.execute(
                            """INSERT OR IGNORE INTO count
                               (id, vote_event_id, option, value, group_id)
                               VALUES (?, ?, ?, ?, ?)""",
                            (count_id, vote_event_id, option, value, org_id),
                        )
                        counts_inserted += 1

        # Totales globales
        totals = [
            ("a_favor", votacion.pro_count),
            ("en_contra", votacion.contra_count),
            ("abstencion", votacion.abstention_count),
        ]

        for option, value in totals:
            if value > 0:
                count_id = next_id(conn, "count")
                conn.execute(
                    """INSERT OR IGNORE INTO count
                       (id, vote_event_id, option, value, group_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (count_id, vote_event_id, option, value, None),
                )
                counts_inserted += 1

        return counts_inserted

    def init_schema(self) -> None:
        """Verifica que el schema y datos estáticos de congress.db existan."""
        conn = self._get_conn()
        try:
            tablas_requeridas = [
                "vote_event",
                "vote",
                "person",
                "membership",
                "motion",
                "organization",
            ]
            for tabla in tablas_requeridas:
                try:
                    conn.execute(f"SELECT 1 FROM {tabla} LIMIT 1")
                except sqlite3.OperationalError:
                    self.logger.warning(f"Tabla '{tabla}' no existe en la BD")

            existing = conn.execute(
                "SELECT id, nombre, abbr FROM organization WHERE id = 'O09'"
            ).fetchone()
            if existing:
                if existing[1] == "O09" or existing[2] is None:
                    conn.execute(
                        """UPDATE organization SET nombre = 'Senado de la República', abbr = 'SENADO'
                           WHERE id = 'O09'"""
                    )
                    conn.commit()
                    self.logger.info("Organización O09 actualizada: Senado de la República")
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO organization (id, nombre, abbr, clasificacion)
                       VALUES ('O09', 'Senado de la República', 'SENADO', 'institucion')"""
                )
                conn.commit()
                self.logger.info("Organización O09 creada: Senado de la República")

            self.logger.info("Schema de congress.db verificado correctamente")
        finally:
            conn.close()
