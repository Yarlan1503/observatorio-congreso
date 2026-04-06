"""
test_helpers.py — Tests unitarios para db/helpers.py.

Cubre get_or_create_organization(): creación, lookup, blocked names,
validación de fechas, ID generation y case-insensitive lookup.

Uso:
    pytest db/tests/test_helpers.py -v
"""

import sqlite3

import pytest

from db.helpers import get_or_create_organization


@pytest.fixture
def db_conn(tmp_path):
    """Crea BD SQLite temporal con tabla organization."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE organization (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            abbr TEXT,
            clasificacion TEXT NOT NULL CHECK(
                clasificacion IN ('partido', 'bancada', 'coalicion',
                    'gobierno', 'institucion', 'otro')
            ),
            fundacion TEXT,
            disolucion TEXT
        )
    """)
    # Seed: organización existente
    conn.execute(
        "INSERT INTO organization (id, nombre, abbr, clasificacion) VALUES (?, ?, ?, ?)",
        ("O01", "Morena", "MORENA", "partido"),
    )
    conn.commit()
    yield conn
    conn.close()


class TestGetOrCreateOrganizationBasic:
    """Tests básicos de get_or_create_organization()."""

    def test_crea_nueva_organizacion(self, db_conn):
        """Organización nueva se crea correctamente."""
        org_id = get_or_create_organization("PAN", db_conn)
        db_conn.commit()

        assert org_id is not None
        row = db_conn.execute(
            "SELECT id, nombre, abbr, clasificacion FROM organization WHERE id = ?",
            (org_id,),
        ).fetchone()
        assert row is not None
        assert row[1] == "PAN"
        assert row[2] == "PAN"
        assert row[3] == "partido"

    def test_no_duplica_nombre_existente(self, db_conn):
        """Organización existente no se duplica (mismo nombre)."""
        id1 = get_or_create_organization("Morena", db_conn)
        id2 = get_or_create_organization("Morena", db_conn)
        assert id1 == id2 == "O01"

    def test_no_duplica_abbr_existente(self, db_conn):
        """Lookup por abbr existente."""
        org_id = get_or_create_organization("MORENA", db_conn)
        assert org_id == "O01"

    def test_lookup_por_id_directo(self, db_conn):
        """Lookup directo por ID."""
        org_id = get_or_create_organization("O01", db_conn)
        assert org_id == "O01"

    def test_id_sequential(self, db_conn):
        """ID generation secuencial (O##)."""
        id1 = get_or_create_organization("PAN", db_conn)
        db_conn.commit()
        id2 = get_or_create_organization("PRI", db_conn)
        db_conn.commit()

        assert id1 == "O02"
        assert id2 == "O03"


class TestGetOrCreateOrganizationBlocked:
    """Tests de validación de inputs bloqueados."""

    def test_blocked_total(self, db_conn):
        """'TOTAL' es rechazado."""
        result = get_or_create_organization("TOTAL", db_conn)
        assert result is None

    def test_blocked_total_case(self, db_conn):
        """'total' en lowercase es rechazado (no está en blocked names)."""
        # _BLOCKED_ORG_NAMES es {"TOTAL"} — case-sensitive check
        result = get_or_create_organization("total", db_conn)
        # 'total' no está en frozenset({"TOTAL"}), pero la creación
        # sí debería proceder — el blocked check es exact match
        assert result is not None

    def test_blocked_fecha(self, db_conn):
        """Fechas DD/MM/YYYY son rechazadas."""
        result = get_or_create_organization("06/04/2026", db_conn)
        assert result is None

    def test_blocked_fecha_otra(self, db_conn):
        """Otra fecha DD/MM/YYYY es rechazada."""
        result = get_or_create_organization("31/12/2025", db_conn)
        assert result is None

    def test_input_vacio_rechazado(self, db_conn):
        """Input vacío es rechazado."""
        assert get_or_create_organization("", db_conn) is None
        assert get_or_create_organization("  ", db_conn) is None
        assert get_or_create_organization(None, db_conn) is None


class TestGetOrCreateOrganizationLookup:
    """Tests de lookup case-insensitive."""

    def test_case_insensitive_abbr(self, db_conn):
        """Case-insensitive lookup por abbr funciona."""
        id1 = get_or_create_organization("morena", db_conn)
        assert id1 == "O01"

    def test_case_insensitive_mixto(self, db_conn):
        """Case-insensitive con mixed case."""
        id1 = get_or_create_organization("MoReNa", db_conn)
        assert id1 == "O01"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
