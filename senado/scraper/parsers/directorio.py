"""Parser para el directorio de senadores del Senado LXVI."""

from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup


# Mapeo de nombres completos de estados a abreviaturas
ESTADO_TO_ABBR = {
    "Aguascalientes": "AGS",
    "Baja California": "BC",
    "Baja California Sur": "BCS",
    "Campeche": "CAM",
    "Coahuila": "COAH",
    "Colima": "COL",
    "Chiapas": "CHIS",
    "Chihuahua": "CHIH",
    "Ciudad de México": "CDMX",
    "Durango": "DGO",
    "Estado de México": "MEX",
    "Guanajuato": "GTO",
    "Guerrero": "GRO",
    "Hidalgo": "HGO",
    "Jalisco": "JAL",
    "Michoacán": "MICH",
    "Morelos": "MOR",
    "Nayarit": "NAY",
    "Nuevo León": "NL",
    "Oaxaca": "OAX",
    "Puebla": "PUE",
    "Querétaro": "QRO",
    "Quintana Roo": "QROO",
    "San Luis Potosí": "SLP",
    "Sinaloa": "SIN",
    "Sonora": "SON",
    "Tabasco": "TAB",
    "Tamaulipas": "TAMS",
    "Tlaxcala": "TLAX",
    "Veracruz": "VER",
    "Yucatán": "YUC",
    "Zacatecas": "ZAC",
}

# Estados válidos para validación
ESTADOS_VALIDOS = set(ESTADO_TO_ABBR.keys())


@dataclass
class SenadorDirectorioRecord:
    """Datos de un senador del directorio."""

    senado_id: int  # ID del portal (ej: 1579)
    nombre: str  # Nombre completo
    partido: str  # Grupo parlamentario (MORENA, PAN, etc.)
    estado: str  # Entidad federativa (nombre completo)
    curul_tipo: str  # mayoría_relativa o plurinominal


def parse_directorio_senadores(html: str) -> list[SenadorDirectorioRecord]:
    """
    Parsea el HTML del directorio de senadores.

    La tabla tiene estructura:
    # | Nombre | Grupo Parlamentario | Ubicación | ...

    Los enlaces a perfiles son /66/senador/{id}

    Args:
        html: HTML de la página /66/senadores/directorio_de_senadores

    Returns:
        Lista de SenadorDirectorioRecord con senado_id, nombre, partido
        (estado y curul_tipo quedan Pending hasta cruzar con perfiles)
    """
    # IMPORTANTE: usar lxml porque el HTML del Senado tiene estructuras
    # malformadas que html.parser no maneja correctamente
    soup = BeautifulSoup(html, "lxml")
    resultados = []

    # Buscar TODAS las tablas del directorio
    # El portal renderiza los datos en múltiples tablas
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # El enlace al perfil está en la columna de Nombre (índice 1)
            link = row.find("a", href=lambda h: h and "/66/senador/" in h)
            if not link:
                continue

            # Extraer senado_id del href
            href = link.get("href", "")
            parsed = urlparse(href)
            path_parts = parsed.path.strip("/").split("/")
            senado_id = None
            for i, part in enumerate(path_parts):
                if part == "senador" and i + 1 < len(path_parts):
                    next_part = path_parts[i + 1]
                    if next_part.isdigit():
                        senado_id = int(next_part)
                        break

            if senado_id is None:
                continue

            # Nombre completo del enlace
            nombre = link.get_text(strip=True)

            # Grupo parlamentario (columna 2, índice 2)
            partido = ""
            if len(cells) >= 3:
                partido = cells[2].get_text(strip=True)

            # La columna de Ubicación (índice 3) no contiene el estado真正的
            # El estado real está en el perfil individual, no en el directorio

            resultados.append(
                SenadorDirectorioRecord(
                    senado_id=senado_id,
                    nombre=nombre,
                    partido=partido,
                    estado="",  # Pendiente: cruzar con perfil individual
                    curul_tipo="",  # Pendiente: cruzar con perfil individual
                )
            )

    return resultados


def parse_senador_perfil(html: str, senado_id: int) -> SenadorDirectorioRecord | None:
    """
    Parsea el HTML de un perfil individual de senador.

    Extrae:
    - nombre: del <h1> (ej: "Sen. Heriberto Marcelo Aguilar Castillo")
    - estado: del <h4> que contiene el nombre de un estado mexicano
    - curul_tipo: de <h3> que contiene "Mayoría Relativa" o "Representación Proporcional"

    Args:
        html: HTML de la página /66/senador/{id}
        senado_id: ID del senator para asociar

    Returns:
        SenadorDirectorioRecord con los datos extraídos, o None si no se pudo parsear
    """
    # Usar lxml para mejor parsing de HTML malformado
    soup = BeautifulSoup(html, "lxml")
    nombre = ""
    estado = ""
    curul_tipo = ""

    # Extraer nombre del <h1>
    h1 = soup.find("h1")
    if h1:
        nombre = h1.get_text(strip=True)
        # Limpiar prefijo "Sen. " si existe
        if nombre.startswith("Sen."):
            nombre = nombre[4:].strip()
        elif nombre.startswith("Senador "):
            nombre = nombre[8:].strip()

    # Buscar estado en <h4> que contenga nombre de estado mexicano
    for h4 in soup.find_all("h4"):
        text = h4.get_text(strip=True)
        if text in ESTADOS_VALIDOS:
            estado = text
            break

    # Buscar curul_tipo en <h3>
    # Formatos posibles:
    # - "Senador Electo por el Principio de Mayoría Relativa"
    # - "Senador Electo por el Principio de Representación Proporcional"
    for h3 in soup.find_all("h3"):
        text = h3.get_text(strip=True)
        text_lower = text.lower()
        if "mayoría relativa" in text_lower or "mayoria relativa" in text_lower:
            curul_tipo = "mayoría_relativa"
            break
        elif (
            "representación proporcional" in text_lower
            or "representacion proporcional" in text_lower
        ):
            curul_tipo = "plurinominal"
            break

    if not nombre:
        return None

    return SenadorDirectorioRecord(
        senado_id=senado_id,
        nombre=nombre,
        partido="",  # El partido no está en el perfil individual
        estado=estado,
        curul_tipo=curul_tipo,
    )


def enrich_directorio_con_perfiles(
    directorio: list[SenadorDirectorioRecord],
    perfiles: dict[int, SenadorDirectorioRecord],
) -> list[SenadorDirectorioRecord]:
    """
    Enriquece los registros del directorio con datos de perfiles individuales.

    Args:
        directorio: Lista de SenadorDirectorioRecord del directorio
        perfiles: Dict {senado_id: SenadorDirectorioRecord} con datos de perfiles

    Returns:
        Lista de SenadorDirectorioRecord con estado y curul_tipo completados
    """
    resultado = []
    for record in directorio:
        if record.senado_id in perfiles:
            perfil = perfiles[record.senado_id]
            record.estado = perfil.estado
            record.curul_tipo = perfil.curul_tipo
        resultado.append(record)
    return resultado
