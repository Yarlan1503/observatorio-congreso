"""
test_transformers.py — Tests unitarios para transformers del Senado.

Cubre determinar_resultado() — función crítica que decide
aprobada/rechazada/empate para las votaciones del Senado,
incluyendo mayoría calificada (Art. 135 CPEUM, 2/3 de presentes).

Uso:
    pytest tests/senadores/test_transformers.py -v
"""

import pytest

from scraper_congreso.senadores.votaciones.transformers import determinar_resultado


class TestDeterminarResultadoMayoriasSimple:
    """Tests para determinar_resultado() con mayoría simple."""

    def test_mayoria_simple_aprobada(self):
        """Mayoría simple: pro > contra → aprobada."""
        assert determinar_resultado(pro_count=60, contra_count=40) == "aprobada"

    def test_mayoria_simple_rechazada(self):
        """Mayoría simple: contra > pro → rechazada."""
        assert determinar_resultado(pro_count=30, contra_count=70) == "rechazada"

    def test_empate(self):
        """pro == contra → empate."""
        assert determinar_resultado(pro_count=50, contra_count=50) == "empate"

    def test_presentes_cero_rechazada(self):
        """Presentes = 0 → rechazada (edge case que causó fantasmas)."""
        assert determinar_resultado(pro_count=0, contra_count=0) == "empate"
        # Con abstención explícita = 0 también es empate
        assert determinar_resultado(pro_count=0, contra_count=0, abstention_count=0) == "empate"

    def test_requirement_default_mayoria_simple(self):
        """requirement=None o no especificado → mayoría simple."""
        assert determinar_resultado(pro_count=10, contra_count=5, requirement=None) == "aprobada"
        assert determinar_resultado(pro_count=10, contra_count=5) == "aprobada"


class TestDeterminarResultadoMayoriasCalificada:
    """Tests para determinar_resultado() con mayoría calificada (2/3)."""

    def test_calificada_aprobada(self):
        """Mayoría calificada: pro >= 2/3 de presentes → aprobada."""
        # 90 de 120 = 75% >= 66.67%
        assert (
            determinar_resultado(
                pro_count=90,
                contra_count=20,
                abstention_count=10,
                requirement="mayoria_calificada",
            )
            == "aprobada"
        )

    def test_calificada_umbral_exacto(self):
        """Mayoría calificada: pro = 2/3 exacto → aprobada (>=)."""
        # 80 de 120 = 66.67% exacto
        assert (
            determinar_resultado(
                pro_count=80,
                contra_count=40,
                abstention_count=0,
                requirement="mayoria_calificada",
            )
            == "aprobada"
        )

    def test_calificada_rechazada(self):
        """Mayoría calificada: pro < 2/3 → rechazada."""
        # 70 de 120 = 58.3% < 66.67%
        assert (
            determinar_resultado(
                pro_count=70,
                contra_count=40,
                abstention_count=10,
                requirement="mayoria_calificada",
            )
            == "rechazada"
        )

    def test_calificada_presentes_cero(self):
        """Mayoría calificada con presentes = 0 → rechazada."""
        assert (
            determinar_resultado(
                pro_count=0,
                contra_count=0,
                abstention_count=0,
                requirement="mayoria_calificada",
            )
            == "rechazada"
        )

    def test_calificada_sin_abstencion_fallback(self):
        """Mayoría calificada sin datos de abstención → fallback a mayoría simple."""
        # abstention_count = 0 (default), usa mayoría simple
        assert (
            determinar_resultado(
                pro_count=60,
                contra_count=40,
                requirement="mayoria_calificada",
            )
            == "aprobada"
        )

    def test_calificada_con_abstencion_presente(self):
        """Abstención cuenta como presente para calcular 2/3."""
        # 80 pro + 20 contra + 20 abst = 120 presentes
        # 2/3 de 120 = 80, 80 >= 80 → aprobada
        assert (
            determinar_resultado(
                pro_count=80,
                contra_count=20,
                abstention_count=20,
                requirement="mayoria_calificada",
            )
            == "aprobada"
        )

    def test_calificada_abstencion_alta(self):
        """Muchas abstenciones hacen difícil alcanzar 2/3."""
        # 50 pro + 10 contra + 60 abst = 120 presentes
        # 2/3 de 120 = 80, 50 < 80 → rechazada aunque pro > contra
        assert (
            determinar_resultado(
                pro_count=50,
                contra_count=10,
                abstention_count=60,
                requirement="mayoria_calificada",
            )
            == "rechazada"
        )

    def test_calificada_solo_pro_y_abstencion(self):
        """Sin votos en contra, 2/3 debe incluir abstenciones."""
        # 70 pro + 0 contra + 40 abst = 110 presentes
        # 2/3 de 110 = 73.33, 70 < 73.33 → rechazada
        assert (
            determinar_resultado(
                pro_count=70,
                contra_count=0,
                abstention_count=40,
                requirement="mayoria_calificada",
            )
            == "rechazada"
        )


class TestDeterminarResultadoEdgeCases:
    """Tests edge cases y regresión."""

    def test_valores_grandes(self):
        """Valores grandes de senadores (LX = 128, LXVI = 128)."""
        # LXVI: 87 presentes, 2/3 = 58
        assert (
            determinar_resultado(
                pro_count=59,
                contra_count=20,
                abstention_count=8,
                requirement="mayoria_calificada",
            )
            == "aprobada"
        )

    def test_un_voto_diferencia_simple(self):
        """Un solo voto de diferencia en mayoría simple."""
        assert determinar_resultado(pro_count=51, contra_count=50) == "aprobada"
        assert determinar_resultado(pro_count=50, contra_count=51) == "rechazada"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
