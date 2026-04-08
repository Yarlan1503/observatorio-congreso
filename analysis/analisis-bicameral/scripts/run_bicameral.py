"""
run_bicameral.py — Análisis Bicameral del Observatorio del Congreso
===================================================================

Compara Diputados y Senado en 4 dimensiones:
1. NOMINATE Comparado (posiciones ideológicas)
2. Disciplina Comparada (disciplina partidista)
3. Estructura de Co-votación Comparada (alianzas, modularidad)
4. Poder Comparado en Reformas (poder empírico, calificada)

Uso:
    cd /path/to/observatorio-congreso
    .venv/bin/python -m analysis.analisis-bicameral.scripts.run_bicameral

    # O alternativamente:
    .venv/bin/python analysis/analisis-bicameral/scripts/run_bicameral.py
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import csv
import math
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import seaborn as sns

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DIP_OUTPUT = ROOT / "analysis" / "analisis-diputados" / "output"
SEN_OUTPUT = ROOT / "analysis" / "analisis-senado" / "output"
BIC_OUTPUT = ROOT / "analysis" / "analisis-bicameral" / "output"

# ---------------------------------------------------------------------------
# Party config
# ---------------------------------------------------------------------------
PARTY_COLORS = {
    "MORENA": "#8B0000",
    "PAN": "#003399",
    "PRI": "#00A650",
    "PVEM": "#006633",
    "PT": "#CC0000",
    "MC": "#FF6600",
    "PRD": "#FFD700",
    "Independientes": "#808080",
}

# Common parties for comparison
COMMON_PARTIES = ["MORENA", "PAN", "PRI", "PVEM", "PT", "MC", "PRD"]

# Party name normalization: various forms → canonical short name
PARTY_NORM = {
    "Morena": "MORENA",
    "MORENA": "MORENA",
    "PAN": "PAN",
    "Partido Accion Nacional (PAN)": "PAN",
    "Partido Acci\u00f3n Nacional (PAN)": "PAN",
    "PRI": "PRI",
    "Partido Revolucionario Institucional (PRI)": "PRI",
    "PVEM": "PVEM",
    "Partido Verde Ecologista de Mexico (PVEM)": "PVEM",
    "Partido Verde Ecologista de M\u00e9xico (PVEM)": "PVEM",
    "PT": "PT",
    "Partido del Trabajo (PT)": "PT",
    "MC": "MC",
    "Movimiento Ciudadano (MC)": "MC",
    "PRD": "PRD",
    "Partido de la Revolucion Democratica (PRD)": "PRD",
    "Partido de la Revoluci\u00f3n Democr\u00e1tica (PRD)": "PRD",
    "Independientes": "Independientes",
    "SG": "SG",
    "PES": "PES",
    "CONV": "CONV",
    "Convergencia": "CONV",
    "NA": "NA",
    "Nueva Alianza": "NA",
    "NUEVA ALIANZA": "NA",
}

# Org-ID → canonical short name (from DB mapping)
ORG_NORM = {
    "O01": "MORENA",
    "O02": "PT",
    "O03": "PVEM",
    "O04": "PAN",
    "O05": "PRI",
    "O06": "MC",
    "O07": "PRD",
    "O11": "MORENA",
    "O12": "PAN",
    "O13": "PVEM",
    "O14": "PT",
    "O15": "PRI",
    "O16": "MC",
    "O17": "Independientes",
    "O18": "PRD",
    "O19": "SG",
    "O25": "PES",
    "O26": "NA",
}

# Legislatura normalization
LEG_NORM = {
    "LX (06-09)": "LX (2006-09)",
    "LX+ (2006-09-29 a 2010-04-29)": "LX/LXI (2006-10)",
    "LXI (09-12)": "LXI (2009-12)",
    "LXII (12-13)": "LXII (2012-15)",
    "LXII (12-15)": "LXII (2012-15)",
    "LXIII (15-18)": "LXIII (2015-18)",
    "LXIV (18-19)": "LXIV (2018-21)",
    "LXIV (18-21)": "LXIV (2018-21)",
    "LXV (21-23)": "LXV/LXVI (2021-26)",
    "LXV+ (2021-12-15 a 2026-03-25)": "LXV/LXVI (2021-26)",
    "LXVI (24-26)": "LXVI (2024-26)",
}

# Legislatura sort order
LEG_ORDER = [
    "LX/LXI (2006-10)",
    "LX (2006-09)",
    "LXI (2009-12)",
    "LXII (2012-15)",
    "LXIII (2015-18)",
    "LXIV (2018-21)",
    "LXV/LXVI (2021-26)",
    "LXVI (2024-26)",
]


def norm_party(name: str) -> str:
    """Normalize a party name to canonical short form."""
    if not name:
        return "???"
    return PARTY_NORM.get(name.strip(), name.strip())


def norm_leg(name: str) -> str:
    """Normalize a legislatura label."""
    if not name:
        return name
    return LEG_NORM.get(name.strip(), name.strip())


def read_csv(path: Path) -> list[dict]:
    """Read a CSV file into a list of dicts."""
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ===========================================================================
# ANÁLISIS 1: NOMINATE Comparado
# ===========================================================================


def analyze_nominate():
    """Compara posiciones ideológicas NOMINATE entre cámaras."""
    print("\n" + "=" * 80)
    print("ANÁLISIS 1: NOMINATE COMPARADO")
    print("=" * 80)

    dip_coords = read_csv(DIP_OUTPUT / "nominate" / "coordenadas_cross.csv")
    sen_coords = read_csv(SEN_OUTPUT / "nominate" / "coordenadas_cross.csv")

    # Normalize party names
    for row in dip_coords:
        row["partido_norm"] = norm_party(row["partido"])
    for row in sen_coords:
        row["partido_norm"] = norm_party(row["partido"])

    # Calculate centroids per party × camara
    def calc_centroids(coords):
        party_data = defaultdict(lambda: {"dim_1": [], "dim_2": []})
        for r in coords:
            pn = r["partido_norm"]
            if pn in COMMON_PARTIES:
                try:
                    party_data[pn]["dim_1"].append(float(r["dim_1"]))
                    party_data[pn]["dim_2"].append(float(r["dim_2"]))
                except (ValueError, KeyError):
                    pass
        result = {}
        for party, vals in party_data.items():
            if len(vals["dim_1"]) >= 3:
                result[party] = {
                    "centroid_x": np.mean(vals["dim_1"]),
                    "centroid_y": np.mean(vals["dim_2"]),
                    "std_x": np.std(vals["dim_1"]),
                    "std_y": np.std(vals["dim_2"]),
                    "n": len(vals["dim_1"]),
                }
        return result

    dip_centroids = calc_centroids(dip_coords)
    sen_centroids = calc_centroids(sen_coords)

    # Build comparison table
    common = sorted(set(dip_centroids.keys()) & set(sen_centroids.keys()))
    rows = []
    for party in common:
        d = dip_centroids[party]
        s = sen_centroids[party]
        dist = math.sqrt(
            (d["centroid_x"] - s["centroid_x"]) ** 2 + (d["centroid_y"] - s["centroid_y"]) ** 2
        )
        rows.append(
            {
                "partido": party,
                "centroid_D_x": round(d["centroid_x"], 4),
                "centroid_D_y": round(d["centroid_y"], 4),
                "std_D_x": round(d["std_x"], 4),
                "n_D": d["n"],
                "centroid_S_x": round(s["centroid_x"], 4),
                "centroid_S_y": round(s["centroid_y"], 4),
                "std_S_x": round(s["std_x"], 4),
                "n_S": s["n"],
                "distancia": round(dist, 4),
            }
        )

    # Save CSV
    BIC_OUTPUT.mkdir(parents=True, exist_ok=True)
    with open(BIC_OUTPUT / "nominate_comparado.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # Print summary
    print(f"\n  Centroides calculados para {len(rows)} partidos comunes:")
    print(f"  {'Partido':<12} {'D_x':>8} {'D_y':>8} {'S_x':>8} {'S_y':>8} {'Dist':>8}")
    print(f"  {'-' * 52}")
    for r in sorted(rows, key=lambda x: -x["distancia"]):
        print(
            f"  {r['partido']:<12} {r['centroid_D_x']:>8.3f} {r['centroid_D_y']:>8.3f} "
            f"{r['centroid_S_x']:>8.3f} {r['centroid_S_y']:>8.3f} {r['distancia']:>8.3f}"
        )

    # --- Plot 1: Scatter bicameral ---
    fig, ax = plt.subplots(figsize=(12, 9))
    markers = {"D": "o", "S": "^"}
    camara_labels = {"D": "Diputados", "S": "Senado"}

    for camara, centroids, coords in [
        ("D", dip_centroids, dip_coords),
        ("S", sen_centroids, sen_coords),
    ]:
        for party in common:
            if party not in centroids:
                continue
            c = centroids[party]
            color = PARTY_COLORS.get(party, "#999999")
            # Plot individual legislators (sample for clarity)
            party_coords = [r for r in coords if r["partido_norm"] == party]
            xs = [float(r["dim_1"]) for r in party_coords[:200]]
            ys = [float(r["dim_2"]) for r in party_coords[:200]]
            ax.scatter(xs, ys, c=color, alpha=0.08, s=15, marker=markers[camara])
            # Plot centroid
            ax.scatter(
                c["centroid_x"],
                c["centroid_y"],
                c=color,
                marker=markers[camara],
                s=200,
                edgecolors="black",
                linewidth=1.5,
                zorder=5,
                label=f"{party} ({camara_labels[camara]})",
            )

    # Deduplicate legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper right", fontsize=8, ncol=2)

    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.axvline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_xlabel("Dimensión 1 (Gobierno-Oposición)", fontsize=12)
    ax.set_ylabel("Dimensión 2 (Secundaria)", fontsize=12)
    ax.set_title("NOMINATE Comparado: Diputados (○) vs Senado (△)", fontsize=14)
    fig.tight_layout()
    fig.savefig(BIC_OUTPUT / "nominate_scatter_bicameral.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → nominate_scatter_bicameral.png generado")

    # --- Plot 2: Bar chart de distancia intra-partido ---
    fig, ax = plt.subplots(figsize=(10, 6))
    sorted_rows = sorted(rows, key=lambda x: -x["distancia"])
    parties = [r["partido"] for r in sorted_rows]
    dists = [r["distancia"] for r in sorted_rows]
    colors = [PARTY_COLORS.get(p, "#999999") for p in parties]

    bars = ax.barh(parties, dists, color=colors, edgecolor="black", linewidth=0.5)
    for bar, dist in zip(bars, dists):
        ax.text(
            bar.get_width() + 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{dist:.3f}",
            va="center",
            fontsize=10,
        )

    ax.set_xlabel("Distancia euclidiana entre centroides D-S")
    ax.set_title("Distancia Ideológica Intra-Partido: Diputados vs Senado")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(BIC_OUTPUT / "nominate_distancia_partidos.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → nominate_distancia_partidos.png generado")

    return rows


# ===========================================================================
# ANÁLISIS 2: Disciplina Comparada
# ===========================================================================


def analyze_disciplina():
    """Compara disciplina partidista entre cámaras."""
    print("\n" + "=" * 80)
    print("ANÁLISIS 2: DISCIPLINA COMPARADA")
    print("=" * 80)

    # Read disciplina files
    dip_disc = read_csv(DIP_OUTPUT / "dinamica" / "disciplina_partidista.csv")
    sen_disc = read_csv(SEN_OUTPUT / "dinamica" / "disciplina_partidista.csv")

    # Parse into structured format: list of {legislatura, partido, disciplina, camara}
    def parse_disciplina(data, camara):
        result = []
        for row in data:
            leg_raw = row.get("partido", "").strip()
            leg = norm_leg(leg_raw)
            for party_raw, val in row.items():
                if party_raw == "partido":
                    continue
                pn = norm_party(party_raw)
                if pn in COMMON_PARTIES and val.strip():
                    try:
                        result.append(
                            {
                                "legislatura_raw": leg_raw,
                                "legislatura": leg,
                                "partido": pn,
                                "disciplina": float(val),
                                "camara": camara,
                            }
                        )
                    except ValueError:
                        pass
        return result

    dip_parsed = parse_disciplina(dip_disc, "Diputados")
    sen_parsed = parse_disciplina(sen_disc, "Senado")
    all_data = dip_parsed + sen_parsed

    # Build comparison table: for matching legislatura × party
    # Normalize legislaturas to common set
    leg_map = {
        "LX/LXI (2006-10)": "LX-LXI (2006-12)",
        "LX (2006-09)": "LX-LXI (2006-12)",
        "LXI (2009-12)": "LX-LXI (2006-12)",
        "LXII (2012-15)": "LXII (2012-15)",
        "LXIII (2015-18)": "LXIII (2015-18)",
        "LXIV (2018-21)": "LXIV (2018-21)",
        "LXV/LXVI (2021-26)": "LXV+ (2021-26)",
        "LXVI (2024-26)": "LXV+ (2021-26)",
    }

    for d in all_data:
        d["leg_common"] = leg_map.get(d["legislatura"], d["legislatura"])

    # Create comparison: party × leg_common → {D: val, S: val}
    comp = defaultdict(lambda: {"D": None, "S": None})
    for d in all_data:
        key = (d["partido"], d["leg_common"])
        comp[key][d["camara"][0]] = d["disciplina"]

    rows = []
    for (party, leg), vals in sorted(comp.items()):
        if vals["D"] is not None and vals["S"] is not None:
            delta = vals["S"] - vals["D"]
            rows.append(
                {
                    "partido": party,
                    "legislatura": leg,
                    "disciplina_D": round(vals["D"], 4),
                    "disciplina_S": round(vals["S"], 4),
                    "delta_S_menos_D": round(delta, 4),
                }
            )

    # Save CSV
    with open(BIC_OUTPUT / "disciplina_comparada.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    # Print summary
    print(f"\n  Comparaciones posibles: {len(rows)} pares (partido × legislatura)")
    avg_delta = np.mean([r["delta_S_menos_D"] for r in rows]) if rows else 0
    print(f"  Delta promedio (S-D): {avg_delta:+.4f}")
    if avg_delta > 0:
        print(f"  → Senado es más disciplinado en promedio")
    else:
        print(f"  → Diputados es más disciplinado en promedio")

    print(f"\n  {'Partido':<12} {'Legislatura':<20} {'D':>8} {'S':>8} {'Δ(S-D)':>8}")
    print(f"  {'-' * 64}")
    for r in rows:
        print(
            f"  {r['partido']:<12} {r['legislatura']:<20} {r['disciplina_D']:>8.4f} "
            f"{r['disciplina_S']:>8.4f} {r['delta_S_menos_D']:>+8.4f}"
        )

    # --- Plot 1: Lineas bicameral ---
    leg_order_common = [
        "LX-LXI (2006-12)",
        "LXII (2012-15)",
        "LXIII (2015-18)",
        "LXIV (2018-21)",
        "LXV+ (2021-26)",
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey=True)
    axes_flat = axes.flatten()

    plot_parties = [p for p in COMMON_PARTIES if any(r["partido"] == p for r in rows)]
    for idx, party in enumerate(plot_parties[:6]):
        ax = axes_flat[idx]
        party_rows = [r for r in rows if r["partido"] == party]

        # Get all data for this party (including where only one camara has data)
        party_all_d = [d for d in dip_parsed if d["partido"] == party]
        party_all_s = [d for d in sen_parsed if d["partido"] == party]

        if party_all_d:
            legs_d = [d["leg_common"] for d in party_all_d]
            vals_d = [d["disciplina"] for d in party_all_d]
            # Sort by leg order
            pairs_d = sorted(
                zip(legs_d, vals_d),
                key=lambda x: leg_order_common.index(x[0]) if x[0] in leg_order_common else 99,
            )
            ax.plot(
                [p[0] for p in pairs_d],
                [p[1] for p in pairs_d],
                "o-",
                color=PARTY_COLORS.get(party, "#999"),
                label="Diputados",
                linewidth=2,
                markersize=8,
            )

        if party_all_s:
            legs_s = [d["leg_common"] for d in party_all_s]
            vals_s = [d["disciplina"] for d in party_all_s]
            pairs_s = sorted(
                zip(legs_s, vals_s),
                key=lambda x: leg_order_common.index(x[0]) if x[0] in leg_order_common else 99,
            )
            ax.plot(
                [p[0] for p in pairs_s],
                [p[1] for p in pairs_s],
                "^--",
                color=PARTY_COLORS.get(party, "#999"),
                label="Senado",
                linewidth=2,
                markersize=8,
                alpha=0.7,
            )

        ax.set_title(party, fontsize=13, fontweight="bold")
        ax.set_ylim(0.7, 1.02)
        ax.tick_params(axis="x", rotation=30, labelsize=8)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    # Hide unused subplots
    for idx in range(len(plot_parties), len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle(
        "Disciplina Partidista: Diputados (línea) vs Senado (triángulo)",
        fontsize=15,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(BIC_OUTPUT / "disciplina_lineas_bicameral.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → disciplina_lineas_bicameral.png generado")

    # --- Plot 2: Heatmap delta ---
    if rows:
        parties_in_rows = sorted(set(r["partido"] for r in rows))
        legs_in_rows = sorted(
            set(r["legislatura"] for r in rows),
            key=lambda x: leg_order_common.index(x) if x in leg_order_common else 99,
        )

        matrix = np.full((len(parties_in_rows), len(legs_in_rows)), np.nan)
        for r in rows:
            pi = parties_in_rows.index(r["partido"])
            li = legs_in_rows.index(r["legislatura"])
            matrix[pi, li] = r["delta_S_menos_D"]

        fig, ax = plt.subplots(figsize=(12, 6))
        sns.heatmap(
            matrix,
            ax=ax,
            annot=True,
            fmt=".3f",
            center=0,
            cmap="RdBu_r",
            xticklabels=legs_in_rows,
            yticklabels=parties_in_rows,
            linewidths=0.5,
            cbar_kws={"label": "Δ Disciplina (Senado - Diputados)"},
        )
        ax.set_title("Disciplina Comparada: Δ(Senado - Diputados) por Partido × Legislatura")
        ax.set_xlabel("Legislatura")
        ax.set_ylabel("Partido")
        fig.tight_layout()
        fig.savefig(BIC_OUTPUT / "disciplina_delta_heatmap.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  → disciplina_delta_heatmap.png generado")

    return rows


# ===========================================================================
# ANÁLISIS 3: Estructura de Co-votación Comparada
# ===========================================================================


def analyze_covotacion():
    """Compara estructura de co-votación entre cámaras."""
    print("\n" + "=" * 80)
    print("ANÁLISIS 3: ESTRUCTURA DE CO-VOTACIÓN COMPARADA")
    print("=" * 80)

    # Read evolution metrics
    dip_evol = read_csv(DIP_OUTPUT / "dinamica" / "evolucion_metricas.csv")
    sen_evol = read_csv(SEN_OUTPUT / "dinamica" / "evolucion_metricas.csv")

    # Read co-votation matrices
    dip_mat = read_csv(DIP_OUTPUT / "matriz_partidos.csv")
    sen_mat = read_csv(SEN_OUTPUT / "matriz_partidos.csv")

    # --- 3a: Comparison table of metrics ---
    # Normalize legislaturas
    for row in dip_evol:
        row["leg_norm"] = norm_leg(row.get("legislatura", ""))
    for row in sen_evol:
        row["leg_norm"] = norm_leg(row.get("legislatura", ""))

    # Find matching legislaturas
    dip_legs = {r["leg_norm"]: r for r in dip_evol}
    sen_legs = {r["leg_norm"]: r for r in sen_evol}
    common_legs = sorted(set(dip_legs.keys()) & set(sen_legs.keys()))

    metrics_rows = []
    for leg in common_legs:
        d = dip_legs[leg]
        s = sen_legs[leg]
        metrics_rows.append(
            {
                "legislatura": leg,
                "modularidad_D": round(float(d.get("modularidad", 0)), 4),
                "modularidad_S": round(float(s.get("modularidad", 0)), 4),
                "densidad_D": round(float(d.get("densidad", 0)), 4),
                "densidad_S": round(float(s.get("densidad", 0)), 4),
                "n_comunidades_D": d.get("n_comunidades", ""),
                "n_comunidades_S": s.get("n_comunidades", ""),
                "frontera_D": round(float(d.get("frontera_coalicion", 0)), 4),
                "frontera_S": round(float(s.get("frontera_coalicion", 0)), 4),
            }
        )

    with open(BIC_OUTPUT / "metricas_comparadas.csv", "w", newline="", encoding="utf-8") as f:
        if metrics_rows:
            writer = csv.DictWriter(f, fieldnames=metrics_rows[0].keys())
            writer.writeheader()
            writer.writerows(metrics_rows)

    print(f"\n  Métricas comparadas para {len(metrics_rows)} legislaturas:")
    print(f"  {'Legislatura':<22} {'Mod_D':>8} {'Mod_S':>8} {'Den_D':>8} {'Den_S':>8}")
    print(f"  {'-' * 58}")
    for r in metrics_rows:
        print(
            f"  {r['legislatura']:<22} {r['modularidad_D']:>8.4f} {r['modularidad_S']:>8.4f} "
            f"{r['densidad_D']:>8.4f} {r['densidad_S']:>8.4f}"
        )

    # --- 3b: Correlation between co-votation matrices ---
    # Parse matrices and normalize party names
    def parse_matrix(data):
        mat = {}
        for row in data:
            keys = list(row.keys())
            # First key is the row party name (may be empty in header for first column)
            party_row_raw = keys[0] if keys else ""
            # For rows, the first column value is the party name
            # The DictReader uses the first row as headers, so keys[0] is the header
            # and the row value for that key is the party name in that row
            # But actually the matrix has party names as both row headers and column headers
            # The first column header is empty (because it's the row index)
            # So we need to get the party name from the first VALUE of the row
            # But DictReader puts it as the value for the empty-string key
            # Let's handle both cases
            if party_row_raw == "":
                # Empty header column - value is the row party name
                party_row_name = row.get("", "")
            else:
                party_row_name = party_row_raw
            party_row = norm_party(party_row_name)
            vals = {}
            for k, v in row.items():
                if k == "":
                    continue  # Skip the row index column
                pn = norm_party(k)
                try:
                    vals[pn] = float(v)
                except (ValueError, TypeError):
                    pass
            if party_row and party_row != "???" and vals:
                mat[party_row] = vals
        return mat

    dip_cov = parse_matrix(dip_mat)
    sen_cov = parse_matrix(sen_mat)

    # Find common parties
    common_parties_mat = sorted(set(dip_cov.keys()) & set(sen_cov.keys()))
    print(f"\n  Partidos comunes en matrices de co-votación: {common_parties_mat}")

    # Calculate correlation
    dip_vals = []
    sen_vals = []
    for p1 in common_parties_mat:
        for p2 in common_parties_mat:
            if p1 in dip_cov and p2 in dip_cov.get(p1, {}):
                if p1 in sen_cov and p2 in sen_cov.get(p1, {}):
                    dip_vals.append(dip_cov[p1][p2])
                    sen_vals.append(sen_cov[p1][p2])

    if len(dip_vals) > 3:
        corr = np.corrcoef(dip_vals, sen_vals)[0, 1]
        print(f"  Correlación entre matrices de co-votación: {corr:.4f}")
    else:
        corr = None
        print(f"  No hay suficientes datos para correlación")

    # --- Plot 1: Modularidad comparada ---
    fig, ax = plt.subplots(figsize=(10, 6))
    legs_all = sorted(
        set([r["leg_norm"] for r in dip_evol] + [r["leg_norm"] for r in sen_evol]),
        key=lambda x: LEG_ORDER.index(x) if x in LEG_ORDER else 99,
    )

    dip_mod = {r["leg_norm"]: float(r.get("modularidad", 0)) for r in dip_evol}
    sen_mod = {r["leg_norm"]: float(r.get("modularidad", 0)) for r in sen_evol}

    x = range(len(legs_all))
    d_vals = [dip_mod.get(l, None) for l in legs_all]
    s_vals = [sen_mod.get(l, None) for l in legs_all]

    # Plot only non-None values
    d_x = [i for i, v in enumerate(d_vals) if v is not None]
    d_y = [v for v in d_vals if v is not None]
    s_x = [i for i, v in enumerate(s_vals) if v is not None]
    s_y = [v for v in s_vals if v is not None]

    ax.plot(d_x, d_y, "o-", color="#003399", linewidth=2.5, markersize=10, label="Diputados")
    ax.plot(s_x, s_y, "^--", color="#CC0000", linewidth=2.5, markersize=10, label="Senado")
    ax.set_xticks(range(len(legs_all)))
    ax.set_xticklabels(legs_all, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Modularidad")
    ax.set_title("Modularidad de Co-votación: Diputados vs Senado")
    ax.legend(fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(BIC_OUTPUT / "modularidad_comparada.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → modularidad_comparada.png generado")

    # --- Plot 2: Heatmaps lado a lado ---
    # Use common parties for both matrices
    plot_parties = [p for p in COMMON_PARTIES if p in dip_cov and p in sen_cov]

    if len(plot_parties) >= 3:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

        # Diputados matrix
        d_matrix = np.zeros((len(plot_parties), len(plot_parties)))
        for i, p1 in enumerate(plot_parties):
            for j, p2 in enumerate(plot_parties):
                d_matrix[i, j] = dip_cov.get(p1, {}).get(p2, 0)

        # Senado matrix
        s_matrix = np.zeros((len(plot_parties), len(plot_parties)))
        for i, p1 in enumerate(plot_parties):
            for j, p2 in enumerate(plot_parties):
                s_matrix[i, j] = sen_cov.get(p1, {}).get(p2, 0)

        vmin = min(d_matrix.min(), s_matrix.min())
        vmax = max(d_matrix.max(), s_matrix.max())

        sns.heatmap(
            d_matrix,
            ax=ax1,
            annot=True,
            fmt=".2f",
            cmap="YlOrRd",
            xticklabels=plot_parties,
            yticklabels=plot_parties,
            vmin=vmin,
            vmax=vmax,
            linewidths=0.5,
        )
        ax1.set_title("Diputados — Co-votación")
        ax1.tick_params(axis="x", rotation=45)
        ax1.tick_params(axis="y", rotation=0)

        sns.heatmap(
            s_matrix,
            ax=ax2,
            annot=True,
            fmt=".2f",
            cmap="YlOrRd",
            xticklabels=plot_parties,
            yticklabels=plot_parties,
            vmin=vmin,
            vmax=vmax,
            linewidths=0.5,
        )
        ax2.set_title("Senado — Co-votación")
        ax2.tick_params(axis="x", rotation=45)
        ax2.tick_params(axis="y", rotation=0)

        fig.suptitle("Matrices de Co-votación Partido×Partido", fontsize=14, fontweight="bold")
        fig.tight_layout()
        fig.savefig(BIC_OUTPUT / "alianzas_bicameral.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  → alianzas_bicameral.png generado")

    return metrics_rows


# ===========================================================================
# ANÁLISIS 4: Poder Comparado en Reformas
# ===========================================================================


def analyze_poder():
    """Compara poder empírico y votaciones de mayoría calificada entre cámaras."""
    print("\n" + "=" * 80)
    print("ANÁLISIS 4: PODER COMPARADO EN REFORMAS")
    print("=" * 80)

    # Read power comparison tables
    dip_poder = read_csv(DIP_OUTPUT / "comparacion_poder.csv")
    sen_poder = read_csv(SEN_OUTPUT / "comparacion_poder.csv")

    # Read vote details
    dip_detalle = read_csv(DIP_OUTPUT / "votaciones_detalle.csv")
    sen_detalle = read_csv(SEN_OUTPUT / "votaciones_detalle.csv")

    # Read dissidents
    dip_disid = read_csv(DIP_OUTPUT / "disidentes.csv")
    sen_disid = read_csv(SEN_OUTPUT / "disidentes.csv")

    # --- 4a: Normalize party names in poder tables ---
    for row in dip_poder:
        row["partido_norm"] = norm_party(row.get("partido", ""))
    for row in sen_poder:
        row["partido_norm"] = ORG_NORM.get(
            row.get("org_id", ""), norm_party(row.get("partido", ""))
        )

    # --- 4b: Build power comparison ---
    dip_power = {r["partido_norm"]: r for r in dip_poder}
    sen_power = {r["partido_norm"]: r for r in sen_poder}
    common = sorted(set(dip_power.keys()) & set(sen_power.keys()))

    poder_rows = []
    for party in common:
        d = dip_power[party]
        s = sen_power[party]
        emp_d = float(d.get("empirico_pct", 0))
        emp_s = float(s.get("empirico_pct", 0))
        ratio = emp_s / emp_d if emp_d > 0 else None

        poder_rows.append(
            {
                "partido": party,
                "escanos_D": d.get("escanos", ""),
                "escanos_S": s.get("escanos", ""),
                "poder_empirico_D": round(emp_d, 2),
                "poder_empirico_S": round(emp_s, 2),
                "ratio_S_D": round(ratio, 2) if ratio else "N/A",
            }
        )

    with open(BIC_OUTPUT / "poder_comparado.csv", "w", newline="", encoding="utf-8") as f:
        if poder_rows:
            writer = csv.DictWriter(f, fieldnames=poder_rows[0].keys())
            writer.writeheader()
            writer.writerows(poder_rows)

    print(f"\n  Poder empírico comparado ({len(poder_rows)} partidos):")
    print(f"  {'Partido':<14} {'Esc_D':>6} {'Esc_S':>6} {'Emp_D%':>8} {'Emp_S%':>8} {'Ratio':>8}")
    print(f"  {'-' * 56}")
    for r in sorted(poder_rows, key=lambda x: -float(x.get("poder_empirico_D", 0))):
        print(
            f"  {r['partido']:<14} {r['escanos_D']:>6} {r['escanos_S']:>6} "
            f"{r['poder_empirico_D']:>8.2f} {r['poder_empirico_S']:>8.2f} "
            f"{str(r['ratio_S_D']):>8}"
        )

    # --- 4c: Calificada analysis ---
    dip_calif = [r for r in dip_detalle if r.get("requirement") == "mayoria_calificada"]
    sen_calif = [r for r in sen_detalle if r.get("requirement") == "mayoria_calificada"]

    # Count critical parties in calificada
    dip_crit_parties = defaultdict(int)
    for r in dip_calif:
        cps = r.get("critical_parties", "")
        if cps:
            for cp in cps.split("|"):
                pn = ORG_NORM.get(cp.strip(), cp.strip())
                dip_crit_parties[pn] += 1

    sen_crit_parties = defaultdict(int)
    for r in sen_calif:
        cps = r.get("critical_parties", "")
        if cps:
            for cp in cps.split("|"):
                pn = ORG_NORM.get(cp.strip(), cp.strip())
                sen_crit_parties[pn] += 1

    calif_rows = []
    all_calif_parties = sorted(set(list(dip_crit_parties.keys()) + list(sen_crit_parties.keys())))
    for party in all_calif_parties:
        calif_rows.append(
            {
                "partido": party,
                "critico_en_D": dip_crit_parties.get(party, 0),
                "total_calificada_D": len(dip_calif),
                "critico_en_S": sen_crit_parties.get(party, 0),
                "total_calificada_S": len(sen_calif),
            }
        )

    with open(BIC_OUTPUT / "calificada_comparada.csv", "w", newline="", encoding="utf-8") as f:
        if calif_rows:
            writer = csv.DictWriter(f, fieldnames=calif_rows[0].keys())
            writer.writeheader()
            writer.writerows(calif_rows)

    print(f"\n  Votaciones de mayoría calificada:")
    print(
        f"    Diputados: {len(dip_calif)} (aprobadas: {sum(1 for r in dip_calif if r.get('result') == 'aprobada')})"
    )
    print(
        f"    Senado: {len(sen_calif)} (aprobadas: {sum(1 for r in sen_calif if r.get('result') == 'aprobada')})"
    )

    print(f"\n  Partidos críticos en calificada:")
    print(f"  {'Partido':<14} {'Crítico_D':>10} {'Crítico_S':>10}")
    print(f"  {'-' * 38}")
    for r in calif_rows:
        print(f"  {r['partido']:<14} {r['critico_en_D']:>10} {r['critico_en_S']:>10}")

    # --- 4d: Disidentes comparison ---
    print(f"\n  Top disidentes:")
    print(f"  {'Diputados':<40} {'Senado':<40}")
    print(f"  {'-' * 80}")
    for i in range(max(len(dip_disid), len(sen_disid))):
        d = dip_disid[i] if i < len(dip_disid) else None
        s = sen_disid[i] if i < len(sen_disid) else None
        d_str = f"{d['nombre'][:25]:<25} ({d['partido']}, {d['disidencia_pct']}%)" if d else ""
        s_str = f"{s['nombre'][:25]:<25} ({s['partido']}, {s['disidencia_pct']}%)" if s else ""
        print(f"  {d_str:<40} {s_str:<40}")

    avg_d = np.mean([float(r["disidencia_pct"]) for r in dip_disid]) if dip_disid else 0
    avg_s = np.mean([float(r["disidencia_pct"]) for r in sen_disid]) if sen_disid else 0
    print(f"\n  Disidencia promedio top-10: Diputados={avg_d:.1f}%, Senado={avg_s:.1f}%")

    # --- Plot 1: Grouped bar chart ---
    fig, ax = plt.subplots(figsize=(12, 7))
    plot_parties = [r["partido"] for r in poder_rows if r["partido"] in COMMON_PARTIES]
    plot_parties_sorted = sorted(
        plot_parties,
        key=lambda p: (
            -(
                float(dip_power.get(p, {}).get("empirico_pct", 0))
                + float(sen_power.get(p, {}).get("empirico_pct", 0))
            )
        ),
    )

    x = np.arange(len(plot_parties_sorted))
    width = 0.35

    d_vals = [float(dip_power.get(p, {}).get("empirico_pct", 0)) for p in plot_parties_sorted]
    s_vals = [float(sen_power.get(p, {}).get("empirico_pct", 0)) for p in plot_parties_sorted]

    bars1 = ax.bar(
        x - width / 2,
        d_vals,
        width,
        label="Diputados",
        color="#003399",
        edgecolor="black",
        linewidth=0.5,
    )
    bars2 = ax.bar(
        x + width / 2,
        s_vals,
        width,
        label="Senado",
        color="#CC0000",
        edgecolor="black",
        linewidth=0.5,
        alpha=0.8,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(plot_parties_sorted, fontsize=11)
    ax.set_ylabel("Poder Empírico (%)")
    ax.set_title("Poder Empírico por Partido: Diputados vs Senado")
    ax.legend(fontsize=12)
    ax.grid(axis="y", alpha=0.3)

    # Add value labels
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + 0.3,
                f"{h:.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    for bar in bars2:
        h = bar.get_height()
        if h > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + 0.3,
                f"{h:.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    fig.tight_layout()
    fig.savefig(BIC_OUTPUT / "poder_bicameral_barras.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → poder_bicameral_barras.png generado")

    return poder_rows


# ===========================================================================
# Main
# ===========================================================================


def main():
    print("=" * 80)
    print("ANÁLISIS BICAMERAL — Observatorio del Congreso de la Unión")
    print(f"Proyecto: {ROOT}")
    print(f"Diputados: {DIP_OUTPUT}")
    print(f"Senado: {SEN_OUTPUT}")
    print(f"Output: {BIC_OUTPUT}")
    print("=" * 80)

    BIC_OUTPUT.mkdir(parents=True, exist_ok=True)

    # Verify inputs exist
    missing = []
    for path in [
        DIP_OUTPUT / "nominate" / "coordenadas_cross.csv",
        SEN_OUTPUT / "nominate" / "coordenadas_cross.csv",
        DIP_OUTPUT / "dinamica" / "disciplina_partidista.csv",
        SEN_OUTPUT / "dinamica" / "disciplina_partidista.csv",
        DIP_OUTPUT / "dinamica" / "evolucion_metricas.csv",
        SEN_OUTPUT / "dinamica" / "evolucion_metricas.csv",
        DIP_OUTPUT / "matriz_partidos.csv",
        SEN_OUTPUT / "matriz_partidos.csv",
        DIP_OUTPUT / "comparacion_poder.csv",
        SEN_OUTPUT / "comparacion_poder.csv",
        DIP_OUTPUT / "votaciones_detalle.csv",
        SEN_OUTPUT / "votaciones_detalle.csv",
        DIP_OUTPUT / "disidentes.csv",
        SEN_OUTPUT / "disidentes.csv",
    ]:
        if not path.exists():
            missing.append(str(path))

    if missing:
        print("\n⚠ ARCHIVOS FALTANTES:")
        for m in missing:
            print(f"  - {m}")
        print("\nEjecuta primero las Fase 1 (Diputados y Senado) y el fix del prerrequisito.")
        return

    # Run 4 analyses
    nominate_results = analyze_nominate()
    disciplina_results = analyze_disciplina()
    covotacion_results = analyze_covotacion()
    poder_results = analyze_poder()

    # Final summary
    print("\n" + "=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)

    print(f"\n  Archivos generados en {BIC_OUTPUT}/:")
    for f in sorted(BIC_OUTPUT.iterdir()):
        print(f"    ✓ {f.name}")

    print(f"\n  Análisis 1 (NOMINATE): {len(nominate_results)} partidos comparados")
    print(f"  Análisis 2 (Disciplina): {len(disciplina_results)} pares comparados")
    print(f"  Análisis 3 (Co-votación): {len(covotacion_results)} legislaturas comparadas")
    print(f"  Análisis 4 (Poder): {len(poder_results)} partidos comparados")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
