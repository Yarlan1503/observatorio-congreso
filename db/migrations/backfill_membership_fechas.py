#!/usr/bin/env python3
"""
Backfill de start_date / end_date para memberships del Observatorio del Congreso.

Estrategia por tipo:
  - Diputados con start_date="" (string vacío): inferir legislatura de vote_events,
    luego asignar fechas constitucionales (leg.start, leg.end).
  - Senadores con end_date=NULL: inferir legislatura del start_date existente,
    luego asignar end_date constitucional.

Reglas:
  - NO sobreescribe fechas ya existentes.
  - NO tocar roles que no sean diputado o senador.
  - Idempotente: segunda ejecución no cambia nada.

Uso:
    .venv/bin/python3 -m db.migrations.backfill_membership_fechas
"""

import sqlite3
import sys
from pathlib import Path

from db.constants import LEGISLATURAS

# ── Paths ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO / "db" / "congreso.db"


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_leg_rango() -> list[tuple[str, str, str]]:
    """Retorna lista de (leg_key, start, end) ordenada por start."""
    return sorted(
        [(k, v["start"], v["end"]) for k, v in LEGISLATURAS.items()],
        key=lambda x: x[1],
    )


def _fecha_to_leg(fecha: str, leg_rango: list[tuple[str, str, str]]) -> str | None:
    """Dada una fecha YYYY-MM-DD, retorna la key de legislatura que la contiene."""
    for leg_key, start, end in leg_rango:
        if start <= fecha <= end:
            return leg_key
    return None


# ── FASE A: Diputados con start_date vacío ────────────────────────────────


def _fase_a_diputados(db: sqlite3.Connection, leg_rango: list) -> dict:
    """Backfill de diputados con start_date='' y end_date=NULL.

    Infieren la legislatura a partir de los vote_events donde votaron,
    usando la legislatura más frecuente de sus votos.
    """
    print("\n" + "=" * 60)
    print("FASE A: Diputados con start_date vacío")
    print("=" * 60)

    stats = {
        "total": 0,
        "actualizados": 0,
        "sin_legislatura": 0,
        "leg_desconocida": 0,
        "detalles_sin_leg": [],
        "detalles_leg_desconocida": [],
    }

    # Obtener diputados con start_date vacío y end_date NULL
    rows = db.execute(
        """SELECT m.id, m.person_id, m.label
           FROM membership m
           WHERE m.rol = 'diputado' AND m.start_date = '' AND m.end_date IS NULL"""
    ).fetchall()

    stats["total"] = len(rows)
    print(f"  Diputados candidatos: {stats['total']}")

    if not rows:
        return stats

    for membership_id, person_id, label in rows:
        # Inferir legislatura más frecuente de sus votos
        leg_row = db.execute(
            """SELECT ve.legislatura, COUNT(*) as cnt
               FROM vote v
               JOIN vote_event ve ON v.vote_event_id = ve.id
               WHERE v.voter_id = ?
                 AND ve.legislatura IS NOT NULL
               GROUP BY ve.legislatura
               ORDER BY cnt DESC
               LIMIT 1""",
            (person_id,),
        ).fetchone()

        if leg_row is None:
            stats["sin_legislatura"] += 1
            stats["detalles_sin_leg"].append((membership_id, person_id, label))
            continue

        leg_key = leg_row[0]

        if leg_key not in LEGISLATURAS:
            stats["leg_desconocida"] += 1
            stats["detalles_leg_desconocida"].append((membership_id, person_id, label, leg_key))
            continue

        leg = LEGISLATURAS[leg_key]
        db.execute(
            "UPDATE membership SET start_date = ?, end_date = ? WHERE id = ?",
            (leg["start"], leg["end"], membership_id),
        )
        stats["actualizados"] += 1

    print(f"  Actualizados: {stats['actualizados']}")
    print(f"  Sin legislatura (sin votos): {stats['sin_legislatura']}")
    print(f"  Legislatura desconocida: {stats['leg_desconocida']}")

    if stats["detalles_sin_leg"]:
        print(f"\n  Sin legislatura ({len(stats['detalles_sin_leg'])}):")
        for mid, pid, lbl in stats["detalles_sin_leg"][:20]:
            print(f"    {mid} ({pid}): {lbl}")
        if len(stats["detalles_sin_leg"]) > 20:
            print(f"    ... y {len(stats['detalles_sin_leg']) - 20} más")

    if stats["detalles_leg_desconocida"]:
        print(f"\n  Legislatura desconocida ({len(stats['detalles_leg_desconocida'])}):")
        for mid, pid, lbl, leg in stats["detalles_leg_desconocida"]:
            print(f"    {mid} ({pid}): {lbl} — leg={leg}")

    return stats


# ── FASE B: Senadores sin end_date ────────────────────────────────────────


def _fase_b_senadores(db: sqlite3.Connection, leg_rango: list) -> dict:
    """Backfill de senadores con end_date=NULL que ya tienen start_date real.

    Infiere legislatura del start_date (mapear al rango constitucional).
    """
    print("\n" + "=" * 60)
    print("FASE B: Senadores sin end_date")
    print("=" * 60)

    stats = {"total": 0, "actualizados": 0, "sin_legislatura": 0, "detalles_sin_leg": []}

    # Obtener senadores sin end_date y con start_date real
    rows = db.execute(
        """SELECT m.id, m.person_id, m.start_date, m.label
           FROM membership m
           WHERE m.rol = 'senador'
             AND m.end_date IS NULL
             AND m.start_date IS NOT NULL
             AND m.start_date != ''"""
    ).fetchall()

    stats["total"] = len(rows)
    print(f"  Senadores candidatos: {stats['total']}")

    if not rows:
        return stats

    for membership_id, person_id, start_date, label in rows:
        leg_key = _fecha_to_leg(start_date, leg_rango)

        if leg_key is None:
            stats["sin_legislatura"] += 1
            stats["detalles_sin_leg"].append((membership_id, person_id, start_date, label))
            continue

        leg = LEGISLATURAS[leg_key]
        db.execute(
            "UPDATE membership SET end_date = ? WHERE id = ?",
            (leg["end"], membership_id),
        )
        stats["actualizados"] += 1

    print(f"  Actualizados: {stats['actualizados']}")
    print(f"  Sin legislatura (fecha fuera de rango): {stats['sin_legislatura']}")

    if stats["detalles_sin_leg"]:
        print(f"\n  Sin legislatura ({len(stats['detalles_sin_leg'])}):")
        for mid, pid, sd, lbl in stats["detalles_sin_leg"][:20]:
            print(f"    {mid} ({pid}): start={sd} — {lbl}")
        if len(stats["detalles_sin_leg"]) > 20:
            print(f"    ... y {len(stats['detalles_sin_leg']) - 20} más")

    return stats


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    print("Backfill de Fechas de Membership — Observatorio del Congreso")
    print(f"BD: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"ERROR: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA foreign_keys=ON")

    leg_rango = _build_leg_rango()

    # ── Estado inicial ──────────────────────────────────────────────────
    print("\n--- Estado Inicial ---")
    for rol in ["diputado", "senador"]:
        total = db.execute("SELECT COUNT(*) FROM membership WHERE rol=?", (rol,)).fetchone()[0]
        con_start = db.execute(
            "SELECT COUNT(*) FROM membership WHERE rol=? AND start_date IS NOT NULL AND start_date != ''",
            (rol,),
        ).fetchone()[0]
        con_end = db.execute(
            "SELECT COUNT(*) FROM membership WHERE rol=? AND end_date IS NOT NULL",
            (rol,),
        ).fetchone()[0]
        print(f"  {rol}: total={total}, con_start={con_start}, con_end={con_end}")

    # ── Ejecutar fases ──────────────────────────────────────────────────
    stats_a = _fase_a_diputados(db, leg_rango)
    stats_b = _fase_b_senadores(db, leg_rango)

    db.commit()

    # ── Estado final ────────────────────────────────────────────────────
    print("\n--- Estado Final ---")
    for rol in ["diputado", "senador"]:
        total = db.execute("SELECT COUNT(*) FROM membership WHERE rol=?", (rol,)).fetchone()[0]
        con_start = db.execute(
            "SELECT COUNT(*) FROM membership WHERE rol=? AND start_date IS NOT NULL AND start_date != ''",
            (rol,),
        ).fetchone()[0]
        con_end = db.execute(
            "SELECT COUNT(*) FROM membership WHERE rol=? AND end_date IS NOT NULL",
            (rol,),
        ).fetchone()[0]
        pct_start = con_start * 100 / total if total else 0
        pct_end = con_end * 100 / total if total else 0
        print(
            f"  {rol}: total={total}, con_start={con_start} ({pct_start:.1f}%), con_end={con_end} ({pct_end:.1f}%)"
        )

    # Residuales
    sin_ambos = db.execute(
        """SELECT COUNT(*) FROM membership
           WHERE (start_date IS NULL OR start_date = '') AND end_date IS NULL"""
    ).fetchone()[0]
    print(f"\n  Residuales sin ambas fechas: {sin_ambos}")

    # ── Reporte final ───────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("REPORTE FINAL")
    print("=" * 60)
    print("  FASE A — Diputados:")
    print(f"    Candidatos:        {stats_a['total']}")
    print(f"    Actualizados:      {stats_a['actualizados']}")
    print(f"    Sin legislatura:   {stats_a['sin_legislatura']}")
    print(f"    Leg desconocida:   {stats_a['leg_desconocida']}")
    print("  FASE B — Senadores:")
    print(f"    Candidatos:        {stats_b['total']}")
    print(f"    Actualizados:      {stats_b['actualizados']}")
    print(f"    Sin legislatura:   {stats_b['sin_legislatura']}")

    db.close()
    print("\n✓ Listo.")


if __name__ == "__main__":
    main()
