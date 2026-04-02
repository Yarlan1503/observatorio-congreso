"""
resultados.py — Parser para la página de resultados del SIL.

Extrae la lista de votaciones de los resultados de búsqueda,
con soporte para paginación y texto plano.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from scraper_sil.models import SILVotacionIndex

logger = logging.getLogger(__name__)

# ============================================================================
# PATTERNS para parsing de texto plano
# ============================================================================

PATTERN_ASUNTO = re.compile(r"&nbsp;(\d+)(.*?)(?=A\s+favor:)", re.DOTALL)

PATTERN_VOTOS = re.compile(
    r"A\s+favor:\s*(\d+)\s*"
    r"En\s+contra:\s*(\d+)\s*"
    r"Abstenció[n]:\s*(\d+)",
    re.IGNORECASE,
)

PATTERN_CLAVE = re.compile(r"ClaveAsunto=(\d+)", re.IGNORECASE)

PATTERN_ESTATUS = re.compile(
    r"Pendiente\s+en\s+comisi(?:ó|o)n\s*\(?\s*es\s*\)?\s+de\s+revisora\s+el\s+(\d{2}-[A-Z]{3}-\d{4})",
    re.IGNORECASE,
)


def parse_resultados(texto: str) -> tuple[list[SILVotacionIndex], int]:
    """Extrae la lista de votaciones de la página de resultados.

    Auto-detecta si el input es HTML (contiene <table>) o texto plano
    y usa el parser apropiado.

    Args:
        texto: HTML o texto plano de la página de resultados.

    Returns:
        Tuple de (lista de votaciones, número total de resultados).
    """
    # Auto-detección: si contiene <table> usar parser HTML, si no texto plano
    if "<table" in texto.lower():
        return _parse_resultados_html(texto)
    else:
        return parse_resultados_text(texto)


def _parse_resultados_html(html: str) -> tuple[list[SILVotacionIndex], int]:
    """Parser HTML para resultados con tabla.

    Args:
        html: HTML de la página de resultados.

    Returns:
        Tuple de (lista de votaciones, número total de resultados).
    """
    soup = BeautifulSoup(html, "lxml")
    votaciones: list[SILVotacionIndex] = []

    # Buscar la tabla de resultados
    # El SIL usa diferentes estructuras, intentamos varias
    table = soup.find(
        "table", {"class": re.compile(r"table|result|busqueda", re.I)}
    ) or soup.find("table")

    if not table:
        logger.warning("No se encontró tabla de resultados")
        return [], 0

    # Buscar las filas con datos de votaciones
    rows = table.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        # Intentar extraer datos de la fila
        votacion = _parse_row(row, cells)
        if votacion:
            votaciones.append(votacion)

    # Extraer total de resultados
    total = _extract_total_resultados(soup)

    logger.info(f"Parsed {len(votaciones)} votaciones de la página (total: {total})")
    return votaciones, total


def parse_resultados_text(texto_plano: str) -> tuple[list[SILVotacionIndex], int]:
    """Parsea texto plano de resultados de búsqueda SIL.

    El texto plano viene sin tags HTML. Estructura observada:
        &nbsp;1Dictamen a discusiónCon proyecto de decreto...
                  A favor: 102
                  En contra: 0
                  Abstención: 0
                   Pendiente en comisión(es) de revisora el 03-DIC-2025

    Args:
        texto_plano: Texto plano de la respuesta del servidor.

    Returns:
        Tuple de (lista de votaciones, número total de resultados).
    """
    votaciones: list[SILVotacionIndex] = []

    # Split por bloques &nbsp;N (donde N es número de asunto)
    # IMPORTANTE: hacer el split ANTES de reemplazar &nbsp; por espacio
    bloques = re.split(r"&nbsp;(\d+)", texto_plano)

    # El primer elemento puede venir vacío o con texto antes del primer &nbsp;
    # Empezamos desde el índice 1 que es el primer número
    i = 1
    while i < len(bloques) - 1:
        numero = bloques[i].strip()
        contenido = bloques[i + 1] if i + 1 < len(bloques) else ""

        if numero and contenido:
            # Normalizar entidades HTML en el contenido del bloque
            contenido_normalizado = contenido.replace("&nbsp;", " ").replace(
                "&amp;", "&"
            )
            votacion = _parse_bloque_text(numero, contenido_normalizado)
            if votacion:
                votaciones.append(votacion)

        i += 2  # Saltar número y contenido

    # Extraer total de resultados del texto
    total = _extract_total_from_text(texto_plano)

    logger.info(f"Parsed {len(votaciones)} votaciones de texto plano (total: {total})")
    return votaciones, total


def _parse_bloque_text(numero: str, contenido: str) -> Optional[SILVotacionIndex]:
    """Parsea un bloque individual de texto plano.

    Args:
        numero: Número de asunto.
        contenido: Texto del bloque.

    Returns:
        SILVotacionIndex si se parseó correctamente, None si no.
    """
    try:
        # Extraer descripción (todo antes de "A favor:")
        match_asunto = PATTERN_ASUNTO.search(contenido)
        if not match_asunto:
            # Intentar con descripción directa antes de "A favor:"
            desc_match = re.search(r"^(.*?)\s*A\s+favor:", contenido, re.DOTALL)
            if desc_match:
                titulo = desc_match.group(1).strip()
            else:
                titulo = contenido.strip()
        else:
            # El número ya lo tenemos, la descripción está antes de "A favor:"
            titulo = match_asunto.group(2).strip() if match_asunto.group(2) else ""

        # Extraer votos
        match_votos = PATTERN_VOTOS.search(contenido)
        if match_votos:
            a_favor = int(match_votos.group(1))
            en_contra = int(match_votos.group(2))
            abstencion = int(match_votos.group(3))
        else:
            a_favor = en_contra = abstencion = 0

        # Extraer ClaveAsunto del contenido (buscar en enlaces o referencias)
        clave_asunto = numero  # Usar el número como clave por defecto
        match_clave = PATTERN_CLAVE.search(contenido)
        if match_clave:
            clave_asunto = match_clave.group(1)

        # Extraer estatus (fecha de pendiente)
        estatus_match = PATTERN_ESTATUS.search(contenido)
        resultado = ""
        if estatus_match:
            resultado = f"Pendiente de revisora el {estatus_match.group(1)}"

        # Extraer legislature si está presente
        legislature = ""
        leg_match = re.search(r"L[VIXL]+", contenido, re.I)
        if leg_match:
            legislature = leg_match.group().upper()

        # Extraer fecha si está presente
        fecha = ""
        fecha_match = re.search(r"\d{2}/\d{2}/\d{4}", contenido)
        if fecha_match:
            fecha = fecha_match.group()

        return SILVotacionIndex(
            clave_asunto=clave_asunto,
            clave_tramite="",
            titulo=titulo[:500] if titulo else "",
            legislature=legislature,
            fecha=fecha,
            resultado=resultado,
            tipo_asunto="",
            num_votos=a_favor + en_contra + abstencion
            if a_favor or en_contra or abstencion
            else None,
        )

    except Exception as e:
        logger.debug(f"Error parsing bloque text: {e}")
        return None


def _extract_total_from_text(texto: str) -> int:
    """Extrae el total de resultados del texto plano.

    Args:
        texto: Texto con información de paginación.

    Returns:
        Total de resultados, 0 si no se encontró.
    """
    patterns = [
        r"de\s+([\d,]+)\s+resultados",
        r"Total\s*:?\s*([\d,]+)",
        r"Se\s+encontraron\s+([\d,]+)",
        r"registros?\s*:?\s*([\d,]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, texto, re.IGNORECASE)
        if match:
            total_str = match.group(1).replace(",", "")
            return int(total_str)

    return 0


def _parse_row(row: BeautifulSoup, cells: list) -> Optional[SILVotacionIndex]:
    """Parsea una fila de la tabla de resultados.

    Args:
        row: Elemento <tr>.
        cells: Lista de elementos <td>.

    Returns:
        SILVotacionIndex si se parseó correctamente, None si no.
    """
    try:
        if len(cells) < 4:
            return None

        # Los índices de columnas varían, buscamos por contenido
        # Típicamente: Fecha | Legislative | Clave | Descripción | Resultado
        texto_cells = [c.get_text(strip=True) for c in cells]

        # Buscar clave de asunto (patrón: número de al menos 4 dígitos)
        clave_asunto = ""
        clave_tramite = ""
        for i, texto in enumerate(texto_cells):
            match = re.search(r"^\d{4,}$", texto.replace("-", ""))
            if match:
                clave_asunto = match.group()
                # Puede estar en formato "1234-1" o "1234"
                parts = texto.split("-")
                clave_asunto = parts[0]
                if len(parts) > 1:
                    clave_tramite = parts[1]
                break

        if not clave_asunto:
            # Buscar en enlaces de la fila
            links = row.find_all("a")
            for link in links:
                href = link.get("href", "")
                match = re.search(r"ClaveAsunto=(\d+)", href)
                if match:
                    clave_asunto = match.group(1)
                    # Extraer clave_tramite si está
                    tramite_match = re.search(r"ClaveTramite=(\d+)", href)
                    if tramite_match:
                        clave_tramite = tramite_match.group(1)
                    break

        if not clave_asunto:
            return None

        # Extraer legislature (buscar patrón LXXVI, etc.)
        legislature = ""
        for texto in texto_cells:
            match = re.search(r"L[VIXL]+", texto, re.I)
            if match:
                legislature = match.group().upper()
                break

        # Extraer fecha (patrón dd/mm/yyyy o similar)
        fecha = ""
        for texto in texto_cells:
            match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", texto)
            if match:
                fecha = match.group()
                break

        # Extraer título/descripción (generalmente la celda más larga)
        titulo = ""
        for i, texto in enumerate(texto_cells):
            if len(texto) > len(titulo) and i > 0:
                titulo = texto

        # Extraer resultado
        resultado = ""
        for texto in texto_cells:
            texto_lower = texto.lower()
            if any(
                r in texto_lower
                for r in ["aprobado", "rechazado", "desechado", "empate"]
            ):
                resultado = texto
                break

        # Extraer tipo de asunto
        tipo_asunto = ""
        for cell in cells:
            # Buscar en atributos o texto
            cell_text = cell.get_text(strip=True)
            for tipo_key, tipo_val in [
                ("reforma", "Reforma Constitucional"),
                ("ley", "Ley o Decreto"),
                ("punto", "Punto de Acuerdo"),
                ("nombramiento", "Nombramiento"),
                ("iniciativa", "Iniciativa"),
            ]:
                if tipo_key in cell_text.lower():
                    tipo_asunto = tipo_val
                    break

        return SILVotacionIndex(
            clave_asunto=clave_asunto,
            clave_tramite=clave_tramite,
            titulo=titulo[:500] if titulo else "",  # Limitar longitud
            legislature=legislature,
            fecha=fecha,
            resultado=resultado,
            tipo_asunto=tipo_asunto,
        )

    except Exception as e:
        logger.debug(f"Error parsing row: {e}")
        return None


def _extract_total_resultados(soup: BeautifulSoup) -> int:
    """Extrae el número total de resultados de la página.

    Args:
        soup: BeautifulSoup de la página.

    Returns:
        Total de resultados, 0 si no se encontró.
    """
    # Buscar en textos que contengan "resultados" o "registros"
    text = soup.get_text()

    patterns = [
        # "1 - 50 de 2,450 resultados" o "1 - 50 de 2450 resultados"
        r"(\d[\d,]*)\s*$",  # Número con comas al final
        r"de\s+([\d,]+)\s+resultados",
        r"de\s+(\d+)\s*-?\s*\d*\s*de\s+(\d+)",
        r"Registros\s*:?\s*(\d+)\s*a\s*\d+\s+de\s+(\d+)",
        r"Total\s*:?\s*(\d+)",
        r"Se\s+encontraron\s+(\d+)\s+resultados",
        r"(\d+)\s+resultados?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Usar el último grupo que generalmente es el total
            total_str = match.group(len(match.groups()))
            # Remover comas para obtener el número
            total = int(total_str.replace(",", ""))
            return total

    return 0


def parse_paginacion(html: str) -> dict:
    """Extrae información de paginación de la página de resultados.

    Args:
        html: HTML de la página de resultados.

    Returns:
        Dict con:
        {
            'current_page': int,
            'total_pages': int,
            'results_per_page': int,
            'total_results': int
        }
    """
    soup = BeautifulSoup(html, "lxml")
    info = {
        "current_page": 1,
        "total_pages": 1,
        "results_per_page": 50,
        "total_results": 0,
    }

    text = soup.get_text()

    # Extraer pagina actual (con o sin acento)
    match = re.search(r"[Pp]á?gina\s+(\d+)\s+de\s+(\d+)", text)
    if match:
        info["current_page"] = int(match.group(1))
        info["total_pages"] = int(match.group(2))

    # Extraer total de resultados
    match = re.search(r"(\d+)\s+-\s+\d+\s+de\s+([\d,]+)", text)
    if match:
        total_str = match.group(2).replace(",", "")
        info["total_results"] = int(total_str)

    # Buscar selector de paginas
    paginas_select = soup.find(
        "select", {"name": re.compile(r"paginas|pagination", re.I)}
    )
    if paginas_select:
        for option in paginas_select.find_all("option"):
            if "selected" in option.attrs:
                info["results_per_page"] = int(option.get("value", 50))
                break

    return info
