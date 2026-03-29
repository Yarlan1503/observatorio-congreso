"""
visualizacion_nominate.py — Visualizaciones del análisis NOMINATE (ideal point estimation).

Genera gráficos de puntos ideales, trayectorias cross-legislatura, distribución
partidista y evolución de posiciones a lo largo del tiempo.

Funciones principales:
1. plot_nominate_scatter — Scatter 2D de puntos ideales por legislador
2. plot_nominate_trajectory — Trayectorias de legisladores entre legislaturas
3. plot_nominate_parties — Centroides y elipses de confianza por partido
4. plot_nominate_evolution — Evolución de centroides partidistas
5. generate_all_nominate_visualizations — Orquestador de todas las visualizaciones
"""

import logging
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Sin display — backend no interactivo

import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
import numpy as np
from matplotlib.patches import Ellipse

from analysis.visualizacion import DEFAULT_COLOR, PARTY_COLORS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración global
# ---------------------------------------------------------------------------

plt.rcParams.update(
    {
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "figure.facecolor": "white",
    }
)

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

# Orden canónico de legislaturas (temporal)
LEG_ORDER: list[str] = ["LX", "LXI", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _get_color(party_id: str) -> str:
    """Retorna el color asociado a un partido, con fallback gris.

    Acepta tanto org_ids (``"O01"``) como nombres cortos (``"MORENA"``).
    Convierte org_id → nombre corto vía ``_ORG_TO_SHORT`` antes de buscar
    en ``PARTY_COLORS``.

    Args:
        party_id: Org_id o nombre corto del partido.

    Returns:
        Hex color del partido o gris por defecto.
    """
    short_name = _ORG_TO_SHORT.get(party_id, party_id)
    return PARTY_COLORS.get(short_name, DEFAULT_COLOR)


def _short_name(party_id: str) -> str:
    """Convierte org_id a nombre corto para display.

    Args:
        party_id: Org_id (ej: ``"O01"``) o nombre corto.

    Returns:
        Nombre corto legible (ej: ``"MORENA"``) o el valor original.
    """
    return _ORG_TO_SHORT.get(party_id, party_id)


def _detect_multi_leg(results: dict) -> bool:
    """Detecta si *results* es un dict por legislatura (multi-legislatura).

    Un dict por legislatura tiene claves como LX, LXI, …, LXVI y cada valor
    es un resultado individual con ``'coordinates'``.

    Args:
        results: Dict de resultados NOMINATE.

    Returns:
        ``True`` si es un dict por legislatura, ``False`` si es un resultado
        individual.
    """
    # Un resultado individual siempre tiene 'coordinates'
    if "coordinates" in results:
        return False
    # Verificar si las claves coinciden con legislaturas conocidas
    known_legs = set(LEG_ORDER)
    result_keys = set(results.keys())
    overlap = result_keys & known_legs
    return len(overlap) >= 1 and all(
        "coordinates" in v for v in results.values() if isinstance(v, dict)
    )


def _sort_legislaturas(labels: list[str]) -> list[str]:
    """Ordena labels de legislatura en orden temporal.

    Args:
        labels: Lista de labels de legislatura.

    Returns:
        Lista ordenada cronológicamente.
    """
    order_map = {leg: i for i, leg in enumerate(LEG_ORDER)}
    return sorted(labels, key=lambda x: order_map.get(x, 99))


def confidence_ellipse(
    x: np.ndarray, y: np.ndarray, ax: plt.Axes, n_std: float = 2.0, **kwargs
) -> Ellipse | None:
    """Dibujar elipse de confianza para datos 2D.

    Calcula la elipse de confianza basada en la covarianza de los datos
    y la añade al eje proporcionado.

    Args:
        x: Coordenadas X de los puntos.
        y: Coordenadas Y de los puntos.
        ax: Eje de matplotlib donde dibujar la elipse.
        n_std: Número de desviaciones estándar para la elipse.
            Por defecto 2.0 (≈95% de confianza).
        **kwargs: Argumentos adicionales para ``matplotlib.patches.Ellipse``
            (facecolor, edgecolor, alpha, etc.).

    Returns:
        La elipse añadida al eje, o ``None`` si hay menos de 3 puntos.
    """
    if len(x) < 3:
        return None
    cov = np.cov(x, y)
    pearson = cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1])
    # Clamp para evitar NaN por errores numéricos
    pearson = np.clip(pearson, -1.0, 1.0)
    ell_radius_x = np.sqrt(1 + pearson)
    ell_radius_y = np.sqrt(1 - pearson)
    ellipse = Ellipse(
        (0, 0),
        width=ell_radius_x * 2,
        height=ell_radius_y * 2,
        **kwargs,
    )
    scale_x = np.sqrt(cov[0, 0]) * n_std
    scale_y = np.sqrt(cov[1, 1]) * n_std
    mean_x = np.mean(x)
    mean_y = np.mean(y)
    transf = (
        transforms.Affine2D()
        .rotate_deg(45)
        .scale(scale_x, scale_y)
        .translate(mean_x, mean_y)
    )
    ellipse.set_transform(transf + ax.transData)
    return ax.add_patch(ellipse)


# ---------------------------------------------------------------------------
# Función 1: Scatter de puntos ideales
# ---------------------------------------------------------------------------


def plot_nominate_scatter(
    results: dict,
    output_dir: str,
    legislatura_label: str = "",
) -> str:
    """Scatter plot 2D de puntos ideales de legisladores.

    Cada punto representa un legislador, coloreado por partido. Genera un
    panel de subplots si *results* contiene múltiples legislaturas.

    Args:
        results: Resultado NOMINATE individual o dict por legislatura
            (claves LX, LXI, …, LXVI).
        output_dir: Directorio donde guardar el PNG.
        legislatura_label: Label de legislatura para título y nombre de
            archivo. Se ignora si *results* es multi-legislatura.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if _detect_multi_leg(results):
        # Panel multi-legislatura
        legs = _sort_legislaturas([k for k in results if k in set(LEG_ORDER)])
        n = len(legs)
        if n == 0:
            logger.warning("Sin legislaturas válidas en results")
            return ""

        ncols = 2
        nrows = (n + 1) // 2
        fig, axes = plt.subplots(
            nrows, ncols, figsize=(6 * ncols, 5 * nrows), squeeze=False
        )

        for idx, leg in enumerate(legs):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]
            _draw_single_scatter(ax, results[leg])
            ax.set_title(f"Puntos Ideales — {leg}", fontsize=10)

        # Ocultar subplots vacíos
        for idx in range(n, nrows * ncols):
            row, col = divmod(idx, ncols)
            axes[row][col].set_visible(False)

        fig.suptitle("Puntos Ideales NOMINATE por Legislatura", fontsize=13, y=1.0)
        plt.tight_layout()
        filepath = output_path / "nominate_scatter_todas.png"
    else:
        # Legislatura individual
        fig, ax = plt.subplots(figsize=(8, 7))
        _draw_single_scatter(ax, results)
        title = (
            f"Puntos Ideales NOMINATE — {legislatura_label}"
            if legislatura_label
            else "Puntos Ideales NOMINATE"
        )
        ax.set_title(title)
        plt.tight_layout()
        label = legislatura_label if legislatura_label else "individual"
        filepath = output_path / f"nominate_scatter_{label}.png"

    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    logger.info("Scatter guardado: %s", filepath)
    return str(filepath.resolve())


def _draw_single_scatter(ax: plt.Axes, result: dict) -> None:
    """Dibujar un scatter de puntos ideales en un eje.

    Args:
        ax: Eje de matplotlib donde dibujar.
        result: Resultado NOMINATE individual.
    """
    coords = result.get("coordinates")
    if coords is None or len(coords) == 0:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", transform=ax.transAxes)
        return

    parties = result.get("legislator_parties", {})
    legislators = result.get("legislators", [])

    # Determinar color por legislador
    colors: list[str] = []
    parties_present: set[str] = set()
    for i, leg_id in enumerate(legislators):
        party = parties.get(leg_id, "")
        colors.append(_get_color(party))
        if party:
            parties_present.add(party)

    x = coords[:, 0]
    y = coords[:, 1] if coords.shape[1] > 1 else np.zeros_like(x)

    ax.scatter(x, y, c=colors, s=25, alpha=0.7, edgecolors="none")
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_xlabel("Dimensión 1")
    ax.set_ylabel("Dimensión 2")
    ax.grid(True, alpha=0.3)

    # Anotar centroides de partidos principales
    for party in parties_present:
        mask = [
            legislators[i]
            for i in range(len(legislators))
            if parties.get(legislators[i]) == party
        ]
        if not mask:
            continue
        indices = [i for i, lid in enumerate(legislators) if lid in set(mask)]
        if len(indices) < 3:
            continue
        cx = np.mean(x[indices])
        cy = np.mean(y[indices])
        display_name = _short_name(party)
        ax.annotate(
            display_name,
            (cx, cy),
            fontsize=7,
            fontweight="bold",
            ha="center",
            va="center",
            color=_get_color(party),
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor="white",
                alpha=0.7,
                edgecolor=_get_color(party),
            ),
        )

    # Leyenda manual (solo partidos presentes)
    handles = []
    for party in sorted(parties_present):
        display_name = _short_name(party)
        handles.append(
            plt.Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=_get_color(party),
                markersize=6,
                label=display_name,
            )
        )
    if handles:
        ax.legend(handles=handles, loc="best", fontsize=7, ncol=2)


# ---------------------------------------------------------------------------
# Función 2: Trayectorias de legisladores
# ---------------------------------------------------------------------------


def plot_nominate_trajectory(
    results_by_leg: dict,
    output_dir: str,
) -> str:
    """Trayectoria de puntos ideales para legisladores en múltiples legislaturas.

    Conecta las posiciones del mismo legislador a lo largo del tiempo con
    líneas coloreadas por partido principal.

    Args:
        results_by_leg: Dict por legislatura (claves LX, LXI, …, LXVI),
            cada valor es un resultado NOMINATE individual.
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    legs = _sort_legislaturas([k for k in results_by_leg if k in set(LEG_ORDER)])
    if len(legs) < 2:
        logger.warning("Se necesitan ≥2 legislaturas para trayectorias")
        fig, ax = plt.subplots(figsize=(8, 7))
        ax.text(
            0.5,
            0.5,
            "Se necesitan ≥2 legislaturas",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        filepath = output_path / "nominate_trayectorias.png"
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return str(filepath.resolve())

    # Construir índice: legislador → [(leg, x, y), ...]
    legislator_positions: dict[str, list[tuple[str, float, float]]] = {}
    legislator_parties_all: dict[str, list[str]] = {}

    for leg in legs:
        result = results_by_leg[leg]
        coords = result.get("coordinates")
        legislators = result.get("legislators", [])
        parties = result.get("legislator_parties", {})

        if coords is None:
            continue

        for i, leg_id in enumerate(legislators):
            x_val = float(coords[i, 0])
            y_val = float(coords[i, 1]) if coords.shape[1] > 1 else 0.0
            legislator_positions.setdefault(leg_id, []).append((leg, x_val, y_val))
            party = parties.get(leg_id, "")
            if party:
                legislator_parties_all.setdefault(leg_id, []).append(party)

    # Filtrar: solo legisladores en ≥2 legislaturas
    trajectories = {
        lid: positions
        for lid, positions in legislator_positions.items()
        if len(positions) >= 2
    }

    if not trajectories:
        logger.warning("Ningún legislador aparece en ≥2 legislaturas")
        fig, ax = plt.subplots(figsize=(8, 7))
        ax.text(
            0.5,
            0.5,
            "Sin legisladores con trayectorias",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        filepath = output_path / "nominate_trayectorias.png"
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return str(filepath.resolve())

    # Si hay >100, muestrear los que más legislaturas abarcan
    if len(trajectories) > 100:
        sorted_trajs = sorted(
            trajectories.items(), key=lambda item: len(item[1]), reverse=True
        )
        trajectories = dict(sorted_trajs[:100])
        logger.info("Muestreados 100 legisladores de %d totales", len(sorted_trajs))

    # Determinar partido principal de cada legislador
    def _main_party(leg_id: str) -> str:
        party_list = legislator_parties_all.get(leg_id, [])
        if not party_list:
            return ""
        return Counter(party_list).most_common(1)[0][0]

    fig, ax = plt.subplots(figsize=(10, 9))

    # Orden de legislaturas para este gráfico
    leg_order_map = {leg: i for i, leg in enumerate(legs)}

    for lid, positions in trajectories.items():
        positions_sorted = sorted(positions, key=lambda p: leg_order_map.get(p[0], 99))
        xs = [p[1] for p in positions_sorted]
        ys = [p[2] for p in positions_sorted]
        party = _main_party(lid)
        color = _get_color(party)

        ax.plot(xs, ys, "-", color=color, alpha=0.4, linewidth=0.8)
        ax.scatter(xs, ys, color=color, s=15, alpha=0.7, edgecolors="none")

    # Anotar legislaturas en posiciones aproximadas
    for leg in legs:
        result = results_by_leg[leg]
        coords = result.get("coordinates")
        if coords is None or len(coords) == 0:
            continue
        cx = np.mean(coords[:, 0])
        cy = np.mean(coords[:, 1]) if coords.shape[1] > 1 else 0.0
        ax.annotate(
            leg,
            (cx, cy),
            fontsize=9,
            fontweight="bold",
            ha="center",
            va="bottom",
            color="#333333",
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="white",
                alpha=0.8,
                edgecolor="#999999",
            ),
        )

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_xlabel("Dimensión 1")
    ax.set_ylabel("Dimensión 2")
    ax.set_title("Trayectorias Ideales — Legislaturas LX a LXVI")
    ax.grid(True, alpha=0.3)

    # Nota sobre alineación
    ax.text(
        0.02,
        0.02,
        "Nota: coordenadas raw por legislatura (espacios NOMINATE independientes)",
        transform=ax.transAxes,
        fontsize=7,
        color="#666666",
        style="italic",
    )

    # Leyenda de partidos
    all_parties: set[str] = set()
    for lid in trajectories:
        mp = _main_party(lid)
        if mp:
            all_parties.add(mp)

    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=_get_color(p),
            markersize=6,
            label=_short_name(p),
        )
        for p in sorted(all_parties)
    ]
    if handles:
        ax.legend(handles=handles, loc="best", fontsize=8, ncol=2)

    plt.tight_layout()
    filepath = output_path / "nominate_trayectorias.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    logger.info("Trayectorias guardadas: %s", filepath)
    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 3: Centroides y elipses por partido
# ---------------------------------------------------------------------------


def plot_nominate_parties(
    results: dict,
    output_dir: str,
    legislatura_label: str = "",
) -> str:
    """Centroides y elipses de confianza por partido.

    Dibuja el centroide (media de coordenadas) y una elipse al 95% de
    confianza para cada partido presente en los datos.

    Args:
        results: Resultado NOMINATE individual.
        output_dir: Directorio donde guardar el PNG.
        legislatura_label: Label de legislatura para título y nombre de
            archivo.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    coords = results.get("coordinates")
    if coords is None or len(coords) == 0:
        logger.warning("Sin coordenadas para gráfico de partidos")
        fig, ax = plt.subplots(figsize=(8, 7))
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", transform=ax.transAxes)
        filepath = (
            output_path / f"nominate_partidos_{legislatura_label or 'sin_datos'}.png"
        )
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return str(filepath.resolve())

    legislators = results.get("legislators", [])
    parties = results.get("legislator_parties", {})

    x = coords[:, 0]
    y = coords[:, 1] if coords.shape[1] > 1 else np.zeros_like(x)

    # Agrupar por partido
    party_coords: dict[str, list[int]] = {}
    for i, leg_id in enumerate(legislators):
        party = parties.get(leg_id, "Sin partido")
        party_coords.setdefault(party, []).append(i)

    fig, ax = plt.subplots(figsize=(9, 8))

    # Scatter de fondo (todos los puntos, gris claro)
    ax.scatter(x, y, c="#DDDDDD", s=10, alpha=0.4, edgecolors="none", zorder=1)

    # Elipses y centroides
    for party, indices in sorted(party_coords.items()):
        color = _get_color(party)
        px = x[indices]
        py = y[indices]
        cx = np.mean(px)
        cy = np.mean(py)

        # Elipse solo si hay ≥3 miembros
        if len(indices) >= 3:
            confidence_ellipse(
                px,
                py,
                ax,
                n_std=2.0,
                facecolor=color,
                edgecolor=color,
                alpha=0.2,
                linewidth=1.5,
                zorder=2,
            )

        # Centroide
        ax.scatter(
            cx,
            cy,
            c=color,
            s=80,
            marker="D",
            edgecolors="white",
            linewidths=1,
            zorder=4,
        )

        # Etiqueta del centroide
        display_name = _short_name(party)
        ax.annotate(
            f"{display_name} ({len(indices)})",
            (cx, cy),
            fontsize=7,
            fontweight="bold",
            ha="center",
            va="bottom",
            xytext=(0, 8),
            textcoords="offset points",
            color=color,
        )

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_xlabel("Dimensión 1")
    ax.set_ylabel("Dimensión 2")
    title = (
        f"Distribución Partidista — {legislatura_label}"
        if legislatura_label
        else "Distribución Partidista"
    )
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    # Leyenda
    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="D",
            color="w",
            markerfacecolor=_get_color(p),
            markersize=7,
            label=f"{_short_name(p)} ({len(indices)})",
        )
        for p, indices in sorted(party_coords.items())
    ]
    ax.legend(handles=handles, loc="best", fontsize=8, ncol=2)

    plt.tight_layout()
    filepath = output_path / f"nominate_partidos_{legislatura_label or 'sin_label'}.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    logger.info("Partidos guardados: %s", filepath)
    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 4: Evolución de posiciones partidistas
# ---------------------------------------------------------------------------


def plot_nominate_evolution(
    results_by_leg: dict,
    output_dir: str,
) -> str:
    """Evolución del centroide de cada partido a lo largo de legislaturas.

    Dibuja flechas conectando los centroides de cada partido de legislatura
    en legislatura, mostrando la dirección del movimiento ideológico.

    Args:
        results_by_leg: Dict por legislatura (claves LX, LXI, …, LXVI),
            cada valor es un resultado NOMINATE individual.
        output_dir: Directorio donde guardar el PNG.

    Returns:
        Ruta absoluta del archivo PNG generado.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    legs = _sort_legislaturas([k for k in results_by_leg if k in set(LEG_ORDER)])
    if len(legs) < 2:
        logger.warning("Se necesitan ≥2 legislaturas para evolución")
        fig, ax = plt.subplots(figsize=(8, 7))
        ax.text(
            0.5,
            0.5,
            "Se necesitan ≥2 legislaturas",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        filepath = output_path / "nominate_evolucion.png"
        fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return str(filepath.resolve())

    # Calcular centroides por partido y legislatura
    party_centroids: dict[str, list[tuple[str, float, float]]] = {}

    for leg in legs:
        result = results_by_leg[leg]
        coords = result.get("coordinates")
        legislators = result.get("legislators", [])
        parties = result.get("legislator_parties", {})

        if coords is None or len(coords) == 0:
            continue

        x = coords[:, 0]
        y = coords[:, 1] if coords.shape[1] > 1 else np.zeros_like(x)

        # Agrupar por partido
        party_indices: dict[str, list[int]] = {}
        for i, leg_id in enumerate(legislators):
            party = parties.get(leg_id, "")
            if party:
                party_indices.setdefault(party, []).append(i)

        for party, indices in party_indices.items():
            cx = float(np.mean(x[indices]))
            cy = float(np.mean(y[indices]))
            party_centroids.setdefault(party, []).append((leg, cx, cy))

    # Filtrar: solo partidos con presencia en ≥3 legislaturas
    qualified = {
        p: positions for p, positions in party_centroids.items() if len(positions) >= 3
    }

    if not qualified:
        logger.warning("Ningún partido tiene presencia en ≥3 legislaturas")
        # Relajar a ≥2
        qualified = {
            p: positions
            for p, positions in party_centroids.items()
            if len(positions) >= 2
        }
        if not qualified:
            fig, ax = plt.subplots(figsize=(8, 7))
            ax.text(
                0.5,
                0.5,
                "Sin partidos con trayectoria suficiente",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            filepath = output_path / "nominate_evolucion.png"
            fig.savefig(filepath, dpi=300, bbox_inches="tight")
            plt.close(fig)
            return str(filepath.resolve())

    fig, ax = plt.subplots(figsize=(10, 9))

    leg_order_map = {leg: i for i, leg in enumerate(legs)}

    for party, positions in sorted(qualified.items()):
        positions_sorted = sorted(positions, key=lambda p: leg_order_map.get(p[0], 99))
        xs = [p[1] for p in positions_sorted]
        ys = [p[2] for p in positions_sorted]
        color = _get_color(party)

        # Línea conectando centroides
        ax.plot(xs, ys, "-", color=color, linewidth=2, alpha=0.7, zorder=2)

        # Puntos con índice de legislatura
        for i, (leg_label, cx, cy) in enumerate(positions_sorted):
            ax.scatter(
                cx,
                cy,
                c=color,
                s=60,
                edgecolors="white",
                linewidths=1,
                zorder=3,
            )
            # Anotar nombre de legislatura
            ax.annotate(
                leg_label,
                (cx, cy),
                fontsize=7,
                ha="center",
                va="bottom",
                xytext=(0, 6),
                textcoords="offset points",
                color=color,
            )

        # Flecha desde primero a último
        if len(xs) >= 2:
            dx = xs[-1] - xs[0]
            dy = ys[-1] - ys[0]
            ax.annotate(
                "",
                xy=(xs[-1], ys[-1]),
                xytext=(xs[0], ys[0]),
                arrowprops=dict(
                    arrowstyle="->",
                    color=color,
                    lw=1.5,
                    alpha=0.5,
                ),
                zorder=1,
            )

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_xlabel("Dimensión 1")
    ax.set_ylabel("Dimensión 2")
    ax.set_title("Evolución de Posiciones Partidistas")
    ax.grid(True, alpha=0.3)

    # Leyenda
    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=_get_color(p),
            markersize=8,
            label=_short_name(p),
        )
        for p in sorted(qualified.keys())
    ]
    ax.legend(handles=handles, loc="best", fontsize=9, ncol=2)

    # Nota sobre alineación
    ax.text(
        0.02,
        0.02,
        "Nota: coordenadas raw por legislatura (espacios NOMINATE independientes)",
        transform=ax.transAxes,
        fontsize=7,
        color="#666666",
        style="italic",
    )

    plt.tight_layout()
    filepath = output_path / "nominate_evolucion.png"
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)

    logger.info("Evolución guardada: %s", filepath)
    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# Función 5: Orquestador
# ---------------------------------------------------------------------------


def generate_all_nominate_visualizations(
    results_by_leg: dict,
    output_dir: str,
) -> dict[str, str]:
    """Orquesta la generación de todas las visualizaciones NOMINATE.

    Genera:
    1. Scatter de puntos ideales por legislatura
    2. Distribución partidista (centroides + elipses) por legislatura
    3. Trayectorias de legisladores (global)
    4. Evolución de posiciones partidistas (global)
    5. Panel de scatter para todas las legislaturas (si hay múltiples)

    Args:
        results_by_leg: Dict por legislatura (claves LX, LXI, …, LXVI),
            cada valor es un resultado NOMINATE individual.
        output_dir: Directorio base donde guardar todos los archivos.

    Returns:
        Diccionario ``{nombre → ruta_archivo}`` con las rutas de todos los
        archivos generados.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    legs = _sort_legislaturas([k for k in results_by_leg if k in set(LEG_ORDER)])

    # 1. Scatter y partidos por legislatura individual
    for leg in legs:
        try:
            path = plot_nominate_scatter(
                results_by_leg[leg], output_dir, legislatura_label=leg
            )
            if path:
                results[f"scatter_{leg}"] = path
        except Exception as e:
            logger.error("Error scatter %s: %s", leg, e)

        try:
            path = plot_nominate_parties(
                results_by_leg[leg], output_dir, legislatura_label=leg
            )
            if path:
                results[f"partidos_{leg}"] = path
        except Exception as e:
            logger.error("Error partidos %s: %s", leg, e)

    # 2. Panel global de scatter (todas las legislaturas)
    if len(legs) > 1:
        try:
            path = plot_nominate_scatter(results_by_leg, output_dir)
            if path:
                results["scatter_todas"] = path
        except Exception as e:
            logger.error("Error scatter todas: %s", e)

    # 3. Trayectorias
    if len(legs) >= 2:
        try:
            path = plot_nominate_trajectory(results_by_leg, output_dir)
            if path:
                results["trayectorias"] = path
        except Exception as e:
            logger.error("Error trayectorias: %s", e)

    # 4. Evolución
    if len(legs) >= 2:
        try:
            path = plot_nominate_evolution(results_by_leg, output_dir)
            if path:
                results["evolucion"] = path
        except Exception as e:
            logger.error("Error evolución: %s", e)

    logger.info("Visualizaciones NOMINATE generadas: %d archivos", len(results))
    return results
