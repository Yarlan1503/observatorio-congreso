"""analysis — Módulo de análisis de co-votación legislativa."""

from analysis.config import (
    CLOSE_VOTES_THRESHOLD,
    DEALIGNMENT_THRESHOLD,
    LOUVAIN_RESOLUTION,
    LOUVAIN_SEED,
    MIN_EVENTS_PER_WINDOW,
    REFORMA_JUDICIAL_VE_IDS,
    TOP_DISSENTERS_GLOBAL,
    TOP_DISSIDENTS_PER_WINDOW,
)
from analysis.constants import (
    CAMARA_MAP,
    COMMON_PARTIES,
    COLORES_WEB,
    DEFAULT_COLOR,
    ORG_TO_SHORT,
    PARTIDO_MAP,
    PARTY_COLORS,
    PARTY_ORDER,
)
from analysis.db import get_connection
