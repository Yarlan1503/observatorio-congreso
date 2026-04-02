"""Módulo de URLs para el scraper del Senado LXVI (66° legislativa)."""

BASE_URL = "https://www.senado.gob.mx"


def url_indice_votaciones() -> str:
    """Retorna la ruta relativa al índice de votaciones del Senado LXVI.

    Returns:
        str: Ruta relativa '/66/votaciones/'
    """
    return "/66/votaciones/"


def url_votacion(id: int) -> str:
    """Retorna la ruta relativa a una votación específica.

    Args:
        id: Identificador de la votación.

    Returns:
        str: Ruta relativa '/66/votacion/{id}'
    """
    return f"/66/votacion/{id}"


def url_votos_ajax(id: int, cell: int = 1, order: str = "DESC") -> str:
    """Retorna la ruta relativa para obtener los votos vía AJAX.

    Args:
        id: Identificador de la votación.
        cell: Número de celda/columna para ordenar (default 1).
        order: Orden de排序 ('ASC' o 'DESC', default 'DESC').

    Returns:
        str: Ruta relativa al endpoint AJAX de votos.
    """
    return f"/66/app/votaciones/functions/viewTableVot.php?action=ajax&cell={cell}&order={order}&votacion={id}&q="


def url_senadores() -> str:
    """Retorna la ruta relativa a la lista de senadores del LXVI.

    Returns:
        str: Ruta relativa '/66/senadores'
    """
    return "/66/senadores"
