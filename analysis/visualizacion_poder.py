"""
visualizacion_poder.py — Gráficas de Poder Legislativo
Observatorio del Congreso de la Unión (LXVI Legislatura, Cámara de Diputados)

Genera 6 visualizaciones:
1. Barras agrupadas: Poder nominal vs Shapley vs Banzhaf (Simple y Calificada)
2. Barras horizontales: Poder empírico por partido
3. Comparación triple: Nominal vs Shapley vs Banzhaf vs Empírico (mayoría simple)
4. Línea temporal: Evolución del poder empírico acumulado
5. Reforma Judicial: Barras apiladas VE04 con línea de mayoría calificada
6. Heatmap: Patrón de votación por partido × votación

Uso: python3 analysis/visualizacion_poder.py
"""

import matplotlib

matplotlib.use("Agg")  # Sin display — backend no interactivo

import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from analysis.constants import ORG_TO_SHORT, PARTY_COLORS

# ---------------------------------------------------------------------------
# Configuración global
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent / "db" / "congreso.db"
OUTPUT_DIR = Path(__file__).parent / "analisis-diputados/output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Normalizar nombres de grupo a org_id
GROUP_TO_ORG = {
    "Morena": "O01",
    "PT": "O02",
    "PVEM": "O03",
    "PAN": "O04",
    "PRI": "O05",
    "MC": "O06",
    "PRD": "O07",
    "Independientes": "O11",
    "O01": "O01",
    "O02": "O02",
    "O03": "O03",
    "O04": "O04",
    "O05": "O05",
    "O06": "O06",
    "O07": "O07",
    "O11": "O11",
}

PARTY_ORDER = ["Morena", "PT", "PVEM", "PAN", "PRI", "MC", "Independientes"]

# Estilo global
plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "#f8f8f8",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "font.size": 11,
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_group(group_val):
    """Normaliza vote.group a org_id."""
    if group_val is None:
        return None
    return GROUP_TO_ORG.get(group_val, group_val)


def get_org_name(org_id):
    """Retorna nombre corto del partido."""
    return ORG_TO_SHORT.get(org_id, org_id)


def clean_pct_column(series):
    """Limpia una columna que puede tener '%' como string → float."""
    return (
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.strip()
        .pipe(pd.to_numeric, errors="coerce")
    )


def get_party_color(nombre):
    """Retorna color para un partido, gris si no encontrado."""
    return PARTY_COLORS.get(nombre, "#808080")


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------


def load_csvs():
    """Carga y limpia todos los CSVs necesarios."""
    poder_completo = pd.read_csv(OUTPUT_DIR / "poder_completo.csv")
    comparacion = pd.read_csv(OUTPUT_DIR / "comparacion_poder.csv")
    poder_empirico = pd.read_csv(OUTPUT_DIR / "poder_empirico.csv")
    disidentes = pd.read_csv(OUTPUT_DIR / "disidentes.csv")

    # Limpiar columnas con % en poder_completo
    for col in ["Nominal_%", "Shapley_Shubik_%", "Banzhaf_%"]:
        if col in poder_completo.columns:
            poder_completo[col] = clean_pct_column(poder_completo[col])

    # Limpiar columnas con % o _pct en comparacion
    for col in comparacion.columns:
        if "%" in col or "_pct" in col:
            comparacion[col] = clean_pct_column(comparacion[col])

    # Limpiar poder_empirico
    for col in poder_empirico.columns:
        if "%" in col or "poder" in col.lower():
            poder_empirico[col] = clean_pct_column(poder_empirico[col])

    return poder_completo, comparacion, poder_empirico, disidentes


# ---------------------------------------------------------------------------
# Gráfica 1: Poder nominal vs Shapley vs Banzhaf (Simple y Calificada)
# ---------------------------------------------------------------------------


def plot_nominal_vs_indices(poder_completo):
    """Barras agrupadas: Nominal vs Shapley vs Banzhaf para Simple y Calificada."""
    umbrales = ["Simple (251/500)", "Calificada 2/3 (334/500)"]
    titulos = ["Mayoría Simple (251/500)", "Mayoría Calificada (334/500)"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    for ax, umbral, titulo in zip([ax1, ax2], umbrales, titulos):
        df = poder_completo[poder_completo["Umbral"] == umbral].copy()

        # Ordenar partidos
        df["orden"] = df["Partido"].map({p: i for i, p in enumerate(PARTY_ORDER)})
        df = df.sort_values("orden")

        partidos = df["Partido"].values
        x = np.arange(len(partidos))
        width = 0.25

        bars_nom = ax.bar(
            x - width,
            df["Nominal_%"],
            width,
            label="Nominal",
            color="#999999",
            edgecolor="white",
            linewidth=0.5,
        )
        bars_ss = ax.bar(
            x,
            df["Shapley_Shubik_%"],
            width,
            label="Shapley-Shubik",
            color="#003399",
            edgecolor="white",
            linewidth=0.5,
        )
        bars_bz = ax.bar(
            x + width,
            df["Banzhaf_%"],
            width,
            label="Banzhaf",
            color="#FF8C00",
            edgecolor="white",
            linewidth=0.5,
        )

        ax.set_xlabel("Partido")
        ax.set_ylabel("Porcentaje de poder (%)")
        ax.set_title(titulo, fontsize=13, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(partidos, rotation=30, ha="right")
        ax.set_ylim(0, 100)
        ax.yaxis.set_major_formatter(mtick.PercentFormatter())

        # Leyenda solo en el primer subplot
        if ax == ax1:
            ax.legend(loc="upper right", fontsize=10)

        # Anotar valores en las barras más altas (>10%)
        for bars in [bars_nom, bars_ss, bars_bz]:
            for bar in bars:
                h = bar.get_height()
                if h > 5:
                    ax.annotate(
                        f"{h:.1f}%",
                        xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                    )

    fig.suptitle(
        "Poder Nominal vs Índices de Poder — LXVI Legislatura",
        fontsize=15,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()
    filepath = OUTPUT_DIR / "poder_nominal_vs_indices.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {filepath.name}")


# ---------------------------------------------------------------------------
# Gráfica 2: Poder empírico por partido (barras horizontales)
# ---------------------------------------------------------------------------


def plot_poder_empirico(poder_empirico, comparacion):
    """Barras horizontales mostrando poder empírico por partido."""
    fig, ax = plt.subplots(figsize=(12, 6))

    # Merge para tener escaños + empírico
    df = comparacion[["partido", "escanos"]].copy()
    df = df.rename(columns={"partido": "Partido", "escanos": "Escaños"})

    emp = poder_empirico[["partido", "poder_empirico"]].copy()
    emp = emp.rename(columns={"partido": "Partido", "poder_empirico": "Poder_Empirico"})
    # Convertir a porcentaje
    emp["Poder_Empirico"] = emp["Poder_Empirico"] * 100

    df = df.merge(emp, on="Partido", how="left")
    df["Poder_Empirico"] = df["Poder_Empirico"].fillna(0)

    # Ordenar por poder empírico descendente
    df = df.sort_values("Poder_Empirico", ascending=True)

    colores = [get_party_color(p) for p in df["Partido"]]
    bars = ax.barh(
        df["Partido"],
        df["Poder_Empirico"],
        color=colores,
        edgecolor="white",
        linewidth=0.5,
        height=0.6,
    )

    # Anotaciones con el porcentaje
    for bar, val in zip(bars, df["Poder_Empirico"]):
        ax.annotate(
            f"{val:.1f}%",
            xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(5, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xlabel("Poder empírico (% de votaciones donde fue crítico)")
    ax.set_ylabel("")
    ax.set_title(
        "Poder Empírico por Partido — LXVI Legislatura",
        fontsize=14,
        fontweight="bold",
    )
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlim(0, max(df["Poder_Empirico"]) * 1.2 + 5)

    plt.tight_layout()
    filepath = OUTPUT_DIR / "poder_empirico.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {filepath.name}")


# ---------------------------------------------------------------------------
# Gráfica 3: Comparación triple (Nominal vs Shapley vs Banzhaf vs Empírico)
# ---------------------------------------------------------------------------


def plot_comparacion_triple(comparacion):
    """Barras agrupadas con 4 métricas para mayoría simple."""
    fig, ax = plt.subplots(figsize=(16, 7))

    df = comparacion.copy()

    # Asegurar orden por escaños descendente
    df = df.sort_values("escanos", ascending=False)

    partidos = df["partido"].values
    x = np.arange(len(partidos))
    width = 0.2

    bars_nom = ax.bar(
        x - 1.5 * width,
        df["nominal_pct"],
        width,
        label="Nominal",
        color="#999999",
        edgecolor="white",
    )
    bars_ss = ax.bar(
        x - 0.5 * width,
        df["shapley_shubik_pct"],
        width,
        label="Shapley-Shubik",
        color="#003399",
        edgecolor="white",
    )
    bars_bz = ax.bar(
        x + 0.5 * width,
        df["banzhaf_pct"],
        width,
        label="Banzhaf",
        color="#FF8C00",
        edgecolor="white",
    )
    bars_emp = ax.bar(
        x + 1.5 * width,
        df["empirico_pct"],
        width,
        label="Empírico",
        color="#228B22",
        edgecolor="white",
    )

    # Anotar valores en barras > 5%
    for bars in [bars_nom, bars_ss, bars_bz, bars_emp]:
        for bar in bars:
            h = bar.get_height()
            if h > 3:
                ax.annotate(
                    f"{h:.1f}%",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 2),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                )

    ax.set_xlabel("Partido")
    ax.set_ylabel("Porcentaje de poder (%)")
    ax.set_title(
        "Poder Nominal vs Teórico vs Empírico — Mayoría Simple\nLXVI Legislatura",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(partidos, rotation=30, ha="right")
    ax.set_ylim(0, max(df["nominal_pct"].max(), df["empirico_pct"].max()) * 1.15)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.legend(loc="upper right", fontsize=10)

    plt.tight_layout()
    filepath = OUTPUT_DIR / "poder_comparacion_triple.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {filepath.name}")


# ---------------------------------------------------------------------------
# Gráfica 4: Línea temporal — Poder empírico acumulado
# ---------------------------------------------------------------------------


def plot_linea_temporal():
    """Evolución del poder empírico por partido a lo largo de las votaciones."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # Obtener votaciones ordenadas por fecha
    cur.execute("""
        SELECT ve.id, ve.start_date
        FROM vote_event ve
        WHERE ve.result IS NOT NULL
        ORDER BY ve.start_date, ve.id
    """)
    ve_rows = cur.fetchall()
    ve_ids = [r[0] for r in ve_rows]

    if not ve_ids:
        print("  ✗ Sin votaciones para gráfica temporal")
        conn.close()
        return

    # Para cada votación, obtener votos por partido y calcular críticos
    import math

    # Track critical counts acumulados por partido
    org_crit_count = defaultdict(int)
    timeline_data = []  # [(ve_id, date, {org: cumulative_pct})]

    for i, (ve_id, ve_date) in enumerate(ve_rows):
        # Obtener requerimiento
        cur.execute(
            """
            SELECT m.requirement
            FROM vote_event ve
            JOIN motion m ON ve.motion_id = m.id
            WHERE ve.id = ?
        """,
            (ve_id,),
        )
        req_row = cur.fetchone()
        requirement = req_row[0] if req_row else "mayoria_simple"

        # Obtener votos por partido
        cur.execute(
            """
            SELECT "group", option, COUNT(*) as cnt
            FROM vote
            WHERE vote_event_id = ?
            GROUP BY "group", option
        """,
            (ve_id,),
        )

        party_votes = {}
        for group_val, option, cnt in cur.fetchall():
            org = normalize_group(group_val)
            if org is None:
                continue
            if org not in party_votes:
                party_votes[org] = {
                    "favor": 0,
                    "contra": 0,
                    "abstencion": 0,
                    "ausente": 0,
                }
            if option == "a_favor":
                party_votes[org]["favor"] += cnt
            elif option == "en_contra":
                party_votes[org]["contra"] += cnt
            elif option == "abstencion":
                party_votes[org]["abstencion"] += cnt
            elif option == "ausente":
                party_votes[org]["ausente"] += cnt

        # Calcular mayoría necesaria
        total_asistentes = sum(
            pv["favor"] + pv["contra"] + pv["abstencion"] for pv in party_votes.values()
        )
        if requirement == "mayoria_calificada":
            majority = math.ceil(2 / 3 * 500)
        else:
            majority = math.ceil(total_asistentes / 2) if total_asistentes > 0 else 1

        # Obtener resultado
        cur.execute("SELECT result FROM vote_event WHERE id = ?", (ve_id,))
        result_row = cur.fetchone()
        result = result_row[0] if result_row else None

        # Encontrar críticos
        critical = []
        if result == "aprobada":
            total_winning = sum(pv["favor"] for pv in party_votes.values())
            for org, pv in party_votes.items():
                if pv["favor"] > 0:
                    remaining = total_winning - pv["favor"]
                    if remaining < majority:
                        critical.append(org)
        elif result == "rechazada":
            total_winning = sum(pv["contra"] for pv in party_votes.values())
            for org, pv in party_votes.items():
                if pv["contra"] > 0:
                    remaining = total_winning - pv["contra"]
                    if remaining < majority:
                        critical.append(org)

        # Actualizar conteo acumulado
        for org in critical:
            org_crit_count[org] += 1

        # Asegurar todos los partidos activos están en el diccionario
        all_orgs = set(ORG_TO_SHORT.keys())
        for org in all_orgs:
            if org not in org_crit_count:
                org_crit_count[org] = 0

        # Calcular % acumulado
        n_votaciones = i + 1
        cumulative = {}
        for org in all_orgs:
            cumulative[org] = (org_crit_count[org] / n_votaciones) * 100 if n_votaciones > 0 else 0

        timeline_data.append((ve_id, ve_date, cumulative.copy()))

    # Asegurar timeline_data existe y tiene datos
    if not timeline_data:
        print("  ✗ Sin datos para gráfica temporal")
        conn.close()
        return

    # --- Graficar ---
    fig, ax = plt.subplots(figsize=(16, 7))

    n = len(timeline_data)
    x_pos = np.arange(n)
    x_labels = [td[0] for td in timeline_data]  # VE IDs

    # Partidos a graficar (solo los que tuvieron algún poder)
    active_orgs = [org for org, count in org_crit_count.items() if count > 0]
    # Añadir Morena siempre
    if "O01" not in active_orgs:
        active_orgs.append("O01")

    for org in sorted(active_orgs):
        nombre = get_org_name(org)
        valores = [td[2].get(org, 0) for td in timeline_data]
        color = get_party_color(nombre)
        ax.plot(
            x_pos,
            valores,
            label=nombre,
            color=color,
            linewidth=2,
            marker="o",
            markersize=3,
            alpha=0.85,
        )

    ax.set_xlabel("Votación")
    ax.set_ylabel("Poder empírico acumulado (%)")
    ax.set_title(
        "Evolución del Poder Empírico por Partido — LXVI Legislatura",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x_pos[:: max(1, n // 15)])
    ax.set_xticklabels(
        [x_labels[i] for i in range(0, n, max(1, n // 15))],
        rotation=45,
        ha="right",
        fontsize=9,
    )
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.legend(loc="upper left", fontsize=9, ncol=2)
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    filepath = OUTPUT_DIR / "poder_evolucion_temporal.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {filepath.name}")
    conn.close()


# ---------------------------------------------------------------------------
# Gráfica 5: Reforma Judicial — Detalle VE04
# ---------------------------------------------------------------------------


def plot_reforma_judicial():
    """Barras apiladas por partido para VE04 con línea de mayoría calificada."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # Obtener datos de VE04 desde la BD
    ve_id = "VE04"
    cur.execute(
        """
        SELECT "group", option, COUNT(*) as cnt
        FROM vote
        WHERE vote_event_id = ?
        GROUP BY "group", option
    """,
        (ve_id,),
    )

    party_data = {}
    for group_val, option, cnt in cur.fetchall():
        org = normalize_group(group_val)
        if org is None:
            continue
        nombre = get_org_name(org)
        if nombre not in party_data:
            party_data[nombre] = {
                "a_favor": 0,
                "en_contra": 0,
                "ausente": 0,
                "abstencion": 0,
            }
        if option in party_data[nombre]:
            party_data[nombre][option] += cnt

    conn.close()

    if not party_data:
        print("  ✗ Sin datos para Reforma Judicial")
        return

    # Ordenar partidos: primero los que votaron a favor, luego en contra
    favor_parties = sorted(
        [p for p in party_data if party_data[p]["a_favor"] > 0],
        key=lambda p: party_data[p]["a_favor"],
        reverse=True,
    )
    contra_parties = sorted(
        [p for p in party_data if party_data[p]["en_contra"] > 0],
        key=lambda p: party_data[p]["en_contra"],
        reverse=True,
    )
    ordered_parties = favor_parties + contra_parties

    # Construir arrays
    favor_vals = [party_data[p]["a_favor"] for p in ordered_parties]
    contra_vals = [party_data[p]["en_contra"] for p in ordered_parties]
    ausente_vals = [party_data[p]["ausente"] for p in ordered_parties]

    fig, ax = plt.subplots(figsize=(14, 7))

    x = np.arange(len(ordered_parties))
    width = 0.6

    bars_favor = ax.bar(x, favor_vals, width, label="A favor", color="#2ecc71", edgecolor="white")
    bars_contra = ax.bar(
        x,
        contra_vals,
        width,
        bottom=favor_vals,
        label="En contra",
        color="#e74c3c",
        edgecolor="white",
    )
    bars_ausente = ax.bar(
        x,
        ausente_vals,
        width,
        bottom=[f + c for f, c in zip(favor_vals, contra_vals)],
        label="Ausente",
        color="#bdc3c7",
        edgecolor="white",
    )

    # Línea de mayoría calificada (334)
    ax.axhline(
        y=334,
        color="#2c3e50",
        linestyle="--",
        linewidth=2,
        label="Mayoría calificada (334)",
    )

    # Anotar margen
    total_favor = sum(favor_vals)
    margin = total_favor - 334
    ax.annotate(
        f"A favor total: {total_favor} (margen: +{margin})",
        xy=(len(ordered_parties) - 0.5, 334),
        xytext=(10, 15),
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#2c3e50"),
    )

    # Anotar valores dentro de las barras
    for i, (f, c, a) in enumerate(zip(favor_vals, contra_vals, ausente_vals)):
        if f > 0:
            ax.text(
                i,
                f / 2,
                str(f),
                ha="center",
                va="center",
                fontweight="bold",
                fontsize=10,
                color="white",
            )
        if c > 0:
            ax.text(
                i,
                f + c / 2,
                str(c),
                ha="center",
                va="center",
                fontweight="bold",
                fontsize=10,
                color="white",
            )
        if a > 0:
            ax.text(
                i,
                f + c + a / 2,
                str(a),
                ha="center",
                va="center",
                fontweight="bold",
                fontsize=9,
                color="#555555",
            )

    ax.set_xlabel("Partido")
    ax.set_ylabel("Votos")
    ax.set_title(
        "Reforma Judicial (VE04) — Desglose por Partido\nLXVI Legislatura",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(ordered_parties, rotation=30, ha="right")
    ax.legend(loc="upper right", fontsize=10)

    plt.tight_layout()
    filepath = OUTPUT_DIR / "reforma_judicial_detalle.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {filepath.name}")


# ---------------------------------------------------------------------------
# Gráfica 6: Heatmap de votaciones
# ---------------------------------------------------------------------------


def plot_heatmap_votaciones():
    """Heatmap partido × votación mostrando alineamiento."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # Obtener votaciones ordenadas por fecha
    cur.execute("""
        SELECT ve.id, ve.start_date
        FROM vote_event ve
        WHERE ve.result IS NOT NULL
        ORDER BY ve.start_date, ve.id
    """)
    ve_rows = cur.fetchall()
    ve_ids = [r[0] for r in ve_rows]

    if not ve_ids:
        print("  ✗ Sin votaciones para heatmap")
        conn.close()
        return

    # Partidos a incluir (excluir PRD si no tiene votos)
    party_orgs = ["O01", "O02", "O03", "O04", "O05", "O06", "O11"]
    party_names = [get_org_name(org) for org in party_orgs]

    # Construir matriz: filas=partidos, columnas=votaciones
    matrix = np.full((len(party_orgs), len(ve_ids)), np.nan)

    for j, (ve_id, _) in enumerate(ve_rows):
        cur.execute(
            """
            SELECT "group", option, COUNT(*) as cnt
            FROM vote
            WHERE vote_event_id = ?
            GROUP BY "group", option
        """,
            (ve_id,),
        )

        party_options = defaultdict(lambda: defaultdict(int))
        for group_val, option, cnt in cur.fetchall():
            org = normalize_group(group_val)
            if org and org in party_orgs:
                party_options[org][option] += cnt

        for i, org in enumerate(party_orgs):
            opts = party_options.get(org, {})
            asistentes = (
                opts.get("a_favor", 0) + opts.get("en_contra", 0) + opts.get("abstencion", 0)
            )

            if asistentes == 0:
                matrix[i, j] = 0  # ausente
            elif opts.get("a_favor", 0) > asistentes / 2:
                matrix[i, j] = 2  # mayoría a favor
            elif opts.get("en_contra", 0) > asistentes / 2:
                matrix[i, j] = 1  # mayoría en contra
            else:
                matrix[i, j] = -1  # split

    conn.close()

    # --- Graficar ---
    fig, ax = plt.subplots(figsize=(20, 6))

    # Colormap personalizado: -1=rojo, 0=gris, 1=naranja, 2=verde
    from matplotlib.colors import ListedColormap

    cmap = ListedColormap(["#e74c3c", "#bdc3c7", "#e67e22", "#2ecc71"])

    im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=-1, vmax=2, interpolation="nearest")

    # Labels
    ax.set_yticks(range(len(party_names)))
    ax.set_yticklabels(party_names, fontsize=10)
    ax.set_xticks(range(len(ve_ids)))
    ax.set_xticklabels(ve_ids, rotation=90, fontsize=6)

    ax.set_xlabel("Votación (orden cronológico)")
    ax.set_ylabel("Partido")
    ax.set_title(
        "Patrón de Votación por Partido — LXVI Legislatura",
        fontsize=14,
        fontweight="bold",
    )

    # Leyenda manual
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor="#2ecc71", label="A favor (mayoría del partido)"),
        Patch(facecolor="#e67e22", label="En contra (mayoría del partido)"),
        Patch(facecolor="#bdc3c7", label="Ausente / abstención masiva"),
        Patch(facecolor="#e74c3c", label="Voto dividido (split)"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper right",
        fontsize=8,
        ncol=2,
        bbox_to_anchor=(1.0, -0.1),
    )

    plt.tight_layout()
    filepath = OUTPUT_DIR / "heatmap_votaciones.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {filepath.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 70)
    print("VISUALIZACIÓN DE PODER — Observatorio del Congreso de la Unión")
    print("LXVI Legislatura — Cámara de Diputados")
    print("=" * 70)

    # Cargar CSVs
    print("\nCargando datos...")
    poder_completo, comparacion, poder_empirico, disidentes = load_csvs()
    print(f"  poder_completo: {len(poder_completo)} filas")
    print(f"  comparacion:    {len(comparacion)} filas")
    print(f"  poder_empirico: {len(poder_empirico)} filas")
    print(f"  disidentes:     {len(disidentes)} filas")

    # Generar gráficas (con try/except individual)
    print("\nGenerando gráficas...")

    plots = [
        (
            "Gráfica 1: Nominal vs Índices",
            lambda: plot_nominal_vs_indices(poder_completo),
        ),
        (
            "Gráfica 2: Poder empírico",
            lambda: plot_poder_empirico(poder_empirico, comparacion),
        ),
        ("Gráfica 3: Comparación triple", lambda: plot_comparacion_triple(comparacion)),
        ("Gráfica 4: Evolución temporal", plot_linea_temporal),
        ("Gráfica 5: Reforma Judicial", plot_reforma_judicial),
        ("Gráfica 6: Heatmap votaciones", plot_heatmap_votaciones),
    ]

    errors = []
    for name, fn in plots:
        try:
            fn()
        except Exception as e:
            errors.append((name, str(e)))
            print(f"  ✗ {name}: ERROR — {e}")

    # Resumen
    print("\n" + "=" * 70)
    print(f"Gráficas generadas en: {OUTPUT_DIR}")
    if errors:
        print(f"\nErrores ({len(errors)}):")
        for name, err in errors:
            print(f"  - {name}: {err}")
    else:
        print("\nTodas las gráficas generadas exitosamente.")
    print("=" * 70)


if __name__ == "__main__":
    main()
