"""
tests/test_transformers_diputados.py — Tests para scraper/transformers.py (Diputados SITL).

Ejecutar con: pytest tests/
"""

import pytest
from diputados.scraper.models import DesgloseVotacion, DesglosePartido
from diputados.scraper.transformers import (
    determinar_resultado_votacion,
    determinar_tipo_motion,
    parsear_fecha_sitl,
    sentido_to_option,
)
from diputados.scraper.utils.text_utils import normalize_name


# ============================================================
# Tests: scraper/transformers.py — determinar_resultado_votacion
# ============================================================


class TestDeterminarResultadoVotacion:
    """Tests para la función determinar_resultado_votacion."""

    def _make_desglose(
        self, a_favor, en_contra, abstenciones=0, ausentes=0
    ) -> DesgloseVotacion:
        """Helper para crear un DesgloseVotacion con los valores dados."""
        totales = DesglosePartido(
            partido_nombre="TOTAL",
            a_favor=a_favor,
            en_contra=en_contra,
            abstencion=abstenciones,
            ausente=ausentes,
            solo_asistencia=0,
            total=a_favor + en_contra + abstenciones + ausentes,
        )
        return DesgloseVotacion(
            sitl_id=0, titulo="test", fecha="", totales=totales, partidos=[]
        )

    # --- Mayoria Simple ---

    def test_mayoria_simple_aprobada(self):
        """Mayoria simple: a_favor > en_contra → aprobada."""
        desglose = self._make_desglose(a_favor=100, en_contra=50)
        result = determinar_resultado_votacion(desglose, requirement="mayoria_simple")
        assert result == "aprobada", "a_favor > en_contra debe ser aprobada"

    def test_mayoria_simple_rechazada(self):
        """Mayoria simple: a_favor < en_contra → rechazada."""
        desglose = self._make_desglose(a_favor=50, en_contra=100)
        result = determinar_resultado_votacion(desglose, requirement="mayoria_simple")
        assert result == "rechazada", "a_favor < en_contra debe ser rechazada"

    def test_mayoria_simple_empate(self):
        """Mayoria simple: a_favor == en_contra → empate."""
        desglose = self._make_desglose(a_favor=100, en_contra=100)
        result = determinar_resultado_votacion(desglose, requirement="mayoria_simple")
        assert result == "empate", "a_favor == en_contra debe ser empate"

    # --- Mayoria Calificada (2/3 de presentes) ---

    def test_mayoria_calificada_aprobada(self):
        """Mayoria calificada: a_favor >= 2/3 de presentes → aprobada."""
        # 200 presentes (150 a favor + 30 contra + 20 abstenciones)
        # 2/3 de 200 = 133.33, 150 >= 133.33 → aprobada
        desglose = self._make_desglose(a_favor=150, en_contra=30, abstenciones=20)
        result = determinar_resultado_votacion(
            desglose, requirement="mayoria_calificada"
        )
        assert result == "aprobada", "a_favor >= 2/3 de presentes debe ser aprobada"

    def test_mayoria_calificada_rechazada_justo_empate(self):
        """Mayoria calificada: a_favor < 2/3 → rechazada."""
        # 300 presentes, 2/3 = 200, 150 < 200 → rechazada
        desglose = self._make_desglose(a_favor=150, en_contra=100, abstenciones=50)
        result = determinar_resultado_votacion(
            desglose, requirement="mayoria_calificada"
        )
        assert result == "rechazada", "a_favor < 2/3 de presentes debe ser rechazada"

    def test_mayoria_calificada_empate_exacto_2_3(self):
        """Mayoria calificada: a_favor == exactamente 2/3 → aprobada."""
        # 300 presentes, 2/3 = 200 exacto
        desglose = self._make_desglose(a_favor=200, en_contra=50, abstenciones=50)
        result = determinar_resultado_votacion(
            desglose, requirement="mayoria_calificada"
        )
        assert result == "aprobada", "a_favor == 2/3 exacto debe ser aprobada"

    # --- Edge case: presentes == 0 ---

    def test_mayoria_calificada_sin_presentes(self):
        """Mayoria calificada con 0 presentes → rechazada (no puede aprobarse)."""
        desglose = self._make_desglose(a_favor=0, en_contra=0, abstenciones=0)
        result = determinar_resultado_votacion(
            desglose, requirement="mayoria_calificada"
        )
        assert result == "rechazada", "Sin presentes debe ser rechazada"

    def test_mayoria_simple_sin_presentes(self):
        """Mayoria simple con 0 presentes → empate."""
        desglose = self._make_desglose(a_favor=0, en_contra=0)
        result = determinar_resultado_votacion(desglose, requirement="mayoria_simple")
        assert result == "empate", "Sin votos debe ser empate"

    # --- Fallback ---

    def test_requirement_desconocido_fallback_simple(self):
        """Requirement desconocido → fallback a mayoria_simple."""
        desglose = self._make_desglose(a_favor=10, en_contra=5)
        result = determinar_resultado_votacion(desglose, requirement="desconocido")
        assert result == "aprobada", "Fallback debe usar mayoria_simple"


# ============================================================
# Tests: scraper/transformers.py — determinar_tipo_motion
# ============================================================


class TestDeterminarTipoMotion:
    """Tests para la función determinar_tipo_motion."""

    def test_reforma_constitucional_CONSTITUCION(self):
        """Contiene 'CONSTITUCIÓN' → reforma_constitucional."""
        result = determinar_tipo_motion("Reforma a la CONSTITUCIÓN Federal")
        assert result == "reforma_constitucional", (
            "Debe clasificar como reforma constitucional"
        )

    def test_reforma_constitucional_CONSTITUCIONAL(self):
        """Contiene 'CONSTITUCIONAL' → reforma_constitucional."""
        result = determinar_tipo_motion("Ley constitucional sobre telecomunicaciones")
        assert result == "reforma_constitucional", (
            "Debe clasificar como reforma constitucional"
        )

    def test_ley_secundaria_LEY(self):
        """Contiene 'LEY' pero no 'CONSTITUCIÓN' → ley_secundaria."""
        result = determinar_tipo_motion("Ley de Ingresos de la Federación")
        assert result == "ley_secundaria", (
            "LEY sin CONSTITUCIÓN debe ser ley_secundaria"
        )

    def test_ley_secundaria_ley_federal(self):
        """Contiene 'LEY' sin CONSTITUCIÓN → ley_secundaria."""
        result = determinar_tipo_motion("Ley Federal del Trabajo")
        assert result == "ley_secundaria", (
            "LEY sin CONSTITUCIÓN debe ser ley_secundaria"
        )

    def test_ordinaria_PRESUPUESTO(self):
        """Contiene 'PRESUPUESTO' → ordinaria."""
        result = determinar_tipo_motion("Decreto de Presupuesto de Egresos")
        assert result == "ordinaria", "PRESUPUESTO debe ser ordinaria"

    def test_ordinaria_DECRETO_INGRESOS(self):
        """Contiene 'DECRETO' + 'INGRESOS' (sin 'LEY') → ordinaria."""
        result = determinar_tipo_motion("Decreto de Ingresos de la Federacion")
        assert result == "ordinaria", "DECRETO + INGRESOS debe ser ordinaria"

    def test_ordinaria_DECRETO_EGRESOS(self):
        """Contiene 'DECRETO' + 'EGRESOS' → ordinaria."""
        result = determinar_tipo_motion("Decreto de Egresos de la Federacion")
        assert result == "ordinaria", "DECRETO + EGRESOS debe ser ordinaria"

    def test_otra_ninguna_coincidencia(self):
        """Sin coincidencias → otra."""
        result = determinar_tipo_motion("Votacion sobre dictamen de comision")
        assert result == "otra", "Sin coincidencias debe ser otra"

    def test_otra_caso_vacio(self):
        """String vacío → otra."""
        result = determinar_tipo_motion("")
        assert result == "otra", "String vacío debe ser otra"


# ============================================================
# Tests: scraper/transformers.py — parsear_fecha_sitl
# ============================================================


class TestParsearFechaSitl:
    """Tests para la función parsear_fecha_sitl."""

    def test_formato_sitl_dic(self):
        """Formato '10 Diciembre 2024' → '2024-12-10'."""
        result = parsear_fecha_sitl("10 Diciembre 2024")
        assert result == "2024-12-10", "Diciembre debe convertirse a 12"

    def test_formato_sitl_enero(self):
        """Formato '15 Enero 2024' → '2024-01-15'."""
        result = parsear_fecha_sitl("15 Enero 2024")
        assert result == "2024-01-15", "Enero debe convertirse a 01"

    def test_formato_sitl_varios_meses(self):
        """Verifica todos los meses."""
        assert parsear_fecha_sitl("01 Enero 2024") == "2024-01-01"
        assert parsear_fecha_sitl("28 Febrero 2024") == "2024-02-28"
        assert parsear_fecha_sitl("15 Marzo 2024") == "2024-03-15"
        assert parsear_fecha_sitl("30 Abril 2024") == "2024-04-30"
        assert parsear_fecha_sitl("10 Mayo 2024") == "2024-05-10"
        assert parsear_fecha_sitl("20 Junio 2024") == "2024-06-20"
        assert parsear_fecha_sitl("05 Julio 2024") == "2024-07-05"
        assert parsear_fecha_sitl("14 Agosto 2024") == "2024-08-14"
        assert parsear_fecha_sitl("01 Septiembre 2024") == "2024-09-01"
        assert parsear_fecha_sitl("12 Octubre 2024") == "2024-10-12"
        assert parsear_fecha_sitl("25 Noviembre 2024") == "2024-11-25"
        assert parsear_fecha_sitl("31 Diciembre 2024") == "2024-12-31"

    def test_formato_iso_pasa_directo(self):
        """Formato ISO '2024-12-10' → pasa directo."""
        result = parsear_fecha_sitl("2024-12-10")
        assert result == "2024-12-10", "Formato ISO debe pasar directo"

    def test_formato_slash_dd_mm_yyyy(self):
        """Formato 'DD/MM/YYYY' → convierte a ISO."""
        result = parsear_fecha_sitl("10/12/2024")
        assert result == "2024-12-10", "DD/MM/YYYY debe convertirse a ISO"

    def test_formato_slash_single_digit(self):
        """Formato 'D/M/YYYY' → convierte a ISO con padding."""
        result = parsear_fecha_sitl("5/3/2024")
        assert result == "2024-03-05", "D/M/YYYY debe convertirse a ISO con ceros"

    def test_input_vacio(self):
        """Input vacío → retorna string vacío."""
        result = parsear_fecha_sitl("")
        assert result == "", "Input vacío debe retornar string vacío"

    def test_input_solo_espacios(self):
        """Input solo espacios → retorna string vacío."""
        result = parsear_fecha_sitl("   ")
        assert result == "", "Input solo espacios debe retornar string vacío"

    def test_formato_sitl_con_dia_single_digit(self):
        """Formato '5 Diciembre 2024' → '2024-12-05'."""
        result = parsear_fecha_sitl("5 Diciembre 2024")
        assert result == "2024-12-05", "Día single digit debe tener padding"


# ============================================================
# Tests: scraper/transformers.py — sentido_to_option
# ============================================================


class TestSentidoToOption:
    """Tests para la función sentido_to_option."""

    def test_a_favor(self):
        """'A favor' → 'a_favor'."""
        result = sentido_to_option("A favor")
        assert result == "a_favor", "'A favor' debe convertirse a 'a_favor'"

    def test_a_favor_case_insensitive(self):
        """'A FAVOR' → 'a_favor' (case insensitive)."""
        result = sentido_to_option("A FAVOR")
        assert result == "a_favor"

    def test_en_contra(self):
        """'En contra' → 'en_contra'."""
        result = sentido_to_option("En contra")
        assert result == "en_contra", "'En contra' debe convertirse a 'en_contra'"

    def test_ausente(self):
        """'Ausente' → 'ausente'."""
        result = sentido_to_option("Ausente")
        assert result == "ausente", "'Ausente' debe convertirse a 'ausente'"

    def test_abstencion_con_acento(self):
        """'Abstención' → 'abstencion'."""
        result = sentido_to_option("Abstención")
        assert result == "abstencion", "'Abstención' debe convertirse a 'abstencion'"

    def test_abstencion_sin_acento(self):
        """'Abstencion' → 'abstencion'."""
        result = sentido_to_option("Abstencion")
        assert result == "abstencion", "'Abstencion' debe convertirse a 'abstencion'"

    def test_solo_asistencia(self):
        """'Solo asistencia' → 'abstencion'."""
        result = sentido_to_option("Solo asistencia")
        assert result == "abstencion", (
            "'Solo asistencia' debe convertirse a 'abstencion'"
        )

    def test_solo_asistencia_case_insensitive(self):
        """'SOLO ASISTENCIA' → 'abstencion'."""
        result = sentido_to_option("SOLO ASISTENCIA")
        assert result == "abstencion"

    def test_voto_desconocido(self):
        """Voto no reconocido → 'ausente' con warning."""
        result = sentido_to_option("voto_extraño")
        assert result == "ausente", "Voto desconocido debe retornar 'ausente'"


# ============================================================
# Tests: scraper/transformers.py — normalize_name
# ============================================================


class TestNormalizarNombre:
    """Tests para la función normalize_name (Diputados)."""

    def test_ejemplo_oficial(self):
        """'Álvarez Villaseñor Raúl' → 'alvarez villasenor raul'."""
        result = normalize_name("Álvarez Villaseñor Raúl")
        assert result == "alvarez villasenor raul", "Debe eliminar acentos y lowercase"

    def test_elimina_acentos(self):
        """Verifica eliminación de acentos comunes."""
        assert normalize_name("José María García") == "jose maria garcia"
        assert normalize_name("Niño García") == "nino garcia"
        assert normalize_name("Álvarez") == "alvarez"
        assert normalize_name("López") == "lopez"

    def test_colapsa_espacios(self):
        """Espacios múltiples → espacio simple."""
        result = normalize_name("  Juan   Pérez   Gómez  ")
        assert result == "juan perez gomez", "Debe colapsar espacios múltiples"

    def test_strip_espacios_extremos(self):
        """Espacios al inicio/final → eliminados."""
        result = normalize_name("  María López  ")
        assert result == "maria lopez", "Debe hacer strip de espacios extremos"

    def test_lowercase(self):
        """Todo debe ser lowercase."""
        result = normalize_name("MARIANO FERNÁNDEZ")
        assert result == "mariano fernandez"
