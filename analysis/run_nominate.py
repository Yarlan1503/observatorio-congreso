#!/usr/bin/env python3
"""
run_nominate.py — Pipeline de análisis W-NOMINATE para el Congreso de la Unión.

Ejecuta el análisis de puntos ideales NOMINATE (Poole & Rosenthal, 1985/1997)
para estimar las posiciones ideológicas de legisladores a partir de sus
patrones de votación.

Modos de ejecución:
    - by-legislatura: Ejecutar por cada legislatura individualmente
    - cross: Ejecutar con todos los datos combinados
    - both: Ambos modos (default)

Uso:
    python3 -m analysis.run_nominate
    python3 -m analysis.run_nominate --legislatura LXVI --mode by-legislatura
    python3 -m analysis.run_nominate --mode cross --dimensions 2 --maxiter 50
    python3 -m analysis.run_nominate --mode both --min-votes 20
"""

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

from analysis.nominate import (
    prepare_vote_matrix,
    run_wnominate,
)
from analysis.visualizacion_nominate import (
    generate_all_nominate_visualizations,
    plot_nominate_scatter,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Raíz del proyecto
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"
OUTPUT_DIR = Path(__file__).parent / "analisis-diputados/output/nominate"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# Mapa de argumento de cámara a filtro
CAMARA_MAP = {"diputados": "D", "senado": "S"}


def parse_args():
    """Parsear argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Análisis W-NOMINATE de puntos ideales del Congreso de la Unión",
    )
    parser.add_argument(
        "--camara",
        choices=["diputados", "senado"],
        default=None,
        help="Filtrar por cámara (diputados o senado)",
    )
    parser.add_argument(
        "--legislatura",
        default=None,
        help="Legislatura específica (default: todas)",
    )
    parser.add_argument(
        "--dimensions",
        type=int,
        default=2,
        help="Dimensiones del espacio NOMINATE (default: 2)",
    )
    parser.add_argument(
        "--maxiter",
        type=int,
        default=100,
        help="Máximo de iteraciones (default: 100)",
    )
    parser.add_argument(
        "--mode",
        default="both",
        choices=["by-legislatura", "cross", "both"],
        help="Modo de ejecución (default: both)",
    )
    parser.add_argument(
        "--min-votes",
        type=int,
        default=10,
        help="Mínimo de votos por legislador (default: 10)",
    )
    parser.add_argument(
        "--lopsided-threshold",
        type=float,
        default=0.975,
        help="Umbral para filtrar lopsided votes (0=deshabilitado, default: 0.975)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida (default: analysis/output/nominate)",
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=15,
        help="Número de workers para paralelizar NOMINATE (default: 15, 1=secuencial)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers de ejecución
# ---------------------------------------------------------------------------


def _get_legislaturas(db_path: str, camara: str | None = None) -> list[str]:
    """Obtener lista de legislaturas con vote_events en la BD.

    Args:
        db_path: Ruta al archivo SQLite.
        camara: Filtro de cámara ('D' o 'S'). Si None, todas.

    Returns:
        Lista de nombres de legislatura ordenados.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        if camara is not None:
            camara_org = "O08" if camara == "D" else "O09"
            legs_df = pd.read_sql_query(
                "SELECT DISTINCT legislatura FROM vote_event "
                "WHERE legislatura IS NOT NULL AND organization_id = ? "
                "ORDER BY legislatura",
                conn,
                params=[camara_org],
            )
        else:
            legs_df = pd.read_sql_query(
                "SELECT DISTINCT legislatura FROM vote_event "
                "WHERE legislatura IS NOT NULL ORDER BY legislatura",
                conn,
            )
    finally:
        conn.close()
    return legs_df["legislatura"].tolist()


def _run_single_legislatura(
    db_path: str,
    legislatura: str,
    dimensions: int,
    maxiter: int,
    min_votes: int,
    lopsided_threshold: float = 0.975,
    camara: str | None = None,
    n_workers: int = 1,
) -> tuple[dict, dict]:
    """Ejecutar NOMINATE para una legislatura individual.

    Args:
        db_path: Ruta al archivo SQLite.
        legislatura: Nombre de la legislatura (ej: ``'LXVI'``).
        dimensions: Número de dimensiones.
        maxiter: Máximo de iteraciones.
        min_votes: Mínimo de votos binarios por legislador.
        lopsided_threshold: Umbral para filtrar lopsided votes.
        camara: Filtro de cámara ('D' o 'S').
        n_workers: Workers para paralelizar (1=secuencial).

    Returns:
        Tupla (vote_data, nominate_result).
    """
    data = prepare_vote_matrix(
        db_path,
        legislatura=legislatura,
        min_votes=min_votes,
        lopsided_threshold=lopsided_threshold,
        camara=camara,
    )
    result = run_wnominate(
        data,
        dimensions=dimensions,
        maxiter=maxiter,
        n_workers=n_workers,
    )
    return data, result


def _run_cross_legislatura(
    db_path: str,
    dimensions: int,
    maxiter: int,
    min_votes: int,
    lopsided_threshold: float = 0.975,
    camara: str | None = None,
    n_workers: int = 1,
) -> tuple[dict, dict]:
    """Ejecutar NOMINATE con todos los datos combinados (estilo DW-NOMINATE).

    Args:
        db_path: Ruta al archivo SQLite.
        dimensions: Número de dimensiones.
        maxiter: Máximo de iteraciones.
        min_votes: Mínimo de votos binarios por legislador.
        lopsided_threshold: Umbral para filtrar lopsided votes.
        camara: Filtro de cámara ('D' o 'S').
        n_workers: Workers para paralelizar (1=secuencial).

    Returns:
        Tupla (vote_data, nominate_result) con ``legislatura_labels`` adicional
        en el resultado.
    """
    data = prepare_vote_matrix(
        db_path,
        legislatura=None,
        min_votes=min_votes,
        lopsided_threshold=lopsided_threshold,
        camara=camara,
    )
    result = run_wnominate(
        data,
        dimensions=dimensions,
        maxiter=maxiter,
        n_workers=n_workers,
    )

    # Determinar legislatura principal de cada legislador
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        placeholders = ",".join(["?"] * len(data["legislators"]))
        query = (
            "SELECT v.voter_id, ve.legislatura, COUNT(*) as n "
            "FROM vote v "
            "JOIN vote_event ve ON v.vote_event_id = ve.id "
            f"WHERE v.voter_id IN ({placeholders}) "
            "GROUP BY v.voter_id, ve.legislatura"
        )
        leg_df = pd.read_sql_query(query, conn, params=data["legislators"])
    finally:
        conn.close()

    legislatura_labels: dict[str, str] = {}
    for voter_id, group in leg_df.groupby("voter_id"):
        best = group.loc[group["n"].idxmax()]
        legislatura_labels[voter_id] = best["legislatura"]

    result["legislatura_labels"] = legislatura_labels
    return data, result


# ---------------------------------------------------------------------------
# Resumen textual
# ---------------------------------------------------------------------------


def _print_legislatura_summary(
    leg_name: str,
    data: dict,
    result: dict,
) -> None:
    """Imprimir resumen textual de una legislatura o resultado cross.

    Args:
        leg_name: Nombre identificativo (ej: ``'LXVI'`` o ``'Cross'``).
        data: Dict retornado por ``prepare_vote_matrix``.
        result: Dict retornado por ``run_wnominate``.
    """
    fit = result["fit"]
    logger.info("=== %s Legislatura ===", leg_name)
    logger.info(
        "Legisladores: %d | Votaciones: %d | Esparsidad: %.2f%%",
        data["n_legislators"],
        data["n_votes"],
        data["sparsity"] * 100,
    )
    logger.info(
        "Dimensiones: %d | β: %.2f | w: %.2f",
        result["dimensions"],
        result["beta"],
        result["w"],
    )
    logger.info("Classification Rate: %.2f%%", fit["classification_rate"] * 100)
    logger.info("APRE: %.4f", fit["apre"])
    logger.info("GMP: %.4f", fit["gmp"])
    logger.info(
        "Iteraciones: %d | Convergió: %s",
        result["n_iterations"],
        result["converged"],
    )


# ---------------------------------------------------------------------------
# Exportación CSV
# ---------------------------------------------------------------------------


def export_by_legislatura_csvs(
    results_by_leg: dict[str, tuple[dict, dict]],
    output_dir: Path,
) -> list[str]:
    """Exportar coordenadas_nominate.csv y metricas_ajuste.csv.

    Args:
        results_by_leg: Dict legislatura → (vote_data, nominate_result).
        output_dir: Directorio de salida.

    Returns:
        Lista de rutas de archivos generados.
    """
    files: list[str] = []

    # --- coordenadas_nominate.csv ---
    coord_rows: list[dict] = []
    for leg_name, (data, result) in results_by_leg.items():
        coords = result["coordinates"]
        legislators = result["legislators"]
        names = result["legislator_names"]
        parties = result["legislator_parties"]
        org_map = result["org_map"]

        for i, voter_id in enumerate(legislators):
            dim_1 = round(float(coords[i, 0]), 6)
            dim_2 = round(float(coords[i, 1]), 6) if coords.shape[1] > 1 else 0.0
            party_id = parties.get(voter_id, "")
            party_name = org_map.get(party_id, party_id)

            coord_rows.append(
                {
                    "voter_id": voter_id,
                    "nombre": names.get(voter_id, ""),
                    "partido": party_name,
                    "dim_1": dim_1,
                    "dim_2": dim_2,
                    "legislatura": leg_name,
                }
            )

    csv_coord = output_dir / "coordenadas_nominate.csv"
    pd.DataFrame(coord_rows).to_csv(csv_coord, index=False)
    logger.info("  coordenadas_nominate.csv: %s", csv_coord)
    files.append(str(csv_coord))

    # --- metricas_ajuste.csv ---
    metric_rows: list[dict] = []
    for leg_name, (data, result) in results_by_leg.items():
        fit = result["fit"]
        metric_rows.append(
            {
                "legislatura": leg_name,
                "n_legisladores": data["n_legislators"],
                "n_votaciones": data["n_votes"],
                "classification_rate": round(fit["classification_rate"], 4),
                "apre": round(fit["apre"], 4),
                "gmp": round(fit["gmp"], 4),
                "beta": round(result["beta"], 2),
                "w": round(result["w"], 2),
                "iteraciones": result["n_iterations"],
                "convergio": result["converged"],
                "lopsided_threshold": data.get("lopsided_threshold", 0.975),
            }
        )

    csv_metric = output_dir / "metricas_ajuste.csv"
    pd.DataFrame(metric_rows).to_csv(csv_metric, index=False)
    logger.info("  metricas_ajuste.csv: %s", csv_metric)
    files.append(str(csv_metric))

    return files


def export_cross_csv(
    cross_data: dict,
    cross_result: dict,
    output_dir: Path,
) -> str:
    """Exportar coordenadas_cross.csv.

    Args:
        cross_data: Dict de ``prepare_vote_matrix``.
        cross_result: Dict de ``run_wnominate`` con ``legislatura_labels``.
        output_dir: Directorio de salida.

    Returns:
        Ruta del archivo generado.
    """
    coords = cross_result["coordinates"]
    legislators = cross_result["legislators"]
    names = cross_result["legislator_names"]
    parties = cross_result["legislator_parties"]
    org_map = cross_result["org_map"]
    leg_labels = cross_result.get("legislatura_labels", {})

    rows: list[dict] = []
    for i, voter_id in enumerate(legislators):
        dim_1 = round(float(coords[i, 0]), 6)
        dim_2 = round(float(coords[i, 1]), 6) if coords.shape[1] > 1 else 0.0
        party_id = parties.get(voter_id, "")
        party_name = org_map.get(party_id, party_id)

        rows.append(
            {
                "voter_id": voter_id,
                "nombre": names.get(voter_id, ""),
                "partido": party_name,
                "legislatura": leg_labels.get(voter_id, ""),
                "dim_1": dim_1,
                "dim_2": dim_2,
            }
        )

    csv_path = output_dir / "coordenadas_cross.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    logger.info("  coordenadas_cross.csv: %s", csv_path)
    return str(csv_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Punto de entrada principal del pipeline NOMINATE."""
    args = parse_args()
    t_start = time.time()

    # Paths
    db_path = str(DB_PATH)
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    camara = CAMARA_MAP.get(args.camara) if args.camara else None

    # Banner de inicio
    logger.info("=" * 60)
    logger.info("=== ANÁLISIS W-NOMINATE — CONGRESO DE LA UNIÓN ===")
    logger.info("BD: %s", DB_PATH)
    logger.info("Output: %s", output_dir)
    logger.info(
        "Modo: %s | Dimensiones: %d | MaxIter: %d | MinVotes: %d | Lopsided: %.3f | Workers: %d",
        args.mode,
        args.dimensions,
        args.maxiter,
        args.min_votes,
        args.lopsided_threshold,
        args.n_workers,
    )
    if args.legislatura:
        logger.info("Legislatura: %s", args.legislatura)
    logger.info("=" * 60)

    # Verificar BD
    if not DB_PATH.exists():
        logger.error("Base de datos no encontrada: %s", DB_PATH)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Determinar legislaturas a procesar
    if args.legislatura:
        legislaturas = [args.legislatura]
    else:
        legislaturas = _get_legislaturas(db_path, camara=camara)

    if not legislaturas:
        logger.error("No se encontraron legislaturas en la base de datos")
        sys.exit(1)

    logger.info("Legislaturas a procesar: %s", ", ".join(legislaturas))

    all_files: list[str] = []

    # ================================================================
    # MODO BY-LEGISLATURA
    # ================================================================
    results_by_leg: dict[str, tuple[dict, dict]] = {}

    if args.mode in ("by-legislatura", "both"):
        logger.info("\n--- MODO BY-LEGISLATURA ---")

        for leg in legislaturas:
            try:
                data, result = _run_single_legislatura(
                    db_path,
                    leg,
                    args.dimensions,
                    args.maxiter,
                    args.min_votes,
                    args.lopsided_threshold,
                    camara=camara,
                    n_workers=args.n_workers,
                )
                results_by_leg[leg] = (data, result)
                _print_legislatura_summary(leg, data, result)
                logger.info("")
            except ValueError as e:
                logger.warning(
                    "Legislatura %s omitida (datos insuficientes): %s",
                    leg,
                    e,
                )

        if results_by_leg:
            # Visualizaciones
            logger.info("Generando visualizaciones by-legislatura...")
            viz_results = {leg: r for leg, (d, r) in results_by_leg.items()}
            viz_files = generate_all_nominate_visualizations(
                viz_results,
                str(output_dir),
            )
            all_files.extend(viz_files.values())
            logger.info("Visualizaciones generadas: %d", len(viz_files))

            # CSVs
            logger.info("\nExportando CSVs by-legislatura...")
            csv_files = export_by_legislatura_csvs(results_by_leg, output_dir)
            all_files.extend(csv_files)
        else:
            logger.warning("Ninguna legislatura produjo resultados válidos")

    # ================================================================
    # MODO CROSS-LEGISLATURA
    # ================================================================
    if args.mode in ("cross", "both"):
        logger.info("\n--- MODO CROSS-LEGISLATURA ---")

        try:
            cross_data, cross_result = _run_cross_legislatura(
                db_path,
                args.dimensions,
                args.maxiter,
                args.min_votes,
                args.lopsided_threshold,
                camara=camara,
                n_workers=args.n_workers,
            )

            # Resumen textual
            _print_legislatura_summary("Cross", cross_data, cross_result)

            # Scatter plot
            logger.info("\nGenerando scatter cross-legislatura...")
            scatter_path = plot_nominate_scatter(
                cross_result,
                str(output_dir),
                legislatura_label="cross",
            )
            if scatter_path:
                all_files.append(scatter_path)

            # CSV
            logger.info("\nExportando CSV cross-legislatura...")
            cross_csv = export_cross_csv(
                cross_data,
                cross_result,
                output_dir,
            )
            all_files.append(cross_csv)

        except ValueError as e:
            logger.error(
                "Cross-legislatura falló (datos insuficientes): %s",
                e,
            )

    # ================================================================
    # RESUMEN FINAL
    # ================================================================
    t_elapsed = time.time() - t_start

    # Estadísticas agregadas
    n_legs_processed = len(results_by_leg)
    total_unique_legislators: set[str] = set()
    avg_class_rate = 0.0

    if results_by_leg:
        class_rates: list[float] = []
        for _leg_name, (data, result) in results_by_leg.items():
            total_unique_legislators.update(result["legislators"])
            class_rates.append(result["fit"]["classification_rate"])
        avg_class_rate = sum(class_rates) / len(class_rates) if class_rates else 0.0

    logger.info("\n" + "=" * 60)
    logger.info("=== ANÁLISIS W-NOMINATE COMPLETADO ===")
    logger.info("Legislaturas procesadas: %d", n_legs_processed)
    logger.info("Legisladores únicos: %d", len(total_unique_legislators))
    logger.info("Classification rate promedio: %.2f%%", avg_class_rate * 100)
    logger.info("Tiempo total: %.1f segundos", t_elapsed)
    logger.info("Archivos generados (%d):", len(all_files))
    for f in all_files:
        logger.info("  %s", f)
    logger.info("=" * 60)

    return {
        "results_by_leg": results_by_leg,
        "files_generated": all_files,
        "elapsed_seconds": t_elapsed,
    }


if __name__ == "__main__":
    main()
