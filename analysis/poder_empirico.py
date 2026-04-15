"""
poder_empirico.py — Poder Observado en Votaciones Reales
Observatorio del Congreso de la Unión (LXVI Legislatura, Cámara de Diputados)

Analiza el poder real de cada partido basándose en votaciones nominales:
- Partidos críticos por votación (sin cuyo apoyo no se alcanzaba la mayoría)
- Índice de poder empírico (veces crítico / total votaciones)
- Comparación con poder nominal, Shapley-Shubik y Banzhaf
- Análisis específico de la Reforma Judicial (VE04/VE05)
- Votaciones cerradas y swing voters
- Top 10 disidentes (votaron diferente a su partido)

Uso: python3 analysis/poder_empirico.py
"""

import csv
import logging
import math
import os
from collections import defaultdict
from itertools import combinations

from analysis.db import get_connection

from analysis.config import (
    CLOSE_VOTES_THRESHOLD,
    REFORMA_JUDICIAL_VE_IDS,
    TOP_DISSENTERS_GLOBAL,
)
from analysis.constants import CAMARA_MAP
from db.constants import (
    _NAME_TO_ORG,
    _ORG_ID_TO_NAME,
    _PARTY_ORG_IDS,
    CAMARA_DIPUTADOS_ID,
    CAMARA_SENADO_ID,
    MIN_VOTES,
    TOTAL_SEATS,
    get_total_seats,
    init_constants_from_db,
)

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "congreso.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "analisis-diputados/output")

# --- Constantes ---

# Alias para compatibilidad interna (se refrescan en main() tras init_constants_from_db)
GROUP_TO_ORG = _NAME_TO_ORG
ORG_SHORT_NAME = _ORG_ID_TO_NAME
PARTY_ORGS = list(_PARTY_ORG_IDS)

# Total de asientos dinámico (se ajusta en main() según cámara)
_total_seats_for_analysis = TOTAL_SEATS


# --- Helpers ---


def normalize_group(group_val):
    """Normaliza vote.group a org_id. Retorna None si es None o desconocido."""
    if group_val is None:
        return None
    return GROUP_TO_ORG.get(group_val, group_val)


def get_org_name(org_id):
    """Retorna nombre corto del partido."""
    return ORG_SHORT_NAME.get(org_id, org_id)


def pct(value, total):
    """Calcula porcentaje de forma segura."""
    if total == 0:
        return 0.0
    return value / total * 100


# --- Datos ---


def get_vote_events_with_results(conn, camara: str | None = None):
    """Retorna lista de vote_event_ids con resultado.

    Args:
        conn: Conexión SQLite.
        camara: Si 'D', solo Diputados. Si 'S', solo Senado. Si None, todas.

    Returns:
        Lista de vote_event IDs ordenados.
    """
    cur = conn.cursor()
    if camara == "D":
        cur.execute(
            """
            SELECT id FROM vote_event
            WHERE result IS NOT NULL AND organization_id = ?
            ORDER BY id
        """,
            (CAMARA_DIPUTADOS_ID,),
        )
    elif camara == "S":
        cur.execute(
            """
            SELECT id FROM vote_event
            WHERE result IS NOT NULL AND organization_id = ?
            ORDER BY id
        """,
            (CAMARA_SENADO_ID,),
        )
    else:
        cur.execute("""
            SELECT id FROM vote_event
            WHERE result IS NOT NULL
            ORDER BY id
        """)
    return [row[0] for row in cur.fetchall()]


def get_requirement(conn, ve_id):
    """Retorna el tipo de mayoría requerida para una votación."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.requirement
        FROM vote_event ve
        JOIN motion m ON ve.motion_id = m.id
        WHERE ve.id = ?
    """,
        (ve_id,),
    )
    row = cur.fetchone()
    return row[0] if row else "mayoria_simple"


def _get_latest_legislatura(conn, camara: str) -> str | None:
    """Retorna la legislatura más reciente con datos sustanciales para una cámara.

    Filtra legislaturas con al menos 100 votos para evitar VEs de prueba
    (ej. caso cero) que contaminen los conteos de escaños.
    """
    org_id = CAMARA_DIPUTADOS_ID if camara == "D" else CAMARA_SENADO_ID
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ve.legislatura
        FROM vote_event ve
        JOIN vote v ON v.vote_event_id = ve.id
        WHERE ve.organization_id = ? AND ve.legislatura IS NOT NULL
        GROUP BY ve.legislatura
        HAVING COUNT(v.id) > 100
        ORDER BY ve.legislatura DESC
        LIMIT 1
    """,
        (org_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_seat_counts(conn, camara: str | None = None, legislatura: str | None = None):
    """
    Retorna {org_id: seat_count} con el máximo de votantes por partido
    en cualquier votación individual de la legislatura especificada.
    Proxy para escaños efectivos.

    Normaliza grupos (nombres vs IDs) ANTES de tomar el máximo,
    ya que VE01 usa nombres ('PT', 'PVEM') y VE03+ usa IDs ('O02', 'O03').

    Si no se especifica legislatura, usa la más reciente para la cámara dada.
    Esto evita escaños inflados al tomar el MAX entre legislaturas.

    Args:
        conn: Conexión SQLite.
        camara: Si 'D', filtra a Diputados. Si 'S', filtra a Senado.
        legislatura: Legislatura específica ('LXVI', 'LXIV', etc.).
            Si es None, usa la más reciente para la cámara.
    """
    # Determine legislatura: use latest for the given cámara if not specified
    effective_camara = camara or "D"
    if legislatura is None:
        legislatura = _get_latest_legislatura(conn, effective_camara)

    cur = conn.cursor()
    if camara == "D":
        cur.execute(
            """
            SELECT v.vote_event_id, v."group", COUNT(*) as cnt
            FROM vote v
            JOIN vote_event ve ON v.vote_event_id = ve.id
            WHERE v."group" IS NOT NULL AND ve.organization_id = 'O08'
            AND ve.legislatura = ?
            GROUP BY v.vote_event_id, v."group"
        """,
            (legislatura,),
        )
    elif camara == "S":
        cur.execute(
            """
            SELECT v.vote_event_id, v."group", COUNT(*) as cnt
            FROM vote v
            JOIN vote_event ve ON v.vote_event_id = ve.id
            WHERE v."group" IS NOT NULL AND ve.organization_id = 'O09'
            AND ve.legislatura = ?
            GROUP BY v.vote_event_id, v."group"
        """,
            (legislatura,),
        )
    else:
        # No camera filter — use legislatura if available
        if legislatura:
            cur.execute(
                """
                SELECT v.vote_event_id, v."group", COUNT(*) as cnt
                FROM vote v
                JOIN vote_event ve ON v.vote_event_id = ve.id
                WHERE v."group" IS NOT NULL AND ve.legislatura = ?
                GROUP BY v.vote_event_id, v."group"
            """,
                (legislatura,),
            )
        else:
            cur.execute(
                """
                SELECT vote_event_id, "group", COUNT(*) as cnt
                FROM vote
                WHERE "group" IS NOT NULL
                GROUP BY vote_event_id, "group"
            """
            )
    # Agrupar por org_id normalizado, tomando el máximo
    seats = {}
    for _, group_val, count in cur.fetchall():
        org = normalize_group(group_val)
        if org:
            seats[org] = max(seats.get(org, 0), count)
    return seats


def get_person_name(conn, person_id):
    """Retorna el nombre de una persona."""
    cur = conn.cursor()
    cur.execute("SELECT nombre FROM person WHERE id = ?", (person_id,))
    row = cur.fetchone()
    return row[0] if row else person_id


# --- Análisis central ---


def analyze_vote_event(conn, ve_id):
    """
    Analiza una votación individual.

    Returns: {
        'vote_event_id': str,
        'total_asistentes': int,
        'mayoria_necesaria': int,
        'a_favor_total': int,
        'en_contra_total': int,
        'abstencion_total': int,
        'ausente_total': int,
        'result': str,
        'requirement': str,
        'party_votes': {org_id: {'favor': int, 'contra': int, 'abstencion': int, 'ausente': int, 'total': int, 'position': str}},
        'critical_parties': [org_id, ...],
        'margin': int,
    }
    """
    cur = conn.cursor()
    requirement = get_requirement(conn, ve_id)

    # Obtener resultado
    cur.execute("SELECT result FROM vote_event WHERE id = ?", (ve_id,))
    result_row = cur.fetchone()
    result = result_row[0] if result_row else None

    # Obtener votos por partido
    cur.execute(
        """
        SELECT "group", option, COUNT(*) as cnt
        FROM vote
        WHERE vote_event_id = ?
        GROUP BY "group", option
        ORDER BY "group", option
    """,
        (ve_id,),
    )

    party_votes = {}
    a_favor_total = 0
    en_contra_total = 0
    abstencion_total = 0
    ausente_total = 0

    for group_val, option, cnt in cur.fetchall():
        org = normalize_group(group_val)
        if org is None:
            # Voto sin grupo (ej. independiente sin partido asignado)
            # Sumar a los totales generales
            if option == "a_favor":
                a_favor_total += cnt
            elif option == "en_contra":
                en_contra_total += cnt
            elif option == "abstencion":
                abstencion_total += cnt
            elif option == "ausente":
                ausente_total += cnt
            continue

        if org not in party_votes:
            party_votes[org] = {
                "favor": 0,
                "contra": 0,
                "abstencion": 0,
                "ausente": 0,
                "total": 0,
            }

        pv = party_votes[org]
        pv["total"] += cnt
        if option == "a_favor":
            pv["favor"] += cnt
            a_favor_total += cnt
        elif option == "en_contra":
            pv["contra"] += cnt
            en_contra_total += cnt
        elif option == "abstencion":
            pv["abstencion"] += cnt
            abstencion_total += cnt
        elif option == "ausente":
            pv["ausente"] += cnt
            ausente_total += cnt

    # Calcular asistentes y mayoría necesaria
    total_asistentes = a_favor_total + en_contra_total + abstencion_total

    if requirement == "mayoria_calificada":
        # 2/3 del total de la Cámara (500 Diputados / 128 Senado)
        mayoria_necesaria = math.ceil(2 / 3 * _total_seats_for_analysis)  # 334 o 86
    else:
        # Mayoría simple: ceil(asistentes / 2)
        mayoria_necesaria = math.ceil(total_asistentes / 2)

    # Determinar posición de cada partido
    for org, pv in party_votes.items():
        asistentes_partido = pv["favor"] + pv["contra"] + pv["abstencion"]
        if asistentes_partido == 0:
            pv["position"] = "ausente"
            continue

        # Posición = la opción con más votos entre los asistentes
        # >50% de asistentes a_favor → 'favor', >50% en_contra → 'contra', sino 'split'
        if pv["favor"] > asistentes_partido / 2:
            pv["position"] = "favor"
        elif pv["contra"] > asistentes_partido / 2:
            pv["position"] = "contra"
        else:
            pv["position"] = "split"

    # Encontrar partidos críticos
    critical = find_critical_parties(party_votes, mayoria_necesaria, result)

    # Margen
    if result == "aprobada":
        margin = a_favor_total - mayoria_necesaria
    else:
        margin = en_contra_total - mayoria_necesaria if mayoria_necesaria else 0

    return {
        "vote_event_id": ve_id,
        "total_asistentes": total_asistentes,
        "mayoria_necesaria": mayoria_necesaria,
        "a_favor_total": a_favor_total,
        "en_contra_total": en_contra_total,
        "abstencion_total": abstencion_total,
        "ausente_total": ausente_total,
        "result": result,
        "requirement": requirement,
        "party_votes": party_votes,
        "critical_parties": critical,
        "margin": margin,
    }


def find_critical_parties(party_votes, majority, result):
    """
    Encuentra qué partidos fueron críticos para el resultado.

    Un partido es crítico si, sin sus votos a_favor (o en_contra),
    la coalición ganadora habría perdido.

    Si aprobada: sin los a_favor del partido, a_favor_total - partido_favor < mayoría
    Si rechazada: sin los en_contra del partido, en_contra_total - partido_contra < mayoría
    """
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

    return sorted(critical)


# --- Índice de poder empírico ---


def calc_empirical_power(analyses):
    """
    Calcula el poder empírico de cada partido.

    poder_empirico = votaciones_donde_fue_critico / total_votaciones_con_resultado

    Returns: {org_id: float}
    """
    total = len(analyses)
    if total == 0:
        return {}

    critical_count = defaultdict(int)
    for analysis in analyses:
        for org in analysis["critical_parties"]:
            critical_count[org] += 1

    # Incluir todos los partidos que aparecieron en al menos una votación
    all_orgs = set()
    for analysis in analyses:
        all_orgs.update(analysis["party_votes"].keys())

    return {org: critical_count.get(org, 0) / total for org in sorted(all_orgs)}


# --- Índices teóricos de poder ---


def calc_shapley_shubik(weights, quota):
    """
    Calcula el índice Shapley-Shubik.

    Delega a la implementación O(n²W) de poder_partidos.shapley_shubik.
    Anteriormente usaba O(n!) con itertools.permutations — validado como
    numéricamente idéntico el 2025-04-15 (4 datasets, diff=0.0 en todos).

    weights: dict {player_id: weight} o list de weights
        Si es list, se convierte a {i: w for i, w in enumerate(weights)}.
    quota: int o list — umbral para coalición ganadora
        Si es list (votos por jugador), se deriva mayoría simple:
        sum(weights) // 2 + 1.

    Returns: {player_id: float} donde la suma = 1.0
    """
    from analysis.poder_partidos import shapley_shubik

    if isinstance(weights, list):
        weights = dict(enumerate(weights))

    if isinstance(quota, list):
        quota = sum(weights.values()) // 2 + 1

    return shapley_shubik(weights, quota)


def calc_banzhaf(weights, quota):
    """
    Calcula el índice Banzhaf normalizado.

    weights: {player_id: weight}
    quota: umbral para coalición ganadora

    Returns: {player_id: float} donde la suma = 1.0
    """
    players = list(weights.keys())
    critical_count = defaultdict(int)

    for r in range(len(players) + 1):
        for coalition in combinations(players, r):
            coalition_weight = sum(weights[p] for p in coalition)
            if coalition_weight >= quota:
                for player in coalition:
                    if coalition_weight - weights[player] < quota:
                        critical_count[player] += 1

    total_critical = sum(critical_count.values())
    if total_critical == 0:
        return {p: 0.0 for p in players}

    return {p: critical_count.get(p, 0) / total_critical for p in players}


# --- Tabla comparativa ---


def build_comparison_table(
    conn, empirical_power, camara: str | None = None, db_path: str = DB_PATH
):
    """
    Construye tabla comparativa: partido × nominal × shapley × banzhaf × empirico.

    Usa poder para mayoría simple (quota basada en total de asientos de la cámara).

    Args:
        conn: Conexión SQLite.
        empirical_power: Dict de poder empírico.
        camara: 'D' para Diputados, 'S' para Senado, None para default.
        db_path: Ruta a la BD para calcular asientos dinámicos.
    """
    seats = get_seat_counts(conn, camara=camara)

    # Solo partidos con escaños en votaciones
    active_seats = {org: cnt for org, cnt in seats.items() if cnt > 0}

    # Calcular total de asientos dinámicamente
    total_seats = get_total_seats(db_path, camara or "D")

    # Quota para mayoría simple: más de la mitad
    quota_simple = math.floor(total_seats / 2) + 1

    ss = calc_shapley_shubik(active_seats, quota_simple)
    bz = calc_banzhaf(active_seats, quota_simple)

    comparison = []
    for org in sorted(active_seats.keys(), key=lambda x: active_seats[x], reverse=True):
        seat_count = active_seats[org]
        nominal = seat_count / total_seats if total_seats > 0 else 0
        shapley = ss.get(org, 0)
        banzhaf_val = bz.get(org, 0)
        empirico = empirical_power.get(org, 0)

        comparison.append(
            {
                "org_id": org,
                "partido": get_org_name(org),
                "escanos": seat_count,
                "nominal": nominal,
                "shapley_shubik": shapley,
                "banzhaf": banzhaf_val,
                "empirico": empirico,
            }
        )

    return comparison, quota_simple, total_seats


# --- Análisis Reforma Judicial ---


def analyze_reforma_judicial(conn, ve_ids):
    """Análisis detallado de la Reforma Judicial (VE04 y VE05)."""
    results = []
    for ve_id in ve_ids:
        analysis = analyze_vote_event(conn, ve_id)
        results.append(analysis)
    return results


# --- Votaciones cerradas ---


def analyze_close_votes(conn, analyses, threshold=10):
    """
    Identifica votaciones cerradas (margen < threshold) y swing voters.

    Returns: {
        'close_votes': [{vote_event_id, margin, a_favor, en_contra, ...}],
        'swing_voters': [{vote_event_id, person_id, person_name, party, their_vote, party_position}]
    }
    """
    close = []
    for a in analyses:
        margin = abs(a["a_favor_total"] - a["en_contra_total"])
        if margin < threshold:
            close.append(
                {
                    "vote_event_id": a["vote_event_id"],
                    "margin": margin,
                    "a_favor": a["a_favor_total"],
                    "en_contra": a["en_contra_total"],
                    "abstencion": a["abstencion_total"],
                    "result": a["result"],
                    "requirement": a["requirement"],
                    "mayoria_necesaria": a["mayoria_necesaria"],
                    "critical_parties": a["critical_parties"],
                }
            )

    # Swing voters: en votaciones cerradas, personas que votaron diferente a su partido
    # y cuyo voto individual podría haber cambiado el resultado
    swing_voters = []
    for cv in close:
        ve_id = cv["vote_event_id"]
        a_favor_total = cv["a_favor"]
        en_contra_total = cv["en_contra"]
        majority = cv["mayoria_necesaria"]
        result = cv["result"]

        # Obtener posición de cada partido en esta votación
        analysis = next(a for a in analyses if a["vote_event_id"] == ve_id)
        party_positions = {}
        for org, pv in analysis["party_votes"].items():
            party_positions[org] = pv["position"]

        # Obtener votos individuales
        cur = conn.cursor()
        cur.execute(
            """
            SELECT voter_id, option, "group"
            FROM vote
            WHERE vote_event_id = ?
        """,
            (ve_id,),
        )

        for voter_id, option, group_val in cur.fetchall():
            org = normalize_group(group_val)
            if org is None:
                continue

            party_pos = party_positions.get(org, "split")
            if party_pos == "split" or party_pos == "ausente":
                continue

            # ¿Votó diferente a su partido?
            dissenting = False
            if (party_pos == "favor" and option != "a_favor") or (
                party_pos == "contra" and option != "en_contra"
            ):
                dissenting = True

            if not dissenting:
                continue

            # ¿Su voto individual podría haber cambiado el resultado?
            could_flip = False
            if result == "aprobada":
                # Si votaron a_favor y sin ellos no llegaban a la mayoría
                if option == "a_favor" and (a_favor_total - 1) < majority:
                    could_flip = True
                # Si votaron en_contra/abstencion y sumando su voto a_favor...
                # (no cambia el resultado ya que ganó a_favor)
            elif result == "rechazada":
                if option == "en_contra" and (en_contra_total - 1) < majority:
                    could_flip = True

            swing_voters.append(
                {
                    "vote_event_id": ve_id,
                    "person_id": voter_id,
                    "person_name": get_person_name(conn, voter_id),
                    "party": get_org_name(org),
                    "org_id": org,
                    "their_vote": option,
                    "party_position": party_pos,
                    "could_flip_result": could_flip,
                }
            )

    return {"close_votes": close, "swing_voters": swing_voters}


# --- Disidentes ---


def find_top_dissidents(conn, min_votes=MIN_VOTES, camara: str | None = None):
    """
    Encuentra los legisladores que más votaron diferente a su partido.

    Args:
        conn: Conexión SQLite.
        min_votes: Mínimo de votaciones para incluir un legislador.
        camara: Filtro de cámara ('D', 'S' o None).

    Returns: [(person_id, person_name, party, dissent_rate, total_votes, dissent_count)]
    """
    cur = conn.cursor()

    # Obtener votaciones con resultado
    ve_ids = get_vote_events_with_results(conn, camara=camara)

    # Para cada votación, obtener la posición mayoritaria de cada partido
    ve_party_positions = {}
    for ve_id in ve_ids:
        cur.execute(
            """
            SELECT "group", option, COUNT(*) as cnt
            FROM vote
            WHERE vote_event_id = ? AND "group" IS NOT NULL
            GROUP BY "group", option
        """,
            (ve_id,),
        )

        party_options = defaultdict(lambda: defaultdict(int))
        for group_val, option, cnt in cur.fetchall():
            org = normalize_group(group_val)
            if org:
                party_options[org][option] += cnt

        positions = {}
        for org, opts in party_options.items():
            asistentes = (
                opts.get("a_favor", 0) + opts.get("en_contra", 0) + opts.get("abstencion", 0)
            )
            if asistentes == 0:
                positions[org] = "ausente"
            elif opts.get("a_favor", 0) > asistentes / 2:
                positions[org] = "a_favor"
            elif opts.get("en_contra", 0) > asistentes / 2:
                positions[org] = "en_contra"
            else:
                positions[org] = "split"

        ve_party_positions[ve_id] = positions

    # Obtener todos los votos individuales en votaciones con resultado
    ve_placeholders = ",".join("?" for _ in ve_ids)
    cur.execute(
        f"""
        SELECT voter_id, vote_event_id, option, "group"
        FROM vote
        WHERE vote_event_id IN ({ve_placeholders})
    """,
        ve_ids,
    )

    # Contar disidencias por persona
    person_stats = defaultdict(lambda: {"total": 0, "dissent": 0, "party_counts": defaultdict(int)})

    for voter_id, ve_id, option, group_val in cur.fetchall():
        org = normalize_group(group_val)
        if org is None:
            continue

        person_stats[voter_id]["total"] += 1
        person_stats[voter_id]["party_counts"][org] += 1

        party_pos = ve_party_positions.get(ve_id, {}).get(org, "split")
        if party_pos == "split" or party_pos == "ausente":
            continue

        # ¿Votó diferente a su partido?
        if option != party_pos:
            person_stats[voter_id]["dissent"] += 1

    # Determinar partido principal de cada persona (el que más votos tiene)
    person_party = {}
    for person_id, stats in person_stats.items():
        if stats["party_counts"]:
            main_party = max(stats["party_counts"], key=stats["party_counts"].get)
            person_party[person_id] = main_party

    # Filtrar por mínimo de votaciones y calcular tasa de disidencia
    dissidents = []
    for person_id, stats in person_stats.items():
        if stats["total"] < min_votes:
            continue
        dissent_rate = stats["dissent"] / stats["total"]
        party = person_party.get(person_id, "???")
        dissidents.append(
            (
                person_id,
                get_person_name(conn, person_id),
                get_org_name(party),
                dissent_rate,
                stats["total"],
                stats["dissent"],
            )
        )

    # Ordenar por tasa de disidencia (desc), luego por votos de disidencia (desc)
    dissidents.sort(key=lambda x: (-x[3], -x[5]))

    return dissidents[:TOP_DISSENTERS_GLOBAL]


# --- Output ---


def save_results(
    comparison,
    reforma_analyses,
    dissidents,
    all_analyses,
    close_votes_analysis,
    output_dir=OUTPUT_DIR,
):
    """Guarda todos los resultados en CSVs.

    Args:
        output_dir: Directorio de salida. Default: OUTPUT_DIR global.
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. poder_empirico.csv
    with open(os.path.join(output_dir, "poder_empirico.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["partido", "org_id", "poder_empirico"])
        for row in comparison:
            writer.writerow([row["partido"], row["org_id"], f"{row['empirico']:.4f}"])

    # 2. comparacion_poder.csv
    with open(os.path.join(output_dir, "comparacion_poder.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "partido",
                "org_id",
                "escanos",
                "nominal_pct",
                "shapley_shubik_pct",
                "banzhaf_pct",
                "empirico_pct",
            ]
        )
        for row in comparison:
            writer.writerow(
                [
                    row["partido"],
                    row["org_id"],
                    row["escanos"],
                    f"{row['nominal'] * 100:.2f}",
                    f"{row['shapley_shubik'] * 100:.2f}",
                    f"{row['banzhaf'] * 100:.2f}",
                    f"{row['empirico'] * 100:.2f}",
                ]
            )

    # 3. votaciones_detalle.csv
    with open(os.path.join(output_dir, "votaciones_detalle.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "vote_event_id",
                "result",
                "requirement",
                "asistentes",
                "mayoria_necesaria",
                "a_favor",
                "en_contra",
                "abstencion",
                "ausente",
                "margin",
                "critical_parties",
                "critical_count",
            ]
        )
        for a in all_analyses:
            writer.writerow(
                [
                    a["vote_event_id"],
                    a["result"],
                    a["requirement"],
                    a["total_asistentes"],
                    a["mayoria_necesaria"],
                    a["a_favor_total"],
                    a["en_contra_total"],
                    a["abstencion_total"],
                    a["ausente_total"],
                    a["margin"],
                    "|".join(a["critical_parties"]),
                    len(a["critical_parties"]),
                ]
            )

    # 4. disidentes.csv
    with open(os.path.join(output_dir, "disidentes.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "person_id",
                "nombre",
                "partido",
                "disidencia_pct",
                "total_votaciones",
                "votos_disidentes",
            ]
        )
        for i, (pid, name, party, rate, total, dissent) in enumerate(dissidents, 1):
            writer.writerow([i, pid, name, party, f"{rate * 100:.1f}", total, dissent])

    # 5. reforma_judicial.csv
    with open(os.path.join(output_dir, "reforma_judicial.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "vote_event_id",
                "result",
                "requirement",
                "mayoria_necesaria",
                "a_favor_total",
                "en_contra_total",
                "ausente_total",
                "margin",
                "critical_parties",
            ]
        )
        for a in reforma_analyses:
            writer.writerow(
                [
                    a["vote_event_id"],
                    a["result"],
                    a["requirement"],
                    a["mayoria_necesaria"],
                    a["a_favor_total"],
                    a["en_contra_total"],
                    a["ausente_total"],
                    a["margin"],
                    "|".join(a["critical_parties"]),
                ]
            )
        # Añadir detalle por partido
        writer.writerow([])
        writer.writerow(["--- DESGLOSE POR PARTIDO ---"])
        writer.writerow(
            [
                "vote_event_id",
                "partido",
                "org_id",
                "a_favor",
                "en_contra",
                "abstencion",
                "ausente",
                "total",
                "posicion",
                "critico",
            ]
        )
        for a in reforma_analyses:
            for org in sorted(a["party_votes"].keys()):
                pv = a["party_votes"][org]
                is_critical = "SI" if org in a["critical_parties"] else "NO"
                writer.writerow(
                    [
                        a["vote_event_id"],
                        get_org_name(org),
                        org,
                        pv["favor"],
                        pv["contra"],
                        pv["abstencion"],
                        pv["ausente"],
                        pv["total"],
                        pv["position"],
                        is_critical,
                    ]
                )


def log_all_results(
    comparison,
    quota_simple,
    reforma_analyses,
    close_votes_analysis,
    dissidents,
    all_analyses,
    out_dir=OUTPUT_DIR,
):
    """Registra todos los resultados numéricos vía logging."""

    SEP = "=" * 100

    logger.info(SEP)
    logger.info("PODER EMPIRICO — Observatorio del Congreso de la Union")
    logger.info("LXVI Legislatura - Camara de Diputados")
    logger.info(SEP)

    # =========================================================================
    # 1. TABLA COMPARATIVA DE PODER
    # =========================================================================
    logger.info("")
    logger.info("1. TABLA COMPARATIVA DE PODER".center(100))
    quota_label = "(Quota mayoria simple = %d escaños)" % quota_simple
    logger.info(quota_label.center(100))
    logger.info("-" * 100)
    logger.info(
        "%-16s %8s %10s %12s %10s %10s %10s",
        "Partido",
        "Escaños",
        "Nominal",
        "Shapley-S",
        "Banzhaf",
        "Empírico",
        "Emp>Shap",
    )
    logger.info("-" * 100)

    for row in comparison:
        nom = row["nominal"] * 100
        ss = row["shapley_shubik"] * 100
        bz = row["banzhaf"] * 100
        emp = row["empirico"] * 100
        ratio = "%.1fx" % (emp / ss) if ss > 0 else "N/A"
        logger.info(
            "%-16s %8d %8.1f%% %10.1f%% %8.1f%% %8.1f%% %10s",
            row["partido"],
            row["escanos"],
            nom,
            ss,
            bz,
            emp,
            ratio,
        )

    logger.info("-" * 100)
    total_seats = sum(r["escanos"] for r in comparison)
    total_nom = sum(r["nominal"] for r in comparison) * 100
    total_ss = sum(r["shapley_shubik"] for r in comparison) * 100
    total_bz = sum(r["banzhaf"] for r in comparison) * 100
    total_emp = sum(r["empirico"] for r in comparison) * 100
    logger.info(
        "%-16s %8d %8.1f%% %10.1f%% %8.1f%% %8.1f%%",
        "TOTAL",
        total_seats,
        total_nom,
        total_ss,
        total_bz,
        total_emp,
    )

    # Interpretación
    logger.info("")
    logger.info("INTERPRETACION".center(100))
    logger.info("-" * 100)
    morena_row = next((r for r in comparison if r["org_id"] == "O01"), None)
    if morena_row:
        emp_morena = morena_row["empirico"] * 100
        ss_morena = morena_row["shapley_shubik"] * 100
        logger.info(
            "  Morena tiene %d escaños (%.1f%% de la Camara).",
            morena_row["escanos"],
            morena_row["nominal"] * 100,
        )
        logger.info(
            "  Shapley-Shubik = %.1f%%: con mayoria simple, Morena domina unilateralmente.",
            ss_morena,
        )
        logger.info(
            "  Poder empirico = %.1f%%: porcentaje de votaciones donde fue critica.",
            emp_morena,
        )
        logger.info(
            "  La diferencia entre poder teorico (%.1f%%) y empirico (%.1f%%)",
            ss_morena,
            emp_morena,
        )
        logger.info("  revela donde las coaliciones reales difieren del modelo de mayoria simple.")

    pt_row = next((r for r in comparison if r["org_id"] == "O02"), None)
    pvem_row = next((r for r in comparison if r["org_id"] == "O03"), None)
    if pt_row and pvem_row:
        logger.info(
            "  PT (%.1f%% empirico) y PVEM (%.1f%% empirico)",
            pt_row["empirico"] * 100,
            pvem_row["empirico"] * 100,
        )
        logger.info("  tienen 0%% de poder Shapley-Shubik para mayoria simple, pero su poder")
        logger.info("  empirico proviene de votaciones que requieren mayoria calificada (2/3).")

    # =========================================================================
    # 2. REFORMA JUDICIAL (VE04 / VE05)
    # =========================================================================
    logger.info("")
    logger.info(SEP)
    logger.info("2. REFORMA JUDICIAL (VE04 y VE05)".center(100))
    logger.info(SEP)

    for a in reforma_analyses:
        ve_id = a["vote_event_id"]
        logger.info("  %s", "─" * 90)
        result_display = (a["result"] or "N/A").upper()
        logger.info("  %s: %s — Requerimiento: %s", ve_id, result_display, a["requirement"])
        logger.info("  %s", "─" * 90)
        logger.info("  Mayoria necesaria (2/3 de 500): %d", a["mayoria_necesaria"])
        logger.info("  A favor:   %4d", a["a_favor_total"])
        logger.info("  En contra: %4d", a["en_contra_total"])
        logger.info("  Abstencion:%4d", a["abstencion_total"])
        logger.info("  Ausente:   %4d", a["ausente_total"])
        logger.info("  Margen:    %4d (a_favor - mayoria_necesaria)", a["margin"])

        logger.info("")
        logger.info("  Desglose por partido:")
        logger.info(
            "  %-16s %8s %10s %10s %8s %6s %10s %8s",
            "Partido",
            "A favor",
            "En contra",
            "Abstencion",
            "Ausente",
            "Total",
            "Posición",
            "Crítico",
        )
        logger.info("  %s", "─" * 88)

        for org in ["O01", "O02", "O03", "O04", "O05", "O06"]:
            if org in a["party_votes"]:
                pv = a["party_votes"][org]
                is_critical = "*** SI" if org in a["critical_parties"] else "NO"
                pos_display = pv["position"]
                logger.info(
                    "  %-16s %8d %10d %10d %8d %6d %10s %8s",
                    get_org_name(org),
                    pv["favor"],
                    pv["contra"],
                    pv["abstencion"],
                    pv["ausente"],
                    pv["total"],
                    pos_display,
                    is_critical,
                )

        # Coalición ganadora
        coleccion_favor = []
        for org in sorted(a["party_votes"].keys()):
            pv = a["party_votes"][org]
            if pv["favor"] > 0:
                coleccion_favor.append("%s(%d)" % (get_org_name(org), pv["favor"]))
        coalicion_str = " + ".join(coleccion_favor)
        logger.info("")
        logger.info("  Coalicion ganadora: %s = %d", coalicion_str, a["a_favor_total"])

        # Verificar criticidad
        logger.info(
            "  Partidos criticos (sin cuyo apoyo no se llegaba a %d):",
            a["mayoria_necesaria"],
        )
        for org in a["critical_parties"]:
            pv = a["party_votes"][org]
            remaining = a["a_favor_total"] - pv["favor"]
            logger.info(
                "    - %s: sin sus %d votos a favor → %d < %d → CRITICO",
                get_org_name(org),
                pv["favor"],
                remaining,
                a["mayoria_necesaria"],
            )

        # Partidos NO críticos
        non_critical = [
            org
            for org in a["party_votes"]
            if org not in a["critical_parties"] and a["party_votes"][org]["favor"] > 0
        ]
        for org in non_critical:
            pv = a["party_votes"][org]
            remaining = a["a_favor_total"] - pv["favor"]
            logger.info(
                "    - %s: sin sus %d votos → %d >= %d → no critico",
                get_org_name(org),
                pv["favor"],
                remaining,
                a["mayoria_necesaria"],
            )

    # =========================================================================
    # 3. VOTACIONES CERRADAS (< 10 votos de margen)
    # =========================================================================
    logger.info("")
    logger.info(SEP)
    logger.info("3. VOTACIONES CERRADAS (margen < 10)".center(100))
    logger.info(SEP)

    close = close_votes_analysis["close_votes"]
    if close:
        logger.info("")
        logger.info("  Se encontraron %d votaciones cerradas:", len(close))
        logger.info("")
        logger.info(
            "  %-10s %8s %10s %8s %-20s %-30s",
            "VE",
            "A favor",
            "En contra",
            "Margen",
            "Requerimiento",
            "Críticos",
        )
        logger.info("  %s", "─" * 90)
        for cv in close:
            crit_names = [get_org_name(o) for o in cv["critical_parties"]]
            crit_display = ", ".join(crit_names) if crit_names else "Ninguno"
            logger.info(
                "  %-10s %8d %10d %8d %-20s %s",
                cv["vote_event_id"],
                cv["a_favor"],
                cv["en_contra"],
                cv["margin"],
                cv["requirement"],
                crit_display,
            )

        # Swing voters
        swing = close_votes_analysis["swing_voters"]
        if swing:
            logger.info("")
            logger.info("  Swing voters en votaciones cerradas (%d):", len(swing))
            logger.info(
                "  %-35s %-12s %-12s %-14s %-25s",
                "Legislador",
                "Partido",
                "Su voto",
                "Pos. partido",
                "Podría cambiar resultado",
            )
            logger.info("  %s", "─" * 100)
            for sv in swing:
                flip_str = "SI" if sv["could_flip_result"] else "No"
                logger.info(
                    "  %-35s %-12s %-12s %-14s %-25s",
                    sv["person_name"],
                    sv["party"],
                    sv["their_vote"],
                    sv["party_position"],
                    flip_str,
                )
        else:
            logger.info(
                "  No se encontraron swing voters (nadie voto diferente a su partido en votaciones cerradas)."
            )
    else:
        logger.info("  No se encontraron votaciones cerradas (margen < 10).")

    # =========================================================================
    # 4. TOP 10 DISIDENTES
    # =========================================================================
    logger.info("")
    logger.info(SEP)
    logger.info("4. TOP 10 DISIDENTES (votaron diferente a su partido)".center(100))
    logger.info(SEP)

    if dissidents:
        logger.info("")
        logger.info(
            "  %-4s %-35s %-12s %12s %12s %12s",
            "#",
            "Legislador",
            "Partido",
            "Disidencia",
            "Votaciones",
            "Disidentes",
        )
        logger.info("  %s", "─" * 90)
        for i, (pid, name, party, rate, total, dissent) in enumerate(dissidents, 1):
            logger.info(
                "  %-4d %-35s %-12s %10.1f%% %12d %12d",
                i,
                name,
                party,
                rate * 100,
                total,
                dissent,
            )
    else:
        logger.info(
            "  No se encontraron disidentes (ningun legislador voto diferente a su partido)."
        )

    # =========================================================================
    # 5. DETALLE POR VOTACIÓN (VE03-VE54)
    # =========================================================================
    logger.info("")
    logger.info(SEP)
    logger.info("5. DETALLE POR VOTACION (VE03-VE54)".center(100))
    logger.info(SEP)
    logger.info("")
    logger.info(
        "  %-8s %-18s %7s %8s %6s %7s %6s %5s %7s %-25s",
        "VE",
        "Req.",
        "Asist.",
        "Mayoria",
        "Favor",
        "Contra",
        "Abst.",
        "Aus.",
        "Margen",
        "Críticos",
    )
    logger.info("  %s", "─" * 100)

    for a in all_analyses:
        crit_names = [get_org_name(o) for o in a["critical_parties"]]
        crit_str = ", ".join(crit_names) if crit_names else "Ninguno (unanime)"
        logger.info(
            "  %-8s %-18s %7d %8d %6d %7d %6d %5d %7d %s",
            a["vote_event_id"],
            a["requirement"],
            a["total_asistentes"],
            a["mayoria_necesaria"],
            a["a_favor_total"],
            a["en_contra_total"],
            a["abstencion_total"],
            a["ausente_total"],
            a["margin"],
            crit_str,
        )

    # =========================================================================
    # RESUMEN ESTADÍSTICO
    # =========================================================================
    logger.info("")
    logger.info(SEP)
    logger.info("RESUMEN ESTADISTICO".center(100))
    logger.info(SEP)
    logger.info("")
    logger.info("  Total votaciones analizadas: %d", len(all_analyses))
    aprobadas = sum(1 for a in all_analyses if a["result"] == "aprobada")
    logger.info("  Todas aprobadas: %d", aprobadas)
    mayoria_simple = sum(1 for a in all_analyses if a["requirement"] == "mayoria_simple")
    logger.info("  Mayoria simple: %d", mayoria_simple)
    mayoria_calificada = sum(1 for a in all_analyses if a["requirement"] == "mayoria_calificada")
    logger.info("  Mayoria calificada: %d", mayoria_calificada)

    # Partidos más críticos
    crit_counts = defaultdict(int)
    for a in all_analyses:
        for org in a["critical_parties"]:
            crit_counts[org] += 1

    logger.info("")
    logger.info("  Veces critico por partido:")
    for org in sorted(crit_counts, key=crit_counts.get, reverse=True):
        logger.info(
            "    %-16s %4d / %d (%.1f%%)",
            get_org_name(org),
            crit_counts[org],
            len(all_analyses),
            crit_counts[org] / len(all_analyses) * 100,
        )

    # Votaciones donde nadie fue crítico (unánimes)
    unanimous = sum(1 for a in all_analyses if len(a["critical_parties"]) == 0)
    logger.info("")
    logger.info("  Votaciones unanimes (sin partidos criticos): %d", unanimous)

    # Votaciones con algún partido crítico
    with_critical = sum(1 for a in all_analyses if len(a["critical_parties"]) > 0)
    logger.info("  Votaciones con al menos un partido critico: %d", with_critical)

    logger.info("")
    logger.info("Archivos CSV generados en: %s/", out_dir)
    logger.info(SEP)


# Mantener compatibilidad: alias para el nombre original
print_all_results = log_all_results


# --- Main ---


def main(camara: str | None = None, output_dir: str | None = None):
    """Ejecuta análisis de poder empírico.

    Args:
        camara: 'D' para Diputados, 'S' para Senado, None para todas.
        output_dir: Directorio de salida. Si None, usa el default.
    """
    global GROUP_TO_ORG, ORG_SHORT_NAME, PARTY_ORGS, _total_seats_for_analysis

    out_dir = output_dir or OUTPUT_DIR

    # Inicializar constantes desde la BD para mapeos correctos de partidos.
    # Necesario porque la BD tiene IDs distintos (O11=MORENA, O12=PAN...)
    # vs. los hardcoded para Diputados LXVI (O01=Morena, O04=PAN...).
    init_constants_from_db(DB_PATH)
    import db.constants as _dbc

    GROUP_TO_ORG = _dbc._NAME_TO_ORG
    ORG_SHORT_NAME = _dbc._ORG_ID_TO_NAME
    PARTY_ORGS = list(_dbc._PARTY_ORG_IDS)

    # Ajustar total de asientos según cámara
    _total_seats_for_analysis = get_total_seats(DB_PATH, camara or "D")

    conn = get_connection(DB_PATH)

    # Obtener votaciones con resultado
    vote_events = get_vote_events_with_results(conn, camara=camara)
    if not vote_events:
        logger.warning("No se encontraron votaciones con resultado.")
        conn.close()
        return
    logger.info(
        "Votaciones con resultado: %d (%s-%s)", len(vote_events), vote_events[0], vote_events[-1]
    )

    # Analizar cada votación
    analyses = [analyze_vote_event(conn, ve_id) for ve_id in vote_events]

    # Calcular poder empírico
    empirical_power = calc_empirical_power(analyses)

    # Tabla comparativa
    comparison, quota_simple, total_seats = build_comparison_table(
        conn, empirical_power, camara=camara
    )

    # Análisis Reforma Judicial (solo para Diputados)
    reforma_ve_ids = REFORMA_JUDICIAL_VE_IDS if camara != "S" else []
    reforma_analyses = analyze_reforma_judicial(conn, reforma_ve_ids) if reforma_ve_ids else []

    # Votaciones cerradas
    close_votes_analysis = analyze_close_votes(conn, analyses, threshold=CLOSE_VOTES_THRESHOLD)

    # Top disidentes
    dissidents = find_top_dissidents(conn, min_votes=10, camara=camara)

    # Guardar CSVs
    save_results(
        comparison, reforma_analyses, dissidents, analyses, close_votes_analysis, output_dir=out_dir
    )

    # Registrar resultados
    camara_label = (
        "Camara de Diputados" if camara == "D" else ("Senado" if camara == "S" else "Congreso")
    )
    log_all_results(
        comparison,
        quota_simple,
        reforma_analyses,
        close_votes_analysis,
        dissidents,
        analyses,
        out_dir=out_dir,
    )

    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Análisis de poder empírico basado en votaciones reales"
    )
    parser.add_argument(
        "--camara",
        choices=["diputados", "senado"],
        default=None,
        help="Filtrar por cámara (diputados o senado)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida (default: analysis/analisis-diputados/output)",
    )
    args = parser.parse_args()

    camara_code = CAMARA_MAP.get(args.camara) if args.camara else None
    main(camara=camara_code, output_dir=args.output_dir)
