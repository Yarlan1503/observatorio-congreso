# db/constants.py — Constantes compartidas del Observatorio del Congreso
"""
Mapeos y constantes de normalización de partidos del Congreso de la Unión.

Este módulo centraliza los mapeos usados en todos los módulos de analysis/
para evitar duplicación y garantizar consistencia.

Constantes:
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
"""

# ---------------------------------------------------------------------------
# Mapeo de normalización de vote.group → org_id canónico
# ---------------------------------------------------------------------------
_NAME_TO_ORG: dict[str | None, str] = {
    # IDs canónicos (ya normalizados)
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
    # Nombres de texto encontrados en vote.group
    "Morena": "O01",
    "PT": "O02",
    "PVEM": "O03",
    "PAN": "O04",
    "PRI": "O05",
    "MC": "O06",
    "PRD": "O07",
    "Independientes": "O11",
    # NULL → Independientes
    None: "O11",
}

# ---------------------------------------------------------------------------
# Mapeo de org_id → nombre completo
# ---------------------------------------------------------------------------
_ORG_ID_TO_NAME: dict[str, str] = {
    "O01": "Morena",
    "O02": "PT",
    "O03": "PVEM",
    "O04": "PAN",
    "O05": "PRI",
    "O06": "MC",
    "O07": "PRD",
    "O08": "Institución",
    "O09": "Institución",
    "O10": "Coalición",
    "O11": "Independientes",
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
)

# Floor de probabilidad para evitar log(0) = -inf en el log-likelihood.
# Consistente con implementaciones de referencia (R wnominate package).
_P_FLOOR: float = 1e-15

# Total de asientos en el Congreso (Cámara de Diputados)
TOTAL_SEATS: int = 500

# Threshold mínimo de votos para incluir legislator en análisis de co-votación
MIN_VOTES: int = 10
