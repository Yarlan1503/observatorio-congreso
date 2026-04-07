"""perfil_parser.py — Parser de perfiles de senadores del portal LXVI.

Portal: https://senado.gob.mx/66/senador/{id}

Extrae de cada perfil:
- Nombre completo (sin prefijo Senador/Senadora)
- Género (M/F) inferido del título
- curul_tipo (mayoria_relativa, plurinominal, suplente)
- Estado (entidad federativa)
- Partido (del icono del partido)
- Suplente (si aplica)
"""

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# =============================================================================
# Mapeo de principio de elección → valor BD
# =============================================================================

CURUL_TIPO_MAP: dict[str, str] = {
    "mayoría relativa": "mayoria_relativa",
    "primera minoría": "plurinominal",
    "representación proporcional": "plurinominal",
    "asignación proporcional": "plurinominal",
}


# =============================================================================
# Dataclass de perfil
# =============================================================================


@dataclass
class SenPerfil:
    """Perfil de un senador extraído del portal.

    Attributes:
        nombre: Nombre completo sin prefijo "Senador"/"Senadora".
        genero: "M" o "F". None si no se puede inferir.
        curul_tipo: Tipo de curul (mayoria_relativa, plurinominal, suplente).
        estado: Nombre de la entidad federativa.
        partido: Abreviatura del partido (MORENA, PAN, PRI, etc.).
        suplente: Nombre del suplente (si aplica).
        portal_id: ID numérico del perfil en el portal.
    """

    nombre: str = ""
    genero: str | None = None
    curul_tipo: str | None = None
    estado: str = ""
    partido: str = ""
    suplente: str = ""
    portal_id: int = 0


# =============================================================================
# Funciones de validación
# =============================================================================


def _looks_like_valid_profile(html: str) -> bool:
    """Valida que el HTML parece ser un perfil de senador válido.

    Criterios de validez:
    - Contiene al menos un marcador estructural del portal:
      "nSenador" (clase del h2 con nombre), "tipoEleccion" (clase del h3),
      o "logo-partido" (clase del img del partido).
    - Tiene un tamaño razonable (> 5KB). Los perfiles reales son 200KB+
      pero IDs de legislaturas anteriores pueden ser más pequeños.

    Args:
        html: Contenido HTML de la respuesta.

    Returns:
        True si parece un perfil válido.
    """
    if len(html) < 5000:
        # Demasiado pequeño para ser un perfil real
        return False

    # Buscar marcadores estructurales del portal de perfiles
    structural_markers = ("nSenador", "tipoEleccion", "logo-partido")
    html_lower = html.lower()
    return any(marker.lower() in html_lower for marker in structural_markers)


# =============================================================================
# Funciones de parseo
# =============================================================================


def parse_perfil_html(html: str, portal_id: int) -> SenPerfil:
    """Parsea el HTML de un perfil de senador.

    Args:
        html: Contenido HTML completo de la página del perfil.
        portal_id: ID numérico del perfil en el portal.

    Returns:
        SenPerfil con los datos extraídos, o un perfil vacío si falla el parseo.
    """
    perfil = SenPerfil(portal_id=portal_id)

    if not html or len(html.strip()) == 0:
        logger.warning(f"HTML vacío para perfil ID {portal_id}")
        return perfil

    # Validación: un perfil real debe tener el contenedor principal
    # o al menos el título de senador. Si no lo tiene, probablemente
    # es una página de error, redirect, o contenido inválido.
    if not _looks_like_valid_profile(html):
        logger.debug(f"HTML no parece un perfil válido para ID {portal_id}")
        return perfil

    soup = BeautifulSoup(html, "lxml")

    # --- Nombre y género (del h2.nSenador) ---
    perfil.nombre, perfil.genero = _extract_nombre_genero(soup)

    # --- curul_tipo (del h3.tipoEleccion) ---
    perfil.curul_tipo = _extract_curul_tipo(soup)

    # --- Estado ---
    perfil.estado = _extract_estado(soup)

    # --- Partido ---
    perfil.partido = _extract_partido(soup)

    # --- Suplente ---
    perfil.suplente = _extract_suplente(soup)

    return perfil


def _extract_nombre_genero(soup: BeautifulSoup) -> tuple[str, str | None]:
    """Extrae nombre y género del <h2 class="nSenador">.

    Patrones observados:
        "Senador Marco Antonio Adame Castillo"
        "Senadora Imelda Castro Castro"

    Returns:
        Tuple de (nombre_sin_prefijo, genero).
    """
    h2 = soup.find("h2", class_="nSenador")
    if not h2:
        logger.warning("No se encontró h2.nSenador")
        return "", None

    texto = h2.get_text(strip=True)

    # Intentar extraer "Senadora" o "Senador"
    genero = None
    nombre = texto

    # Patrón: "Senadora Nombre..." o "Senador Nombre..."
    match = re.match(r"^Senador[a]?\s+(.+)$", texto, re.IGNORECASE)
    if match:
        nombre = match.group(1).strip()
        if re.match(r"^Senadora\b", texto, re.IGNORECASE):
            genero = "F"
        else:
            genero = "M"
    else:
        logger.warning(f"No se pudo parsear nombre/género de: '{texto}'")

    return nombre, genero


def _extract_curul_tipo(soup: BeautifulSoup) -> str | None:
    """Extrae el tipo de curul del <h3 class="tipoEleccion">.

    Patrones observados:
        "Senador Electo por el Principio de Mayoría Relativa"
        "Senadora Electa por el Principio de Primera Minoría"
        "Senador Electo por el Principio de Representación Proporcional"

    Returns:
        Valor mapeado a la BD (mayoria_relativa, plurinominal, suplente).
        None si no se puede determinar.
    """
    h3 = soup.find("h3", class_="tipoEleccion")
    if not h3:
        logger.debug("No se encontró h3.tipoEleccion")
        return None

    texto = h3.get_text(strip=True)

    # Buscar el principio de elección en el texto
    for portal_key, bd_value in CURUL_TIPO_MAP.items():
        if portal_key in texto.lower():
            return bd_value

    # Caso especial: ¿es suplente?
    # Algunos perfiles de suplentes pueden no tener tipoEleccion
    if "suplente" in texto.lower():
        return "suplente"

    logger.warning(f"No se pudo mapear curul_tipo de: '{texto}'")
    return None


def _extract_estado(soup: BeautifulSoup) -> str:
    """Extrae el nombre de la entidad federativa.

    Busca en <h4 class="nEstadi"> o en el alt/title de la imagen del escudo.

    Returns:
        Nombre del estado (string vacío si no se encuentra).
    """
    # Primero: intentar con <h4 class="nEstadi">
    h4 = soup.find("h4", class_="nEstadi")
    if h4:
        return h4.get_text(strip=True)

    # Fallback: extraer del filename del escudo
    escudo = soup.find("img", src=re.compile(r"escudos/"))
    if escudo:
        src = escudo.get("src", "")
        # El filename es el estado en minúsculas: "chiapas.png"
        match = re.search(r"escudos/([^/]+)\.\w+", src)
        if match:
            # Capitalizar primera letra
            estado = match.group(1).replace("_", " ").title()
            return estado

    return ""


def _extract_partido(soup: BeautifulSoup) -> str:
    """Extrae la abreviatura del partido del icono del partido.

    Busca <img class="logo-partido"> y extrae del filename:
        "../images/iconos_partidos/MORENA_.png" → "MORENA"
        "../images/iconos_partidos/PAN_.png" → "PAN"

    Returns:
        Abreviatura del partido (string vacío si no se encuentra).
    """
    img = soup.find("img", class_="logo-partido")
    if not img:
        return ""

    src = img.get("src", "")
    # Extraer del filename: "iconos_partidos/PRI_.png"
    match = re.search(r"iconos_partidos/([^/]+)", src)
    if match:
        partido = match.group(1)
        # Limpiar: "PRI_.png" → "PRI", "MORENA_.png" → "MORENA"
        partido = partido.split(".")[0]  # quitar extensión
        partido = partido.rstrip("_")  # quitar trailing underscore
        return partido.upper()

    return ""


def _extract_suplente(soup: BeautifulSoup) -> str:
    """Extrae el nombre del suplente.

    Busca en <p class="suplente"> el texto después de "Suplente:".

    Returns:
        Nombre del suplente (string vacío si no aplica).
    """
    p = soup.find("p", class_="suplente")
    if not p:
        return ""

    texto = p.get_text(strip=True)
    match = re.search(r"Suplente[:\s]+(.+?)(?:\s*$)", texto, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""
