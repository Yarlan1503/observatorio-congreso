"""
config.py — Parámetros tuneables del análisis del Observatorio Congreso.

Centraliza umbrales, IDs y contadores usados en los módulos de analysis/
para facilitar ajustes sin modificar la lógica de cada módulo.

Constantes agrupadas por categoría:
    - Ventanas temporales (covotacion_dinamica)
    - Detección de comunidades (comunidades)
    - Poder empírico (poder_empirico)
    - Evolución de partidos (evolucion_partidos)
"""

# ---------------------------------------------------------------------------
# Ventanas temporales — Análisis cross-legislatura
# ---------------------------------------------------------------------------
# Mínimo de votaciones por ventana temporal (ventanas menores se combinan)
MIN_EVENTS_PER_WINDOW: int = 30

# ---------------------------------------------------------------------------
# Detección de comunidades (Louvain)
# ---------------------------------------------------------------------------
# Semilla para reproducibilidad del algoritmo de Louvain
LOUVAIN_SEED: int = 42

# Resolución del algoritmo (> 1.0 = comunidades más pequeñas)
LOUVAIN_RESOLUTION: float = 1.0

# ---------------------------------------------------------------------------
# Poder empírico — Umbrales y listas
# ---------------------------------------------------------------------------
# Margen máximo para considerar una votación "cerrada"
CLOSE_VOTES_THRESHOLD: int = 10

# Vote_event IDs de la Reforma Judicial (específico de la legislatura)
REFORMA_JUDICIAL_VE_IDS: list[str] = ["VE04", "VE05"]

# Top N legisladores disidentes a retornar (análisis global)
TOP_DISSENTERS_GLOBAL: int = 10

# ---------------------------------------------------------------------------
# Covotación dinámica — Disidentes por ventana
# ---------------------------------------------------------------------------
# Top N legisladores disidentes por ventana temporal
TOP_DISSIDENTS_PER_WINDOW: int = 5

# ---------------------------------------------------------------------------
# Evolución de partidos — Umbrales de detección
# ---------------------------------------------------------------------------
# Cambio mínimo en co-votación para detectar dealignment (negativo = pérdida)
DEALIGNMENT_THRESHOLD: float = -0.05
