"""
analysis/efecto_genero.py — Análisis de Efecto Género en el Congreso Mexicano.

Explora si el género de los legisladores influye en su comportamiento
legislativo: disciplina partidista, posicionamiento ideológico (NOMINATE),
y patrones de co-votación.

Nota sobre el "Congreso Congelado":
    Cuando la disciplina partidista es >99% (votación casi unánime por bloque),
    la brecha de género esperada es <2% por construcción estadística.
    Esto no significa que no haya diferencias, sino que el instrumento
    (disciplina de voto) pierde poder discriminativo en regímenes hiperdisciplinados.

Outputs:
    - genero_disciplina.csv: estadísticas de disciplina por género-partido-legislatura
    - genero_brecha.csv: brechas M/F con tests estadísticos
    - genero_nominate.csv: centroides NOMINATE por género-partido-legislatura
    - genero_evolucion.csv: evolución temporal de feminización y disciplina
    - genero_covotacion.csv: agreement rate M/F por legislatura
    - genero_disciplina_heatmap.png: heatmap de brechas
    - genero_nominate_scatter.png: scatter NOMINATE por género
    - genero_timeline.png: timeline feminización vs brecha

Usage:
    python -m analysis.run_efecto_genero --camara diputados
    python -m analysis.run_efecto_genero --camara senado
"""

import contextlib
import logging
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from db.constants import CAMARA_DIPUTADOS_ID, CAMARA_SENADO_ID

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"

CAMARA_TO_ORG_ID = {
    "diputados": CAMARA_DIPUTADOS_ID,  # O08
    "senado": CAMARA_SENADO_ID,  # O09
}

LEGISLATURAS_ORDERED = ["LX", "LXI", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]

MIN_PERSONAS_PER_CELDA = 5


# ---------------------------------------------------------------------------
# Paso 1: Panel de género (agregación por celda)
# ---------------------------------------------------------------------------


def build_gender_panel(camara: str) -> pd.DataFrame:
    """Construye panel agregado por (legislatura, partido, género).

    Desde trayectorias_panel.csv:
    - Agrupa por (legislatura, partido, genero)
    - Calcula: disciplina_mean, disciplina_std, n_personas
    - Centroides NOMINATE por género-partido-legislatura (dim_1_raw, dim_2_raw)
    - Filtra: mínimo 5 personas por celda (M o F)

    Args:
        camara: 'diputados' o 'senado'

    Returns:
        DataFrame con columnas:
        legislatura, partido, genero, n_personas, disciplina_mean,
        disciplina_std, centroid_d1, centroid_d2, std_d1, std_d2
    """
    path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}")

    df = pd.read_csv(path)

    # Excluir géneros nulos
    n_before = len(df)
    df = df.dropna(subset=["genero"])
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        logger.info(
            "Excluidos %d registros sin género de %d totales (%.1f%%)",
            n_dropped,
            n_before,
            100 * n_dropped / n_before,
        )

    # Solo M y F
    df = df[df["genero"].isin(["M", "F"])]

    # Agregar por celda
    agg = (
        df.groupby(["legislatura", "partido", "genero"])
        .agg(
            n_personas=("voter_id", "nunique"),
            disciplina_mean=("disciplina", "mean"),
            disciplina_std=("disciplina", "std"),
            centroid_d1=("dim_1_raw", "mean"),
            centroid_d2=("dim_2_raw", "mean"),
            std_d1=("dim_1_raw", "std"),
            std_d2=("dim_2_raw", "std"),
        )
        .reset_index()
    )

    # Filtrar celdas con menos de MIN_PERSONAS_PER_CELDA
    agg = agg[agg["n_personas"] >= MIN_PERSONAS_PER_CELDA]

    # Ordenar legislaturas
    agg["legislatura"] = pd.Categorical(
        agg["legislatura"],
        categories=LEGISLATURAS_ORDERED,
        ordered=True,
    )
    agg = agg.sort_values(["legislatura", "partido", "genero"]).reset_index(drop=True)

    logger.info(
        "Gender panel: %d celdas, %d partidos, %d legislaturas",
        len(agg),
        agg["partido"].nunique(),
        agg["legislatura"].nunique(),
    )
    return agg


# ---------------------------------------------------------------------------
# Paso 2: Brecha de género con tests estadísticos
# ---------------------------------------------------------------------------


def compute_gender_gap(gender_panel: pd.DataFrame) -> pd.DataFrame:
    """Calcula brechas de género por partido-legislatura con tests estadísticos.

    Para cada partido-legislatura:
    - gap_disciplina = disciplina_F - disciplina_M
    - gap_nominate_d1 = centroid_d1_F - centroid_d1_M
    - t-test (scipy.stats.ttest_ind) sobre disciplina individual M vs F
    - Mann-Whitney U como no-paramétrico

    Los tests estadísticos requieren datos individuales (no agregados),
    así que carga trayectorias_panel para cada grupo.

    Args:
        gender_panel: DataFrame de build_gender_panel()

    Returns:
        DataFrame con columnas:
        legislatura, partido, gap_disciplina, gap_nominate_d1,
        t_stat, p_value, u_stat, p_value_mwu, significant
    """
    # Detectar camara desde el gender_panel (necesitamos saber cuál es)
    # Leemos la primera legislatura para determinar el path
    # Se asume que gender_panel viene de build_gender_panel, pero necesitamos
    # datos individuales para los tests estadísticos.
    # Cargamos datos crudos de la camara que corresponde
    camara = _detect_camara(gender_panel)

    raw_path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
    raw = pd.read_csv(raw_path)
    raw = raw.dropna(subset=["genero"])
    raw = raw[raw["genero"].isin(["M", "F"])]

    results = []
    for (leg, partido), grp in gender_panel.groupby(["legislatura", "partido"]):
        row_f = grp[grp["genero"] == "F"]
        row_m = grp[grp["genero"] == "M"]

        if row_f.empty or row_m.empty:
            continue

        gap_disciplina = float(row_f["disciplina_mean"].iloc[0] - row_m["disciplina_mean"].iloc[0])
        gap_nominate_d1 = float(row_f["centroid_d1"].iloc[0] - row_m["centroid_d1"].iloc[0])

        # Datos individuales para tests estadísticos
        mask = (raw["legislatura"] == str(leg)) & (raw["partido"] == partido)
        indiv = raw[mask]

        disc_f = indiv.loc[indiv["genero"] == "F", "disciplina"].dropna().values
        disc_m = indiv.loc[indiv["genero"] == "M", "disciplina"].dropna().values

        t_stat, p_value = np.nan, np.nan
        u_stat, p_value_mwu = np.nan, np.nan

        if len(disc_f) >= MIN_PERSONAS_PER_CELDA and len(disc_m) >= MIN_PERSONAS_PER_CELDA:
            # t-test (Welch's — unequal variances)
            t_stat, p_value = stats.ttest_ind(disc_f, disc_m, equal_var=False)

            # Mann-Whitney U (no-paramétrico)
            # All values identical → ValueError, silently skip
            with contextlib.suppress(ValueError):
                u_stat, p_value_mwu = stats.mannwhitneyu(disc_f, disc_m, alternative="two-sided")

        significant = bool(p_value < 0.05) if not np.isnan(p_value) else False

        results.append(
            {
                "legislatura": str(leg),
                "partido": partido,
                "gap_disciplina": round(gap_disciplina, 6),
                "gap_nominate_d1": round(gap_nominate_d1, 6),
                "t_stat": round(float(t_stat), 4) if not np.isnan(t_stat) else np.nan,
                "p_value": round(float(p_value), 6) if not np.isnan(p_value) else np.nan,
                "u_stat": round(float(u_stat), 4) if not np.isnan(u_stat) else np.nan,
                "p_value_mwu": round(float(p_value_mwu), 6)
                if not np.isnan(p_value_mwu)
                else np.nan,
                "significant": significant,
            }
        )

    result = pd.DataFrame(results)

    # Ordenar legislaturas
    if not result.empty:
        result["legislatura"] = pd.Categorical(
            result["legislatura"],
            categories=LEGISLATURAS_ORDERED,
            ordered=True,
        )
        result = result.sort_values(["legislatura", "partido"]).reset_index(drop=True)

    logger.info(
        "Gender gap: %d partido-legislatura pares, %d significativos (p<0.05)",
        len(result),
        result["significant"].sum() if not result.empty else 0,
    )
    return result


def _detect_camara(gender_panel: pd.DataFrame) -> str:
    """Detecta la cámara analizada buscando en el path del panel.

    Heurística: intenta cargar trayectorias_panel de ambas cámaras
    y compara legislaturas/partidos.
    """
    for camara in ["diputados", "senado"]:
        path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
        if path.exists():
            return camara
    # Fallback
    return "diputados"


# ---------------------------------------------------------------------------
# Paso 3: Análisis de feminización temporal
# ---------------------------------------------------------------------------


def analyze_feminization(panel: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """Analiza la evolución de la feminización del Congreso.

    Por legislatura:
    - pct_mujeres, n_mujeres, n_hombres
    - gap_disciplina_global: brecha M/F promedio (agregado)
    - disciplina_congreso: disciplina promedio agregada

    Correlaciones (Spearman):
    - pct_mujeres vs disciplina_congreso
    - pct_mujeres vs modularidad (desde evolucion_metricas.csv)

    Args:
        panel: DataFrame de build_gender_panel()
        db_path: ruta a congreso.db

    Returns:
        DataFrame con columnas:
        legislatura, pct_mujeres, n_mujeres, n_hombres,
        gap_disciplina_global, disciplina_congreso,
        spearman_pct_disc_coef, spearman_pct_disc_p,
        spearman_pct_mod_coef, spearman_pct_mod_p
    """
    camara = _detect_camara(panel)

    # Cargar datos crudos para contar individuos
    raw_path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
    raw = pd.read_csv(raw_path)
    raw = raw.dropna(subset=["genero"])
    raw = raw[raw["genero"].isin(["M", "F"])]

    records = []
    for leg in sorted(
        raw["legislatura"].unique(),
        key=lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99,
    ):
        leg_data = raw[raw["legislatura"] == leg]
        n_mujeres = int((leg_data["genero"] == "F").sum())
        n_hombres = int((leg_data["genero"] == "M").sum())
        total = n_mujeres + n_hombres
        pct_mujeres = round(n_mujeres / total, 4) if total > 0 else np.nan

        # Disciplina promedio por género
        disc_f = leg_data.loc[leg_data["genero"] == "F", "disciplina"].mean()
        disc_m = leg_data.loc[leg_data["genero"] == "M", "disciplina"].mean()
        gap_disciplina_global = (
            round(float(disc_f - disc_m), 6) if pd.notna(disc_f) and pd.notna(disc_m) else np.nan
        )
        disciplina_congreso = round(float(leg_data["disciplina"].mean()), 6)

        records.append(
            {
                "legislatura": leg,
                "pct_mujeres": pct_mujeres,
                "n_mujeres": n_mujeres,
                "n_hombres": n_hombres,
                "gap_disciplina_global": gap_disciplina_global,
                "disciplina_congreso": disciplina_congreso,
            }
        )

    result = pd.DataFrame(records)

    if len(result) < 3:
        # Muy pocos puntos para correlación significativa
        result["spearman_pct_disc_coef"] = np.nan
        result["spearman_pct_disc_p"] = np.nan
        result["spearman_pct_mod_coef"] = np.nan
        result["spearman_pct_mod_p"] = np.nan
        logger.warning("Solo %d legislaturas para correlación (mínimo 3)", len(result))
        return result

    # Correlaciones Spearman
    coef_disc, p_disc = stats.spearmanr(result["pct_mujeres"], result["disciplina_congreso"])

    # Cargar modularidad desde evolucion_metricas
    evo_path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/evolucion_metricas.csv"
    if evo_path.exists():
        evo = pd.read_csv(evo_path)
        # Tomar la última ventana por legislatura
        evo = evo.sort_values("ventana").groupby("legislatura").last().reset_index()
        evo = evo[["legislatura", "modularidad"]]

        result_mod = result.merge(evo, on="legislatura", how="left")
        if result_mod["modularidad"].notna().sum() >= 3:
            coef_mod, p_mod = stats.spearmanr(result_mod["pct_mujeres"], result_mod["modularidad"])
        else:
            coef_mod, p_mod = np.nan, np.nan
    else:
        coef_mod, p_mod = np.nan, np.nan
        logger.warning("No se encontró evolucion_metricas.csv para %s", camara)

    # Asignar a todas las filas (son correlaciones globales)
    result["spearman_pct_disc_coef"] = round(float(coef_disc), 6)
    result["spearman_pct_disc_p"] = round(float(p_disc), 6)
    result["spearman_pct_mod_coef"] = (
        round(float(coef_mod), 6) if not np.isnan(coef_mod) else np.nan
    )
    result["spearman_pct_mod_p"] = round(float(p_mod), 6) if not np.isnan(p_mod) else np.nan

    logger.info(
        "Feminización: %s a %s, Spearman(pct_m→disc)=%.3f (p=%.4f), Spearman(pct_m→mod)=%.3f (p=%.4f)",
        result["legislatura"].iloc[0],
        result["legislatura"].iloc[-1],
        coef_disc,
        p_disc,
        coef_mod if not np.isnan(coef_mod) else 0,
        p_mod if not np.isnan(p_mod) else 1,
    )
    return result


# ---------------------------------------------------------------------------
# Paso 4: Co-votación por género (agreement rate)
# ---------------------------------------------------------------------------


def compute_gender_covotacion(camara: str, db_path: Path) -> pd.DataFrame:
    """Calcula agreement rate M/F por legislatura.

    Para cada legislatura:
    - Para cada vote_event, calcular % a_favor para M y F por separado
    - Agreement rate = 1 - |pct_favor_M - pct_favor_F|
    - Promediar agreement rate por legislatura

    Enfoque eficiente: un único query SQL que cuenta votos por género
    y opción por vote_event, luego calcula agreement rate en pandas.

    Args:
        camara: 'diputados' o 'senado'
        db_path: ruta a congreso.db

    Returns:
        DataFrame con columnas:
        legislatura, agreement_rate_mf, pct_favor_m, pct_favor_f, n_events
    """
    org_id = CAMARA_TO_ORG_ID[camara]

    query = """
    SELECT ve.legislatura, v.vote_event_id,
           p.genero,
           v.option,
           COUNT(*) as n_votes
    FROM vote v
    JOIN vote_event ve ON v.vote_event_id = ve.id
    JOIN person p ON v.voter_id = p.id
    WHERE ve.organization_id = ?
      AND ve.legislatura IS NOT NULL
      AND p.genero IN ('M', 'F')
      AND v.option IN ('a_favor', 'en_contra', 'abstencion')
    GROUP BY ve.legislatura, v.vote_event_id, p.genero, v.option
    """

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        df = pd.read_sql_query(query, conn, params=(org_id,))
    finally:
        conn.close()

    if df.empty:
        logger.warning("No se encontraron datos de co-votación para %s", camara)
        return pd.DataFrame(
            columns=["legislatura", "agreement_rate_mf", "pct_favor_m", "pct_favor_f", "n_events"]
        )

    # Pivot: por (legislatura, vote_event_id, genero), calcular total y a_favor
    # Primero calcular total por (legislatura, ve, genero)
    totals = (
        df.groupby(["legislatura", "vote_event_id", "genero"])["n_votes"]
        .sum()
        .reset_index()
        .rename(columns={"n_votes": "total_votes"})
    )

    # Solo a_favor
    favor = df[df["option"] == "a_favor"][
        ["legislatura", "vote_event_id", "genero", "n_votes"]
    ].rename(columns={"n_votes": "favor_votes"})

    # Merge
    merged = totals.merge(favor, on=["legislatura", "vote_event_id", "genero"], how="left")
    merged["favor_votes"] = merged["favor_votes"].fillna(0)
    merged["pct_favor"] = merged["favor_votes"] / merged["total_votes"]

    # Pivot por género para tener M y F en columnas
    pivoted = merged.pivot_table(
        index=["legislatura", "vote_event_id"],
        columns="genero",
        values="pct_favor",
    ).reset_index()

    # Solo eventos donde tenemos ambos géneros
    pivoted = pivoted.dropna(subset=["M", "F"])

    if pivoted.empty:
        logger.warning("No hay eventos con ambos géneros para %s", camara)
        return pd.DataFrame(
            columns=["legislatura", "agreement_rate_mf", "pct_favor_m", "pct_favor_f", "n_events"]
        )

    pivoted["agreement"] = 1.0 - (pivoted["F"] - pivoted["M"]).abs()

    # Agregar por legislatura
    result = (
        pivoted.groupby("legislatura")
        .agg(
            agreement_rate_mf=("agreement", "mean"),
            pct_favor_m=("M", "mean"),
            pct_favor_f=("F", "mean"),
            n_events=("vote_event_id", "count"),
        )
        .reset_index()
    )

    # Redondear
    result["agreement_rate_mf"] = result["agreement_rate_mf"].round(6)
    result["pct_favor_m"] = result["pct_favor_m"].round(6)
    result["pct_favor_f"] = result["pct_favor_f"].round(6)

    # Ordenar legislaturas
    result["legislatura"] = pd.Categorical(
        result["legislatura"],
        categories=LEGISLATURAS_ORDERED,
        ordered=True,
    )
    result = result.sort_values("legislatura").reset_index(drop=True)

    logger.info(
        "Co-votación género: %d legislaturas, agreement promedio=%.4f",
        len(result),
        result["agreement_rate_mf"].mean(),
    )
    return result


# ---------------------------------------------------------------------------
# Paso 5: Visualizaciones
# ---------------------------------------------------------------------------


def plot_gender_disciplina_heatmap(gap: pd.DataFrame, output_dir: Path):
    """Heatmap de gap de disciplina M/F por partido × legislatura.

    Filas: partidos, Columnas: legislaturas
    Valores: gap_disciplina (F - M)
    Colores: divergentes (blue = más disciplinadas mujeres, red = más disciplinados hombres)

    Args:
        gap: DataFrame de compute_gender_gap()
        output_dir: directorio de salida
    """
    if gap.empty:
        logger.warning("No hay datos de brecha para heatmap")
        return

    # Pivot para heatmap
    pivot = gap.pivot_table(
        index="partido",
        columns="legislatura",
        values="gap_disciplina",
    )

    # Ordenar columnas por legislatura
    leg_order = [l for l in LEGISLATURAS_ORDERED if l in pivot.columns]
    pivot = pivot[leg_order]

    fig, ax = plt.subplots(figsize=(12, 8))

    # Determinar rango simétrico
    vmax = max(abs(pivot.min().min()), abs(pivot.max().max()), 0.01)

    im = ax.imshow(
        pivot.values,
        cmap="RdBu",
        aspect="auto",
        vmin=-vmax,
        vmax=vmax,
    )

    # Labels
    ax.set_xticks(range(len(leg_order)))
    ax.set_xticklabels(leg_order, fontsize=10)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=10)

    # Anotar valores
    for i in range(len(pivot.index)):
        for j in range(len(leg_order)):
            val = pivot.iloc[i, j]
            if pd.notna(val):
                color = "white" if abs(val) > vmax * 0.6 else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.3f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color=color,
                )

    plt.colorbar(im, ax=ax, label="Gap disciplina (F - M)")
    ax.set_title("Brecha de disciplina por género (F - M) por partido y legislatura")
    ax.set_xlabel("Legislatura")
    ax.set_ylabel("Partido")

    plt.tight_layout()
    out_path = output_dir / "genero_disciplina_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


def plot_gender_nominate_scatter(panel: pd.DataFrame, output_dir: Path):
    """Scatter NOMINATE con colores por género para la última legislatura.

    Para la última legislatura disponible (LXVI si existe, si no LXV):
    - x = dim_1_raw, y = dim_2_raw
    - color = género (M=blue, F=red)
    - Centroides marcados con X grande

    Usa datos de trayectorias_panel (puntos individuales), no gender_panel.

    Args:
        panel: DataFrame de build_gender_panel()
        output_dir: directorio de salida
    """
    camara = _detect_camara(panel)

    # Cargar datos crudos para puntos individuales
    raw_path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
    raw = pd.read_csv(raw_path)
    raw = raw.dropna(subset=["genero"])
    raw = raw[raw["genero"].isin(["M", "F"])]

    # Seleccionar última legislatura disponible
    available_legs = sorted(
        raw["legislatura"].unique(),
        key=lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99,
    )
    target_leg = available_legs[-1]

    leg_data = raw[raw["legislatura"] == target_leg]

    fig, ax = plt.subplots(figsize=(10, 8))

    # Scatter por género
    for genero, color, marker_label in [
        ("M", "#4477AA", "Masculino"),
        ("F", "#EE6677", "Femenino"),
    ]:
        mask = leg_data["genero"] == genero
        subset = leg_data[mask]
        ax.scatter(
            subset["dim_1_raw"],
            subset["dim_2_raw"],
            c=color,
            s=20,
            alpha=0.4,
            label=f"{marker_label} (n={len(subset)})",
        )

    # Centroides (desde gender_panel para esta legislatura)
    leg_panel = panel[panel["legislatura"].astype(str) == target_leg]
    for genero, color in [("M", "#4477AA"), ("F", "#EE6677")]:
        centroides = leg_panel[leg_panel["genero"] == genero]
        if not centroides.empty:
            for _, row in centroides.iterrows():
                ax.scatter(
                    row["centroid_d1"],
                    row["centroid_d2"],
                    marker="X",
                    s=200,
                    c=color,
                    edgecolors="black",
                    linewidths=1.5,
                    zorder=10,
                )

    ax.set_xlabel("Dimensión 1 (NOMINATE)")
    ax.set_ylabel("Dimensión 2 (NOMINATE)")
    ax.set_title(f"Posicionamiento NOMINATE por género — {camara.capitalize()} — {target_leg}")
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = output_dir / "genero_nominate_scatter.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


def plot_gender_timeline(feminization: pd.DataFrame, output_dir: Path):
    """Doble eje: % mujeres (línea) + gap disciplina (barras) por legislatura.

    Eje izquierdo: % mujeres (línea azul)
    Eje derecho: gap_disciplina_global (barras, color=red si positivo, blue si negativo)

    Args:
        feminization: DataFrame de analyze_feminization()
        output_dir: directorio de salida
    """
    if feminization.empty:
        logger.warning("No hay datos de feminización para timeline")
        return

    fig, ax1 = plt.subplots(figsize=(12, 6))

    x = range(len(feminization))
    legs = feminization["legislatura"].astype(str).values

    # Línea: % mujeres
    (line1,) = ax1.plot(
        x,
        feminization["pct_mujeres"] * 100,
        "b-o",
        linewidth=2,
        markersize=8,
        label="% Mujeres",
    )
    ax1.set_xlabel("Legislatura")
    ax1.set_ylabel("% Mujeres", color="blue")
    ax1.tick_params(axis="y", labelcolor="blue")
    ax1.set_xticks(x)
    ax1.set_xticklabels(legs)

    # Barras: gap disciplina (eje derecho)
    ax2 = ax1.twinx()
    gaps = feminization["gap_disciplina_global"].values * 100  # a porcentaje
    colors = ["#EE6677" if g > 0 else "#4477AA" for g in gaps]
    bars = ax2.bar(x, gaps, alpha=0.6, color=colors, width=0.5, label="Gap disciplina (F-M)")
    ax2.set_ylabel("Gap disciplina (pp)", color="red")
    ax2.tick_params(axis="y", labelcolor="red")

    # Leyenda combinada
    lines = [line1, bars]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", fontsize=10)

    ax1.set_title("Evolución de feminización y brecha de disciplina por género")

    # Grid suave
    ax1.grid(True, alpha=0.2)

    plt.tight_layout()
    out_path = output_dir / "genero_timeline.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


# ---------------------------------------------------------------------------
# Paso 6: Runner principal
# ---------------------------------------------------------------------------


def run_efecto_genero(camara: str, output_dir: str | None = None):
    """Ejecuta todo el pipeline de análisis de efecto género para una cámara.

    Orquesta: panel de género → brechas → feminización → co-votación → plots.

    Args:
        camara: 'diputados' o 'senado'
        output_dir: directorio de salida (default: analysis/analisis-{camara}/output/)

    Returns:
        Dict con DataFrames generados y archivos creados.
    """
    if output_dir is None:
        output_dir = str(PROJECT_ROOT / f"analysis/analisis-{camara}/output")
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("=== Iniciando pipeline de efecto género para %s ===", camara)

    # 1. Construir panel de género
    gender_panel = build_gender_panel(camara)

    # 2. Calcular brechas con tests estadísticos
    gender_gap = compute_gender_gap(gender_panel)

    # 3. Análisis de feminización
    feminization = analyze_feminization(gender_panel, DB_PATH)

    # 4. Co-votación por género
    covotacion = compute_gender_covotacion(camara, DB_PATH)

    # 5. Guardar CSVs
    files_created = []

    # genero_disciplina.csv
    disciplina_csv = gender_panel[
        ["legislatura", "partido", "genero", "n_personas", "disciplina_mean", "disciplina_std"]
    ].copy()
    f1 = out_path / "genero_disciplina.csv"
    disciplina_csv.to_csv(f1, index=False)
    files_created.append(str(f1))
    logger.info("Guardado: %s (%d filas)", f1, len(disciplina_csv))

    # genero_brecha.csv
    f2 = out_path / "genero_brecha.csv"
    gender_gap.to_csv(f2, index=False)
    files_created.append(str(f2))
    logger.info("Guardado: %s (%d filas)", f2, len(gender_gap))

    # genero_nominate.csv
    nominate_csv = gender_panel[
        ["legislatura", "partido", "genero", "centroid_d1", "centroid_d2", "std_d1", "std_d2"]
    ].copy()
    f3 = out_path / "genero_nominate.csv"
    nominate_csv.to_csv(f3, index=False)
    files_created.append(str(f3))
    logger.info("Guardado: %s (%d filas)", f3, len(nominate_csv))

    # genero_evolucion.csv
    f4 = out_path / "genero_evolucion.csv"
    feminization.to_csv(f4, index=False)
    files_created.append(str(f4))
    logger.info("Guardado: %s (%d filas)", f4, len(feminization))

    # genero_covotacion.csv
    f5 = out_path / "genero_covotacion.csv"
    covotacion.to_csv(f5, index=False)
    files_created.append(str(f5))
    logger.info("Guardado: %s (%d filas)", f5, len(covotacion))

    # 6. Generar plots
    plot_gender_disciplina_heatmap(gender_gap, out_path)
    files_created.append(str(out_path / "genero_disciplina_heatmap.png"))

    plot_gender_nominate_scatter(gender_panel, out_path)
    files_created.append(str(out_path / "genero_nominate_scatter.png"))

    plot_gender_timeline(feminization, out_path)
    files_created.append(str(out_path / "genero_timeline.png"))

    logger.info(
        "=== Pipeline completo para %s: %d archivos generados ===",
        camara,
        len(files_created),
    )

    return {
        "gender_panel": gender_panel,
        "gender_gap": gender_gap,
        "feminization": feminization,
        "covotacion": covotacion,
        "files_created": files_created,
    }
