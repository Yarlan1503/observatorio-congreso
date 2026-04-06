#!/usr/bin/env python3
"""
limpiar_org_basura_v2.py — Elimina organizaciones basura residuales.

Limpia:
- O29 '06/04/2026' — fecha parseada como partido (0 refs)
- O30 'TOTAL' — etiqueta de totales (581 counts basura en Diputados)

Uso:  uv run python db/migrations/limpiar_org_basura_v2.py
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")

BASURA = {
    "O29": {"nombre": "06/04/2026", "razon": "fecha parseada como partido"},
    "O30": {"nombre": "TOTAL", "razon": "etiqueta de totales colada como partido"},
}


def main():
    print("=" * 65)
    print("Limpiar organizaciones basura residuales")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] Base de datos no encontrada: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    total_deleted_counts = 0

    for org_id, info in BASURA.items():
        print(f"\n--- {org_id} '{info['nombre']}' ---")
        print(f"    Razón: {info['razon']}")

        # Verificar que existe
        row = cur.execute("SELECT id, nombre FROM organization WHERE id = ?", (org_id,)).fetchone()
        if not row:
            print("    No existe — saltando.")
            continue

        # Contar refs
        count_refs = cur.execute(
            "SELECT COUNT(*) FROM count WHERE group_id = ?", (org_id,)
        ).fetchone()[0]
        member_refs = cur.execute(
            "SELECT COUNT(*) FROM membership WHERE org_id = ?", (org_id,)
        ).fetchone()[0]
        print(f"    Refs en count: {count_refs}")
        print(f"    Refs en membership: {member_refs}")

        # Eliminar counts asociados
        if count_refs > 0:
            cur.execute("DELETE FROM count WHERE group_id = ?", (org_id,))
            print(f"    Counts eliminados: {count_refs}")
            total_deleted_counts += count_refs

        # Eliminar organización
        cur.execute("DELETE FROM organization WHERE id = ?", (org_id,))
        print(f"    Organización '{info['nombre']}' eliminada.")

    conn.commit()
    print(f"\n  ✓ Commit exitoso. {total_deleted_counts} counts eliminados.")

    # Verificación
    print(f"\n{'─' * 65}")
    print("VERIFICACIÓN")
    print(f"{'─' * 65}")
    remaining = cur.execute(
        "SELECT COUNT(*) FROM organization WHERE id IN ('O29', 'O30')"
    ).fetchone()[0]
    print(f"  Orgs basura restantes: {remaining}")

    total_orgs = cur.execute("SELECT COUNT(*) FROM organization").fetchone()[0]
    print(f"  Total organizaciones: {total_orgs}")

    conn.close()
    print(f"\n{'=' * 65}")
    print("Limpieza completada exitosamente")
    print(f"{'=' * 65}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
