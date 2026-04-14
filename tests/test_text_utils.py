"""
test_text_utils.py — Tests unitarios para utils/text_utils.py.

Cubre normalize_name(), determinar_requirement(), determinar_tipo_motion(),
parse_fecha_iso() y MESES_ES.

Uso:
    pytest tests/test_text_utils.py -v
"""

import pytest

from scraper_congreso.senadores.votaciones.transformers import parse_fecha_iso
from scraper_congreso.utils.text_utils import (
    MESES_ES,
    determinar_requirement,
    determinar_tipo_motion,
    normalize_name,
)


class TestNormalizeName:
    """Tests para normalize_name()."""

    def test_acentos(self):
        """Elimina acentos."""
        assert normalize_name("Álvarez Villaseñor") == "alvarez villasenor"

    def test_ñ(self):
        """Mantiene la ñ (no es acento)."""
        assert normalize_name("Nuñez") == "nunez"

    def test_lowercase(self):
        """Convierte a lowercase."""
        assert normalize_name("MARÍA GARCÍA") == "maria garcia"

    def test_espacios_extra(self):
        """Colapsa espacios múltiples."""
        assert normalize_name("Juan   Pérez    López") == "juan perez lopez"

    def test_espacios_bordes(self):
        """Elimina espacios al inicio y final."""
        assert normalize_name("  Nombre  ") == "nombre"

    def test_nombre_completo(self):
        """Nombre completo normalizado."""
        assert (
            normalize_name("Dr. RAÚL Álvarez-Villaseñor Jr.") == "dr. raul alvarez-villasenor jr."
        )


class TestDeterminarRequirement:
    """Tests para determinar_requirement()."""

    def test_constitucional(self):
        """Detecta mayoría calificada por 'CONSTITUCIÓN'."""
        assert (
            determinar_requirement("Reforma al Artículo 135 CONSTITUCIONAL") == "mayoria_calificada"
        )

    def test_constitucion_sin_acento(self):
        """Detecta aunque falte acento."""
        assert determinar_requirement("Reforma CONSTITUCION") == "mayoria_calificada"

    def test_constitucional_uppercase(self):
        """Case-insensitive."""
        assert determinar_requirement("reforma constitucional") == "mayoria_calificada"

    def test_ley_secundaria(self):
        """Ley secundaria → mayoría simple."""
        assert determinar_requirement("Ley de Ingresos") == "mayoria_simple"

    def test_ordinaria(self):
        """Votación ordinaria → mayoría simple."""
        assert determinar_requirement("Decreto por el que se aprueba") == "mayoria_simple"

    def test_vacio(self):
        """String vacío → mayoría simple."""
        assert determinar_requirement("") == "mayoria_simple"


class TestDeterminarTipoMotion:
    """Tests para determinar_tipo_motion()."""

    def test_reforma_constitucional(self):
        assert determinar_tipo_motion("Reforma CONSTITUCIONAL") == "reforma_constitucional"

    def test_ley_secundaria(self):
        assert determinar_tipo_motion("Ley General de Educación") == "ley_secundaria"

    def test_presupuesto(self):
        assert determinar_tipo_motion("PRESUPUESTO de Egresos") == "ordinaria"

    def test_decreto_ingresos(self):
        assert determinar_tipo_motion("Decreto de Ingresos") == "ordinaria"

    def test_otra(self):
        assert determinar_tipo_motion("Punto de acuerdo") == "otra"


class TestParseFechaIso:
    """Tests para parse_fecha_iso()."""

    def test_formato_dd_mm_yyyy(self):
        assert parse_fecha_iso("31/03/2026") == "2026-03-31"

    def test_formato_dd_mm_yyyy_con_zeros(self):
        assert parse_fecha_iso("01/01/2024") == "2024-01-01"

    def test_formato_yyyy_mm_dd(self):
        assert parse_fecha_iso("2026-03-31") == "2026-03-31"

    def test_vacio(self):
        assert parse_fecha_iso("") == ""

    def test_none(self):
        assert parse_fecha_iso(None) == ""

    def test_invalido(self):
        assert parse_fecha_iso("no-es-fecha") == ""


class TestMesesEs:
    """Tests para el diccionario MESES_ES."""

    def test_completo(self):
        """12 meses definidos."""
        assert len(MESES_ES) == 12

    def test_valores(self):
        """Valores son strings de 2 dígitos."""
        for _mes, num in MESES_ES.items():
            assert isinstance(num, str)
            assert len(num) == 2
            assert num.isdigit()

    def test_enero(self):
        assert MESES_ES["enero"] == "01"

    def test_diciembre(self):
        assert MESES_ES["diciembre"] == "12"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
