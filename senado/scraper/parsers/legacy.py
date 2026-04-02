"""Parser para formato Legacy (LX-LXV) del portal de votaciones del Senado.

El portal de votaciones del Senado para legislaturas LX-LXV tiene una estructura
HTML diferente a LXVI. Las URLs son:
    https://www.senado.gob.mx/informacion/votaciones/vota/{id}
    Rango: 1 a 4690

Estructura:
    - Metadata en divs con classes específicas (panel-heading, col-sm-12, etc.)
    - Tabla agregada por partido (primera tabla)
    - Tabla de votos nominales (segunda tabla, con SENADOR (A) en header)
"""

import re
from typing import Optional

from bs4 import BeautifulSoup

from ..models import SenVotacionDetail, SenVotoNominal


# =============================================================================
# Helpers
# =============================================================================


def _parse_legislature(legislature_text: str) -> str:
    """Extrae el identificador de legislature del texto HTML.

    'VOTACIONES DE LA LX LEGISLATURA' → 'LX'
    'VOTACIONES DE LA LXI LEGISLATURA' → 'LXI'

    Args:
        legislature_text: Texto que contiene el identificador de legislature.

    Returns:
        Identificador de legislature en formato romano (LX, LXI, etc.).
    """
    match = re.search(r"LA\s+([LXVI]+)\s+LEGISLATURA", legislature_text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def _parse_ejercicio(ejercicio_text: str) -> int:
    """Convierte el texto de año de ejercicio a número.

    'PRIMER AÑO DE EJERCICIO' → 1
    'SEGUNDO AÑO DE EJERCICIO' → 2
    'TERCER AÑO DE EJERCICIO' → 3

    Args:
        ejercicio_text: Texto del año de ejercicio.

    Returns:
        Año de ejercicio como entero (1, 2 o 3).
    """
    text = ejercicio_text.strip().upper()
    if "PRIMER" in text or "PRIMERO" in text:
        return 1
    if "SEGUNDO" in text:
        return 2
    if "TERCER" in text or "TERCERO" in text:
        return 3
    return 0


def _parse_fecha_legacy(fecha_text: str) -> str:
    """Convierte formato natural a dd/mm/yyyy.

    'Martes 05 de septiembre de 2006' → '05/09/2006'

    Compatible con _parse_fecha_iso en transformers.py.

    Args:
        fecha_text: Texto de fecha en formato natural en español.

    Returns:
        Fecha en formato dd/mm/yyyy.
    """
    meses = {
        "enero": "01",
        "febrero": "02",
        "marzo": "03",
        "abril": "04",
        "mayo": "05",
        "junio": "06",
        "julio": "07",
        "agosto": "08",
        "septiembre": "09",
        "octubre": "10",
        "noviembre": "11",
        "diciembre": "12",
    }

    text = fecha_text.strip()
    # Patrón: "Martes 05 de septiembre de 2006"
    match = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text, re.IGNORECASE)
    if match:
        dia = match.group(1).zfill(2)
        mes_nombre = match.group(2).lower()
        año = match.group(3)
        mes = meses.get(mes_nombre, "01")
        return f"{dia}/{mes}/{año}"

    return ""


def _normalize_voto(voto_text: str) -> str:
    """Normaliza el texto del voto para voto_to_option().

    Maneja HTML entities (ABSTENCI&Oacute;N → ABSTENCIÓN) y normaliza
    mayúsculas/minúsculas. Retorna el valor RAW (PRO/CONTRA/ABSTENCIÓN)
    sin transformar para que transformers.py:voto_to_option() lo procese.

    Args:
        voto_text: Texto del voto extraído del HTML.

    Returns:
        Voto normalizado (PRO, CONTRA o ABSTENCIÓN) - valor RAW.
    """
    text = voto_text.strip().upper()

    # Manejar HTML entities comunes
    text = text.replace("&OACUTE;", "O")
    text = text.replace("&AACUTE;", "A")
    text = text.replace("&EACUTE;", "E")
    text = text.replace("&IACUTE;", "I")
    text = text.replace("&OACUTE;", "O")
    text = text.replace("&UACUTE;", "U")

    if "PRO" in text and "ABSTEN" not in text:
        return "PRO"
    if "CONTRA" in text:
        return "CONTRA"
    if "ABSTEN" in text:
        return "ABSTENCIÓN"

    return voto_text.strip()


# =============================================================================
# Parser principal
# =============================================================================


def parse_legacy_votacion(
    html: str, senado_id: int
) -> tuple[SenVotacionDetail, list[SenVotoNominal]]:
    """
    Parsea el HTML de una votación del formato legacy (LX-LXV).

    Extrae:
    - Legislature y año de ejercicio de los elementos de metadata
    - Fecha y descripción del cuerpo del documento
    - Conteos agregados por partido de la primera tabla
    - Votos nominales de la segunda tabla

    Args:
        html: HTML de la página de votación.
        senado_id: ID de la votación en el portal.

    Returns:
        Tuple de (SenVotacionDetail, list[SenVotoNominal]).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Valores por defecto
    legislature = ""
    año_ejercicio = 0
    fecha = ""
    descripcion = ""
    pro_count = 0
    contra_count = 0
    abstention_count = 0

    # -------------------------------------------------------------------------
    # 1. Extraer legislature del panel-heading
    # -------------------------------------------------------------------------
    panel_heading = soup.find("div", class_="panel-heading")
    if panel_heading:
        heading_text = panel_heading.get_text(strip=True)
        legislature = _parse_legislature(heading_text)

    # -------------------------------------------------------------------------
    # 2. Extraer año de ejercicio del h3
    # -------------------------------------------------------------------------
    h3_tags = soup.find_all("h3")
    for h3 in h3_tags:
        h3_text = h3.get_text(strip=True)
        if "AÑO DE EJERCICIO" in h3_text.upper():
            año_ejercicio = _parse_ejercicio(h3_text)
            break

    # -------------------------------------------------------------------------
    # 3. Extraer fecha del div col-sm-12 text-center
    # -------------------------------------------------------------------------
    fecha_divs = soup.find_all(
        "div", class_=lambda c: c and "col-sm-12" in c.split() if c else False
    )
    for div in fecha_divs:
        div_text = div.get_text(strip=True)
        if re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", div_text, re.IGNORECASE):
            fecha = _parse_fecha_legacy(div_text)
            break

    # -------------------------------------------------------------------------
    # 4. Extraer descripción del div col-sm-12 text-justify
    # -------------------------------------------------------------------------
    for div in fecha_divs:
        div_classes = div.get("class", [])
        if "text-justify" in div_classes:
            descripcion = div.get_text(strip=True)
            break

    # -------------------------------------------------------------------------
    # 5. Extraer conteos de la primera tabla (agregada por partido)
    # -------------------------------------------------------------------------
    tables = soup.find_all("table")

    # Primera tabla: buscar la que tiene "Presentes:" en el header
    if len(tables) >= 1:
        primera_tabla = tables[0]
        # Buscar header con "Presentes"
        header_text = primera_tabla.get_text(strip=True)
        if "Presentes" in header_text or "Presentes" in header_text:
            # Buscar filas de partidos (PRI, PAN, PRD, etc.)
            tbody = primera_tabla.find("tbody") or primera_tabla
            filas = tbody.find_all("tr")

            for fila in filas:
                cells = fila.find_all(["td", "th"])
                if len(cells) < 6:
                    continue

                cell_texts = [c.get_text(strip=True) for c in cells]

                # Verificar si es fila de partido (primera columna es partido)
                partido = cell_texts[0].upper()
                if partido in ("PRI", "PAN", "PRD", "PVEM", "PT", "SIN GRUPO"):
                    # Columnas: Partido | A Favor | En Contra | Abstención | Comisión Oficial | Total
                    try:
                        a_favor = int(cell_texts[1]) if cell_texts[1].isdigit() else 0
                        en_contra = int(cell_texts[2]) if cell_texts[2].isdigit() else 0
                        abst = int(cell_texts[3]) if cell_texts[3].isdigit() else 0

                        pro_count += a_favor
                        contra_count += en_contra
                        abstention_count += abst
                    except (ValueError, IndexError):
                        pass

    # -------------------------------------------------------------------------
    # 6. Extraer votos nominales de la segunda tabla
    # -------------------------------------------------------------------------
    votos: list[SenVotoNominal] = []

    if len(tables) >= 2:
        segunda_tabla = tables[1]
        # Verificar que sea la tabla nominal (tiene SENADOR en header)
        header_cells = segunda_tabla.find_all(["th"])
        is_nominal = False
        for th in header_cells:
            th_text = th.get_text(strip=True).upper()
            if "SENADOR" in th_text or "VOTO" in th_text:
                is_nominal = True
                break

        if is_nominal:
            tbody = segunda_tabla.find("tbody") or segunda_tabla
            filas = tbody.find_all("tr")

            for fila in filas:
                cells = fila.find_all("td")
                if len(cells) < 3:
                    continue

                # td[0]: número
                numero_text = cells[0].get_text(strip=True)
                try:
                    numero = int(numero_text)
                except ValueError:
                    num_match = re.search(r"\d+", numero_text)
                    numero = int(num_match.group()) if num_match else 0

                # td[1]: nombre (del link)
                nombre = ""
                link = cells[1].find("a")
                if link:
                    nombre = link.get_text(strip=True)
                else:
                    nombre = cells[1].get_text(strip=True)

                # Limpiar prefijo "Sen. "
                nombre = re.sub(r"^Sen\.\s*", "", nombre, flags=re.IGNORECASE).strip()

                # td[2]: voto
                voto_text = cells[2].get_text(strip=True)
                voto = _normalize_voto(voto_text)

                # Grupo parlamentario: intentar extraer del link o de la celda
                grupo_parlamentario = ""
                if link:
                    parent = link.parent
                    if parent:
                        # Buscar el partido en la misma fila
                        grupo_text = cells[1].get_text(strip=True)
                        # El partido puede estar después del nombre
                        pass

                # En el formato legacy, no hay columna de partido visible
                # Se deja vacío y se resuelve en transformers.py
                grupo_parlamentario = ""

                votos.append(
                    SenVotoNominal(
                        numero=numero,
                        nombre=nombre,
                        grupo_parlamentario=grupo_parlamentario,
                        voto=voto,
                    )
                )

    # -------------------------------------------------------------------------
    # 7. Construir resultado
    # -------------------------------------------------------------------------
    detail = SenVotacionDetail(
        fecha=fecha,
        año_ejercicio=año_ejercicio,
        periodo=legislature,
        descripcion=descripcion,
        pro_count=pro_count,
        contra_count=contra_count,
        abstention_count=abstention_count,
    )

    return detail, votos
