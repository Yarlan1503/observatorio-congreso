"""
tests/test_schema.py — Tests de verificación del schema SQL
Proyecto: Observatorio Congreso

Ejecutar con: pytest tests/test_schema.py
"""

import sqlite3
import pytest
from pathlib import Path

# Rutas a los schemas
SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"
SENADO_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "senado_schema.sql"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_main():
    """Conexión a BD SQLite en memoria con schema principal (Diputados)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    yield conn
    conn.close()


@pytest.fixture
def db_senado():
    """Conexión a BD SQLite en memoria con schema del Senado."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    senado_sql = SENADO_SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(senado_sql)
    yield conn
    conn.close()


# =============================================================================
# Tests de Schema Principal (Diputados)
# =============================================================================


def test_schema_carga_sin_errores(db_main):
    """Verifica que schema.sql carga sin errores de sintaxis."""
    # La creación del fixture ya valida que execudescript no lance excepciones
    cursor = db_main.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    expected_tables = {
        "area",
        "organization",
        "person",
        "membership",
        "post",
        "motion",
        "vote_event",
        "vote",
        "count",
        "actor_externo",
        "relacion_poder",
        "evento_politico",
    }
    assert expected_tables.issubset(tables), (
        f"Faltan tablas: {expected_tables - tables}"
    )


def test_foreign_keys_habilitadas(db_main):
    """Verifica que PRAGMA foreign_keys retorna ON después de cargar schema."""
    cursor = db_main.execute("PRAGMA foreign_keys")
    fk_enabled = cursor.fetchone()[0]
    assert fk_enabled == 1, "Foreign keys no están habilitadas"


def test_vote_event_requires_motion(db_main):
    """Insertar vote_event sin motion_id debe fallar (FK violation)."""
    # Primero crear la organización que vote_event necesita
    db_main.execute(
        "INSERT INTO organization (id, nombre, clasificacion) VALUES ('O1', 'Test', 'partido')"
    )
    db_main.execute(
        "INSERT INTO motion (id, texto, clasificacion, requirement) VALUES ('Y1', 'Test', 'ordinaria', 'mayoria_simple')"
    )

    # Intentar insertar vote_event sin motion_id (motion_id es NOT NULL)
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO vote_event (id, start_date, organization_id)
            VALUES ('VE1', '2024-01-01', 'O1')
        """)
    assert "NOT NULL constraint failed: vote_event.motion_id" in str(exc_info.value)


def test_vote_requires_voter_and_event(db_main):
    """Insertar vote sin vote_event_id o voter_id debe fallar."""
    # Setup: crear las entidades necesarias (organization primero por FK)
    db_main.execute(
        "INSERT INTO organization (id, nombre, clasificacion) VALUES ('O1', 'Test', 'partido')"
    )
    db_main.execute("INSERT INTO person (id, nombre) VALUES ('P1', 'Test Person')")
    db_main.execute("""
        INSERT INTO motion (id, texto, clasificacion, requirement)
        VALUES ('Y1', 'Test motion', 'ordinaria', 'mayoria_simple')
    """)
    db_main.execute("""
        INSERT INTO vote_event (id, motion_id, start_date, organization_id)
        VALUES ('VE1', 'Y1', '2024-01-01', 'O1')
    """)

    # Intentar sin vote_event_id
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO vote (id, voter_id, option)
            VALUES ('V1', 'P1', 'a_favor')
        """)
    assert "NOT NULL constraint failed: vote.vote_event_id" in str(exc_info.value)

    # Intentar sin voter_id
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO vote (id, vote_event_id, option)
            VALUES ('V2', 'VE1', 'a_favor')
        """)
    assert "NOT NULL constraint failed: vote.voter_id" in str(exc_info.value)


def test_membership_requires_person_and_org(db_main):
    """Insertar membership sin person_id o org_id debe fallar."""
    # Intentar sin person_id
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO membership (id, org_id, rol, start_date)
            VALUES ('M1', 'O1', 'diputado', '2024-01-01')
        """)
    assert "NOT NULL constraint failed: membership.person_id" in str(exc_info.value)

    # Intentar sin org_id
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO membership (id, person_id, rol, start_date)
            VALUES ('M2', 'P1', 'diputado', '2024-01-01')
        """)
    assert "NOT NULL constraint failed: membership.org_id" in str(exc_info.value)


def test_trigger_person_dates(db_main):
    """Insertar person con end_date < start_date debe fallar (trigger)."""
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO person (id, nombre, start_date, end_date)
            VALUES ('P1', 'Test', '2024-12-31', '2024-01-01')
        """)
    assert "end_date debe ser >= start_date en person" in str(exc_info.value)


def test_trigger_membership_dates(db_main):
    """Insertar membership con end_date < start_date debe fallar (trigger)."""
    # Primero crear las entidades necesarias
    db_main.execute("INSERT INTO person (id, nombre) VALUES ('P1', 'Test Person')")
    db_main.execute(
        "INSERT INTO organization (id, nombre, clasificacion) VALUES ('O1', 'Test', 'partido')"
    )

    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date)
            VALUES ('M1', 'P1', 'O1', 'diputado', '2024-12-31', '2024-01-01')
        """)
    assert "end_date debe ser >= start_date en membership" in str(exc_info.value)


def test_count_value_non_negative(db_main):
    """Insertar count con value < 0 debe fallar (CHECK constraint)."""
    # Setup: crear las entidades necesarias (organization primero por FK)
    db_main.execute(
        "INSERT INTO organization (id, nombre, clasificacion) VALUES ('O1', 'Test', 'partido')"
    )
    db_main.execute("""
        INSERT INTO motion (id, texto, clasificacion, requirement)
        VALUES ('Y1', 'Test motion', 'ordinaria', 'mayoria_simple')
    """)
    db_main.execute("""
        INSERT INTO vote_event (id, motion_id, start_date, organization_id)
        VALUES ('VE1', 'Y1', '2024-01-01', 'O1')
    """)

    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_main.execute("""
            INSERT INTO count (id, vote_event_id, option, value, group_id)
            VALUES ('C1', 'VE1', 'a_favor', -1, 'O1')
        """)
    assert "CHECK constraint failed: value >= 0" in str(
        exc_info.value
    ) or "CHECK constraint failed" in str(exc_info.value)


# =============================================================================
# Tests de Schema Senado
# =============================================================================


def test_senado_schema_carga_sin_errores(db_senado):
    """Verifica que senado_schema.sql carga sin errores."""
    cursor = db_senado.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    expected_tables = {
        "senado_organizacion",
        "senado_persona",
        "senado_membresia",
        "senado_votacion",
        "senado_voto",
    }
    assert expected_tables.issubset(tables), (
        f"Faltan tablas: {expected_tables - tables}"
    )


def test_senado_voto_unique_per_votacion(db_senado):
    """Dos votos del mismo persona_id en same votacion_id debe fallar (UNIQUE constraint)."""
    # Setup: crear organización, persona y votación
    db_senado.execute("""
        INSERT INTO senado_organizacion (nombre, clasificacion, abreviatura)
        VALUES ('Morena', 'partido', 'MORENA')
    """)
    db_senado.execute("""
        INSERT INTO senado_persona (nombre, nombre_normalizado)
        VALUES ('Test Senator', 'TEST SENATOR')
    """)
    db_senado.execute("""
        INSERT INTO senado_votacion (id, titulo, fuente_url)
        VALUES (1, 'Test Voting', 'https://senado.gob.mx/votacion/1')
    """)

    # Primer voto - debería succeeder
    db_senado.execute("""
        INSERT INTO senado_voto (votacion_id, persona_id, opcion, grupo)
        VALUES (1, 1, 'a_favor', 'MORENA')
    """)

    # Segundo voto del mismo persona_id en la misma votacion_id - debe fallar
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db_senado.execute("""
            INSERT INTO senado_voto (votacion_id, persona_id, opcion, grupo)
            VALUES (1, 1, 'en_contra', 'MORENA')
        """)
    assert "UNIQUE constraint failed: senado_voto.votacion_id" in str(
        exc_info.value
    ) or "UNIQUE constraint failed" in str(exc_info.value)
