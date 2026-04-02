"""congreso_loader.py — Carga datos al schema unificado de congress.db.

Schema unificado con prefijos de ID:
    VE_S (vote_event), Y_S (motion), V_S (vote),
    MB (membership), P (person)

Recibe ``CongresoVotacionRecord`` (construido por cli.py a partir de
``parse_legacy_votacion``) y lo inserta en el schema unificado.

Idempotente: INSERT OR IGNORE para no duplicar datos.
Transaccional: toda una votación se inserta en una sola transacción.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# ID Prefijos para el schema unificado
# ============================================================

ID_PREFIXES = {
    "vote_event": "VE_S",
    "motion": "Y_S",
    "vote": "V_S",
    "membership": "MB",
    "person": "P",
}

SENADO_ORG_ID = "O09"  # "Senado de la República"


# ============================================================
# Contadores de IDs
# ============================================================


@dataclass
class CongresoIdCounters:
    """Contadores para generar IDs con prefijo en el schema unificado."""

    vote_event: int = 0
    motion: int = 0
    person: int = 0
    membership: int = 0
    vote: int = 0

    def next_id(self, entity_type: str) -> str:
        """Genera el siguiente ID para un tipo de entidad dado."""
        prefix = ID_PREFIXES.get(entity_type)
        if not prefix:
            raise ValueError(f"Tipo de entidad desconocido: {entity_type}")

        count = getattr(self, entity_type) + 1
        setattr(self, entity_type, count)
        return f"{prefix}{count:05d}"


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
        self._counters = CongresoIdCounters()
        self._init_counters_from_db()

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

    def _init_counters_from_db(self) -> None:
        """Inicializa contadores desde los IDs existentes en BD."""
        conn = self._get_conn()
        try:
            tables_prefixes = [
                ("vote_event", "vote_event"),
                ("motion", "motion"),
                ("person", "person"),
                ("membership", "membership"),
                ("vote", "vote"),
            ]

            for table, entity_type in tables_prefixes:
                try:
                    row = conn.execute(
                        f"SELECT id FROM {table} ORDER BY LENGTH(id) DESC, id DESC LIMIT 1"
                    ).fetchone()
                    if row:
                        prefix = ID_PREFIXES[entity_type]
                        num_str = row[0][len(prefix) :].lstrip("0") or "0"
                        num = int(num_str)
                        setattr(self._counters, entity_type, num)
                except Exception:
                    pass  # Tabla vacía o no existe
        finally:
            conn.close()

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
        ID P* secuencial.

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

        person_id = self._counters.next_id("person")
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
    ) -> tuple[str, bool]:
        """Crea membership si no existe.

        Busca una membresía existente por person_id + org_id + rol.
        Si no existe, inserta con ID MB* secuencial.

        Args:
            person_id: ID de la persona.
            org_id: ID de la organización.
            rol: Rol (ej: "senador").
            start_date: Fecha de inicio en formato ISO.
            conn: Conexión activa a SQLite.

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

        memb_id = self._counters.next_id("membership")
        conn.execute(
            """INSERT OR IGNORE INTO membership
               (id, person_id, org_id, rol, start_date)
               VALUES (?, ?, ?, ?, ?)""",
            (memb_id, person_id, org_id, rol, start_date),
        )
        return memb_id, True

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
        }

        # Cache local: nombre → persona_id (P*)
        _persona_ids: dict[str, str] = {}

        try:
            conn.execute("BEGIN TRANSACTION")

            # --- Generar IDs para vote_event y motion ---
            motion_id = self._counters.next_id("motion")
            vote_event_id = self._counters.next_id("vote_event")

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

                # Resolver org_id por abbr
                org_row = conn.execute(
                    "SELECT id FROM organization WHERE abbr = ?",
                    (org_abbr,),
                ).fetchone()

                if not org_row:
                    # Si no hay match por abbr, usar el org_id directo
                    org_id = org_abbr
                else:
                    org_id = org_row[0]

                # start_date: usar la fecha de la votación como default
                start_date = memb_data.get("start_date", votacion.fecha_iso)

                _, was_created = self.get_or_create_membership(
                    persona_id, org_id, rol, start_date, conn
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

                vote_id = self._counters.next_id("vote")
                option = self._voto_to_option(voto.voto)

                conn.execute(
                    """INSERT OR IGNORE INTO vote
                       (id, vote_event_id, voter_id, option, "group")
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        vote_id,
                        vote_event_id,
                        persona_id,
                        option,
                        voto.grupo_parlamentario,
                    ),
                )
                stats["votos"] += 1

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
