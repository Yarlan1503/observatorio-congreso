"""
visualizacion.py — Generación de visualizaciones del grafo de co-votación legislativa.

Produce grafos de legisladores, grafos de partidos, histogramas de pesos
y exporta el grafo en formato GraphML para análisis externo.
"""

import networkx as nx
import matplotlib

matplotlib.use("Agg")  # Sin display — backend no interactivo
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional


# --- Esquema de colores por partido ---

PARTY_COLORS: dict[str, str] = {
    "MORENA": "#8B0000",  # rojo oscuro
    "PT": "#FF6600",  # naranja
    "PVEM": "#228B22",  # verde
    "PAN": "#003399",  # azul
    "PRI": "#008833",  # verde PRI
    "MC": "#FF8C00",  # naranja MC
    "PRD": "#FFD700",  # amarillo
    "Independientes": "#808080",  # gris
}

DEFAULT_COLOR: str = "#CCCCCC"


def _get_party_color(party_name: Optional[str]) -> str:
    """Retorna el color asociado a un partido.

    Args:
        party_name: Nombre del partido (atributo ``party_name`` del nodo).

    Returns:
        Hex color del partido o color por defecto.
    """
    if party_name is None:
        return DEFAULT_COLOR
    return PARTY_COLORS.get(party_name, DEFAULT_COLOR)


# ---------------------------------------------------------------------------
# Función 1: Grafo principal de legisladores
# ---------------------------------------------------------------------------


def plot_main_graph(
    graph: nx.Graph,
    output_dir: str,
    weight_percentile: float = 75.0,
) -> str:
    """Genera el grafo principal de co-votación entre legisladores.

    Nodos = legisladores coloreados por partido. Aristas filtradas al
    percentil indicado de peso. Tamaño de nodo proporcional a
    ``degree_centrality``.

    Args:
        graph: Grafo de NetworkX con nodos (legisladores) y aristas
            ponderadas por co-votación.
        output_dir: Directorio donde guardar el PNG.
        weight_percentile: Percentil mínimo de peso para filtrar aristas.
            Por defecto 75.0.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # --- Filtrar aristas por percentil ---
    all_weights = [d["weight"] for _, _, d in graph.edges(data=True)]
    if not all_weights:
        # Sin aristas, grafo vacío
        fig, ax = plt.subplots(figsize=(14, 14))
        ax.set_title("Red de Co-votación - LXVI Legislatura (Periodo 1)")
        filepath = output_path / "grafo_covotacion.png"
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return str(filepath.resolve())

    threshold = float(np.percentile(all_weights, weight_percentile))

    # Construir lista de aristas que pasan el umbral
    filtered_edges = [
        (u, v, d)
        for u, v, d in graph.edges(data=True)
        if d.get("weight", 0) >= threshold
    ]

    # Crear subgrafo solo con las aristas filtradas (mantiene nodos aislados)
    sub = nx.Graph()
    sub.add_nodes_from(graph.nodes(data=True))
    sub.add_edges_from(filtered_edges)

    # Tomar solo la componente conexa más grande si hay demasiados nodos
    # para que el layout sea computable
    if sub.number_of_nodes() > 200 and not nx.is_connected(sub):
        components = list(nx.connected_components(sub))
        largest = max(components, key=len)
        sub = sub.subgraph(largest).copy()

    # --- Layout ---
    pos = nx.spring_layout(sub, seed=42, k=0.1, iterations=50)

    # --- Colores y tamaños de nodo ---
    node_colors = [
        _get_party_color(sub.nodes[n].get("party_name")) for n in sub.nodes()
    ]

    # Tamaño proporcional a degree_centrality
    centralities = [sub.nodes[n].get("degree_centrality", 0.0) for n in sub.nodes()]
    max_centrality = (
        max(centralities) if centralities and max(centralities) > 0 else 1.0
    )
    node_sizes = [50 + 450 * (c / max_centrality) for c in centralities]

    # --- Labels ---
    labels: dict[str, str] = {}
    for n, data in sub.nodes(data=True):
        label_parts: list[str] = []
        name = data.get("name", data.get("nombre", n))
        if name:
            label_parts.append(str(name))
        community = data.get("community")
        if community is not None:
            label_parts.append(f"C{community}")
        labels[n] = "\n".join(label_parts) if label_parts else str(n)

    # --- Dibujar ---
    fig, ax = plt.subplots(figsize=(14, 14))

    nx.draw_networkx_edges(
        sub,
        pos,
        ax=ax,
        alpha=0.3,
        width=0.5,
        edge_color="#999999",
    )

    nx.draw_networkx_nodes(
        sub,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.85,
        edgecolors="white",
        linewidths=0.3,
    )

    nx.draw_networkx_labels(
        sub,
        pos,
        labels,
        ax=ax,
        font_size=4,
        font_color="black",
    )

    ax.set_title("Red de Co-votación - LXVI Legislatura (Periodo 1)", fontsize=14)
    ax.axis("off")
    plt.tight_layout()

    filepath = output_path / "grafo_covotacion.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 2: Grafo de partidos
# ---------------------------------------------------------------------------


def plot_party_graph(
    party_matrix: pd.DataFrame,
    party_sizes: dict[str, int],
    org_map: dict[str, str],
    output_dir: str,
) -> str:
    """Genera el grafo de co-votación promedio entre partidos.

    Nodos = partidos legislativos. Aristas = co-votación promedio.
    Tamaño de nodo proporcional a escaños. Grosor de arista proporcional
    al peso de co-votación.

    Args:
        party_matrix: DataFrame indexado por party_id con columnas
            party_id. Valores = co-votación promedio.
        party_sizes: Diccionario party_id → número de escaños.
        org_map: Diccionario party_id → nombre legible del partido.
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # IDs de partidos legislativos (O01-O07, O11)
    valid_prefixes = {"O01", "O02", "O03", "O04", "O05", "O06", "O07", "O11"}
    party_ids = [pid for pid in party_matrix.index if pid in valid_prefixes]

    if not party_ids:
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.set_title("Co-votación Promedio entre Partidos - LXVI Legislatura")
        filepath = output_path / "grafo_partidos.png"
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return str(filepath.resolve())

    # Sub-matriz de co-votación
    sub_matrix = party_matrix.loc[party_ids, party_ids]

    # --- Construir grafo de partidos ---
    G = nx.Graph()
    for pid in party_ids:
        name = org_map.get(pid, pid)
        G.add_node(pid, name=name, size=party_sizes.get(pid, 1))

    for i, pid_i in enumerate(party_ids):
        for j, pid_j in enumerate(party_ids):
            if i < j:
                weight = sub_matrix.loc[pid_i, pid_j]
                if pd.notna(weight):
                    G.add_edge(pid_i, pid_j, weight=float(weight))

    # --- Layout ---
    if len(party_ids) <= 10:
        pos = nx.circular_layout(G)
    else:
        pos = nx.spring_layout(G, seed=42)

    # --- Colores y tamaños ---
    node_colors = [_get_party_color(org_map.get(pid)) for pid in G.nodes()]

    sizes = [party_sizes.get(pid, 1) for pid in G.nodes()]
    max_size = max(sizes) if sizes and max(sizes) > 0 else 1
    node_sizes = [200 + 2800 * (s / max_size) for s in sizes]

    # --- Grosor de aristas proporcional al peso ---
    weights_list = [d["weight"] for _, _, d in G.edges(data=True)]
    if weights_list:
        min_w = min(weights_list)
        max_w = max(weights_list)
        range_w = max_w - min_w if max_w != min_w else 1.0
    else:
        min_w, max_w, range_w = 0, 1, 1

    edge_widths = [
        0.5 + 4.5 * ((d["weight"] - min_w) / range_w) for _, _, d in G.edges(data=True)
    ]

    # Labels de nodos
    node_labels = {pid: org_map.get(pid, pid) for pid in G.nodes()}

    # Labels de aristas (peso de co-votación)
    edge_labels = {(u, v): f"{d['weight']:.2f}" for u, v, d in G.edges(data=True)}

    # --- Dibujar ---
    fig, ax = plt.subplots(figsize=(12, 10))

    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        width=edge_widths,
        alpha=0.5,
        edge_color="#666666",
    )

    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.9,
        edgecolors="white",
        linewidths=1.5,
    )

    nx.draw_networkx_labels(
        G,
        pos,
        node_labels,
        ax=ax,
        font_size=9,
        font_weight="bold",
        font_color="white",
    )

    nx.draw_networkx_edge_labels(
        G,
        pos,
        edge_labels,
        ax=ax,
        font_size=7,
        font_color="#333333",
    )

    ax.set_title(
        "Co-votación Promedio entre Partidos - LXVI Legislatura",
        fontsize=14,
    )
    ax.axis("off")
    plt.tight_layout()

    filepath = output_path / "grafo_partidos.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 3: Histograma de distribución de pesos
# ---------------------------------------------------------------------------


def plot_weight_distribution(
    weights: list[float],
    output_dir: str,
) -> str:
    """Genera un histograma de la distribución de pesos de co-votación.

    Muestra la frecuencia de los pesos con una línea vertical en el
    percentil 75.

    Args:
        weights: Lista de todos los valores de co-votación (pesos de
            aristas).
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.hist(weights, bins=50, color="#4682B4", edgecolor="white", alpha=0.85)

    # Línea vertical en percentil 75
    p75 = float(np.percentile(weights, 75))
    ax.axvline(
        p75,
        color="#DC143C",
        linestyle="--",
        linewidth=1.5,
        label=f"Percentil 75 = {p75:.3f}",
    )

    ax.set_title("Distribución de Pesos de Co-votación", fontsize=13)
    ax.set_xlabel("Co-votación (similitud normalizada)", fontsize=11)
    ax.set_ylabel("Frecuencia", fontsize=11)
    ax.legend(fontsize=10)
    plt.tight_layout()

    filepath = output_path / "histograma_pesos.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 4: Exportar grafo a GraphML
# ---------------------------------------------------------------------------


def save_graphml(
    graph: nx.Graph,
    output_dir: str,
) -> str:
    """Guarda el grafo completo en formato GraphML.

    Convierte atributos ``None`` a cadenas vacías para cumplir con
    el requisito de tipos básicos de GraphML.

    Args:
        graph: Grafo de NetworkX con atributos de nodo y arista.
        output_dir: Directorio donde guardar el archivo.

    Returns:
        Ruta absoluta del archivo ``.graphml`` generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Atributos de nodo a exportar
    node_attrs = [
        "name",
        "nombre",
        "party_id",
        "party_name",
        "community",
        "degree_centrality",
        "betweenness_centrality",
    ]

    # Limpiar atributos None → cadena vacía (GraphML requiere tipos básicos)
    clean = graph.copy()
    for n, data in clean.nodes(data=True):
        for attr in node_attrs:
            val = data.get(attr)
            if val is None:
                data[attr] = ""
            elif not isinstance(val, (str, int, float)):
                data[attr] = str(val)

    # Limpiar atributos de arista
    for _, _, data in clean.edges(data=True):
        for key, val in data.items():
            if val is None:
                data[key] = ""
            elif not isinstance(val, (str, int, float)):
                data[key] = str(val)

    filepath = output_path / "grafo_covotacion.graphml"
    nx.write_graphml(clean, str(filepath))

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 5: Orquestador de visualizaciones
# ---------------------------------------------------------------------------


def generate_all_visualizations(
    graph: nx.Graph,
    metrics: dict,
    output_dir: str,
) -> dict[str, str]:
    """Orquesta la generación de todas las visualizaciones.

    Genera: histograma de pesos, grafo principal, grafo de partidos
    y exportación GraphML.

    Args:
        graph: Grafo de co-votación con nodos y aristas ponderadas.
        metrics: Diccionario retornado por
            ``covotacion.compute_quantitative_metrics``. Debe contener
            ``weight_distribution``, ``party_matrix``, ``party_sizes``
            y ``org_map``.
        output_dir: Directorio base donde guardar todos los archivos.

    Returns:
        Diccionario ``{nombre_visualización → ruta_archivo}`` con las
        rutas de todos los archivos generados.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    # 1. Extraer pesos de aristas
    weights = [d["weight"] for _, _, d in graph.edges(data=True)]

    # 2. Histograma de distribución de pesos
    if weights:
        results["histograma_pesos"] = plot_weight_distribution(weights, output_dir)

    # 3. Grafo principal de legisladores
    results["grafo_covotacion"] = plot_main_graph(graph, output_dir)

    # 4. Grafo de partidos (si hay datos en metrics)
    party_matrix = metrics.get("party_matrix")
    party_sizes = metrics.get("party_sizes")
    org_map = metrics.get("org_map")
    if party_matrix is not None and party_sizes is not None and org_map is not None:
        results["grafo_partidos"] = plot_party_graph(
            party_matrix,
            party_sizes,
            org_map,
            output_dir,
        )

    # 5. Exportar GraphML
    results["graphml"] = save_graphml(graph, output_dir)

    return results
