"""
analysis/evolucion_partidos.py — Evolución de Partidos por Legislatura.

Panel partido×legislatura con disciplina, dispersión NOMINATE, poder empírico y tendencias.

Usage:
    python -m analysis.evolucion_partidos --camara diputados
    python -m analysis.evolucion_partidos --camara senado
    python -m analysis.evolucion_partidos --camara ambas
"""

import logging
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import db.constants as _dbc
from analysis.constants import CAMARA_MAP, PARTY_COLORS
from analysis.db import get_connection
from analysis.poder_partidos import shapley_shubik
from db.constants import (
    CAMARA_DIPUTADOS_ID,
    CAMARA_SENADO_ID,
    LEGISLATURAS_ORDERED,
    get_total_seats,
    init_constants_from_db,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"

CAMARA_TO_ORG = {"diputados": CAMARA_DIPUTADOS_ID, "senado": CAMARA_SENADO_ID}
CAMARA_LABEL = {"diputados": "Cámara de Diputados", "senado": "Senado de la República"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_org_short_name(org_id: str) -> str:
    """Retorna nombre corto del partido."""
    return _dbc._ORG_TO_SHORT.get(org_id, org_id)


def _normalize_group(group_val) -> str | None:
    """Normaliza vote.group a org_id."""
    if group_val is None:
        return None
    return _dbc._NAME_TO_ORG.get(group_val, group_val)


# ---------------------------------------------------------------------------
# Paso 1: Panel partido×legislatura
# ---------------------------------------------------------------------------


def build_party_panel(camara: str, db_path: Path) -> pd.DataFrame:
    """Construye panel partido×legislatura.

    Fuentes:
    - trayectorias_panel.csv: disciplina individual + NOMINATE por persona-legislatura
    - SQL: conteos de votaciones y votos por partido-legislatura

    Args:
        camara: 'diputados' o 'senado'
        db_path: Path a congreso.db

    Returns: DataFrame with columns:
        legislatura, partido, org_id, n_legisladores, disciplina_media, disciplina_std,
        dispersion_d1, dispersion_d2, centroide_d1, centroide_d2,
        n_votaciones, n_votos_partido
    """
    # Cargar trayectorias panel
    panel_path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
    if not panel_path.exists():
        raise FileNotFoundError(f"No se encontró {panel_path}")

    panel = pd.read_csv(panel_path)
    logger.info("Cargadas %d filas de trayectorias para %s", len(panel), camara)

    # Agregar por partido-legislatura
    agg = (
        panel.groupby(["legislatura", "partido"])
        .agg(
            n_legisladores=("voter_id", "nunique"),
            disciplina_media=("disciplina", "mean"),
            disciplina_std=("disciplina", "std"),
            dispersion_d1=("dim_1_raw", "std"),
            dispersion_d2=("dim_2_raw", "std"),
            centroide_d1=("dim_1_raw", "mean"),
            centroide_d2=("dim_2_raw", "mean"),
            n_votos_partido=("n_votos", "sum"),
        )
        .reset_index()
    )

    # NaN std cuando hay solo 1 legislador → 0
    for col in ["disciplina_std", "dispersion_d1", "dispersion_d2"]:
        agg[col] = agg[col].fillna(0)

    # Contar votaciones por legislatura desde la BD
    conn = get_connection(db_path)
    org_id = CAMARA_TO_ORG[camara]
    try:
        n_votaciones = pd.read_sql_query(
            """
            SELECT legislatura, COUNT(DISTINCT id) as n_votaciones
            FROM vote_event
            WHERE organization_id = ? AND legislatura IS NOT NULL
            GROUP BY legislatura
            """,
            conn,
            params=(org_id,),
        )
    finally:
        conn.close()

    # Merge n_votaciones
    agg = agg.merge(n_votaciones, on="legislatura", how="left")

    # Mapear partido → org_id usando los mapeos actualizados de db.constants
    short_to_org = {v: k for k, v in _dbc._ORG_TO_SHORT.items()}
    agg["org_id"] = agg["partido"].map(short_to_org)

    # Ordenar por legislatura
    agg["_leg_order"] = agg["legislatura"].map(
        lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99
    )
    agg = (
        agg.sort_values(["_leg_order", "partido"])
        .drop(columns=["_leg_order"])
        .reset_index(drop=True)
    )

    logger.info("Panel partido×legislatura: %d filas para %s", len(agg), camara)
    return agg


# ---------------------------------------------------------------------------
# Paso 2: Poder dinámico por legislatura
# ---------------------------------------------------------------------------


def compute_power_by_legislatura(camara: str, db_path: Path) -> pd.DataFrame:
    """Calcula Shapley-Shubik y Banzhaf empírico por legislatura.

    Para cada legislatura:
    1. Obtener composición (partido → n_escaños) via max voters por partido en un VE
    2. Calcular Shapley-Shubik usando DP
    3. Calcular Banzhaf empírico: para cada VE, determinar partidos críticos

    Returns: DataFrame with columns:
        legislatura, partido, org_id, n_seats, shapley_shubik, banzhaf_pct,
        n_calificadas, n_critical
    """
    conn = get_connection(db_path)

    camara_code = CAMARA_MAP[camara]
    org_id = CAMARA_TO_ORG[camara]
    total_seats = get_total_seats(str(db_path), camara_code)

    # Obtener legislaturas con datos
    legs = pd.read_sql_query(
        """
        SELECT DISTINCT legislatura
        FROM vote_event
        WHERE organization_id = ? AND legislatura IS NOT NULL
        ORDER BY legislatura
        """,
        conn,
        params=(org_id,),
    )["legislatura"].tolist()

    rows = []

    for leg in legs:
        # 1. Composición: max voters por partido en un VE de esta legislatura
        seats_df = pd.read_sql_query(
            """
            SELECT v."group" as grp, COUNT(*) as cnt
            FROM vote v
            JOIN vote_event ve ON v.vote_event_id = ve.id
            WHERE ve.organization_id = ? AND ve.legislatura = ?
              AND v."group" IS NOT NULL
            GROUP BY v.vote_event_id, v."group"
            ORDER BY v."group", cnt DESC
            """,
            conn,
            params=(org_id, leg),
        )

        # Normalizar groups y tomar max por org_id
        org_to_short_keys = set(_dbc._ORG_TO_SHORT.keys())
        seats: dict[str, int] = {}
        for grp, cnt in zip(seats_df["grp"], seats_df["cnt"]):
            oid = _normalize_group(grp)
            if oid and oid in org_to_short_keys:
                seats[oid] = max(seats.get(oid, 0), cnt)

        if not seats:
            continue

        # 2. Shapley-Shubik (mayoría simple)
        quota_simple = math.floor(total_seats / 2) + 1
        ss = shapley_shubik(seats, quota_simple)

        # 3. Banzhaf empírico: analizar cada VE de esta legislatura
        ve_ids = pd.read_sql_query(
            """
            SELECT id FROM vote_event
            WHERE organization_id = ? AND legislatura = ? AND result IS NOT NULL
            """,
            conn,
            params=(org_id, leg),
        )["id"].tolist()

        n_calificadas = 0
        critical_counts: dict[str, int] = {}

        for ve_id in ve_ids:
            # Obtener requirement directamente de vote_event
            req_row = conn.execute(
                "SELECT requirement FROM vote_event WHERE id = ?",
                (ve_id,),
            ).fetchone()
            requirement = req_row[0] if req_row and req_row[0] else "mayoria_simple"

            # Obtener resultado
            result_row = conn.execute(
                "SELECT result FROM vote_event WHERE id = ?", (ve_id,)
            ).fetchone()
            result = result_row[0] if result_row else None

            if requirement == "mayoria_calificada":
                n_calificadas += 1

            # Obtener votos por partido
            votes_df = pd.read_sql_query(
                """
                SELECT "group" as grp, option, COUNT(*) as cnt
                FROM vote WHERE vote_event_id = ?
                GROUP BY "group", option
                """,
                conn,
                params=(ve_id,),
            )

            party_votes: dict[str, dict[str, int]] = {}
            a_favor_total = 0
            for grp, option, cnt in zip(votes_df["grp"], votes_df["option"], votes_df["cnt"]):
                oid = _normalize_group(grp)
                if oid is None:
                    if option == "a_favor":
                        a_favor_total += cnt
                    continue
                if oid not in party_votes:
                    party_votes[oid] = {
                        "favor": 0,
                        "contra": 0,
                        "abstencion": 0,
                        "ausente": 0,
                    }
                party_votes[oid][option] = party_votes[oid].get(option, 0) + cnt
                if option == "a_favor":
                    a_favor_total += cnt

            # Determinar mayoría necesaria
            total_asistentes = sum(
                pv["favor"] + pv["contra"] + pv["abstencion"] for pv in party_votes.values()
            )
            if requirement == "mayoria_calificada":
                mayoria_necesaria = math.ceil(2 / 3 * total_seats)
            else:
                mayoria_necesaria = math.ceil(total_asistentes / 2) if total_asistentes > 0 else 0

            # Encontrar partidos críticos (solo en votaciones aprobadas)
            if result == "aprobada":
                for oid, pv in party_votes.items():
                    if pv["favor"] > 0:
                        remaining = a_favor_total - pv["favor"]
                        if remaining < mayoria_necesaria:
                            critical_counts[oid] = critical_counts.get(oid, 0) + 1

        # Normalizar Banzhaf empírico
        banzhaf_emp: dict[str, float] = {}
        for oid in seats:
            banzhaf_emp[oid] = critical_counts.get(oid, 0) / len(ve_ids) if ve_ids else 0

        # Build rows
        for oid, n_seats in seats.items():
            short_name = _get_org_short_name(oid)
            rows.append(
                {
                    "legislatura": leg,
                    "partido": short_name,
                    "org_id": oid,
                    "n_seats": n_seats,
                    "shapley_shubik": round(ss.get(oid, 0) * 100, 2),
                    "banzhaf_pct": round(banzhaf_emp.get(oid, 0) * 100, 2),
                    "n_calificadas": n_calificadas,
                    "n_critical": critical_counts.get(oid, 0),
                    "n_votaciones": len(ve_ids),
                }
            )

    conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning("Sin datos de poder para %s", camara)
        return df

    # Ordenar
    df["_leg_order"] = df["legislatura"].map(
        lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99
    )
    df = (
        df.sort_values(["_leg_order", "partido"])
        .drop(columns=["_leg_order"])
        .reset_index(drop=True)
    )

    logger.info("Poder dinámico: %d filas para %s", len(df), camara)
    return df


# ---------------------------------------------------------------------------
# Paso 3: Dealignment y consolidación
# ---------------------------------------------------------------------------


def analyze_dealignment(panel: pd.DataFrame) -> pd.DataFrame:
    """Identifica partidos con pérdida de cohesión (dealignment).

    Para cada partido con 3+ legislaturas:
    - Calcular tendencia de disciplina (regresión lineal: disciplina ~ ordinal legislatura)
    - Calcular delta disciplina entre primera y última legislatura
    - Flag: dealignment si disciplina cae >5pp

    Args:
        panel: DataFrame del panel partido×legislatura (output de build_party_panel)

    Returns: DataFrame with columns:
        partido, n_legislaturas, leg_first, leg_last,
        disciplina_first, disciplina_last, delta_disciplina,
        tendencia, es_dealignment
    """
    rows = []

    for partido, grp in panel.groupby("partido"):
        if len(grp) < 3:
            continue

        # Ordenar por legislatura
        grp = grp.copy()
        grp["_order"] = grp["legislatura"].map(
            lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99
        )
        grp = grp.sort_values("_order")

        disc_vals = grp["disciplina_media"].values
        n = len(disc_vals)

        if n < 3:
            continue

        # Regresión lineal simple: y = a + b*x
        x = np.arange(n, dtype=float)
        y = disc_vals
        x_mean = x.mean()
        y_mean = y.mean()
        ss_xy = ((x - x_mean) * (y - y_mean)).sum()
        ss_xx = ((x - x_mean) ** 2).sum()
        slope = ss_xy / ss_xx if ss_xx > 0 else 0

        # Delta disciplina
        first_disc = disc_vals[0]
        last_disc = disc_vals[-1]
        delta = last_disc - first_disc

        # Dealignment: caída > 5 puntos porcentuales
        es_dealignment = delta < -0.05

        rows.append(
            {
                "partido": partido,
                "n_legislaturas": n,
                "leg_first": grp["legislatura"].iloc[0],
                "leg_last": grp["legislatura"].iloc[-1],
                "disciplina_first": round(first_disc, 4),
                "disciplina_last": round(last_disc, 4),
                "delta_disciplina": round(delta, 4),
                "tendencia": round(slope, 6),
                "es_dealignment": es_dealignment,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("delta_disciplina").reset_index(drop=True)

    logger.info(
        "Dealignment: %d partidos analizados, %d con dealignment",
        len(df),
        df["es_dealignment"].sum() if not df.empty else 0,
    )
    return df


# ---------------------------------------------------------------------------
# Paso 4: Visualizaciones
# ---------------------------------------------------------------------------


def plot_disciplina_heatmap(panel: pd.DataFrame, output_dir: Path):
    """Heatmap: partidos × legislaturas con disciplina como color."""
    if panel.empty:
        return

    # Pivot para heatmap
    pivot = panel.pivot_table(
        index="partido",
        columns="legislatura",
        values="disciplina_media",
        aggfunc="first",
    )

    # Ordenar columnas por legislatura
    cols_ordered = [c for c in LEGISLATURAS_ORDERED if c in pivot.columns]
    pivot = pivot[cols_ordered]

    # Ordenar filas por frecuencia
    party_order = panel["partido"].value_counts().index.tolist()
    party_order = [p for p in party_order if p in pivot.index]
    pivot = pivot.loc[party_order]

    fig, ax = plt.subplots(figsize=(12, 8))

    data = pivot.values.astype(float)
    # Mask NaN
    mask = np.isnan(data)

    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=0.7, vmax=1.0)

    ax.set_xticks(range(len(cols_ordered)))
    ax.set_xticklabels(cols_ordered, fontsize=10)
    ax.set_yticks(range(len(party_order)))
    ax.set_yticklabels(party_order, fontsize=10)

    # Annotate cells
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if not mask[i, j]:
                val = data[i, j]
                color = "white" if val < 0.85 else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.3f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=color,
                )

    ax.set_title("Disciplina Partidista por Legislatura", fontsize=14)
    plt.colorbar(im, ax=ax, label="Disciplina media")

    plt.tight_layout()
    out_path = output_dir / "partidos_heatmap_disciplina.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


def plot_power_timeline(power: pd.DataFrame, output_dir: Path):
    """Líneas: poder empírico (Banzhaf) por partido × legislatura."""
    if power.empty:
        return

    # Solo partidos principales (con al menos 1 evento crítico)
    top_parties = power.groupby("partido")["n_critical"].sum()
    top_parties = top_parties[top_parties > 0].sort_values(ascending=False).head(8).index.tolist()

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Panel 1: Shapley-Shubik
    ax = axes[0]
    for party in top_parties:
        pdata = power[power["partido"] == party].copy()
        pdata["_order"] = pdata["legislatura"].map(
            lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99
        )
        pdata = pdata.sort_values("_order")
        color = PARTY_COLORS.get(party)
        ax.plot(
            pdata["legislatura"],
            pdata["shapley_shubik"],
            marker="o",
            label=party,
            color=color,
            linewidth=2,
            markersize=5,
        )
    ax.set_title("Poder Shapley-Shubik por Legislatura", fontsize=12)
    ax.set_ylabel("Shapley-Shubik (%)")
    ax.set_xlabel("Legislatura")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="x", rotation=45)

    # Panel 2: Banzhaf empírico
    ax = axes[1]
    for party in top_parties:
        pdata = power[power["partido"] == party].copy()
        pdata["_order"] = pdata["legislatura"].map(
            lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99
        )
        pdata = pdata.sort_values("_order")
        color = PARTY_COLORS.get(party)
        ax.plot(
            pdata["legislatura"],
            pdata["banzhaf_pct"],
            marker="s",
            label=party,
            color=color,
            linewidth=2,
            markersize=5,
        )
    ax.set_title("Poder Empírico (Banzhaf) por Legislatura", fontsize=12)
    ax.set_ylabel("Banzhaf empírico (%)")
    ax.set_xlabel("Legislatura")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    out_path = output_dir / "partidos_timeline_poder.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


def plot_nominate_ellipses(panel: pd.DataFrame, output_dir: Path):
    """Scatter NOMINATE con ellipses de dispersión por partido-legislatura.

    Solo para los 3-4 partidos principales.
    Muestra la evolución del centroide y dispersión NOMINATE por legislatura.
    """
    if panel.empty:
        return

    # Top partidos por número total de legisladores
    top_parties = panel.groupby("partido")["n_legisladores"].sum()
    top_parties = top_parties.sort_values(ascending=False).head(4).index.tolist()

    fig, ax = plt.subplots(figsize=(14, 9))

    for party in top_parties:
        pdata = panel[panel["partido"] == party].copy()
        pdata["_order"] = pdata["legislatura"].map(
            lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99
        )
        pdata = pdata.sort_values("_order")

        color = PARTY_COLORS.get(party, "#666666")

        # Plot trajectory of centroids
        ax.plot(
            pdata["centroide_d1"],
            pdata["centroide_d2"],
            marker="o",
            label=party,
            color=color,
            linewidth=2,
            markersize=8,
            alpha=0.8,
        )

        # Draw ellipses (2σ) for each legislatura
        for _, row in pdata.iterrows():
            if pd.notna(row["dispersion_d1"]) and pd.notna(row["dispersion_d2"]):
                ellipse = plt.matplotlib.patches.Ellipse(
                    (row["centroide_d1"], row["centroide_d2"]),
                    width=2 * row["dispersion_d1"] * 2,  # 2σ × 2 (full width)
                    height=2 * row["dispersion_d2"] * 2,
                    alpha=0.15,
                    color=color,
                )
                ax.add_patch(ellipse)

                # Annotate legislatura
                ax.annotate(
                    row["legislatura"],
                    (row["centroide_d1"], row["centroide_d2"]),
                    textcoords="offset points",
                    xytext=(5, 5),
                    fontsize=7,
                    alpha=0.7,
                )

    ax.set_xlabel("Dimensión 1 NOMINATE (raw)")
    ax.set_ylabel("Dimensión 2 NOMINATE (raw)")
    ax.set_title(
        "Evolución NOMINATE: Centroides y Dispersión por Partido-Legislatura",
        fontsize=13,
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = output_dir / "partidos_nominate_evolucion.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


# ---------------------------------------------------------------------------
# Paso 5: Runner principal
# ---------------------------------------------------------------------------


def run_evolucion_partidos(camara: str, output_dir: str | None = None):
    """Ejecuta todo el pipeline de evolución de partidos para una cámara.

    Args:
        camara: 'diputados' o 'senado'
        output_dir: Directorio de salida. Default: analysis/analisis-{camara}/output/

    Returns: dict with all DataFrames and files created.
    """
    # Inicializar constantes desde BD — CRÍTICO para mapeos actualizados
    init_constants_from_db(str(DB_PATH))

    if output_dir is None:
        output_dir = str(PROJECT_ROOT / f"analysis/analisis-{camara}/output")
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("=== Pipeline Evolución de Partidos — %s ===", camara.upper())

    # Paso 1: Panel partido×legislatura
    panel = build_party_panel(camara, DB_PATH)

    # Paso 2: Poder dinámico
    power = compute_power_by_legislatura(camara, DB_PATH)

    # Merge poder al panel
    if not power.empty:
        panel = panel.merge(
            power[["legislatura", "org_id", "shapley_shubik", "banzhaf_pct", "n_calificadas"]],
            on=["legislatura", "org_id"],
            how="left",
        )

    # Paso 3: Dealignment
    dealignment = analyze_dealignment(panel)

    # Paso 4: Visualizaciones
    plot_disciplina_heatmap(panel, out_path)
    plot_power_timeline(power, out_path)
    plot_nominate_ellipses(panel, out_path)

    # Guardar CSVs
    files_created = []

    f1 = out_path / "evolucion_partidos.csv"
    panel.to_csv(f1, index=False)
    files_created.append(str(f1))
    logger.info("Guardado: %s (%d filas)", f1, len(panel))

    f2 = out_path / "poder_dinamico.csv"
    power.to_csv(f2, index=False)
    files_created.append(str(f2))
    logger.info("Guardado: %s (%d filas)", f2, len(power))

    f3 = out_path / "dealignment.csv"
    dealignment.to_csv(f3, index=False)
    files_created.append(str(f3))
    logger.info("Guardado: %s (%d filas)", f3, len(dealignment))

    # Print dealignment summary
    if not dealignment.empty:
        logger.info("\n--- DEALIGNATION SUMMARY ---")
        for _, row in dealignment.iterrows():
            flag = " *** DEALIGNMENT ***" if row["es_dealignment"] else ""
            logger.info(
                "  %s: %s → %s (%.2f → %.2f, delta=%.4f)%s",
                row["partido"],
                row["leg_first"],
                row["leg_last"],
                row["disciplina_first"],
                row["disciplina_last"],
                row["delta_disciplina"],
                flag,
            )

    logger.info("=== Pipeline completo: %d archivos generados ===", len(files_created))

    return {
        "panel": panel,
        "power": power,
        "dealignment": dealignment,
        "files_created": files_created,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Evolución de Partidos por Legislatura",
    )
    parser.add_argument(
        "--camara",
        choices=["diputados", "senado", "ambas"],
        default="ambas",
        help="Cámara a analizar (default: ambas)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida (default: analysis/analisis-{camara}/output/)",
    )
    args = parser.parse_args()

    if args.camara == "ambas":
        for cam in ["diputados", "senado"]:
            run_evolucion_partidos(cam, args.output_dir)
    else:
        run_evolucion_partidos(args.camara, args.output_dir)
