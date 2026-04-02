#!/usr/bin/env python3
"""
add_requirement_column.py — Agrega columna requirement a vote_event y la poble.

Idempotente: verifica si la columna ya existe antes de agregarla.

Uso:
    python db/add_requirement_column.py            # ejecuta migración
    python db/add_requirement_column.py --stats    # muestra estado actual
"""

import sqlite3
import sys
from pathlib import Path

# Path del proyecto: un nivel arriba de db/
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from diputados.scraper.config import DB_PATH


def get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Retorna los nombres de columnas de una tabla."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def show_stats(conn: sqlite3.Connection) -> None:
    """Muestra estadísticas actuales de requirement en vote_event y motion."""
    print("\n=== ESTADÍSTICAS ===\n")

    # Total vote_events
    total_ve = conn.execute("SELECT COUNT(*) FROM vote_event").fetchone()[0]
    print(f"vote_event total: {total_ve}")

    # Total motions
    total_m = conn.execute("SELECT COUNT(*) FROM motion").fetchone()[0]
    print(f"motion total:     {total_m}")

    # ¿Columna requirement existe en vote_event?
    columns = get_columns(conn, "vote_event")
    has_req = "requirement" in columns
    print(f"requirement en vote_event: {'SÍ' if has_req else 'NO'}")

    if has_req:
        # Distribución de requirement en vote_event
        print("\n--- vote_event.requirement ---")
        rows = conn.execute(
            "SELECT requirement, COUNT(*) FROM vote_event GROUP BY requirement ORDER BY requirement"
        ).fetchall()
        for req, count in rows:
            label = req if req else "NULL"
            print(f"  {label}: {count}")

        # NULLs
        nulls = conn.execute(
            "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
        ).fetchone()[0]
        print(f"\nvote_events sin requirement: {nulls}")

    # Distribución de requirement en motion (referencia)
    print("\n--- motion.requirement (referencia) ---")
    rows = conn.execute(
        "SELECT requirement, COUNT(*) FROM motion GROUP BY requirement ORDER BY requirement"
    ).fetchall()
    for req, count in rows:
        print(f"  {req}: {count}")


def migrate(conn: sqlite3.Connection) -> None:
    """Ejecuta la migración: agrega columna y pobla datos."""
    columns = get_columns(conn, "vote_event")

    if "requirement" in columns:
        print("✓ La columna 'requirement' ya existe en vote_event.")
    else:
        print("Agregando columna 'requirement' a vote_event...")
        conn.execute(
            "ALTER TABLE vote_event ADD COLUMN requirement TEXT "
            "CHECK(requirement IN ('mayoria_simple', 'mayoria_calificada', 'unanime', NULL))"
        )
        print("✓ Columna agregada.")

    # Poblar requirement desde motion
    nulls_before = conn.execute(
        "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
    ).fetchone()[0]

    if nulls_before == 0:
        print("✓ Todos los vote_events ya tienen requirement asignado.")
        return

    print(f"Actualizando {nulls_before} vote_events con requirement de su motion...")
    conn.execute(
        "UPDATE vote_event SET requirement = "
        "(SELECT m.requirement FROM motion m WHERE m.id = vote_event.motion_id) "
        "WHERE requirement IS NULL"
    )
    conn.commit()

    nulls_after = conn.execute(
        "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
    ).fetchone()[0]
    updated = nulls_before - nulls_after
    print(f"✓ {updated} vote_events actualizados.")

    if nulls_after > 0:
        print(
            f"⚠ {nulls_after} vote_events quedaron sin requirement "
            f"(motion sin requirement o motion_id roto)."
        )
        # Mostrar ejemplos problemáticos
        orphans = conn.execute(
            "SELECT ve.id, ve.motion_id FROM vote_event ve "
            "WHERE ve.requirement IS NULL LIMIT 5"
        ).fetchall()
        for ve_id, motion_id in orphans:
            print(f"  - {ve_id} (motion_id={motion_id})")


def main():
    db_path = str(DB_PATH)
    print(f"DB: {db_path}")

    if not Path(db_path).exists():
        print(f"ERROR: No existe la BD en {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        if "--stats" in sys.argv:
            show_stats(conn)
        else:
            print("\n=== ANTES DE MIGRACIÓN ===")
            show_stats(conn)

            print("\n\n=== EJECUTANDO MIGRACIÓN ===")
            migrate(conn)

            print("\n\n=== DESPUÉS DE MIGRACIÓN ===")
            show_stats(conn)

            # Verificación final
            nulls = conn.execute(
                "SELECT COUNT(*) FROM vote_event WHERE requirement IS NULL"
            ).fetchone()[0]
            if nulls == 0:
                print("\n✓ MIGRACIÓN COMPLETA: 0 NULLs en vote_event.requirement")
            else:
                print(f"\n⚠ MIGRACIÓN PARCIAL: {nulls} NULLs restantes")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
