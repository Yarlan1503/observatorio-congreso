#!/usr/bin/env python3
"""
Análisis de grafos de co-votación - LXVI Legislatura
Ejecuta: python -m analysis.run_analysis
O: python analysis/run_analysis.py
"""

import sys
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Raíz del proyecto
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    logger.info("=== ANÁLISIS DE CO-VOTACIÓN LXVI LEGISLATURA ===")
    logger.info(f"BD: {DB_PATH}")
    logger.info(f"Output: {OUTPUT_DIR}")

    # --- FASE 1: Carga de datos y construcción del grafo ---
    # IMPORTAR al inicio de la función para evitar circular imports:
    from analysis.covotacion import (
        load_data,
        normalize_party,
        get_primary_party,
        build_covotacion_matrix,
        build_graph,
        compute_quantitative_metrics,
    )

    logger.info("Cargando datos...")
    votes_df, persons_df, org_map = load_data(str(DB_PATH))
    logger.info(f"  Votos: {len(votes_df)} registros")
    logger.info(f"  Personas: {len(persons_df)}")
    logger.info(f"  Organizaciones: {len(org_map)} partidos")

    party_map = get_primary_party(votes_df)
    logger.info(f"  Legisladores con partido asignado: {len(party_map)}")

    logger.info("Construyendo matriz de co-votación...")
    matrix, legislators, co_participations = build_covotacion_matrix(
        votes_df, min_votes=10
    )
    logger.info(f"  Legisladores elegibles: {len(legislators)}")
    logger.info(f"  Matriz: {matrix.shape}")

    logger.info("Construyendo grafo...")
    graph = build_graph(matrix, legislators, party_map, persons_df)
    logger.info(f"  Nodos: {graph.number_of_nodes()}")
    logger.info(f"  Aristas: {graph.number_of_edges()}")

    # --- FASE 2: Métricas cuantitativas ---
    logger.info("Calculando métricas cuantitativas...")
    metrics = compute_quantitative_metrics(graph, party_map, org_map)
    logger.info(f"  Densidad: {metrics['density']:.4f}")
    logger.info(f"  Peso promedio: {metrics['avg_weight']:.4f}")
    logger.info(f"  Número de aristas: {metrics['num_edges']}")

    # --- FASE 3: Centralidad ---
    from analysis.centralidad import (
        compute_all_centrality,
        top_n_centrality,
        add_centrality_to_graph,
    )

    logger.info("Calculando centralidad...")
    centrality = compute_all_centrality(graph)
    graph = add_centrality_to_graph(graph, centrality)

    top_degree = top_n_centrality(
        centrality["degree"], persons_df, party_map, org_map, n=10
    )
    top_betweenness = top_n_centrality(
        centrality["betweenness"], persons_df, party_map, org_map, n=10
    )

    logger.info("\n=== TOP 10 DEGREE CENTRALITY ===")
    for entry in top_degree:
        logger.info(
            f"  {entry['rank']}. {entry['nombre']} ({entry['partido']}) - {entry['score']:.4f}"
        )

    logger.info("\n=== TOP 10 BETWEENNESS CENTRALITY ===")
    for entry in top_betweenness:
        logger.info(
            f"  {entry['rank']}. {entry['nombre']} ({entry['partido']}) - {entry['score']:.4f}"
        )

    # --- FASE 4: Comunidades ---
    from analysis.comunidades import (
        detect_communities,
        analyze_communities,
        get_partition_as_attribute,
    )

    logger.info("Detectando comunidades (Louvain)...")
    partition = detect_communities(graph)
    graph = get_partition_as_attribute(graph, partition)
    community_analysis = analyze_communities(graph, partition, party_map, org_map)

    logger.info(f"  Comunidades detectadas: {community_analysis['num_communities']}")
    logger.info(f"  Modularidad: {community_analysis['modularity']:.4f}")
    logger.info(f"  Tamaños: {community_analysis['community_sizes']}")

    logger.info("\n=== COMPOSICIÓN POR COMUNIDAD ===")
    for comm_id, composition in community_analysis["community_composition"].items():
        total = sum(composition.values())
        dominant = max(composition, key=composition.get)
        logger.info(
            f"  Comunidad {comm_id} ({total} legisladores, {dominant} dominante):"
        )
        for party, count in sorted(composition.items(), key=lambda x: -x[1]):
            logger.info(f"    {party}: {count} ({count / total * 100:.1f}%)")

    if community_analysis["cross_party_legislators"]:
        logger.info(
            f"\n  Legisladores en comunidad inesperada: {len(community_analysis['cross_party_legislators'])}"
        )
        for leg in community_analysis["cross_party_legislators"][:10]:
            logger.info(
                f"    {leg['name']} ({leg['own_party']}) → Comunidad {leg['community_id']} (dominante: {leg['dominant_party']})"
            )

    if community_analysis["sub_blocks_morena"]:
        logger.info("\n  Sub-bloques MORENA:")
        for block in community_analysis["sub_blocks_morena"]:
            logger.info(
                f"    Comunidad {block['community_id']}: {block['size']} legisladores MORENA ({block['proportion_of_morena'] * 100:.1f}% del total MORENA)"
            )

    # --- FASE 5: Top/Bottom pares ---
    logger.info("\n=== TOP 20 PARES CROSS-PARTY (alianza cruzada) ===")
    for pair in metrics["top20_cross_party"]:
        logger.info(
            f"  {pair['name_a']} ({pair['party_a']}) <-> {pair['name_b']} ({pair['party_b']}): {pair['weight']:.4f}"
        )

    logger.info("\n=== BOTTOM 20 PARES INTRA-PARTY (disidencia) ===")
    for pair in metrics["bottom20_same_party"]:
        logger.info(
            f"  {pair['name_a']} ({pair['party_a']}) <-> {pair['name_b']} ({pair['party_b']}): {pair['weight']:.4f}"
        )

    # --- FASE 6: Co-votación intra/inter partido ---
    logger.info("\n=== CO-VOTACIÓN PROMEDIO INTRA-PARTIDO ===")
    for party_id, avg in metrics["intra_party_avg"].items():
        party_name = org_map.get(party_id, party_id)
        logger.info(f"  {party_name}: {avg:.4f}")

    logger.info("\n=== MATRIZ PARTIDO × PARTIDO ===")
    party_matrix = metrics["party_matrix"]
    logger.info(f"\n{party_matrix.to_string()}")

    # --- FASE 7: Visualizaciones y exportación ---
    from analysis.visualizacion import generate_all_visualizations

    logger.info("\nGenerando visualizaciones y exports...")
    viz_results = generate_all_visualizations(graph, metrics, str(OUTPUT_DIR))
    for name, path in viz_results.items():
        logger.info(f"  {name}: {path}")

    # --- FASE 8: Exportar CSVs ---
    import pandas as pd

    # CSV: matriz partido × partido
    party_csv = OUTPUT_DIR / "matriz_partidos.csv"
    party_matrix.to_csv(party_csv)
    logger.info(f"  CSV partidos: {party_csv}")

    # CSV: métricas por legislador
    legislator_data = []
    for node_id in graph.nodes():
        attrs = graph.nodes[node_id]
        legislator_data.append(
            {
                "legislator_id": node_id,
                "nombre": attrs.get("nombre", ""),
                "partido": attrs.get("party_name", ""),
                "partido_id": attrs.get("party_id", ""),
                "comunidad": attrs.get("community", ""),
                "degree_centrality": attrs.get("degree_centrality", 0),
                "betweenness_centrality": attrs.get("betweenness_centrality", 0),
            }
        )

    # Añadir co-votación intra/inter partido
    for ld in legislator_data:
        pid = ld["partido_id"]
        ld["covotacion_intra_partido"] = metrics["intra_party_avg"].get(pid, 0)
        # Promedio inter-partido: promedio de co-votación con TODOS los demás partidos
        inter_vals = []
        for other_pid, other_name in org_map.items():
            if other_pid != pid:
                key = tuple(sorted([pid, other_pid]))
                inter_vals.append(metrics["inter_party_avg"].get(key, 0))
        ld["covotacion_inter_partido_prom"] = (
            sum(inter_vals) / len(inter_vals) if inter_vals else 0
        )

    legislators_csv = OUTPUT_DIR / "metricas_legisladores.csv"
    pd.DataFrame(legislator_data).to_csv(legislators_csv, index=False)
    logger.info(f"  CSV legisladores: {legislators_csv}")

    # --- RESUMEN FINAL ---
    logger.info("\n" + "=" * 60)
    logger.info("=== ANÁLISIS COMPLETADO ===")
    logger.info(f"Legisladores analizados: {metrics['num_legislators']}")
    logger.info(f"Aristas en el grafo: {metrics['num_edges']}")
    logger.info(f"Densidad: {metrics['density']:.4f}")
    logger.info(f"Peso promedio aristas: {metrics['avg_weight']:.4f}")
    logger.info(f"Comunidades detectadas: {community_analysis['num_communities']}")
    logger.info(f"Modularidad: {community_analysis['modularity']:.4f}")
    logger.info(f"Archivos generados en: {OUTPUT_DIR}")
    logger.info("=" * 60)

    return {
        "graph": graph,
        "metrics": metrics,
        "centrality": centrality,
        "partition": partition,
        "community_analysis": community_analysis,
    }


if __name__ == "__main__":
    main()
