#!/usr/bin/env python3
"""
nominate.py — Módulo de análisis W-NOMINATE para el Congreso de la Unión.

Implementa el algoritmo W-NOMINATE (Weighted Nominal Three-Step Estimation)
de Poole & Rosenthal (1985, 1997) para estimar puntos ideales de legisladores
a partir de sus patrones de votación.

Referencias:
    - Poole, K.T. & Rosenthal, H. (1985). "A Spatial Model for Legislative
      Roll Call Analysis". American Journal of Political Science, 29(2), 357-384.
    - Poole, K.T. & Rosenthal, H. (1997). "Congress: A Political-Economic
      History of Roll Call Voting". Oxford University Press.
    - Poole, K.T. (2005). "Spatial Models of Parliamentary Voting".
      Cambridge University Press.

Funciones principales:
    - prepare_vote_matrix: construye matriz binarizada legislators × vote_events
    - run_wnominate: ejecuta W-NOMINATE desde cero
    - compute_fit_statistics: calcula métricas de calidad del modelo
    - nominate_by_legislatura: ejecuta por cada legislatura individual
    - nominate_cross_legislatura: ejecuta con datos combinados
"""

import logging
import sqlite3
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import svd
from scipy.optimize import minimize
from scipy.stats import norm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes y mapeos (centralizados en db.constants)
# ---------------------------------------------------------------------------
from db.constants import _NAME_TO_ORG, _P_FLOOR, _PARTY_ORG_IDS

_SEED = 42


# ---------------------------------------------------------------------------
# Función 1: prepare_vote_matrix
# ---------------------------------------------------------------------------
def prepare_vote_matrix(
    db_path: str,
    legislatura: str | None = None,
    min_votes: int = 10,
    min_participants: int = 10,
    lopsided_threshold: float = 0.975,
    camara: str | None = None,
) -> dict:
    """Construir la matriz binarizada legislators × vote_events para NOMINATE.

    La binarización sigue la convención estándar:
        - ``'a_favor'`` → 1 (Yea)
        - ``'en_contra'`` → 0 (Nay)
        - ``'abstencion'`` → NaN (no es yea ni nay, se excluye)
        - ``'ausente'`` → NaN (missing)

    La matriz resultante contiene solo legisladores con ≥ ``min_votes`` votos
    binarios (a_favor o en_contra) y solo votaciones con ≥ ``min_participants``
    que emitieron a_favor o en_contra.

    Args:
        db_path: Ruta al archivo SQLite (congreso.db).
        legislatura: Filtro de legislatura (ej: ``'LXVI'``). Si es ``None``,
            carga todas las legislaturas.
        min_votes: Mínimo de votos binarios para incluir un legislador.
        min_participants: Mínimo de participantes binarios para incluir
            una votación.
        lopsided_threshold: Umbral para filtrar votaciones lopsided
            (donde la proporción mayoritaria excede este valor).
            ``None`` o 0 deshabilita el filtro. Default: 0.975.
        camara: Filtrar por cámara. ``'D'`` para Diputados, ``'S'`` para
            Senado. Si es ``None``, no filtra.

    Returns:
        Diccionario con:
        - ``'matrix'``: np.ndarray shape (n_legislators, n_votes), con NaN
          para entradas faltantes.
        - ``'legislators'``: lista de voter_ids ordenados.
        - ``'vote_events'``: lista de vote_event_ids ordenados.
        - ``'legislator_names'``: dict voter_id → nombre.
        - ``'legislator_parties'``: dict voter_id → org_id del partido.
        - ``'org_map'``: dict org_id → nombre del partido.
        - ``'legislatura'``: legislatura filtrada o ``None``.
        - ``'n_legislators'``: número de legisladores.
        - ``'n_votes'``: número de votaciones.
        - ``'sparsity'``: proporción de NaN en la matriz.

    Raises:
        FileNotFoundError: Si ``db_path`` no existe.
        ValueError: Si no hay datos suficientes para construir la matriz.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        # ------------------------------------------------------------------
        # 1. Cargar votos con filtro de legislatura y/o cámara
        # ------------------------------------------------------------------
        needs_join = legislatura is not None or camara is not None
        conditions: list[str] = []
        params: list[str] = []

        if legislatura is not None:
            conditions.append("ve.legislatura = ?")
            params.append(legislatura)

        if camara is not None:
            camara_org = "O08" if camara == "D" else "O09"
            conditions.append("ve.organization_id = ?")
            params.append(camara_org)

        if needs_join:
            where = " AND ".join(conditions)
            vote_query = (
                'SELECT v.voter_id, v.vote_event_id, v.option, v."group" '
                "FROM vote v JOIN vote_event ve ON v.vote_event_id = ve.id "
                f"WHERE {where}"
            )
            votes_df = pd.read_sql_query(vote_query, conn, params=params)
        else:
            vote_query = 'SELECT v.voter_id, v.vote_event_id, v.option, v."group" FROM vote v'
            votes_df = pd.read_sql_query(vote_query, conn)

        if votes_df.empty:
            raise ValueError(f"No se encontraron votos para legislatura={legislatura}")

        # Normalizar partido
        votes_df["party_id"] = votes_df["group"].map(lambda x: _NAME_TO_ORG.get(x, "O11"))

        # ------------------------------------------------------------------
        # 2. Binarizar: solo a_favor (1) y en_contra (0)
        # ------------------------------------------------------------------
        # abstencion y ausente se convierten en NaN (no participó en términos
        # binarios)
        option_map = {"a_favor": 1.0, "en_contra": 0.0}
        votes_df["binary"] = votes_df["option"].map(option_map)

        # Filtrar solo votos binarios para determinar elegibilidad
        binary_votes = votes_df.dropna(subset=["binary"]).copy()

        # ------------------------------------------------------------------
        # 2.5. Filtrar lopsided votes (votaciones unanimemente desbalanceadas)
        # ------------------------------------------------------------------
        # Eliminar votaciones donde la proporción de votos mayoritarios
        # (entre los binarios no-NaN) supera el threshold. Esto sigue el
        # estándar del paquete wnominate de R (default 0.975).
        if lopsided_threshold is not None and lopsided_threshold > 0:
            # Calcular proporción mayoritaria por vote_event
            binary_by_ve = binary_votes.groupby("vote_event_id")["binary"].agg(
                lambda x: max(x.sum(), len(x) - x.sum()) / len(x) if len(x) > 0 else 0
            )
            lopsided_ves = set(binary_by_ve[binary_by_ve > lopsided_threshold].index)
            n_original = len(set(binary_votes["vote_event_id"].unique()))
            n_lopsided = len(lopsided_ves)
            logger.info(
                "Filtro lopsided (threshold=%.3f): %d de %d votaciones eliminadas",
                lopsided_threshold,
                n_lopsided,
                n_original,
            )
            # Eliminar votaciones lopsided del DataFrame
            votes_df = votes_df[~votes_df["vote_event_id"].isin(lopsided_ves)].copy()
            binary_votes = binary_votes[~binary_votes["vote_event_id"].isin(lopsided_ves)].copy()
        else:
            logger.info("Filtro lopsided deshabilitado (threshold=None o 0)")

        # ------------------------------------------------------------------
        # 3. Filtrar legisladores con ≥ min_votes votos binarios
        # ------------------------------------------------------------------
        leg_counts = binary_votes["voter_id"].value_counts()
        eligible_legs = set(leg_counts[leg_counts >= min_votes].index)

        # ------------------------------------------------------------------
        # 4. Filtrar vote_events con ≥ min_participants binarios
        # ------------------------------------------------------------------
        filtered_binary = binary_votes[binary_votes["voter_id"].isin(eligible_legs)]
        ve_counts = filtered_binary["vote_event_id"].value_counts()
        eligible_ves = set(ve_counts[ve_counts >= min_participants].index)

        # ------------------------------------------------------------------
        # 5. Construir matriz pivote
        # ------------------------------------------------------------------
        # Trabajar solo con votos en eventos elegibles
        working = votes_df[
            (votes_df["voter_id"].isin(eligible_legs))
            & (votes_df["vote_event_id"].isin(eligible_ves))
        ].copy()

        # Re-aplicar filtro de min_votes y min_participants (puede haber
        # cambiado al filtrar eventos)
        leg_counts2 = working.dropna(subset=["binary"])["voter_id"].value_counts()
        eligible_legs = set(leg_counts2[leg_counts2 >= min_votes].index)

        ve_counts2 = (
            working[working["voter_id"].isin(eligible_legs)]
            .dropna(subset=["binary"])["vote_event_id"]
            .value_counts()
        )
        eligible_ves = set(ve_counts2[ve_counts2 >= min_participants].index)

        working = working[
            (working["voter_id"].isin(eligible_legs))
            & (working["vote_event_id"].isin(eligible_ves))
        ]

        # Legisladores y eventos ordenados
        legislators = sorted(eligible_legs)
        vote_events = sorted(eligible_ves)

        if not legislators or not vote_events:
            raise ValueError(
                f"Datos insuficientes: {len(legislators)} legisladores, "
                f"{len(vote_events)} votaciones (min_votes={min_votes}, "
                f"min_participants={min_participants})"
            )

        # Pivotar: filas=legislators, columnas=vote_events, valores=binary
        pivot = working.pivot_table(
            index="voter_id",
            columns="vote_event_id",
            values="binary",
            aggfunc="first",
        )

        # Reindexar para asegurar orden consistente
        pivot = pivot.reindex(index=legislators, columns=vote_events)

        matrix = pivot.values  # ya tiene NaN donde corresponde

        # ------------------------------------------------------------------
        # 6. Obtener nombres de legisladores
        # ------------------------------------------------------------------
        placeholders = ",".join(["?"] * len(legislators))
        persons_df = pd.read_sql_query(
            f"SELECT id, nombre FROM person WHERE id IN ({placeholders})",
            conn,
            params=legislators,
        )
        legislator_names: dict[str, str] = dict(zip(persons_df["id"], persons_df["nombre"]))

        # ------------------------------------------------------------------
        # 7. Obtener partido principal de cada legislador
        # ------------------------------------------------------------------
        legislator_parties = _get_primary_party(votes_df)

        # ------------------------------------------------------------------
        # 8. Obtener mapa de organizaciones
        # ------------------------------------------------------------------
        orgs_df = pd.read_sql_query("SELECT id, nombre FROM organization", conn)
        org_map: dict[str, str] = {}
        for _, row in orgs_df.iterrows():
            if row["id"] in _PARTY_ORG_IDS:
                org_map[row["id"]] = row["nombre"]

        # ------------------------------------------------------------------
        # 9. Calcular sparsity
        # ------------------------------------------------------------------
        n_total = matrix.size
        n_nan = np.isnan(matrix).sum()
        sparsity = n_nan / n_total if n_total > 0 else 0.0

        logger.info(
            "Matriz preparada: %d legisladores × %d votaciones, sparsity=%.2f%%",
            len(legislators),
            len(vote_events),
            sparsity * 100,
        )

        return {
            "matrix": matrix,
            "legislators": legislators,
            "vote_events": vote_events,
            "legislator_names": legislator_names,
            "legislator_parties": legislator_parties,
            "org_map": org_map,
            "legislatura": legislatura,
            "n_legislators": len(legislators),
            "n_votes": len(vote_events),
            "sparsity": sparsity,
            "lopsided_threshold": lopsided_threshold,
        }

    finally:
        conn.close()


def _get_primary_party(votes_df: pd.DataFrame) -> dict[str, str]:
    """Obtener el partido principal (org_id más frecuente) de cada legislador.

    Replica la lógica de ``get_primary_party`` de covotacion.py:
    normaliza ``vote.group`` con ``_NAME_TO_ORG`` y retorna el org_id
    más frecuente por legislador.

    Args:
        votes_df: DataFrame con columnas ``['voter_id', 'group']``.

    Returns:
        Dict voter_id → org_id (partido principal).
    """
    primary: dict[str, str] = {}
    for voter_id, group in votes_df.groupby("voter_id"):
        # Normalizar cada group value al org_id canónico
        org_ids = group["group"].map(lambda x: _NAME_TO_ORG.get(x, "O11"))
        party_counts = Counter(org_ids)
        primary[voter_id] = party_counts.most_common(1)[0][0]
    return primary


# ---------------------------------------------------------------------------
# Función 2a: Workers para paralelización de W-NOMINATE
# ---------------------------------------------------------------------------
def _bill_worker(task: tuple) -> tuple[int, np.ndarray]:
    """Worker para optimizar parámetros de la votación j (picklable, top-level).

    Recibe todos los datos necesarios como argumento explícito para ser
    compatible con multiprocessing.  Cada worker es independiente — no
    comparte estado mutable con otros workers.

    Args:
        task: Tupla (j, params_j, coords_subset, votes_subset,
              beta_val, w_val, dims, opt_opts).

    Returns:
        Tupla (j, new_params_j) con los parámetros optimizados.
    """
    (j, params_j, coords_subset, votes_subset, beta_val, w_val, dims, opt_opts) = task

    n_obs = len(votes_subset)
    if n_obs == 0:
        return j, params_j

    dim_weights = np.ones(dims)
    if dims > 1:
        dim_weights[1:] = w_val

    def neg_ll(p_flat: np.ndarray) -> float:
        O_j = p_flat[:dims]
        P_j = p_flat[dims:]

        yea_pole = O_j + P_j
        nay_pole = O_j - P_j

        diff_yea = coords_subset - yea_pole[np.newaxis, :]
        diff_yea_w = diff_yea * dim_weights[np.newaxis, :]
        dist2_yea = (diff_yea_w**2).sum(axis=1)

        diff_nay = coords_subset - nay_pole[np.newaxis, :]
        diff_nay_w = diff_nay * dim_weights[np.newaxis, :]
        dist2_nay = (diff_nay_w**2).sum(axis=1)

        logit = beta_val * (np.exp(-dist2_yea) - np.exp(-dist2_nay))
        logit = np.clip(logit, -30, 30)

        p_yea = norm.cdf(logit)
        p_correct = np.where(votes_subset == 1.0, p_yea, 1.0 - p_yea)
        p_correct = np.clip(p_correct, _P_FLOOR, 1.0)

        return -np.sum(np.log(p_correct))

    result = minimize(neg_ll, params_j, method="Nelder-Mead", options=opt_opts)
    return j, result.x


def _leg_worker(task: tuple) -> tuple[int, np.ndarray]:
    """Worker para optimizar punto ideal del legislador i (picklable, top-level).

    Recibe todos los datos necesarios como argumento explícito para ser
    compatible con multiprocessing.  Cada worker es independiente.

    Args:
        task: Tupla (i, coords_i, bill_params_subset, votes_subset,
              beta_val, w_val, dims, opt_opts).

    Returns:
        Tupla (i, new_coords_i) con las coordenadas optimizadas.
    """
    (i, coords_i, bill_params_subset, votes_subset, beta_val, w_val, dims, opt_opts) = task

    n_obs = len(votes_subset)
    if n_obs == 0:
        return i, coords_i

    dim_weights = np.ones(dims)
    if dims > 1:
        dim_weights[1:] = w_val

    def neg_ll(x_flat: np.ndarray) -> float:
        x_i = x_flat

        O_j = bill_params_subset[:, :dims]
        P_j = bill_params_subset[:, dims:]

        yea_pole = O_j + P_j
        nay_pole = O_j - P_j

        diff_yea = x_i[np.newaxis, :] - yea_pole
        diff_yea_w = diff_yea * dim_weights[np.newaxis, :]
        dist2_yea = (diff_yea_w**2).sum(axis=1)

        diff_nay = x_i[np.newaxis, :] - nay_pole
        diff_nay_w = diff_nay * dim_weights[np.newaxis, :]
        dist2_nay = (diff_nay_w**2).sum(axis=1)

        logit = beta_val * (np.exp(-dist2_yea) - np.exp(-dist2_nay))
        logit = np.clip(logit, -30, 30)

        p_yea = norm.cdf(logit)
        p_correct = np.where(votes_subset == 1.0, p_yea, 1.0 - p_yea)
        p_correct = np.clip(p_correct, _P_FLOOR, 1.0)

        ll = np.sum(np.log(p_correct))

        # Penalización por salir del hipercubo unitario
        if np.sum(x_flat**2) > 1.0:
            ll -= 1e300

        return -ll

    result = minimize(neg_ll, coords_i, method="Nelder-Mead", options=opt_opts)
    return i, result.x


# ---------------------------------------------------------------------------
# Función 2b: run_wnominate
# ---------------------------------------------------------------------------
def run_wnominate(
    vote_data: dict,
    dimensions: int = 2,
    maxiter: int = 100,
    tol: float = 1e-5,
    seed: int = 42,
    n_workers: int = 1,
) -> dict:
    """Ejecutar el algoritmo W-NOMINATE para estimar puntos ideales.

    El modelo W-NOMINATE asume que cada legislador i tiene un punto ideal
    x_i en un espacio s-dimensional, y cada votación j tiene un punto de
    política definido por un punto medio O_j y un vector de dispersión P_j.

    La probabilidad de votar Yea es:

        P(Yea_ij) = Φ(β × [exp(-d²(x_i, O_j + P_j)) - exp(-d²(x_i, O_j - P_j))])

    Donde:
        - Φ = CDF de la normal estándar
        - d²(x, y) = Σ_k (x_k - y_k)² para la 1ra dimensión, y
          w² × (x_k - y_k)² para dimensiones adicionales
        - β = parámetro de saliencia (signal-to-noise ratio)
        - w = peso de la segunda dimensión (< 1, típico ~0.5)

    El algoritmo alterna entre:
        1. Fijar puntos ideales, optimizar parámetros de votación (O_j, P_j)
        2. Fijar parámetros de votación, optimizar puntos ideales (x_i)
        3. Optimizar parámetros globales (β, w)

    Restricción: los puntos ideales deben estar dentro del hipercubo unitario
    (||x_i||² ≤ 1), implementada con penalización en el log-likelihood.

    Args:
        vote_data: Diccionario retornado por ``prepare_vote_matrix``.
        dimensions: Número de dimensiones del espacio (típicamente 2).
        maxiter: Máximo de iteraciones del algoritmo alternante.
        tol: Tolerancia de convergencia en log-likelihood.
        seed: Semilla para reproducibilidad.
        n_workers: Número de procesos para paralelizar la optimización.
            ``1`` = secuencial (default, idéntico al comportamiento original).
            ``>1`` = usa ``ProcessPoolExecutor`` con ``max_workers=n_workers``.
            Recomendado: 15 en máquinas con ≥20 cores.

    Returns:
        Diccionario con coordenadas, parámetros y métricas de ajuste.

    Raises:
        ValueError: Si la matriz está vacía o las dimensiones son inválidas.
    """
    # NOTA: El algoritmo W-NOMINATE es determinista (SVD + Nelder-Mead).
    # El parámetro seed se conserva por compatibilidad de interfaz pero
    # no afecta el resultado; la reproducibilidad es inherente al método.
    _ = seed

    use_parallel = n_workers > 1
    if use_parallel:
        logger.info("Paralelización habilitada: %d workers (ProcessPoolExecutor)", n_workers)

    vote_matrix = vote_data["matrix"].astype(np.float64)
    n_legs, n_votes = vote_matrix.shape

    if n_legs == 0 or n_votes == 0:
        raise ValueError("Matriz vacía — no se puede ejecutar NOMINATE")

    if dimensions < 1:
        raise ValueError(f"Dimensiones debe ser ≥ 1, recibido {dimensions}")

    logger.info(
        "Iniciando W-NOMINATE: %d legisladores × %d votaciones, dims=%d, maxiter=%d",
        n_legs,
        n_votes,
        dimensions,
        maxiter,
    )

    # ------------------------------------------------------------------
    # 1. Inicialización con SVD truncado
    # ------------------------------------------------------------------
    # Reemplazar NaN con 0.5 (valor neutro) para SVD
    matrix_filled = np.nan_to_num(vote_matrix, nan=0.5)

    # Restar la media por columna
    matrix_centered = matrix_filled - matrix_filled.mean(axis=0)

    # SVD truncado (tomar solo las componentes necesarias)
    # Para matrices grandes, usar economic SVD
    k = min(dimensions, min(n_legs, n_votes) - 1)
    U, S, Vt = svd(matrix_centered, full_matrices=False)

    # Tomar las primeras 'dimensions' componentes
    initial_coords = U[:, :dimensions] * S[:dimensions]

    # Normalizar al hipercubo unitario (||x_i||² ≤ 1)
    norms = np.sqrt((initial_coords**2).sum(axis=1, keepdims=True))
    initial_coords = initial_coords / np.maximum(norms, 1.0) * 0.9

    # Asegurar shape correcta
    if initial_coords.shape[1] < dimensions:
        padding = np.zeros((n_legs, dimensions - initial_coords.shape[1]))
        initial_coords = np.hstack([initial_coords, padding])

    # ------------------------------------------------------------------
    # 2. Inicializar parámetros
    # ------------------------------------------------------------------
    coordinates = initial_coords.copy()  # shape (n_legs, dims)
    beta = 8.0  # Parámetro de saliencia (típico de la literatura)
    w = 0.5  # Peso de la 2da dimensión (< 1)

    # Parámetros de cada votación: [O_j_x, O_j_y, P_j_x, P_j_y] para 2D
    # Para dimensions > 2, la estructura es: O_j (dims) + P_j (dims)
    bill_params = np.zeros((n_votes, 2 * dimensions))

    # Inicializar parámetros de votación de forma razonable
    for j in range(n_votes):
        col = vote_matrix[:, j]
        valid = ~np.isnan(col)
        if valid.sum() > 0:
            yea_rate = col[valid].mean()
            # Punto medio en la 1ra dimensión basado en tasa de aprobación
            bill_params[j, 0] = yea_rate - 0.5
            # P_j en dirección de aprobación
            bill_params[j, dimensions] = 0.3

    # ------------------------------------------------------------------
    # 3. Pre-computar máscaras de NaN para cada legislador y votación
    # ------------------------------------------------------------------
    # Máscara de observaciones válidas (True = observado)
    obs_mask = ~np.isnan(vote_matrix)  # shape (n_legs, n_votes)

    # Para cada legislador: índices de votaciones donde participó
    leg_vote_indices = [np.where(obs_mask[i])[0] for i in range(n_legs)]

    # Para cada votación: índices de legisladores que participaron
    vote_leg_indices = [np.where(obs_mask[:, j])[0] for j in range(n_votes)]

    logger.info("Máscaras de observación pre-computadas")

    # ------------------------------------------------------------------
    # 4. Funciones auxiliares para log-likelihood
    # ------------------------------------------------------------------
    def _compute_prob_correct_vec(
        coords: np.ndarray,
        bill_p: np.ndarray,
        b: float,
        w_val: float,
        votes: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """Calcular P(voto correcto) de forma vectorizada.

        Para cada (i, j) donde mask[i,j] = True:
            P_ij = Φ(β × [exp(-d²(x_i, O_j+P_j)) - exp(-d²(x_i, O_j-P_j))])
            P(correct_ij) = P_ij si votes[i,j]=1, (1-P_ij) si votes[i,j]=0

        Args:
            coords: puntos ideales, shape (n_legs, dims).
            bill_p: parámetros de votación, shape (n_votes, 2*dims).
            b: parámetro β.
            w_val: peso de la 2da dimensión.
            votes: matriz de votos (1/0/NaN), shape (n_legs, n_votes).
            mask: máscara de observaciones, shape (n_legs, n_votes).

        Returns:
            Probabilidades de voto correcto, shape (n_legs, n_votes),
            con NaN donde mask=False.
        """
        n_l, n_v = votes.shape
        dims = coords.shape[1]

        # Extraer O_j y P_j de los parámetros de votación
        O_j = bill_p[:, :dims]  # shape (n_votes, dims)
        P_j = bill_p[:, dims:]  # shape (n_votes, dims)

        # Pesos por dimensión: dim 0 → peso 1.0, dims ≥1 → peso w
        dim_weights = np.ones(dims)
        if dims > 1:
            dim_weights[1:] = w_val

        # --- Distancia a O_j + P_j (polo Yea) ---
        yea_pole = O_j + P_j  # shape (n_votes, dims)
        # diff_yea[i,j,k] = coords[i,k] - yea_pole[j,k]
        diff_yea = coords[:, np.newaxis, :] - yea_pole[np.newaxis, :, :]
        # Aplicar pesos por dimensión
        diff_yea_weighted = diff_yea * dim_weights[np.newaxis, np.newaxis, :]
        dist2_yea = (diff_yea_weighted**2).sum(axis=2)  # shape (n_l, n_v)

        # --- Distancia a O_j - P_j (polo Nay) ---
        nay_pole = O_j - P_j  # shape (n_votes, dims)
        diff_nay = coords[:, np.newaxis, :] - nay_pole[np.newaxis, :, :]
        diff_nay_weighted = diff_nay * dim_weights[np.newaxis, np.newaxis, :]
        dist2_nay = (diff_nay_weighted**2).sum(axis=2)  # shape (n_l, n_v)

        # Probabilidad de Yea
        logit = b * (np.exp(-dist2_yea) - np.exp(-dist2_nay))

        # Clamp para evitar overflow en norm.cdf
        logit = np.clip(logit, -30, 30)

        p_yea = norm.cdf(logit)  # shape (n_l, n_v)

        # P(correcto): si votó a_favor (1) → p_yea; si en_contra (0) → 1-p_yea
        p_correct = np.where(votes == 1.0, p_yea, 1.0 - p_yea)

        # Clamp probabilidad mínima para evitar log(0) = -inf
        # Consistente con _P_FLOOR = 1e-15 (referencia: R wnominate)
        p_correct = np.clip(p_correct, _P_FLOOR, 1.0)

        # Aplicar máscara (NaN donde no observado)
        p_correct = np.where(mask, p_correct, np.nan)

        return p_correct

    def _total_log_likelihood(
        coords: np.ndarray,
        bill_p: np.ndarray,
        b: float,
        w_val: float,
    ) -> float:
        """Calcular log-likelihood total del modelo.

        Usa un clamp de probabilidad mínima (_P_FLOOR) para evitar que
        observaciones mal clasificadas produzcan log(0) = -inf, lo cual
        impediría la convergencia del algoritmo. Esto es consistente con
        la práctica estándar en implementaciones de NOMINATE.
        """
        p_correct = _compute_prob_correct_vec(coords, bill_p, b, w_val, vote_matrix, obs_mask)
        # Log-likelihood: suma de log(P(correcto)) solo donde hay observación
        # p_correct ya está clampeado a [_P_FLOOR, 1.0], así que log es seguro
        log_p = np.log(p_correct)
        # Reemplazar NaN (no observados) con 0 para la suma
        valid_ll = np.where(obs_mask, log_p, 0.0)
        # Reemplazar cualquier -inf residual por un valor muy negativo
        # (safety net, no debería ocurrir con el clamp)
        valid_ll = np.where(np.isfinite(valid_ll), valid_ll, -23.0)
        total_ll = valid_ll.sum()

        # Penalización por puntos fuera del hipercubo unitario
        norms_sq = (coords**2).sum(axis=1)
        penalty = np.sum(norms_sq > 1.0) * 1e300

        return total_ll - penalty

    # ------------------------------------------------------------------
    # 5. Funciones de optimización para cada componente
    # ------------------------------------------------------------------
    opt_opts = {"maxiter": 200, "xatol": 1e-4, "fatol": 1e-4}

    def _optimize_bill_j(params_j: np.ndarray, j: int) -> np.ndarray:
        """Optimizar parámetros de la votación j (O_j, P_j).

        Minimiza el negativo del log-likelihood para la votación j,
        manteniendo fijos los puntos ideales y parámetros globales.
        """
        leg_idx = vote_leg_indices[j]
        if len(leg_idx) == 0:
            return params_j

        x_i = coordinates[leg_idx]  # shape (n_obs_j, dims)
        v_ij = vote_matrix[leg_idx, j]  # shape (n_obs_j,)

        dims = coordinates.shape[1]

        # Pesos por dimensión
        dim_weights = np.ones(dims)
        if dims > 1:
            dim_weights[1:] = w

        def neg_ll(p_flat: np.ndarray) -> float:
            O_j = p_flat[:dims]
            P_j = p_flat[dims:]

            yea_pole = O_j + P_j
            nay_pole = O_j - P_j

            diff_yea = x_i - yea_pole[np.newaxis, :]
            diff_yea_w = diff_yea * dim_weights[np.newaxis, :]
            dist2_yea = (diff_yea_w**2).sum(axis=1)

            diff_nay = x_i - nay_pole[np.newaxis, :]
            diff_nay_w = diff_nay * dim_weights[np.newaxis, :]
            dist2_nay = (diff_nay_w**2).sum(axis=1)

            logit = beta * (np.exp(-dist2_yea) - np.exp(-dist2_nay))
            logit = np.clip(logit, -30, 30)

            p_yea = norm.cdf(logit)
            p_correct = np.where(v_ij == 1.0, p_yea, 1.0 - p_yea)

            # Clamp probabilidad mínima para evitar log(0)
            p_correct = np.clip(p_correct, _P_FLOOR, 1.0)

            return -np.sum(np.log(p_correct))

        result = minimize(neg_ll, params_j, method="Nelder-Mead", options=opt_opts)
        return result.x

    def _optimize_leg_i(coords_i: np.ndarray, i: int) -> np.ndarray:
        """Optimizar punto ideal del legislador i.

        Minimiza el negativo del log-likelihood para el legislador i,
        manteniendo fijos los parámetros de votación y globales.
        """
        ve_idx = leg_vote_indices[i]
        if len(ve_idx) == 0:
            return coords_i

        bill_p = bill_params[ve_idx]  # shape (n_obs_i, 2*dims)
        v_ij = vote_matrix[i, ve_idx]  # shape (n_obs_i,)

        dims = len(coords_i)
        dim_weights = np.ones(dims)
        if dims > 1:
            dim_weights[1:] = w

        def neg_ll(x_flat: np.ndarray) -> float:
            x_i = x_flat

            O_j = bill_p[:, :dims]
            P_j = bill_p[:, dims:]

            yea_pole = O_j + P_j
            nay_pole = O_j - P_j

            diff_yea = x_i[np.newaxis, :] - yea_pole
            diff_yea_w = diff_yea * dim_weights[np.newaxis, :]
            dist2_yea = (diff_yea_w**2).sum(axis=1)

            diff_nay = x_i[np.newaxis, :] - nay_pole
            diff_nay_w = diff_nay * dim_weights[np.newaxis, :]
            dist2_nay = (diff_nay_w**2).sum(axis=1)

            logit = beta * (np.exp(-dist2_yea) - np.exp(-dist2_nay))
            logit = np.clip(logit, -30, 30)

            p_yea = norm.cdf(logit)
            p_correct = np.where(v_ij == 1.0, p_yea, 1.0 - p_yea)
            p_correct = np.clip(p_correct, _P_FLOOR, 1.0)

            ll = np.sum(np.log(p_correct))

            # Penalización por salir del hipercubo unitario
            if np.sum(x_flat**2) > 1.0:
                ll -= 1e300

            return -ll

        result = minimize(neg_ll, coords_i, method="Nelder-Mead", options=opt_opts)
        return result.x

    def _optimize_globals(
        current_coords: np.ndarray,
        current_bill: np.ndarray,
    ) -> tuple[float, float]:
        """Optimizar parámetros globales (β, w).

        β > 0 (saliencia), 0 < w < 1 (peso dimensión 2+).
        """

        def neg_ll(params: np.ndarray) -> float:
            log_b = params[0]
            w_val = 1.0 / (1.0 + np.exp(-params[1]))  # sigmoid para w ∈ (0,1)

            # Bounds en espacio log(β): β ∈ (0, 30] → log(β) ∈ (-inf, log(30)]
            if log_b > np.log(30.0):
                return 1e300

            b_val = np.exp(log_b)

            p_correct = _compute_prob_correct_vec(
                current_coords, current_bill, b_val, w_val, vote_matrix, obs_mask
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                log_p = np.log(np.clip(p_correct, _P_FLOOR, 1.0))
            valid_ll = np.where(obs_mask, log_p, 0.0)
            return -valid_ll.sum()

        # Opciones de optimización más estrictas para parámetros globales
        global_opt_opts = {"maxiter": 500, "xatol": 1e-5, "fatol": 1e-5}

        # Parametrización: log(β) para β > 0, logit sin restringir para w
        initial_b = np.log(beta)
        initial_w_logit = np.log(w / (1.0 - w))
        x0 = np.array([initial_b, initial_w_logit])

        result = minimize(neg_ll, x0, method="Nelder-Mead", options=global_opt_opts)

        opt_beta = np.exp(result.x[0])
        opt_w = 1.0 / (1.0 + np.exp(-result.x[1]))

        return opt_beta, opt_w

    # ------------------------------------------------------------------
    # 6. Ciclo principal alternante
    # ------------------------------------------------------------------
    prev_ll = -np.inf
    converged = False
    pool: ProcessPoolExecutor | None = None

    if use_parallel:
        pool = ProcessPoolExecutor(max_workers=n_workers)

    try:
        for iteration in range(1, maxiter + 1):
            # --- Paso a: Optimizar parámetros de cada votación ---
            if use_parallel and pool is not None:
                tasks = []
                for j in range(n_votes):
                    leg_idx = vote_leg_indices[j]
                    tasks.append(
                        (
                            j,
                            bill_params[j].copy(),
                            coordinates[leg_idx].copy(),
                            vote_matrix[leg_idx, j].copy(),
                            beta,
                            w,
                            dimensions,
                            opt_opts,
                        )
                    )
                chunksize = max(1, len(tasks) // (n_workers * 4))
                for j, new_p in pool.map(_bill_worker, tasks, chunksize=chunksize):
                    bill_params[j] = new_p
            else:
                for j in range(n_votes):
                    bill_params[j] = _optimize_bill_j(bill_params[j], j)

            # --- Paso b: Optimizar puntos ideales de cada legislador ---
            if use_parallel and pool is not None:
                tasks = []
                for i in range(n_legs):
                    ve_idx = leg_vote_indices[i]
                    tasks.append(
                        (
                            i,
                            coordinates[i].copy(),
                            bill_params[ve_idx].copy(),
                            vote_matrix[i, ve_idx].copy(),
                            beta,
                            w,
                            dimensions,
                            opt_opts,
                        )
                    )
                chunksize = max(1, len(tasks) // (n_workers * 4))
                for i, new_c in pool.map(_leg_worker, tasks, chunksize=chunksize):
                    coordinates[i] = new_c
            else:
                for i in range(n_legs):
                    coordinates[i] = _optimize_leg_i(coordinates[i], i)

            # --- Paso c: Optimizar parámetros globales ---
            beta, w = _optimize_globals(coordinates, bill_params)

            # --- Calcular log-likelihood ---
            current_ll = _total_log_likelihood(coordinates, bill_params, beta, w)

            # --- Métricas parciales ---
            fit_stats = _compute_fit_statistics_impl(
                coordinates, bill_params, vote_matrix, beta, w, dimensions, obs_mask
            )

            logger.info(
                "Iteración %d/%d: LL=%.2f, β=%.3f, w=%.3f, class_rate=%.2f%%, APRE=%.4f",
                iteration,
                maxiter,
                current_ll,
                beta,
                w,
                fit_stats["classification_rate"] * 100,
                fit_stats["apre"],
            )

            # --- Verificar convergencia ---
            if iteration > 1 and np.isfinite(current_ll) and np.isfinite(prev_ll):
                if abs(current_ll - prev_ll) < tol:
                    converged = True
                    logger.info(
                        "Convergencia alcanzada en iteración %d (ΔLL=%.6f < tol=%.6f)",
                        iteration,
                        abs(current_ll - prev_ll),
                        tol,
                    )
                    break

            prev_ll = current_ll
    finally:
        if pool is not None:
            pool.shutdown(wait=True)

    if not converged:
        delta = (
            abs(current_ll - prev_ll)
            if np.isfinite(current_ll) and np.isfinite(prev_ll)
            else float("inf")
        )
        logger.info(
            "No convergió después de %d iteraciones (ΔLL=%.6f)",
            maxiter,
            delta,
        )

    # ------------------------------------------------------------------
    # 7. Calcular métricas de ajuste finales
    # ------------------------------------------------------------------
    fit = compute_fit_statistics(coordinates, bill_params, vote_matrix, beta, w, dimensions)

    return {
        "coordinates": coordinates,
        "legislators": vote_data["legislators"],
        "legislator_names": vote_data["legislator_names"],
        "legislator_parties": vote_data["legislator_parties"],
        "org_map": vote_data["org_map"],
        "bill_parameters": bill_params,
        "vote_events": vote_data["vote_events"],
        "beta": beta,
        "w": w,
        "dimensions": dimensions,
        "fit": fit,
        "n_iterations": iteration if not converged else iteration,
        "converged": converged,
    }


# ---------------------------------------------------------------------------
# Función 3: compute_fit_statistics
# ---------------------------------------------------------------------------
def compute_fit_statistics(
    coordinates: np.ndarray,
    bill_parameters: np.ndarray,
    vote_matrix: np.ndarray,
    beta: float,
    w: float,
    dimensions: int | None = None,
) -> dict:
    """Calcular métricas de calidad del modelo W-NOMINATE.

    Métricas calculadas:
        - **Classification rate**: porcentaje de votos correctamente
          clasificados (P(Yea) > 0.5 cuando voto=1, etc.).
        - **APRE** (Aggregate Proportional Reduction in Error):
          1 - (errores_modelo / errores_null). El modelo nulo predice
          siempre la opción mayoritaria por votación.
        - **GMP** (Geometric Mean Probability):
          exp(log_likelihood / n_total_votes) — probabilidad geométrica media.
        - **Log-likelihood**: Σ log P(voto correcto).

    Args:
        coordinates: Puntos ideales, shape (n_legislators, dims).
        bill_parameters: Parámetros de votación, shape (n_votes, 2*dims).
        vote_matrix: Matriz binaria (1/0/NaN), shape (n_legs, n_votes).
        beta: Parámetro de saliencia.
        w: Peso de la 2da dimensión.
        dimensions: Número de dimensiones (inferido si es None).

    Returns:
        Diccionario con classification_rate, apre, gmp, log_likelihood,
        n_total_votes, n_correct.
    """
    if dimensions is None:
        dimensions = coordinates.shape[1]

    obs_mask = ~np.isnan(vote_matrix)

    return _compute_fit_statistics_impl(
        coordinates, bill_parameters, vote_matrix, beta, w, dimensions, obs_mask
    )


def _compute_fit_statistics_impl(
    coordinates: np.ndarray,
    bill_parameters: np.ndarray,
    vote_matrix: np.ndarray,
    beta: float,
    w: float,
    dimensions: int,
    obs_mask: np.ndarray,
) -> dict:
    """Implementación interna de métricas de ajuste.

    Separada de la pública para poder reutilizarse durante las iteraciones
    sin recalcular la máscara.
    """
    n_legs, n_votes = vote_matrix.shape
    dims = dimensions

    # Pesos por dimensión
    dim_weights = np.ones(dims)
    if dims > 1:
        dim_weights[1:] = w

    O_j = bill_parameters[:, :dims]
    P_j = bill_parameters[:, dims:]

    # --- Calcular probabilidades vectorizadas ---
    yea_pole = O_j + P_j
    nay_pole = O_j - P_j

    diff_yea = coordinates[:, np.newaxis, :] - yea_pole[np.newaxis, :, :]
    diff_yea_w = diff_yea * dim_weights[np.newaxis, np.newaxis, :]
    dist2_yea = (diff_yea_w**2).sum(axis=2)

    diff_nay = coordinates[:, np.newaxis, :] - nay_pole[np.newaxis, :, :]
    diff_nay_w = diff_nay * dim_weights[np.newaxis, np.newaxis, :]
    dist2_nay = (diff_nay_w**2).sum(axis=2)

    logit = beta * (np.exp(-dist2_yea) - np.exp(-dist2_nay))
    logit = np.clip(logit, -30, 30)

    p_yea = norm.cdf(logit)

    # --- Classification rate ---
    predicted_yea = (p_yea > 0.5).astype(float)
    actual_yea = np.nan_to_num(vote_matrix, nan=-1.0)

    # Solo donde hay observación
    correct = (predicted_yea == actual_yea) & obs_mask
    n_total = obs_mask.sum()
    n_correct = correct.sum()
    class_rate = n_correct / n_total if n_total > 0 else 0.0

    # --- Modelo nulo (predicción mayoritaria por votación) ---
    # Para cada votación, predecir la opción mayoritaria
    vote_values = np.where(obs_mask, vote_matrix, np.nan)
    with np.errstate(all="ignore"):
        yea_counts = np.nansum(vote_values == 1.0, axis=0)
        nay_counts = np.nansum(vote_values == 0.0, axis=0)
        majority_is_yea = yea_counts >= nay_counts

    # Errores del modelo nulo
    null_errors = 0
    for j in range(n_votes):
        if not obs_mask[:, j].any():
            continue
        majority_pred = 1.0 if majority_is_yea[j] else 0.0
        actual_j = vote_matrix[obs_mask[:, j], j]
        null_errors += (actual_j != majority_pred).sum()

    model_errors = n_total - n_correct

    # APRE: 1 - (errores_modelo / errores_null)
    apre = 1.0 - (model_errors / null_errors) if null_errors > 0 else 0.0

    # --- Log-likelihood y GMP ---
    p_correct = np.where(vote_matrix == 1.0, p_yea, 1.0 - p_yea)
    p_correct = np.where(obs_mask, p_correct, np.nan)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_p = np.log(np.clip(p_correct, _P_FLOOR, 1.0))
    valid_ll = np.where(obs_mask, log_p, 0.0)
    total_ll = valid_ll.sum()

    # GMP: exp(LL / n)
    gmp = np.exp(total_ll / n_total) if n_total > 0 else 0.0

    return {
        "classification_rate": float(class_rate),
        "apre": float(apre),
        "gmp": float(gmp),
        "log_likelihood": float(total_ll),
        "n_total_votes": int(n_total),
        "n_correct": int(n_correct),
    }


# ---------------------------------------------------------------------------
# Función 4: nominate_by_legislatura
# ---------------------------------------------------------------------------
def nominate_by_legislatura(
    db_path: str,
    dimensions: int = 2,
    min_votes: int = 10,
    lopsided_threshold: float = 0.975,
) -> dict:
    """Ejecutar W-NOMINATE para cada legislatura individualmente.

    Obtiene la lista de legislaturas con vote_events en la BD y ejecuta
    ``prepare_vote_matrix`` → ``run_wnominate`` para cada una.

    Args:
        db_path: Ruta al archivo SQLite.
        dimensions: Número de dimensiones del espacio.
        min_votes: Mínimo de votos binarios por legislador.

    Returns:
        Dict con clave = legislatura (ej: ``'LXVI'``) y valor = resultado
        de ``run_wnominate``. Legislaturas sin datos suficientes se omiten
        con un warning en el log.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        legs_df = pd.read_sql_query(
            "SELECT DISTINCT legislatura FROM vote_event "
            "WHERE legislatura IS NOT NULL ORDER BY legislatura",
            conn,
        )
    finally:
        conn.close()

    legislaturas = legs_df["legislatura"].tolist()
    resultados: dict[str, dict] = {}

    for leg in legislaturas:
        logger.info("Procesando legislatura %s", leg)
        try:
            data = prepare_vote_matrix(
                db_path,
                legislatura=leg,
                min_votes=min_votes,
                lopsided_threshold=lopsided_threshold,
            )
            resultado = run_wnominate(data, dimensions=dimensions, seed=_SEED)
            resultados[leg] = resultado
            logger.info(
                "Legislatura %s completada: %d legisladores, %d votaciones, class_rate=%.2f%%",
                leg,
                data["n_legislators"],
                data["n_votes"],
                resultado["fit"]["classification_rate"] * 100,
            )
        except ValueError as e:
            logger.warning("Legislatura %s omitida (datos insuficientes): %s", leg, e)

    logger.info(
        "Procesamiento por legislatura completado: %d de %d exitosas",
        len(resultados),
        len(legislaturas),
    )

    return resultados


# ---------------------------------------------------------------------------
# Función 5: nominate_cross_legislatura
# ---------------------------------------------------------------------------
def nominate_cross_legislatura(
    db_path: str,
    dimensions: int = 2,
    min_votes: int = 10,
    lopsided_threshold: float = 0.975,
) -> dict:
    """Ejecutar W-NOMINATE con todos los datos combinados (estilo DW-NOMINATE).

    Carga todas las legislaturas sin filtro, construye una sola matriz
    grande y ejecuta W-NOMINATE. Esto produce coordenadas comparables
    entre legislaturas (versión simplificada de DW-NOMINATE).

    Args:
        db_path: Ruta al archivo SQLite.
        dimensions: Número de dimensiones del espacio.
        min_votes: Mínimo de votos binarios por legislador.

    Returns:
        Resultado de ``run_wnominate`` con campo adicional
        ``'legislatura_labels'``: dict voter_id → legislatura principal
        (la legislatura donde más votó).
    """
    # Cargar todos los datos
    data = prepare_vote_matrix(
        db_path,
        legislatura=None,
        min_votes=min_votes,
        lopsided_threshold=lopsided_threshold,
    )

    # Ejecutar NOMINATE
    resultado = run_wnominate(data, dimensions=dimensions, seed=_SEED)

    # Determinar legislatura principal de cada legislador
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        # Obtener la legislatura principal por votación
        leg_labels_query = """
            SELECT v.voter_id, ve.legislatura, COUNT(*) as n
            FROM vote v
            JOIN vote_event ve ON v.vote_event_id = ve.id
            WHERE v.voter_id IN ({})
            GROUP BY v.voter_id, ve.legislatura
        """.format(",".join(["?"] * len(data["legislators"])))
        leg_df = pd.read_sql_query(leg_labels_query, conn, params=data["legislators"])
    finally:
        conn.close()

    # Para cada legislador, quedarse con la legislatura con más votos
    legislatura_labels: dict[str, str] = {}
    for voter_id, group in leg_df.groupby("voter_id"):
        best = group.loc[group["n"].idxmax()]
        legislatura_labels[voter_id] = best["legislatura"]

    resultado["legislatura_labels"] = legislatura_labels

    logger.info(
        "NOMINATE cross-legislatura completado: %d legisladores, %d votaciones, class_rate=%.2f%%",
        data["n_legislators"],
        data["n_votes"],
        resultado["fit"]["classification_rate"] * 100,
    )

    return resultado
