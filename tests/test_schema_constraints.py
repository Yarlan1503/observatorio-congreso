"""Tests para CHECKs y triggers de db/schema.sql."""

import sqlite3
import pytest

SCHEMA_PATH = "db/schema.sql"


@pytest.fixture
def fresh_db(tmp_path):
    """BD temporal con schema completo cargado."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    yield conn
    conn.close()


# ============================================================
# Helpers: inserts mínimos para satisfacer FK
# ============================================================


def _insert_area(conn, id="A01", nombre="Jalisco", clasificacion="estado"):
    conn.execute(
        "INSERT INTO area (id, nombre, clasificacion) VALUES (?, ?, ?)",
        (id, nombre, clasificacion),
    )


def _insert_organization(conn, id="O01", nombre="MORENA", clasificacion="partido"):
    conn.execute(
        "INSERT INTO organization (id, nombre, clasificacion) VALUES (?, ?, ?)",
        (id, nombre, clasificacion),
    )


def _insert_person(conn, id="P01", nombre="Juan Pérez"):
    conn.execute(
        "INSERT INTO person (id, nombre) VALUES (?, ?)",
        (id, nombre),
    )


def _insert_motion(
    conn, id="Y01", texto="Iniciativa test", clasificacion="ordinaria", requirement="mayoria_simple"
):
    conn.execute(
        "INSERT INTO motion (id, texto, clasificacion, requirement) VALUES (?, ?, ?, ?)",
        (id, texto, clasificacion, requirement),
    )


def _insert_vote_event(
    conn, id="VE01", motion_id="Y01", start_date="2024-01-01", organization_id="O01"
):
    conn.execute(
        "INSERT INTO vote_event (id, motion_id, start_date, organization_id) VALUES (?, ?, ?, ?)",
        (id, motion_id, start_date, organization_id),
    )


# ============================================================
# CHECK: area
# ============================================================


class TestCheckArea:
    """Tests para CHECK constraints en tabla area."""

    @pytest.mark.parametrize("val", ["estado", "distrito", "circunscripcion"])
    def test_clasificacion_valida(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO area (id, nombre, clasificacion) VALUES (?, ?, ?)",
            ("A01", "Test", val),
        )

    def test_clasificacion_invalida(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO area (id, nombre, clasificacion) VALUES ('A99', 'Test', 'invalido')"
            )


# ============================================================
# CHECK: organization
# ============================================================


class TestCheckOrganization:
    """Tests para CHECK constraints en tabla organization."""

    @pytest.mark.parametrize(
        "val", ["partido", "bancada", "coalicion", "gobierno", "institucion", "otro"]
    )
    def test_clasificacion_valida(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO organization (id, nombre, clasificacion) VALUES (?, ?, ?)",
            ("O01", f"Org_{val}", val),
        )

    def test_clasificacion_invalida(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO organization (id, nombre, clasificacion) VALUES ('O99', 'Test', 'syndicate')"
            )


# ============================================================
# CHECK: person
# ============================================================


class TestCheckPerson:
    """Tests para CHECK constraints en tabla person."""

    @pytest.mark.parametrize("val", ["M", "F", "NB"])
    def test_genero_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, genero) VALUES (?, ?, ?)",
            ("P01", "Test", val),
        )

    def test_genero_null(self, fresh_db):
        fresh_db.execute("INSERT INTO person (id, nombre, genero) VALUES ('P01', 'Test', NULL)")

    def test_genero_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute("INSERT INTO person (id, nombre, genero) VALUES ('P99', 'Test', 'X')")

    @pytest.mark.parametrize("val", ["mayoria_relativa", "plurinominal", "suplente"])
    def test_curul_tipo_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, curul_tipo) VALUES ('P01', 'Test', ?)",
            (val,),
        )

    def test_curul_tipo_null(self, fresh_db):
        fresh_db.execute("INSERT INTO person (id, nombre, curul_tipo) VALUES ('P01', 'Test', NULL)")

    def test_curul_tipo_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO person (id, nombre, curul_tipo) VALUES ('P99', 'Test', 'designado')"
            )

    @pytest.mark.parametrize("val", [1, 2, 3, 4, 5])
    def test_circunscripcion_valida(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, circunscripcion) VALUES ('P01', 'Test', ?)",
            (val,),
        )

    def test_circunscripcion_null(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, circunscripcion) VALUES ('P01', 'Test', NULL)"
        )

    def test_circunscripcion_fuera_rango_bajo(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO person (id, nombre, circunscripcion) VALUES ('P99', 'Test', 0)"
            )

    def test_circunscripcion_fuera_rango_alto(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO person (id, nombre, circunscripcion) VALUES ('P99', 'Test', 6)"
            )

    @pytest.mark.parametrize("val", ["Monreal", "AMLO", "Sheinbaum", "institucionalista"])
    def test_corriente_interna_valida(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, corriente_interna) VALUES ('P01', 'Test', ?)",
            (val,),
        )

    def test_corriente_interna_null(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, corriente_interna) VALUES ('P01', 'Test', NULL)"
        )

    def test_corriente_interna_invalida(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO person (id, nombre, corriente_interna) VALUES ('P99', 'Test', 'Chiapas')"
            )

    @pytest.mark.parametrize("val", ["alta", "media", "baja"])
    def test_vulnerabilidad_valida(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, vulnerabilidad) VALUES ('P01', 'Test', ?)",
            (val,),
        )

    def test_vulnerabilidad_null(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO person (id, nombre, vulnerabilidad) VALUES ('P01', 'Test', NULL)"
        )

    def test_vulnerabilidad_invalida(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO person (id, nombre, vulnerabilidad) VALUES ('P99', 'Test', 'critica')"
            )


# ============================================================
# CHECK: motion
# ============================================================


class TestCheckMotion:
    """Tests para CHECK constraints en tabla motion."""

    @pytest.mark.parametrize(
        "val", ["reforma_constitucional", "ley_secundaria", "ordinaria", "otra"]
    )
    def test_clasificacion_valida(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO motion (id, texto, clasificacion, requirement) VALUES (?, ?, ?, 'mayoria_simple')",
            ("Y01", "Test", val),
        )

    def test_clasificacion_invalida(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO motion (id, texto, clasificacion, requirement) VALUES ('Y99', 'Test', 'decreto', 'mayoria_simple')"
            )

    @pytest.mark.parametrize("val", ["mayoria_simple", "mayoria_calificada", "unanime"])
    def test_requirement_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO motion (id, texto, clasificacion, requirement) VALUES ('Y01', 'Test', 'ordinaria', ?)",
            (val,),
        )

    def test_requirement_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO motion (id, texto, clasificacion, requirement) VALUES ('Y99', 'Test', 'ordinaria', 'absoluta')"
            )

    @pytest.mark.parametrize("val", ["aprobada", "rechazada", "pendiente", "retirada"])
    def test_result_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO motion (id, texto, clasificacion, requirement, result) VALUES ('Y01', 'Test', 'ordinaria', 'mayoria_simple', ?)",
            (val,),
        )

    def test_result_null(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO motion (id, texto, clasificacion, requirement, result) VALUES ('Y01', 'Test', 'ordinaria', 'mayoria_simple', NULL)"
        )

    def test_result_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO motion (id, texto, clasificacion, requirement, result) VALUES ('Y99', 'Test', 'ordinaria', 'mayoria_simple', 'empate')"
            )


# ============================================================
# CHECK: vote_event
# ============================================================


class TestCheckVoteEvent:
    """Tests para CHECK constraints en tabla vote_event."""

    def _setup_parents(self, conn):
        _insert_organization(conn)
        _insert_motion(conn)

    @pytest.mark.parametrize("val", ["aprobada", "rechazada", "empate"])
    def test_result_valido(self, fresh_db, val):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO vote_event (id, motion_id, start_date, organization_id, result) VALUES ('VE01', 'Y01', '2024-01-01', 'O01', ?)",
            (val,),
        )

    def test_result_null(self, fresh_db):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO vote_event (id, motion_id, start_date, organization_id, result) VALUES ('VE01', 'Y01', '2024-01-01', 'O01', NULL)"
        )

    def test_result_invalido(self, fresh_db):
        self._setup_parents(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO vote_event (id, motion_id, start_date, organization_id, result) VALUES ('VE99', 'Y01', '2024-01-01', 'O01', 'pendiente')"
            )

    @pytest.mark.parametrize("val", ["mayoria_simple", "mayoria_calificada", "unanime"])
    def test_requirement_valido(self, fresh_db, val):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO vote_event (id, motion_id, start_date, organization_id, requirement) VALUES ('VE01', 'Y01', '2024-01-01', 'O01', ?)",
            (val,),
        )

    def test_requirement_null(self, fresh_db):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO vote_event (id, motion_id, start_date, organization_id, requirement) VALUES ('VE01', 'Y01', '2024-01-01', 'O01', NULL)"
        )

    def test_requirement_invalido(self, fresh_db):
        self._setup_parents(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO vote_event (id, motion_id, start_date, organization_id, requirement) VALUES ('VE99', 'Y01', '2024-01-01', 'O01', 'dos_tercios')"
            )


# ============================================================
# CHECK: vote
# ============================================================


class TestCheckVote:
    """Tests para CHECK constraints en tabla vote."""

    def _setup_parents(self, conn):
        _insert_organization(conn)
        _insert_motion(conn)
        _insert_vote_event(conn)
        _insert_person(conn)

    @pytest.mark.parametrize("val", ["a_favor", "en_contra", "abstencion", "ausente"])
    def test_option_valida(self, fresh_db, val):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO vote (id, vote_event_id, voter_id, option) VALUES ('V01', 'VE01', 'P01', ?)",
            (val,),
        )

    def test_option_invalida(self, fresh_db):
        self._setup_parents(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO vote (id, vote_event_id, voter_id, option) VALUES ('V99', 'VE01', 'P01', 'presente')"
            )


# ============================================================
# CHECK: count
# ============================================================


class TestCheckCount:
    """Tests para CHECK constraints en tabla count."""

    def _setup_parents(self, conn):
        _insert_organization(conn)
        _insert_motion(conn)
        _insert_vote_event(conn)

    @pytest.mark.parametrize("val", ["a_favor", "en_contra", "abstencion", "ausente"])
    def test_option_valida(self, fresh_db, val):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO count (id, vote_event_id, option, value) VALUES ('C01', 'VE01', ?, 10)",
            (val,),
        )

    def test_option_invalida(self, fresh_db):
        self._setup_parents(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO count (id, vote_event_id, option, value) VALUES ('C99', 'VE01', 'ausentes', 10)"
            )

    def test_value_cero(self, fresh_db):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO count (id, vote_event_id, option, value) VALUES ('C01', 'VE01', 'a_favor', 0)"
        )

    def test_value_positivo(self, fresh_db):
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO count (id, vote_event_id, option, value) VALUES ('C01', 'VE01', 'a_favor', 250)"
        )

    def test_value_negativo(self, fresh_db):
        self._setup_parents(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO count (id, vote_event_id, option, value) VALUES ('C99', 'VE01', 'a_favor', -1)"
            )


# ============================================================
# CHECK: actor_externo
# ============================================================


class TestCheckActorExterno:
    """Tests para CHECK constraints en tabla actor_externo."""

    @pytest.mark.parametrize(
        "val", ["gobernador", "alcalde", "ex_presidente", "dirigente", "juez", "otro"]
    )
    def test_tipo_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO actor_externo (id, nombre, tipo) VALUES ('AE01', 'Test', ?)",
            (val,),
        )

    def test_tipo_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO actor_externo (id, nombre, tipo) VALUES ('AE99', 'Test', 'senador')"
            )


# ============================================================
# CHECK: relacion_poder
# ============================================================


class TestCheckRelacionPoder:
    """Tests para CHECK constraints en tabla relacion_poder."""

    @pytest.mark.parametrize("val", ["person", "organization", "actor_externo"])
    def test_source_type_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP01', ?, 'P01', 'person', 'P02', 'alianza', 3)",
            (val,),
        )

    def test_source_type_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP99', 'partido', 'P01', 'person', 'P02', 'alianza', 3)"
            )

    @pytest.mark.parametrize("val", ["person", "organization", "actor_externo"])
    def test_target_type_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP01', 'person', 'P01', ?, 'P02', 'alianza', 3)",
            (val,),
        )

    def test_target_type_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP99', 'person', 'P01', 'grupo', 'P02', 'alianza', 3)"
            )

    @pytest.mark.parametrize(
        "val",
        ["lealtad", "presion", "influencia", "familiar", "clientelismo", "conflicto", "alianza"],
    )
    def test_tipo_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP01', 'person', 'P01', 'person', 'P02', ?, 3)",
            (val,),
        )

    def test_tipo_invalido(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP99', 'person', 'P01', 'person', 'P02', 'amistad', 3)"
            )

    @pytest.mark.parametrize("val", [1, 2, 3, 4, 5])
    def test_peso_valido(self, fresh_db, val):
        fresh_db.execute(
            "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP01', 'person', 'P01', 'person', 'P02', 'alianza', ?)",
            (val,),
        )

    def test_peso_fuera_rango_bajo(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP99', 'person', 'P01', 'person', 'P02', 'alianza', 0)"
            )

    def test_peso_fuera_rango_alto(self, fresh_db):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO relacion_poder (id, source_type, source_id, target_type, target_id, tipo, peso) VALUES ('RP99', 'person', 'P01', 'person', 'P02', 'alianza', 6)"
            )


# ============================================================
# TRIGGERS: person dates
# ============================================================


class TestTriggersPerson:
    """Tests para triggers de validación de fechas en person."""

    def test_insert_fechas_validas(self, fresh_db):
        """INSERT con end_date >= start_date se acepta."""
        fresh_db.execute(
            "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P01', 'Test', '2024-01-01', '2024-12-31')"
        )

    def test_insert_fechas_iguales(self, fresh_db):
        """INSERT con end_date == start_date se acepta."""
        fresh_db.execute(
            "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P01', 'Test', '2024-01-01', '2024-01-01')"
        )

    def test_insert_end_date_antes_start_date(self, fresh_db):
        """INSERT con end_date < start_date es rechazado por trigger."""
        with pytest.raises(sqlite3.IntegrityError, match="end_date debe ser"):
            fresh_db.execute(
                "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P99', 'Test', '2024-12-31', '2024-01-01')"
            )

    def test_insert_sin_end_date(self, fresh_db):
        """INSERT sin end_date (NULL) se acepta."""
        fresh_db.execute(
            "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P01', 'Test', '2024-01-01', NULL)"
        )

    def test_insert_sin_start_date(self, fresh_db):
        """INSERT sin start_date se acepta (trigger solo valida cuando ambos existen)."""
        fresh_db.execute(
            "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P01', 'Test', NULL, '2024-12-31')"
        )

    def test_update_end_date_antes_start_date(self, fresh_db):
        """UPDATE que pone end_date < start_date es rechazado por trigger."""
        fresh_db.execute(
            "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P01', 'Test', '2024-01-01', '2024-12-31')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="end_date debe ser"):
            fresh_db.execute("UPDATE person SET end_date = '2023-01-01' WHERE id = 'P01'")

    def test_update_fechas_validas(self, fresh_db):
        """UPDATE con fechas válidas se acepta."""
        fresh_db.execute(
            "INSERT INTO person (id, nombre, start_date, end_date) VALUES ('P01', 'Test', '2024-01-01', '2024-12-31')"
        )
        fresh_db.execute("UPDATE person SET end_date = '2025-06-30' WHERE id = 'P01'")


# ============================================================
# TRIGGERS: membership dates
# ============================================================


class TestTriggersMembership:
    """Tests para triggers de validación de fechas en membership."""

    def _setup_parents(self, conn):
        _insert_organization(conn)
        _insert_person(conn)

    def test_insert_fechas_validas(self, fresh_db):
        """INSERT membership con end_date >= start_date se acepta."""
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date) VALUES ('M01', 'P01', 'O01', 'diputado', '2024-01-01', '2024-12-31')"
        )

    def test_insert_fechas_iguales(self, fresh_db):
        """INSERT membership con end_date == start_date se acepta."""
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date) VALUES ('M01', 'P01', 'O01', 'diputado', '2024-01-01', '2024-01-01')"
        )

    def test_insert_end_date_antes_start_date(self, fresh_db):
        """INSERT membership con end_date < start_date es rechazado por trigger."""
        self._setup_parents(fresh_db)
        with pytest.raises(sqlite3.IntegrityError, match="end_date debe ser"):
            fresh_db.execute(
                "INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date) VALUES ('M99', 'P01', 'O01', 'diputado', '2024-12-31', '2024-01-01')"
            )

    def test_insert_sin_end_date(self, fresh_db):
        """INSERT membership sin end_date (NULL, vigente) se acepta."""
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date) VALUES ('M01', 'P01', 'O01', 'diputado', '2024-01-01', NULL)"
        )

    def test_update_end_date_antes_start_date(self, fresh_db):
        """UPDATE membership que pone end_date < start_date es rechazado."""
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date) VALUES ('M01', 'P01', 'O01', 'diputado', '2024-01-01', '2024-12-31')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="end_date debe ser"):
            fresh_db.execute("UPDATE membership SET end_date = '2023-01-01' WHERE id = 'M01'")

    def test_update_fechas_validas(self, fresh_db):
        """UPDATE membership con fechas válidas se acepta."""
        self._setup_parents(fresh_db)
        fresh_db.execute(
            "INSERT INTO membership (id, person_id, org_id, rol, start_date, end_date) VALUES ('M01', 'P01', 'O01', 'diputado', '2024-01-01', '2024-12-31')"
        )
        fresh_db.execute("UPDATE membership SET end_date = '2025-06-30' WHERE id = 'M01'")
