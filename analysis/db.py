"""
db.py — Capa de acceso a datos para el módulo de análisis.

Centraliza la conexión a SQLite y proporciona queries parametrizadas
que eliminan la duplicación de patrones SQL en los módulos de analysis/.

Funciones:
    get_connection: conexión SQLite con PRAGMAs y row_factory configurados.
    get_vote_events: vote_events filtrados por legislatura, cámara, resultado.
    get_votes: votos filtrados por evento y/o votante, con JOIN opcional.
    get_persons: personas, filtrables por ID.
    get_organizations: organizaciones, filtrables por clasificación.
    get_memberships: memberships filtrados por persona, organización, rol.
"""

import sqlite3
from pathlib import Path

# Ruta por defecto: <proyecto>/db/congreso.db
DEFAULT_DB_PATH = Path(__file__).parent.parent / "db" / "congreso.db"


# ---------------------------------------------------------------------------
# Helper de conexión
# ---------------------------------------------------------------------------


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Retorna conexión SQLite con PRAGMAs y row_factory configurados.

    Configura:
        - journal_mode = WAL (mejor concurrencia read/write).
        - busy_timeout = 5000ms (reintenta si la BD está bloqueada).
        - foreign_keys = ON (respeta constraints FK).
        - row_factory = sqlite3.Row (acceso dict-like por nombre de columna).

    Args:
        db_path: Ruta a la BD. Si es ``None``, usa ``DEFAULT_DB_PATH``.

    Returns:
        Conexión SQLite lista para usar. El llamador debe cerrarla.
    """
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Queries parametrizadas
# ---------------------------------------------------------------------------


def get_vote_events(
    db_path: Path | str | None = None,
    legislatura: str | None = None,
    organization_id: str | None = None,
    result: str | None = None,
) -> list[sqlite3.Row]:
    """Retorna vote_events filtrados.

    Todos los parámetros de filtro son opcionales. Si se omiten
    (o son ``None``), no se aplica ese filtro.

    Args:
        db_path: Ruta a la BD. Si es ``None``, usa ``DEFAULT_DB_PATH``.
        legislatura: Filtrar por legislatura (ej: ``'LXVI'``).
        organization_id: Filtrar por cámara (``'O08'`` o ``'O09'``).
        result: Filtrar por resultado (``'aprobada'``, ``'rechazada'``, etc.).

    Returns:
        Lista de ``sqlite3.Row`` con todas las columnas de ``vote_event``.
    """
    conditions: list[str] = []
    params: list[str] = []

    if legislatura is not None:
        conditions.append("legislatura = ?")
        params.append(legislatura)

    if organization_id is not None:
        conditions.append("organization_id = ?")
        params.append(organization_id)

    if result is not None:
        conditions.append("result = ?")
        params.append(result)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM vote_event{where}"

    conn = get_connection(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def get_votes(
    db_path: Path | str | None = None,
    vote_event_id: str | None = None,
    voter_id: str | None = None,
    join_vote_event: bool = False,
) -> list[sqlite3.Row]:
    """Retorna votos filtrados.

    Args:
        db_path: Ruta a la BD. Si es ``None``, usa ``DEFAULT_DB_PATH``.
        vote_event_id: Filtrar por evento de votación.
        voter_id: Filtrar por votante.
        join_vote_event: Si es ``True``, hace ``JOIN`` con ``vote_event``
            para incluir columnas de ``legislatura`` y ``organization_id``.

    Returns:
        Lista de ``sqlite3.Row``.
    """
    if join_vote_event:
        base_query = (
            "SELECT v.*, ve.legislatura, ve.organization_id AS ve_organization_id "
            "FROM vote v JOIN vote_event ve ON v.vote_event_id = ve.id"
        )
    else:
        base_query = "SELECT * FROM vote"

    conditions: list[str] = []
    params: list[str] = []

    if vote_event_id is not None:
        prefix = "v." if join_vote_event else ""
        conditions.append(f"{prefix}vote_event_id = ?")
        params.append(vote_event_id)

    if voter_id is not None:
        prefix = "v." if join_vote_event else ""
        conditions.append(f"{prefix}voter_id = ?")
        params.append(voter_id)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"{base_query}{where}"

    conn = get_connection(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def get_persons(
    db_path: Path | str | None = None,
    person_id: str | None = None,
) -> list[sqlite3.Row]:
    """Retorna personas.

    Args:
        db_path: Ruta a la BD. Si es ``None``, usa ``DEFAULT_DB_PATH``.
        person_id: Si se proporciona, retorna solo esa persona.

    Returns:
        Lista de ``sqlite3.Row`` con columnas de ``person``.
    """
    if person_id is not None:
        query = "SELECT * FROM person WHERE id = ?"
        params: list[str] = [person_id]
    else:
        query = "SELECT * FROM person"
        params = []

    conn = get_connection(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def get_organizations(
    db_path: Path | str | None = None,
    clasificacion: str | None = None,
) -> list[sqlite3.Row]:
    """Retorna organizaciones.

    Args:
        db_path: Ruta a la BD. Si es ``None``, usa ``DEFAULT_DB_PATH``.
        clasificacion: Filtrar por clasificación (``'partido'``,
            ``'institucion'``, etc.).

    Returns:
        Lista de ``sqlite3.Row`` con columnas de ``organization``.
    """
    if clasificacion is not None:
        query = "SELECT * FROM organization WHERE clasificacion = ?"
        params: list[str] = [clasificacion]
    else:
        query = "SELECT * FROM organization"
        params = []

    conn = get_connection(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def get_memberships(
    db_path: Path | str | None = None,
    person_id: str | None = None,
    org_id: str | None = None,
    rol: str | None = None,
) -> list[sqlite3.Row]:
    """Retorna memberships filtrados.

    Todos los filtros son opcionales y se combinan con ``AND``.

    Args:
        db_path: Ruta a la BD. Si es ``None``, usa ``DEFAULT_DB_PATH``.
        person_id: Filtrar por persona.
        org_id: Filtrar por organización.
        rol: Filtrar por rol (``'diputado'``, ``'senador'``, etc.).

    Returns:
        Lista de ``sqlite3.Row`` con columnas de ``membership``.
    """
    conditions: list[str] = []
    params: list[str] = []

    if person_id is not None:
        conditions.append("person_id = ?")
        params.append(person_id)

    if org_id is not None:
        conditions.append("org_id = ?")
        params.append(org_id)

    if rol is not None:
        conditions.append("rol = ?")
        params.append(rol)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM membership{where}"

    conn = get_connection(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()
