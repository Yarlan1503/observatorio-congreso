"""
poder_partidos.py — Índices de Poder Shapley-Shubik y Banzhaf
Observatorio del Congreso de la Unión (LXVI Legislature)

Calcula índices de poder legislativo para cada partido basándose en:
- Shapley-Shubik: poder marginal promedio en todas las permutaciones
- Banzhaf: poder crítico en todas las coaliciones

Soporta análisis por cámara (Diputados o Senado).

Uso:
    python3 analysis/poder_partidos.py
    python3 analysis/poder_partidos.py --camara senado --output-dir analysis/analisis-senado/output
"""

import itertools
import logging
import math
from pathlib import Path

import pandas as pd

from analysis.db import DEFAULT_DB_PATH as DB_PATH
from analysis.db import get_connection

logger = logging.getLogger(__name__)

from analysis.constants import CAMARA_MAP
from db.constants import _NAME_TO_ORG, _ORG_ID_TO_NAME, _PARTY_ORG_IDS, init_constants_from_db

OUTPUT_DIR = Path(__file__).parent / "analisis-diputados/output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Alias para compatibilidad interna
GROUP_TO_ORG = _NAME_TO_ORG
ORG_SHORT_NAME = _ORG_ID_TO_NAME
PARTY_ORGS = set(_PARTY_ORG_IDS)


# --- Funciones de datos ---


def get_party_name(conn, org_id: str) -> str:
    """Retorna nombre corto del partido."""
    return ORG_SHORT_NAME.get(org_id, org_id)


def get_seats_per_party(conn, rol: str = "diputado") -> dict:
    """
    Retorna {org_id: seat_count} con personas únicas asignadas a un solo partido.

    Estrategia:
    1. Obtener todas las memberships a partidos (clasificacion='partido').
    2. Para personas con multi-membership a partidos distintos:
       a. Contar votos normalizados por org_id en la tabla vote.
       b. Asignar al org_id donde más votos tiene.
       c. Si empate o sin votos, usar la membership con start_date más reciente.
    3. Para personas con memberships duplicadas al mismo partido: contar una sola vez.

    Args:
        conn: Conexión SQLite.
        rol: Filtrar por rol ('diputado' o 'senador').
    """
    cur = conn.cursor()

    # Obtener org_ids de partidos dinámicamente
    cur.execute("SELECT id FROM organization WHERE clasificacion = 'partido'")
    party_org_ids = [row[0] for row in cur.fetchall()]
    party_placeholders = ",".join(["?"] * len(party_org_ids))

    # Paso 1: Obtener todas las memberships a partidos
    cur.execute(
        f"""
        SELECT person_id, org_id, start_date
        FROM membership
        WHERE org_id IN ({party_placeholders})
        AND rol = ?
        ORDER BY person_id, org_id
        """,
        (*party_org_ids, rol),
    )
    rows = cur.fetchall()

    # Construir diccionario: person_id -> set de org_ids únicos
    person_orgs = {}
    person_dates = {}  # person_id -> {org_id: start_date}
    for person_id, org_id, start_date in rows:
        if person_id not in person_orgs:
            person_orgs[person_id] = set()
            person_dates[person_id] = {}
        person_orgs[person_id].add(org_id)
        # Guardar la fecha más reciente por org_id (puede haber múltiples memberships)
        if org_id not in person_dates[person_id] or (start_date or "") > (
            person_dates[person_id].get(org_id) or ""
        ):
            person_dates[person_id][org_id] = start_date

    # Paso 2: Obtener patrones de voto por persona
    # Normalizar group a org_id
    cur.execute(
        """
        SELECT voter_id, "group", COUNT(*) as cnt
        FROM vote
        WHERE "group" IS NOT NULL
        GROUP BY voter_id, "group"
        """
    )
    vote_rows = cur.fetchall()

    person_votes = {}  # person_id -> {org_id: count}
    for voter_id, group, cnt in vote_rows:
        org_id = GROUP_TO_ORG.get(group)
        if org_id is None:
            continue
        if voter_id not in person_votes:
            person_votes[voter_id] = {}
        person_votes[voter_id][org_id] = person_votes[voter_id].get(org_id, 0) + cnt

    # Paso 3: Asignar cada persona a un solo partido
    person_assignment = {}

    for person_id, orgs in person_orgs.items():
        if len(orgs) == 1:
            # Caso simple: una sola membresía
            person_assignment[person_id] = next(iter(orgs))
        else:
            # Multi-membership: usar votos para desambiguar
            votes = person_votes.get(person_id, {})
            # Filtrar votos solo a los orgs donde tiene membresía
            relevant_votes = {org: votes.get(org, 0) for org in orgs}

            max_votes = max(relevant_votes.values())
            if max_votes > 0:
                # Asignar al org con más votos
                best_orgs = [org for org, cnt in relevant_votes.items() if cnt == max_votes]
                if len(best_orgs) == 1:
                    person_assignment[person_id] = best_orgs[0]
                else:
                    # Empate: usar start_date más reciente
                    best_date = ""
                    best_org = best_orgs[0]
                    for org in best_orgs:
                        d = person_dates[person_id].get(org) or ""
                        if d > best_date:
                            best_date = d
                            best_org = org
                    person_assignment[person_id] = best_org
            else:
                # Sin votos: usar start_date más reciente
                best_date = ""
                best_org = next(iter(orgs))
                for org in orgs:
                    d = person_dates[person_id].get(org) or ""
                    if d > best_date:
                        best_date = d
                        best_org = org
                person_assignment[person_id] = best_org

    # Paso 4: Contar escaños por partido
    seats = {}
    for person_id, org_id in person_assignment.items():
        seats[org_id] = seats.get(org_id, 0) + 1

    return seats


# --- Algoritmos de poder ---


def shapley_shubik(weights: dict, quota: int) -> dict:
    """
    Calcula el índice Shapley-Shubik usando programación dinámica O(n²W).

    weights: {player_id: weight}
    quota: umbral para ganar

    Returns: {player_id: float} donde la suma = 1.0

    Algoritmo DP: Para cada jugador i, computa dp[s][w] = número de
    subconjuntos de tamaño s con peso total w usando todos los jugadores
    excepto i. El índice SS_i es:

        SS_i = Σ_{s,w: w < quota, w + w_i >= quota}
               dp_i[s][w] * s! * (n-1-s)! / n!

    Complejidad: O(n²W) donde n = jugadores, W = quota.
    Con 13 partidos y quota ~1951, son ~330K operaciones por jugador.
    """
    players = list(weights.keys())
    n = len(players)
    n_fact = math.factorial(n)
    max_w = quota - 1

    result = {}

    for player_i in players:
        w_i = weights[player_i]

        # DP: dp[s][w] = número de subconjuntos de tamaño s con peso w
        # usando jugadores distintos de player_i
        dp = [[0] * (max_w + 1) for _ in range(n)]
        dp[0][0] = 1

        for p in players:
            if p == player_i:
                continue
            w_j = weights[p]
            for s in range(n - 2, -1, -1):
                for w in range(max_w - w_j, -1, -1):
                    if dp[s][w]:
                        dp[s + 1][w + w_j] += dp[s][w]

        # Sumar contribuciones donde player_i es pivotal:
        # w < quota Y w + w_i >= quota
        phi_i = 0
        w_min = max(0, quota - w_i)
        for s in range(n):
            s_fact = math.factorial(s)
            rest_fact = math.factorial(n - 1 - s)
            for w in range(w_min, quota):
                if dp[s][w]:
                    phi_i += dp[s][w] * s_fact * rest_fact

        result[player_i] = phi_i / n_fact

    return result


def banzhaf(weights: dict, quota: int) -> dict:
    """
    Calcula el índice Banzhaf normalizado.

    weights: {player_id: weight}
    quota: umbral para ganar

    Returns: {player_id: float} donde la suma = 1.0

    Algoritmo: Para cada coalición (subconjunto de jugadores):
    - Una coalición es "ganadora" si la suma de pesos >= quota
    - Un jugador es "crítico" en una coalición si:
      - La coalición ES ganadora, PERO deja de serlo si ese jugador sale
    - Índice = veces crítico para jugador / total veces crítico para todos

    Con 8 jugadores, 2^8 = 256 coaliciones — trivial.
    """
    players = list(weights.keys())
    critical_count = {p: 0 for p in players}

    # Iterar sobre todos los subconjuntos (coaliciones)
    for r in range(len(players) + 1):
        for coalition in itertools.combinations(players, r):
            coalition_set = set(coalition)
            coalition_weight = sum(weights[p] for p in coalition)

            if coalition_weight >= quota:
                # Coalición ganadora: verificar quién es crítico
                for player in coalition:
                    weight_without = coalition_weight - weights[player]
                    if weight_without < quota:
                        critical_count[player] += 1

    total_critical = sum(critical_count.values())

    if total_critical == 0:
        # Ningún jugador es crítico (ej: umbral demasiado alto)
        return {p: 0.0 for p in players}

    return {p: critical_count[p] / total_critical for p in players}


# --- Presentación ---


def print_tabla_completa(
    df: pd.DataFrame, seats: dict, total_seats: int, camara_label: str = "Cámara de Diputados"
):
    """Imprime la tabla completa de resultados con formato legible."""

    logger.info("=" * 100)
    logger.info("ÍNDICES DE PODER LEGISLATIVO — LXVI LEGISLATURA, %s", camara_label.upper())
    logger.info("=" * 100)

    # Tabla de escaños
    logger.info("")
    logger.info("%s", f"{'ESCAÑOS POR PARTIDO':^100}")
    logger.info("-" * 60)
    logger.info("%-18s %-8s %8s %12s", "Partido", "Org_ID", "Escaños", "Nominal %")
    logger.info("-" * 60)

    # Ordenar por escaños descendente
    sorted_seats = sorted(seats.items(), key=lambda x: x[1], reverse=True)
    for org_id, seat_count in sorted_seats:
        name = ORG_SHORT_NAME.get(org_id, org_id)
        pct = seat_count / total_seats * 100
        logger.info("%-18s %-8s %8d %11.2f%%", name, org_id, seat_count, pct)

    logger.info("-" * 60)
    logger.info("%-18s %-8s %8d %12s", "TOTAL", "", total_seats, "100.00%")
    logger.info("")

    # Umbrales
    thresholds = df["Umbral"].unique()

    for threshold_name in thresholds:
        mask = df["Umbral"] == threshold_name
        sub = df[mask].sort_values("Escaños", ascending=False)

        logger.info("")
        logger.info("%s", f"{'UMBRAL: ' + threshold_name.upper():^100}")
        logger.info("-" * 100)
        logger.info(
            "%-18s %8s %12s %18s %12s %10s %10s",
            "Partido",
            "Escaños",
            "Nominal %",
            "Shapley-Shubik %",
            "Banzhaf %",
            "SS/Nom",
            "BZ/Nom",
        )
        logger.info("-" * 100)

        for _, row in sub.iterrows():
            nominal = row["Nominal_%"]
            ss = row["Shapley_Shubik_%"]
            bz = row["Banzhaf_%"]
            ss_ratio = ss / nominal if nominal > 0 else 0
            bz_ratio = bz / nominal if nominal > 0 else 0
            logger.info(
                "%-18s %8d %11.2f%% %17.2f%% %11.2f%% %9.2fx %9.2fx",
                row["Partido"],
                row["Escaños"],
                nominal,
                ss,
                bz,
                ss_ratio,
                bz_ratio,
            )

        logger.info("-" * 100)
        ss_sum = sub["Shapley_Shubik_%"].sum()
        bz_sum = sub["Banzhaf_%"].sum()
        nom_sum = sub["Nominal_%"].sum()
        seats_sum = sub["Escaños"].sum()
        logger.info(
            "%-18s %8d %11.2f%% %17.2f%% %11.2f%%",
            "TOTAL",
            seats_sum,
            nom_sum,
            ss_sum,
            bz_sum,
        )
        logger.info("")

    # Análisis de coaliciones clave
    logger.info("")
    logger.info("%s", f"{'ANÁLISIS DE COALICIONES CLAVE':^100}")
    logger.info("=" * 100)
    _print_coalition_analysis(seats, total_seats)

    logger.info("")
    logger.info("Archivos CSV generados en: %s/", OUTPUT_DIR)
    logger.info("=" * 100)


def _print_coalition_analysis(seats: dict, total_seats: int):
    """Imprime análisis de coaliciones ganadoras por umbral."""

    simple_quota = math.floor(total_seats / 2) + 1
    calif_quota = math.ceil(2 / 3 * total_seats)
    tres_cuartos_quota = math.ceil(3 / 4 * total_seats)

    thresholds = {
        f"Simple ({simple_quota}/{total_seats})": simple_quota,
        f"Calificada 2/3 ({calif_quota}/{total_seats})": calif_quota,
        f"3/4 ({tres_cuartos_quota}/{total_seats})": tres_cuartos_quota,
    }

    # Coaliciones conocidas
    coalitions = {
        "Sigamos Haciendo Historia (Morena+PT+PVEM)": ["O01", "O02", "O03"],
        "Morena + PT": ["O01", "O02"],
        "Morena + PVEM": ["O01", "O03"],
        "PT + PVEM": ["O02", "O03"],
        "Oposición (PAN+PRI+MC+PRD)": ["O04", "O05", "O06", "O07"],
        "PAN + PRI": ["O04", "O05"],
        "PAN + MC": ["O04", "O06"],
    }

    logger.info("%-45s %8s %8s %8s %8s %8s", "Coalición", "Escaños", "%", "Simple", "2/3", "3/4")
    logger.info("-" * 95)

    for coal_name, org_ids in coalitions.items():
        coal_seats = sum(seats.get(org, 0) for org in org_ids)
        coal_pct = coal_seats / total_seats * 100

        simple = "✓" if coal_seats >= simple_quota else "✗"
        calif = "✓" if coal_seats >= calif_quota else "✗"
        tres_cuartos = "✓" if coal_seats >= tres_cuartos_quota else "✗"

        logger.info(
            "%-45s %8d %7.1f%% %8s %8s %8s",
            coal_name,
            coal_seats,
            coal_pct,
            simple,
            calif,
            tres_cuartos,
        )

    logger.info("")
    logger.info("%s", f"{'Nota: ✓ = alcanza el umbral, ✗ = no lo alcanza':^95}")
    logger.info(
        "%s",
        f"{'Los porcentajes redondeados pueden no sumar 100.00% (los índices exactos sí suman 1.0)':^95}",
    )


# --- Main ---


def main(camara: str = "D", output_dir: Path | None = None):
    """Ejecuta análisis de poder por partidos.

    Args:
        camara: 'D' para Diputados, 'S' para Senado.
        output_dir: Directorio de salida. Si None, usa el default.
    """
    global GROUP_TO_ORG, ORG_SHORT_NAME, PARTY_ORGS

    # Inicializar constantes desde la BD para mapeos correctos de partidos.
    init_constants_from_db(str(DB_PATH))
    import db.constants as _dbc

    GROUP_TO_ORG = _dbc._NAME_TO_ORG
    ORG_SHORT_NAME = _dbc._ORG_ID_TO_NAME
    PARTY_ORGS = set(_dbc._PARTY_ORG_IDS)

    rol = "diputado" if camara == "D" else "senador"
    camara_label = "Cámara de Diputados" if camara == "D" else "Senado de la República"
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection(DB_PATH)
    seats = get_seats_per_party(conn, rol=rol)

    total_seats = sum(seats.values())
    simple_quota = math.floor(total_seats / 2) + 1
    calif_quota = math.ceil(2 / 3 * total_seats)
    tres_cuartos_quota = math.ceil(3 / 4 * total_seats)

    thresholds = {
        f"Simple ({simple_quota}/{total_seats})": simple_quota,
        f"Calificada 2/3 ({calif_quota}/{total_seats})": calif_quota,
        f"3/4 ({tres_cuartos_quota}/{total_seats})": tres_cuartos_quota,
    }

    # Verificar total de escaños
    default_total = 500 if camara == "D" else 128
    logger.info("Total escaños computados: %d", total_seats)
    logger.info(
        "  (La %s tiene %d curules; el exceso refleja legisladores que "
        "sirvieron durante la legislatura pero fueron reemplazados)",
        camara_label,
        default_total,
    )
    logger.info(
        "  (Solo se cuentan memberships con rol='%s'; militantes del caso cero excluidos)", rol
    )

    # Verificar que los índices suman exactamente 1.0
    results = []
    for threshold_name, quota in thresholds.items():
        ss = shapley_shubik(seats, quota)
        bz = banzhaf(seats, quota)

        # Verificación interna: índices suman exactamente 1.0
        assert abs(sum(ss.values()) - 1.0) < 1e-10, (
            f"Shapley-Shubik no suma 1.0 para {threshold_name}: {sum(ss.values())}"
        )
        assert abs(sum(bz.values()) - 1.0) < 1e-10, (
            f"Banzhaf no suma 1.0 para {threshold_name}: {sum(bz.values())}"
        )

        for org_id, seat_count in seats.items():
            party_name = get_party_name(conn, org_id)
            nominal_pct = seat_count / total_seats * 100
            results.append(
                {
                    "Partido": party_name,
                    "Org_ID": org_id,
                    "Escaños": seat_count,
                    "Umbral": threshold_name,
                    "Nominal_%": round(nominal_pct, 2),
                    "Shapley_Shubik_%": round(ss.get(org_id, 0) * 100, 2),
                    "Banzhaf_%": round(bz.get(org_id, 0) * 100, 2),
                }
            )

    df = pd.DataFrame(results)

    # Guardar CSVs por umbral
    for threshold_name in thresholds:
        slug = threshold_name.split()[0].lower().replace("/", "")
        mask = df["Umbral"] == threshold_name
        df[mask].to_csv(out_dir / f"poder_{slug}.csv", index=False)

    # Tabla completa
    df.to_csv(out_dir / "poder_completo.csv", index=False)

    logger.info("")
    print_tabla_completa(df, seats, total_seats, camara_label=camara_label)

    conn.close()
    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Índices de poder Shapley-Shubik y Banzhaf")
    parser.add_argument(
        "--camara",
        choices=["diputados", "senado"],
        default="diputados",
        help="Cámara a analizar (default: diputados)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida (default: analysis/analisis-diputados/output)",
    )
    args = parser.parse_args()

    camara_code = CAMARA_MAP[args.camara]
    main(camara=camara_code, output_dir=args.output_dir)
