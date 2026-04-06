#!/usr/bin/env python3
"""
backfill_requirement.py — Rellena vote_event.requirement desde motion.requirement.

Para vote_events donde requirement IS NULL:
1. JOIN con motion para obtener motion.requirement
2. Si motion.requirement también es NULL → inferir del título de la motion
3. Reportar estadísticas

Idempotente: solo actualiza donde requirement IS NULL.
Uso: python db/backfill_requirement.py
"""

import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "congreso.db"


def determinar_requirement(titulo: str) -> str:
    """Infiere requirement del título de la motion."""
    titulo_up = titulo.upper()
    if "CONSTITUCI" in titulo_up:
        return "mayoria_calificada"
    return "mayoria_simple"


def main():
    if not DB_PATH.exists():
        print(f"ERROR: No existe la BD en {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    try:
        return _run(conn)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection) -> int:
    print(f"DB: {DB_PATH}")
    print()

    # ── 1. Contar NULLs antes ──────────────────────────────────────
    nulls_before = conn.execute(
        "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM vote_event").fetchone()[0]

    print(f"vote_event total: {total}")
    print(f"vote_event con requirement NULL: {nulls_before}")

    if nulls_before == 0:
        print("\n✓ Todos los vote_events ya tienen requirement. No se necesitan actualizaciones.")
        # Mostrar distribución actual
        print("\nDistribución actual:")
        for req, count in conn.execute(
            "SELECT requirement, COUNT(*) FROM vote_event GROUP BY requirement ORDER BY requirement"
        ):
            print(f"  {req}: {count}")
        return 0

    # ── 2. Actualizar desde motion.requirement ─────────────────────
    print(f"\nActualizando {nulls_before} vote_events desde motion.requirement...")
    conn.execute(
        "UPDATE vote_event "
        "SET requirement = ("
        "    SELECT m.requirement FROM motion m WHERE m.id = vote_event.motion_id"
        ") "
        "WHERE requirement IS NULL"
    )
    conn.commit()

    updated_from_motion = (
        nulls_before
        - conn.execute("SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL").fetchone()[0]
    )
    print(f"  Desde motion.requirement: {updated_from_motion}")

    # ── 3. Inferir de título para NULLs restantes ──────────────────
    nulls_after_motion = conn.execute(
        "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
    ).fetchone()[0]

    updated_from_title = 0
    if nulls_after_motion > 0:
        print(
            f"\nQuedan {nulls_after_motion} con motion.requirement NULL. Infiriendo del título..."
        )
        rows = conn.execute(
            "SELECT ve.id, m.texto "
            "FROM vote_event ve "
            "JOIN motion m ON m.id = ve.motion_id "
            "WHERE ve.requirement IS NULL"
        ).fetchall()

        for ve_id, texto in rows:
            req = determinar_requirement(texto or "")
            conn.execute(
                "UPDATE vote_event SET requirement = ? WHERE id = ?",
                (req, ve_id),
            )
            updated_from_title += 1

        conn.commit()
        print(f"  Inferidos del título: {updated_from_title}")

    # ── 4. Reporte final ───────────────────────────────────────────
    nulls_final = conn.execute(
        "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
    ).fetchone()[0]

    print("\n=== REPORTE ===")
    print(f"  NULLs antes:          {nulls_before}")
    print(f"  Desde motion:         {updated_from_motion}")
    print(f"  Inferidos (título):   {updated_from_title}")
    print(f"  NULLs después:        {nulls_final}")

    print("\nDistribución final:")
    for req, count in conn.execute(
        "SELECT requirement, COUNT(*) FROM vote_event GROUP BY requirement ORDER BY requirement"
    ):
        print(f"  {req}: {count}")

    if nulls_final == 0:
        print("\n✓ BACKFILL COMPLETO: 0 NULLs en vote_event.requirement")
        return 0
    else:
        print(f"\n⚠ BACKFILL PARCIAL: {nulls_final} NULLs restantes")
        return 1


if __name__ == "__main__":
    sys.exit(main())
