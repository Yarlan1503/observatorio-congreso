"""congreso_loader.py — Carga datos al schema unificado de congress.db.

Schema unificado con prefijos de ID:
    VE_S (vote_event Senado), Y_S (motion Senado), V_S (vote Senado),
    M_S (membership Senado), P (person global)

Recibe ``CongresoVotacionRecord`` (construido por cli.py a partir de
``parse_legacy_votacion``) y lo inserta en el schema unificado.

Idempotente: INSERT OR IGNORE para no duplicar datos.
Transaccional: toda una votación se inserta en una sola transacción.
"""

import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ID generator compartido entre cámaras
_db_module_path = str(Path(__file__).resolve().parent.parent.parent / "db")
if _db_module_path not in sys.path:
    sys.path.insert(0, _db_module_path)
from id_generator import next_id, get_next_id_batch

logger = logging.getLogger(__name__)


SENADO_ORG_ID = "O09"  # "Senado de la República"


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

    senado_id: int  # ID original del portal (1-4690)
    fecha_iso: str  # yyyy-mm-dd
    descripcion: str  # Texto de la iniciativa
    pro_count: int
    contra_count: int
    abstention_count: int
    legislature: str = ""  # LX, LXI, ..., LXV (alias para compatibilidad)
    votos: list[CongresoVotoRecord] = field(default_factory=list)
    voto_personas_nuevas: list[dict] = field(default_factory=list)
    voto_membresias_nuevas: list[dict] = field(default_factory=list)


# ============================================================
# CongresoLoader
# ============================================================


class CongresoLoader:
    """Carga datos al schema unificado de congreso.db.

    Idempotente: INSERT OR IGNORE para no duplicar datos.
    Transaccional: toda una votación se inserta en una sola transacción.

    Args:
        db_path: Path a la BD. Por defecto ``db/congreso.db`` relativo
            al workspace root.
    """

    def __init__(self, db_path: str = "db/congreso.db"):
        self.db_path = self._resolve_db_path(db_path)

    def _resolve_db_path(self, db_path: str) -> Path:
        """Resuelve el path de la BD.

        Si es relativo, se interpreta desde el workspace root
        (/home/cachorro/Documentos/Congreso de la Union).

        Args:
            db_path: Path absoluto o relativo a la BD.

        Returns:
            Path absoluto a la BD.
        """
        p = Path(db_path)
        if p.is_absolute():
            return p
        # Workspace root
        workspace_root = Path("/home/cachorro/Documentos/Congreso de la Union")
        return workspace_root / p

    def _get_conn(self) -> sqlite3.Connection:
        """Obtiene conexión a la BD con foreign keys y WAL mode.

        Returns:
            Conexión SQLite configurada con FK=y, WAL mode,
            y timeout suficiente.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    # ---- Helpers de mapeo ----

    @staticmethod
    def _voto_to_option(voto: str) -> str:
        """Convierte el sentido del voto del portal al formato de la BD.

        PRO → a_favor
        CONTRA → en_contra
        ABSTENCIÓN (o variantes) → abstencion

        Args:
            voto: Sentido del voto del portal (PRO, CONTRA, ABSTENCIÓN).

        Returns:
            Opción en formato BD (a_favor, en_contra, abstencion).
        """
        s = voto.strip().upper()

        # Normalizar acentos para comparación
        import unicodedata

        nfkd = unicodedata.normalize("NFKD", s)
        sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))

        if "PRO" in sin_acentos and "ABSTEN" not in sin_acentos:
            return "a_favor"
        if "CONTRA" in sin_acentos:
            return "en_contra"
        if "ABSTENCION" in sin_acentos or "ABSTEN" in sin_acentos:
            return "abstencion"

        logger.warning(f"Sentido de voto no reconocido: '{voto}', usando 'abstencion'")
        return "abstencion"

    @staticmethod
    def _determinar_resultado(pro_count: int, contra_count: int) -> str:
        """Determina el resultado de una votación.

        - pro > contra → "aprobada"
        - pro < contra → "rechazada"
        - iguales → "empate"

        Args:
            pro_count: Votos a favor.
            contra_count: Votos en contra.

        Returns:
            Resultado: "aprobada", "rechazada" o "empate".
        """
        if pro_count > contra_count:
            return "aprobada"
        elif pro_count < contra_count:
            return "rechazada"
        else:
            return "empate"

    # ---- Entidades ----

    def get_or_create_person(
        self, nombre: str, genero: Optional[str], conn: sqlite3.Connection
    ) -> tuple[str, bool]:
        """Busca persona por nombre. Si no existe, crea nueva con ID P*.

        Busca por ``nombre`` exacto. Si no existe, inserta con un nuevo
        ID P* secuencial global (compartido entre Diputados y Senado).

        Args:
            nombre: Nombre completo del legislador.
            genero: Género ("M", "F", "NB" o ``None``).
            conn: Conexión activa a SQLite.

        Returns:
            Tuple de (ID de la persona, True si fue creada nueva).
        """
        row = conn.execute(
            "SELECT id FROM person WHERE nombre = ?",
            (nombre,),
        ).fetchone()

        if row:
            return row[0], False

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
        end_date: Optional[str] = None,
    ) -> tuple[str, bool]:
        """Crea membership si no existe.

        Busca una membresía existente por person_id + org_id + rol.
        Si no existe, inserta con ID M_S* secuencial.

        Args:
            person_id: ID de la persona.
            org_id: ID de la organización.
            rol: Rol (ej: "senador").
            start_date: Fecha de inicio en formato ISO.
            conn: Conexión activa a SQLite.
            label: Descripción legible del cargo (ej: "Senador, Guanajuato").
            end_date: Fecha de fin (None = vigente).

        Returns:
            Tuple de (ID de la membresía, True si fue creada nueva).
        """
        # Verificar si ya existe
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

    def get_or_create_organization(self, org_ref: str, conn: sqlite3.Connection) -> str:
        """Busca organización por abbr o ID. Si no existe, crea nueva.

        Args:
            org_ref: Abreviatura (MORENA, PAN) o ID (O09) de la organización.
            conn: Conexión activa a SQLite.

        Returns:
            ID de la organización (existente o nueva).
        """
        # Primero buscar por abbr
        row = conn.execute(
            "SELECT id FROM organization WHERE abbr = ?",
            (org_ref,),
        ).fetchone()
        if row:
            return row[0]

        # Buscar por ID directo
        row = conn.execute(
            "SELECT id FROM organization WHERE id = ?",
            (org_ref,),
        ).fetchone()
        if row:
            return row[0]

        # Buscar por nombre exacto
        row = conn.execute(
            "SELECT id FROM organization WHERE nombre = ?",
            (org_ref,),
        ).fetchone()
        if row:
            return row[0]

        # Crear nueva organización
        # Si empieza con "O" es un ID canónico, sino es una abreviatura
        if org_ref.startswith("O"):
            org_id = org_ref
            nombre = org_ref
            abbr = None
        else:
            org_id = org_ref
            nombre = org_ref
            abbr = org_ref

        clasificacion = "institucion" if org_ref == SENADO_ORG_ID else "partido"

        conn.execute(
            """INSERT OR IGNORE INTO organization
               (id, nombre, abbr, clasificacion)
               VALUES (?, ?, ?, ?)""",
            (org_id, nombre, abbr, clasificacion),
        )
        logger.info(f"Organización creada: {org_id} ({nombre})")
        return org_id

    # ---- Upsert principal ----

    def upsert_votacion(self, votacion: CongresoVotacionRecord) -> dict:
        """Inserta votación completa. Retorna estadísticas.

        Proceso (dentro de una transacción):
        1. Generar IDs: VE_S* para vote_event, Y_S* para motion
        2. INSERT OR IGNORE personas nuevas con IDs P*
        3. INSERT OR IGNORE membresías nuevas con IDs MB*
        4. INSERT INTO vote_event y motion
        5. INSERT OR IGNORE votos individuales con IDs V_S*
        6. COMMIT

        En caso de error: ROLLBACK.

        Args:
            votacion: :class:`CongresoVotacionRecord` con todos los datos.

        Returns:
            Dict con estadísticas:
            ``{
                "votacion_id": "VE_S00001",
                "motion_id": "Y_S00001",
                "votos": 118,
                "personas_nuevas": 5,
                "membresias_nuevas": 3
            }``
        """
        conn = self._get_conn()

        stats = {
            "votacion_id": "",
            "motion_id": "",
            "votos": 0,
            "personas_nuevas": 0,
            "membresias_nuevas": 0,
            "counts": 0,
        }

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
                        row = conn.execute(
                            "SELECT id FROM person WHERE nombre = ?",
                            (persona_ref,),
                        ).fetchone()
                        persona_id = row[0] if row else None
                else:
                    persona_id = persona_ref

                if persona_id is None:
                    logger.warning(
                        f"No se encontró persona para membresía: {memb_data}"
                    )
                    continue

                # Resolver org_id — crear si no existe
                org_id = self.get_or_create_organization(org_abbr, conn)

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

            # --- 3. Motion ---
            resultado = self._determinar_resultado(
                votacion.pro_count, votacion.contra_count
            )

            conn.execute(
                """INSERT OR IGNORE INTO motion
                   (id, texto, clasificacion, requirement, result, date, legislative_session)
                   VALUES (?, ?, 'ordinaria', 'mayoria_simple', ?, ?, ?)""",
                (
                    motion_id,
                    votacion.descripcion,
                    resultado,
                    votacion.fecha_iso,
                    votacion.legislature,
                ),
            )

            # --- 4. Vote_event ---
            # Asegurar que la organización del Senado exista
            self.get_or_create_organization(SENADO_ORG_ID, conn)

            conn.execute(
                """INSERT OR IGNORE INTO vote_event
                   (id, motion_id, start_date, organization_id, result,
                    voter_count, legislatura)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    vote_event_id,
                    motion_id,
                    votacion.fecha_iso,
                    SENADO_ORG_ID,
                    resultado,
                    votacion.pro_count
                    + votacion.contra_count
                    + votacion.abstention_count,
                    votacion.legislature or "",
                ),
            )

            # --- 5. Votos individuales ---
            for voto in votacion.votos:
                nombre = voto.nombre

                # Resolver persona_id
                persona_id = _persona_ids.get(nombre)
                if persona_id is None:
                    row = conn.execute(
                        "SELECT id FROM person WHERE nombre = ?",
                        (nombre,),
                    ).fetchone()
                    persona_id = row[0] if row else None

                if persona_id is None:
                    logger.warning(
                        f"Voto de '{nombre}' ignorado: persona no encontrada"
                    )
                    continue

                vote_id = next_id(conn, "vote", camara="S")
                option = self._voto_to_option(voto.voto)

                # Resolver vote.group: buscar org_id via membership
                # Si el parser no proporciona grupo (vacío), buscar membership
                group_id = voto.grupo_parlamentario
                if not group_id or group_id.strip() == "":
                    group_id = self._resolve_group_from_membership(
                        persona_id, votacion.fecha_iso, conn
                    )
                else:
                    # Normalizar: si es texto de partido, resolver a org_id
                    group_id = self.get_or_create_organization(group_id.strip(), conn)

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

            conn.execute("COMMIT")
            logger.info(
                f"Upsert completado: vote_event={vote_event_id}, "
                f"motion={motion_id}, {stats['votos']} votos, "
                f"{stats['personas_nuevas']} personas nuevas, "
                f"{stats['membresias_nuevas']} membresías nuevas"
            )

        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Error en upsert de votación {votacion.senado_id}: {e}")
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
    ) -> Optional[str]:
        """Resuelve el org_id de un legislador via su membership activa.

        Busca la membership más cercana en fecha para un senador.
        Si no encuentra, busca la membership más reciente (fallback).

        Args:
            person_id: ID de la persona.
            fecha_iso: Fecha de la votación (YYYY-MM-DD).
            conn: Conexión activa a SQLite.

        Returns:
            org_id del partido o None si no se puede resolver.
        """
        # Buscar membership activa en la fecha de la votación
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

        # Fallback: buscar la membership más cercana (anterior o posterior)
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
        """Inserta conteos por partido en la tabla count.

        Lee los conteos de CongresoVotacionRecord y los inserta
        en la tabla count con los org_ids canónicos.

        Args:
            vote_event_id: ID del vote_event.
            votacion: Registro de votación con conteos.
            conn: Conexión activa a SQLite.

        Returns:
            Número de counts insertados.
        """
        # Los conteos por partido no vienen en CongresoVotacionRecord
        # directamente (el parser legacy no extrae desglose por partido
        # de forma estructurada). Insertamos totales globales.
        counts_inserted = 0

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

    # ---- Integridad ----

    def verificar_integridad(self) -> bool:
        """Verifica integridad referencial de la BD.

        Returns:
            ``True`` si no hay violaciones de FK, ``False`` si las hay.
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

    def init_schema(self) -> None:
        """Verifica que el schema de congress.db exista.

        El schema ya existe en congreso.db (108MB, tablas verificadas).
        Este método es para compatibilidad con el CLI y verificación.
        """
        conn = self._get_conn()
        try:
            # Verificar que las tablas principales existen
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
                    logger.warning(f"Tabla '{tabla}' no existe en la BD")
            logger.info("Schema de congress.db verificado correctamente")
        finally:
            conn.close()

    def estadisticas(self) -> dict:
        """Retorna conteos actuales de todas las tablas relevantes.

        Returns:
            Dict con nombre de tabla → número de registros.
        """
        conn = self._get_conn()
        try:
            tablas = [
                "vote_event",
                "motion",
                "person",
                "membership",
                "vote",
            ]
            stats: dict[str, int] = {}
            for tabla in tablas:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()
                    stats[tabla] = row[0]
                except sqlite3.OperationalError:
                    stats[tabla] = -1  # Tabla no existe
            return stats
        finally:
            conn.close()
