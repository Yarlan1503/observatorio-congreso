"""
tests/test_transformers_senado.py — Tests para scraper/senado/transformers.py (Senado).

Ejecutar con: pytest tests/
"""

import pytest
from senado.scraper.transformers import (
    normalizar_nombre as senado_normalizar_nombre,
    voto_to_option,
)


# ============================================================
# Tests: scraper/senado/transformers.py — normalizar_nombre (Senado)
# ============================================================


class TestSenadoNormalizarNombre:
    """Tests para la función normalizar_nombre del Senado."""

    def test_strip_prefijo_sen(self):
        """Strip prefijo 'Sen. ' del nombre y normaliza acentos."""
        result = senado_normalizar_nombre("Sen. Juan Pérez García")
        assert result == "juan perez garcia", (
            "Debe eliminar prefijo Sen. y normalizar acentos"
        )

    def test_strip_prefijo_sen_sin_punto(self):
        """Strip prefijo 'Sen ' (sin punto) y normaliza acentos."""
        result = senado_normalizar_nombre("Sen Juan Pérez García")
        assert result == "juan perez garcia", (
            "Debe eliminar prefijo Sen y normalizar acentos"
        )

    def test_normaliza_acentos(self):
        """Verifica normalización de acentos (se eliminan)."""
        result = senado_normalizar_nombre("Sen. José María López")
        assert result == "jose maria lopez", "Debe normalizar acentos (eliminarlos)"

    def test_lowercase(self):
        """Todo debe ser lowercase y sin acentos."""
        result = senado_normalizar_nombre("Sen. ÁLVARO MÉNDEZ")
        assert result == "alvaro mendez", "Debe ser lowercase y sin acentos"

    def test_colapsa_espacios(self):
        """Espacios múltiples → espacio simple y sin acentos."""
        result = senado_normalizar_nombre("Sen.  Juan   Pérez  ")
        assert result == "juan perez", "Debe colapsar espacios y normalizar acentos"

    def test_sin_prefijo_pasa_normal(self):
        """Nombre sin prefijo se normaliza (sin acentos)."""
        result = senado_normalizar_nombre("María González López")
        assert result == "maria gonzalez lopez", (
            "Sin prefijo normaliza normalmente (sin acentos)"
        )


# ============================================================
# Tests: scraper/senado/transformers.py — voto_to_option (Senado)
# ============================================================


class TestSenadoVotoToOption:
    """Tests para la función voto_to_option del Senado."""

    def test_pro_a_favor(self):
        """'PRO' → 'a_favor'."""
        result = voto_to_option("PRO")
        assert result == "a_favor", "'PRO' debe convertirse a 'a_favor'"

    def test_en_pro_a_favor(self):
        """'EN PRO' → 'a_favor'."""
        result = voto_to_option("EN PRO")
        assert result == "a_favor", "'EN PRO' debe convertirse a 'a_favor'"

    def test_pro_case_insensitive(self):
        """'pro' (lowercase) → 'a_favor'."""
        result = voto_to_option("pro")
        assert result == "a_favor", "'pro' lowercase debe convertirse a 'a_favor'"

    def test_contra_en_contra(self):
        """'CONTRA' → 'en_contra'."""
        result = voto_to_option("CONTRA")
        assert result == "en_contra", "'CONTRA' debe convertirse a 'en_contra'"

    def test_contra_case_insensitive(self):
        """'contra' (lowercase) → 'en_contra'."""
        result = voto_to_option("contra")
        assert result == "en_contra", (
            "'contra' lowercase debe convertirse a 'en_contra'"
        )

    def test_abstencion_con_acento(self):
        """'ABSTENCIÓN' → 'abstencion'."""
        result = voto_to_option("ABSTENCIÓN")
        assert result == "abstencion", "'ABSTENCIÓN' debe convertirse a 'abstencion'"

    def test_abstencion_sin_acento(self):
        """'ABSTENCION' → 'abstencion'."""
        result = voto_to_option("ABSTENCION")
        assert result == "abstencion", "'ABSTENCION' debe convertirse a 'abstencion'"

    def test_abstencion_real(self):
        """'ABSTENCIÓN' → 'abstencion'."""
        result = voto_to_option("ABSTENCIÓN")
        assert result == "abstencion"

    def test_voto_desconocido(self):
        """Voto no reconocido → 'abstencion'."""
        result = voto_to_option("VOTO DESCONOCIDO")
        assert result == "abstencion", "Voto desconocido debe retornar 'abstencion'"
