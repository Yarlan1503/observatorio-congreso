"""analysis/efecto_curul_tipo.py — Efecto del tipo de curul en disciplina y posicionamiento.

Analiza si los legisladores plurinominales son más disciplinados que los de mayoría relativa:
1. Panel curul_tipo×partido×legislatura (agregado)
2. Brecha MR vs Pluri (gap + tests estadísticos)
3. Within-person (mismo legislador, diferente tipo de curul)
4. Coverage check por legislatura
5. Visualizaciones (heatmap, scatter, boxplot)

Usage:
    python -m analysis.efecto_curul_tipo --camara diputados
"""

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from db.constants import LEGISLATURAS_ORDERED

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"
CAMARAS = ["diputados", "senado"]
CURUL_TIPOS_ANALISIS = ["mayoria_relativa", "plurinominal"]  # excluir suplentes
MIN_PERSONAS_CELDA = 5  # mínimo para incluir en análisis agregado


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_trayectorias(camara: str) -> pd.DataFrame:
    """Carga trayectorias_panel.csv para la cámara dada."""
    path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/trayectorias_panel.csv"
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}")
    df = pd.read_csv(path)
    logger.info("Cargadas %d filas de trayectorias_panel para %s", len(df), camara)
    return df


def _legislatura_sort_key(leg: str) -> int:
    """Convierte 'LX' -> 60, 'LXI' -> 61, etc. para ordenamiento."""
    roman_map = {
        "LX": 60,
        "LXI": 61,
        "LXII": 62,
        "LXIII": 63,
        "LXIV": 64,
        "LXV": 65,
        "LXVI": 66,
    }
    return roman_map.get(leg, 0)


# ---------------------------------------------------------------------------
# 1. Panel agregado
# ---------------------------------------------------------------------------


def build_curul_panel(camara: str) -> pd.DataFrame:
    """Panel agregado por curul_tipo×partido×legislatura.

    Desde trayectorias_panel.csv:
    1. Cargar CSV
    2. Filtrar: solo filas con curul_tipo NOT NULL y curul_tipo in CURUL_TIPOS_ANALISIS
       (excluir suplentes y NULLs)
    3. Agrupar por (legislatura, partido, curul_tipo)
    4. Calcular: disciplina_mean, disciplina_std, n_personas, n_votos_mean
    5. Centroides NOMINATE: dim_1_aligned mean, dim_2_aligned mean, dim_1 std
    6. Filtrar: mínimo MIN_PERSONAS_CELDA personas por celda

    Returns:
        DataFrame con columnas:
            legislatura, partido, curul_tipo, n_personas, disciplina_mean,
            disciplina_std, centroid_d1, centroid_d2, std_d1, n_votos_mean
    """
    df = _load_trayectorias(camara)

    # Filtrar: solo tipos de análisis (excluir suplentes y NULLs)
    mask = df["curul_tipo"].notna() & df["curul_tipo"].isin(CURUL_TIPOS_ANALISIS)
    df = df.loc[mask].copy()
    logger.info(
        "Después de filtrar curul_tipo: %d filas (%s)",
        len(df),
        ", ".join(CURUL_TIPOS_ANALISIS),
    )

    # Agregar por (legislatura, partido, curul_tipo)
    agg = (
        df.groupby(["legislatura", "partido", "curul_tipo"], observed=True)
        .agg(
            n_personas=("voter_id", "nunique"),
            disciplina_mean=("disciplina", "mean"),
            disciplina_std=("disciplina", "std"),
            centroid_d1=("dim_1_aligned", "mean"),
            centroid_d2=("dim_2_aligned", "mean"),
            std_d1=("dim_1_aligned", "std"),
            n_votos_mean=("n_votos", "mean"),
        )
        .reset_index()
    )

    # Filtrar: mínimo de personas por celda
    before = len(agg)
    agg = agg.loc[agg["n_personas"] >= MIN_PERSONAS_CELDA].copy()
    after = len(agg)
    logger.info(
        "Panel agregado: %d celdas (%d eliminadas por < %d personas)",
        after,
        before - after,
        MIN_PERSONAS_CELDA,
    )

    return agg


# ---------------------------------------------------------------------------
# 2. Gap MR vs Pluri
# ---------------------------------------------------------------------------


def compute_curul_gap(curul_panel: pd.DataFrame) -> pd.DataFrame:
    """Gap MR vs Pluri por partido-legislatura.

    Para cada partido-legislatura que tenga AMBOS tipos:
    1. Pivot: obtener disciplina_mean y centroid_d1 para MR y Pluri
    2. gap_disciplina = disciplina_plurinominal - disciplina_mayoria_relativa
    3. gap_nominate_d1 = centroid_d1_pluri - centroid_d1_mr

    Tests estadísticos (usar scipy.stats):
    - Pooled std: sqrt((std_mr² + std_pluri²) / 2)
    - Cohen's d = gap_disciplina / pooled_std
    - Welch's t-test: scipy.stats.ttest_ind_from_stats(...)
    - significant: p_value < 0.05

    Returns:
        DataFrame con columnas:
            legislatura, partido, n_mr, n_pluri, gap_disciplina, gap_nominate_d1,
            t_stat, p_value, cohens_d, significant
    """
    # Pivot para obtener MR y Pluri lado a lado
    pivot = curul_panel.pivot_table(
        index=["legislatura", "partido"],
        columns="curul_tipo",
        values=[
            "disciplina_mean",
            "disciplina_std",
            "centroid_d1",
            "n_personas",
        ],
    ).reset_index()

    # Aplanar columnas multi-índice
    pivot.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in pivot.columns]

    # Solo filas con AMBOS tipos
    cols_mr = [c for c in pivot.columns if c.endswith("_mayoria_relativa")]
    cols_pl = [c for c in pivot.columns if c.endswith("_plurinominal")]
    has_both = pivot[cols_mr].notna().all(axis=1) & pivot[cols_pl].notna().all(axis=1)
    both = pivot.loc[has_both].copy()

    if both.empty:
        logger.warning("No hay partido-legislatura con ambos tipos de curul")
        return pd.DataFrame(
            columns=[
                "legislatura",
                "partido",
                "n_mr",
                "n_pluri",
                "gap_disciplina",
                "gap_nominate_d1",
                "t_stat",
                "p_value",
                "cohens_d",
                "significant",
            ]
        )

    results = []
    for _, row in both.iterrows():
        disc_mr = row["disciplina_mean_mayoria_relativa"]
        disc_pl = row["disciplina_mean_plurinominal"]
        std_mr = row["disciplina_std_mayoria_relativa"]
        std_pl = row["disciplina_std_plurinominal"]
        n_mr = int(row["n_personas_mayoria_relativa"])
        n_pl = int(row["n_personas_plurinominal"])
        d1_mr = row["centroid_d1_mayoria_relativa"]
        d1_pl = row["centroid_d1_plurinominal"]

        gap_disc = disc_pl - disc_mr
        gap_d1 = d1_pl - d1_mr

        # Pooled std y Cohen's d
        pooled_std = np.sqrt((std_mr**2 + std_pl**2) / 2)
        cohens_d = gap_disc / pooled_std if pooled_std > 0 else np.nan

        # Welch's t-test (dos muestras independientes, varianzas desiguales)
        try:
            t_stat, p_value = stats.ttest_ind_from_stats(
                mean1=disc_mr,
                std1=std_mr,
                nobs1=n_mr,
                mean2=disc_pl,
                std2=std_pl,
                nobs2=n_pl,
                equal_var=False,
            )
        except Exception:
            t_stat, p_value = np.nan, np.nan

        results.append(
            {
                "legislatura": row["legislatura"],
                "partido": row["partido"],
                "n_mr": n_mr,
                "n_pluri": n_pl,
                "gap_disciplina": gap_disc,
                "gap_nominate_d1": gap_d1,
                "t_stat": t_stat,
                "p_value": p_value,
                "cohens_d": cohens_d,
                "significant": p_value < 0.05 if pd.notna(p_value) else False,
            }
        )

    gap_df = pd.DataFrame(results)
    n_sig = gap_df["significant"].sum()
    logger.info(
        "Gap computado: %d partido-legislatura pares, %d significativos (p<0.05)",
        len(gap_df),
        n_sig,
    )
    return gap_df


# ---------------------------------------------------------------------------
# 3. Within-person
# ---------------------------------------------------------------------------


def analyze_within_person(camara: str) -> pd.DataFrame:
    """Within-person: mismo legislador con diferente curul_tipo.

    Desde trayectorias_panel.csv:
    1. Filtrar: solo filas con curul_tipo in CURUL_TIPOS_ANALISIS
    2. Para cada voter_id con 2+ legislaturas:
       - Verificar si curul_tipo cambió entre legislaturas
       - Si tiene tanto mayoria_relativa como plurinominal en diferentes legislaturas:
         * disciplina_mr: disciplina promedio cuando era mayoria_relativa
         * disciplina_pluri: disciplina promedio cuando era plurinominal
         * delta_disciplina = disciplina_pluri - disciplina_mr
         * delta_nominate_d1 = mean(dim_1_aligned cuando pluri) - mean(dim_1_aligned cuando mr)
    3. Tomar el partido más frecuente como "partido" del legislador

    Returns:
        DataFrame con columnas:
            voter_id, nombre, partido, n_legs_mr, n_legs_pluri,
            disciplina_mr, disciplina_pluri, delta_disciplina, delta_nominate_d1
    """
    df = _load_trayectorias(camara)

    # Filtrar solo tipos de análisis
    mask = df["curul_tipo"].notna() & df["curul_tipo"].isin(CURUL_TIPOS_ANALISIS)
    df = df.loc[mask].copy()

    results = []
    for voter_id, group in df.groupby("voter_id"):
        tipos = group["curul_tipo"].unique()

        # Necesita tener AMBOS tipos (MR y Pluri)
        if not set(CURUL_TIPOS_ANALISIS).issubset(set(tipos)):
            continue

        mr_rows = group.loc[group["curul_tipo"] == "mayoria_relativa"]
        pl_rows = group.loc[group["curul_tipo"] == "plurinominal"]

        disciplina_mr = mr_rows["disciplina"].mean()
        disciplina_pl = pl_rows["disciplina"].mean()
        d1_mr = mr_rows["dim_1_aligned"].mean()
        d1_pl = pl_rows["dim_1_aligned"].mean()

        # Partido más frecuente
        partido = group["partido"].mode().iloc[0] if len(group["partido"].mode()) > 0 else ""

        # Nombre (tomar el primero)
        nombre = group["nombre"].iloc[0]

        results.append(
            {
                "voter_id": voter_id,
                "nombre": nombre,
                "partido": partido,
                "n_legs_mr": len(mr_rows),
                "n_legs_pluri": len(pl_rows),
                "disciplina_mr": disciplina_mr,
                "disciplina_pluri": disciplina_pl,
                "delta_disciplina": disciplina_pl - disciplina_mr,
                "delta_nominate_d1": d1_pl - d1_mr,
            }
        )

    within_df = pd.DataFrame(
        results,
        columns=[
            "voter_id",
            "nombre",
            "partido",
            "n_legs_mr",
            "n_legs_pluri",
            "disciplina_mr",
            "disciplina_pluri",
            "delta_disciplina",
            "delta_nominate_d1",
        ],
    )
    logger.info(
        "Within-person: %d legisladores con ambos tipos de curul",
        len(within_df),
    )
    return within_df


# ---------------------------------------------------------------------------
# 4. Coverage
# ---------------------------------------------------------------------------


def check_curul_coverage(camara: str) -> pd.DataFrame:
    """Coverage de curul_tipo por legislatura.

    Desde trayectorias_panel.csv:
    1. Para cada legislatura:
       - total: total de personas (voter_id únicos)
       - con_tipo: personas con curul_tipo NOT NULL
       - pct: con_tipo / total * 100
       - n_mr: personas con mayoria_relativa
       - n_pluri: personas con plurinominal
       - n_suplente: personas con suplente

    Returns:
        DataFrame con columnas:
            legislatura, total, con_tipo, pct, n_mr, n_pluri, n_suplente
    """
    df = _load_trayectorias(camara)

    records = []
    for leg, group in df.groupby("legislatura"):
        total = group["voter_id"].nunique()
        con_tipo = group.loc[group["curul_tipo"].notna(), "voter_id"].nunique()
        n_mr = group.loc[group["curul_tipo"] == "mayoria_relativa", "voter_id"].nunique()
        n_pl = group.loc[group["curul_tipo"] == "plurinominal", "voter_id"].nunique()
        n_sup = group.loc[group["curul_tipo"] == "suplente", "voter_id"].nunique()
        pct = con_tipo / total * 100 if total > 0 else 0.0

        records.append(
            {
                "legislatura": leg,
                "total": total,
                "con_tipo": con_tipo,
                "pct": round(pct, 1),
                "n_mr": n_mr,
                "n_pluri": n_pl,
                "n_suplente": n_sup,
            }
        )

    cov_df = pd.DataFrame(records)
    # Ordenar por legislatura
    cov_df["_sort"] = cov_df["legislatura"].map(_legislatura_sort_key)
    cov_df = cov_df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    avg_cov = cov_df["pct"].mean()
    logger.info("Coverage promedio: %.1f%%", avg_cov)
    return cov_df


# ---------------------------------------------------------------------------
# 5. Visualizaciones
# ---------------------------------------------------------------------------


def plot_curul_heatmap(gap_df: pd.DataFrame, output_dir: Path):
    """Heatmap: gap disciplina (Pluri - MR) por partido×legislatura.

    - Filas: partidos (ordenados por frecuencia)
    - Columnas: legislaturas (ordenadas LX-LXVI)
    - Valores: gap_disciplina (rojo = pluri más disciplinado, azul = mr más disciplinado)
    - Anotaciones: valor del gap
    - Solo celdas con datos
    - Guardar: output_dir / "curul_tipo_heatmap.png"
    """
    if gap_df.empty:
        logger.warning("Gap vacío, saltando heatmap")
        return

    # Pivot a matriz partido × legislatura
    heatmap_data = gap_df.pivot(
        index="partido",
        columns="legislatura",
        values="gap_disciplina",
    )

    # Ordenar
    leg_order = [l for l in LEGISLATURAS_ORDERED if l in heatmap_data.columns]
    heatmap_data = heatmap_data[leg_order]

    # Ordenar partidos por frecuencia (número de legislaturas con datos)
    partido_freq = heatmap_data.notna().sum(axis=1).sort_values(ascending=False)
    heatmap_data = heatmap_data.loc[partido_freq.index]

    fig, ax = plt.subplots(figsize=(12, max(6, len(heatmap_data) * 0.5 + 2)))

    # Mask para NaN
    mask = heatmap_data.isna()

    # Determinar vmax/vmin centrado en 0
    abs_max = max(abs(heatmap_data.min().min()), abs(heatmap_data.max().max()))
    if pd.isna(abs_max) or abs_max == 0:
        abs_max = 0.05

    im = ax.imshow(
        heatmap_data.values,
        cmap="RdBu_r",
        aspect="auto",
        vmin=-abs_max,
        vmax=abs_max,
    )

    # Anotaciones
    for i in range(heatmap_data.shape[0]):
        for j in range(heatmap_data.shape[1]):
            if not mask.iloc[i, j]:
                val = heatmap_data.iloc[i, j]
                color = "white" if abs(val) > abs_max * 0.6 else "black"
                ax.text(
                    j,
                    i,
                    f"{val:+.3f}",
                    ha="center",
                    va="center",
                    color=color,
                    fontsize=8,
                )

    ax.set_xticks(range(len(leg_order)))
    ax.set_xticklabels(leg_order, fontsize=10)
    ax.set_yticks(range(len(heatmap_data)))
    ax.set_yticklabels(heatmap_data.index, fontsize=9)

    ax.set_xlabel("Legislatura")
    ax.set_ylabel("Partido")
    ax.set_title(
        "Gap Disciplina: Plurinominal − Mayoría Relativa\n(rojo = Pluri más disciplinado, azul = MR más disciplinado)"
    )

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Gap disciplina (pp)")

    plt.tight_layout()
    path = output_dir / "curul_tipo_heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Guardado: %s", path)


def plot_curul_nominate_scatter(panel: pd.DataFrame, output_dir: Path):
    """Scatter NOMINATE: centroides por partido-coloreado por tipo de curul.

    Espacio dim_1 × dim_2. Cada punto es un (partido, legislatura, curul_tipo).
    Color: curul_tipo. Conectados por línea faint si mismo partido-legislatura.
    """
    if panel.empty:
        logger.warning("Panel vacío, saltando scatter")
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    color_map = {
        "mayoria_relativa": "#d62728",  # rojo
        "plurinominal": "#1f77b4",  # azul
    }

    # Conectar puntos del mismo partido-legislatura
    for (partido, leg), group in panel.groupby(["partido", "legislatura"]):
        if len(group) == 2:
            rows = group.sort_values("curul_tipo")
            ax.plot(
                rows["centroid_d1"].values,
                rows["centroid_d2"].values,
                color="gray",
                alpha=0.25,
                linewidth=0.8,
                zorder=1,
            )

    # Scatter por tipo
    for tipo in CURUL_TIPOS_ANALISIS:
        subset = panel.loc[panel["curul_tipo"] == tipo]
        if subset.empty:
            continue
        ax.scatter(
            subset["centroid_d1"],
            subset["centroid_d2"],
            c=color_map.get(tipo, "gray"),
            s=subset["n_personas"] * 3,
            alpha=0.7,
            label=f"{tipo.replace('_', ' ').title()}",
            edgecolors="white",
            linewidth=0.5,
            zorder=2,
        )

    ax.axhline(0, color="gray", linewidth=0.5, alpha=0.5)
    ax.axvline(0, color="gray", linewidth=0.5, alpha=0.5)

    ax.set_xlabel("Dimensión 1 NOMINATE (centroid)")
    ax.set_ylabel("Dimensión 2 NOMINATE (centroid)")
    ax.set_title("Centroides NOMINATE por Tipo de Curul\n(Tamaño ∝ n_personas)")
    ax.legend(loc="best")

    plt.tight_layout()
    path = output_dir / "curul_tipo_scatter.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Guardado: %s", path)


def plot_within_person_boxplot(within_df: pd.DataFrame, output_dir: Path):
    """Boxplot: disciplina same person MR vs Pluri (paired).

    - Dos cajas: disciplina_mr y disciplina_pluri del mismo legislador
    - Conectar con líneas individuales (paired design)
    - Mostrar n de legislators
    - Annotate mean delta y p-value (Wilcoxon signed-rank test)
    - Si n < 20: agregar nota "Descriptivo — n < 20"
    - Guardar: output_dir / "curul_tipo_within_boxplot.png"
    """
    if within_df.empty:
        logger.warning("Within-person vacío, saltando boxplot")
        return

    n = len(within_df)
    mean_delta = within_df["delta_disciplina"].mean()

    # Wilcoxon signed-rank test (no paramétrico, paired)
    if n >= 3:
        deltas = within_df["delta_disciplina"].dropna()
        if deltas.std() > 0:
            stat, p_val = stats.wilcoxon(deltas)
        else:
            stat, p_val = np.nan, np.nan
    else:
        stat, p_val = np.nan, np.nan

    fig, ax = plt.subplots(figsize=(8, 6))

    # Líneas individuales (paired design)
    for _, row in within_df.iterrows():
        ax.plot(
            [0, 1],
            [row["disciplina_mr"], row["disciplina_pluri"]],
            color="gray",
            alpha=0.3,
            linewidth=0.7,
        )

    # Boxplots
    bp = ax.boxplot(
        [within_df["disciplina_mr"].values, within_df["disciplina_pluri"].values],
        positions=[0, 1],
        widths=0.4,
        patch_artist=True,
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "black", "markersize": 6},
    )

    bp["boxes"][0].set_facecolor("#d6272880")
    bp["boxes"][0].set_label("Mayoría Relativa")
    bp["boxes"][1].set_facecolor("#1f77b480")
    bp["boxes"][1].set_label("Plurinominal")

    # Puntos individuales con jitter
    jitter = np.random.default_rng(42).uniform(-0.08, 0.08, n)
    ax.scatter(
        jitter - 0.0,
        within_df["disciplina_mr"],
        color="#d62728",
        alpha=0.5,
        s=20,
        zorder=3,
    )
    ax.scatter(
        jitter + 1.0,
        within_df["disciplina_pluri"],
        color="#1f77b4",
        alpha=0.5,
        s=20,
        zorder=3,
    )

    # Labels
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Mayoría\nRelativa", "Plurinominal"])
    ax.set_ylabel("Disciplina")
    ax.set_title(f"Disciplina Within-Person: MR vs Pluri (n={n})")
    ax.legend(loc="lower left")

    # Annotation
    p_text = f"p={p_val:.4f}" if pd.notna(p_val) else "p=N/A"
    note = ""
    if n < 20:
        note = "\n⚠ Descriptivo — n < 20"

    ax.annotate(
        f"Δ medio = {mean_delta:+.4f}\n{p_text}{note}",
        xy=(0.98, 0.02),
        xycoords="axes fraction",
        ha="right",
        va="bottom",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.7),
    )

    plt.tight_layout()
    path = output_dir / "curul_tipo_within_boxplot.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Guardado: %s", path)


# ---------------------------------------------------------------------------
# 6. Runner principal
# ---------------------------------------------------------------------------


def run_efecto_curul_tipo(camara: str, output_dir: str | None = None):
    """Runner principal.

    1. Determinar output_dir: output_dir o default analysis/analisis-{camara}/output/
    2. Ejecutar las 4 funciones analíticas
    3. Guardar CSVs:
       - curul_tipo_disciplina.csv (panel)
       - curul_tipo_gap.csv (brecha)
       - curul_tipo_within.csv (within-person)
       - curul_tipo_coverage.csv (coverage)
    4. Generar 3 visualizaciones
    5. Print resumen estadístico:
       - Coverage promedio
       - Gap promedio (significatividad)
       - N within-person switches
       - Hallazgos clave
    """
    if output_dir is None:
        output_dir = str(PROJECT_ROOT / f"analysis/analisis-{camara}/output")
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("=== Efecto Curul Tipo — %s ===", camara.upper())

    # 1. Panel agregado
    panel = build_curul_panel(camara)
    f_panel = out_path / "curul_tipo_disciplina.csv"
    panel.to_csv(f_panel, index=False)
    logger.info("Guardado: %s (%d filas)", f_panel, len(panel))

    # 2. Gap MR vs Pluri
    gap_df = compute_curul_gap(panel)
    f_gap = out_path / "curul_tipo_gap.csv"
    gap_df.to_csv(f_gap, index=False)
    logger.info("Guardado: %s (%d filas)", f_gap, len(gap_df))

    # 3. Within-person
    within_df = analyze_within_person(camara)
    f_within = out_path / "curul_tipo_within.csv"
    within_df.to_csv(f_within, index=False)
    logger.info("Guardado: %s (%d filas)", f_within, len(within_df))

    # 4. Coverage
    cov_df = check_curul_coverage(camara)
    f_cov = out_path / "curul_tipo_coverage.csv"
    cov_df.to_csv(f_cov, index=False)
    logger.info("Guardado: %s (%d filas)", f_cov, len(cov_df))

    # 5. Visualizaciones
    plot_curul_heatmap(gap_df, out_path)
    plot_curul_nominate_scatter(panel, out_path)
    plot_within_person_boxplot(within_df, out_path)

    # 6. Resumen estadístico
    logger.info("\n" + "=" * 50)
    logger.info("RESUMEN — %s", camara.upper())
    logger.info("=" * 50)

    # Coverage
    avg_cov = cov_df["pct"].mean()
    logger.info("Coverage promedio: %.1f%%", avg_cov)

    # Gap
    if not gap_df.empty:
        avg_gap = gap_df["gap_disciplina"].mean()
        n_sig = gap_df["significant"].sum()
        n_total = len(gap_df)
        logger.info(
            "Gap disciplina promedio (Pluri - MR): %.4f (%d/%d significativos)",
            avg_gap,
            n_sig,
            n_total,
        )

    # Within-person
    n_within = len(within_df)
    logger.info("Legisladores con ambos tipos (within-person): %d", n_within)

    if n_within > 0:
        mean_delta = within_df["delta_disciplina"].mean()
        logger.info("Delta within-person promedio: %.4f", mean_delta)

        if n_within < 20:
            logger.info("⚠ n < 20: resultados descriptivos, no inferenciales")

    # Hallazgos clave
    logger.info("\n--- Hallazgos clave ---")
    if not gap_df.empty:
        direction = (
            "plurinominales MÁS disciplinados"
            if avg_gap > 0
            else "mayoría relativa MÁS disciplinada"
        )
        logger.info(
            "Dirección del efecto: %s (gap promedio: %.4f pp)",
            direction,
            abs(avg_gap),
        )

    if n_within > 0 and n_within >= 3:
        direction_w = "pluri" if within_df["delta_disciplina"].mean() > 0 else "MR"
        n_pos = (within_df["delta_disciplina"] > 0).sum()
        n_neg = (within_df["delta_disciplina"] < 0).sum()
        logger.info(
            "Within-person: %d van ↑ al cambiar a Pluri, %d van ↓ (%s favorecido)",
            n_pos,
            n_neg,
            direction_w,
        )

    logger.info("=== Fin efecto curul tipo — %s ===\n", camara.upper())
