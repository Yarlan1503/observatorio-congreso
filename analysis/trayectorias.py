"""
analysis/trayectorias.py — Análisis de Trayectorias Individuales.

Produce:
1. Panel persona × legislatura con NOMINATE alineado + disciplina individual
2. Procrustes alignment entre pares consecutivos de legislaturas
3. Métricas de trayectoria individual (estabilidad, movimiento ideológico)
4. Detección de switchers (cambio de partido)
5. Visualizaciones

Usage:
    python -m analysis.run_trayectorias --camara diputados
    python -m analysis.run_trayectorias --camara senado
"""

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.linalg import svd

from analysis.db import get_connection
from db.constants import (
    _ORG_ID_TO_NAME,
    CAMARA_DIPUTADOS_ID,
    CAMARA_SENADO_ID,
    LEGISLATURAS_ORDERED,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "congreso.db"

CAMARA_TO_ORG_ID = {
    "diputados": CAMARA_DIPUTADOS_ID,  # O08
    "senado": CAMARA_SENADO_ID,  # O09
}


# ---------------------------------------------------------------------------
# Paso 1: Carga y merge
# ---------------------------------------------------------------------------


def load_nominate_coords(camara: str) -> pd.DataFrame:
    """Carga coordenadas_nominate.csv para la cámara dada.

    Args:
        camara: 'diputados' o 'senado'

    Returns:
        DataFrame con: voter_id, nombre, partido, dim_1, dim_2, legislatura, camara
    """
    path = PROJECT_ROOT / f"analysis/analisis-{camara}/output/coordenadas_nominate.csv"
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}")

    df = pd.read_csv(path)
    df["camara"] = camara
    logger.info(
        "Cargadas %d coordenadas NOMINATE para %s (%d voters únicos)",
        len(df),
        camara,
        df["voter_id"].nunique(),
    )
    return df


def compute_individual_discipline(db_path: Path, camara: str) -> pd.DataFrame:
    """Calcula disciplina individual por persona-legislatura.

    Disciplina = % de votos donde el legislador votó con la mayoría de su partido.

    Returns:
        DataFrame con: voter_id, legislatura, partido_id, n_votos, disciplina
    """
    org_id = CAMARA_TO_ORG_ID[camara]

    query = """
    WITH mayoritaria AS (
        SELECT vote_event_id, "group", option,
            ROW_NUMBER() OVER (
                PARTITION BY vote_event_id, "group"
                ORDER BY COUNT(*) DESC
            ) as rn
        FROM vote
        GROUP BY vote_event_id, "group", option
    )
    SELECT v.voter_id, ve.legislatura, v."group" as partido_id,
        COUNT(*) as n_votos,
        ROUND(1.0 * SUM(CASE WHEN v.option = m.option THEN 1 ELSE 0 END) / COUNT(*), 4) as disciplina
    FROM vote v
    JOIN vote_event ve ON v.vote_event_id = ve.id
    JOIN mayoritaria m
        ON v.vote_event_id = m.vote_event_id
        AND v."group" = m."group"
        AND m.rn = 1
    WHERE v."group" IS NOT NULL
      AND ve.legislatura IS NOT NULL
      AND ve.organization_id = ?
    GROUP BY v.voter_id, ve.legislatura, v."group"
    HAVING n_votos >= 10
    """

    conn = get_connection(db_path)
    try:
        df = pd.read_sql_query(query, conn, params=(org_id,))
    finally:
        conn.close()

    logger.info(
        "Calculada disciplina para %d persona-legislaturas en %s",
        len(df),
        camara,
    )
    return df


def build_panel(coords: pd.DataFrame, discipline: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """Merge NOMINATE + disciplina + datos persona.

    Returns DataFrame with columns:
        voter_id, nombre, genero, curul_tipo, legislatura, partido, partido_id,
        dim_1, dim_2, disciplina, n_votos, camara
    """
    # Keep only the primary party per voter-legislatura (most votes)
    discipline = discipline.sort_values("n_votos", ascending=False).drop_duplicates(
        subset=["voter_id", "legislatura"], keep="first"
    )

    # Merge coords left join discipline
    panel = coords.merge(
        discipline,
        on=["voter_id", "legislatura"],
        how="left",
    )

    # Query person table for genero, curul_tipo
    conn = get_connection(db_path)
    try:
        persons = pd.read_sql_query(
            "SELECT id as voter_id, nombre, genero, curul_tipo FROM person",
            conn,
        )
    finally:
        conn.close()

    # Drop duplicate nombre from person table (we keep coords' nombre)
    persons = persons.drop(columns=["nombre"])

    panel = panel.merge(persons, on="voter_id", how="left")

    # Map partido_id → partido name for discipline column, keep NOMINATE partido as primary
    # coords' 'partido' column survives the merge since discipline doesn't have it.
    panel["partido_disciplina"] = panel["partido_id"].map(_ORG_ID_TO_NAME)

    # Ensure column order
    cols = [
        "voter_id",
        "nombre",
        "genero",
        "curul_tipo",
        "legislatura",
        "partido",
        "partido_disciplina",
        "partido_id",
        "dim_1",
        "dim_2",
        "disciplina",
        "n_votos",
        "camara",
    ]
    panel = panel[[c for c in cols if c in panel.columns]]

    logger.info(
        "Panel construido: %d filas, %d voters únicos", len(panel), panel["voter_id"].nunique()
    )
    return panel


# ---------------------------------------------------------------------------
# Paso 2: Procrustes Alignment
# ---------------------------------------------------------------------------


def align_legislature_pair(coords_ref: np.ndarray, coords_target: np.ndarray) -> dict:
    """Alinea coords_target contra coords_ref usando Procrustes manual.

    Extrae los parámetros de transformación (rotación, escala, traslación)
    para poder aplicarlos a TODOS los legisladores del target, no solo el overlap.

    Returns dict with:
        rotation_matrix, scale_factor,
        translation_ref (mean of ref), translation_target (mean of target),
        norm_ref, norm_target, disparity, correlation
    """
    # 1. Center
    mean_ref = coords_ref.mean(axis=0)
    mean_target = coords_target.mean(axis=0)

    ref_centered = coords_ref - mean_ref
    target_centered = coords_target - mean_target

    # 2. Scale to unit Frobenius norm
    norm_ref = np.linalg.norm(ref_centered, "fro")
    norm_target = np.linalg.norm(target_centered, "fro")

    if norm_ref < 1e-12 or norm_target < 1e-12:
        return {
            "rotation_matrix": np.eye(2),
            "scale_factor": 1.0,
            "translation_ref": mean_ref,
            "translation_target": mean_target,
            "norm_ref": norm_ref,
            "norm_target": norm_target,
            "disparity": 0.0,
            "correlation": 1.0,
        }

    ref_scaled = ref_centered / norm_ref
    target_scaled = target_centered / norm_target

    # 3. Optimal rotation via SVD
    H = ref_scaled.T @ target_scaled
    U, _S, Vt = svd(H)

    # Ensure proper rotation (det = +1)
    d = np.linalg.det(Vt.T @ U.T)
    sign_matrix = np.diag([1.0, np.sign(d)])
    rotation_matrix = Vt.T @ sign_matrix @ U.T

    # 4. Scale factor
    scale_factor = norm_ref / norm_target

    # 5. Compute disparity on the overlap
    target_transformed = scale_factor * (target_centered @ rotation_matrix.T)
    disparity = float(np.sum((ref_centered - target_transformed) ** 2))

    # Correlation
    ref_flat = ref_centered.flatten()
    tgt_flat = target_transformed.flatten()
    correlation = float(np.corrcoef(ref_flat, tgt_flat)[0, 1])

    return {
        "rotation_matrix": rotation_matrix,
        "scale_factor": scale_factor,
        "translation_ref": mean_ref,
        "translation_target": mean_target,
        "norm_ref": norm_ref,
        "norm_target": norm_target,
        "disparity": disparity,
        "correlation": correlation,
    }


def apply_transform(coords: np.ndarray, params: dict, mean_ref_prev: np.ndarray) -> np.ndarray:
    """Aplica transformación Procrustes a un array de coordenadas.

    Steps:
    1. Center coords (subtract mean_target)
    2. Apply rotation: centered @ R.T
    3. Apply scale: * scale_factor
    4. Add mean_ref_prev (the reference mean from previous alignment)

    Returns transformed coords.
    """
    centered = coords - params["translation_target"]
    rotated = centered @ params["rotation_matrix"].T
    scaled = rotated * params["scale_factor"]
    transformed = scaled + mean_ref_prev
    return transformed


def compute_all_alignments(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Alinea todas las legislaturas consecutivas a un espacio común.

    Strategy:
    1. For each target legislatura (LXI through LXVI):
       a. Find overlap with the last ALIGNED legislatura that has enough overlap
       b. Compute Procrustes using overlap as correspondence
       c. Apply rotation/scale/translation to ALL target coords
    2. This chains naturally since we use the already-aligned previous leg

    We deduplicate to one row per voter_id × legislatura (first occurrence)
    to handle cases where the panel has multiple rows (different partido_id).

    Returns:
        alignments: DataFrame with columns: leg_pair, overlap_n, disparity, correlation
        panel_aligned: copy of panel with dim_1_raw, dim_2_raw, dim_1_aligned, dim_2_aligned
    """
    legs_sorted = sorted(
        panel["legislatura"].unique(),
        key=lambda x: LEGISLATURAS_ORDERED.index(x) if x in LEGISLATURAS_ORDERED else 99,
    )

    panel_aligned = panel.copy()
    panel_aligned["dim_1_raw"] = panel_aligned["dim_1"].copy()
    panel_aligned["dim_2_raw"] = panel_aligned["dim_2"].copy()
    panel_aligned["dim_1_aligned"] = panel_aligned["dim_1"].copy()
    panel_aligned["dim_2_aligned"] = panel_aligned["dim_2"].copy()

    # Build a deduplicated lookup: one row per (voter_id, legislatura) for alignment
    dedup = panel_aligned.drop_duplicates(subset=["voter_id", "legislatura"], keep="first")

    alignment_records = []

    # Reference legislatura (first one)
    ref_leg = legs_sorted[0]
    logger.info("Legislatura de referencia: %s", ref_leg)

    # Center the reference legislatura
    ref_mask = dedup["legislatura"] == ref_leg
    ref_coords = dedup.loc[ref_mask, ["dim_1_aligned", "dim_2_aligned"]].values
    cumulative_ref_mean = ref_coords.mean(axis=0)

    # Apply centering to ALL rows in panel_aligned (including dupes)
    all_ref_mask = panel_aligned["legislatura"] == ref_leg
    all_ref_coords = panel_aligned.loc[all_ref_mask, ["dim_1_aligned", "dim_2_aligned"]].values
    panel_aligned.loc[all_ref_mask, "dim_1_aligned"] = all_ref_coords[:, 0] - cumulative_ref_mean[0]
    panel_aligned.loc[all_ref_mask, "dim_2_aligned"] = all_ref_coords[:, 1] - cumulative_ref_mean[1]

    # Track the last legislatura that was successfully aligned (for chaining)
    last_aligned_leg = ref_leg

    for i in range(1, len(legs_sorted)):
        curr_leg = legs_sorted[i]

        # Use the last successfully aligned legislatura as reference
        prev_leg = last_aligned_leg

        # Get already-aligned coords for previous legislatura (deduplicated)
        prev_dedup = dedup[dedup["legislatura"] == prev_leg][
            ["voter_id", "dim_1_aligned", "dim_2_aligned"]
        ]
        # Re-read from panel_aligned (which has the aligned values)
        prev_mask_panel = panel_aligned["legislatura"] == prev_leg
        prev_aligned = panel_aligned.loc[
            prev_mask_panel, ["voter_id", "dim_1_aligned", "dim_2_aligned"]
        ].drop_duplicates(subset=["voter_id"], keep="first")

        curr_dedup = dedup[dedup["legislatura"] == curr_leg][["voter_id", "dim_1", "dim_2"]]

        # Find overlap
        overlap_ids = sorted(set(prev_aligned["voter_id"]) & set(curr_dedup["voter_id"]))
        overlap_n = len(overlap_ids)

        if overlap_n < 20:
            logger.warning(
                "Overlap insuficiente entre %s y %s: %d. Sin alignment directo.",
                prev_leg,
                curr_leg,
                overlap_n,
            )
            # Just center current coords and add cumulative mean
            curr_mask = panel_aligned["legislatura"] == curr_leg
            curr_coords = panel_aligned.loc[curr_mask, ["dim_1", "dim_2"]].values
            curr_mean = curr_coords.mean(axis=0)
            panel_aligned.loc[curr_mask, "dim_1_aligned"] = (
                curr_coords[:, 0] - curr_mean[0] + cumulative_ref_mean[0]
            )
            panel_aligned.loc[curr_mask, "dim_2_aligned"] = (
                curr_coords[:, 1] - curr_mean[1] + cumulative_ref_mean[1]
            )
            # Update dedup to reflect aligned values
            dedup = panel_aligned.drop_duplicates(subset=["voter_id", "legislatura"], keep="first")
            alignment_records.append(
                {
                    "leg_pair": f"{prev_leg}->{curr_leg}",
                    "overlap_n": overlap_n,
                    "disparity": np.nan,
                    "correlation": np.nan,
                }
            )
            # Don't update last_aligned_leg — next legislatura will try against same ref
            continue

        # Get overlap coords — aligned by voter_id (both sorted the same way)
        prev_overlap = (
            prev_aligned[prev_aligned["voter_id"].isin(overlap_ids)]
            .set_index("voter_id")
            .loc[overlap_ids]
        )
        curr_overlap = (
            curr_dedup[curr_dedup["voter_id"].isin(overlap_ids)]
            .set_index("voter_id")
            .loc[overlap_ids]
        )

        ref_coords_overlap = prev_overlap[["dim_1_aligned", "dim_2_aligned"]].values
        target_coords_overlap = curr_overlap[["dim_1", "dim_2"]].values

        # Compute Procrustes
        params = align_legislature_pair(ref_coords_overlap, target_coords_overlap)

        logger.info(
            "Alignment %s -> %s: overlap=%d, disparity=%.4f, corr=%.4f",
            prev_leg,
            curr_leg,
            overlap_n,
            params["disparity"],
            params["correlation"],
        )

        # Apply transform to ALL current legislators (including dupes)
        curr_mask = panel_aligned["legislatura"] == curr_leg
        curr_all_coords = panel_aligned.loc[curr_mask, ["dim_1", "dim_2"]].values
        transformed = apply_transform(curr_all_coords, params, cumulative_ref_mean)

        panel_aligned.loc[curr_mask, "dim_1_aligned"] = transformed[:, 0]
        panel_aligned.loc[curr_mask, "dim_2_aligned"] = transformed[:, 1]

        # Update dedup
        dedup = panel_aligned.drop_duplicates(subset=["voter_id", "legislatura"], keep="first")

        last_aligned_leg = curr_leg

        alignment_records.append(
            {
                "leg_pair": f"{prev_leg}->{curr_leg}",
                "overlap_n": overlap_n,
                "disparity": round(params["disparity"], 6),
                "correlation": round(params["correlation"], 6),
            }
        )

    alignments_df = pd.DataFrame(alignment_records)
    logger.info("Alignment completo: %d pares", len(alignments_df))
    return alignments_df, panel_aligned


# ---------------------------------------------------------------------------
# Paso 3: Métricas de trayectoria
# ---------------------------------------------------------------------------


def compute_trajectory_metrics(panel_aligned: pd.DataFrame) -> pd.DataFrame:
    """Para cada legislador con 2+ legislaturas en el panel.

    Returns: DataFrame with one row per legislador with 2+ legislaturas.
    """
    # Count legs per voter
    leg_counts = panel_aligned.groupby("voter_id")["legislatura"].nunique()
    multi_leg = leg_counts[leg_counts >= 2].index

    if len(multi_leg) == 0:
        logger.warning("No se encontraron legisladores con 2+ legislaturas")
        return pd.DataFrame()

    records = []
    for voter_id in multi_leg:
        voter_data = panel_aligned[panel_aligned["voter_id"] == voter_id].copy()
        voter_data = voter_data.sort_values(
            "legislatura",
            key=lambda x: x.map(
                lambda v: LEGISLATURAS_ORDERED.index(v) if v in LEGISLATURAS_ORDERED else 99
            ),
        )

        n_legs = voter_data["legislatura"].nunique()
        legislaturas = ";".join(voter_data["legislatura"].unique())
        partidos = ";".join(voter_data["partido"].dropna().unique())

        # Estabilidad: std dev of dim_1_aligned
        estabilidad_d1 = voter_data["dim_1_aligned"].std()

        # Movimiento ideológico: euclidean distance between first and last
        first_row = voter_data.iloc[0]
        last_row = voter_data.iloc[-1]
        movimiento = np.sqrt(
            (first_row["dim_1_aligned"] - last_row["dim_1_aligned"]) ** 2
            + (first_row["dim_2_aligned"] - last_row["dim_2_aligned"]) ** 2
        )

        # Delta disciplina: mean of absolute changes between consecutive legs
        if "disciplina" in voter_data.columns and voter_data["disciplina"].notna().sum() >= 2:
            disc_vals = voter_data["disciplina"].dropna().values
            delta_disc = np.mean(np.abs(np.diff(disc_vals)))
        else:
            delta_disc = np.nan

        # Switcher: changed party between any consecutive pair
        parties_sequence = voter_data["partido"].values
        es_switcher = any(
            parties_sequence[j] != parties_sequence[j + 1] for j in range(len(parties_sequence) - 1)
        )

        records.append(
            {
                "voter_id": voter_id,
                "nombre": voter_data["nombre"].iloc[0],
                "genero": voter_data["genero"].iloc[0],
                "n_legs": n_legs,
                "legislaturas": legislaturas,
                "partidos": partidos,
                "estabilidad_nominate_d1": round(estabilidad_d1, 6)
                if not np.isnan(estabilidad_d1)
                else np.nan,
                "movimiento_ideologico": round(movimiento, 6),
                "delta_disciplina_mean": round(delta_disc, 4)
                if not np.isnan(delta_disc)
                else np.nan,
                "es_switcher": es_switcher,
            }
        )

    result = pd.DataFrame(records)
    logger.info(
        "Métricas de trayectoria: %d legisladores con 2+ legs (%d switchers)",
        len(result),
        result["es_switcher"].sum(),
    )
    return result


# ---------------------------------------------------------------------------
# Paso 4: Switchers
# ---------------------------------------------------------------------------


def detect_switchers(panel_aligned: pd.DataFrame) -> pd.DataFrame:
    """Identifica legislators que cambiaron de partido entre legislaturas.

    Returns: DataFrame with one row per switch event.
    """
    # Get multi-leg voters
    leg_counts = panel_aligned.groupby("voter_id")["legislatura"].nunique()
    multi_leg = leg_counts[leg_counts >= 2].index

    records = []
    for voter_id in multi_leg:
        voter_data = panel_aligned[panel_aligned["voter_id"] == voter_id].copy()
        voter_data = voter_data.sort_values(
            "legislatura",
            key=lambda x: x.map(
                lambda v: LEGISLATURAS_ORDERED.index(v) if v in LEGISLATURAS_ORDERED else 99
            ),
        )

        parties = voter_data["partido"].values
        for j in range(len(parties) - 1):
            if parties[j] != parties[j + 1]:
                row_orig = voter_data.iloc[j]
                row_dest = voter_data.iloc[j + 1]

                delta_disc = np.nan
                disc_antes = row_orig.get("disciplina", np.nan)
                disc_despues = row_dest.get("disciplina", np.nan)
                if pd.notna(disc_antes) and pd.notna(disc_despues):
                    delta_disc = round(disc_despues - disc_antes, 4)

                dim1_antes = row_orig.get("dim_1_aligned", np.nan)
                dim1_despues = row_dest.get("dim_1_aligned", np.nan)
                delta_dim1 = np.nan
                if pd.notna(dim1_antes) and pd.notna(dim1_despues):
                    delta_dim1 = round(dim1_despues - dim1_antes, 6)

                records.append(
                    {
                        "voter_id": voter_id,
                        "nombre": row_orig["nombre"],
                        "legislatura_origen": row_orig["legislatura"],
                        "legislatura_destino": row_dest["legislatura"],
                        "partido_origen": parties[j],
                        "partido_destino": parties[j + 1],
                        "disciplina_antes": disc_antes,
                        "disciplina_despues": disc_despues,
                        "delta_disciplina": delta_disc,
                        "dim1_antes": dim1_antes,
                        "dim1_despues": dim1_despues,
                        "delta_dim1": delta_dim1,
                    }
                )

    result = pd.DataFrame(records)
    logger.info("Switchers detectados: %d eventos de cambio de partido", len(result))
    return result


# ---------------------------------------------------------------------------
# Paso 5: Visualizaciones
# ---------------------------------------------------------------------------


def _top_parties(panel: pd.DataFrame, n: int = 8) -> list[str]:
    """Returns top-N parties by frequency."""
    party_counts = panel["partido"].value_counts()
    return party_counts.head(n).index.tolist()


def plot_trajectory_scatter(panel_aligned: pd.DataFrame, output_dir: Path):
    """Scatter NOMINATE (aligned) con líneas conectando multi-legisladores."""
    fig, ax = plt.subplots(figsize=(12, 8))

    top_parties = _top_parties(panel_aligned, n=8)
    color_map = {}
    cmap = plt.cm.get_cmap("tab10")
    for i, party in enumerate(top_parties):
        color_map[party] = cmap(i)
    default_color = (0.7, 0.7, 0.7, 0.3)

    # Draw connecting lines for multi-leg legislators
    leg_counts = panel_aligned.groupby("voter_id")["legislatura"].nunique()
    multi_leg = leg_counts[leg_counts >= 2].index
    switchers_set = set()
    if "partido" in panel_aligned.columns:
        for voter_id in multi_leg:
            voter_data = panel_aligned[panel_aligned["voter_id"] == voter_id].sort_values(
                "legislatura",
                key=lambda x: x.map(
                    lambda v: LEGISLATURAS_ORDERED.index(v) if v in LEGISLATURAS_ORDERED else 99
                ),
            )
            parties = voter_data["partido"].values
            if any(parties[j] != parties[j + 1] for j in range(len(parties) - 1)):
                switchers_set.add(voter_id)

    for voter_id in multi_leg:
        voter_data = panel_aligned[panel_aligned["voter_id"] == voter_id].sort_values(
            "legislatura",
            key=lambda x: x.map(
                lambda v: LEGISLATURAS_ORDERED.index(v) if v in LEGISLATURAS_ORDERED else 99
            ),
        )
        x = voter_data["dim_1_aligned"].values
        y = voter_data["dim_2_aligned"].values

        if voter_id in switchers_set:
            ax.plot(x, y, color="red", alpha=0.6, linewidth=1.0, zorder=2)
        else:
            ax.plot(x, y, color="grey", alpha=0.15, linewidth=0.5, zorder=1)

    # Scatter points colored by party
    for party in top_parties:
        mask = panel_aligned["partido"] == party
        subset = panel_aligned[mask]
        ax.scatter(
            subset["dim_1_aligned"],
            subset["dim_2_aligned"],
            c=[color_map[party]],
            label=party,
            s=15,
            alpha=0.5,
            zorder=3,
        )

    # Remaining parties in grey
    mask_other = ~panel_aligned["partido"].isin(top_parties)
    if mask_other.any():
        ax.scatter(
            panel_aligned.loc[mask_other, "dim_1_aligned"],
            panel_aligned.loc[mask_other, "dim_2_aligned"],
            c=[default_color],
            s=8,
            alpha=0.3,
            zorder=3,
        )

    ax.set_xlabel("Dimensión 1 (alineada)")
    ax.set_ylabel("Dimensión 2 (alineada)")
    camara = panel_aligned["camara"].iloc[0] if "camara" in panel_aligned.columns else ""
    ax.set_title(f"Trayectorias NOMINATE — {camara.capitalize()}")
    ax.legend(loc="upper right", fontsize=8, markerscale=2)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = output_dir / "trayectorias_scatter.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


def plot_switchers_before_after(switchers: pd.DataFrame, output_dir: Path):
    """Box plot: disciplina y dim_1 antes/después de switch."""
    if switchers.empty:
        logger.warning("No hay switchers para graficar")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Disciplina
    disc_data = switchers[["disciplina_antes", "disciplina_despues"]].dropna()
    if not disc_data.empty:
        axes[0].boxplot(
            [disc_data["disciplina_antes"].values, disc_data["disciplina_despues"].values],
            labels=["Antes", "Después"],
        )
    axes[0].set_title("Disciplina partidista")
    axes[0].set_ylabel("Disciplina")

    # Posición dim_1
    dim_data = switchers[["dim1_antes", "dim1_despues"]].dropna()
    if not dim_data.empty:
        axes[1].boxplot(
            [dim_data["dim1_antes"].values, dim_data["dim1_despues"].values],
            labels=["Antes", "Después"],
        )
    axes[1].set_title("Posición ideológica (dim_1)")
    axes[1].set_ylabel("Dim 1 (alineada)")

    plt.suptitle("Switchers: Antes vs Después del cambio de partido")
    plt.tight_layout()
    out_path = output_dir / "switchers_before_after.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


def plot_stability_distribution(trajectories: pd.DataFrame, output_dir: Path):
    """Histograma de estabilidad NOMINATE y movimiento ideológico."""
    if trajectories.empty:
        logger.warning("No hay datos de trayectoria para graficar")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Estabilidad
    est_data = trajectories["estabilidad_nominate_d1"].dropna()
    if not est_data.empty:
        axes[0].hist(est_data, bins=30, color="steelblue", alpha=0.7, edgecolor="white")
    axes[0].set_title("Estabilidad NOMINATE (dim_1)")
    axes[0].set_xlabel("Desviación estándar dim_1")
    axes[0].set_ylabel("Frecuencia")

    # Movimiento ideológico
    mov_data = trajectories["movimiento_ideologico"].dropna()
    if not mov_data.empty:
        axes[1].hist(mov_data, bins=30, color="coral", alpha=0.7, edgecolor="white")
    axes[1].set_title("Movimiento ideológico")
    axes[1].set_xlabel("Distancia euclidiana (primera → última leg)")
    axes[1].set_ylabel("Frecuencia")

    plt.tight_layout()
    out_path = output_dir / "trayectorias_stability.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Guardado: %s", out_path)


# ---------------------------------------------------------------------------
# Paso 6: Runner principal
# ---------------------------------------------------------------------------


def run_trayectorias(camara: str, output_dir: str | None = None):
    """Ejecuta todo el pipeline de trayectorias para una cámara.

    Returns dict with: panel, alignments, trajectories, switchers, files_created
    """
    if output_dir is None:
        output_dir = str(PROJECT_ROOT / f"analysis/analisis-{camara}/output")
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("=== Iniciando pipeline de trayectorias para %s ===", camara)

    # 1. Load NOMINATE coords
    coords = load_nominate_coords(camara)

    # 2. Compute individual discipline
    discipline = compute_individual_discipline(DB_PATH, camara)

    # 3. Build panel
    panel = build_panel(coords, discipline, DB_PATH)

    # 4. Compute alignments
    alignments, panel_aligned = compute_all_alignments(panel)

    # 5. Compute trajectory metrics
    trajectories = compute_trajectory_metrics(panel_aligned)

    # 6. Detect switchers
    switchers = detect_switchers(panel_aligned)

    # 7. Save CSVs
    files_created = []

    # trayectorias_panel.csv
    panel_cols = [
        "voter_id",
        "nombre",
        "genero",
        "curul_tipo",
        "legislatura",
        "partido",
        "partido_disciplina",
        "dim_1_aligned",
        "dim_2_aligned",
        "dim_1_raw",
        "dim_2_raw",
        "disciplina",
        "n_votos",
    ]
    panel_save = panel_aligned[[c for c in panel_cols if c in panel_aligned.columns]]
    f1 = out_path / "trayectorias_panel.csv"
    panel_save.to_csv(f1, index=False)
    files_created.append(str(f1))
    logger.info("Guardado: %s (%d filas)", f1, len(panel_save))

    # trayectorias_resumen.csv
    f2 = out_path / "trayectorias_resumen.csv"
    trajectories.to_csv(f2, index=False)
    files_created.append(str(f2))
    logger.info("Guardado: %s (%d filas)", f2, len(trajectories))

    # switchers_detalle.csv
    f3 = out_path / "switchers_detalle.csv"
    switchers.to_csv(f3, index=False)
    files_created.append(str(f3))
    logger.info("Guardado: %s (%d filas)", f3, len(switchers))

    # procrustes_alignment.csv
    f4 = out_path / "procrustes_alignment.csv"
    alignments.to_csv(f4, index=False)
    files_created.append(str(f4))
    logger.info("Guardado: %s (%d filas)", f4, len(alignments))

    # 8. Generate plots
    plot_trajectory_scatter(panel_aligned, out_path)
    files_created.append(str(out_path / "trayectorias_scatter.png"))

    plot_switchers_before_after(switchers, out_path)
    files_created.append(str(out_path / "switchers_before_after.png"))

    plot_stability_distribution(trajectories, out_path)
    files_created.append(str(out_path / "trayectorias_stability.png"))

    logger.info(
        "=== Pipeline completo para %s: %d archivos generados ===",
        camara,
        len(files_created),
    )

    return {
        "panel": panel_aligned,
        "alignments": alignments,
        "trajectories": trajectories,
        "switchers": switchers,
        "files_created": files_created,
    }
