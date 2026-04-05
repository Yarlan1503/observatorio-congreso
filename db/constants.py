# db/constants.py — Constantes compartidas del Observatorio del Congreso
"""
Mapeos y constantes de normalización de partidos del Congreso de la Unión.

Este módulo centraliza los mapeos usados en todos los módulos de analysis/
para evitar duplicación y garantizar consistencia.

Constantes (por defecto, hardcodeadas para Diputados LXVI):
    _NAME_TO_ORG: dict[str | None, str]
        Mapeo de normalización de vote.group → org_id canónico.
        Acepta tanto IDs ('O01') como nombres de texto ('Morena').
        None se mapea a 'O11' (Independientes).

    _ORG_ID_TO_NAME: dict[str, str]
        Mapeo de org_id → nombre completo del partido.

    _ORG_TO_SHORT: dict[str, str]
        Mapeo de org_id → nombre corto (sigla) para reportes.

    _PARTY_ORG_IDS: tuple[str, ...]
        Tuple de org_ids que corresponden a partidos políticos reconocidos
        (excluye instituciones O08, O09 y coaliciones O10).

    _P_FLOOR: float
        Floor de probabilidad para evitar log(0) = -inf en NOMINATE.

Funciones dinámicas:
    init_constants_from_db(db_path): reemplaza los mapeos estáticos con datos
        reales de la tabla organization de la BD.

    get_total_seats(db_path, camara): cuenta personas únicas con membership
        activa en una cámara dada.
"""

import sqlite3
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# IDs de las cámaras
# ---------------------------------------------------------------------------
CAMARA_DIPUTADOS_ID: str = "O08"
CAMARA_SENADO_ID: str = "O09"

# ---------------------------------------------------------------------------
# Mapeo de normalización de vote.group → org_id canónico
# ---------------------------------------------------------------------------
_NAME_TO_ORG: dict[str | None, str] = {
    # IDs canónicos (ya normalizados) — passthrough
    "O01": "O01",
    "O02": "O02",
    "O03": "O03",
    "O04": "O04",
    "O05": "O05",
    "O06": "O06",
    "O07": "O07",
    "O08": "O08",
    "O09": "O09",
    "O10": "O10",
    "O11": "O11",
    "O12": "O12",
    "O13": "O13",
    "O14": "O14",
    "O15": "O15",
    "O16": "O16",
    # Nombres de texto encontrados en vote.group
    "Morena": "O01",
    "PT": "O02",
    "PVEM": "O03",
    "PAN": "O04",
    "PRI": "O05",
    "MC": "O06",
    "PRD": "O07",
    "Independientes": "O11",
    "CONV": "O12",
    "NA": "O13",
    "ALT": "O14",
    "PES": "O15",
    "SP": "O16",
    # NULL → Independientes
    None: "O11",
}

# ---------------------------------------------------------------------------
# Mapeo de org_id → nombre completo
# ---------------------------------------------------------------------------
_ORG_ID_TO_NAME: dict[str, str] = {
    "O01": "Morena",
    "O02": "Partido del Trabajo (PT)",
    "O03": "Partido Verde Ecologista de México (PVEM)",
    "O04": "Partido Acción Nacional (PAN)",
    "O05": "Partido Revolucionario Institucional (PRI)",
    "O06": "Movimiento Ciudadano (MC)",
    "O07": "Partido de la Revolución Democrática (PRD)",
    "O08": "Cámara de Diputados",
    "O09": "Senado de la República",
    "O10": "Sigamos Haciendo Historia",
    "O11": "Independientes",
    "O12": "Convergencia",
    "O13": "Nueva Alianza",
    "O14": "Alternativa Socialdemócrata",
    "O15": "Partido Encuentro Social",
    "O16": "Sin Partido",
}

# Alias para compatibilidad (usado en nominate.py y visualizaciones)
_ORG_TO_SHORT: dict[str, str] = {
    "O01": "MORENA",
    "O02": "PT",
    "O03": "PVEM",
    "O04": "PAN",
    "O05": "PRI",
    "O06": "MC",
    "O07": "PRD",
    "O11": "Independientes",
    "O12": "CONV",
    "O13": "NA",
    "O14": "ALT",
    "O15": "PES",
}

# ---------------------------------------------------------------------------
# Partidos reconocidos (excluye instituciones y coaliciones)
# ---------------------------------------------------------------------------
_PARTY_ORG_IDS: tuple[str, ...] = (
    "O01",
    "O02",
    "O03",
    "O04",
    "O05",
    "O06",
    "O07",
    "O11",
    "O12",
    "O13",
    "O14",
    "O15",
    "O16",
)

# Floor de probabilidad para evitar log(0) = -inf en el log-likelihood.
# Consistente con implementaciones de referencia (R wnominate package).
_P_FLOOR: float = 1e-15

# Total de asientos por defecto (Cámara de Diputados)
TOTAL_SEATS: int = 500

# Threshold mínimo de votos para incluir legislator en análisis de co-votación
MIN_VOTES: int = 10


# ===========================================================================
# Funciones dinámicas
# ===========================================================================


def init_constants_from_db(db_path: str) -> None:
    """Reemplaza los mapeos estáticos con datos reales de la BD.

    Lee la tabla organization y construye:
    - _NAME_TO_ORG: mapeo de nombre/abbr → org_id
    - _ORG_ID_TO_NAME: mapeo de org_id → nombre completo
    - _ORG_TO_SHORT: mapeo de org_id → abbr (sigla)
    - _PARTY_ORG_IDS: tuple de org_ids de partidos políticos

    Los valores hardcodeados se mantienen como fallback para orgs que
    existan en constantes pero no en la BD.

    Args:
        db_path: Ruta a la BD SQLite (congreso.db).
    """
    global _NAME_TO_ORG, _ORG_ID_TO_NAME, _ORG_TO_SHORT, _PARTY_ORG_IDS

    path = Path(db_path)
    if not path.exists():
        return

    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT id, nombre, abbr, clasificacion FROM organization"
        ).fetchall()

        # Construir mapeos dinámicos
        new_name_to_org: dict[str | None, str] = {None: "O11"}
        new_org_to_name: dict[str, str] = {}
        new_org_to_short: dict[str, str] = {}
        party_ids: list[str] = []

        for org_id, nombre, abbr, clasificacion in rows:
            # org_id → nombre
            new_org_to_name[org_id] = nombre

            # org_id → short (usar abbr si existe, sino extraer del nombre)
            if abbr:
                new_org_to_short[org_id] = abbr
            elif clasificacion == "partido":
                # Usar primera palabra del nombre como sigla
                new_org_to_short[org_id] = nombre.split("(")[0].split()[0].upper()

            # nombre/abbr → org_id (para normalización de vote.group)
            new_name_to_org[org_id] = org_id  # IDs canónicos (passthrough)
            if abbr:
                new_name_to_org[abbr] = org_id
                new_name_to_org[abbr.upper()] = org_id
            # Nombre completo como key
            new_name_to_org[nombre] = org_id
            # Primera palabra del nombre (para matching parcial)
            first_word = nombre.split()[0] if nombre else ""
            if first_word and len(first_word) > 2:
                new_name_to_org[first_word] = org_id
                new_name_to_org[first_word.upper()] = org_id

            # Acumular partidos
            if clasificacion == "partido":
                party_ids.append(org_id)

        # Agregar Independientes si existe
        if "O11" not in new_org_to_name:
            new_org_to_name["O11"] = "Independientes"
            new_org_to_short["O11"] = "Independientes"
            party_ids.append("O11")

        # Merge con fallbacks (hardcodeados que no estén en BD)
        for key, val in _NAME_TO_ORG.items():
            if key not in new_name_to_org:
                new_name_to_org[key] = val
        for key, val in _ORG_ID_TO_NAME.items():
            if key not in new_org_to_name:
                new_org_to_name[key] = val

        # Actualizar globals
        _NAME_TO_ORG = new_name_to_org
        _ORG_ID_TO_NAME = new_org_to_name
        _ORG_TO_SHORT = new_org_to_short
        _PARTY_ORG_IDS = tuple(sorted(set(party_ids)))

    finally:
        conn.close()


def get_total_seats(db_path: str, camara: str = "D") -> int:
    """Cuenta personas únicas con membership activa en una cámara.

    Para Diputados (D): cuenta personas con rol='diputado' y membership activa.
    Para Senado (S): cuenta personas con rol='senador' y membership activa.

    Si la BD no existe o no hay datos, retorna el valor por defecto:
    - Diputados: 500
    - Senado: 128

    Args:
        db_path: Ruta a la BD SQLite.
        camara: 'D' para Diputados, 'S' para Senado.

    Returns:
        Número de personas únicas con membership activa.
    """
    defaults = {"D": 500, "S": 128}
    default = defaults.get(camara, 500)

    path = Path(db_path)
    if not path.exists():
        return default

    rol = "diputado" if camara == "D" else "senador"

    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            """SELECT COUNT(DISTINCT person_id) FROM membership
               WHERE rol = ?""",
            (rol,),
        ).fetchone()
        count = row[0] if row and row[0] > 0 else default
        return count
    finally:
        conn.close()
