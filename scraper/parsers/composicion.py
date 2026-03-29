"""
parsers/composicion.py — Parser de la composición del pleno del SITL.

Parsea la página info_diputados.php que muestra la composición actual
de la Cámara de Diputados por partido y entidad federativa.

NOTA: La página real es principalmente visual (SVG map, tarjetas de estados).
Los datos de composición por partido no están en una tabla estructurada
sino dispersos en <figcaption> y links a listado_diputados_gpnp.php.

Este parser extrae lo que es posible de la página:
- Links a curricula de diputados (si están presentes)
- Links a listado por partido (con tipot={party_id})

Para datos completos de composición por partido, se recomienda
scrapear las páginas de listado_diputados_gpnp.php por partido.
"""

import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from scraper.config import SITL_PARTY_BY_ID
from scraper.models import ComposicionPleno, ComposicionPartido, DiputadoComposicion


def parse_composicion(html: str, legislatura: str) -> Optional[ComposicionPleno]:
    """Parsea el HTML de la página de composición del pleno.

    NOTA: Esta página es mayormente visual. El parser extrae links a listados
    por partido pero los datos de composición detallada por partido requieren
    scrapeo adicional de listado_diputados_gpnp.php.

    Args:
        html: HTML de la página info_diputados.php.
        legislatura: Clave de legislatura (ej: "LXVI").

    Returns:
        ComposicionPleno con los datos extraídos, o None si no hay datos.
    """
    soup = BeautifulSoup(html, "lxml")
    partidos: list[ComposicionPartido] = []

    # Buscar links a listado_diputados_gpnp.php?tipot={party_id}
    # Estos links identifican cada partido
    party_links = soup.find_all(
        "a", href=re.compile(r"listado_diputados_gpnp\.php\?tipot=(\d+)")
    )

    seen_party_ids: set[int] = set()
    for link in party_links:
        match = re.search(r"tipot=(\d+)", link["href"])
        if not match:
            continue

        party_id = int(match.group(1))

        # Solo party IDs de partidos (no estados que usan tipot=Edo)
        if party_id not in SITL_PARTY_BY_ID:
            continue

        if party_id in seen_party_ids:
            continue
        seen_party_ids.add(party_id)

        partido_nombre = SITL_PARTY_BY_ID[party_id]

        # Buscar el número de diputados en el figcaption cercano
        total = _extraer_total_partido(link)

        partidos.append(
            ComposicionPartido(
                partido_nombre=partido_nombre,
                total=total,
                diputados=[],
            )
        )

    if not partidos:
        return None

    return ComposicionPleno(
        legislatura=legislatura,
        partidos=partidos,
    )


def _extraer_total_partido(link: Tag) -> int:
    """Intenta extraer el número total de diputados de un partido.

    Busca en el figcaption o elementos cercanos al link del partido.
    Si no encuentra número, retorna 0.
    """
    # Buscar figcaption en ancestros
    parent = link.parent
    for _ in range(5):  # Subir hasta 5 niveles
        if parent is None:
            break
        figcaption = parent.find("figcaption") if isinstance(parent, Tag) else None
        if figcaption:
            # Buscar <span class="numero"> dentro del figcaption
            span_num = figcaption.find("span", class_="numero")
            if span_num:
                try:
                    return int(span_num.get_text(strip=True))
                except ValueError:
                    pass
            # Si no hay span.numero, intentar con el texto completo
            texto = figcaption.get_text(strip=True)
            match = re.search(r"(\d+)", texto)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        parent = parent.parent if isinstance(parent, Tag) else None

    return 0
