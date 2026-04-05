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

import sqlite3
import csv
import os
import math
from collections import defaultdict
from itertools import permutations, combinations

from db.constants import (
    _NAME_TO_ORG,
    _ORG_ID_TO_NAME,
    _PARTY_ORG_IDS,
    TOTAL_SEATS,
    MIN_VOTES,
    CAMARA_DIPUTADOS_ID,
    CAMARA_SENADO_ID,
    get_total_seats,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "congreso.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# --- Constantes ---

# Alias para compatibilidad interna
GROUP_TO_ORG = _NAME_TO_ORG
ORG_SHORT_NAME = _ORG_ID_TO_NAME
PARTY_ORGS = list(_PARTY_ORG_IDS)


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


def get_seat_counts(conn):
    """
    Retorna {org_id: seat_count} con el máximo de votantes por partido
    en cualquier votación individual. Proxy para escaños efectivos.

    Normaliza grupos (nombres vs IDs) ANTES de tomar el máximo,
    ya que VE01 usa nombres ('PT', 'PVEM') y VE03+ usa IDs ('O02', 'O03').
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT vote_event_id, "group", COUNT(*) as cnt
        FROM vote
        WHERE "group" IS NOT NULL
        GROUP BY vote_event_id, "group"
    """)
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
        # 2/3 del total de la Cámara (500)
        mayoria_necesaria = math.ceil(2 / 3 * TOTAL_SEATS)  # 334
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

    weights: {player_id: weight}
    quota: umbral para coalición ganadora

    Returns: {player_id: float} donde la suma = 1.0
    """
    players = list(weights.keys())
    n = len(players)
    pivotal_count = defaultdict(int)
    total_perms = math.factorial(n)

    for perm in permutations(players):
        cumulative = 0
        for player in perm:
            cumulative += weights[player]
            if cumulative >= quota:
                pivotal_count[player] += 1
                break

    return {p: pivotal_count.get(p, 0) / total_perms for p in players}


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
    seats = get_seat_counts(conn)

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
            if party_pos == "favor" and option != "a_favor":
                dissenting = True
            elif party_pos == "contra" and option != "en_contra":
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


def find_top_dissidents(conn, min_votes=MIN_VOTES):
    """
    Encuentra los legisladores que más votaron diferente a su partido.

    Returns: [(person_id, person_name, party, dissent_rate, total_votes, dissent_count)]
    """
    cur = conn.cursor()

    # Obtener votaciones con resultado
    ve_ids = get_vote_events_with_results(conn)

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
                opts.get("a_favor", 0)
                + opts.get("en_contra", 0)
                + opts.get("abstencion", 0)
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
    person_stats = defaultdict(
        lambda: {"total": 0, "dissent": 0, "party_counts": defaultdict(int)}
    )

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

    return dissidents[:10]


# --- Output ---


def save_results(
    comparison, reforma_analyses, dissidents, all_analyses, close_votes_analysis
):
    """Guarda todos los resultados en CSVs."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. poder_empirico.csv
    with open(os.path.join(OUTPUT_DIR, "poder_empirico.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["partido", "org_id", "poder_empirico"])
        for row in comparison:
            writer.writerow([row["partido"], row["org_id"], f"{row['empirico']:.4f}"])

    # 2. comparacion_poder.csv
    with open(os.path.join(OUTPUT_DIR, "comparacion_poder.csv"), "w", newline="") as f:
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
    with open(os.path.join(OUTPUT_DIR, "votaciones_detalle.csv"), "w", newline="") as f:
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
    with open(os.path.join(OUTPUT_DIR, "disidentes.csv"), "w", newline="") as f:
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
    with open(os.path.join(OUTPUT_DIR, "reforma_judicial.csv"), "w", newline="") as f:
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


def print_all_results(
    comparison,
    quota_simple,
    reforma_analyses,
    close_votes_analysis,
    dissidents,
    all_analyses,
):
    """Imprime todos los resultados numéricos."""

    SEP = "=" * 100

    print()
    print(SEP)
    print("PODER EMPIRICO — Observatorio del Congreso de la Union")
    print("LXVI Legislatura - Camara de Diputados")
    print(SEP)

    # =========================================================================
    # 1. TABLA COMPARATIVA DE PODER
    # =========================================================================
    print(f"\n{'1. TABLA COMPARATIVA DE PODER':^100}")
    print(f"{'(Quota mayoria simple = ' + str(quota_simple) + ' escaños)':^100}")
    print("-" * 100)
    print(
        f"{'Partido':<16} {'Escaños':>8} {'Nominal':>10} {'Shapley-S':>12} {'Banzhaf':>10} {'Empírico':>10} {'Emp>Shap':>10}"
    )
    print("-" * 100)

    for row in comparison:
        nom = row["nominal"] * 100
        ss = row["shapley_shubik"] * 100
        bz = row["banzhaf"] * 100
        emp = row["empirico"] * 100
        ratio = f"{emp / ss:.1f}x" if ss > 0 else "N/A"
        print(
            f"{row['partido']:<16} {row['escanos']:>8} {nom:>9.1f}% {ss:>11.1f}% {bz:>9.1f}% {emp:>9.1f}% {ratio:>10}"
        )

    print("-" * 100)
    total_seats = sum(r["escanos"] for r in comparison)
    total_nom = sum(r["nominal"] for r in comparison) * 100
    total_ss = sum(r["shapley_shubik"] for r in comparison) * 100
    total_bz = sum(r["banzhaf"] for r in comparison) * 100
    total_emp = sum(r["empirico"] for r in comparison) * 100
    print(
        f"{'TOTAL':<16} {total_seats:>8} {total_nom:>9.1f}% {total_ss:>11.1f}% {total_bz:>9.1f}% {total_emp:>9.1f}%"
    )
    print()

    # Interpretación
    print(f"{'INTERPRETACION':^100}")
    print("-" * 100)
    morena_row = next((r for r in comparison if r["org_id"] == "O01"), None)
    if morena_row:
        emp_morena = morena_row["empirico"] * 100
        ss_morena = morena_row["shapley_shubik"] * 100
        print(
            f"  Morena tiene {morena_row['escanos']} escaños ({morena_row['nominal'] * 100:.1f}% de la Camara)."
        )
        print(
            f"  Shapley-Shubik = {ss_morena:.1f}%: con mayoria simple, Morena domina unilateralmente."
        )
        print(
            f"  Poder empirico = {emp_morena:.1f}%: porcentaje de votaciones donde fue critica."
        )
        print(
            f"  La diferencia entre poder teorico ({ss_morena:.1f}%) y empirico ({emp_morena:.1f}%)"
        )
        print(
            f"  revela donde las coaliciones reales difieren del modelo de mayoria simple."
        )

    pt_row = next((r for r in comparison if r["org_id"] == "O02"), None)
    pvem_row = next((r for r in comparison if r["org_id"] == "O03"), None)
    if pt_row and pvem_row:
        print(
            f"\n  PT ({pt_row['empirico'] * 100:.1f}% empirico) y PVEM ({pvem_row['empirico'] * 100:.1f}% empirico)"
        )
        print(f"  tienen 0% de poder Shapley-Shubik para mayoria simple, pero su poder")
        print(
            f"  empirico proviene de votaciones que requieren mayoria calificada (2/3)."
        )
    print()

    # =========================================================================
    # 2. REFORMA JUDICIAL (VE04 / VE05)
    # =========================================================================
    print(SEP)
    print(f"{'2. REFORMA JUDICIAL (VE04 y VE05)':^100}")
    print(SEP)

    for a in reforma_analyses:
        ve_id = a["vote_event_id"]
        print(f"\n  {'─' * 90}")
        print(f"  {ve_id}: {a['result'].upper()} — Requerimiento: {a['requirement']}")
        print(f"  {'─' * 90}")
        print(f"  Mayoria necesaria (2/3 de 500): {a['mayoria_necesaria']}")
        print(f"  A favor:   {a['a_favor_total']:>4}")
        print(f"  En contra: {a['en_contra_total']:>4}")
        print(f"  Abstencion:{a['abstencion_total']:>4}")
        print(f"  Ausente:   {a['ausente_total']:>4}")
        print(f"  Margen:    {a['margin']:>4} (a_favor - mayoria_necesaria)")

        print(f"\n  {'Desglose por partido:':}")
        print(
            f"  {'Partido':<16} {'A favor':>8} {'En contra':>10} {'Abstencion':>10} {'Ausente':>8} {'Total':>6} {'Posición':>10} {'Crítico':>8}"
        )
        print(f"  {'─' * 88}")

        for org in ["O01", "O02", "O03", "O04", "O05", "O06"]:
            if org in a["party_votes"]:
                pv = a["party_votes"][org]
                is_critical = "*** SI" if org in a["critical_parties"] else "NO"
                pos_display = pv["position"]
                print(
                    f"  {get_org_name(org):<16} {pv['favor']:>8} {pv['contra']:>10} {pv['abstencion']:>10} {pv['ausente']:>8} {pv['total']:>6} {pos_display:>10} {is_critical:>8}"
                )

        # Coalición ganadora
        coleccion_favor = []
        for org in sorted(a["party_votes"].keys()):
            pv = a["party_votes"][org]
            if pv["favor"] > 0:
                coleccion_favor.append(f"{get_org_name(org)}({pv['favor']})")
        coalicion_str = " + ".join(coleccion_favor)
        print(f"\n  Coalicion ganadora: {coalicion_str} = {a['a_favor_total']}")

        # Verificar criticidad
        print(
            f"  Partidos criticos (sin cuyo apoyo no se llegaba a {a['mayoria_necesaria']}):"
        )
        for org in a["critical_parties"]:
            pv = a["party_votes"][org]
            remaining = a["a_favor_total"] - pv["favor"]
            print(
                f"    - {get_org_name(org)}: sin sus {pv['favor']} votos a favor → {remaining} < {a['mayoria_necesaria']} → CRITICO"
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
            print(
                f"    - {get_org_name(org)}: sin sus {pv['favor']} votos → {remaining} >= {a['mayoria_necesaria']} → no critico"
            )

    print()

    # =========================================================================
    # 3. VOTACIONES CERRADAS (< 10 votos de margen)
    # =========================================================================
    print(SEP)
    print(f"{'3. VOTACIONES CERRADAS (margen < 10)':^100}")
    print(SEP)

    close = close_votes_analysis["close_votes"]
    if close:
        print(f"\n  Se encontraron {len(close)} votaciones cerradas:\n")
        print(
            f"  {'VE':<10} {'A favor':>8} {'En contra':>10} {'Margen':>8} {'Requerimiento':<20} {'Críticos':<30}"
        )
        print(f"  {'─' * 90}")
        for cv in close:
            crit_names = [get_org_name(o) for o in cv["critical_parties"]]
            print(
                f"  {cv['vote_event_id']:<10} {cv['a_favor']:>8} {cv['en_contra']:>10} {cv['margin']:>8} {cv['requirement']:<20} {', '.join(crit_names) if crit_names else 'Ninguno'}"
            )

        # Swing voters
        swing = close_votes_analysis["swing_voters"]
        if swing:
            print(f"\n  Swing voters en votaciones cerradas ({len(swing)}):")
            print(
                f"  {'Legislador':<35} {'Partido':<12} {'Su voto':<12} {'Pos. partido':<14} {'Podría cambiar resultado':<25}"
            )
            print(f"  {'─' * 100}")
            for sv in swing:
                flip_str = "SI" if sv["could_flip_result"] else "No"
                print(
                    f"  {sv['person_name']:<35} {sv['party']:<12} {sv['their_vote']:<12} {sv['party_position']:<14} {flip_str:<25}"
                )
        else:
            print(
                "\n  No se encontraron swing voters (nadie voto diferente a su partido en votaciones cerradas)."
            )
    else:
        print("\n  No se encontraron votaciones cerradas (margen < 10).")
    print()

    # =========================================================================
    # 4. TOP 10 DISIDENTES
    # =========================================================================
    print(SEP)
    print(f"{'4. TOP 10 DISIDENTES (votaron diferente a su partido)':^100}")
    print(SEP)

    if dissidents:
        print(
            f"\n  {'#':<4} {'Legislador':<35} {'Partido':<12} {'Disidencia':>12} {'Votaciones':>12} {'Disidentes':>12}"
        )
        print(f"  {'─' * 90}")
        for i, (pid, name, party, rate, total, dissent) in enumerate(dissidents, 1):
            print(
                f"  {i:<4} {name:<35} {party:<12} {rate * 100:>11.1f}% {total:>12} {dissent:>12}"
            )
    else:
        print(
            "\n  No se encontraron disidentes (ningun legislador voto diferente a su partido)."
        )
    print()

    # =========================================================================
    # 5. DETALLE POR VOTACIÓN (VE03-VE54)
    # =========================================================================
    print(SEP)
    print(f"{'5. DETALLE POR VOTACION (VE03-VE54)':^100}")
    print(SEP)
    print(
        f"\n  {'VE':<8} {'Req.':<18} {'Asist.':>7} {'Mayoria':>8} {'Favor':>6} {'Contra':>7} {'Abst.':>6} {'Aus.':>5} {'Margen':>7} {'Críticos':<25}"
    )
    print(f"  {'─' * 100}")

    for a in all_analyses:
        crit_names = [get_org_name(o) for o in a["critical_parties"]]
        crit_str = ", ".join(crit_names) if crit_names else "Ninguno (unanime)"
        print(
            f"  {a['vote_event_id']:<8} {a['requirement']:<18} {a['total_asistentes']:>7} {a['mayoria_necesaria']:>8} "
            f"{a['a_favor_total']:>6} {a['en_contra_total']:>7} {a['abstencion_total']:>6} {a['ausente_total']:>5} "
            f"{a['margin']:>7} {crit_str:<25}"
        )

    # =========================================================================
    # RESUMEN ESTADÍSTICO
    # =========================================================================
    print()
    print(SEP)
    print(f"{'RESUMEN ESTADISTICO':^100}")
    print(SEP)
    print(f"\n  Total votaciones analizadas: {len(all_analyses)}")
    print(
        f"  Todas aprobadas: {sum(1 for a in all_analyses if a['result'] == 'aprobada')}"
    )
    print(
        f"  Mayoria simple: {sum(1 for a in all_analyses if a['requirement'] == 'mayoria_simple')}"
    )
    print(
        f"  Mayoria calificada: {sum(1 for a in all_analyses if a['requirement'] == 'mayoria_calificada')}"
    )

    # Partidos más críticos
    crit_counts = defaultdict(int)
    for a in all_analyses:
        for org in a["critical_parties"]:
            crit_counts[org] += 1

    print(f"\n  Veces critico por partido:")
    for org in sorted(crit_counts, key=crit_counts.get, reverse=True):
        print(
            f"    {get_org_name(org):<16} {crit_counts[org]:>4} / {len(all_analyses)} ({crit_counts[org] / len(all_analyses) * 100:.1f}%)"
        )

    # Votaciones donde nadie fue crítico (unánimes)
    unanimous = sum(1 for a in all_analyses if len(a["critical_parties"]) == 0)
    print(f"\n  Votaciones unanimes (sin partidos criticos): {unanimous}")

    # Votaciones con algún partido crítico
    with_critical = sum(1 for a in all_analyses if len(a["critical_parties"]) > 0)
    print(f"  Votaciones con al menos un partido critico: {with_critical}")

    print()
    print(f"Archivos CSV generados en: {OUTPUT_DIR}/")
    print(SEP)


# --- Main ---


def main(camara: str | None = None):
    """Ejecuta análisis de poder empírico.

    Args:
        camara: 'D' para Diputados, 'S' para Senado, None para todas.
    """
    conn = sqlite3.connect(DB_PATH)

    # Obtener votaciones con resultado
    vote_events = get_vote_events_with_results(conn, camara=camara)
    if not vote_events:
        print("No se encontraron votaciones con resultado.")
        conn.close()
        return
    print(
        f"Votaciones con resultado: {len(vote_events)} ({vote_events[0]}-{vote_events[-1]})"
    )

    # Analizar cada votación
    analyses = [analyze_vote_event(conn, ve_id) for ve_id in vote_events]

    # Calcular poder empírico
    empirical_power = calc_empirical_power(analyses)

    # Tabla comparativa
    comparison, quota_simple, total_seats = build_comparison_table(
        conn, empirical_power, camara=camara
    )

    # Análisis Reforma Judicial
    reforma_analyses = analyze_reforma_judicial(conn, ["VE04", "VE05"])

    # Votaciones cerradas
    close_votes_analysis = analyze_close_votes(conn, analyses, threshold=10)

    # Top disidentes
    dissidents = find_top_dissidents(conn, min_votes=10)

    # Guardar CSVs
    save_results(
        comparison, reforma_analyses, dissidents, analyses, close_votes_analysis
    )

    # Imprimir resultados
    print_all_results(
        comparison,
        quota_simple,
        reforma_analyses,
        close_votes_analysis,
        dissidents,
        analyses,
    )

    conn.close()


if __name__ == "__main__":
    main()
