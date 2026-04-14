"""
parsers/nominal.py — Parser del listado nominal de votos por partido del SITL.

Parsea la página listados_votaciones{suffix}.php?partidot={party}&votaciont={id}
que contiene el listado individual de votos de los diputados de un partido.

Estructura HTML LXVI (con clase CSS):
- Tabla con clase 'tablegpnp table-responsive-sm', headers: #, Diputado(a), Sentido del voto
- Cada nombre: <a href="votaciones_por_pernplxvi.php?iddipt={id}&pert=1">NOMBRE</a>

Estructura HTML LX-LXV (sin clase CSS):
- Tablas sin clase, pero con links iddipt= en las filas de datos
- Layout anidado: los datos están en tablas internas dentro de una tabla wrapper

Común a todas las legislaturas:
- Partido en <span> antes de la tabla
- Sentido del voto: "A favor", "En contra", "Ausente", "Abstencion"
- Tabla resumen al final: "A favor: N", "En contra: N", etc.
"""

import re

from bs4 import BeautifulSoup

from ..models import NominalVotacion, VotoNominal

# Patrones para el resumen final
_PATRON_RESUMEN = re.compile(
    r"(A favor|En contra|Abstenciones?|Sin sentido del voto|Ausentes?|Total)\s*:\s*(\d+)",
    re.IGNORECASE,
)


def parse_nominal(html: str, sitl_id: int, partido_nombre: str) -> NominalVotacion:
    """Parsea el HTML del listado nominal de votos de un partido.

    Args:
        html: HTML de la página nominal del SITL.
        sitl_id: ID SITL de la votación.
        partido_nombre: Nombre del partido (grupo parlamentario del desglose SITL).
            NOTA: NO se sobreescribe con el span del HTML. En LXV el SITL cambió
            el formato y el <span> muestra la afiliación individual del diputado,
            no el grupo parlamentario. El parámetro es la fuente de verdad.

    Returns:
        NominalVotacion con la lista de votos y resumen.
    """
    soup = BeautifulSoup(html, "lxml")
    votos: list[VotoNominal] = []
    resumen: dict[str, int] = {}

    # NOTA: NO se usa _extraer_partido() para sobreescribir partido_nombre.
    # En LXV el SITL cambió el formato: el <span> antes de la tabla muestra la
    # afiliación individual del diputado (ej. "Morena"), no el grupo parlamentario
    # (ej. "Morena, PVEM y PT"). El partido_nombre que viene del desglose
    # estadístico SITL es la fuente de verdad para el grupo parlamentario.
    # La función _extraer_partido() se conserva para uso diagnóstico futuro.

    # Buscar tablas de datos — LXVI usa clase 'tablegpnp', LX-LXV no tienen clase
    tablas = soup.find_all("table", class_="tablegpnp")

    if not tablas:
        # Fallback para legislaturas LX-LXV: buscar tablas con links iddipt=
        # Las tablas de layout anidadas contienen los datos reales
        for table in soup.find_all("table"):
            if table.find("a", href=re.compile(r"iddipt=\d+")):
                tablas.append(table)

    for tabla in tablas:
        # Si la tabla contiene votos individuales (tiene links de diputados)
        if tabla.find("a", href=re.compile(r"iddipt=\d+")):
            _parse_tabla_votos(tabla, votos)
        else:
            _parse_tabla_resumen(tabla, resumen)

    return NominalVotacion(
        sitl_id=sitl_id,
        partido_nombre=partido_nombre,
        votos=votos,
        resumen=resumen,
    )


def _extraer_partido(soup: BeautifulSoup) -> str | None:
    """Extrae el nombre del partido del span antes de la tabla."""
    # Buscar el span que indica el partido (justo antes de la tabla)
    # LXVI usa Estilo61enex1, otras legislaturas pueden variar
    for class_name in ["Estilo61enex1", "Estilo61enex", "Estilo61encx"]:
        for span in soup.find_all("span", class_=class_name):
            texto = span.get_text(strip=True)
            if texto and not texto.startswith("Primer") and "PERIODO" not in texto.upper():
                # Evitar que sea el header de la votación o títulos largos
                if len(texto) < 100 and not any(
                    kw in texto.upper() for kw in ["DECRETO", "VOTACIÓN", "LISTADO", "MINUTA"]
                ):
                    return texto
    return None


def _parse_tabla_votos(tabla, votos: list[VotoNominal]) -> None:
    """Parsea las filas de votos individuales de una tabla."""
    for row in tabla.find_all("tr"):
        celdas = row.find_all("td")
        if len(celdas) < 3:
            continue

        # Número secuencial
        try:
            numero = int(celdas[0].get_text(strip=True))
        except ValueError:
            continue

        # Nombre del diputado (puede estar dentro de un link)
        link = celdas[1].find("a", href=True)
        nombre = ""
        diputado_sitl_id = None

        if link:
            nombre = link.get_text(strip=True)
            match = re.search(r"iddipt=(\d+)", link["href"])
            if match:
                diputado_sitl_id = int(match.group(1))
        else:
            nombre = celdas[1].get_text(strip=True)

        # Sentido del voto
        sentido = celdas[2].get_text(strip=True)

        if not nombre or not sentido:
            continue

        # Normalizar sentido
        if sentido.lower() == "abstencion":
            sentido = "Abstención"

        votos.append(
            VotoNominal(
                numero=numero,
                nombre=nombre,
                sentido=sentido,
                diputado_sitl_id=diputado_sitl_id,
            )
        )


def _parse_tabla_resumen(tabla, resumen: dict[str, int]) -> None:
    """Parsea la tabla resumen con totales (A favor, En contra, etc.)."""
    texto = tabla.get_text()
    for match in _PATRON_RESUMEN.finditer(texto):
        clave = match.group(1).strip()
        valor = int(match.group(2))
        # Normalizar claves
        clave_lower = clave.lower()
        if "favor" in clave_lower:
            resumen["a_favor"] = valor
        elif "contra" in clave_lower:
            resumen["en_contra"] = valor
        elif "absten" in clave_lower:
            resumen["abstencion"] = valor
        elif "ausente" in clave_lower:
            resumen["ausentes"] = valor
        elif "sin sentido" in clave_lower:
            resumen["sin_sentido"] = valor
        elif "total" in clave_lower:
            resumen["total"] = valor
