"""
parsers/votaciones.py — Parser del listado de votaciones por periodo del SITL.

Parsea la página votacionesxperiodonplxvi.php?pert={N} que contiene
el listado de todas las votaciones nominales de un periodo legislativo.

Estructura HTML real (verificada contra votaciones_p1.html):
- Tabla con clase 'tablevotaciones'
- Filas de fecha: <TR><TD colspan=2>3 Septiembre 2024</TD></TR>
- Filas de votación: <tr valign="top"> con 2 <td>:
  - 1er td: <a href="estadistico_votacionnplxvi.php?votaciont=ID">NUM</a>
  - 2do td: Título de la votación
- votaciont NO es igual al numero_secuencial (hay offset)
"""

import re
from bs4 import BeautifulSoup

from ..models import VotacionRecord


def parse_votaciones(html: str, periodo: int) -> list[VotacionRecord]:
    """Parsea el HTML del listado de votaciones y retorna lista de VotacionRecord.

    Args:
        html: HTML de la página de votaciones del SITL.
        periodo: Número de periodo legislativo.

    Returns:
        Lista de VotacionRecord con las votaciones encontradas.
    """
    soup = BeautifulSoup(html, "lxml")
    records: list[VotacionRecord] = []

    # Fecha actual (se actualiza al encontrar filas de fecha)
    fecha_actual = ""

    # Buscar la tabla principal con clase 'tablevotaciones'
    tabla = soup.find("table", class_="tablevotaciones")
    if not tabla:
        # Fallback: buscar cualquier tabla que contenga links con votaciont=
        tabla = soup.find("table")

    if not tabla:
        return records

    # Iterar sobre todas las filas
    for row in tabla.find_all("tr"):
        celdas = row.find_all("td")
        if not celdas:
            continue

        # Detectar fila de fecha: colspan=2 con texto de fecha
        if len(celdas) == 1 and celdas[0].get("colspan"):
            texto = celdas[0].get_text(strip=True)
            if texto and not texto.isdigit():
                fecha_actual = texto
                continue

        # Detectar fila de votación: tiene link con votaciont=
        link = row.find("a", href=re.compile(r"votaciont=(\d+)", re.IGNORECASE))
        if not link:
            continue

        match = re.search(r"votaciont=(\d+)", link["href"], re.IGNORECASE)
        if not match:
            continue

        sitl_id = int(match.group(1))

        # Número secuencial del texto del link
        try:
            numero_secuencial = int(link.get_text(strip=True))
        except ValueError:
            numero_secuencial = len(records) + 1

        # Título: segunda celda con clase 'Estiloparrafoc'
        titulo = ""
        if len(celdas) >= 2:
            titulo = celdas[1].get_text(strip=True)

        # Usar la fecha acumulada más cercana hacia arriba
        records.append(
            VotacionRecord(
                sitl_id=sitl_id,
                numero_secuencial=numero_secuencial,
                titulo=titulo,
                fecha=fecha_actual,
                periodo=periodo,
            )
        )

    return records
