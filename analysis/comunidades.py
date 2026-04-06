"""
Detección de comunidades legislativas vía algoritmo de Louvain.

Recibe un grafo de co-votación (construido por covotacion.py) y detecta
comunidades de legisladores que votan de forma similar. Luego analiza
la composición partidista de cada comunidad para identificar bloques
de poder y legisladores cruzados.

Dependencias:
    - networkx
    - python-louvain (community)
    - pandas
"""

from collections import Counter

import community
import networkx as nx


def detect_communities(
    graph: nx.Graph,
    resolution: float = 1.0,
) -> dict[str, int]:
    """
    Detecta comunidades en un grafo de co-votación usando Louvain.

    Aplica el algoritmo de Louvain (python-louvain) para encontrar
    la partición que maximiza la modularidad del grafo.

    Args:
        graph: Grafo de networkx con pesos en aristas (atributo 'weight').
        resolution: Parámetro de resolución del algoritmo. Valores > 1.0
                    producen comunidades más pequeñas; < 1.0, más grandes.

    Returns:
        Diccionario node_id → community_id (entero desde 0).
        Todos los nodos del grafo están presentes en el resultado.
    """
    print(f"[comunidades] Detectando comunidades con resolution={resolution}")
    print(
        f"[comunidades] Grafo de entrada: {graph.number_of_nodes()} nodos, "
        f"{graph.number_of_edges()} aristas"
    )

    partition: dict[str, int] = community.best_partition(
        graph,
        resolution=resolution,
        weight="weight",
    )

    num_communities = len(set(partition.values()))
    print(
        f"[comunidades] Partición obtenida: {len(partition)} nodos en {num_communities} comunidades"
    )

    # Verificar que todos los nodos del grafo están en la partición
    graph_nodes = set(graph.nodes())
    partition_nodes = set(partition.keys())
    missing = graph_nodes - partition_nodes
    if missing:
        print(
            f"[comunidades] ADVERTENCIA: {len(missing)} nodos del grafo "
            f"no están en la partición: {missing}"
        )

    return partition


def analyze_communities(
    graph: nx.Graph,
    partition: dict[str, int],
    party_map: dict[str, str],
    org_map: dict[str, str],
) -> dict:
    """
    Analiza las comunidades detectadas y su composición partidista.

    Calcula métricas de composición, pureza partidista, legisladores
    cruzados y sub-bloques internos de MORENA.

    Args:
        graph: Grafo original de co-votación.
        partition: Diccionario node_id → community_id (de detect_communities).
        party_map: Diccionario voter_id → party_id
                   (ej: {'P100': 'O01', 'P200': 'O04'}).
        org_map: Diccionario party_id → party_name
                 (ej: {'O01': 'Morena', 'O04': 'PAN'}).

    Returns:
        Diccionario con 7 campos:
        - num_communities (int): número total de comunidades.
        - community_sizes (dict): community_id → tamaño.
        - community_composition (dict): community_id → {party_name: count}.
        - community_party_purity (dict): community_id → proporción partido dominante.
        - cross_party_legislators (list): legisladores fuera de su comunidad esperada.
        - sub_blocks_morena (list): sub-bloques MORENA en múltiples comunidades.
        - modularity (float): modularidad del particionamiento.
    """
    print("[comunidades] Analizando composición de comunidades...")

    # 1. Número total de comunidades
    community_ids = set(partition.values())
    num_communities = len(community_ids)
    print(f"[comunidades] {num_communities} comunidades detectadas")

    # 2. Tamaño de cada comunidad
    community_sizes: dict[int, int] = dict(Counter(partition.values()))
    print(f"[comunidades] Tamaños: {dict(sorted(community_sizes.items()))}")

    # 3. Composición partidista por comunidad
    community_composition: dict[int, dict[str, int]] = {cid: {} for cid in community_ids}
    for node_id, cid in partition.items():
        party_id = party_map.get(node_id)
        if party_id is None:
            party_name = "Sin partido"
        else:
            party_name = org_map.get(party_id, f"Desconocido({party_id})")

        if party_name not in community_composition[cid]:
            community_composition[cid][party_name] = 0
        community_composition[cid][party_name] += 1

    # 4. Pureza partidista (proporción del partido dominante)
    community_party_purity: dict[int, float] = {}
    # También guardar el partido dominante por comunidad para uso posterior
    dominant_party: dict[int, str] = {}

    for cid in community_ids:
        composition = community_composition[cid]
        total = community_sizes[cid]
        if composition:
            top_party, top_count = max(composition.items(), key=lambda x: x[1])
            purity = top_count / total if total > 0 else 0.0
        else:
            top_party = "N/A"
            purity = 0.0
        community_party_purity[cid] = purity
        dominant_party[cid] = top_party

    print(f"[comunidades] Pureza por comunidad: {dict(sorted(community_party_purity.items()))}")

    # 5. Legisladores cruzados (en comunidad donde su partido NO es dominante)
    cross_party_legislators: list[dict] = []
    for node_id, cid in partition.items():
        party_id = party_map.get(node_id)
        if party_id is None:
            own_party = "Sin partido"
        else:
            own_party = org_map.get(party_id, f"Desconocido({party_id})")

        dom_party = dominant_party[cid]
        if own_party != dom_party:
            cross_party_legislators.append(
                {
                    "legislator_id": node_id,
                    "name": node_id,  # Se puede mejorar si hay name_map
                    "own_party": own_party,
                    "community_id": cid,
                    "dominant_party": dom_party,
                    "dominant_party_proportion": community_party_purity[cid],
                }
            )

    print(
        f"[comunidades] {len(cross_party_legislators)} legisladores "
        f"cruzados (fuera de su comunidad partidista dominante)"
    )

    # 6. Sub-bloques de MORENA (comunidades con ≥5 legisladores MORENA)
    sub_blocks_morena: list[dict] = []
    morena_name_variants = {"morena", "Morena", "MORENA"}

    for cid in community_ids:
        composition = community_composition[cid]
        # Buscar MORENA con cualquier casing
        morena_count = 0
        for party_name, count in composition.items():
            if party_name in morena_name_variants:
                morena_count = count
                break

        if morena_count >= 5:
            sub_blocks_morena.append(
                {
                    "community_id": cid,
                    "size": morena_count,
                    "proportion_of_morena": morena_count / community_sizes[cid]
                    if community_sizes[cid] > 0
                    else 0.0,
                }
            )

    # Ordenar por tamaño descendente
    sub_blocks_morena.sort(key=lambda x: x["size"], reverse=True)
    print(
        f"[comunidades] {len(sub_blocks_morena)} sub-bloques MORENA "
        f"(≥5 legisladores): {sub_blocks_morena}"
    )

    # 7. Modularidad del particionamiento
    modularity_value: float = community.modularity(partition, graph, weight="weight")
    print(f"[comunidades] Modularidad: {modularity_value:.4f}")

    return {
        "num_communities": num_communities,
        "community_sizes": community_sizes,
        "community_composition": community_composition,
        "community_party_purity": community_party_purity,
        "cross_party_legislators": cross_party_legislators,
        "sub_blocks_morena": sub_blocks_morena,
        "modularity": modularity_value,
    }


def get_partition_as_attribute(
    graph: nx.Graph,
    partition: dict[str, int],
) -> nx.Graph:
    """
    Añade el atributo 'community' a cada nodo del grafo.

    Modifica el grafo in-place añadiendo el atributo 'community' a cada
    nodo según la partición proporcionada. Retorna el mismo objeto grafo.

    Args:
        graph: Grafo de networkx a modificar.
        partition: Diccionario node_id → community_id.

    Returns:
        El mismo objeto grafo, mutado con el atributo 'community' en cada nodo.
    """
    nx.set_node_attributes(graph, partition, "community")
    print(f"[comunidades] Atributo 'community' asignado a {len(partition)} nodos del grafo")
    return graph
