"""
busqueda.py — Parser para el formulario de búsqueda del SIL.

Provee función para extraer opciones válidas del formulario
(tipos de asunto, legislaturas, resultados, etc.) y construir
los parámetros POST.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from scraper_sil.models import SILBusquedaParams

logger = logging.getLogger(__name__)


def parse_busqueda_form(html: str) -> dict:
    """Extrae las opciones disponibles del formulario de búsqueda.

    Args:
        html: HTML del formulario ProcesoBusquedaAvanzada.php.

    Returns:
        Dict con opciones del formulario:
        {
            'legislaturas': ['LVI', 'LVII', ...],
            'tipos_asunto': {'1': 'Reforma Constitucional', ...},
            'resultados': {'A': 'Aprobado', 'D': 'Desechado', ...},
            'campos_hidden': {'nombre_campo': 'valor', ...}
        }
    """
    soup = BeautifulSoup(html, "lxml")
    options = {
        "legislaturas": [],
        "tipos_asunto": {},
        "resultados": {},
        "campos_hidden": {},
    }

    # Extraer legislaturas del select LEGISLATURA
    legislature_select = soup.find("select", {"name": "LEGISLATURA"})
    if legislature_select:
        for option in legislature_select.find_all("option"):
            value = option.get("value", "").strip()
            if value:
                options["legislaturas"].append(value)
    else:
        # hardcoded si el parser no lo encuentra
        options["legislaturas"] = [
            "LVI",
            "LVII",
            "LVIII",
            "LIX",
            "LX",
            "LXI",
            "LXII",
            "LXIII",
            "LXIV",
            "LXV",
            "LXVI",
        ]

    # Extraer tipos de asunto del select TASUNTO_AR
    tipo_asunto_select = soup.find("select", {"name": "TASUNTO_AR[]"})
    if tipo_asunto_select:
        for option in tipo_asunto_select.find_all("option"):
            value = option.get("value", "").strip()
            label = option.get_text(strip=True)
            if value:
                options["tipos_asunto"][value] = label

    # Extraer resultados del select RESULTADO
    resultado_select = soup.find("select", {"name": "RESULTADO"})
    if resultado_select:
        for option in resultado_select.find_all("option"):
            value = option.get("value", "").strip()
            label = option.get_text(strip=True)
            if value:
                options["resultados"][value] = label

    # Extraer campos hidden
    for hidden in soup.find_all("input", {"type": "hidden"}):
        name = hidden.get("name")
        value = hidden.get("value", "")
        if name:
            options["campos_hidden"][name] = value

    logger.debug(
        f"Form parsed: {len(options['legislaturas'])} legislaturas, "
        f"{len(options['tipos_asunto'])} tipos asunto, "
        f"{len(options['resultados'])} resultados"
    )

    return options


def build_search_params(
    params: SILBusquedaParams,
    form_options: Optional[dict] = None,
    session_info: Optional["SessionInfo"] = None,
) -> dict:
    """Construye parámetros POST para el formulario de búsqueda.

    Args:
        params: Parámetros de búsqueda.
        form_options: Opciones extraídas del formulario (para validación).

    Returns:
        Dict con todos los parámetros POST para el formulario.
    """
    post_params = {
        # Obligatorios - SIN ESTOS DA "Undefined index"
        "LEGISLATURA": params.legislature,
        "PAGINAS": str(params.paginas),
        "ESTATUS": "-1",  # CAMPO CRÍTICO FALTANTE
        "RESULTADOVOTACION": "9",  # Vota: Todos
        # Campos fijos
        "buscar": "1",
        "TIPOBUSQUEDA": "2",
        # Checkboxes - TODOS marcados por defecto
        "CAMARA_PRESENTADOR[]": ["1", "2", "5"],
    }

    # Agregar tipos de asunto si se especificaron
    if params.tipo_asunto:
        for tipo in params.tipo_asunto:
            post_params.setdefault("TASUNTO_AR[]", []).append(tipo)
            # httpx espera lista para valores múltiples
        if "TASUNTO_AR[]" not in post_params:
            post_params["TASUNTO_AR[]"] = params.tipo_asunto

    # Agregar resultado si se especificó
    if params.resultado:
        post_params["RESULTADO"] = params.resultado

    # Agregar fechas si se especificaron
    if params.fecha_inicio:
        post_params["FECHA_INIC"] = params.fecha_inicio
    if params.fecha_fin:
        post_params["FECHA_FIN"] = params.fecha_fin

    # Agregar parámetros de sesión si están disponibles
    if session_info:
        if session_info.serial:
            post_params["Serial"] = session_info.serial
        if session_info.reg:
            post_params["Reg"] = session_info.reg
        if session_info.origen:
            post_params["Origen"] = session_info.origen
        if session_info.referencia:
            post_params["REFERENCIA"] = session_info.referencia

    return post_params


def extract_sid_from_form(html: str) -> Optional[str]:
    """Extrae el SID del formulario de búsqueda.

    Args:
        html: HTML del formulario.

    Returns:
        SID si se encuentra, None otherwise.
    """
    soup = BeautifulSoup(html, "lxml")

    # Buscar en el action del formulario
    form = soup.find("form")
    if form:
        action = form.get("action", "")
        match = re.search(r"SID=([A-Za-z0-9]+)", action)
        if match:
            return match.group(1)

    # Buscar en inputs hidden
    sid_input = soup.find("input", {"name": "SID"})
    if sid_input:
        return sid_input.get("value")

    # Buscar en cualquier URL del HTML
    match = re.search(r"[?&]SID=([A-Za-z0-9]+)", html)
    if match:
        return match.group(1)

    return None
