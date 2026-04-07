#!/usr/bin/env python3
"""
Análisis dinámico de grafos de co-votación — Pipeline cross-legislatura.

Ejecuta:
    python3 -m analysis.run_covotacion_dinamica
    python3 -m analysis.run_covotacion_dinamica --strategy biennium
    python3 -m analysis.run_covotacion_dinamica --strategy sliding --window-size 200 --overlap 50
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from analysis.covotacion_dinamica import (
    analyze_windows,
    build_windows,
    compute_evolution_metrics,
)
from analysis.visualizacion_dinamica import generate_all_dynamic_visualizations

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Raíz del proyecto
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"
OUTPUT_DIR = Path(__file__).parent / "analisis-diputados/output/dinamica"


# Mapa de argumento de cámara a filtro
CAMARA_MAP = {"diputados": "D", "senado": "S"}


def parse_args():
    """Parsear argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Análisis dinámico cross-legislatura de grafos de co-votación",
    )
    parser.add_argument(
        "--camara",
        choices=["diputados", "senado"],
        default=None,
        help="Filtrar por cámara (diputados o senado)",
    )
    parser.add_argument(
        "--strategy",
        default="legislatura",
        choices=["legislatura", "biennium", "sliding"],
        help="Estrategia de ventanas temporales (default: legislatura)",
    )
    parser.add_argument(
        "--min-events",
        type=int,
        default=30,
        help="Mínimo de votaciones por ventana (default: 30)",
    )
    parser.add_argument(
        "--min-votes",
        type=int,
        default=10,
        help="Mínimo de votos para elegibilidad de legislador (default: 10)",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=None,
        help="Tamaño de ventana (solo sliding)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=None,
        help="Overlap entre ventanas (solo sliding)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida (default: analysis/analisis-diputados/output/dinamica)",
    )
    return parser.parse_args()


def export_csvs(window_results: dict, evolution: dict, output_dir: Path):
    """Exportar 3 CSVs: evolución métricas, disciplina partidista, stability index.

    Args:
        window_results: Dict label → resultado de analyze_windows.
        evolution: Dict de compute_evolution_metrics.
        output_dir: Directorio donde guardar los CSVs.
    """
    # --- CSV 1: evolucion_metricas.csv — una fila por ventana ---
    rows = []
    for label, data in window_results.items():
        w = data["window"]
        m = data["metrics"]
        ca = data["community_analysis"]
        rows.append(
            {
                "ventana": label,
                "legislatura": w.get("legislatura", ""),
                "fecha_inicio": w["start_date"],
                "fecha_fin": w["end_date"],
                "n_eventos": len(w["vote_event_ids"]),
                "n_legisladores": m["num_legislators"],
                "n_aristas": m["num_edges"],
                "densidad": round(m["density"], 6),
                "peso_promedio": round(m["avg_weight"], 6),
                "modularidad": round(ca["modularity"], 6),
                "n_comunidades": ca["num_communities"],
                "frontera_coalicion": round(
                    evolution.get("frontera_coalicion_por_ventana", {}).get(label, 0),
                    6,
                ),
            }
        )

    csv_metrics = output_dir / "evolucion_metricas.csv"
    pd.DataFrame(rows).to_csv(csv_metrics, index=False)
    logger.info("  evolucion_metricas.csv: %s", csv_metrics)

    # --- CSV 2: disciplina_partidista.csv — partido × ventana ---
    disc = evolution.get("disciplina_por_ventana", {})
    if disc:
        disc_df = pd.DataFrame(disc).T
        disc_df.index.name = "partido"
        csv_disc = output_dir / "disciplina_partidista.csv"
        disc_df.to_csv(csv_disc)
        logger.info("  disciplina_partidista.csv: %s", csv_disc)

    # --- CSV 3: stability_index.csv — pares de ventanas con ARI ---
    stability = evolution.get("stability_index", {})
    if stability:
        stab_rows = []
        for pair, ari in stability.items():
            parts = pair.split(" → ")
            stab_rows.append(
                {
                    "periodo_origen": parts[0] if len(parts) == 2 else pair,
                    "periodo_destino": parts[1] if len(parts) == 2 else "",
                    "ari": round(ari, 6),
                }
            )
        csv_stab = output_dir / "stability_index.csv"
        pd.DataFrame(stab_rows).to_csv(csv_stab, index=False)
        logger.info("  stability_index.csv: %s", csv_stab)


def main():
    args = parse_args()

    # Resolve paths and camara
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    camara = CAMARA_MAP.get(args.camara) if args.camara else None

    # 1. Banner de inicio
    logger.info("=" * 60)
    logger.info("=== ANÁLISIS DINÁMICO CROSS-LEGISLATURA ===")
    logger.info("BD: %s", DB_PATH)
    logger.info("Output: %s", output_dir)
    logger.info(
        "Estrategia: %s | min_events: %d | min_votes: %d | camara: %s",
        args.strategy,
        args.min_events,
        args.min_votes,
        camara or "todas",
    )
    logger.info("=" * 60)

    # 2. Verificar BD
    if not DB_PATH.exists():
        logger.error("Base de datos no encontrada: %s", DB_PATH)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # 3. FASE 1: Construir ventanas
    logger.info("\n--- FASE 1: Construyendo ventanas temporales ---")
    windows = build_windows(
        str(DB_PATH),
        strategy=args.strategy,
        min_events=args.min_events,
        window_size=args.window_size,
        overlap=args.overlap,
        camara=camara,
    )

    if not windows:
        logger.error("No se generaron ventanas temporales. Abortando.")
        sys.exit(1)

    logger.info("\nVentanas generadas (%d):", len(windows))
    for w in windows:
        logger.info(
            "  %s | %s | %d eventos | %s a %s",
            w["label"],
            w.get("legislatura", "?"),
            len(w["vote_event_ids"]),
            w["start_date"],
            w["end_date"],
        )

    # 4. FASE 2: Analizar ventanas
    logger.info("\n--- FASE 2: Construyendo grafos por ventana ---")
    window_results = analyze_windows(
        str(DB_PATH),
        windows,
        min_votes=args.min_votes,
        camara=camara,
    )

    if not window_results:
        logger.error("No se construyeron grafos. Abortando.")
        sys.exit(1)

    logger.info("\nGrafos construidos exitosamente:")
    for label, data in window_results.items():
        g = data["graph"]
        ca = data["community_analysis"]
        logger.info(
            "  %s: %d legisladores, %d aristas, densidad=%.4f, modularidad=%.4f, %d comunidades",
            label,
            g.number_of_nodes(),
            g.number_of_edges(),
            data["metrics"]["density"],
            ca["modularity"],
            ca["num_communities"],
        )

    # 5. FASE 3: Métricas de evolución
    logger.info("\n--- FASE 3: Calculando métricas de evolución ---")
    evolution = compute_evolution_metrics(window_results)

    # Print disciplina
    logger.info("\nDisciplina partidista por ventana:")
    for label, parties in evolution.get("disciplina_por_ventana", {}).items():
        logger.info("  %s:", label)
        for party, val in sorted(parties.items(), key=lambda x: -x[1]):
            logger.info("    %s: %.4f", party, val)

    # Print modularidad
    logger.info("\nModularidad por ventana:")
    for label, mod in evolution.get("modularidad_por_ventana", {}).items():
        logger.info("  %s: %.4f", label, mod)

    # Print densidad
    logger.info("\nDensidad por ventana:")
    for label, dens in evolution.get("densidad_por_ventana", {}).items():
        logger.info("  %s: %.4f", label, dens)

    # Print stability
    logger.info("\nStability Index (ARI entre ventanas consecutivas):")
    for pair, ari in evolution.get("stability_index", {}).items():
        logger.info("  %s: %.4f", pair, ari)

    # Print frontera coalición
    logger.info("\nFrontera de coalición por ventana:")
    for label, frontier in evolution.get("frontera_coalicion_por_ventana", {}).items():
        logger.info("  %s: %.4f", label, frontier)

    # Print disidentes
    logger.info("\nTop 5 disidentes por ventana:")
    for label, dissidents in evolution.get("disidencia_por_ventana", {}).items():
        logger.info("  %s:", label)
        for d in dissidents:
            logger.info(
                "    %s (%s): co-votación intra=%.4f",
                d["nombre"],
                d["partido"],
                d["covotacion_intra"],
            )

    # 6. FASE 4: Visualizaciones
    logger.info("\n--- FASE 4: Generando visualizaciones ---")
    viz_files = generate_all_dynamic_visualizations(
        window_results,
        evolution,
        str(output_dir),
    )
    logger.info("Archivos generados:")
    for name, path in viz_files.items():
        logger.info("  %s: %s", name, path)

    # 7. FASE 5: Exportar CSVs
    logger.info("\n--- FASE 5: Exportando CSVs ---")
    export_csvs(window_results, evolution, output_dir)

    # 8. RESUMEN FINAL
    logger.info("\n" + "=" * 60)
    logger.info("=== ANÁLISIS DINÁMICO CROSS-LEGISLATURA COMPLETADO ===")
    logger.info("Estrategia: %s | Ventanas: %d", args.strategy, len(window_results))
    logger.info("Archivos en: %s", output_dir)
    logger.info("=" * 60)

    return {
        "window_results": window_results,
        "evolution": evolution,
        "viz_files": viz_files,
    }


if __name__ == "__main__":
    main()
