"""
detalle.py — Parser para el detalle de una votación del SIL.

Extrae metadata completa: asunto, trámite, quorum,
totales de votación, y conteos por grupo.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from scraper_sil.models import SILVotacionDetail

logger = logging.getLogger(__name__)


def parse_detalle_votacion(
    html: str,
    clave_asunto: Optional[str] = None,
    clave_tramite: Optional[str] = None,
) -> Optional[SILVotacionDetail]:
    """Extrae metadata de una página de detalle de votación.

    Args:
        html: HTML de la página DetalleVotacion.php.
        clave_asunto: Clave del asunto (para debugging).
        clave_tramite: Clave del trámite (para debugging).

    Returns:
        SILVotacionDetail con todos los datos, o None si falla.
    """
    soup = BeautifulSoup(html, "lxml")

    # Extraer datos de la página
    detalle = _extract_metadata(soup, clave_asunto, clave_tramite)

    if detalle:
        # Extraer conteos
        _extract_conteos(soup, detalle)

        # Extraer quorum si está disponible
        _extract_quorum(soup, detalle)

    return detalle


def _extract_metadata(
    soup: BeautifulSoup,
    clave_asunto: Optional[str],
    clave_tramite: Optional[str],
) -> Optional[SILVotacionDetail]:
    """Extrae metadata básica del detalle."""
    try:
        text = soup.get_text()

        # Intentar extraer legislature de la página
        legislature = ""
        match = re.search(r"Legislatura\s*[:\-]?\s*(L[VIXL]+)", text, re.I)
        if match:
            legislature = match.group(1).upper()

        # Extraer fecha
        fecha = ""
        match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
        if match:
            fecha = match.group(1)

        # Extraer título/asunto (buscar en headers o títulos)
        titulo = ""
        h1 = soup.find("h1") or soup.find("h2") or soup.find("h3")
        if h1:
            titulo = h1.get_text(strip=True)

        # Si no hay título en h1, buscar en la página
        if not titulo:
            title = soup.find("title")
            if title:
                titulo = title.get_text(strip=True)

        # Extraer tipo de asunto
        tipo_asunto = ""
        for tipo_key, tipo_val in [
            ("reforma constitucional", "Reforma Constitucional"),
            ("ley", "Ley o Decreto"),
            ("decreto", "Ley o Decreto"),
            ("punto de acuerdo", "Punto de Acuerdo"),
            ("nombramiento", "Nombramiento"),
            ("convocatoria", "Convocatoria"),
            ("dictamen", "Dictamen"),
            ("iniciativa", "Iniciativa"),
        ]:
            if tipo_key in text.lower():
                tipo_asunto = tipo_val
                break

        # Extraer resultado
        resultado = ""
        for res_key, res_val in [
            ("aprobado", "Aprobado"),
            ("rechazado", "Rechazado"),
            ("desechado", "Desechado"),
            ("empate", "Empate"),
        ]:
            if res_key in text.lower():
                resultado = res_val
                break

        # Extraer tipo de votacion
        tipo_votacion = ""
        if "nominal" in text.lower():
            tipo_votacion = "Nominal"
        elif "económica" in text.lower() or "economica" in text.lower():
            tipo_votacion = "Económica"
        elif (
            "secreta" in text.lower()
            or "cédula" in text.lower()
            or "cedula" in text.lower()
        ):
            tipo_votacion = "Secreta"

        # Extraer clave de asunto de la URL o página si no se proporcionó
        if not clave_asunto:
            # Buscar en la URL de la página
            pass

        return SILVotacionDetail(
            clave_asunto=clave_asunto or "",
            clave_tramite=clave_tramite or "",
            titulo=titulo[:500] if titulo else "",
            legislature=legislature,
            fecha=fecha,
            tipo_asunto=tipo_asunto,
            resultado=resultado,
            tipo_votacion=tipo_votacion,
            quorum="",
        )

    except Exception as e:
        logger.error(f"Error extrayendo metadata: {e}")
        return None


def _extract_conteos(soup: BeautifulSoup, detalle: SILVotacionDetail) -> None:
    """Extrae conteos de votos de la página.

    Args:
        soup: BeautifulSoup de la página.
        detalle: Objeto SILVotacionDetail a completar.
    """
    text = soup.get_text()

    # Patrones para totales
    # "A favor: 67" o "Favor: 67" o "67 votos a favor"
    patterns = {
        "a_favor": [
            r"(?i)favor\s*[:\-]?\s*(\d+)",
            r"(\d+)\s+(?:votos?\s+)?a\s+favor",
            r"a\s+favor[:\s]*(\d+)",
        ],
        "en_contra": [
            r"(?i)contra\s*[:\-]?\s*(\d+)",
            r"(\d+)\s+(?:votos?\s+)?en\s+contra",
            r"en\s+contra[:\s]*(\d+)",
        ],
        "abstencion": [
            r"(?i)abstención\s*[:\-]?\s*(\d+)",
            r"abstencion\s*[:\-]?\s*(\d+)",
            r"(\d+)\s+(?:votos?\s+)?de\s+abstención",
        ],
        "ausente": [
            r"(?i)ausente\s*[:\-]?\s*(\d+)",
            r"(\d+)\s+(?:votos?\s+)?ausentes?",
        ],
    }

    for key, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                setattr(detalle, key, value)
                break

    # total_presentes se calcula automaticamente via property


def _extract_quorum(soup: BeautifulSoup, detalle: SILVotacionDetail) -> None:
    """Extrae información de quorum de la página.

    Args:
        soup: BeautifulSoup de la página.
        detalle: Objeto SILVotacionDetail a completar.
    """
    text = soup.get_text()

    # Buscar información de quorum
    match = re.search(r"(?i)quorum\s*[:\-]?\s*(\d+)\s*(?:de\s+)?(\d+)", text)
    if match:
        presente = int(match.group(1))
        total = int(match.group(2))
        detalle.quorum = f"{presente}/{total}"
    else:
        # Buscar patrón simple de quorum
        match = re.search(r"(?i)quorum\s*[:\-]?\s*([\d/]+)", text)
        if match:
            detalle.quorum = match.group(1)


def extract_votos_por_grupo(html: str) -> dict[str, dict[str, int]]:
    """Extrae conteo de votos por grupo parlamentario.

    Args:
        html: HTML de la página de detalle.

    Returns:
        Dict con estructura:
        {
            'MORENA': {'a_favor': 45, 'en_contra': 0, 'abstencion': 2},
            'PAN': {'a_favor': 0, 'en_contra': 10, 'abstencion': 1},
            ...
        }
    """
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, dict[str, int]] = {}

    # Buscar tabla de conteo por grupo
    table = soup.find("table", {"class": re.compile(r"partido|grupo|resumen", re.I)})
    if not table:
        # Buscar cualquier tabla que parezca tener datos de partidos
        tables = soup.find_all("table")
        for t in tables:
            headers = t.find_all("th")
            for th in headers:
                if any(
                    k in th.get_text().lower() for k in ["partido", "grupo", "voto"]
                ):
                    table = t
                    break
            if table:
                break

    if not table:
        return result

    # Parsear la tabla
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # Primera celda es el nombre del grupo
        grupo = cells[0].get_text(strip=True)
        if not grupo or len(grupo) > 50:
            continue

        # Las siguientes celdas son los conteos
        # Típicamente: a_favor, en_contra, abstencion
        if grupo not in result:
            result[grupo] = {
                "a_favor": 0,
                "en_contra": 0,
                "abstencion": 0,
                "ausente": 0,
            }

        for i, cell in enumerate(cells[1:], start=0):
            value = cell.get_text(strip=True)
            try:
                count = int(value)
                if i == 0:
                    result[grupo]["a_favor"] = count
                elif i == 1:
                    result[grupo]["en_contra"] = count
                elif i == 2:
                    result[grupo]["abstencion"] = count
                elif i == 3:
                    result[grupo]["ausente"] = count
            except ValueError:
                pass

    return result
