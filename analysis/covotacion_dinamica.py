#!/usr/bin/env python3
"""
covotacion_dinamica.py — Módulo de grafos dinámicos de co-votación legislativa.

Construye grafos de co-votación segmentados por ventanas temporales (periodos
legislativos o ventanas deslizantes) y calcula métricas de evolución para
analizar cómo cambian las alianzas, disciplina partidista y comunidades
a lo largo de la legislatura.

Reutiliza funciones de:
    - analysis.covotacion (load_data, get_primary_party, build_covotacion_matrix,
      build_graph, compute_quantitative_metrics)
    - analysis.comunidades (detect_communities, analyze_communities,
      get_partition_as_attribute)
    - analysis.centralidad (compute_all_centrality, add_centrality_to_graph)
    - analysis.visualizacion (PARTY_COLORS)

Funciones principales:
    - get_time_windows: derivar ventanas temporales desde la BD
    - build_dynamic_graphs: construir un grafo completo por ventana
    - compute_evolution_metrics: calcular métricas de evolución temporal
    - plot_dynamic_visualizations: generar todas las visualizaciones
"""

import logging
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Sin display — backend no interactivo
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

from analysis.centralidad import (
    add_centrality_to_graph,
    compute_all_centrality,
)
from analysis.comunidades import (
    analyze_communities,
    detect_communities,
    get_partition_as_attribute,
)
from analysis.covotacion import (
    _PARTY_ORG_IDS,
    build_covotacion_matrix,
    build_graph,
    compute_quantitative_metrics,
    get_primary_party,
    load_data,
    normalize_party,
)
from analysis.db import get_connection
from analysis.visualizacion import PARTY_COLORS

logger = logging.getLogger(__name__)

# Mapeo de nombres completos (org_map) → nombres cortos (PARTY_COLORS)
_LONG_TO_SHORT: dict[str, str] = {
    "Morena": "MORENA",
    "Partido del Trabajo (PT)": "PT",
    "Partido Verde Ecologista de México (PVEM)": "PVEM",
    "Partido Revolucionario Institucional (PRI)": "PRI",
    "Partido Acción Nacional (PAN)": "PAN",
    "Movimiento Ciudadano (MC)": "MC",
    "Partido de la Revolución Democrática (PRD)": "PRD",
    "Independientes": "Independientes",
}


def _short_party_name(name: str) -> str:
    """Convertir nombre largo de partido a nombre corto para PARTY_COLORS."""
    return _LONG_TO_SHORT.get(name, name)


# ---------------------------------------------------------------------------
# Función 1: get_time_windows
# ---------------------------------------------------------------------------
def get_time_windows(
    db_path: str,
    legislatura: str,
    mode: str = "period",
    min_events: int = 30,
    window_size: int | None = None,
    overlap: int | None = None,
) -> list[dict]:
    """Derivar ventanas temporales a partir de los datos de votación.

    Para mode='period', agrupa por periodos legislativos naturales
    (Sep-Dic = P1, Feb-Jul = P2, etc.). Para mode='sliding', crea
    ventanas de tamaño fijo con solapamiento.

    Args:
        db_path: ruta al archivo SQLite (congreso.db).
        legislatura: string como 'LXVI'.
        mode: 'period' (periodo legislativo natural) o 'sliding' (ventana deslizante).
        min_events: mínimo de votaciones por ventana (default 30).
            Si una ventana no alcanza, se combina con la adyacente.
        window_size: número de votaciones por ventana (solo para mode='sliding').
        overlap: solapamiento entre ventanas (solo para mode='sliding').

    Returns:
        Lista de dicts, cada uno con:
        - 'label': etiqueta legible ('P1 (Sep-Dic 2024)')
        - 'start_date': fecha ISO de inicio
        - 'end_date': fecha ISO de fin
        - 'vote_event_ids': lista de IDs de vote_events
        - 'n_events': número de eventos en la ventana
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    conn = get_connection(db_path)
    try:
        query = (
            "SELECT id, start_date FROM vote_event "
            "WHERE legislatura = ? AND start_date IS NOT NULL AND start_date != '' "
            "ORDER BY start_date"
        )
        ve_df = pd.read_sql_query(query, conn, params=(legislatura,))
    finally:
        conn.close()

    if ve_df.empty:
        logger.warning("No se encontraron vote_events para legislatura %s", legislatura)
        return []

    # Parsear fechas
    ve_df["start_date"] = pd.to_datetime(ve_df["start_date"])

    if mode == "period":
        windows = _build_period_windows(ve_df)
    elif mode == "sliding":
        if window_size is None:
            raise ValueError("window_size es obligatorio para mode='sliding'")
        windows = _build_sliding_windows(ve_df, window_size, overlap)
    else:
        raise ValueError(f"Modo no reconocido: {mode}. Usar 'period' o 'sliding'.")

    # Combinar ventanas con menos de min_events
    windows = _merge_small_windows(windows, min_events)

    # Filtrar ventanas vacías
    windows = [w for w in windows if w["n_events"] > 0]

    logger.info(
        "Ventanas temporales generadas (%s): %d ventanas para %s",
        mode,
        len(windows),
        legislatura,
    )
    for w in windows:
        logger.info(
            "  %s: %d eventos (%s a %s)",
            w["label"],
            w["n_events"],
            w["start_date"],
            w["end_date"],
        )

    return windows


def _build_period_windows(ve_df: pd.DataFrame) -> list[dict]:
    """Agrupar vote_events por periodos legislativos naturales.

    El año legislativo mexicano inicia en septiembre:
    - month >= 9 → año legislativo = año actual
    - month <= 8 → año legislativo = año anterior

    Dentro de cada año legislativo:
    - Sep-Dic = "Periodo Ordinario 1"
    - Ene-Ago = "Periodo Ordinario 2"
    """
    # Calcular año legislativo
    years = ve_df["start_date"].dt.year
    months = ve_df["start_date"].dt.month
    leg_years = np.where(months >= 9, years, years - 1)

    ve_df = ve_df.copy()
    ve_df["leg_year"] = leg_years
    ve_df["month"] = months

    windows = []
    # Agrupar por (año legislativo, periodo)
    for leg_year in sorted(ve_df["leg_year"].unique()):
        year_df = ve_df[ve_df["leg_year"] == leg_year]

        # Periodo 1: Sep-Dic
        p1 = year_df[(year_df["month"] >= 9) & (year_df["month"] <= 12)]
        if not p1.empty:
            windows.append(_make_window(p1, f"P{len(windows) + 1} (Sep-Dic {leg_year})"))

        # Periodo 2: Ene-Ago del año siguiente
        p2 = year_df[(year_df["month"] >= 1) & (year_df["month"] <= 8)]
        if not p2.empty:
            # Determinar sub-rango más preciso
            min_m = p2["month"].min()
            max_m = p2["month"].max()
            month_names = {
                1: "Ene",
                2: "Feb",
                3: "Mar",
                4: "Abr",
                5: "May",
                6: "Jun",
                7: "Jul",
                8: "Ago",
            }
            label = f"P{len(windows) + 1} ({month_names.get(min_m, str(min_m))}-{month_names.get(max_m, str(max_m))} {leg_year + 1})"
            windows.append(_make_window(p2, label))

    return windows


def _build_sliding_windows(
    ve_df: pd.DataFrame,
    window_size: int,
    overlap: int | None,
) -> list[dict]:
    """Crear ventanas deslizantes de tamaño fijo con solapamiento."""
    if overlap is None:
        overlap = 0

    if overlap >= window_size:
        raise ValueError(f"overlap ({overlap}) debe ser menor que window_size ({window_size})")

    step = window_size - overlap
    n = len(ve_df)
    windows = []

    start = 0
    idx = 1
    while start < n:
        end = min(start + window_size, n)
        chunk = ve_df.iloc[start:end]

        label = f"W{idx} ({chunk['start_date'].iloc[0].strftime('%Y-%m')}"
        label += f" a {chunk['start_date'].iloc[-1].strftime('%Y-%m')})"
        windows.append(_make_window(chunk, label))

        start += step
        idx += 1

    return windows


def _make_window(ve_chunk: pd.DataFrame, label: str) -> dict:
    """Crear un dict de ventana a partir de un chunk de vote_events."""
    return {
        "label": label,
        "start_date": ve_chunk["start_date"].min().strftime("%Y-%m-%d"),
        "end_date": ve_chunk["start_date"].max().strftime("%Y-%m-%d"),
        "vote_event_ids": ve_chunk["id"].tolist(),
        "n_events": len(ve_chunk),
    }


def _merge_small_windows(windows: list[dict], min_events: int) -> list[dict]:
    """Combinar ventanas con menos de min_events con la adyacente más cercana."""
    if not windows:
        return windows

    merged = [windows[0].copy()]

    for w in windows[1:]:
        if merged[-1]["n_events"] < min_events:
            # Combinar con la ventana anterior
            prev = merged[-1]
            prev["vote_event_ids"].extend(w["vote_event_ids"])
            prev["n_events"] = len(prev["vote_event_ids"])
            prev["end_date"] = w["end_date"]
            # Actualizar label para reflejar la combinación
            prev["label"] = (
                f"{prev['label'].split(' (')[0]}+ ({prev['start_date']} a {prev['end_date']})"
            )
            # Limpiar label excesivamente largo
            if len(prev["label"]) > 80:
                prev["label"] = f"P_combinado ({prev['start_date']} a {prev['end_date']})"
        else:
            merged.append(w.copy())

    # Verificar si la última ventana quedó pequeña
    if len(merged) > 1 and merged[-1]["n_events"] < min_events:
        # Combinar con la anterior
        last = merged.pop()
        prev = merged[-1]
        prev["vote_event_ids"].extend(last["vote_event_ids"])
        prev["n_events"] = len(prev["vote_event_ids"])
        prev["end_date"] = last["end_date"]
        prev["label"] = (
            f"{prev['label'].split(' (')[0]}+ ({prev['start_date']} a {prev['end_date']})"
        )
        if len(prev["label"]) > 80:
            prev["label"] = f"P_combinado ({prev['start_date']} a {prev['end_date']})"

    return merged


# ---------------------------------------------------------------------------
# Función 2: build_dynamic_graphs
# ---------------------------------------------------------------------------
def build_dynamic_graphs(
    db_path: str,
    legislatura: str,
    windows: list[dict] | None = None,
    min_votes: int = 10,
) -> list[dict]:
    """Construir un grafo de co-votación completo por cada ventana temporal.

    Para cada ventana, construye: matriz → grafo → métricas → comunidades
    → centralidad.

    Args:
        db_path: ruta al archivo SQLite (congreso.db).
        legislatura: string como 'LXVI'.
        windows: lista de ventanas (de get_time_windows). Si None, calcular automáticamente.
        min_votes: mínimo de votos para elegibilidad (pasar a build_covotacion_matrix).

    Returns:
        Lista de dicts, cada uno con:
        - 'window': la ventana temporal
        - 'graph': nx.Graph con atributos completos
        - 'party_map': dict voter_id → party_id
        - 'org_map': dict org_id → org_nombre
        - 'metrics': dict de compute_quantitative_metrics
        - 'partition': dict de detect_communities
        - 'community_analysis': dict de analyze_communities
        - 'centrality': dict de compute_all_centrality
    """
    if windows is None:
        windows = get_time_windows(db_path, legislatura)

    if not windows:
        logger.warning("No hay ventanas temporales para construir grafos")
        return []

    # Cargar datos una sola vez
    votes_df, persons_df, org_map = load_data(db_path)
    logger.info("Datos cargados: %d votos totales", len(votes_df))

    results = []

    for i, window in enumerate(windows):
        label = window["label"]
        logger.info("Procesando ventana %d/%d: %s", i + 1, len(windows), label)

        # Filtrar votos a los vote_events de esta ventana
        ve_ids = set(window["vote_event_ids"])
        window_votes = votes_df[votes_df["vote_event_id"].isin(ve_ids)].copy()

        if window_votes.empty:
            logger.warning("  Sin votos para ventana %s — saltando", label)
            continue

        # Obtener party_map para esta ventana
        party_map = get_primary_party(window_votes)

        # Construir matriz de co-votación
        matrix, legislators, co_participations = build_covotacion_matrix(
            window_votes, min_votes=min_votes
        )

        if not legislators:
            logger.warning("  Sin legisladores elegibles para %s — saltando", label)
            continue

        # Construir grafo
        graph = build_graph(matrix, legislators, party_map, persons_df)

        # Calcular métricas cuantitativas
        metrics = compute_quantitative_metrics(graph, party_map, org_map)

        # Detectar comunidades
        partition = detect_communities(graph)
        graph = get_partition_as_attribute(graph, partition)

        # Analizar comunidades
        community_analysis = analyze_communities(graph, partition, party_map, org_map)

        # Calcular centralidad
        centrality = compute_all_centrality(graph)
        graph = add_centrality_to_graph(graph, centrality)

        results.append(
            {
                "window": window,
                "graph": graph,
                "party_map": party_map,
                "org_map": org_map,
                "metrics": metrics,
                "partition": partition,
                "community_analysis": community_analysis,
                "centrality": centrality,
            }
        )

        logger.info(
            "  %s: %d nodos, %d aristas, modularidad=%.4f",
            label,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            community_analysis["modularity"],
        )

    logger.info("Grafos dinámicos construidos: %d de %d ventanas", len(results), len(windows))
    return results


# ---------------------------------------------------------------------------
# Función 3: compute_evolution_metrics
# ---------------------------------------------------------------------------
# Renombrada para evitar colisión con la nueva API cross-legislatura
def _compute_evolution_metrics_period(
    dynamic_results: list[dict],
    org_map: dict[str, str],
) -> dict:
    """Calcular métricas de evolución temporal a partir de los grafos dinámicos.

    Args:
        dynamic_results: lista de resultados de build_dynamic_graphs.
        org_map: dict org_id → nombre.

    Returns:
        Dict con métricas de evolución:
        - 'disciplina_por_periodo': {label: {party_name: avg_intra_covote}}
        - 'modularidad_por_periodo': {label: modularity}
        - 'tamano_comunidades_por_periodo': {label: [size1, size2, ...]}
        - 'stability_index': {pair_label: ari_float}
        - 'frontera_coalicion_por_periodo': {label: avg_weight_cross_edges}
        - 'disidencia_por_periodo': {label: [top5_dissidents]}
        - 'densidad_por_periodo': {label: density}
        - 'num_legislators_por_periodo': {label: int}
    """
    if not dynamic_results:
        logger.warning("Sin resultados dinámicos para calcular evolución")
        return {}

    disciplina: dict[str, dict[str, float]] = {}
    modularidad: dict[str, float] = {}
    tamano_comunidades: dict[str, list[int]] = {}
    frontera_coalicion: dict[str, float] = {}
    disidencia: dict[str, list[dict]] = {}
    densidad: dict[str, float] = {}
    num_legislators: dict[str, int] = {}

    for result in dynamic_results:
        label = result["window"]["label"]
        graph = result["graph"]
        party_map = result["party_map"]
        metrics = result["metrics"]
        partition = result["partition"]
        community_analysis = result["community_analysis"]

        # Disciplina: co-votación intra-partido (nombres cortos para PARTY_COLORS)
        intra = metrics["intra_party_avg"]
        disciplina[label] = {
            _short_party_name(org_map.get(pid, pid)): avg for pid, avg in intra.items()
        }

        # Modularidad
        modularidad[label] = community_analysis["modularity"]

        # Tamaño de comunidades
        sizes = list(community_analysis["community_sizes"].values())
        tamano_comunidades[label] = sorted(sizes, reverse=True)

        # Frontera de coalición
        frontera_coalicion[label] = _compute_coalition_frontier(graph, partition, party_map)

        # Disidencia: top 5 legisladores con menor co-votación intra-partido
        disidencia[label] = _compute_top_dissidents(graph, party_map, org_map)

        # Densidad
        densidad[label] = metrics["density"]

        # Número de legisladores
        num_legislators[label] = metrics["num_legislators"]

    # Stability index: ARI entre periodos consecutivos
    stability = _compute_stability_index(dynamic_results, org_map)

    evolution = {
        "disciplina_por_periodo": disciplina,
        "modularidad_por_periodo": modularidad,
        "tamano_comunidades_por_periodo": tamano_comunidades,
        "stability_index": stability,
        "frontera_coalicion_por_periodo": frontera_coalicion,
        "disidencia_por_periodo": disidencia,
        "densidad_por_periodo": densidad,
        "num_legislators_por_periodo": num_legislators,
    }

    logger.info("Métricas de evolución calculadas para %d periodos", len(dynamic_results))
    return evolution


def _compute_coalition_frontier(
    graph: nx.Graph,
    partition: dict[str, int],
    party_map: dict[str, str],
) -> float:
    """Calcular promedio de pesos de aristas entre la comunidad mayoritaria y el resto."""
    if not partition or graph.number_of_edges() == 0:
        return 0.0

    # Encontrar la comunidad mayoritaria
    comm_counts = Counter(partition.values())
    if not comm_counts:
        return 0.0
    majority_comm = comm_counts.most_common(1)[0][0]

    # Nodos en la comunidad mayoritaria
    majority_nodes = {n for n, c in partition.items() if c == majority_comm}

    # Aristas frontera (un nodo en mayoría, otro fuera)
    cross_weights = []
    for u, v, data in graph.edges(data=True):
        u_in = u in majority_nodes
        v_in = v in majority_nodes
        if u_in != v_in:  # Exactamente un nodo en mayoría
            cross_weights.append(data["weight"])

    if not cross_weights:
        return 0.0

    return sum(cross_weights) / len(cross_weights)


def _compute_top_dissidents(
    graph: nx.Graph,
    party_map: dict[str, str],
    org_map: dict[str, str],
    n: int = 5,
) -> list[dict]:
    """Calcular top N legisladores más disidentes (menor co-votación intra-partido)."""
    # Para cada legislador, calcular co-votación promedio con miembros de su partido
    legislator_scores = []

    for node in graph.nodes():
        pid = party_map.get(node, "O11")
        # Aristas intra-partido de este legislador
        intra_weights = []
        for neighbor in graph.neighbors(node):
            neighbor_pid = party_map.get(neighbor, "O11")
            if neighbor_pid == pid:
                intra_weights.append(graph[node][neighbor]["weight"])

        if intra_weights:
            avg_intra = sum(intra_weights) / len(intra_weights)
        else:
            avg_intra = 0.0

        legislator_scores.append(
            {
                "legislator_id": node,
                "nombre": graph.nodes[node].get("nombre", node),
                "partido": _short_party_name(org_map.get(pid, pid)),
                "covotacion_intra": round(avg_intra, 4),
            }
        )

    # Ordenar por co-votación intra ascendente (más disidentes primero)
    legislator_scores.sort(key=lambda x: x["covotacion_intra"])
    return legislator_scores[:n]


def _compute_stability_index(
    dynamic_results: list[dict],
    org_map: dict[str, str],
) -> dict[str, float]:
    """Calcular Adjusted Rand Index entre particiones de periodos consecutivos."""
    stability = {}

    if len(dynamic_results) < 2:
        return stability

    # Intentar importar sklearn
    try:
        from sklearn.metrics import adjusted_rand_score

        use_sklearn = True
    except ImportError:
        logger.warning("sklearn no disponible — usando fallback de coincidencia directa para ARI")
        use_sklearn = False

    for i in range(len(dynamic_results) - 1):
        r_a = dynamic_results[i]
        r_b = dynamic_results[i + 1]

        label_a = r_a["window"]["label"]
        label_b = r_b["window"]["label"]
        pair_label = f"{label_a} → {label_b}"

        part_a = r_a["partition"]
        part_b = r_b["partition"]

        # Legisladores comunes entre ambos periodos
        common = set(part_a.keys()) & set(part_b.keys())

        if len(common) < 2:
            stability[pair_label] = 0.0
            logger.warning(
                "Muy pocos legisladores comunes (%d) para ARI: %s",
                len(common),
                pair_label,
            )
            continue

        common = sorted(common)
        labels_a = [part_a[leg] for leg in common]
        labels_b = [part_b[leg] for leg in common]

        if use_sklearn:
            ari = adjusted_rand_score(labels_a, labels_b)
        else:
            ari = _fallback_ari(labels_a, labels_b)

        stability[pair_label] = round(ari, 4)
        logger.info(
            "  Stability %s: ARI=%.4f (%d legisladores comunes)",
            pair_label,
            ari,
            len(common),
        )

    return stability


def _fallback_ari(labels_a: list[int], labels_b: list[int]) -> float:
    """Fallback simple de ARI basado en coincidencia directa.

    Implementación simplificada del Adjusted Rand Index.
    """
    n = len(labels_a)
    if n == 0:
        return 0.0

    # Construir tabla de contingencia
    pairs_a = {}
    pairs_b = {}
    for i in range(n):
        pairs_a.setdefault(labels_a[i], []).append(i)
        pairs_b.setdefault(labels_b[i], []).append(i)

    # Contar pares concordantes y discordantes
    # Usando la fórmula de Hubert-Arabie

    # Tabla de contingencia
    classes_a = sorted(set(labels_a))
    classes_b = sorted(set(labels_b))
    contingency = np.zeros((len(classes_a), len(classes_b)), dtype=int)

    idx_a = {c: i for i, c in enumerate(classes_a)}
    idx_b = {c: i for i, c in enumerate(classes_b)}

    for k in range(n):
        contingency[idx_a[labels_a[k]]][idx_b[labels_b[k]]] += 1

    # Suma de C(n_ij, 2)
    sum_comb_c = sum(
        int(contingency[i, j] * (contingency[i, j] - 1) / 2)
        for i in range(len(classes_a))
        for j in range(len(classes_b))
    )

    # Sumas marginales
    row_sums = contingency.sum(axis=1)
    col_sums = contingency.sum(axis=0)

    sum_comb_rows = sum(int(r * (r - 1) / 2) for r in row_sums)
    sum_comb_cols = sum(int(c * (c - 1) / 2) for c in col_sums)

    total_comb = int(n * (n - 1) / 2)

    # ARI
    expected = sum_comb_rows * sum_comb_cols / total_comb if total_comb > 0 else 0
    max_index = 0.5 * (sum_comb_rows + sum_comb_cols)

    if max_index == expected:
        return 1.0 if sum_comb_c == expected else 0.0

    ari = (sum_comb_c - expected) / (max_index - expected)
    return max(-1.0, min(1.0, ari))


# ---------------------------------------------------------------------------
# Función 4: plot_dynamic_visualizations
# ---------------------------------------------------------------------------
def plot_dynamic_visualizations(
    dynamic_results: list[dict],
    evolution_metrics: dict,
    org_map: dict[str, str],
    output_dir: str,
) -> dict[str, str]:
    """Generar todas las visualizaciones dinámicas.

    Genera:
    1. heatmap_alianzas.png — Heatmap partidos × periodos
    2. timeline_modularidad.png — Línea de tiempo de modularidad + densidad
    3. timeline_disciplina.png — Línea de tiempo de disciplina partidista
    4. serie_grafos/ — Un PNG por periodo
    5. sankey_comunidades.png (opcional, si hay ≥3 periodos)

    Args:
        dynamic_results: lista de resultados de build_dynamic_graphs.
        evolution_metrics: dict de compute_evolution_metrics.
        org_map: dict org_id → nombre.
        output_dir: directorio de salida.

    Returns:
        Dict {nombre_viz → ruta_archivo}.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    files = {}

    if not dynamic_results:
        logger.warning("Sin resultados para generar visualizaciones")
        return files

    # 1. Heatmap de alianzas
    try:
        files["heatmap_alianzas"] = _plot_heatmap_alianzas(evolution_metrics, org_map, str(out))
    except Exception as e:
        logger.error("Error generando heatmap_alianzas: %s", e)

    # 2. Timeline modularidad + densidad
    try:
        files["timeline_modularidad"] = _plot_timeline_modularidad(evolution_metrics, str(out))
    except Exception as e:
        logger.error("Error generando timeline_modularidad: %s", e)

    # 3. Timeline disciplina partidista
    try:
        files["timeline_disciplina"] = _plot_timeline_disciplina(evolution_metrics, str(out))
    except Exception as e:
        logger.error("Error generando timeline_disciplina: %s", e)

    # 4. Serie de grafos
    try:
        serie_dir = out / "serie_grafos"
        serie_dir.mkdir(parents=True, exist_ok=True)
        serie_files = _plot_serie_grafos(dynamic_results, str(serie_dir))
        files["serie_grafos"] = str(serie_dir)
        files.update(serie_files)
    except Exception as e:
        logger.error("Error generando serie_grafos: %s", e)

    # 5. Sankey (opcional, ≥3 periodos)
    if len(dynamic_results) >= 3:
        try:
            files["sankey_comunidades"] = _plot_sankey_comunidades(
                dynamic_results, org_map, str(out)
            )
        except Exception as e:
            logger.error("Error generando sankey_comunidades: %s", e)

    logger.info("Visualizaciones generadas: %d archivos", len(files))
    return files


def _plot_heatmap_alianzas(
    evolution_metrics: dict,
    org_map: dict[str, str],
    output_dir: str,
) -> str:
    """Heatmap partidos × periodos con co-votación intra-partido."""
    disciplina = evolution_metrics.get("disciplina_por_periodo", {})
    if not disciplina:
        raise ValueError("Sin datos de disciplina para heatmap")

    # Orden canónico de partidos
    party_order = ["MORENA", "PT", "PVEM", "PRI", "PAN", "MC", "PRD"]
    periods = list(disciplina.keys())

    # Construir matriz
    data = []
    labels_y = []
    for party in party_order:
        row = []
        for period in periods:
            row.append(disciplina.get(period, {}).get(party, np.nan))
        # Solo incluir si hay al menos un valor no-NaN
        if any(not np.isnan(v) for v in row):
            data.append(row)
            labels_y.append(party)

    if not data:
        raise ValueError("Sin datos para heatmap")

    matrix = np.array(data)

    fig, ax = plt.subplots(figsize=(max(8, len(periods) * 2.5), max(5, len(labels_y) * 0.8 + 2)))

    im = ax.imshow(matrix, cmap="RdYlBu_r", aspect="auto", vmin=0.4, vmax=1.0)

    # Anotar valores en cada celda
    for i in range(len(labels_y)):
        for j in range(len(periods)):
            val = matrix[i, j]
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

    ax.set_xticks(range(len(periods)))
    ax.set_xticklabels(periods, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(labels_y)))

    # Etiquetas Y con color de partido
    for i, party in enumerate(labels_y):
        ax.get_yticklabels()[i].set_color(PARTY_COLORS.get(party, "black"))
        ax.get_yticklabels()[i].set_fontweight("bold")
    ax.set_yticklabels(labels_y, fontsize=10)

    ax.set_title("Disciplina Partidista por Periodo\n(Co-votación Intra-partido)", fontsize=13)
    fig.colorbar(im, ax=ax, label="Co-votación promedio", shrink=0.8)

    plt.tight_layout()
    filepath = Path(output_dir) / "heatmap_alianzas.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


def _plot_timeline_modularidad(evolution_metrics: dict, output_dir: str) -> str:
    """Línea de tiempo de modularidad con densidad en eje secundario."""
    mod = evolution_metrics.get("modularidad_por_periodo", {})
    dens = evolution_metrics.get("densidad_por_periodo", {})

    if not mod:
        raise ValueError("Sin datos de modularidad")

    periods = list(mod.keys())

    fig, ax1 = plt.subplots(figsize=(max(8, len(periods) * 2), 6))

    # Modularidad (eje izquierdo)
    mod_values = [mod[p] for p in periods]
    ax1.plot(
        periods,
        mod_values,
        "o-",
        color="#2C3E50",
        linewidth=2,
        markersize=8,
        label="Modularidad",
    )
    for i, (p, v) in enumerate(zip(periods, mod_values)):
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

    # Densidad (eje derecho)
    if dens:
        ax2 = ax1.twinx()
        dens_values = [dens.get(p, 0) for p in periods]
        ax2.plot(
            periods,
            dens_values,
            "s--",
            color="#E74C3C",
            linewidth=1.5,
            markersize=6,
            label="Densidad",
        )
        ax2.set_ylabel("Densidad", fontsize=11, color="#E74C3C")
        ax2.tick_params(axis="y", labelcolor="#E74C3C")

    ax1.set_xlabel("Periodo", fontsize=11)
    ax1.set_title("Evolución de Modularidad y Densidad", fontsize=13)
    ax1.tick_params(axis="x", rotation=30)

    # Leyenda combinada
    lines1, labels1 = ax1.get_legend_handles_labels()
    if dens:
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=9)
    else:
        ax1.legend(loc="upper right", fontsize=9)

    plt.tight_layout()
    filepath = Path(output_dir) / "timeline_modularidad.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


def _plot_timeline_disciplina(evolution_metrics: dict, output_dir: str) -> str:
    """Línea de tiempo de disciplina partidista (una línea por partido)."""
    disciplina = evolution_metrics.get("disciplina_por_periodo", {})
    if not disciplina:
        raise ValueError("Sin datos de disciplina")

    periods = list(disciplina.keys())
    # Recopilar todos los partidos presentes
    all_parties = set()
    for period_data in disciplina.values():
        all_parties.update(period_data.keys())

    # Orden canónico
    party_order = ["MORENA", "PT", "PVEM", "PRI", "PAN", "MC", "PRD"]
    parties = [p for p in party_order if p in all_parties]

    fig, ax = plt.subplots(figsize=(max(8, len(periods) * 2), 6))

    for party in parties:
        values = [disciplina.get(p, {}).get(party, np.nan) for p in periods]
        # Solo plotear si hay al menos un valor válido
        valid = [(i, v) for i, v in enumerate(values) if not np.isnan(v)]
        if not valid:
            continue

        color = PARTY_COLORS.get(party, "#CCCCCC")
        valid_indices = [v[0] for v in valid]
        valid_values = [v[1] for v in valid]
        valid_periods = [periods[i] for i in valid_indices]

        ax.plot(
            valid_periods,
            valid_values,
            "o-",
            color=color,
            linewidth=2,
            markersize=6,
            label=party,
        )

    ax.set_xlabel("Periodo", fontsize=11)
    ax.set_ylabel("Co-votación Intra-partido", fontsize=11)
    ax.set_title("Evolución de Disciplina Partidista", fontsize=13)
    ax.tick_params(axis="x", rotation=30)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="best", fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    filepath = Path(output_dir) / "timeline_disciplina.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return str(filepath.resolve())


def _plot_serie_grafos(
    dynamic_results: list[dict],
    output_dir: str,
) -> dict[str, str]:
    """Generar un grafo PNG por periodo."""
    files = {}

    for i, result in enumerate(dynamic_results):
        label = result["window"]["label"]
        graph = result["graph"]

        # Short label para filename
        short_label = f"P{i + 1}"
        filename = f"grafo_{short_label}.png"

        # Filtrar al percentil 75 (igual que grafo estático)
        all_weights = [d["weight"] for _, _, d in graph.edges(data=True)]
        if not all_weights:
            continue

        threshold = float(np.percentile(all_weights, 75))

        filtered_edges = [
            (u, v, d) for u, v, d in graph.edges(data=True) if d.get("weight", 0) >= threshold
        ]

        sub = nx.Graph()
        sub.add_nodes_from(graph.nodes(data=True))
        sub.add_edges_from(filtered_edges)

        # Componente conexa más grande si hay muchos nodos
        if sub.number_of_nodes() > 200 and not nx.is_connected(sub):
            components = list(nx.connected_components(sub))
            largest = max(components, key=len)
            sub = sub.subgraph(largest).copy()

        # Layout con misma semilla
        pos = nx.spring_layout(sub, seed=42, k=0.1, iterations=50)

        # Colores por partido
        node_colors = []
        for n in sub.nodes():
            pname = sub.nodes[n].get("party_name", "")
            node_colors.append(PARTY_COLORS.get(pname, "#CCCCCC"))

        # Tamaño por degree centrality
        centralities = [sub.nodes[n].get("degree_centrality", 0.0) for n in sub.nodes()]
        max_c = max(centralities) if centralities and max(centralities) > 0 else 1.0
        node_sizes = [30 + 370 * (c / max_c) for c in centralities]

        # Dibujar
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

        filepath = Path(output_dir) / filename
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)

        files[f"grafo_{short_label}"] = str(filepath.resolve())

    return files


def _plot_sankey_comunidades(
    dynamic_results: list[dict],
    org_map: dict[str, str],
    output_dir: str,
) -> str:
    """Diagrama de flujo de legisladores entre comunidades (barras apiladas).

    Como matplotlib.sankey es limitado, generamos barras apiladas como
    alternativa que muestra la composición partidista de cada comunidad por periodo.
    """
    periods = []
    all_data = []

    for result in dynamic_results:
        label = result["window"]["label"]
        community_analysis = result["community_analysis"]
        composition = community_analysis["community_composition"]

        periods.append(label)

        # Para cada comunidad, registrar su composición
        comm_data = {}
        for cid, comp in composition.items():
            for party_name, count in comp.items():
                comm_data[f"C{cid}_{party_name}"] = count
        all_data.append(comm_data)

    # Crear tabla de transición: para cada par de periodos, cuántos legisladores
    # estaban en comunidad X en el periodo A y en comunidad Y en el periodo B
    transition_data = _compute_transitions(dynamic_results, org_map)

    # Visualización: barras apiladas de composición por comunidad y periodo
    n_periods = len(periods)
    fig, axes = plt.subplots(1, n_periods, figsize=(4 * n_periods, 7), squeeze=False)

    party_order = ["MORENA", "PT", "PVEM", "PRI", "PAN", "MC", "PRD"]

    for idx, result in enumerate(dynamic_results):
        ax = axes[0, idx]
        label = result["window"]["label"]
        community_analysis = result["community_analysis"]
        composition = community_analysis["community_composition"]
        sizes = community_analysis["community_sizes"]

        communities = sorted(composition.keys())
        x_labels = []
        bottoms = np.zeros(len(communities))

        for party in party_order:
            # composition usa nombres largos; party_order usa nombres cortos
            values = []
            for c in communities:
                comp = composition[c]
                # Buscar por nombre corto mapeando las claves del dict
                val = 0
                for long_name, count in comp.items():
                    if _short_party_name(long_name) == party:
                        val += count
                values.append(val)
            if any(v > 0 for v in values):
                color = PARTY_COLORS.get(party, "#CCCCCC")
                ax.bar(
                    range(len(communities)),
                    values,
                    bottom=bottoms,
                    color=color,
                    label=party if idx == 0 else "",
                    edgecolor="white",
                    linewidth=0.5,
                )
                bottoms += np.array(values)

        x_labels = [f"C{c}\n(n={sizes[c]})" for c in communities]
        ax.set_xticks(range(len(communities)))
        ax.set_xticklabels(x_labels, fontsize=7, rotation=45, ha="right")
        ax.set_title(label, fontsize=9, fontweight="bold")
        ax.set_ylabel("Legisladores" if idx == 0 else "", fontsize=9)

    # Leyenda en el primer axes
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(party_order), fontsize=8)

    fig.suptitle("Composición Partidista de Comunidades por Periodo", fontsize=13, y=1.02)
    plt.tight_layout()

    filepath = Path(output_dir) / "sankey_comunidades.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # También exportar CSV con datos de transición
    if transition_data:
        csv_path = Path(output_dir) / "transiciones_comunidades.csv"
        rows = []
        for (period_a, period_b, comm_a, comm_b), count in transition_data.items():
            rows.append(
                {
                    "periodo_origen": period_a,
                    "periodo_destino": period_b,
                    "comunidad_origen": comm_a,
                    "comunidad_destino": comm_b,
                    "legisladores": count,
                }
            )
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        logger.info("CSV de transiciones exportado: %s", csv_path)

    return str(filepath.resolve())


def _compute_transitions(
    dynamic_results: list[dict],
    org_map: dict[str, str],
) -> dict[tuple, int]:
    """Calcular transiciones de legisladores entre comunidades."""
    transitions = {}

    for i in range(len(dynamic_results) - 1):
        r_a = dynamic_results[i]
        r_b = dynamic_results[i + 1]

        label_a = r_a["window"]["label"]
        label_b = r_b["window"]["label"]
        part_a = r_a["partition"]
        part_b = r_b["partition"]

        common = set(part_a.keys()) & set(part_b.keys())

        for leg in common:
            ca = part_a[leg]
            cb = part_b[leg]
            key = (label_a, label_b, f"C{ca}", f"C{cb}")
            transitions[key] = transitions.get(key, 0) + 1

    return transitions


# ===========================================================================
# API CROSS-LEGISLATURA — Análisis dinámico entre legislaturas
# ===========================================================================


def load_data_by_window(
    db_path: str,
    window_type: str = "legislatura",
    window_value=None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Cargar datos filtrados por ventana temporal.

    A diferencia de load_data (que carga TODO), esta función filtra
    los vote_events antes de devolver votos y personas.

    Args:
        db_path: ruta al archivo SQLite (congreso.db).
        window_type: tipo de filtro:
            - 'legislatura': window_value es un string como 'LXVI'.
            - 'date_range': window_value es una tupla (start_date, end_date) ISO.
            - 'vote_event_list': window_value es una lista de vote_event_ids.
        window_value: valor del filtro según window_type.

    Returns:
        Tupla (votes_df, persons_df, org_map), mismo formato que load_data.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    conn = get_connection(db_path)
    try:
        # Obtener vote_event_ids filtrados según window_type
        if window_type == "legislatura":
            ve_ids = pd.read_sql_query(
                "SELECT id FROM vote_event WHERE legislatura = ?",
                conn,
                params=(window_value,),
            )["id"].tolist()
        elif window_type == "date_range":
            start_date, end_date = window_value
            ve_ids = pd.read_sql_query(
                "SELECT id FROM vote_event WHERE start_date >= ? AND start_date <= ?",
                conn,
                params=(start_date, end_date),
            )["id"].tolist()
        elif window_type == "vote_event_list":
            ve_ids = list(window_value)
        else:
            raise ValueError(
                f"window_type no reconocido: {window_type}. "
                "Usar 'legislatura', 'date_range' o 'vote_event_list'."
            )

        if not ve_ids:
            logger.warning(
                "No se encontraron vote_events para window_type=%s, window_value=%s",
                window_type,
                window_value,
            )
            return pd.DataFrame(), pd.DataFrame(), {}

        # Cargar votos filtrados por vote_event_ids
        placeholders = ",".join("?" for _ in ve_ids)
        votes_df = pd.read_sql_query(
            f'SELECT voter_id, vote_event_id, option, "group" '
            f"FROM vote WHERE vote_event_id IN ({placeholders})",
            conn,
            params=ve_ids,
        )

        # Normalizar partido
        votes_df["party_id"] = votes_df["group"].map(normalize_party)
        votes_df = votes_df[["voter_id", "vote_event_id", "option", "party_id"]]

        # Personas: solo las que aparecen en los votos filtrados
        voter_ids = sorted(set(votes_df["voter_id"].tolist()))
        if voter_ids:
            ph = ",".join("?" for _ in voter_ids)
            persons_df = pd.read_sql_query(
                f"SELECT id, nombre, genero FROM person WHERE id IN ({ph})",
                conn,
                params=voter_ids,
            )
        else:
            persons_df = pd.DataFrame(columns=["id", "nombre", "genero"])

        # Organizaciones (completo, igual que load_data)
        orgs_df = pd.read_sql_query(
            "SELECT id, nombre FROM organization",
            conn,
        )
        org_map: dict[str, str] = {}
        for _, row in orgs_df.iterrows():
            if row["id"] in _PARTY_ORG_IDS:
                org_map[row["id"]] = row["nombre"]

        logger.info(
            "Datos filtrados (%s=%s): %d votos, %d personas, %d organizaciones",
            window_type,
            window_value,
            len(votes_df),
            len(persons_df),
            len(org_map),
        )
    finally:
        conn.close()

    return votes_df, persons_df, org_map


def build_windows(
    db_path: str,
    strategy: str = "legislatura",
    min_events: int = 30,
    window_size: int | None = None,
    overlap: int | None = None,
    camara: str | None = None,
    exclude_legislaturas: list[str] | None = None,
) -> list[dict]:
    """Construir ventanas temporales cross-legislatura.

    Genera ventanas que abarcan múltiples legislaturas para análisis
    de evolución a largo plazo.

    Args:
        db_path: ruta al archivo SQLite (congreso.db).
        strategy: estrategia de agrupación:
            - 'legislatura': una ventana por legislatura.
            - 'biennium': ventanas de 2 años calendario.
            - 'sliding': ventanas deslizantes de window_size votaciones.
        min_events: mínimo de votaciones por ventana (combina pequeñas).
        window_size: tamaño de ventana (solo para strategy='sliding').
        overlap: solapamiento entre ventanas (solo para strategy='sliding').
        camara: Filtrar por cámara. ``'D'`` para Diputados, ``'S'`` para
            Senado. Si es ``None``, no filtra.
        exclude_legislaturas: Lista de legislaturas a excluir (ej: ``['LXVI']``).
            Si es ``None`` o vacía, no excluye ninguna.

    Returns:
        Lista de dicts, cada uno con:
        - 'label': etiqueta legible ('LXVI (2024-27)')
        - 'legislatura': código(s) de legislatura
        - 'start_date': fecha ISO de inicio
        - 'end_date': fecha ISO de fin
        - 'vote_event_ids': lista de IDs
        - 'n_events': número de eventos
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    conn = get_connection(db_path)
    try:
        base_query = (
            "SELECT id, start_date, legislatura FROM vote_event "
            "WHERE start_date IS NOT NULL AND start_date != '' "
        )
        params: list[str] = []
        if camara is not None:
            camara_org = "O08" if camara == "D" else "O09"
            base_query += "AND organization_id = ? "
            params.append(camara_org)
        if exclude_legislaturas:
            placeholders = ",".join("?" for _ in exclude_legislaturas)
            base_query += f"AND legislatura NOT IN ({placeholders}) "
            params.extend(exclude_legislaturas)
        base_query += "ORDER BY start_date"
        ve_df = pd.read_sql_query(base_query, conn, params=params)
    finally:
        conn.close()

    if ve_df.empty:
        logger.warning("No se encontraron vote_events en la base de datos")
        return []

    ve_df["start_date"] = pd.to_datetime(ve_df["start_date"])

    if strategy == "legislatura":
        windows = _build_legislatura_windows(ve_df)
    elif strategy == "biennium":
        windows = _build_biennium_windows(ve_df)
    elif strategy == "sliding":
        if window_size is None:
            raise ValueError("window_size es obligatorio para strategy='sliding'")
        windows = _build_cross_sliding_windows(ve_df, window_size, overlap)
    else:
        raise ValueError(
            f"Estrategia no reconocida: {strategy}. Usar 'legislatura', 'biennium' o 'sliding'."
        )

    # Para estrategia legislatura: mapear vote_event_id → legislatura
    # antes del merge para poder reconstruir códigos concatenados
    ve_to_leg: dict[str, str] = {}
    if strategy == "legislatura":
        for _, row in ve_df.iterrows():
            if pd.notna(row.get("legislatura")):
                ve_to_leg[row["id"]] = row["legislatura"]

    # Combinar ventanas con menos de min_events
    windows = _merge_small_windows(windows, min_events)

    # Filtrar ventanas vacías
    windows = [w for w in windows if w["n_events"] > 0]

    # Post-procesar legislatura para ventanas combinadas (strategy='legislatura')
    if strategy == "legislatura" and ve_to_leg:
        for w in windows:
            codes = sorted(
                set(
                    ve_to_leg.get(ve_id, "")
                    for ve_id in w["vote_event_ids"]
                    if ve_to_leg.get(ve_id, "")
                )
            )
            if len(codes) > 1:
                w["legislatura"] = "+".join(codes)
            elif codes:
                w["legislatura"] = codes[0]

    logger.info(
        "Ventanas cross-legislatura generadas (%s): %d ventanas",
        strategy,
        len(windows),
    )
    for w in windows:
        logger.info(
            "  %s: %d eventos (%s a %s)",
            w["label"],
            w["n_events"],
            w["start_date"],
            w["end_date"],
        )

    return windows


def _build_legislatura_windows(ve_df: pd.DataFrame) -> list[dict]:
    """Una ventana por legislatura, con label legible."""
    windows = []
    for leg in sorted(ve_df["legislatura"].dropna().unique()):
        leg_df = ve_df[ve_df["legislatura"] == leg]
        if leg_df.empty:
            continue

        dates = leg_df["start_date"]
        min_date = dates.min()
        max_date = dates.max()

        # Formato compacto de periodo: "2006-07" o "2024-27"
        yr_start = str(min_date.year)[2:]
        yr_end = str(max_date.year)[2:]
        if yr_start == yr_end:
            periodo = str(min_date.year)
        else:
            periodo = f"{yr_start}-{yr_end}"

        label = f"{leg} ({periodo})"
        windows.append(
            {
                "label": label,
                "legislatura": leg,
                "start_date": min_date.strftime("%Y-%m-%d"),
                "end_date": max_date.strftime("%Y-%m-%d"),
                "vote_event_ids": leg_df["id"].tolist(),
                "n_events": len(leg_df),
            }
        )

    return windows


def _build_biennium_windows(ve_df: pd.DataFrame) -> list[dict]:
    """Ventanas de 2 años calendario por fecha."""
    min_year = ve_df["start_date"].dt.year.min()
    max_year = ve_df["start_date"].dt.year.max()

    # Redondear al año par más cercano (inicio de biennio)
    start_year = min_year if min_year % 2 == 0 else min_year - 1

    windows = []
    year = start_year
    while year <= max_year:
        start = pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year + 1}-12-31")
        mask = (ve_df["start_date"] >= start) & (ve_df["start_date"] <= end)
        chunk = ve_df[mask]

        if not chunk.empty:
            label = f"{year}-{year + 1}"
            windows.append(
                {
                    "label": label,
                    "legislatura": "",
                    "start_date": chunk["start_date"].min().strftime("%Y-%m-%d"),
                    "end_date": chunk["start_date"].max().strftime("%Y-%m-%d"),
                    "vote_event_ids": chunk["id"].tolist(),
                    "n_events": len(chunk),
                }
            )

        year += 2

    return windows


def _build_cross_sliding_windows(
    ve_df: pd.DataFrame,
    window_size: int,
    overlap: int | None,
) -> list[dict]:
    """Ventanas deslizantes sobre TODOS los vote_events (cross-legislatura)."""
    if overlap is None:
        overlap = 0

    if overlap >= window_size:
        raise ValueError(f"overlap ({overlap}) debe ser menor que window_size ({window_size})")

    step = window_size - overlap
    n = len(ve_df)
    windows = []

    start = 0
    idx = 1
    while start < n:
        end = min(start + window_size, n)
        chunk = ve_df.iloc[start:end]

        label = f"W{idx} ({chunk['start_date'].iloc[0].strftime('%Y-%m')}"
        label += f" a {chunk['start_date'].iloc[-1].strftime('%Y-%m')})"

        windows.append(
            {
                "label": label,
                "legislatura": "",
                "start_date": chunk["start_date"].min().strftime("%Y-%m-%d"),
                "end_date": chunk["start_date"].max().strftime("%Y-%m-%d"),
                "vote_event_ids": chunk["id"].tolist(),
                "n_events": len(chunk),
            }
        )

        start += step
        idx += 1

    return windows


def analyze_windows(
    db_path: str,
    windows: list[dict],
    min_votes: int = 10,
    camara: str | None = None,
) -> dict:
    """Analizar cada ventana: matriz, grafo, comunidades, métricas.

    Carga los datos una sola vez y filtra por ventana, reutilizando
    todas las funciones de covotacion.py y comunidades.py.

    Args:
        db_path: ruta al archivo SQLite (congreso.db).
        windows: lista de ventanas (de build_windows).
        min_votes: mínimo de votos para elegibilidad de legislador.
        camara: Filtrar por cámara. ``'D'`` para Diputados, ``'S'`` para
            Senado. Si es ``None``, no filtra.

    Returns:
        Dict label → {matrix, graph, partition, metrics,
                       community_analysis, party_map, org_map, window}.
    """
    if not windows:
        logger.warning("No hay ventanas para analizar")
        return {}

    # Cargar datos una sola vez
    votes_df, persons_df, org_map = load_data(db_path, camara=camara)
    logger.info("Datos cargados para análisis cross-legislatura: %d votos", len(votes_df))

    results: dict = {}

    for i, window in enumerate(windows):
        label = window["label"]
        logger.info("Analizando ventana %d/%d: %s", i + 1, len(windows), label)

        # Filtrar votos a los vote_events de esta ventana
        ve_ids = set(window["vote_event_ids"])
        window_votes = votes_df[votes_df["vote_event_id"].isin(ve_ids)].copy()

        if window_votes.empty:
            logger.warning("  Sin votos para ventana %s — saltando", label)
            continue

        # Obtener party_map para esta ventana
        party_map = get_primary_party(window_votes)

        # Construir matriz de co-votación
        matrix, legislators, co_participations = build_covotacion_matrix(
            window_votes, min_votes=min_votes
        )

        if not legislators:
            logger.warning("  Sin legisladores elegibles para %s — saltando", label)
            continue

        # Filtrar persons_df a solo los voter_ids presentes
        voter_ids_set = set(legislators)
        filtered_persons = persons_df[persons_df["id"].isin(voter_ids_set)].copy()

        # Construir grafo
        graph = build_graph(matrix, legislators, party_map, filtered_persons)

        # Calcular métricas cuantitativas
        metrics = compute_quantitative_metrics(graph, party_map, org_map)

        # Detectar comunidades
        partition = detect_communities(graph)
        graph = get_partition_as_attribute(graph, partition)

        # Analizar comunidades
        community_analysis = analyze_communities(graph, partition, party_map, org_map)

        results[label] = {
            "matrix": matrix,
            "graph": graph,
            "partition": partition,
            "metrics": metrics,
            "community_analysis": community_analysis,
            "party_map": party_map,
            "org_map": org_map,
            "window": window,
        }

        logger.info(
            "  %s: %d nodos, %d aristas, modularidad=%.4f",
            label,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            community_analysis["modularity"],
        )

    logger.info(
        "Análisis cross-legislatura completado: %d de %d ventanas procesadas",
        len(results),
        len(windows),
    )
    return results


def compute_evolution_metrics(
    window_results: dict,
) -> dict:
    """Calcular métricas de evolución cross-legislatura.

    Recibe el dict retornado por analyze_windows y calcula métricas
    de evolución para comparar entre legislaturas.

    Args:
        window_results: dict label → resultado de analyze_windows.

    Returns:
        Dict con métricas de evolución:
        - 'disciplina_por_ventana': {label: {party_short: disciplina_promedio}}
        - 'modularidad_por_ventana': {label: modularidad_float}
        - 'stability_index': {pair_label: ari_float}
        - 'frontera_coalicion_por_ventana': {label: co-votación promedio entre bloques}
        - 'densidad_por_ventana': {label: densidad_float}
        - 'disidencia_por_ventana': {label: [top5_dissidents]}
        - 'tamano_comunidades_por_ventana': {label: [tamaños ordenados desc]}
    """
    if not window_results:
        logger.warning("Sin resultados de ventanas para calcular evolución")
        return {}

    # Ordenar resultados por start_date para procesamiento secuencial
    sorted_items = sorted(
        window_results.items(),
        key=lambda item: item[1]["window"]["start_date"],
    )

    # Obtener org_map del primer resultado
    first_org_map = sorted_items[0][1]["org_map"]

    disciplina: dict[str, dict[str, float]] = {}
    modularidad: dict[str, float] = {}
    frontera_coalicion: dict[str, float] = {}
    disidencia: dict[str, list[dict]] = {}
    densidad: dict[str, float] = {}
    tamano_comunidades: dict[str, list[int]] = {}

    for label, data in sorted_items:
        graph = data["graph"]
        party_map = data["party_map"]
        org_map = data["org_map"]
        metrics = data["metrics"]
        partition = data["partition"]
        community_analysis = data["community_analysis"]

        # Disciplina: co-votación intra-partido (nombres cortos)
        intra = metrics["intra_party_avg"]
        disciplina[label] = {
            _short_party_name(org_map.get(pid, pid)): avg for pid, avg in intra.items()
        }

        # Modularidad
        modularidad[label] = community_analysis["modularity"]

        # Frontera de coalición
        frontera_coalicion[label] = _compute_coalition_frontier(graph, partition, party_map)

        # Disidencia: top 5
        disidencia[label] = _compute_top_dissidents(graph, party_map, org_map)

        # Densidad
        densidad[label] = metrics["density"]

        # Tamaño de comunidades
        sizes = list(community_analysis["community_sizes"].values())
        tamano_comunidades[label] = sorted(sizes, reverse=True)

    # Stability index: ARI entre ventanas consecutivas
    stability = _compute_cross_stability(sorted_items)

    evolution = {
        "disciplina_por_ventana": disciplina,
        "modularidad_por_ventana": modularidad,
        "stability_index": stability,
        "frontera_coalicion_por_ventana": frontera_coalicion,
        "densidad_por_ventana": densidad,
        "disidencia_por_ventana": disidencia,
        "tamano_comunidades_por_ventana": tamano_comunidades,
    }

    logger.info(
        "Métricas de evolución cross-legislatura calculadas para %d ventanas",
        len(sorted_items),
    )
    return evolution


def _compute_cross_stability(
    sorted_items: list[tuple[str, dict]],
) -> dict[str, float]:
    """Calcular ARI entre particiones de ventanas consecutivas (cross-legislatura)."""
    stability: dict[str, float] = {}

    if len(sorted_items) < 2:
        return stability

    # Intentar importar sklearn
    try:
        from sklearn.metrics import adjusted_rand_score

        use_sklearn = True
    except ImportError:
        logger.warning("sklearn no disponible — usando fallback de coincidencia directa para ARI")
        use_sklearn = False

    for i in range(len(sorted_items) - 1):
        label_a, data_a = sorted_items[i]
        label_b, data_b = sorted_items[i + 1]

        pair_label = f"{label_a} → {label_b}"

        part_a = data_a["partition"]
        part_b = data_b["partition"]

        # Legisladores comunes entre ambas ventanas
        common = set(part_a.keys()) & set(part_b.keys())

        if len(common) < 2:
            stability[pair_label] = 0.0
            logger.warning(
                "Muy pocos legisladores comunes (%d) para ARI: %s",
                len(common),
                pair_label,
            )
            continue

        common = sorted(common)
        labels_a = [part_a[leg] for leg in common]
        labels_b = [part_b[leg] for leg in common]

        if use_sklearn:
            ari = adjusted_rand_score(labels_a, labels_b)
        else:
            ari = _fallback_ari(labels_a, labels_b)

        stability[pair_label] = round(ari, 4)
        logger.info(
            "  Stability %s: ARI=%.4f (%d legisladores comunes)",
            pair_label,
            ari,
            len(common),
        )

    return stability
