"""
legislatura.py — Datos y URLs por legislatura del SITL/INFOPAL.

Genera las URLs correctas para cada página del sistema SITL
según la legislatura y el tipo de consulta.
"""

from .config import LEGISLATURAS


def get_legislatura_data(leg: str) -> dict:
    """Retorna los datos de una legislatura. Lanza KeyError si no existe."""
    return LEGISLATURAS[leg]


def _base(leg: str) -> str:
    """URL base para una legislatura.

    LX-LXIII: subdominio propio (ej: http://sitllx.diputados.gob.mx)
    LXIV-LXVI: dominio principal con path prefix (ej: https://sitl.diputados.gob.mx/LXVI_leg)
    """
    data = get_legislatura_data(leg)
    return data["base_url"]


def _suffix(leg: str) -> str:
    """Sufijo PHP para la legislatura (ej: 'nplxvi' para LXVI).

    Se concatena directamente SIN guion bajo, ya que el SITL usa
    el patrón: estadistico_votacionnplxvi.php (no estadistico_votacion_nplxvi.php).
    """
    data = get_legislatura_data(leg)
    sfx = data.get("php_suffix", "")
    return sfx


# Legislaturas LXIV+ no tienen sistema.htm — retornar base URL como fallback
_SISTEMA_HTM_LEGISLATURAS = {"LX", "LXI", "LXII", "LXIII"}


def url_sistema(leg: str) -> str:
    """URL base del sistema INFOPAL para una legislatura.

    LX-LXIII: subdominio propio con sistema.htm disponible.
    LXIV-LXVI: mismo dominio con path prefix; sistema.htm no existe,
    así que se retorna la base URL como fallback.
    """
    base = _base(leg)
    if leg in _SISTEMA_HTM_LEGISLATURAS:
        return f"{base}/sistema.htm"
    return base


def url_votaciones_por_periodo(leg: str, periodo: int) -> str:
    """URL del listado de votaciones de un periodo legislativo.

    LXVI: votacionesxperiodonplxvi.php?pert={periodo}
    """
    return f"{_base(leg)}/votacionesxperiodo{_suffix(leg)}.php?pert={periodo}"


def url_estadistico(leg: str, votacion_id: int) -> str:
    """URL del desglose estadístico de una votación.

    LXVI: estadistico_votacionnplxvi.php?votaciont={votacion_id}
    """
    return f"{_base(leg)}/estadistico_votacion{_suffix(leg)}.php?votaciont={votacion_id}"


def url_nominal(leg: str, partido_id: int, votacion_id: int) -> str:
    """URL del listado nominal de un partido en una votación.

    LXVI: listados_votacionesnplxvi.php?partidot={partido_id}&votaciont={votacion_id}
    """
    return (
        f"{_base(leg)}/listados_votaciones{_suffix(leg)}.php"
        f"?partidot={partido_id}&votaciont={votacion_id}"
    )


def url_historial_legislador(leg: str, diputado_id: int, periodo: int) -> str:
    """URL del historial de votaciones de un diputado por periodo.

    LXVI: votaciones_por_pernplxvi.php?iddipt={diputado_id}&pert={periodo}
    """
    return f"{_base(leg)}/votaciones_por_per{_suffix(leg)}.php?iddipt={diputado_id}&pert={periodo}"


def url_curricula(leg: str, diputado_id: int) -> str:
    """URL de la ficha curricular de un diputado.

    LXVI: curricula.php?dipt={diputado_id}
    """
    return f"{_base(leg)}/curricula.php?dipt={diputado_id}"


def url_composicion(leg: str) -> str:
    """URL de la página de composición del pleno (info_diputados.php).

    LXVI: info_diputados.php
    """
    return f"{_base(leg)}/info_diputados.php"


def url_votaciones_diputado(leg: str, diputado_id: int, periodo: int) -> str:
    """URL de las votaciones de un diputado en un periodo.

    LXVI: votaciones_diputados_xperiodonplxvi.php?dipt={id}
    """
    sfx = _suffix(leg)
    return f"{_base(leg)}/votaciones_diputados_xperiodo{sfx}.php?dipt={diputado_id}"
