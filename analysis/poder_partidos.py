"""
poder_partidos.py — Índices de Poder Shapley-Shubik y Banzhaf
Observatorio del Congreso de la Unión (LXVI Legislature, Cámara de Diputados)

Calcula índices de poder legislativo para cada partido basándose en:
- Shapley-Shubik: poder marginal promedio en todas las permutaciones
- Banzhaf: poder crítico en todas las coaliciones

Uso: python3 analysis/poder_partidos.py
"""

import sqlite3
import itertools
import math
from pathlib import Path

import pandas as pd

from db.constants import _NAME_TO_ORG, _ORG_ID_TO_NAME, _PARTY_ORG_IDS

DB_PATH = Path(__file__).parent.parent / "db" / "congreso.db"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Alias para compatibilidad interna
GROUP_TO_ORG = _NAME_TO_ORG
ORG_SHORT_NAME = _ORG_ID_TO_NAME
PARTY_ORGS = set(_PARTY_ORG_IDS)


# --- Funciones de datos ---


def get_party_name(conn, org_id: str) -> str:
    """Retorna nombre corto del partido."""
    return ORG_SHORT_NAME.get(org_id, org_id)


def get_seats_per_party(conn) -> dict:
    """
    Retorna {org_id: seat_count} con personas únicas asignadas a un solo partido.

    Estrategia:
    1. Obtener todas las memberships a partidos (excluyendo instituciones O08, O09).
    2. Para personas con multi-membership a partidos distintos:
       a. Contar votos normalizados por org_id en la tabla vote.
       b. Asignar al org_id donde más votos tiene.
       c. Si empate o sin votos, usar la membership con start_date más reciente.
    3. Para personas con memberships duplicadas al mismo partido: contar una sola vez.
    """
    cur = conn.cursor()

    # Paso 1: Obtener todas las memberships a partidos (solo diputados)
    cur.execute(
        """
        SELECT person_id, org_id, start_date
        FROM membership
        WHERE org_id IN ('O01','O02','O03','O04','O05','O06','O07','O11')
        AND rol = 'diputado'
        ORDER BY person_id, org_id
        """
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
                best_orgs = [
                    org for org, cnt in relevant_votes.items() if cnt == max_votes
                ]
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
    Calcula el índice Shapley-Shubik.

    weights: {player_id: weight}
    quota: umbral para ganar

    Returns: {player_id: float} donde la suma = 1.0

    Algoritmo: Para cada permutación de jugadores, sumar pesos acumulativamente.
    El jugador que hace que la suma pase el umbral es el "pivotal".
    Índice = veces pivotal / total permutaciones.

    Con 8 jugadores, 8! = 40,320 — perfectamente computable.
    """
    players = list(weights.keys())
    n = len(players)
    pivotal_count = {p: 0 for p in players}
    total_perms = math.factorial(n)

    for perm in itertools.permutations(players):
        cumulative = 0
        for player in perm:
            cumulative += weights[player]
            if cumulative >= quota:
                pivotal_count[player] += 1
                break

    return {p: pivotal_count[p] / total_perms for p in players}


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


def print_tabla_completa(df: pd.DataFrame, seats: dict, total_seats: int):
    """Imprime la tabla completa de resultados con formato legible."""

    print("=" * 100)
    print("ÍNDICES DE PODER LEGISLATIVO — LXVI LEGISLATURA, CÁMARA DE DIPUTADOS")
    print("=" * 100)

    # Tabla de escaños
    print(f"\n{'ESCAÑOS POR PARTIDO':^100}")
    print("-" * 60)
    print(f"{'Partido':<18} {'Org_ID':<8} {'Escaños':>8} {'Nominal %':>12}")
    print("-" * 60)

    # Ordenar por escaños descendente
    sorted_seats = sorted(seats.items(), key=lambda x: x[1], reverse=True)
    for org_id, seat_count in sorted_seats:
        name = ORG_SHORT_NAME.get(org_id, org_id)
        pct = seat_count / total_seats * 100
        print(f"{name:<18} {org_id:<8} {seat_count:>8} {pct:>11.2f}%")

    print("-" * 60)
    print(f"{'TOTAL':<18} {'':8} {total_seats:>8} {'100.00%':>12}")
    print()

    # Umbrales
    thresholds = df["Umbral"].unique()

    for threshold_name in thresholds:
        mask = df["Umbral"] == threshold_name
        sub = df[mask].sort_values("Escaños", ascending=False)

        print(f"\n{'UMBRAL: ' + threshold_name.upper():^100}")
        print("-" * 100)
        print(
            f"{'Partido':<18} {'Escaños':>8} {'Nominal %':>12} "
            f"{'Shapley-Shubik %':>18} {'Banzhaf %':>12} "
            f"{'SS/Nom':>10} {'BZ/Nom':>10}"
        )
        print("-" * 100)

        for _, row in sub.iterrows():
            nominal = row["Nominal_%"]
            ss = row["Shapley_Shubik_%"]
            bz = row["Banzhaf_%"]
            ss_ratio = ss / nominal if nominal > 0 else 0
            bz_ratio = bz / nominal if nominal > 0 else 0
            print(
                f"{row['Partido']:<18} {row['Escaños']:>8} {nominal:>11.2f}% "
                f"{ss:>17.2f}% {bz:>11.2f}% "
                f"{ss_ratio:>9.2f}x {bz_ratio:>9.2f}x"
            )

        print("-" * 100)
        ss_sum = sub["Shapley_Shubik_%"].sum()
        bz_sum = sub["Banzhaf_%"].sum()
        nom_sum = sub["Nominal_%"].sum()
        seats_sum = sub["Escaños"].sum()
        print(
            f"{'TOTAL':<18} {seats_sum:>8} {nom_sum:>11.2f}% "
            f"{ss_sum:>17.2f}% {bz_sum:>11.2f}%"
        )
        print()

    # Análisis de coaliciones clave
    print(f"\n{'ANÁLISIS DE COALICIONES CLAVE':^100}")
    print("=" * 100)
    _print_coalition_analysis(seats, total_seats)

    print()
    print(f"Archivos CSV generados en: {OUTPUT_DIR}/")
    print("=" * 100)


def _print_coalition_analysis(seats: dict, total_seats: int):
    """Imprime análisis de coaliciones ganadoras por umbral."""

    thresholds = {
        "Simple (251/500)": 251,
        "Calificada 2/3 (334/500)": 334,
        "3/4 (375/500)": 375,
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

    print(
        f"{'Coalición':<45} {'Escaños':>8} {'%':>8} {'Simple':>8} {'2/3':>8} {'3/4':>8}"
    )
    print("-" * 95)

    for coal_name, org_ids in coalitions.items():
        coal_seats = sum(seats.get(org, 0) for org in org_ids)
        coal_pct = coal_seats / total_seats * 100

        simple = "✓" if coal_seats >= 251 else "✗"
        calif = "✓" if coal_seats >= 334 else "✗"
        tres_cuartos = "✓" if coal_seats >= 375 else "✗"

        print(
            f"{coal_name:<45} {coal_seats:>8} {coal_pct:>7.1f}% "
            f"{simple:>8} {calif:>8} {tres_cuartos:>8}"
        )

    print()
    print(f"{'Nota: ✓ = alcanza el umbral, ✗ = no lo alcanza':^95}")
    print(
        f"{'Los porcentajes redondeados pueden no sumar 100.00% (los índices exactos sí suman 1.0)':^95}"
    )


# --- Main ---


def main():
    conn = sqlite3.connect(DB_PATH)
    seats = get_seats_per_party(conn)

    thresholds = {
        "Simple (251/500)": 251,
        "Calificada 2/3 (334/500)": 334,
        "3/4 (375/500)": 375,
    }

    total_seats = sum(seats.values())

    # Verificar total de escaños
    print(f"Total escaños computados: {total_seats}")
    print(
        f"  (La Cámara tiene 500 curules; el exceso refleja diputados que "
        f"sirvieron durante la legislatura pero fueron reemplazados)"
    )
    print(
        f"  (Solo se cuentan memberships con rol='diputado'; "
        f"militantes del caso cero excluidos)"
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
        df[mask].to_csv(OUTPUT_DIR / f"poder_{slug}.csv", index=False)

    # Tabla completa
    df.to_csv(OUTPUT_DIR / "poder_completo.csv", index=False)

    # Imprimir resultados
    print()
    print_tabla_completa(df, seats, total_seats)

    conn.close()
    return df


if __name__ == "__main__":
    main()
