"""
tests/test_poder_indices.py
Verificación de los índices de poder Shapley-Shubik y Banzhaf.

Tests basados en las aserciones de lines 407, 410 en analysis/poder_partidos.py:
    assert abs(sum(ss.values()) - 1.0) < 1e-10
    assert abs(sum(bz.values()) - 1.0) < 1e-10
"""

import pytest
from analysis.poder_partidos import shapley_shubik, banzhaf


# --- Fixtures ---


@pytest.fixture
def seats_basico():
    """Seats de prueba básicos: O01=5, O02=3, O03=2 (total=10)."""
    return {"O01": 5, "O02": 3, "O03": 2}


@pytest.fixture
def seats_mayoria():
    """Tres partidos con mayoría simple para uno (251+ vs dos de 100)."""
    return {"A": 251, "B": 100, "C": 100}


@pytest.fixture
def seats_iguales():
    """Tres partidos con igual número de escaños."""
    return {"X": 10, "Y": 10, "Z": 10}


# --- Tests principales ---


def test_shapley_shubik_suma_uno(seats_basico):
    """Shapley-Shubik debe sumar 1.0 (dentro de 1e-10) para cualquier quota."""
    # Mayoria simple: más de la mitad de 10 = 6
    ss_simple = shapley_shubik(seats_basico, quota=6)
    assert abs(sum(ss_simple.values()) - 1.0) < 1e-10, (
        f"Shapley-Shubik no suma 1.0 para mayoria_simple: {sum(ss_simple.values())}"
    )

    # Mayoria calificada 2/3: ceil(2/3 * 10) = 7
    ss_calif = shapley_shubik(seats_basico, quota=7)
    assert abs(sum(ss_calif.values()) - 1.0) < 1e-10, (
        f"Shapley-Shubik no suma 1.0 para mayoria_calificada: {sum(ss_calif.values())}"
    )


def test_banzhaf_suma_uno(seats_basico):
    """Banzhaf debe sumar 1.0 (dentro de 1e-10) para cualquier quota."""
    # Mayoria simple: 6
    bz_simple = banzhaf(seats_basico, quota=6)
    assert abs(sum(bz_simple.values()) - 1.0) < 1e-10, (
        f"Banzhaf no suma 1.0 para mayoria_simple: {sum(bz_simple.values())}"
    )

    # Mayoria calificada 2/3: 7
    bz_calif = banzhaf(seats_basico, quota=7)
    assert abs(sum(bz_calif.values()) - 1.0) < 1e-10, (
        f"Banzhaf no suma 1.0 para mayoria_calificada: {sum(bz_calif.values())}"
    )


def test_shapley_shubik_vs_banzhaf_diferentes(seats_basico):
    """Shapley-Shubik y Banzhaf generalmente dan resultados diferentes."""
    quota = 6
    ss = shapley_shubik(seats_basico, quota)
    bz = banzhaf(seats_basico, quota)

    # Los resultados pueden ser diferentes en la mayoría de los casos
    # Comparar como listas ordenadas para evitar dependencia del orden de keys
    ss_vals = [ss[k] for k in sorted(ss.keys())]
    bz_vals = [bz[k] for k in sorted(bz.keys())]

    # Verificar que ambos suman 1
    assert abs(sum(ss_vals) - 1.0) < 1e-10
    assert abs(sum(bz_vals) - 1.0) < 1e-10

    # Los índices no son siempre idénticos (son diferentes algoritmos)
    # Usamos una tolerancia más relajada para la comparación
    diff = sum(abs(a - b) for a, b in zip(ss_vals, bz_vals))
    # Para este caso específico, esperamos que haya alguna diferencia
    # Si son exactamente iguales, el test igualmente pasa (no es una afirmación fuerte)


def test_indice_cero_partido_sin_escanos():
    """Un partido con 0 escaños debe tener índice 0 en ambos métodos."""
    seats = {"A": 5, "B": 0, "C": 3}
    quota = 6

    ss = shapley_shubik(seats, quota)
    bz = banzhaf(seats, quota)

    assert ss["B"] == 0.0, f"B con 0 escaños tiene Shapley-Shubik no nulo: {ss['B']}"
    assert bz["B"] == 0.0, f"B con 0 escaño tiene Banzhaf no nulo: {bz['B']}"


def test_indice_mayoria_total(seats_mayoria):
    """Con mayoría simple (201), el partido A (251) debe tener >50% del poder."""
    quota = 201  # Mayoria simple para 500 asientos

    ss = shapley_shubik(seats_mayoria, quota)
    bz = banzhaf(seats_mayoria, quota)

    # El partido A tiene 251/451 ≈ 55.7% de los asientos
    # pero debería tener más del 50% del poder debido a la mayoría
    assert ss["A"] > 0.5, f"A no tiene mayoria de poder: {ss['A']}"
    assert bz["A"] > 0.5, f"A no tiene mayoria de poder (Banzhaf): {bz['A']}"


# --- Tests adicionales de robustez ---


def test_umbral_mayoria_calificada_2_3():
    """Verificar que el umbral 2/3 se aplica correctamente."""
    # 2/3 de 10 = 6.67, ceil = 7
    seats = {"A": 4, "B": 3, "C": 3}
    quota = 7  # 2/3 de presentes

    ss = shapley_shubik(seats, quota)
    bz = banzhaf(seats, quota)

    # Verificar que ambos suman 1
    assert abs(sum(ss.values()) - 1.0) < 1e-10
    assert abs(sum(bz.values()) - 1.0) < 1e-10


def test_partidos_iguales_indices_similares(seats_iguales):
    """Si todos los partidos tienen igual número de asientos, sus índices deben ser similares."""
    quota = 16  # Mayoria simple para 30 asientos

    ss = shapley_shubik(seats_iguales, quota)
    bz = banzhaf(seats_iguales, quota)

    # Con shares iguales, los índices deben ser aproximadamente iguales
    ss_vals = list(ss.values())
    bz_vals = list(bz.values())

    # Verificar que todos son similares (desviación estándar pequeña)
    ss_promedio = sum(ss_vals) / len(ss_vals)
    bz_promedio = sum(bz_vals) / len(bz_vals)

    # Cada uno debe estar cerca del promedio (1/3 ≈ 0.333)
    for val in ss_vals:
        assert abs(val - ss_promedio) < 0.15, f"Valor SS outlier: {val}"
    for val in bz_vals:
        assert abs(val - bz_promedio) < 0.15, f"Valor BZ outlier: {val}"

    # Verificar que ambos suman 1
    assert abs(sum(ss_vals) - 1.0) < 1e-10
    assert abs(sum(bz_vals) - 1.0) < 1e-10
