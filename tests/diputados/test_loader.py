"""Tests para scraper_congreso.diputados.loader.Loader.

Usa BD temporal en disco (tempfile) con schema real y datos semilla mínimos.
Verifica upsert idempotente, creación de personas/memberships, y estadísticas.
"""

import json
import os
import sqlite3

import pytest

from scraper_congreso.diputados.loader import Loader
from scraper_congreso.diputados.transformers import (
    CountPopolo,
    MembershipPopolo,
    PersonPopolo,
    VotacionCompleta,
    VoteEventPopolo,
    VotePopolo,
)

# ---------------------------------------------------------------------------
# Path al schema SQL
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_SQL_PATH = os.path.join(PROJECT_ROOT, "db", "schema.sql")


# ---------------------------------------------------------------------------
# Helpers para construir datos de test
# ---------------------------------------------------------------------------

_counter = 0


def _next_suffix() -> int:
    """Genera un sufijo único para IDs de test (evita colisiones entre tests)."""
    global _counter
    _counter += 1
    return _counter


def make_vote_event(suffix: int = 1) -> VoteEventPopolo:
    """Crea un VoteEventPopolo de prueba."""
    return VoteEventPopolo(
        id=f"VE_D{suffix:05d}",
        motion_id=f"Y_D{suffix:05d}",
        start_date="2025-01-15",
        organization_id="O08",
        result="aprobada",
        sitl_id=1000 + suffix,
        voter_count=3,
        source_id=str(1000 + suffix),
        legislatura="LXVI",
        motion_text=f"Votación de prueba #{suffix}",
        motion_clasificacion="otra",
        motion_requirement="mayoria_simple",
        motion_result="aprobada",
        motion_date="2025-01-15",
        motion_legislative_session="LXVI Legislatura",
        motion_fuente_url="https://example.com/votacion",
    )


def make_person(idx: int) -> PersonPopolo:
    """Crea una PersonPopolo de prueba."""
    return PersonPopolo(
        id=f"P{idx:05d}",
        nombre=f"Diputado Test {idx}",
        identifiers_json=json.dumps({"sitl_id": 2000 + idx}),
        start_date="2024-09-01",
        end_date="2027-08-31",
    )


def make_membership(idx: int, person_id: str, org_id: str = "O01") -> MembershipPopolo:
    """Crea una MembershipPopolo de prueba."""
    return MembershipPopolo(
        id=f"M_D{idx:05d}",
        person_id=person_id,
        org_id=org_id,
        rol="diputado",
        label=f"Diputado Test Partido {idx}",
        start_date="2024-09-01",
        end_date=None,
    )


def make_vote(idx: int, vote_event_id: str, voter_id: str, option: str = "a_favor") -> VotePopolo:
    """Crea un VotePopolo de prueba."""
    return VotePopolo(
        id=f"V_D{idx:05d}",
        vote_event_id=vote_event_id,
        voter_id=voter_id,
        option=option,
        group="O01",
    )


def make_count(
    idx: int,
    vote_event_id: str,
    option: str = "a_favor",
    value: int = 3,
    group_id: str | None = None,
) -> CountPopolo:
    """Crea un CountPopolo de prueba."""
    return CountPopolo(
        id=f"C{idx:05d}",
        vote_event_id=vote_event_id,
        option=option,
        value=value,
        group_id=group_id,
    )


def make_votacion_completa(
    num_persons: int = 3,
    options: list[str] | None = None,
) -> VotacionCompleta:
    """Factory: crea una VotacionCompleta configurable.

    Args:
        num_persons: Número de personas/votos a crear.
        options: Lista de opciones para cada voto. Si None, todas "a_favor".
    """
    s = _next_suffix()

    ve = make_vote_event(s)
    persons = [make_person(s * 100 + i) for i in range(num_persons)]
    memberships = [make_membership(s * 100 + i, persons[i].id) for i in range(num_persons)]

    if options is None:
        options = ["a_favor"] * num_persons

    votes = [
        make_vote(s * 100 + i, ve.id, persons[i].id, options[i] if i < len(options) else "a_favor")
        for i in range(num_persons)
    ]

    counts = [
        make_count(s * 100, ve.id, "a_favor", num_persons, "O01"),
        make_count(s * 100 + 1, ve.id, "a_favor", num_persons, None),
    ]

    return VotacionCompleta(
        vote_event=ve,
        votes=votes,
        counts=counts,
        new_persons=persons,
        new_memberships=memberships,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Crea una BD temporal en disco con schema real y organizaciones semilla.

    Retorna el path (str) a la BD. Se elimina al final del test.
    """
    db_file = tmp_path / "test_diputados.db"

    # Crear BD y ejecutar schema
    conn = sqlite3.connect(str(db_file))
    with open(SCHEMA_SQL_PATH) as f:
        conn.executescript(f.read())

    # Datos semilla: organizaciones mínimas
    conn.executescript(
        """
        INSERT INTO organization (id, nombre, abbr, clasificacion)
        VALUES ('O08', 'Cámara de Diputados', 'DIPUTADOS', 'institucion');

        INSERT INTO organization (id, nombre, abbr, clasificacion)
        VALUES ('O01', 'MORENA', 'MORENA', 'partido');
        """
    )
    conn.commit()
    conn.close()

    yield str(db_file)

    # Cleanup: el tmp_path se limpia automáticamente por pytest


@pytest.fixture
def loader(tmp_db):
    """Loader apuntando a la BD temporal."""
    return Loader(db_path=tmp_db)


# ---------------------------------------------------------------------------
# Helper: contar registros en tabla
# ---------------------------------------------------------------------------


def count_rows(db_path: str, table: str) -> int:
    """Cuenta filas en una tabla de la BD."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# ===========================================================================
# Tests
# ===========================================================================


class TestUpsertVotacionInsert:
    """Test: insertar votación nueva completa."""

    def test_creates_motion(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "motion") == 1

    def test_creates_vote_event(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote_event") == 1

    def test_creates_votes(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=5)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote") == 5

    def test_creates_counts(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "count") == len(votacion.counts)

    def test_creates_persons(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=4)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "person") == 4

    def test_creates_memberships(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "membership") == 3

    def test_returns_correct_stats(self, loader):
        votacion = make_votacion_completa(num_persons=3)
        stats = loader.upsert_votacion(votacion)

        assert stats["vote_event"] == votacion.vote_event.id
        assert stats["votes"] == 3
        assert stats["counts"] == len(votacion.counts)
        assert stats["new_persons"] == 3
        assert stats["new_memberships"] == 3


class TestUpsertVotacionIdempotent:
    """Test: insertar la misma votación dos veces no duplica."""

    def test_no_duplicate_motion(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "motion") == 1

    def test_no_duplicate_vote_event(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote_event") == 1

    def test_no_duplicate_votes(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote") == 3

    def test_no_duplicate_counts(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "count") == len(votacion.counts)

    def test_no_duplicate_persons(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "person") == 3

    def test_no_duplicate_memberships(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "membership") == 3

    def test_second_upsert_same_stats_structure(self, loader):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)
        stats2 = loader.upsert_votacion(votacion)

        # El loader retorna stats de lo procesado (no necesariamente 0 nuevos),
        # pero la BD no duplica gracias a INSERT OR IGNORE
        assert "vote_event" in stats2
        assert "votes" in stats2
        assert "new_persons" in stats2


class TestUpsertVotacionWithNewPersons:
    """Test: insertar votación con personas nuevas."""

    def test_persons_created_with_correct_ids(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=2)
        loader.upsert_votacion(votacion)

        conn = sqlite3.connect(tmp_db)
        try:
            for person in votacion.new_persons:
                row = conn.execute(
                    "SELECT id, nombre FROM person WHERE id = ?", (person.id,)
                ).fetchone()
                assert row is not None, f"Persona {person.id} no encontrada"
                assert row[1] == person.nombre
        finally:
            conn.close()

    def test_persons_have_identifiers_json(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=1)
        loader.upsert_votacion(votacion)

        conn = sqlite3.connect(tmp_db)
        try:
            row = conn.execute(
                "SELECT identifiers_json FROM person WHERE id = ?",
                (votacion.new_persons[0].id,),
            ).fetchone()
            assert row is not None
            ids = json.loads(row[0])
            assert "sitl_id" in ids
        finally:
            conn.close()

    def test_memberships_associated_to_persons(self, loader, tmp_db):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)

        conn = sqlite3.connect(tmp_db)
        try:
            for membership in votacion.new_memberships:
                row = conn.execute(
                    "SELECT id, person_id, org_id, rol FROM membership WHERE id = ?",
                    (membership.id,),
                ).fetchone()
                assert row is not None, f"Membership {membership.id} no encontrada"
                assert row[1] == membership.person_id
                assert row[2] == membership.org_id
                assert row[3] == "diputado"
        finally:
            conn.close()


class TestUpsertVotacionWithExistingPersons:
    """Test: insertar votación que referencia personas ya existentes."""

    def test_no_duplicate_existing_persons(self, loader, tmp_db):
        # Pre-insertar personas
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO person (id, nombre, identifiers_json) VALUES (?, ?, ?)",
            ("P00999", "Diputado Existente 1", "{}"),
        )
        conn.commit()
        conn.close()

        assert count_rows(tmp_db, "person") == 1

        # Crear votación que incluye la persona existente como voter
        # pero la persona no está en new_persons (ya existe)
        ve = make_vote_event(99)
        votes = [
            make_vote(1, ve.id, "P00999", "a_favor"),
        ]
        counts = [make_count(1, ve.id, "a_favor", 1, None)]

        votacion = VotacionCompleta(
            vote_event=ve,
            votes=votes,
            counts=counts,
            new_persons=[],
            new_memberships=[],
        )

        loader.upsert_votacion(votacion)

        # La persona no se duplica
        assert count_rows(tmp_db, "person") == 1
        # El voto sí se inserta
        assert count_rows(tmp_db, "vote") == 1

    def test_vote_links_to_existing_person(self, loader, tmp_db):
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO person (id, nombre, identifiers_json) VALUES (?, ?, ?)",
            ("P00888", "Diputado Existente 2", "{}"),
        )
        conn.commit()
        conn.close()

        ve = make_vote_event(88)
        vote = make_vote(1, ve.id, "P00888", "en_contra")
        votacion = VotacionCompleta(
            vote_event=ve,
            votes=[vote],
            counts=[make_count(1, ve.id, "en_contra", 1, None)],
            new_persons=[],
            new_memberships=[],
        )

        loader.upsert_votacion(votacion)

        conn2 = sqlite3.connect(tmp_db)
        try:
            row = conn2.execute(
                'SELECT voter_id, option FROM vote WHERE voter_id = "P00888"'
            ).fetchone()
            assert row is not None
            assert row[0] == "P00888"
            assert row[1] == "en_contra"
        finally:
            conn2.close()


class TestEstadisticas:
    """Test: Loader.estadisticas() retorna conteos correctos."""

    def test_empty_db(self, loader):
        stats = loader.estadisticas()
        # Todas las tablas principales en 0 (excepto organization que tiene semilla)
        assert stats["person"] == 0
        assert stats["vote"] == 0
        assert stats["vote_event"] == 0
        assert stats["motion"] == 0
        assert stats["count"] == 0
        assert stats["membership"] == 0

    def test_after_insert(self, loader):
        votacion = make_votacion_completa(num_persons=4)
        loader.upsert_votacion(votacion)

        stats = loader.estadisticas()
        assert stats["person"] == 4
        assert stats["vote"] == 4
        assert stats["vote_event"] == 1
        assert stats["motion"] == 1
        assert stats["membership"] == 4
        assert stats["count"] == len(votacion.counts)

    def test_organization_has_seed_data(self, loader):
        stats = loader.estadisticas()
        assert stats["organization"] == 2  # O08 + O01


class TestVerificarIntegridad:
    """Test: Loader.verificar_integridad() en BD limpia."""

    def test_clean_db_returns_true(self, loader):
        assert loader.verificar_integridad() is True

    def test_after_insert_still_true(self, loader):
        votacion = make_votacion_completa(num_persons=3)
        loader.upsert_votacion(votacion)

        assert loader.verificar_integridad() is True
