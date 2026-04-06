#!/usr/bin/env python3
"""
covotacion.py — Módulo central de análisis de co-votación legislativa.

Construye matrices y grafos de co-votación a partir de los datos del
Observatorio del Congreso de la Unión (SQLite con esquema Popolo).

Funciones principales:
    - normalize_party: normaliza valores mixtos de vote.group a IDs canónicos
    - load_data: carga votos, personas y organizaciones desde la BD
    - get_primary_party: partido más frecuente por legislador
    - build_covotacion_matrix: matriz NxN de co-votación
    - build_graph: grafo networkx con atributos de nodos y aristas
    - compute_quantitative_metrics: métricas cuantitativas del grafo
"""

import logging
import sqlite3
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from db.constants import _NAME_TO_ORG, _ORG_ID_TO_NAME, _PARTY_ORG_IDS, MIN_VOTES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Función 1: normalize_party
# ---------------------------------------------------------------------------
def normalize_party(group_value: str | None) -> str:
    """Normalizar un valor de vote.group al ID canónico de organización.

    La columna vote.group contiene valores mixtos:
    - IDs de org: 'O01', 'O02', ..., 'O11'
    - Nombres de texto: 'Morena', 'PT', 'PVEM'
    - NULL (sin grupo)

    Retorna el org_id canónico (ej: 'O01', 'O02', etc.).
    Si el valor no está en el mapeo, retorna 'O11' (Independientes).

    Args:
        group_value: valor de la columna vote.group (str o None).

    Returns:
        ID canónico de organización (ej: 'O01').
    """
    return _NAME_TO_ORG.get(group_value, "O11")


# ---------------------------------------------------------------------------
# Función 2: load_data
# ---------------------------------------------------------------------------
def load_data(
    db_path: str, camara: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Cargar votos, personas y organizaciones desde la base de datos.

    Lee las tablas vote, person y organization de la BD SQLite,
    normaliza los partidos en los votos y retorna tres estructuras.

    Args:
        db_path: ruta al archivo SQLite (congreso.db).
        camara: Filtrar por cámara. Si 'D', solo vote_events de Diputados.
            Si 'S', solo vote_events de Senado. Si None, todos.

    Returns:
        Tupla con:
        - votes_df: DataFrame con columnas [voter_id, vote_event_id, option, party_id]
          donde party_id es el org_id normalizado.
        - persons_df: DataFrame con columnas [id, nombre, genero].
        - org_map: dict org_id → org_nombre, solo partidos (O01-O07, O11).

    Raises:
        FileNotFoundError: si db_path no existe.
        sqlite3.Error: si hay error de conexión o consulta.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        # Determinar filtro de cámara
        camara_filter = ""
        params: tuple = ()
        if camara == "D":
            camara_filter = " WHERE ve.organization_id = 'O08'"
        elif camara == "S":
            camara_filter = " WHERE ve.organization_id = 'O09'"

        # Votos (con filtro de cámara si se especifica)
        if camara_filter:
            votes_query = (
                f'SELECT v.voter_id, v.vote_event_id, v.option, v."group" '
                f"FROM vote v "
                f"JOIN vote_event ve ON v.vote_event_id = ve.id"
                f"{camara_filter}"
            )
        else:
            votes_query = 'SELECT voter_id, vote_event_id, option, "group" FROM vote'

        votes_df = pd.read_sql_query(votes_query, conn, params=params)
        # Normalizar partido
        votes_df["party_id"] = votes_df["group"].map(normalize_party)
        votes_df = votes_df[["voter_id", "vote_event_id", "option", "party_id"]]

        # Personas
        persons_df = pd.read_sql_query(
            "SELECT id, nombre, genero FROM person",
            conn,
        )

        # Organizaciones (solo partidos)
        orgs_df = pd.read_sql_query(
            "SELECT id, nombre FROM organization",
            conn,
        )
        org_map: dict[str, str] = {}
        for _, row in orgs_df.iterrows():
            if row["id"] in _PARTY_ORG_IDS:
                org_map[row["id"]] = row["nombre"]

        logger.info(
            "Datos cargados: %d votos, %d personas, %d organizaciones (camara=%s)",
            len(votes_df),
            len(persons_df),
            len(org_map),
            camara or "todas",
        )
    finally:
        conn.close()

    return votes_df, persons_df, org_map


# ---------------------------------------------------------------------------
# Función 3: get_primary_party
# ---------------------------------------------------------------------------
def get_primary_party(votes_df: pd.DataFrame) -> dict[str, str]:
    """Obtener el partido principal de cada legislador.

    El partido principal es el org_id más frecuente en los votos
    de cada legislador. Esto captura cambios de bancada: un legislador
    puede votar con diferentes partidos a lo largo de la legislatura,
    pero su partido principal es el más habitual.

    Args:
        votes_df: DataFrame con columnas [voter_id, vote_event_id, option, party_id].

    Returns:
        Dict voter_id → party_id (partido principal).
    """
    primary: dict[str, str] = {}
    for voter_id, group in votes_df.groupby("voter_id"):
        party_counts = Counter(group["party_id"])
        primary[voter_id] = party_counts.most_common(1)[0][0]
    return primary


# ---------------------------------------------------------------------------
# Función 4: build_covotacion_matrix
# ---------------------------------------------------------------------------
def build_covotacion_matrix(
    votes_df: pd.DataFrame,
    min_votes: int = MIN_VOTES,
) -> tuple[np.ndarray, list[str], dict[tuple[int, int], int]]:
    """Construir la matriz NxN de co-votación entre legisladores.

    Proceso:
    1. Filtra legisladores con ≥ min_votes donde option != 'ausente'.
    2. Para cada par (i, j), encuentra vote_events donde AMBOS participaron
       (option != 'ausente').
    3. Co-votación = coincidencias de option exactas / co-participaciones.
    4. Si co-participaciones = 0, peso = 0.
    5. Matriz es simétrica con diagonal = 1.0.

    Args:
        votes_df: DataFrame con columnas [voter_id, vote_event_id, option, party_id].
        min_votes: mínimo de votos (no ausentes) para ser elegible.

    Returns:
        Tupla con:
        - matrix: numpy array NxN simétrico, diagonal=1.0, valores en [0, 1].
        - legislators: lista ordenada de voter_ids elegibles.
        - co_participations: dict (i, j) → número de co-participaciones.
    """
    # Filtrar ausentes
    active_votes = votes_df[votes_df["option"] != "ausente"].copy()

    # Elegibilidad: legisladores con ≥ min_votes activos
    vote_counts = active_votes["voter_id"].value_counts()
    eligible_ids = set(vote_counts[vote_counts >= min_votes].index)

    # Legisladores ordenados
    legislators = sorted(eligible_ids)
    n = len(legislators)
    leg_idx = {leg_id: idx for idx, leg_id in enumerate(legislators)}

    logger.info(
        "Construyendo matriz de co-votación: %d legisladores elegibles de %d total",
        n,
        len(vote_counts),
    )

    # Filtrar votos a solo legisladores elegibles
    active_votes = active_votes[active_votes["voter_id"].isin(eligible_ids)]

    # Agrupar votos por vote_event_id para acceso rápido
    ve_groups = active_votes.groupby("vote_event_id")

    # Inicializar estructuras
    matrix = np.zeros((n, n), dtype=np.float64)
    co_participations: dict[tuple[int, int], int] = {}

    # Para cada vote_event, computar coincidencias entre pares presentes
    for _ve_id, ve_df in ve_groups:
        # Legisladores presentes en esta votación con su opción
        present = ve_df[["voter_id", "option"]].values  # array de (voter_id, option)
        m = len(present)

        for a in range(m):
            idx_a = leg_idx[present[a, 0]]
            opt_a = present[a, 1]
            for b in range(a, m):
                idx_b = leg_idx[present[b, 0]]
                opt_b = present[b, 1]

                # Clave canónica (i, j) donde i <= j
                key = (min(idx_a, idx_b), max(idx_a, idx_b))

                # Incrementar co-participaciones
                co_participations[key] = co_participations.get(key, 0) + 1

                # Incrementar coincidencias si misma opción
                if opt_a == opt_b:
                    matrix[idx_a, idx_b] += 1
                    if idx_a != idx_b:
                        matrix[idx_b, idx_a] += 1

    # Convertir conteos a proporciones
    for (i, j), co_part in co_participations.items():
        if co_part > 0:
            val = matrix[i, j] / co_part
            matrix[i, j] = val
            matrix[j, i] = val

    # Diagonal = 1.0 (cada legislador co-vota perfectamente consigo mismo)
    np.fill_diagonal(matrix, 1.0)

    logger.info(
        "Matriz construida: %dx%d, %.0f pares con co-participación",
        n,
        n,
        len(co_participations) - n,  # sin diagonal
    )

    return matrix, legislators, co_participations


# ---------------------------------------------------------------------------
# Función 5: build_graph
# ---------------------------------------------------------------------------
def build_graph(
    matrix: np.ndarray,
    legislators: list[str],
    party_map: dict[str, str],
    persons_df: pd.DataFrame,
) -> nx.Graph:
    """Construir grafo de networkx a partir de la matriz de co-votación.

    Nodos: cada legislador con atributos nombre, party_id, party_name.
    Aristas: solo si peso > 0, con atributo weight = co-votación.

    Args:
        matrix: numpy array NxN de co-votación.
        legislators: lista ordenada de voter_ids (mismo orden que matrix).
        party_map: dict voter_id → party_id (partido principal).
        persons_df: DataFrame con columnas [id, nombre, genero].

    Returns:
        networkx.Graph con nodos y aristas con atributos.
    """
    # Lookup de nombres
    name_lookup = dict(zip(persons_df["id"], persons_df["nombre"]))

    G = nx.Graph()

    # Agregar nodos
    for idx, leg_id in enumerate(legislators):
        pid = party_map.get(leg_id, "O11")
        G.add_node(
            leg_id,
            nombre=name_lookup.get(leg_id, leg_id),
            party_id=pid,
            party_name=_ORG_ID_TO_NAME.get(pid, pid),
        )

    # Agregar aristas (solo si peso > 0, sin diagonal)
    n = len(legislators)
    for i in range(n):
        for j in range(i + 1, n):
            w = matrix[i, j]
            if w > 0:
                G.add_edge(legislators[i], legislators[j], weight=w)

    logger.info(
        "Grafo construido: %d nodos, %d aristas",
        G.number_of_nodes(),
        G.number_of_edges(),
    )

    return G


# ---------------------------------------------------------------------------
# Función 6: compute_quantitative_metrics
# ---------------------------------------------------------------------------
def compute_quantitative_metrics(
    graph: nx.Graph,
    party_map: dict[str, str],
    org_map: dict[str, str],
) -> dict:
    """Calcular métricas cuantitativas del grafo de co-votación.

    Produce 10 métricas:
    1. weight_distribution: lista de pesos de aristas.
    2. density: densidad del grafo.
    3. intra_party_avg: dict party_id → promedio intra-partido.
    4. inter_party_avg: dict (party_id_i, party_id_j) → promedio inter-partido.
    5. top20_cross_party: top 20 pares con mayor co-votación inter-partido.
    6. bottom20_same_party: bottom 20 pares con menor co-votación intra-partido.
    7. party_matrix: DataFrame partido × partido con co-votación promedio.
    8. num_legislators: número de nodos.
    9. num_edges: número de aristas.
    10. avg_weight: peso promedio de aristas.

    Args:
        graph: networkx.Graph con atributos weight en aristas y party_id en nodos.
        party_map: dict voter_id → party_id (partido principal).
        org_map: dict org_id → org_nombre.

    Returns:
        Dict con las 10 métricas listadas.
    """
    # 1. Distribución de pesos
    weights = [d["weight"] for _, _, d in graph.edges(data=True)]

    # 2. Densidad
    density = nx.density(graph)

    # Preparar estructuras por partido
    party_edges: dict[str, list[float]] = {}
    cross_edges: dict[tuple[str, str], list[float]] = {}

    for u, v, data in graph.edges(data=True):
        w = data["weight"]
        pu = party_map.get(u, "O11")
        pv = party_map.get(v, "O11")

        if pu == pv:
            party_edges.setdefault(pu, []).append(w)
        else:
            key = tuple(sorted([pu, pv]))
            cross_edges.setdefault(key, []).append(w)

    # 3. Promedio intra-partido
    intra_party_avg: dict[str, float] = {}
    for pid, ws in party_edges.items():
        intra_party_avg[pid] = sum(ws) / len(ws) if ws else 0.0

    # 4. Promedio inter-partido
    inter_party_avg: dict[tuple[str, str], float] = {}
    for key, ws in cross_edges.items():
        inter_party_avg[key] = sum(ws) / len(ws) if ws else 0.0

    # 5. Top 20 pares cross-party (mayor co-votación)
    cross_pairs = []
    for u, v, data in graph.edges(data=True):
        pu = party_map.get(u, "O11")
        pv = party_map.get(v, "O11")
        if pu != pv:
            cross_pairs.append(
                {
                    "legislator_a": u,
                    "name_a": graph.nodes[u].get("nombre", u),
                    "party_a": org_map.get(pu, pu),
                    "party_a_id": pu,
                    "legislator_b": v,
                    "name_b": graph.nodes[v].get("nombre", v),
                    "party_b": org_map.get(pv, pv),
                    "party_b_id": pv,
                    "weight": data["weight"],
                }
            )
    cross_pairs.sort(key=lambda x: x["weight"], reverse=True)
    top20_cross_party = cross_pairs[:20]

    # 6. Bottom 20 pares same-party (menor co-votación)
    same_pairs = []
    for u, v, data in graph.edges(data=True):
        pu = party_map.get(u, "O11")
        pv = party_map.get(v, "O11")
        if pu == pv:
            same_pairs.append(
                {
                    "legislator_a": u,
                    "name_a": graph.nodes[u].get("nombre", u),
                    "party_a": org_map.get(pu, pu),
                    "party_a_id": pu,
                    "legislator_b": v,
                    "name_b": graph.nodes[v].get("nombre", v),
                    "party_b": org_map.get(pv, pv),
                    "party_b_id": pv,
                    "weight": data["weight"],
                }
            )
    same_pairs.sort(key=lambda x: x["weight"])
    bottom20_same_party = same_pairs[:20]

    # 7. Matriz partido × partido
    # Recopilar todos los partidos presentes en el grafo
    parties_in_graph = sorted(set(party_map.get(n, "O11") for n in graph.nodes()))

    party_matrix_data: dict[tuple[str, str], list[float]] = {}
    for u, v, data in graph.edges(data=True):
        pu = party_map.get(u, "O11")
        pv = party_map.get(v, "O11")
        key = (pu, pv)
        party_matrix_data.setdefault(key, []).append(data["weight"])
        if pu != pv:
            key_rev = (pv, pu)
            party_matrix_data.setdefault(key_rev, []).append(data["weight"])

    # Construir DataFrame
    mat_dict: dict[str, dict[str, float]] = {}
    for pi in parties_in_graph:
        row: dict[str, float] = {}
        for pj in parties_in_graph:
            if pi == pj:
                row[pj] = intra_party_avg.get(pi, 0.0)
            else:
                key = (pi, pj)
                vals = party_matrix_data.get(key, [])
                row[pj] = sum(vals) / len(vals) if vals else 0.0
        mat_dict[pi] = row

    party_matrix = pd.DataFrame(mat_dict).T
    # Renombrar índices y columnas con nombres de partido
    party_names = {pid: org_map.get(pid, pid) for pid in parties_in_graph}
    party_matrix.index = [party_names.get(p, p) for p in party_matrix.index]
    party_matrix.columns = [party_names.get(p, p) for p in party_matrix.columns]

    # 8-10. Métricas básicas
    num_legislators = graph.number_of_nodes()
    num_edges = graph.number_of_edges()
    avg_weight = sum(weights) / len(weights) if weights else 0.0

    # 11. Party sizes (legisladores por partido)
    party_sizes: dict[str, int] = {}
    for n_id in graph.nodes():
        pid = party_map.get(n_id, "O11")
        party_sizes[pid] = party_sizes.get(pid, 0) + 1

    return {
        "weight_distribution": weights,
        "density": density,
        "intra_party_avg": intra_party_avg,
        "inter_party_avg": inter_party_avg,
        "top20_cross_party": top20_cross_party,
        "bottom20_same_party": bottom20_same_party,
        "party_matrix": party_matrix,
        "party_sizes": party_sizes,
        "org_map": org_map,
        "num_legislators": num_legislators,
        "num_edges": num_edges,
        "avg_weight": avg_weight,
    }
