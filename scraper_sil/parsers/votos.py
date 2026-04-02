"""
votos.py — Parser para los votos por legislador del SIL.

Extrae la lista de legisladores y su voto de la página
LegisladoresVotacionAsunto.php.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from scraper_sil.models import SILVotoLegislador, SILVotosCompletos

logger = logging.getLogger(__name__)


def parse_votos_grupo(html: str, tipo_voto: str = "F") -> list[SILVotoLegislador]:
    """Extrae lista de legisladores de una página de grupo de voto.

    Args:
        html: HTML de la página LegisladoresVotacionAsunto.php.
        tipo_voto: Tipo de voto (F=a_favor, C=en_contra, A=abstencion, N=ausente).

    Returns:
        Lista de SILVotoLegislador.
    """
    soup = BeautifulSoup(html, "lxml")
    votos: list[SILVotoLegislador] = []

    # Mapear tipo_voto a opción interna
    opcion_map = {
        "F": "a_favor",
        "C": "en_contra",
        "A": "abstencion",
        "N": "ausente",
    }
    opcion = opcion_map.get(tipo_voto.upper(), "a_favor")

    # Buscar tabla de legisladores
    table = _find_legisladores_table(soup)

    if not table:
        logger.warning(f"No se encontró tabla de legisladores para voto {tipo_voto}")
        return votos

    # Parsear filas
    rows = table.find_all("tr")
    for row in rows:
        voto = _parse_legislador_row(row, opcion, tipo_voto)
        if voto:
            votos.append(voto)

    logger.debug(f"Parsed {len(votos)} legisladores para voto {tipo_voto}")
    return votos


def _find_legisladores_table(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    """Busca la tabla de legisladores en la página.

    Args:
        soup: BeautifulSoup de la página.

    Returns:
        Table si se encuentra, None otherwise.
    """
    # Buscar por clase
    table = soup.find(
        "table", {"class": re.compile(r"legislador|votacion|detalle", re.I)}
    )
    if table:
        return table

    # Buscar por texto de headers
    tables = soup.find_all("table")
    for t in tables:
        headers = t.find_all("th")
        header_text = " ".join(h.get_text().lower() for h in headers)

        if any(
            k in header_text for k in ["nombre", "senador", "legislador", "partido"]
        ):
            return t

    # Si no hay headers, tomar la primera tabla que tenga filas con datos
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) > 2:
            first_row_text = rows[0].get_text().lower()
            if len(first_row_text) > 20:  # Tiene contenido real
                return t

    return None


def _parse_legislador_row(
    row: BeautifulSoup,
    opcion: str,
    tipo_voto: str,
) -> Optional[SILVotoLegislador]:
    """Parsea una fila de la tabla de legisladores.

    Args:
        row: Elemento <tr>.
        opcion: Opción de voto en formato interno.
        tipo_voto: Tipo de voto original (F/C/A/N).

    Returns:
        SILVotoLegislador si se parseó correctamente, None si no.
    """
    try:
        cells = row.find_all("td")
        if not cells:
            return None

        # El número de columnas varía, buscar por contexto
        texto_cells = [c.get_text(strip=True) for c in cells]

        # Buscar nombre (campo más largo que no sea partido o estado)
        nombre = ""
        partido = ""
        estado = None
        curul = None

        for i, texto in enumerate(texto_cells):
            # Ignorar números de lista
            if re.match(r"^\d+$", texto):
                continue
            # Ignorar texto vacío
            if not texto:
                continue

            # Detectar partido
            partido_upper = texto.upper()
            if partido_upper in [
                "MORENA",
                "PAN",
                "PRI",
                "PVEM",
                "PT",
                "MC",
                "PRD",
                "NA",
                "SP",
                "SG",
                "NUEVA ALIANZA",
            ]:
                partido = partido_upper
                continue

            # Detectar estado (campo con formato de estado mexicano)
            if re.match(r"^[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ\s]+$", texto) and len(texto) > 3:
                if texto not in ["MORENA", "PAN", "PRI", "PVEM", "PT", "MC"]:
                    if estado is None:
                        estado = texto

            # El nombre generalmente tiene "Sen." o "Dip." o es el más largo
            if "sen." in texto.lower() or "dip." in texto.lower():
                nombre = texto
            elif not nombre and len(texto) > 10:
                nombre = texto

        # Buscar número de curul
        curul_match = re.search(r"curul[:\s]*(\d+)", row.get_text().lower())
        if curul_match:
            curul = curul_match.group(1)

        if not nombre:
            return None

        return SILVotoLegislador(
            nombre=nombre,
            partido=partido,
            estado=estado,
            curul=curul,
            voto=opcion,
            tipo_voto=tipo_voto,
        )

    except Exception as e:
        logger.debug(f"Error parsing row: {e}")
        return None


def parse_votos_completos(
    html_favor: str,
    html_contra: str,
    html_abstencion: str,
    html_ausentes: str,
    clave_asunto: str,
    clave_tramite: str,
) -> SILVotosCompletos:
    """Combina los votos de todos los grupos en un objeto completo.

    Args:
        html_favor: HTML de la página de votos a favor.
        html_contra: HTML de la página de votos en contra.
        html_abstencion: HTML de la página de votos en abstención.
        html_ausentes: HTML de la página de votos ausentes.
        clave_asunto: Clave del asunto.
        clave_tramite: Clave del trámite.

    Returns:
        SILVotosCompletos con todos los votos.
    """
    votos = SILVotosCompletos(
        clave_asunto=clave_asunto,
        clave_tramite=clave_tramite,
    )

    # Parsear cada grupo
    votos_f = parse_votos_grupo(html_favor, "F")
    votos_c = parse_votos_grupo(html_contra, "C")
    votos_a = parse_votos_grupo(html_abstencion, "A")
    votos_n = parse_votos_grupo(html_ausentes, "N")

    votos.votos.extend(votos_f)
    votos.votos.extend(votos_c)
    votos.votos.extend(votos_a)
    votos.votos.extend(votos_n)

    # Calcular totales
    votos.totales = {
        "a_favor": len(votos_f),
        "en_contra": len(votos_c),
        "abstencion": len(votos_a),
        "ausente": len(votos_n),
    }

    return votos


def extract_count_from_votos_page(html: str) -> int:
    """Extrae el número de legisladores de una página de grupo.

    Args:
        html: HTML de la página de grupo.

    Returns:
        Número de legisladores.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text()

    # Buscar patrón como "X legislators" o "X registros"
    match = re.search(r"(\d+)\s+(?:legisladores?|senadores?|registros?)", text, re.I)
    if match:
        return int(match.group(1))

    # Contar filas de la tabla
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        return max(0, len(rows) - 1)  # Menos header

    return 0
