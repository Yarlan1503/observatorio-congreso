"""
centralidad.py — Métricas de centralidad para grafos de co-votación.

Recibe un grafo de networkx (construido por covotacion.py) y calcula
métricas de centralidad: weighted degree y betweenness.

Los pesos del grafo representan SIMILITUD (mayor peso = más co-votación),
por lo que:
- Degree centrality usa pesos (weighted degree normalizado).
- Betweenness se calcula sin pesos (weight=None), porque los pesos de
  co-votación no son distancias geodésicas.
"""

import logging

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)


def compute_degree_centrality(graph: nx.Graph) -> dict[str, float]:
    """Calcula degree centrality ponderada y normalizada.

    Usa weighted degree: suma de pesos de todas las aristas de cada nodo,
    normalizada dividiendo entre el máximo weighted degree observado.

    A diferencia de nx.degree_centrality() (que cuenta aristas),
    esta métrica refleja la intensidad total de co-votación de cada
    legislador.

    Args:
        graph: Grafo de networkx con pesos en aristas (atributo 'weight').

    Returns:
        Dict node_id → weighted_degree_normalized (0.0 a 1.0).
    """
    logger.info(f"Calculando weighted degree centrality ({graph.number_of_nodes()} nodos)")

    # Weighted degree: suma de pesos de aristas por nodo
    weighted_degrees: dict[str, float] = dict(graph.degree(weight="weight"))

    if not weighted_degrees:
        logger.warning("Grafo vacío, retornando dict vacío")
        return {}

    # Normalizar entre el máximo weighted degree
    max_wd = max(weighted_degrees.values())
    if max_wd == 0:
        logger.warning("Todos los weighted degrees son 0, normalización a 0.0")
        return {node: 0.0 for node in weighted_degrees}

    normalized = {node: wd / max_wd for node, wd in weighted_degrees.items()}

    logger.info(
        f"Weighted degree calculado: max={max_wd:.2f}, "
        f"nodos con centralidad > 0.5: "
        f"{sum(1 for v in normalized.values() if v > 0.5)}"
    )

    return normalized


def compute_betweenness_centrality(graph: nx.Graph) -> dict[str, float]:
    """Calcula betweenness centrality sin pesos.

    Usa weight=None porque los pesos del grafo de co-votación representan
    SIMILITUD, no distancia. Un peso alto significa "votan parecido", no
    "están lejos". Usar pesos directamente invertiría la interpretación
    geodésica. La opción correcta es contar saltos (unweighted).

    Args:
        graph: Grafo de networkx.

    Returns:
        Dict node_id → betweenness_centrality_value (0.0 a 1.0).
    """
    logger.info(f"Calculando betweenness centrality unweighted ({graph.number_of_nodes()} nodos)")

    betweenness = nx.betweenness_centrality(graph, weight=None)

    top_betweenness = max(betweenness.values()) if betweenness else 0.0
    logger.info(
        f"Betweenness calculado: max={top_betweenness:.4f}, "
        f"nodos con betweenness > 0.1: "
        f"{sum(1 for v in betweenness.values() if v > 0.1)}"
    )

    return betweenness


def compute_all_centrality(graph: nx.Graph) -> dict[str, dict]:
    """Calcula todas las métricas de centralidad disponibles.

    Actualmente calcula:
    - Weighted degree centrality (normalizada)
    - Betweenness centrality (unweighted)

    Args:
        graph: Grafo de networkx con pesos en aristas.

    Returns:
        Dict con estructura:
        {
            'degree': {node_id: value, ...},
            'betweenness': {node_id: value, ...}
        }
    """
    logger.info(
        f"Calculando todas las métricas de centralidad para {graph.number_of_nodes()} nodos"
    )

    result: dict[str, dict] = {
        "degree": compute_degree_centrality(graph),
        "betweenness": compute_betweenness_centrality(graph),
    }

    logger.info("Métricas de centralidad completadas")
    return result


def top_n_centrality(
    centrality_dict: dict[str, float],
    persons_df: pd.DataFrame,
    party_map: dict[str, str],
    org_map: dict[str, str],
    n: int = 10,
) -> list[dict]:
    """Retorna los N legisladores con mayor centralidad.

    Toma un dict de centralidad (cualquier métrica) y produce un ranking
    de legisladores con nombre, partido y score.

    Args:
        centrality_dict: Dict node_id → score de centralidad.
        persons_df: DataFrame con columnas 'id' y 'nombre'.
        party_map: Dict voter_id → party_id (ej. 'P01' → 'O01').
        org_map: Dict party_id → party_name (ej. 'O01' → 'Morena').
        n: Número de legisladores a retornar (default 10).

    Returns:
        Lista de dicts ordenada de mayor a menor score:
        [
            {'rank': 1, 'legislator_id': 'P01', 'nombre': '...', 'partido': 'Morena', 'score': 0.95},
            ...
        ]
    """
    logger.info(f"Obteniendo top {n} legisladores por centralidad")

    # Construir lookup de nombre: id → nombre
    name_lookup: dict[str, str] = {}
    if "id" in persons_df.columns and "nombre" in persons_df.columns:
        for _, row in persons_df.iterrows():
            name_lookup[str(row["id"])] = str(row["nombre"])

    # Ordenar por score descendente
    sorted_nodes = sorted(centrality_dict.items(), key=lambda x: x[1], reverse=True)

    result: list[dict] = []
    for rank, (node_id, score) in enumerate(sorted_nodes[:n], start=1):
        # Resolver partido: node_id → party_id → party_name
        party_id = party_map.get(node_id, "")
        party_name = org_map.get(party_id, "Sin partido") if party_id else "Sin partido"

        result.append(
            {
                "rank": rank,
                "legislator_id": node_id,
                "nombre": name_lookup.get(node_id, node_id),
                "partido": party_name,
                "score": round(score, 6),
            }
        )

    logger.info(
        f"Top {n}: {result[0]['nombre']} ({result[0]['partido']}) lidera con {result[0]['score']:.4f}"
    )
    return result


def add_centrality_to_graph(graph: nx.Graph, centrality: dict[str, dict]) -> nx.Graph:
    """Añade atributos de centralidad a los nodos del grafo.

    Modifica el grafo in-place agregando 'degree_centrality' y
    'betweenness_centrality' como atributos de cada nodo. Preserva
    todos los atributos existentes.

    Args:
        graph: Grafo de networkx a modificar.
        centrality: Dict con estructura de compute_all_centrality():
            {
                'degree': {node_id: value, ...},
                'betweenness': {node_id: value, ...}
            }

    Returns:
        El mismo grafo modificado (mutado in-place).
    """
    degree = centrality.get("degree", {})
    betweenness = centrality.get("betweenness", {})

    nodes_updated = 0
    for node in graph.nodes():
        if node in degree:
            graph.nodes[node]["degree_centrality"] = degree[node]
            nodes_updated += 1
        if node in betweenness:
            graph.nodes[node]["betweenness_centrality"] = betweenness[node]

    logger.info(
        f"Atributos de centralidad añadidos a {nodes_updated} nodos "
        f"de {graph.number_of_nodes()} totales"
    )

    return graph
