#!/usr/bin/env python3
"""
fix_org_basura.py — Elimina organizaciones basura de la BD.

Elimina:
  - O24 "TOTAL": partido fantasma con ~17K counts contaminados.
    Los counts se limpian (group_id → NULL) antes de borrar.
  - O29 "06/04/2026": fecha parseada como partido por
    get_or_create_organization sin validación. Sin counts asociados.

Detectado en auditoría 2026-04-06.

Uso:
    python db/migrations/fix_org_basura.py            # ejecuta corrección
    python db/migrations/fix_org_basura.py --dry-run  # solo muestra cambios
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent
DB_PATH = DB_DIR / "congreso.db"

BASURA_ORGS = {
    "O24": {"nombre": "TOTAL", "razon": "partido fantasma, ~17K counts contaminados"},
    "O29": {"nombre": "06/04/2026", "razon": "fecha parseada como partido"},
    "O30": {"nombre": "TOTAL", "razon": "recreada tras limpieza de O24 (mismo fantasma)"},
    "O31": {"nombre": "06/04/2026", "razon": "recreada tras limpieza de O29 (misma fecha)"},
}

# Patrones de nombre para detectar basura futura
BASURA_NAME_PATTERNS = ["TOTAL", "06/04/2026"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Elimina organizaciones basura")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra cambios")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Error: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    for org_id, info in BASURA_ORGS.items():
        print(f"\n--- {org_id} '{info['nombre']}' ---")
        print(f"    Razón: {info['razon']}")

        # Verificar que existe
        cur.execute("SELECT id, nombre, clasificacion FROM organization WHERE id = ?", (org_id,))
        row = cur.fetchone()
        if not row:
            print("    ✓ Ya no existe, nada que hacer")
            continue
        print(f"    Encontrada: id={row[0]}, nombre={row[1]}, clasificacion={row[2]}")

        # Contar counts asociados
        cur.execute("SELECT COUNT(*) FROM count WHERE group_id = ?", (org_id,))
        count_total = cur.fetchone()[0]
        print(f"    Counts asociados: {count_total}")

        if args.dry_run:
            if count_total > 0:
                print(f"    [DRY-RUN] UPDATE count SET group_id = NULL WHERE group_id = '{org_id}'")
            print(f"    [DRY-RUN] DELETE FROM organization WHERE id = '{org_id}'")
            continue

        # Ejecutar
        if count_total > 0:
            cur.execute("UPDATE count SET group_id = NULL WHERE group_id = ?", (org_id,))
            print(f"    ✓ Counts limpiados: {cur.rowcount}")

        cur.execute("DELETE FROM organization WHERE id = ?", (org_id,))
        print(f"    ✓ Organización eliminada: {cur.rowcount}")

    if not args.dry_run:
        conn.commit()

    # Resumen final
    cur.execute("SELECT COUNT(*) FROM organization")
    total_orgs = cur.fetchone()[0]
    print("\n=== Resumen ===")
    print(f"Total organizaciones: {total_orgs}")

    conn.close()


if __name__ == "__main__":
    main()
