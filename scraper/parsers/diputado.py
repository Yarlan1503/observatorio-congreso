"""
parsers/diputado.py — Parser de la ficha curricular de diputados del SITL.

Parsea la página curricula.php?dipt={id} que contiene la ficha personal
de un diputado.

Estructura HTML real (verificada contra curricula_1.html):
- Nombre: <h1 class="header-name">Dip. NOMBRE</h1>
- Principio de elección: <h4>Principio de elección: <b> Mayoría Relativa</b></h4>
- Entidad: <p>Entidad: <b> Aguascalientes</b></p>
- Distrito: <p>Distrito: <b> 1 </b></p>
- Curul: <p>Curul: <b> C-063 </b></p>
- Fecha nacimiento: <i class="fa-regular fa-calendar-days"></i>&nbsp; <b>28-marzo - 1976</b>
- Email: <i class="fa-solid fa-envelope"></i>&nbsp; <b>email@diputados.gob.mx</b>
- Suplente: <i class="fa-solid fa-user-group"></i>&nbsp; Suplente: <b>NOMBRE</b>
- Partido: <img src="images/pri.webp"> (imagen, mapear por filename)
- ID del diputado: del parámetro dipt en los links del navbar
- Extensión telefónica: <i class="fa-solid fa-phone-volume"></i>&nbsp; <b>59440</b>
"""

import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from scraper.config import PARTY_IMAGE_MAP
from scraper.models import FichaDiputado


def parse_diputado(html: str, sitl_id: Optional[int] = None) -> Optional[FichaDiputado]:
    """Parsea el HTML de la ficha curricular de un diputado.

    Args:
        html: HTML de la página curricula.php del SITL.
        sitl_id: ID SITL del diputado (si no se pasa, se intenta extraer del HTML).

    Returns:
        FichaDiputado con los datos del diputado, o None si no se encuentra nombre.
    """
    soup = BeautifulSoup(html, "lxml")

    # Extraer sitl_id del HTML si no se proporcionó
    if sitl_id is None:
        sitl_id = _extraer_sitl_id(soup)

    # Nombre: <h1 class="header-name">
    nombre = _extraer_nombre(soup)
    if not nombre:
        return None

    # Partido: por imagen (images/pri.webp, images/morena.webp, etc.)
    partido = _extraer_partido(soup)

    # Buscar el contenedor con los datos del diputado
    # Puede estar en <div class="header-contact"> o en sección con clase "resume"
    contacto = soup.find("div", class_="header-contact")
    if not contacto:
        # Fallback: buscar la sección resume
        contacto = soup.find("section", class_="resume")
    if not contacto:
        contacto = soup

    # Principio de elección: <h4> tag
    principio = _extraer_principio(soup)

    # Entidad, Distrito, Curul: <p> tags con patrón "Clave: <b>valor</b>"
    entidad = _extraer_campo(contacto, "Entidad")
    distrito = _extraer_campo(contacto, "Distrito")
    curul = _extraer_campo(contacto, "Curul")

    # Fecha de nacimiento: icono calendar-days → <b> siguiente
    fecha_nacimiento = _extraer_por_icono(soup, "fa-calendar-days")

    # Email: icono envelope → <b> siguiente
    email = _extraer_por_icono(soup, "fa-envelope")

    # Suplente: icono user-group → texto "Suplente: <b>NOMBRE</b>"
    suplente = _extraer_suplente(soup)

    return FichaDiputado(
        nombre=nombre,
        principio_eleccion=principio,
        entidad=entidad,
        distrito=distrito,
        curul=curul,
        fecha_nacimiento=fecha_nacimiento,
        email=email,
        suplente=suplente,
        partido=partido,
        sitl_id=sitl_id,
    )


def _extraer_nombre(soup: BeautifulSoup) -> Optional[str]:
    """Extrae el nombre del diputado del <h1 class="header-name">."""
    h1 = soup.find("h1", class_="header-name")
    if h1:
        nombre = h1.get_text(strip=True)
        # Remover prefijo "Dip. " si existe
        if nombre.upper().startswith("DIP."):
            nombre = nombre[4:].strip()
        return nombre

    # Fallback para LX-LXII: <span class="Estilo67">Dip. NOMBRE</span>
    for span in soup.find_all("span", class_="Estilo67"):
        texto = span.get_text(strip=True)
        if texto.upper().startswith("DIP."):
            nombre = texto[4:].strip()
            if nombre:
                return nombre

    # Fallback para LXIII-LXV: <td> con <strong> que empieza con "Dip."
    for td in soup.find_all("td"):
        strong = td.find("strong")
        if strong:
            texto = strong.get_text(strip=True)
            if texto.upper().startswith("DIP."):
                nombre = texto[4:].strip()
                if nombre:
                    return nombre

    return None


def _extraer_partido(soup: BeautifulSoup) -> Optional[str]:
    """Extrae el partido del diputado mapeando la imagen del partido."""
    # Buscar imagen en sección de partidos (class="header-gp" o contenedor)
    for img in soup.find_all("img", class_="header-gp"):
        src = img.get("src", "")
        filename = src.split("/")[-1].lower()
        if filename in PARTY_IMAGE_MAP:
            return PARTY_IMAGE_MAP[filename]

    # Fallback: buscar cualquier imagen con src que contenga partido
    for img in soup.find_all("img"):
        src = img.get("src", "")
        filename = src.split("/")[-1].lower()
        if filename in PARTY_IMAGE_MAP:
            return PARTY_IMAGE_MAP[filename]

    return None


def _extraer_principio(soup: BeautifulSoup) -> str:
    """Extrae el principio de elección del <h4>."""
    # LXIV-LXVI: <h4 class="header-job">Principio de elección: <b>Mayoría Relativa</b></h4>
    h4 = soup.find("h4", class_="header-job")
    if h4:
        texto = h4.get_text(strip=True)
        # Extraer valor después de "Principio de elección:"
        if ":" in texto:
            valor = texto.split(":", 1)[1].strip()
            return valor

    # Fallback para LX-LXII: <span class="Estilo67"> con label tipo/principio de elección
    for span in soup.find_all("span", class_="Estilo67"):
        texto = span.get_text(strip=True)
        if "tipo de elecci" in texto.lower() or "principio de elecci" in texto.lower():
            # El valor está en el siguiente <td> hermano del <tr> padre
            tr = span.find_parent("tr")
            if tr:
                tds = tr.find_all("td")
                # El último <td> contiene el valor
                if len(tds) >= 2:
                    # Tomar el texto del último td (el que tiene el valor, no el label)
                    valor = tds[-1].get_text(strip=True)
                    if valor:
                        return valor

    # Fallback para LXIII-LXV: <td> con label "Tipo de elección:" / "Principio de elección:"
    for td in soup.find_all("td"):
        texto = td.get_text(strip=True).lower()
        if "tipo de elecci" in texto or "principio de elecci" in texto:
            hermano = td.find_next_sibling("td")
            if hermano:
                strong = hermano.find("strong")
                valor = (
                    strong.get_text(strip=True)
                    if strong
                    else hermano.get_text(strip=True)
                )
                if valor:
                    return valor

    return ""


def _extraer_campo(contenedor: BeautifulSoup, campo: str) -> Optional[str]:
    """Extrae un campo con formato '<p>Campo: <b>valor</b></p>'."""
    for p in contenedor.find_all("p"):
        texto = p.get_text()
        if f"{campo}:" in texto or f"{campo} :" in texto:
            b = p.find("b")
            if b:
                return b.get_text(strip=True)
    return None


def _extraer_por_icono(soup: BeautifulSoup, icon_class: str) -> Optional[str]:
    """Extrae el texto del <b> siguiente a un icono Font Awesome."""
    icon = soup.find("i", class_=lambda c: c and icon_class in str(c))
    if icon:
        # El <b> puede ser hermano o estar en el mismo <p>
        parent = icon.parent
        if parent:
            b = parent.find("b")
            if b:
                return b.get_text(strip=True)
    return None


def _extraer_suplente(soup: BeautifulSoup) -> Optional[str]:
    """Extrae el nombre del suplente."""
    icon = soup.find("i", class_=lambda c: c and "fa-user-group" in str(c))
    if icon:
        parent = icon.parent
        if parent:
            b = parent.find("b")
            if b:
                return b.get_text(strip=True)
    return None


def _extraer_sitl_id(soup: BeautifulSoup) -> Optional[int]:
    """Extrae el sitl_id de los links del navbar (dipt=NNN)."""
    for link in soup.find_all("a", href=True):
        match = re.search(r"dipt=(\d+)", link["href"])
        if match:
            return int(match.group(1))
    return None
