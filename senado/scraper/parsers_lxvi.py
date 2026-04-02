"""parsers.py — Parsers HTML del portal del Senado de México.

Extrae datos estructurados del HTML de senado.gob.mx (LXVI Legislatura).

Funciones principales:
    parse_votaciones_index()  → URLs de páginas por fecha
    parse_votaciones_fecha()  → IDs y títulos de votaciones de un día
    parse_votacion_detalle()  → Metadatos completos de una votación
    parse_ajax_table()        → Votos individuales de cada senador
"""

import re
import unicodedata
import logging
from typing import Optional

from bs4 import BeautifulSoup

from .models import (
    SenVotacionIndexRecord,
    SenVotacionRaw,
    SenVotacionDetail,
    SenVotoNominal,
)

logger = logging.getLogger(__name__)


# --- Mapa de meses en español para parseo de fechas ---
_MESES_ES: dict[str, str] = {
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


# ============================================================
# Helpers
# ============================================================


def _normalizar_nombre(nombre: str) -> str:
    """Normaliza un nombre de senador para comparación.

    Strip del prefijo "Sen. ", normaliza acentos, convierte a
    lowercase y colapsa espacios.

    Ej: "Sen. Álvarez Lima, José Antonio Cruz" → "alvarez lima, jose antonio cruz"

    Args:
        nombre: Nombre tal como aparece en el portal.

    Returns:
        Nombre normalizado para comparación.
    """
    # Strip prefijo "Sen. " o "Sen. "
    nombre = re.sub(r"^Sen\.?\s*", "", nombre, flags=re.IGNORECASE).strip()
    # Normalizar acentos/diacríticos
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase y colapsar espacios
    return re.sub(r"\s+", " ", sin_acentos.lower().strip())


def _parsear_fecha_senado(fecha_str: str) -> str:
    """Convierte fecha del portal a ISO 8601.

    Formato de entrada: "Miércoles 25 de marzo de 2026"
    Formato de salida:  "2026-03-25"

    Args:
        fecha_str: Fecha en formato del portal del Senado.

    Returns:
        Fecha en formato ISO 8601, o string vacío si no se puede parsear.
    """
    if not fecha_str or not fecha_str.strip():
        return ""

    # Normalizar espacios y entidades HTML residuales
    fecha_str = re.sub(r"\s+", " ", fecha_str.strip())

    # Patrón: "Día de la semana DD de Mes de AAAA"
    match = re.match(r".*?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", fecha_str)
    if match:
        dia = match.group(1).zfill(2)
        mes_nombre = match.group(2).lower().strip()
        anio = match.group(3)

        # Normalizar mes (sin acentos)
        mes_norm = _normalizar_nombre(mes_nombre)
        mes_num = _MESES_ES.get(mes_norm)
        if mes_num:
            return f"{anio}-{mes_num}-{dia}"

    logger.warning(f"No se pudo parsear fecha del Senado: '{fecha_str}'")
    return ""


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto: colapsa espacios, strips, decodifica HTML entities via BS4.

    Args:
        texto: Texto a normalizar.

    Returns:
        Texto limpio.
    """
    if not texto:
        return ""
    # BeautifulSoup get_text() ya decodifica la mayoría de entidades
    texto = re.sub(r"\s+", " ", texto.strip())
    return texto


# ============================================================
# Parser: Index de votaciones
# ============================================================


def parse_votaciones_index(html: str) -> list[str]:
    """Parsea la página de votaciones y extrae URLs de páginas por fecha.

    Lee la página ``/66/votaciones/`` y extrae todos los links a páginas
    de fecha con el patrón ``/66/votaciones/YYYY_MM_DD``.

    Los links pueden aparecer:
    - En ``<a>`` con class ``enlace-votacion`` (últimas votaciones)
    - En tablas con ``<a href='/66/votaciones/...'>`` (listado cronológico)

    Deduplica por fecha (misma fecha aparece múltiples veces).

    Args:
        html: HTML de la página ``/66/votaciones/``.

    Returns:
        Lista de URLs relativas deduplicadas
        (ej: ["/66/votaciones/2026_03_25", ...]).
    """
    soup = BeautifulSoup(html, "lxml")
    urls: set[str] = set()

    # Patrón de fecha: YYYY_MM_DD
    patron_fecha = re.compile(r"/66/votaciones/\d{4}_\d{2}_\d{2}")

    # 1. Buscar enlaces con class "enlace-votacion"
    for a_tag in soup.find_all("a", class_=re.compile(r"enlace-votacion", re.I)):
        href = a_tag.get("href", "")
        if patron_fecha.search(href):
            urls.add(href.strip())

    # 2. Buscar en cualquier <a> que contenga el patrón de fecha
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if patron_fecha.search(href):
            urls.add(href.strip())

    # Ordenar cronológicamente (fecha más reciente primero)
    resultado = sorted(urls, reverse=True)

    logger.debug(f"Índice de votaciones: {len(resultado)} URLs de fecha encontradas")
    return resultado


# ============================================================
# Parser: Página de fecha
# ============================================================


def parse_votaciones_fecha(
    html: str, fecha_str: str
) -> list[SenadoVotacionIndexRecord]:
    """Parsea la página de una fecha y extrae las votaciones del día.

    Lee la página ``/66/votaciones/YYYY_MM_DD`` y extrae los links
    a votaciones individuales: ``<a href="/66/votacion/{id}">Título</a>``.

    HTML real verificado:
    .. code-block:: html

        <tr style="background: rgba(255, 245, 243, 1);">
          <td style="padding: 15px;">
            <div>
              <a href="/66/votacion/5069">Dictamen de la Comisión de Marina...</a>
            </div>
          </td>
        </tr>

    Args:
        html: HTML de la página de fecha.
        fecha_str: Fecha del día (formato ``YYYY_MM_DD``).

    Returns:
        Lista de :class:`SenadoVotacionIndexRecord` con id y titulo.
    """
    soup = BeautifulSoup(html, "lxml")
    records: list[SenadoVotacionIndexRecord] = []

    # Buscar todos los links a votaciones individuales
    patron_votacion = re.compile(r"/66/votacion/(\d+)")

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        match = patron_votacion.search(href)
        if not match:
            continue

        votacion_id = int(match.group(1))
        titulo = a_tag.get_text(strip=True)

        if not titulo:
            continue

        records.append(
            SenadoVotacionIndexRecord(
                id=votacion_id,
                titulo=titulo,
                fecha=fecha_str,
            )
        )

    # Deduplicar por ID (misma votación puede aparecer múltiples veces)
    vistos: set[int] = set()
    unicos: list[SenadoVotacionIndexRecord] = []
    for rec in records:
        if rec.id not in vistos:
            vistos.add(rec.id)
            unicos.append(rec)

    logger.debug(
        f"Fecha {fecha_str}: {len(unicos)} votaciones encontradas "
        f"(de {len(records)} links totales)"
    )
    return unicos


# ============================================================
# Parser: Detalle de votación individual
# ============================================================


def parse_votacion_detalle(
    html: str, votacion_id: int
) -> Optional[SenadoVotacionRecord]:
    """Parsea la página individual de una votación.

    Lee la página ``/66/votacion/{id}`` y extrae:
    - Período legislativo del ``<h3><strong>``
    - Fecha del ``<p><strong>`` dentro del panel-heading
    - Título del dictamen del panel-body
    - Totales: EN PRO, EN CONTRA, ABSTENCIÓN

    HTML real verificado (votación 5069):
    - Header: ``SEGUNDO AÑO DE EJERCICIO<br>SEGUNDO PERIODO ORDINARIO``
    - Fecha: ``Miércoles 25 de marzo de 2026``
    - Totales como texto: ``EN PRO 112``, ``EN CONTRA 1``, ``ABSTENCIÓN 5``

    Args:
        html: HTML de la página ``/66/votacion/{id}``.
        votacion_id: ID de la votación.

    Returns:
        :class:`SenadoVotacionRecord` con los datos completos, o ``None``
        si no se encuentran datos suficientes.
    """
    soup = BeautifulSoup(html, "lxml")

    # --- Extraer período y año de ejercicio ---
    anio_ejercicio = ""
    periodo = ""

    # Buscar en <h3><strong> el texto del período
    h3 = soup.find("h3")
    if h3:
        strong = h3.find("strong")
        if strong:
            texto_periodo = strong.get_text(separator=" ", strip=True)
            texto_periodo = re.sub(r"\s+", " ", texto_periodo)
            # Separar en año de ejercicio y período
            # Formato: "SEGUNDO AÑO DE EJERCICIO SEGUNDO PERIODO ORDINARIO"
            match = re.match(
                r"(\w+\s+AÑO\s+DE\s+EJERCICIO)\s+(.+)",
                texto_periodo,
                re.IGNORECASE,
            )
            if match:
                anio_ejercicio = _normalizar_texto(match.group(1))
                periodo = _normalizar_texto(match.group(2))

    # --- Extraer fecha ---
    fecha_raw = ""
    fecha_iso = ""

    # Buscar fecha en <p><strong> dentro de panel-heading
    panel_heading = soup.find("div", class_="panel-heading")
    if panel_heading:
        for p in panel_heading.find_all("p"):
            strong = p.find("strong")
            if strong:
                texto = strong.get_text(strip=True)
                # Detectar patrón de fecha: "Día de la semana DD de Mes de AAAA"
                if re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", texto):
                    fecha_raw = texto
                    fecha_iso = _parsear_fecha_senado(texto)
                    break

    # Si no se encontró en panel-heading, buscar en todo el HTML
    if not fecha_raw:
        for p in soup.find_all("p"):
            strong = p.find("strong")
            texto = strong.get_text(strip=True) if strong else p.get_text(strip=True)
            if re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", texto):
                fecha_raw = texto
                fecha_iso = _parsear_fecha_senado(texto)
                break

    # --- Extraer título ---
    titulo = ""

    # Buscar en panel-body dentro de td
    panel_body = soup.find("div", class_="panel-body")
    if panel_body:
        # El título puede estar en un <div><a> o directamente como texto
        link = panel_body.find("a")
        if link:
            titulo = link.get_text(strip=True)
        else:
            titulo = panel_body.get_text(strip=True)
            # Limitar a primeras 500 chars (puede incluir texto adicional)
            titulo = titulo[:500] if len(titulo) > 500 else titulo

    # Si no se encontró en panel-body, buscar en <td> directamente
    if not titulo:
        for td in soup.find_all("td"):
            link = td.find("a")
            if link and not re.search(r"/66/votacion/\d+", link.get("href", "")):
                texto = link.get_text(strip=True)
                if len(texto) > 20:  # Los títulos suelen ser largos
                    titulo = texto
                    break

    # --- Extraer totales de votos ---
    texto_completo = soup.get_text()

    # Buscar patrones de totales, manejando HTML entities
    # "EN PRO 112", "EN CONTRA 1", "ABSTENCIÓN 5" o "ABSTENCI&Oacute;N 5"
    total_pro = 0
    total_contra = 0
    total_abstencion = 0

    match_pro = re.search(r"EN\s+PRO\s+(\d+)", texto_completo, re.IGNORECASE)
    if match_pro:
        total_pro = int(match_pro.group(1))

    match_contra = re.search(r"EN\s+CONTRA\s+(\d+)", texto_completo, re.IGNORECASE)
    if match_contra:
        total_contra = int(match_contra.group(1))

    # ABSTENCIÓN puede tener Ó como &Oacute; o Unicode directo
    match_abst = re.search(
        r"ABSTENCI(?:&Oacute;N|ÓN|ON)\s+(\d+)", texto_completo, re.IGNORECASE
    )
    if match_abst:
        total_abstencion = int(match_abst.group(1))

    total_votos = total_pro + total_contra + total_abstencion

    # --- Verificar datos mínimos ---
    if not titulo and not total_pro and not total_contra:
        logger.warning(f"Votación {votacion_id}: datos insuficientes para parsear")
        return None

    # Construir fuente URL
    from .config import SENADO_BASE_URL, SENADO_LEGISLATURA

    fuente_url = f"{SENADO_BASE_URL}/{SENADO_LEGISLATURA}/votacion/{votacion_id}"

    logger.debug(
        f"Votación {votacion_id}: '{titulo[:60]}...' "
        f"PRO={total_pro} CONTRA={total_contra} ABST={total_abstencion}"
    )

    return SenadoVotacionRecord(
        id=votacion_id,
        titulo=titulo,
        fecha=fecha_raw,
        fecha_iso=fecha_iso,
        periodo=periodo,
        anio_ejercicio=anio_ejercicio,
        total_pro=total_pro,
        total_contra=total_contra,
        total_abstencion=total_abstencion,
        total_votos=total_votos,
        fuente_url=fuente_url,
    )


# ============================================================
# Parser: Tabla AJAX de votos
# ============================================================


def parse_ajax_table(html: str) -> list[SenadoVotoRecord]:
    """Parsea la respuesta HTML del endpoint AJAX ``viewTableVot.php``.

    El endpoint devuelve un fragmento HTML con filas de datos:
    Número | Nombre (con prefijo "Sen. ") | Partido | Voto

    Cada fila tiene 4 celdas (``<td>``):
    - Número secuencial
    - Nombre con prefijo "Sen. "
    - Partido (MORENA, PAN, PRI, etc.)
    - Voto (PRO, CONTRA, ABSTENCIÓN)

    El voto puede contener HTML entities: "ABSTENCI&Oacute;N" → "ABSTENCIÓN"

    Args:
        html: HTML fragmento de la respuesta AJAX.

    Returns:
        Lista de :class:`SenadoVotoRecord` con los votos individuales.
    """
    soup = BeautifulSoup(html, "lxml")
    votos: list[SenadoVotoRecord] = []

    # Buscar todas las filas de la tabla
    for row in soup.find_all("tr"):
        celdas = row.find_all("td")
        if len(celdas) < 4:
            continue

        # Número secuencial
        try:
            numero = int(celdas[0].get_text(strip=True))
        except ValueError:
            continue

        # Nombre del senador (con prefijo "Sen. ")
        nombre = celdas[1].get_text(strip=True)
        if not nombre:
            continue

        # Grupo parlamentario (partido)
        grupo = celdas[2].get_text(strip=True)

        # Voto — normalizar HTML entities
        voto_raw = celdas[3].get_text(strip=True)
        voto = _normalizar_voto(voto_raw)

        votos.append(
            SenadoVotoRecord(
                numero=numero,
                nombre=nombre,
                grupo_parlamentario=grupo,
                voto=voto,
            )
        )

    logger.debug(f"Tabla AJAX: {len(votos)} votos individuales parseados")
    return votos


def _normalizar_voto(voto_raw: str) -> str:
    """Normaliza el sentido del voto a valores canónicos.

    Maneja HTML entities y variantes:
    - "ABSTENCI&Oacute;N" → "ABSTENCIÓN"
    - "ABSTENCIÓN" → "ABSTENCIÓN"
    - "PRO" → "PRO"
    - "CONTRA" → "CONTRA"

    Args:
        voto_raw: Texto del voto tal como aparece en el HTML.

    Returns:
        Voto normalizado: "PRO", "CONTRA" o "ABSTENCIÓN".
    """
    if not voto_raw:
        return voto_raw

    voto = voto_raw.strip().upper()

    # BeautifulSoup ya decodifica &Oacute; → Ó (U+00D3), así que el input
    # típico es "ABSTENCIÓN". También manejamos "ABSTENCI&Oacute;N" por si
    # BS4 no decodifica (ej: get_text() vs contenido raw).
    # Patrones que cubrimos:
    #   ABSTENCIÓN  → ABSTENCIÓN (ya correcto)
    #   ABSTENCI&Oacute;N → ABSTENCIÓN (entity residual)
    #   ABSTENCION  → ABSTENCIÓN (sin acento, en mayúsculas)
    if re.search(r"ABSTENCION", voto):
        voto = re.sub(r"ABSTENCION", "ABSTENCIÓN", voto)
    elif re.search(r"ABSTENCI&Oacute;N", voto):
        voto = re.sub(r"ABSTENCI&Oacute;N", "ABSTENCIÓN", voto)

    return voto
