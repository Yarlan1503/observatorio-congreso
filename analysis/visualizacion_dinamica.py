#!/usr/bin/env python3
"""
visualizacion_dinamica.py — Visualizaciones para grafos dinámicos cross-legislatura.

Genera timelines, heatmaps y grafos individuales por ventana temporal
para analizar la evolución de la co-votación legislativa entre legislaturas.
"""

import logging
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Sin display — backend no interactivo
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from analysis.visualizacion import PARTY_COLORS

logger = logging.getLogger(__name__)

# Mapeo org_id → nombre corto (consistente con PARTY_COLORS)
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

# Orden canónico de partidos para visualizaciones
_PARTY_ORDER: list[str] = ["MORENA", "PT", "PVEM", "PRI", "PAN", "MC", "PRD"]


def _get_party_color(party_name: str) -> str:
    """Color de partido con fallback gris."""
    return PARTY_COLORS.get(party_name, "#CCCCCC")


def _sanitize_label(label: str) -> str:
    """Sanitizar label para uso como nombre de archivo."""
    return re.sub(r"[\s()]+", "_", label).strip("_")


# ---------------------------------------------------------------------------
# Función 1: Timeline de disciplina partidista
# ---------------------------------------------------------------------------


def plot_disciplina_timeline(evolution: dict, output_dir: str) -> str:
    """Líneas de tiempo: disciplina por partido a lo largo de legislaturas/ventanas.

    Args:
        evolution: Dict de compute_evolution_metrics (clave 'disciplina_por_ventana').
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo timeline_disciplina.png.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    disciplina = evolution.get("disciplina_por_ventana", {})
    if not disciplina:
        raise ValueError("Sin datos de disciplina por ventana")

    # Ventanas ordenadas por aparición (ya vienen ordenadas cronológicamente)
    ventanas = list(disciplina.keys())
    n_ventanas = len(ventanas)

    # Recopilar todos los partidos presentes
    all_parties: set[str] = set()
    for period_data in disciplina.values():
        all_parties.update(period_data.keys())

    # Orden canónico
    parties = [p for p in _PARTY_ORDER if p in all_parties]
    # Añadir partidos extra que no estén en el orden canónico
    parties.extend(sorted(all_parties - set(_PARTY_ORDER)))

    fig, ax = plt.subplots(figsize=(max(10, n_ventanas * 2), 6))

    for party in parties:
        values = [disciplina.get(v, {}).get(party, np.nan) for v in ventanas]
        # Solo plotear si hay al menos un valor válido
        valid = [(i, val) for i, val in enumerate(values) if not np.isnan(val)]
        if not valid:
            continue

        color = _get_party_color(party)
        valid_indices = [v[0] for v in valid]
        valid_values = [v[1] for v in valid]
        valid_ventanas = [ventanas[i] for i in valid_indices]

        ax.plot(
            valid_ventanas,
            valid_values,
            "o-",
            color=color,
            linewidth=2,
            markersize=6,
            label=party,
        )

    ax.set_xlabel("Legislatura", fontsize=11)
    ax.set_ylabel("Co-votación Intra-partido", fontsize=11)
    ax.set_title("Evolución de Disciplina Partidista por Legislatura", fontsize=13)
    ax.tick_params(axis="x", rotation=30)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="best", fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    filepath = output_path / "timeline_disciplina.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 2: Timeline de modularidad y densidad
# ---------------------------------------------------------------------------


def plot_modularidad_timeline(evolution: dict, output_dir: str) -> str:
    """Línea de tiempo de modularidad y densidad por legislatura.

    Args:
        evolution: Dict de compute_evolution_metrics
            (claves 'modularidad_por_ventana' y 'densidad_por_ventana').
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo timeline_modularidad.png.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    mod = evolution.get("modularidad_por_ventana", {})
    dens = evolution.get("densidad_por_ventana", {})

    if not mod:
        raise ValueError("Sin datos de modularidad por ventana")

    ventanas = list(mod.keys())
    n_ventanas = len(ventanas)

    fig, ax1 = plt.subplots(figsize=(max(10, n_ventanas * 2), 6))

    # Modularidad (eje izquierdo) — línea sólida con marcadores 'o'
    mod_values = [mod[v] for v in ventanas]
    ax1.plot(
        ventanas,
        mod_values,
        "o-",
        color="#2C3E50",
        linewidth=2,
        markersize=8,
        label="Modularidad",
    )

    # Anotar valores sobre cada punto
    for i, v in enumerate(mod_values):
        ax1.annotate(
            f"{v:.3f}",
            (i, v),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=8,
            fontweight="bold",
        )

    ax1.set_ylabel("Modularidad", fontsize=11, color="#2C3E50")
    ax1.tick_params(axis="y", labelcolor="#2C3E50")
    ax1.set_ylim(bottom=0)

    # Densidad (eje derecho) — línea punteada con marcadores 's'
    if dens:
        ax2 = ax1.twinx()
        dens_values = [dens.get(v, 0) for v in ventanas]
        ax2.plot(
            ventanas,
            dens_values,
            "s--",
            color="#E74C3C",
            linewidth=1.5,
            markersize=6,
            label="Densidad",
        )

        # Anotar valores sobre cada punto de densidad
        for i, v in enumerate(dens_values):
            ax2.annotate(
                f"{v:.3f}",
                (i, v),
                textcoords="offset points",
                xytext=(0, -15),
                ha="center",
                fontsize=8,
                fontweight="bold",
                color="#E74C3C",
            )

        ax2.set_ylabel("Densidad", fontsize=11, color="#E74C3C")
        ax2.tick_params(axis="y", labelcolor="#E74C3C")

    ax1.set_xlabel("Legislatura", fontsize=11)
    ax1.set_title("Evolución de Modularidad y Densidad por Legislatura", fontsize=13)
    ax1.tick_params(axis="x", rotation=30)

    # Leyenda combinada
    lines1, labels1 = ax1.get_legend_handles_labels()
    if dens:
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(
            lines1 + lines2,
            labels1 + labels2,
            loc="upper right",
            fontsize=9,
        )
    else:
        ax1.legend(loc="upper right", fontsize=9)

    plt.tight_layout()
    filepath = output_path / "timeline_modularidad.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 3: Heatmap de alianzas (partidos × legislaturas)
# ---------------------------------------------------------------------------


def plot_heatmap_alianzas(window_results: dict, output_dir: str) -> str:
    """Heatmap: partidos × legislaturas con co-votación promedio inter-partido.

    Construye una matriz donde cada celda es la co-votación promedio (intra +
    inter) de un partido en una ventana/legislatura.

    Args:
        window_results: Dict label → result dict (salida de analyze_windows).
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo heatmap_alianzas.png.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not window_results:
        raise ValueError("Sin window_results para heatmap")

    # Ventanas ordenadas cronológicamente (por fecha de inicio)
    labels = sorted(
        window_results.keys(),
        key=lambda lbl: window_results[lbl]["window"]["start_date"],
    )

    # Recopilar partidos presentes usando org_id → nombre corto
    parties_present: set[str] = set()
    for label in labels:
        metrics = window_results[label]["metrics"]
        # intra_party_avg está indexado por org_id
        intra = metrics.get("intra_party_avg", {})
        for org_id in intra:
            short = _ORG_TO_SHORT.get(org_id, org_id)
            parties_present.add(short)
        # inter_party_avg tiene tuplas (org_id, org_id)
        inter = metrics.get("inter_party_avg", {})
        for pair in inter:
            for org_id in pair:
                short = _ORG_TO_SHORT.get(org_id, org_id)
                parties_present.add(short)

    # Orden canónico
    party_order = [p for p in _PARTY_ORDER if p in parties_present]
    party_order.extend(sorted(parties_present - set(_PARTY_ORDER)))

    # Construir matriz: para cada (partido, ventana), co-votación promedio
    # = promedio de: intra_party_avg del partido + todos los inter_party_avg del partido
    matrix_data = np.full((len(party_order), len(labels)), np.nan)

    for j, label in enumerate(labels):
        metrics = window_results[label]["metrics"]
        intra = metrics.get("intra_party_avg", {})
        inter = metrics.get("inter_party_avg", {})

        for i, party_short in enumerate(party_order):
            # Encontrar org_id correspondiente al nombre corto
            org_id = None
            for oid, sname in _ORG_TO_SHORT.items():
                if sname == party_short:
                    org_id = oid
                    break
            if org_id is None:
                continue

            values = []

            # Intra-party (co-votación promedio con miembros del mismo partido)
            if org_id in intra:
                values.append(intra[org_id])

            # Inter-party (co-votación promedio con cada otro partido)
            for pair, avg in inter.items():
                if org_id in pair:
                    values.append(avg)

            if values:
                matrix_data[i, j] = np.mean(values)

    # Verificar que hay datos
    if np.all(np.isnan(matrix_data)):
        raise ValueError("Sin datos numéricos para heatmap")

    n_rows, n_cols = matrix_data.shape

    fig, ax = plt.subplots(figsize=(max(8, n_cols * 2.5), max(5, n_rows * 0.8 + 2)))

    im = ax.imshow(matrix_data, cmap="RdYlBu_r", aspect="auto", vmin=0.4, vmax=1.0)

    # Anotar valor en cada celda
    for i in range(n_rows):
        for j in range(n_cols):
            val = matrix_data[i, j]
            if not np.isnan(val):
                color = "white" if val > 0.75 else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.3f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color=color,
                    fontweight="bold",
                )

    # Etiquetas X (ventanas)
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)

    # Etiquetas Y con color de partido
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(party_order, fontsize=10)
    for i, party in enumerate(party_order):
        tick_label = ax.get_yticklabels()[i]
        tick_label.set_color(_get_party_color(party))
        tick_label.set_fontweight("bold")

    ax.set_title("Co-votación Promedio por Partido y Legislatura", fontsize=13)
    fig.colorbar(im, ax=ax, label="Co-votación promedio", shrink=0.8)

    plt.tight_layout()
    filepath = output_path / "heatmap_alianzas.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 4: Grafo por ventana
# ---------------------------------------------------------------------------


def plot_grafo_por_ventana(window_results: dict, output_dir: str) -> dict[str, str]:
    """Generar un PNG del grafo por ventana para revisión individual.

    Para cada ventana:
    1. Filtra aristas al percentil 75 de peso.
    2. Si >200 nodos y no es conexo, toma componente conexa más grande.
    3. Layout spring_layout(seed=42, k=0.1, iterations=50).
    4. Colores de nodo por party_name.
    5. Tamaño de nodo proporcional a degree_centrality.
    6. Sin labels de texto.

    Args:
        window_results: Dict label → result dict (salida de analyze_windows).
        output_dir: Directorio base donde crear subcarpeta grafos/.

    Returns:
        Dict {label: filepath} con las rutas de cada PNG generado.
    """
    output_path = Path(output_dir)
    grafos_dir = output_path / "grafos"
    grafos_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    for i, (label, result) in enumerate(window_results.items()):
        graph = result["graph"]

        # Filtrar aristas al percentil 75
        all_weights = [d["weight"] for _, _, d in graph.edges(data=True)]
        if not all_weights:
            logger.warning("Sin aristas para ventana %s — saltando grafo", label)
            continue

        threshold = float(np.percentile(all_weights, 75))

        filtered_edges = [
            (u, v, d) for u, v, d in graph.edges(data=True) if d.get("weight", 0) >= threshold
        ]

        # Construir subgrafo
        sub = nx.Graph()
        sub.add_nodes_from(graph.nodes(data=True))
        sub.add_edges_from(filtered_edges)

        # Componente conexa más grande si >200 nodos y no es conexo
        if sub.number_of_nodes() > 200 and not nx.is_connected(sub):
            components = list(nx.connected_components(sub))
            largest = max(components, key=len)
            sub = sub.subgraph(largest).copy()

        # Layout
        pos = nx.spring_layout(sub, seed=42, k=0.1, iterations=50)

        # Colores por party_name
        node_colors = [_get_party_color(sub.nodes[n].get("party_name", "")) for n in sub.nodes()]

        # Tamaño proporcional a degree_centrality
        centralities = [sub.nodes[n].get("degree_centrality", 0.0) for n in sub.nodes()]
        max_c = max(centralities) if centralities and max(centralities) > 0 else 1.0
        node_sizes = [30 + 370 * (c / max_c) for c in centralities]

        # Dibujar (sin labels de texto)
        fig, ax = plt.subplots(figsize=(14, 14))

        nx.draw_networkx_edges(sub, pos, ax=ax, alpha=0.3, width=0.5, edge_color="#999999")
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

        ax.set_title(f"Red de Co-votación — {label}", fontsize=14)
        ax.axis("off")
        plt.tight_layout()

        safe_label = _sanitize_label(label)
        filename = f"grafo_{i + 1:02d}_{safe_label}.png"
        filepath = grafos_dir / filename
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)

        files[label] = str(filepath.resolve())

    logger.info("Grafos por ventana generados: %d", len(files))
    return files


# ---------------------------------------------------------------------------
# Función 5: Orquestador
# ---------------------------------------------------------------------------


def generate_all_dynamic_visualizations(
    window_results: dict,
    evolution: dict,
    output_dir: str,
) -> dict[str, str]:
    """Orquesta la generación de todas las visualizaciones dinámicas.

    Genera:
    1. timeline_disciplina.png — Evolución de disciplina partidista
    2. timeline_modularidad.png — Evolución de modularidad y densidad
    3. heatmap_alianzas.png — Heatmap partidos × legislaturas
    4. grafos/ — Un PNG del grafo por ventana

    Args:
        window_results: Dict label → result dict (salida de analyze_windows).
        evolution: Dict de compute_evolution_metrics.
        output_dir: Directorio base donde guardar todos los archivos.

    Returns:
        Dict {nombre_viz: ruta_archivo} con todas las rutas generadas.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    # 1. Timeline de disciplina
    try:
        path = plot_disciplina_timeline(evolution, output_dir)
        results["timeline_disciplina"] = path
        logger.info("timeline_disciplina: %s", path)
    except Exception as e:
        logger.error("Error generando timeline_disciplina: %s", e)

    # 2. Timeline de modularidad y densidad
    try:
        path = plot_modularidad_timeline(evolution, output_dir)
        results["timeline_modularidad"] = path
        logger.info("timeline_modularidad: %s", path)
    except Exception as e:
        logger.error("Error generando timeline_modularidad: %s", e)

    # 3. Heatmap de alianzas
    try:
        path = plot_heatmap_alianzas(window_results, output_dir)
        results["heatmap_alianzas"] = path
        logger.info("heatmap_alianzas: %s", path)
    except Exception as e:
        logger.error("Error generando heatmap_alianzas: %s", e)

    # 4. Grafos por ventana
    try:
        grafo_files = plot_grafo_por_ventana(window_results, output_dir)
        results.update(grafo_files)
        logger.info("Grafos por ventana: %d archivos", len(grafo_files))
    except Exception as e:
        logger.error("Error generando grafos por ventana: %s", e)

    logger.info("Visualizaciones dinámicas generadas: %d archivos", len(results))
    return results
