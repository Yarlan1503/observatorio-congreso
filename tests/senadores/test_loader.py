"""Tests para scraper_congreso.senadores.votaciones.loader.CongresoLoader.

Usa BD temporal en disco (tempfile) con schema real y datos semilla mínimos.
Verifica upsert idempotente, get_or_create person/membership, y estadísticas.
"""

import os
import sqlite3

import pytest

from scraper_congreso.senadores.votaciones.loader import (
    CongresoLoader,
    CongresoVotacionRecord,
    CongresoVotoRecord,
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
    """Genera un sufijo único para IDs de test."""
    global _counter
    _counter += 1
    return _counter


def make_voto_record(
    nombre: str = "Senador Test",
    grupo: str = "MORENA",
    voto: str = "PRO",
) -> CongresoVotoRecord:
    """Crea un CongresoVotoRecord de prueba."""
    return CongresoVotoRecord(
        nombre=nombre,
        grupo_parlamentario=grupo,
        voto=voto,
    )


def make_votacion_record(
    senado_id: int | None = None,
    num_votos: int = 3,
    votos_data: list[dict] | None = None,
    with_personas_nuevas: bool = True,
    with_membresias_nuevas: bool = True,
    with_counts: bool = True,
) -> CongresoVotacionRecord:
    """Factory: crea un CongresoVotacionRecord configurable.

    Args:
        senado_id: ID del portal del Senado. Auto-generado si None.
        num_votos: Número de votos a crear (si votos_data es None).
        votos_data: Lista de dicts con nombre, grupo, voto para cada voto.
        with_personas_nuevas: Si incluir voto_personas_nuevas.
        with_membresias_nuevas: Si incluir voto_membresias_nuevas.
        with_counts: Si incluir counts_por_partido.
    """
    s = _next_suffix()
    sid = senado_id or (5000 + s)

    if votos_data is None:
        votos_data = [
            {"nombre": f"Senador Test {s}_{i}", "grupo": "MORENA", "voto": "PRO"}
            for i in range(num_votos)
        ]

    votos = [
        CongresoVotoRecord(nombre=v["nombre"], grupo_parlamentario=v["grupo"], voto=v["voto"])
        for v in votos_data
    ]

    personas_nuevas = []
    if with_personas_nuevas:
        for v in votos_data:
            personas_nuevas.append(
                {
                    "nombre": v["nombre"],
                    "genero": None,
                }
            )

    membresias_nuevas = []
    if with_membresias_nuevas:
        for _i, v in enumerate(votos_data):
            membresias_nuevas.append(
                {
                    "persona_id": v["nombre"],  # Se resuelve por nombre
                    "organizacion_id": v["grupo"],
                    "rol": "senador",
                    "start_date": "2024-09-01",
                    "label": f"Senador, {v['grupo']}",
                }
            )

    counts = []
    if with_counts:
        counts.append(
            {
                "partido": "MORENA",
                "a_favor": num_votos,
                "en_contra": 0,
                "abstencion": 0,
            }
        )

    return CongresoVotacionRecord(
        senado_id=sid,
        fecha_iso="2025-03-15",
        descripcion=f"Iniciativa de prueba senado #{s}",
        pro_count=num_votos,
        contra_count=0,
        abstention_count=0,
        legislature="LXVI",
        votos=votos,
        voto_personas_nuevas=personas_nuevas,
        voto_membresias_nuevas=membresias_nuevas,
        counts_por_partido=counts,
        requirement="mayoria_simple",
        fuente_url="https://example.com/senado/votacion",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Crea una BD temporal con schema real y organizaciones semilla."""
    db_file = tmp_path / "test_senadores.db"

    conn = sqlite3.connect(str(db_file))
    with open(SCHEMA_SQL_PATH) as f:
        conn.executescript(f.read())

    # Datos semilla: organizaciones mínimas
    conn.executescript(
        """
        INSERT INTO organization (id, nombre, abbr, clasificacion)
        VALUES ('O09', 'Senado de la República', 'SENADO', 'institucion');

        INSERT INTO organization (id, nombre, abbr, clasificacion)
        VALUES ('O01', 'MORENA', 'MORENA', 'partido');
        """
    )
    conn.commit()
    conn.close()

    yield str(db_file)


@pytest.fixture
def loader(tmp_db):
    """CongresoLoader apuntando a la BD temporal."""
    return CongresoLoader(db_path=tmp_db)


# ---------------------------------------------------------------------------
# Helper
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
        votacion = make_votacion_record(num_votos=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "motion") == 1

    def test_creates_vote_event(self, loader, tmp_db):
        votacion = make_votacion_record(num_votos=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote_event") == 1

    def test_creates_votes(self, loader, tmp_db):
        votacion = make_votacion_record(num_votos=5)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote") == 5

    def test_creates_persons(self, loader, tmp_db):
        votacion = make_votacion_record(num_votos=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "person") == 3

    def test_creates_memberships(self, loader, tmp_db):
        votacion = make_votacion_record(num_votos=3)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "membership") == 3

    def test_creates_counts(self, loader, tmp_db):
        votacion = make_votacion_record(num_votos=3)
        loader.upsert_votacion(votacion)

        # Counts: por partido (1 partido × 1 option con value > 0) + 1 total global
        assert count_rows(tmp_db, "count") >= 1

    def test_returns_correct_stats(self, loader):
        votacion = make_votacion_record(num_votos=3)
        stats = loader.upsert_votacion(votacion)

        assert stats["status"] == "success"
        assert stats["votos"] == 3
        assert stats["personas_nuevas"] == 3
        assert stats["membresias_nuevas"] == 3
        assert "votacion_id" in stats
        assert "motion_id" in stats

    def test_vote_event_has_source_id(self, loader, tmp_db):
        votacion = make_votacion_record(senado_id=5555)
        loader.upsert_votacion(votacion)

        conn = sqlite3.connect(tmp_db)
        try:
            row = conn.execute(
                "SELECT source_id FROM vote_event WHERE source_id = '5555'"
            ).fetchone()
            assert row is not None
            assert row[0] == "5555"
        finally:
            conn.close()


class TestUpsertVotacionIdempotent:
    """Test: insertar la misma votación dos veces no duplica (via source_id dedup)."""

    def test_second_upsert_skipped(self, loader):
        votacion = make_votacion_record(senado_id=6001, num_votos=3)
        stats1 = loader.upsert_votacion(votacion)

        assert stats1["status"] == "success"

        stats2 = loader.upsert_votacion(votacion)
        assert stats2["status"] == "already_exists"

    def test_no_duplicate_vote_events(self, loader, tmp_db):
        votacion = make_votacion_record(senado_id=6002, num_votos=2)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote_event") == 1

    def test_no_duplicate_votes(self, loader, tmp_db):
        votacion = make_votacion_record(senado_id=6003, num_votos=3)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "vote") == 3

    def test_no_duplicate_motions(self, loader, tmp_db):
        votacion = make_votacion_record(senado_id=6004, num_votos=2)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        assert count_rows(tmp_db, "motion") == 1


class TestGetOrCreatePersonNew:
    """Test: CongresoLoader.get_or_create_person con persona nueva."""

    def test_creates_person_with_p_prefix(self, loader, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            person_id, was_created = loader.get_or_create_person("Senadora Nueva Test", "F", conn)
            conn.commit()

            assert was_created is True
            assert person_id.startswith("P")

            # Verificar en BD
            row = conn.execute(
                "SELECT id, nombre, genero FROM person WHERE id = ?", (person_id,)
            ).fetchone()
            assert row is not None
            assert row[1] == "Senadora Nueva Test"
            assert row[2] == "F"
        finally:
            conn.close()

    def test_multiple_persons_get_sequential_ids(self, loader, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            id1, c1 = loader.get_or_create_person("Persona Alpha", None, conn)
            conn.commit()
            id2, c2 = loader.get_or_create_person("Persona Beta", None, conn)
            conn.commit()

            assert c1 is True
            assert c2 is True
            assert id1 != id2
            assert count_rows(tmp_db, "person") == 2
        finally:
            conn.close()


class TestGetOrCreatePersonExisting:
    """Test: CongresoLoader.get_or_create_person con persona existente."""

    def test_reuses_existing_person_by_exact_name(self, loader, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            # Crear persona
            id1, c1 = loader.get_or_create_person("Senador Existente", None, conn)
            conn.commit()

            # Buscar la misma persona
            id2, c2 = loader.get_or_create_person("Senador Existente", None, conn)

            assert c1 is True
            assert c2 is False
            assert id1 == id2
            assert count_rows(tmp_db, "person") == 1
        finally:
            conn.close()

    def test_reuses_existing_person_by_normalized_name(self, loader, tmp_db):
        """Busca por nombre normalizado (sin acentos)."""
        conn = sqlite3.connect(tmp_db)
        try:
            id1, _c1 = loader.get_or_create_person("José María González", None, conn)
            conn.commit()

            # Mismo nombre sin acento
            id2, c2 = loader.get_or_create_person("Jose Maria Gonzalez", None, conn)

            assert c2 is False
            assert id1 == id2
        finally:
            conn.close()


class TestGetOrCreateMembership:
    """Test: CongresoLoader.get_or_create_membership."""

    def test_creates_new_membership(self, loader, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            # Primero crear persona
            person_id, _ = loader.get_or_create_person("Senador Memb Test", None, conn)
            conn.commit()

            memb_id, was_created = loader.get_or_create_membership(
                person_id, "O01", "senador", "2024-09-01", conn, label="Senador MORENA"
            )
            conn.commit()

            assert was_created is True
            assert memb_id.startswith("M_S")

            # Verificar en BD
            row = conn.execute(
                "SELECT id, person_id, org_id, rol FROM membership WHERE id = ?", (memb_id,)
            ).fetchone()
            assert row is not None
            assert row[1] == person_id
            assert row[2] == "O01"
            assert row[3] == "senador"
        finally:
            conn.close()

    def test_reuses_existing_membership(self, loader, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            person_id, _ = loader.get_or_create_person("Senador Memb Dup", None, conn)
            conn.commit()

            id1, c1 = loader.get_or_create_membership(
                person_id, "O01", "senador", "2024-09-01", conn
            )
            conn.commit()

            id2, c2 = loader.get_or_create_membership(
                person_id, "O01", "senador", "2024-09-01", conn
            )

            assert c1 is True
            assert c2 is False
            assert id1 == id2
            assert count_rows(tmp_db, "membership") == 1
        finally:
            conn.close()


class TestVerificarIntegridad:
    """Test: CongresoLoader.verificar_integridad() en BD limpia."""

    def test_clean_db_returns_true(self, loader):
        assert loader.verificar_integridad() is True

    def test_after_insert_still_true(self, loader):
        votacion = make_votacion_record(num_votos=3)
        loader.upsert_votacion(votacion)

        assert loader.verificar_integridad() is True


class TestEstadisticas:
    """Test: CongresoLoader.estadisticas() retorna conteos correctos."""

    def test_empty_db(self, loader):
        stats = loader.estadisticas()
        assert stats["person"] == 0
        assert stats["vote"] == 0
        assert stats["_vote_event"] if "_vote_event" in stats else stats.get("vote_event", 0) == 0
        assert stats["motion"] == 0
        assert stats["membership"] == 0

    def test_after_insert(self, loader):
        votacion = make_votacion_record(num_votos=4)
        loader.upsert_votacion(votacion)

        stats = loader.estadisticas()
        assert stats["person"] == 4
        assert stats["vote"] == 4
        assert stats["vote_event"] == 1
        assert stats["motion"] == 1
        assert stats["membership"] == 4

    def test_after_idempotent_insert(self, loader):
        votacion = make_votacion_record(senado_id=7777, num_votos=2)
        loader.upsert_votacion(votacion)
        loader.upsert_votacion(votacion)

        stats = loader.estadisticas()
        assert stats["vote_event"] == 1
        assert stats["vote"] == 2
        assert stats["person"] == 2


class TestInitSchema:
    """Test: CongresoLoader.init_schema() verifica schema correctamente."""

    def test_init_schema_creates_o09(self, loader, tmp_db):
        # Eliminar O09 para probar que init_schema la recrea
        conn = sqlite3.connect(tmp_db)
        conn.execute("DELETE FROM organization WHERE id = 'O09'")
        conn.commit()
        conn.close()

        loader.init_schema()

        conn = sqlite3.connect(tmp_db)
        try:
            row = conn.execute("SELECT nombre, abbr FROM organization WHERE id = 'O09'").fetchone()
            assert row is not None
            assert row[0] == "Senado de la República"
            assert row[1] == "SENADO"
        finally:
            conn.close()

    def test_init_schema_idempotent(self, loader, tmp_db):
        # Ejecutar init_schema dos veces
        loader.init_schema()
        loader.init_schema()

        conn = sqlite3.connect(tmp_db)
        try:
            row = conn.execute("SELECT COUNT(*) FROM organization WHERE id = 'O09'").fetchone()
            assert row[0] == 1  # No duplica
        finally:
            conn.close()
