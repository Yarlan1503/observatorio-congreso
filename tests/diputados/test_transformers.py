"""
test_transformers.py — Tests unitarios para transformers de Diputados.

Cubre las tres funciones puras de transformers.py:
    - determinar_resultado_votacion() — aprueba/rechaza/empate según mayoría
    - parsear_fecha_sitl() — convierte formatos de fecha del SITL a ISO 8601
    - sentido_to_option() — convierte sentido del voto SITL a formato Popolo

NO cubre: transformar_votacion() (requiere BD), funciones de ID generation,
ni funciones privadas (_partido_to_org_id, etc.).

Uso:
    pytest tests/diputados/test_transformers.py -v
"""

import pytest

from scraper_congreso.diputados.models import DesglosePartido, DesgloseVotacion
from scraper_congreso.diputados.transformers import (
    determinar_resultado_votacion,
    parsear_fecha_sitl,
    sentido_to_option,
)

# ---------------------------------------------------------------------------
# Helpers para construir fixtures inline
# ---------------------------------------------------------------------------


def _desglose(
    a_favor: int = 0,
    en_contra: int = 0,
    abstencion: int = 0,
    solo_asistencia: int = 0,
    ausente: int = 0,
) -> DesgloseVotacion:
    """Crea un DesgloseVotacion mínimo con los totales indicados."""
    total = a_favor + en_contra + abstencion + solo_asistencia + ausente
    totales = DesglosePartido(
        partido_nombre="Total",
        a_favor=a_favor,
        en_contra=en_contra,
        abstencion=abstencion,
        solo_asistencia=solo_asistencia,
        ausente=ausente,
        total=total,
    )
    return DesgloseVotacion(
        sitl_id=1,
        titulo="Votación de prueba",
        fecha="2024-01-01",
        partidos=[],
        totales=totales,
    )


# ===================================================================
# TestDeterminarResultadoVotacion
# ===================================================================


class TestDeterminarResultadoVotacion:
    """Tests para determinar_resultado_votacion() con mayoría simple."""

    def test_simple_aprobada(self):
        """Mayoría simple: favor > contra → aprobada."""
        d = _desglose(a_favor=60, en_contra=40)
        assert determinar_resultado_votacion(d) == "aprobada"

    def test_simple_rechazada(self):
        """Mayoría simple: contra > favor → rechazada."""
        d = _desglose(a_favor=30, en_contra=70)
        assert determinar_resultado_votacion(d) == "rechazada"

    def test_simple_empate(self):
        """Mayoría simple: favor == contra → empate."""
        d = _desglose(a_favor=50, en_contra=50)
        assert determinar_resultado_votacion(d) == "empate"

    def test_simple_presentes_cero_empate(self):
        """Mayoría simple con favor=contra=0 → empate."""
        d = _desglose(a_favor=0, en_contra=0)
        assert determinar_resultado_votacion(d) == "empate"

    def test_simple_un_voto_diferencia_aprobada(self):
        """Un solo voto de diferencia → aprobada."""
        d = _desglose(a_favor=251, en_contra=250)
        assert determinar_resultado_votacion(d) == "aprobada"

    def test_simple_un_voto_diferencia_rechazada(self):
        """Un solo voto de diferencia → rechazada."""
        d = _desglose(a_favor=250, en_contra=251)
        assert determinar_resultado_votacion(d) == "rechazada"

    def test_simple_abstenciones_no_afectan(self):
        """Abstenciones no cambian el resultado en mayoría simple."""
        d = _desglose(a_favor=40, en_contra=30, abstencion=50)
        assert determinar_resultado_votacion(d) == "aprobada"

    def test_simple_solo_abstenciones_empate(self):
        """Solo abstenciones, sin favor ni contra → empate."""
        d = _desglose(a_favor=0, en_contra=0, abstencion=100)
        assert determinar_resultado_votacion(d) == "empate"

    def test_requirement_default_es_simple(self):
        """Requirement por defecto es mayoría simple."""
        d = _desglose(a_favor=10, en_contra=5)
        assert determinar_resultado_votacion(d) == "aprobada"
        assert determinar_resultado_votacion(d, requirement="mayoria_simple") == "aprobada"

    def test_requirement_desconocido_fallback_simple(self):
        """Requirement desconocido → fallback a mayoría simple."""
        d = _desglose(a_favor=60, en_contra=40)
        assert determinar_resultado_votacion(d, requirement="desconocido") == "aprobada"

    def test_requirement_unanime_es_simple(self):
        """Requirement 'unanime' se trata como mayoría simple."""
        d = _desglose(a_favor=60, en_contra=40)
        assert determinar_resultado_votacion(d, requirement="unanime") == "aprobada"

    def test_valores_grandes(self):
        """Valores grandes típicos del pleno (500 diputados)."""
        d = _desglose(a_favor=350, en_contra=150)
        assert determinar_resultado_votacion(d) == "aprobada"


class TestDeterminarResultadoVotacionCalificada:
    """Tests para determinar_resultado_votacion() con mayoría calificada (2/3)."""

    def test_calificada_aprobada(self):
        """Mayoría calificada: favor >= 2/3 de presentes → aprobada."""
        # 90 de 120 = 75% >= 66.67%
        d = _desglose(a_favor=90, en_contra=20, abstencion=10)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_calificada_umbral_exacto(self):
        """Mayoría calificada: favor = 2/3 exacto → aprobada (>=)."""
        # 80 de 120 = 66.67% exacto
        d = _desglose(a_favor=80, en_contra=40, abstencion=0)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_calificada_rechazada(self):
        """Mayoría calificada: favor < 2/3 → rechazada."""
        # 70 de 120 = 58.3% < 66.67%
        d = _desglose(a_favor=70, en_contra=40, abstencion=10)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "rechazada"

    def test_calificada_presentes_cero(self):
        """Mayoría calificada con presentes = 0 → rechazada."""
        d = _desglose(a_favor=0, en_contra=0, abstencion=0)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "rechazada"

    def test_calificada_abstenciones_cuentan_como_presentes(self):
        """Abstenciones cuentan como presentes para calcular 2/3."""
        # 80 pro + 20 contra + 20 abst = 120 presentes
        # 2/3 de 120 = 80, 80 >= 80 → aprobada
        d = _desglose(a_favor=80, en_contra=20, abstencion=20)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_calificada_abstencion_alta_rechaza(self):
        """Muchas abstenciones dificultan alcanzar 2/3."""
        # 50 pro + 10 contra + 60 abst = 120 presentes
        # 2/3 de 120 = 80, 50 < 80 → rechazada
        d = _desglose(a_favor=50, en_contra=10, abstencion=60)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "rechazada"

    def test_calificada_solo_favor_y_abstencion_rechaza(self):
        """Sin votos en contra, pero muchas abstenciones → rechazada."""
        # 70 pro + 0 contra + 40 abst = 110 presentes
        # 2/3 de 110 = 73.33, 70 < 73.33 → rechazada
        d = _desglose(a_favor=70, en_contra=0, abstencion=40)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "rechazada"

    def test_calificada_solo_favor_y_abstencion_aprueba(self):
        """Sin votos en contra, favor >= 2/3 de presentes → aprobada."""
        # 80 pro + 0 contra + 40 abst = 120 presentes
        # 2/3 de 120 = 80, 80 >= 80 → aprobada
        d = _desglose(a_favor=80, en_contra=0, abstencion=40)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_calificada_un_voto_de_diferencia(self):
        """Un voto por debajo del umbral → rechazada."""
        # 79 pro + 40 contra + 0 abst = 119 presentes
        # 2/3 de 119 = 79.33, 79 < 79.33 → rechazada
        d = _desglose(a_favor=79, en_contra=40, abstencion=0)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "rechazada"

    def test_calificada_valores_grandes(self):
        """Pleno completo: ~450 presentes de 500 diputados."""
        # 350 pro + 50 contra + 50 abst = 450 presentes
        # 2/3 de 450 = 300, 350 >= 300 → aprobada
        d = _desglose(a_favor=350, en_contra=50, abstencion=50)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_calificada_no_hay_empate(self):
        """En calificada nunca hay empate: siempre aprobada o rechazada."""
        d = _desglose(a_favor=50, en_contra=50, abstencion=0)
        # 100 presentes, 2/3 = 66.67, 50 < 66.67 → rechazada
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "rechazada"


class TestDeterminarResultadoVotacionEdgeCases:
    """Edge cases y regresión para determinar_resultado_votacion()."""

    def test_solo_asistencia_no_cuenta_como_presente(self):
        """solo_asistencia no se usa en el cálculo (solo favor/contra/abstencion)."""
        # Calificada: 80 pro + 40 contra + 0 abst = 120 presentes
        # solo_asistencia no afecta el cálculo
        d = _desglose(a_favor=80, en_contra=40, abstencion=0, solo_asistencia=50)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_ausente_no_cuenta_como_presente(self):
        """ausente no afecta el cálculo de mayoría calificada."""
        # Calificada: 90 pro + 10 contra + 0 abst = 100 presentes
        # 2/3 de 100 = 66.67, 90 >= 66.67 → aprobada (sin importar ausentes)
        d = _desglose(a_favor=90, en_contra=10, abstencion=0, ausente=400)
        assert determinar_resultado_votacion(d, requirement="mayoria_calificada") == "aprobada"

    def test_simple_un_favor_cero_contra(self):
        """Un solo voto a favor, cero en contra → aprobada."""
        d = _desglose(a_favor=1, en_contra=0)
        assert determinar_resultado_votacion(d) == "aprobada"

    def test_simple_cero_favor_un_contra(self):
        """Cero a favor, un voto en contra → rechazada."""
        d = _desglose(a_favor=0, en_contra=1)
        assert determinar_resultado_votacion(d) == "rechazada"


# ===================================================================
# TestParsearFechaSitl
# ===================================================================


class TestParsearFechaSitl:
    """Tests para parsear_fecha_sitl() — formato SITL a ISO 8601."""

    def test_formato_sitl_estandar(self):
        """Formato estándar SITL: '10 Diciembre 2024' → '2024-12-10'."""
        assert parsear_fecha_sitl("10 Diciembre 2024") == "2024-12-10"

    def test_formato_iso_directo(self):
        """Formato ISO ya formado: '2024-12-10' → '2024-12-10'."""
        assert parsear_fecha_sitl("2024-12-10") == "2024-12-10"

    def test_formato_barra(self):
        """Formato DD/MM/YYYY: '10/12/2024' → '2024-12-10'."""
        assert parsear_fecha_sitl("10/12/2024") == "2024-12-10"

    def test_dia_un_digito(self):
        """Día de un dígito se zfill: '5 Enero 2024' → '2024-01-05'."""
        assert parsear_fecha_sitl("5 Enero 2024") == "2024-01-05"

    def test_todos_los_meses(self):
        """Todos los meses en español se parsean correctamente."""
        expected = [
            ("1 Enero 2024", "2024-01-01"),
            ("2 Febrero 2024", "2024-02-02"),
            ("3 Marzo 2024", "2024-03-03"),
            ("4 Abril 2024", "2024-04-04"),
            ("5 Mayo 2024", "2024-05-05"),
            ("6 Junio 2024", "2024-06-06"),
            ("7 Julio 2024", "2024-07-07"),
            ("8 Agosto 2024", "2024-08-08"),
            ("9 Septiembre 2024", "2024-09-09"),
            ("10 Octubre 2024", "2024-10-10"),
            ("11 Noviembre 2024", "2024-11-11"),
            ("12 Diciembre 2024", "2024-12-12"),
        ]
        for fecha_str, expected_iso in expected:
            assert parsear_fecha_sitl(fecha_str) == expected_iso, f"Falló: {fecha_str}"

    def test_espacios_extra(self):
        """Espacios múltiples se normalizan: '10   Diciembre   2024'."""
        assert parsear_fecha_sitl("10   Diciembre   2024") == "2024-12-10"

    def test_espacios_alrededor(self):
        """Espacios al inicio y final se eliminan."""
        assert parsear_fecha_sitl("  10 Diciembre 2024  ") == "2024-12-10"

    def test_vacio(self):
        """String vacío → string vacío."""
        assert parsear_fecha_sitl("") == ""

    def test_solo_espacios(self):
        """Solo espacios → string vacío."""
        assert parsear_fecha_sitl("   ") == ""

    def test_formato_guion_en_lugar_de_espacio(self):
        """Guiones como separador: '10-Diciembre-2024' → '2024-12-10'."""
        assert parsear_fecha_sitl("10-Diciembre-2024") == "2024-12-10"

    def test_formato_barra_dia_un_digito(self):
        """DD/MM/YYYY con día de un dígito: '5/3/2024' → '2024-03-05'."""
        assert parsear_fecha_sitl("5/3/2024") == "2024-03-05"

    def test_mes_minusculas(self):
        """Mes en minúsculas: '10 diciembre 2024' → '2024-12-10'."""
        assert parsear_fecha_sitl("10 diciembre 2024") == "2024-12-10"

    def test_mes_mixed_case(self):
        """Mes en mixed case: '10 DICIEMBRE 2024' → '2024-12-10'."""
        assert parsear_fecha_sitl("10 DICIEMBRE 2024") == "2024-12-10"

    def test_formato_irreconocible_retorna_original(self):
        """Formato irreconocible → retorna el string original."""
        assert parsear_fecha_sitl("no es una fecha") == "no es una fecha"

    def test_fecha_real_sitl(self):
        """Fecha real del SITL."""
        assert parsear_fecha_sitl("27 Febrero 2025") == "2025-02-27"


# ===================================================================
# TestSentidoToOption
# ===================================================================


class TestSentidoToOption:
    """Tests para sentido_to_option() — sentido SITL a formato Popolo."""

    def test_a_favor(self):
        """'A favor' → 'a_favor'."""
        assert sentido_to_option("A favor") == "a_favor"

    def test_en_contra(self):
        """'En contra' → 'en_contra'."""
        assert sentido_to_option("En contra") == "en_contra"

    def test_ausente(self):
        """'Ausente' → 'ausente'."""
        assert sentido_to_option("Ausente") == "ausente"

    def test_abstencion_sin_acento(self):
        """'Abstencion' → 'abstencion'."""
        assert sentido_to_option("Abstencion") == "abstencion"

    def test_abstencion_con_acento(self):
        """'Abstención' → 'abstencion'."""
        assert sentido_to_option("Abstención") == "abstencion"

    def test_solo_asistencia(self):
        """'Solo asistencia' → 'abstencion'."""
        assert sentido_to_option("Solo asistencia") == "abstencion"

    def test_desconocido_devuelve_ausente(self):
        """Sentido no reconocido → 'ausente'."""
        assert sentido_to_option("No reconocido") == "ausente"

    def test_vacio_devuelve_ausente(self):
        """String vacío → 'ausente'."""
        assert sentido_to_option("") == "ausente"

    def test_a_favor_minusculas(self):
        """'a favor' en minúsculas → 'a_favor'."""
        assert sentido_to_option("a favor") == "a_favor"

    def test_en_contra_mayusculas(self):
        """'EN CONTRA' en mayúsculas → 'en_contra'."""
        assert sentido_to_option("EN CONTRA") == "en_contra"

    def test_espacios_extra(self):
        """Espacios extra alrededor: '  A favor  ' → 'a_favor'."""
        assert sentido_to_option("  A favor  ") == "a_favor"

    def test_ausente_mixed_case(self):
        """Mixed case: 'AUSENTE' → 'ausente'."""
        assert sentido_to_option("AUSENTE") == "ausente"

    def test_abstencion_mixed_case(self):
        """Mixed case con acento: 'ABSTENCIÓN' → 'abstencion'."""
        assert sentido_to_option("ABSTENCIÓN") == "abstencion"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
