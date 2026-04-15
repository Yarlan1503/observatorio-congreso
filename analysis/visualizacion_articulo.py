#!/usr/bin/env python3
"""
visualizacion_articulo.py — Visualizaciones específicas para el artículo
"El congreso congelado: cómo la LXVI Legislatura rigidizó el mapa de alianzas".
"""

import logging
import sys
from glob import glob as _glob
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.constants import ORG_TO_SHORT, PARTY_ORDER

logger = logging.getLogger(__name__)

# Directorios
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "analysis" / "output" / "dinamica"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "images"
GRAFOS_DIR = DATA_DIR / "grafos"


# ---------------------------------------------------------------------------
# Función 1: ARI Evolution — bar chart
# ---------------------------------------------------------------------------


def plot_ari_evolution(output_dir: Path) -> str:
    """Bar chart de Adjusted Rand Index entre legislaturas consecutivas."""
    csv_path = DATA_DIR / "stability_index.csv"
    df = pd.read_csv(csv_path)

    labels = ["LX+→LXII", "LXII→LXIII", "LXIII→LXIV", "LXIV→LXV", "LXV→LXVI"]
    ari_values = df["ari"].tolist()
    colors = ["#CCCCCC", "#CCCCCC", "#CCCCCC", "#003399", "#8B0000"]

    # Legisladores comunes (hardcodeados del análisis previo)
    legisladores_comunes = {
        3: "132 legisladores\ncomunes",
        4: "99 legisladores\ncomunes",
    }

    fig, ax = plt.subplots(figsize=(10, 6), dpi=200)

    bars = ax.bar(range(len(labels)), ari_values, color=colors, edgecolor="white", linewidth=0.5)

    # Anotar valor ARI sobre cada barra
    for i, (bar, val) in enumerate(zip(bars, ari_values)):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
        # Anotar legisladores comunes para barras 4 y 5
        if i in legisladores_comunes:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.07,
                legisladores_comunes[i],
                ha="center",
                va="bottom",
                fontsize=8,
                color="#555555",
            )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("ARI", fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.set_title(
        "Adjusted Rand Index entre legislaturas consecutivas",
        fontsize=13,
        fontweight="bold",
        pad=30,
    )
    ax.text(
        0.5,
        1.03,
        "0 = reinicio total  |  1 = comunidades idénticas",
        transform=ax.transAxes,
        fontsize=10,
        style="italic",
        color="#666666",
        ha="center",
        va="bottom",
    )
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    out_path = output_dir / "ari_evolution.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


# ---------------------------------------------------------------------------
# Función 2: Frontera de coalición — line chart
# ---------------------------------------------------------------------------


def plot_frontera_coalicion(output_dir: Path) -> str:
    """Line chart de la frontera de coalición por legislatura."""
    csv_path = DATA_DIR / "evolucion_metricas.csv"
    df = pd.read_csv(csv_path)

    x_labels = ["LX+", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]
    y_values = df["frontera_coalicion"].tolist()

    fig, ax = plt.subplots(figsize=(10, 6), dpi=200)

    x = np.arange(len(x_labels))

    # Área sombreada
    ax.fill_between(x, y_values, alpha=0.15, color="#2C3E50")

    # Línea principal
    ax.plot(x, y_values, "-o", color="#2C3E50", linewidth=2.5, markersize=7, zorder=5)

    # Línea horizontal de independencia estadística
    ax.axhline(
        y=0.5,
        color="#E74C3C",
        linestyle="--",
        linewidth=1.0,
        label="Independencia estadística",
    )

    # Anotar valores en cada punto
    for i, val in enumerate(y_values):
        ax.annotate(
            f"{val:.2f}",
            xy=(i, val),
            xytext=(0, 10),
            textcoords="offset points",
            fontsize=9,
            ha="center",
        )

    # Anotación de la caída LXV→LXVI
    ax.annotate(
        "−0.30\n(caída más grande\nde la serie)",
        xy=(5, 0.497),
        xytext=(4.2, 0.60),
        fontsize=9,
        fontweight="bold",
        color="#E74C3C",
        arrowprops=dict(arrowstyle="->", color="#E74C3C", lw=1.5),
        ha="center",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=10)
    ax.set_ylabel("Co-votación inter-bloque", fontsize=11)
    ax.set_ylim(0.4, 1.0)
    ax.set_title(
        "Evolución de la frontera de coalición",
        fontsize=13,
        fontweight="bold",
    )
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9, loc="upper right")

    plt.tight_layout()
    out_path = output_dir / "frontera_coalicion_timeline.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


# ---------------------------------------------------------------------------
# Función 3: Heatmap inter-bloque
# ---------------------------------------------------------------------------


def _get_inter_party_data():
    """Intentar obtener datos inter_party_avg del pipeline."""
    try:
        from analysis.covotacion_dinamica import analyze_windows, build_windows

        db_path = PROJECT_ROOT / "db" / "congreso.db"
        if not db_path.exists():
            logger.warning("BD no encontrada, usando fallback para heatmap")
            return None
        windows = build_windows(str(db_path), strategy="legislatura", min_events=30)
        window_results = analyze_windows(str(db_path), windows, min_votes=10)
        # Extraer inter_party_avg por ventana
        data = {}
        for label, result in window_results.items():
            inter_avg = result["metrics"].get("inter_party_avg", {})
            intra_avg = result["metrics"].get("intra_party_avg", {})
            # Convertir keys de (org_id_a, org_id_b) a (short_name_a, short_name_b)
            converted_inter = {}
            for (org_a, org_b), avg in inter_avg.items():
                short_a = ORG_TO_SHORT.get(org_a, org_a)
                short_b = ORG_TO_SHORT.get(org_b, org_b)
                converted_inter[tuple(sorted([short_a, short_b]))] = avg

            converted_intra = {}
            for org_id, avg in intra_avg.items():
                short = ORG_TO_SHORT.get(org_id, org_id)
                converted_intra[short] = avg

            data[label] = {"inter": converted_inter, "intra": converted_intra}
        return data
    except Exception as e:
        logger.warning("Pipeline falló para heatmap inter-bloque: %s", e)
        return None


def _get_window_sort_key(label: str) -> str:
    """Obtener una clave de ordenamiento cronológico para labels de ventana."""
    abbr_map = {
        "LX+": "01_LX+",
        "LXII": "02_LXII",
        "LXIII": "03_LXIII",
        "LXIV": "04_LXIV",
        "LXV": "05_LXV",
        "LXVI": "06_LXVI",
    }
    for key, val in abbr_map.items():
        if key in label:
            return val
    return label


def _abbreviate_label(label: str) -> str:
    """Acortar label de ventana a versión abreviada."""
    if "LX+" in label or "LX+LXI" in label:
        return "LX+"
    for abbr in ["LXVI", "LXV", "LXIV", "LXIII", "LXII"]:
        if abbr in label:
            return abbr
    # Fallback: primera palabra antes del espacio
    return label.split()[0] if label else label


def plot_heatmap_inter_bloque(output_dir: Path) -> str:
    """Grid de heatmaps partido × partido por legislatura."""
    data = _get_inter_party_data()

    if data is not None and len(data) >= 4:
        _plot_heatmap_grid(data, output_dir)
    else:
        logger.info("Usando fallback de barras para heatmap inter-bloque")
        _plot_heatmap_fallback(output_dir)

    return str(output_dir / "heatmap_inter_bloque.png")


def _plot_heatmap_grid(data: dict, output_dir: Path):
    """Heatmap grid usando datos inter_party_avg del pipeline."""
    # Ordenar ventanas cronológicamente
    sorted_labels = sorted(data.keys(), key=_get_window_sort_key)
    n_windows = len(sorted_labels)

    # Determinar partidos presentes en todos los datos
    all_parties = set()
    for label in sorted_labels:
        for a, b in data[label]["inter"]:
            all_parties.add(a)
            all_parties.add(b)
        for p in data[label]["intra"]:
            all_parties.add(p)

    # Filtrar a partidos principales (excluir Independientes y los muy pequeños)
    main_parties = [p for p in PARTY_ORDER if p in all_parties]
    if not main_parties:
        main_parties = sorted(all_parties)

    n_parties = len(main_parties)

    fig, axes = plt.subplots(1, n_windows, figsize=(18, 5), dpi=200)
    if n_windows == 1:
        axes = [axes]

    for idx, label in enumerate(sorted_labels):
        ax = axes[idx]
        window_data = data[label]

        # Construir matriz
        matrix = np.full((n_parties, n_parties), np.nan)
        for i, pi in enumerate(main_parties):
            for j, pj in enumerate(main_parties):
                if i == j:
                    val = window_data["intra"].get(pi, np.nan)
                    matrix[i, j] = val
                else:
                    key = tuple(sorted([pi, pj]))
                    val = window_data["inter"].get(key, np.nan)
                    matrix[i, j] = val

        im = ax.imshow(matrix, cmap="RdYlBu_r", vmin=0.3, vmax=1.0, aspect="equal")

        # Anotar valores en celdas
        for i in range(n_parties):
            for j in range(n_parties):
                val = matrix[i, j]
                if not np.isnan(val):
                    color = "white" if val > 0.75 else "black"
                    ax.text(
                        j,
                        i,
                        f"{val:.2f}",
                        ha="center",
                        va="center",
                        fontsize=7,
                        color=color,
                    )

        ax.set_xticks(range(n_parties))
        ax.set_yticks(range(n_parties))
        ax.set_xticklabels(main_parties, fontsize=7, rotation=45, ha="right")
        ax.set_yticklabels(main_parties, fontsize=7)
        ax.set_title(_abbreviate_label(label), fontsize=10, fontweight="bold")

    # Colorbar
    fig.subplots_adjust(right=0.92)
    cbar_ax = fig.add_axes([0.93, 0.15, 0.015, 0.7])
    fig.colorbar(im, cax=cbar_ax, label="Co-votación promedio")

    fig.suptitle(
        "Co-votación promedio inter e intra-partido por legislatura",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout(rect=[0, 0, 0.92, 0.98])

    out_path = output_dir / "heatmap_inter_bloque.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _plot_heatmap_fallback(output_dir: Path):
    """Fallback: bar chart de frontera_coalicion si el pipeline no está disponible."""
    csv_path = DATA_DIR / "evolucion_metricas.csv"
    df = pd.read_csv(csv_path)

    x_labels = ["LX+", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]
    y_values = df["frontera_coalicion"].tolist()
    colors_bar = ["#2C3E50"] * 5 + ["#E74C3C"]

    fig, ax = plt.subplots(figsize=(10, 6), dpi=200)
    bars = ax.bar(range(len(x_labels)), y_values, color=colors_bar, edgecolor="white")

    for i, (bar, val) in enumerate(zip(bars, y_values)):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xticks(range(len(x_labels)))
    ax.set_xticklabels(x_labels, fontsize=10)
    ax.set_ylabel("Co-votación inter-bloque", fontsize=11)
    ax.set_ylim(0.3, 1.0)
    ax.set_title(
        "Frontera de coalición por legislatura (fallback)",
        fontsize=13,
        fontweight="bold",
    )
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    out_path = output_dir / "heatmap_inter_bloque.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Función 4: Panel de grafos 2×3
# ---------------------------------------------------------------------------

# Subtítulos y colores por ventana
_PANEL_META = [
    {"title": "LX+ (2006-10) — 2 comunidades", "color": "#666666"},
    {"title": "LXII (2012-13) — 3 comunidades", "color": "#27AE60"},
    {"title": "LXIII (2015-18) — 3 comunidades", "color": "#27AE60"},
    {"title": "LXIV (2018-19) — 2 comunidades (+ sub-bloques)", "color": "#F39C12"},
    {"title": "LXV (2021-23) — 2 comunidades", "color": "#666666"},
    {"title": "LXVI (2024-26) — 2 comunidades", "color": "#666666"},
]


def plot_panel_grafos(output_dir: Path) -> str:
    """Panel 2×3 con los grafos de co-votación por legislatura."""
    # Buscar archivos PNG con glob
    pattern = str(GRAFOS_DIR / "grafo_0?_*.png")
    files = sorted(_glob(pattern))

    if not files:
        raise FileNotFoundError(
            f"No se encontraron grafos en {GRAFOS_DIR}. "
            "Ejecute primero el pipeline de covotacion_dinamica."
        )

    # Seleccionar UN grafo por legislatura (desduplicar si hay múltiples versiones)
    selected: dict[str, str] = {}
    for f in sorted(files):
        abbr = _abbreviate_label(Path(f).stem)
        if abbr not in selected:
            selected[abbr] = f
    canonical_order = ["LX+", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]
    files = [selected[k] for k in canonical_order if k in selected]

    if len(files) < 6:
        logger.warning(
            "Se encontraron solo %d grafos (se esperaban 6). Rellenando subplots vacíos.",
            len(files),
        )

    fig, axes = plt.subplots(2, 3, figsize=(20, 14), dpi=150)

    for i, ax in enumerate(axes.flat):
        if i < len(files):
            img = mpimg.imread(files[i])
            ax.imshow(img)
        else:
            ax.text(
                0.5,
                0.5,
                "Sin grafo",
                ha="center",
                va="center",
                fontsize=12,
                color="#999999",
                transform=ax.transAxes,
            )

        ax.axis("off")

        # Subtítulo
        if i < len(_PANEL_META):
            meta = _PANEL_META[i]
            ax.set_title(meta["title"], fontsize=11, color=meta["color"], pad=8)

    fig.suptitle(
        "Evolución de la estructura comunitaria por legislatura",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = output_dir / "panel_grafos.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    """Generar las 4 visualizaciones del artículo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    # 1. ARI Evolution
    try:
        path = plot_ari_evolution(OUTPUT_DIR)
        results["ari_evolution"] = path
        logger.info("✓ ARI evolution: %s", path)
    except Exception as e:
        logger.error("✗ ARI evolution falló: %s", e, exc_info=True)

    # 2. Frontera de coalición
    try:
        path = plot_frontera_coalicion(OUTPUT_DIR)
        results["frontera_coalicion"] = path
        logger.info("✓ Frontera coalición: %s", path)
    except Exception as e:
        logger.error("✗ Frontera coalición falló: %s", e, exc_info=True)

    # 3. Heatmap inter-bloque
    try:
        path = plot_heatmap_inter_bloque(OUTPUT_DIR)
        results["heatmap_inter_bloque"] = path
        logger.info("✓ Heatmap inter-bloque: %s", path)
    except Exception as e:
        logger.error("✗ Heatmap inter-bloque falló: %s", e, exc_info=True)

    # 4. Panel grafos
    try:
        path = plot_panel_grafos(OUTPUT_DIR)
        results["panel_grafos"] = path
        logger.info("✓ Panel grafos: %s", path)
    except Exception as e:
        logger.error("✗ Panel grafos falló: %s", e, exc_info=True)

    # Resumen
    logger.info("")
    logger.info("=" * 60)
    logger.info("Visualizaciones generadas: %d/4", len(results))
    for name, path in results.items():
        logger.info("  ✓ %s: %s", name, path)
    if len(results) < 4:
        logger.info("  ✗ %d visualizaciones fallaron (ver logs arriba)", 4 - len(results))
    logger.info("=" * 60)

    return 0 if len(results) == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
