"""Parser para el portal LXVI (v66) del Senado.

Portal: https://www.senado.gob.mx/66/votacion/{id}
Cubre legislaturas LX-LXVI (IDs 1-5070).

La página principal contiene metadata (legislatura, fecha, descripción, counts).
Los votos nominales se cargan via AJAX endpoint:
    POST /66/app/votaciones/functions/viewTableVot.php
    action=ajax&cell=1&order=DESC&votacion={id}&q=

Ventajas sobre el portal legacy:
- Columna de Grupo Parlamentario por senador (resuelve vote.group vacío)
- Incluye todos los partidos (MORENA, MC, etc.)
- Cobertura LX-LXVI
"""

import re
from typing import Optional

from bs4 import BeautifulSoup

from ..models import SenCountPorPartido, SenVotacionDetail, SenVotoNominal


# =============================================================================
# Helpers
# =============================================================================


_MESES_ES = {
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


def _parse_fecha_natural_to_iso(fecha_text: str) -> str:
    """Convierte fecha en formato natural español a ISO yyyy-mm-dd.

    'Martes 05 de septiembre de 2006' → '2006-09-05'

    Args:
        fecha_text: Fecha en formato natural.

    Returns:
        Fecha ISO o cadena vacía si no se puede parsear.
    """
    text = fecha_text.strip()
    match = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text, re.IGNORECASE)
    if match:
        dia = match.group(1).zfill(2)
        mes_nombre = match.group(2).lower()
        año = match.group(3)
        mes = _MESES_ES.get(mes_nombre, "01")
        return f"{año}-{mes}-{dia}"
    return ""


def _parse_legislature(text: str) -> str:
    """Extrae identificador de legislatura: LX, LXI, ..., LXVI.

    Busca el patrón 'LXVI LEGISLATURA' en el texto.

    Args:
        text: Texto que contiene la legislatura.

    Returns:
        String de legislatura (LX, LXI, etc.) o vacío.
    """
    match = re.search(r"\b([LXVI]+)\s+LEGISLATURA\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def _parse_año_ejercicio(text: str) -> int:
    """Extrae año de ejercicio del texto.

    'PRIMER AÑO DE EJERCICIO' → 1
    'SEGUNDO AÑO DE EJERCICIO' → 2
    'TERCER AÑO DE EJERCICIO' → 3

    Args:
        text: Texto del año de ejercicio.

    Returns:
        Año de ejercicio como entero (1, 2, 3) o 0.
    """
    text_upper = text.strip().upper()
    if "PRIMER" in text_upper or "PRIMERO" in text_upper:
        return 1
    if "SEGUNDO" in text_upper:
        return 2
    if "TERCER" in text_upper or "TERCERO" in text_upper:
        return 3
    return 0


def _parse_periodo(text: str) -> str:
    """Extrae el texto del período parlamentario.

    'PRIMER PERIODO ORDINARIO' → 'PRIMER PERIODO ORDINARIO'
    'SEGUNDO PERIODO EXTRAORDINARIO' → 'SEGUNDO PERIODO EXTRAORDINARIO'

    Args:
        text: Texto que contiene el período.

    Returns:
        Texto del período o vacío.
    """
    match = re.search(
        r"((?:PRIMER|SEGUNDO|TERCER|CUARTO|QUINTO)\s+PERIODO\s+"
        r"(?:ORDINARIO|EXTRAORDINARIO|ORDINARIO\s+DE\s+SESIONES|PERMANENTE))",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    # Fallback: buscar cualquier "PERIODO ..." después de la línea de año
    match = re.search(r"(\w+\s+PERIODO\s+\w+(?:\s+\w+)?)", text, re.IGNORECASE)
    if match:
        periodo = match.group(1).upper()
        if "AÑO" not in periodo:
            return periodo
    return ""


def _normalize_voto(voto_text: str) -> str:
    """Normaliza texto del voto al formato estándar.

    PRO → PRO, CONTRA → CONTRA, ABSTENCIÓN → ABSTENCIÓN, AUSENTE → AUSENTE

    Args:
        voto_text: Texto del voto extraído del HTML.

    Returns:
        Voto normalizado.
    """
    text = voto_text.strip().upper()

    # Manejar HTML entities comunes
    text = text.replace("&OACUTE;", "O")
    text = text.replace("&AACUTE;", "A")
    text = text.replace("&EACUTE;", "E")
    text = text.replace("&IACUTE;", "I")
    text = text.replace("&UACUTE;", "U")

    # Normalizar acentos para comparación
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))

    if "PRO" in sin_acentos and "ABSTEN" not in sin_acentos:
        return "PRO"
    if "CONTRA" in sin_acentos:
        return "CONTRA"
    if "ABSTENCION" in sin_acentos or "ABSTEN" in sin_acentos:
        return "ABSTENCIÓN"
    if "AUSENTE" in sin_acentos:
        return "AUSENTE"

    return voto_text.strip()


def _clean_senador_name(nombre: str) -> str:
    """Limpia el nombre de un senador.

    'Sen. Adame Castillo, Marco Antonio' → 'Adame Castillo, Marco Antonio'
    'Sen. Adame Castillo , Marco Antonio' → 'Adame Castillo, Marco Antonio'
    'Sen. Aldana Prieto , Luis Ricardo' → 'Aldana Prieto, Luis Ricardo'

    Args:
        nombre: Nombre raw del HTML.

    Returns:
        Nombre limpio sin prefijo 'Sen.' y espacios extra.
    """
    # Quitar prefijo "Sen. " o "Sen "
    nombre = re.sub(r"^Sen\.\s*", "", nombre, flags=re.IGNORECASE).strip()
    # Normalizar espacios alrededor de comas: "Apellido , Nombre" → "Apellido, Nombre"
    nombre = re.sub(r"\s*,\s*", ", ", nombre)
    # Normalizar espacios múltiples
    nombre = re.sub(r"\s{2,}", " ", nombre)
    return nombre.strip()


# =============================================================================
# Parser de página principal (metadata)
# =============================================================================


def parse_votacion_page(html: str, senado_id: int) -> SenVotacionDetail:
    """Parsea la página principal de una votación del portal LXVI.

    Extrae metadata: legislatura, año de ejercicio, período, fecha,
    descripción y conteos globales (pro/contra/abstención).

    No extrae votos nominales (esos vienen del endpoint AJAX).

    Args:
        html: HTML completo de https://www.senado.gob.mx/66/votacion/{id}
        senado_id: ID de la votación.

    Returns:
        SenVotacionDetail con metadata. Los votos se agregan después
        via parse_votacion_ajax().
    """
    soup = BeautifulSoup(html, "html.parser")

    # Valores por defecto
    legislature = ""
    año_ejercicio = 0
    periodo = ""
    fecha_raw = ""
    descripcion = ""
    pro_count = 0
    contra_count = 0
    abstention_count = 0

    # -------------------------------------------------------------------------
    # 1. Legislatura, año de ejercicio y período del <h3><strong>
    # -------------------------------------------------------------------------
    # Estructura: <h3><strong>LX LEGISLATURA<br>PRIMER AÑO DE EJERCICIO<br>
    #             PRIMER PERIODO ORDINARIO</strong></h3>
    # NOTA: En ID 5065, la legislatura NO está en el h3 (solo año y período).
    #       La legislatura se infiere del h3 o de otros elementos.
    h3_tags = soup.find_all("h3")
    for h3 in h3_tags:
        h3_text = h3.get_text(separator="\n", strip=True)

        # Buscar legislatura
        if not legislature:
            legislature = _parse_legislature(h3_text)

        # Buscar año de ejercicio
        if "AÑO DE EJERCICIO" in h3_text.upper():
            año_ejercicio = _parse_año_ejercicio(h3_text)

        # Buscar período
        if not periodo:
            periodo = _parse_periodo(h3_text)

    # -------------------------------------------------------------------------
    # 2. Si no se encontró legislatura en h3, buscar en el body completo
    # -------------------------------------------------------------------------
    if not legislature:
        body_text = soup.get_text()
        legislature = _parse_legislature(body_text)

    # Si aún no hay legislatura, default a LXVI — el portal /66/ es el
    # portal de la LXVI Legislatura. Las legislaturas anteriores (LX-LXV)
    # incluyen explícitamente "LX LEGISLATURA" en el h3, pero la LXVI
    # (legislatura actual) no lo hace porque es implícito.
    if not legislature:
        legislature = "LXVI"

    # -------------------------------------------------------------------------
    # 3. Fecha: <div class="col-sm-12 text-center"><strong>Martes 05 ...</strong></div>
    # -------------------------------------------------------------------------
    fecha_divs = soup.find_all(
        "div",
        class_=lambda c: c and "col-sm-12" in c.split() if c else False,
    )
    for div in fecha_divs:
        div_text = div.get_text(strip=True)
        if re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", div_text, re.IGNORECASE):
            fecha_raw = div_text
            break

    # -------------------------------------------------------------------------
    # 4. Descripción: <div class="col-sm-12 text-justify">TEXTO</div>
    # -------------------------------------------------------------------------
    for div in fecha_divs:
        div_classes = div.get("class", [])
        if "text-justify" in div_classes:
            descripcion = div.get_text(strip=True)
            break

    # -------------------------------------------------------------------------
    # 5. Conteos: <tfoot> con EN PRO, EN CONTRA, ABSTENCIÓN
    # -------------------------------------------------------------------------
    tfoot = soup.find("tfoot")
    if tfoot:
        tds = tfoot.find_all("td")
        for td in tds:
            td_text = td.get_text(strip=True).upper()
            # Extraer número del span dentro del td
            span = td.find("span")
            if span:
                try:
                    valor = int(span.get_text(strip=True))
                except ValueError:
                    continue
            else:
                # Intentar extraer número directamente
                num_match = re.search(r"\d+", td_text)
                valor = int(num_match.group()) if num_match else 0

            if "PRO" in td_text and "CONTRA" not in td_text:
                pro_count = valor
            elif "CONTRA" in td_text:
                contra_count = valor
            elif "ABSTEN" in td_text:
                abstention_count = valor

    # -------------------------------------------------------------------------
    # 6. Construir resultado
    # -------------------------------------------------------------------------
    # fecha: usamos formato dd/mm/yyyy para compatibilidad con
    # _parse_fecha_iso() en cli_curl_cffi.py
    fecha_ddmmyyyy = ""
    if fecha_raw:
        match = re.search(
            r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", fecha_raw, re.IGNORECASE
        )
        if match:
            dia = match.group(1).zfill(2)
            mes_nombre = match.group(2).lower()
            año = match.group(3)
            mes = _MESES_ES.get(mes_nombre, "01")
            fecha_ddmmyyyy = f"{dia}/{mes}/{año}"

    return SenVotacionDetail(
        fecha=fecha_ddmmyyyy,
        año_ejercicio=año_ejercicio,
        periodo=periodo if not legislature else legislature,
        descripcion=descripcion,
        pro_count=pro_count,
        contra_count=contra_count,
        abstention_count=abstention_count,
        counts_por_partido=[],  # Se calculan desde la tabla AJAX
    )


# =============================================================================
# Parser de tabla AJAX (votos nominales)
# =============================================================================


def parse_votacion_ajax(html: str, senado_id: int) -> list[SenVotoNominal]:
    """Parsea la respuesta HTML del endpoint AJAX de votos nominales.

    El endpoint retorna fragmentos HTML de tabla con estructura:
        <tr>
            <td>1</td>
            <td><a>Sen. Adame Castillo, Marco Antonio</a></td>
            <td><a>PAN</a></td>
            <td>PRO</td>
        </tr>

    Args:
        html: HTML fragment de la respuesta AJAX.
        senado_id: ID de la votación (para logging).

    Returns:
        Lista de SenVotoNominal con nombre, grupo parlamentario y voto.
    """
    soup = BeautifulSoup(html, "html.parser")
    votos: list[SenVotoNominal] = []

    # Buscar tbody con las filas de votos
    tbody = soup.find("tbody")
    if not tbody:
        # Fallback: buscar todas las filas directamente
        filas = soup.find_all("tr")
    else:
        filas = tbody.find_all("tr")

    for fila in filas:
        cells = fila.find_all("td")
        if len(cells) < 4:
            continue

        # td[0]: número de lista
        numero_text = cells[0].get_text(strip=True)
        try:
            numero = int(numero_text)
        except ValueError:
            num_match = re.search(r"\d+", numero_text)
            numero = int(num_match.group()) if num_match else 0

        # td[1]: nombre (del link si existe)
        nombre_raw = ""
        link = cells[1].find("a")
        if link:
            nombre_raw = link.get_text(strip=True)
        else:
            nombre_raw = cells[1].get_text(strip=True)

        nombre = _clean_senador_name(nombre_raw)

        # td[2]: grupo parlamentario (del link si existe)
        grupo_raw = ""
        link_grupo = cells[2].find("a")
        if link_grupo:
            grupo_raw = link_grupo.get_text(strip=True)
        else:
            grupo_raw = cells[2].get_text(strip=True)

        grupo_parlamentario = grupo_raw.strip().upper()

        # Normalizar grupos especiales
        # "SG" = Senadores sin Grupo / Independientes
        # "SG-PVEM" = coalición, etc.
        # Mantenemos el valor tal cual — el loader lo mapeará a organización

        # td[3]: voto
        voto_raw = cells[3].get_text(strip=True)
        voto = _normalize_voto(voto_raw)

        votos.append(
            SenVotoNominal(
                numero=numero,
                nombre=nombre,
                grupo_parlamentario=grupo_parlamentario,
                voto=voto,
            )
        )

    return votos


# =============================================================================
# Combinación: parse completo
# =============================================================================


def parse_lxvi_votacion(
    page_html: str, ajax_html: str, senado_id: int
) -> tuple[SenVotacionDetail, list[SenVotoNominal]]:
    """Parsea una votación completa del portal LXVI.

    Combina metadata de la página principal con votos del endpoint AJAX.

    Args:
        page_html: HTML de la página principal.
        ajax_html: HTML de la respuesta AJAX (tabla de votos).
        senado_id: ID de la votación.

    Returns:
        Tuple de (SenVotacionDetail, list[SenVotoNominal]).
    """
    detail = parse_votacion_page(page_html, senado_id)
    votos = parse_votacion_ajax(ajax_html, senado_id)

    # Calcular counts_por_partido desde los votos nominales
    party_counts: dict[str, dict[str, int]] = {}
    for voto in votos:
        partido = voto.grupo_parlamentario
        if not partido:
            continue
        if partido not in party_counts:
            party_counts[partido] = {"a_favor": 0, "en_contra": 0, "abstencion": 0}
        option = _voto_to_count_key(voto.voto)
        if option:
            party_counts[partido][option] += 1

    detail.counts_por_partido = [
        SenCountPorPartido(
            partido=p,
            a_favor=counts["a_favor"],
            en_contra=counts["en_contra"],
            abstencion=counts["abstencion"],
        )
        for p, counts in party_counts.items()
    ]

    return detail, votos


def _voto_to_count_key(voto: str) -> Optional[str]:
    """Mapea voto normalizado a key de count.

    PRO → a_favor, CONTRA → en_contra, ABSTENCIÓN → abstencion,
    AUSENTE → None (no cuenta en desglose por partido).
    """
    v = voto.strip().upper()
    if v == "PRO":
        return "a_favor"
    if v == "CONTRA":
        return "en_contra"
    if "ABSTEN" in v:
        return "abstencion"
    # AUSENTE y otros no se cuentan en desglose por partido
    return None
