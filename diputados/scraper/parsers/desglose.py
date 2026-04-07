"""
parsers/desglose.py — Parser del desglose estadístico por partido del SITL.

Parsea la página estadistico_votacionnplxvi.php?votaciont={id} que contiene
el desglose de votos por grupo parlamentario de una votación.

Estructura HTML real (verificada contra estadistico_v52.html):
- Título en <span class="Estilo61encx"> ANTES de la tabla
- Fecha en otro <span class="Estilo61encx">
- Tabla con headers: GRUPO PARLAMENTARIO, A FAVOR, EN CONTRA, ABSTENCIÓN,
  SOLO ASISTENCIA, AUSENTE, TOTAL
- 7 filas de datos (MORENA, PAN, PVEM, PT, PRI, MC, IND)
- Fila TOTAL con bgcolor="#343a40"
- Cada nombre de partido es un link a listados_votacionesnplxvi.php
"""

import re

from bs4 import BeautifulSoup

from ..models import DesglosePartido, DesgloseVotacion


def parse_desglose(html: str, sitl_id: int) -> DesgloseVotacion | None:
    """Parsea el HTML del desglose estadístico de una votación.

    Args:
        html: HTML de la página de estadístico del SITL.
        sitl_id: ID SITL de la votación.

    Returns:
        DesgloseVotacion con los datos parseados, o None si no hay datos.
    """
    soup = BeautifulSoup(html, "lxml")

    # Buscar título y fecha en spans con clase Estilo61encx
    titulo = ""
    fecha = ""
    spans = soup.find_all("span", class_="Estilo61encx")
    for span in spans:
        texto = span.get_text(strip=True)
        if not texto:
            continue
        # Detectar fecha: formato "DD-Mes-AAAA" o "DD Mes AAAA"
        match_fecha = re.search(r"(\d{1,2}[-\s]\w+[-\s]\d{4})", texto)
        if match_fecha and not fecha:
            fecha = match_fecha.group(1)
        elif texto and not titulo:
            # El primer span largo es el título
            titulo = texto

    # Si no encontramos con Estilo61encx, buscar con Estilo61enex (variante)
    if not titulo:
        spans_alt = soup.find_all("span", class_="Estilo61enex")
        for span in spans_alt:
            texto = span.get_text(strip=True)
            if texto:
                titulo = texto
                break

    # Buscar tabla con desglose por partido
    partidos: list[DesglosePartido] = []
    totales: DesglosePartido | None = None

    # Buscar la tabla que contiene las filas con partido links
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            celdas = row.find_all("td")
            if len(celdas) < 7:
                continue

            # Detectar fila de totales por bgcolor
            es_total = row.get("bgcolor") == "#343a40" or (celdas[0].get("bgcolor") == "#343a40")

            # Nombre del partido (puede ser link o texto directo)
            nombre = celdas[0].get_text(strip=True)
            if not nombre:
                continue

            # Saltar header row
            if "GRUPO PARLAMENTARIO" in nombre.upper():
                continue

            try:
                a_favor = int(celdas[1].get_text(strip=True) or "0")
                en_contra = int(celdas[2].get_text(strip=True) or "0")
                abstencion = int(celdas[3].get_text(strip=True) or "0")
                solo_asistencia = int(celdas[4].get_text(strip=True) or "0")
                ausente = int(celdas[5].get_text(strip=True) or "0")
                total = int(celdas[6].get_text(strip=True) or "0")
            except (ValueError, IndexError):
                continue

            partido = DesglosePartido(
                partido_nombre=nombre,
                a_favor=a_favor,
                en_contra=en_contra,
                abstencion=abstencion,
                solo_asistencia=solo_asistencia,
                ausente=ausente,
                total=total,
            )

            if es_total:
                totales = partido
            else:
                partidos.append(partido)

    if not partidos:
        return None

    # Si no se encontró fila de totales, calcular
    if totales is None:
        totales = DesglosePartido(
            partido_nombre="TOTAL",
            a_favor=sum(p.a_favor for p in partidos),
            en_contra=sum(p.en_contra for p in partidos),
            abstencion=sum(p.abstencion for p in partidos),
            solo_asistencia=sum(p.solo_asistencia for p in partidos),
            ausente=sum(p.ausente for p in partidos),
            total=sum(p.total for p in partidos),
        )

    return DesgloseVotacion(
        sitl_id=sitl_id,
        titulo=titulo,
        fecha=fecha,
        partidos=partidos,
        totales=totales,
    )
