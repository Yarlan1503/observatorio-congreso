#!/usr/bin/env python3
"""
limpiar_fantasmas_y_total.py — Limpia VEs fantasma y orgs basura residuales.

Realiza:
1. Elimina vote_events con 0 votos (VEs fantasma del Senado).
2. Elimina counts y organizaciones basura residuales (O24 TOTAL, etc.).

Idempotente: usa DELETE condicional, seguro ejecutar múltiples veces.

Detectado en auditoría 2026-04-06. Actualizado 2026-04-07.

Uso:
    python db/migrations/limpiar_fantasmas_y_total.py            # ejecuta
    python db/migrations/limpiar_fantasmas_y_total.py --dry-run  # solo muestra
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent
DB_PATH = DB_DIR / "congreso.db"

# Organizaciones basura conocidas (O24 ya fue limpiada pero puede recrearse)
BASURA_ORG_IDS = {"O24", "O29", "O30", "O31"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpia VEs fantasma y orgs basura")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra cambios")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Error: BD no encontrada en {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # ========================================================================
    # 1. Eliminar VEs fantasma (0 votos)
    # ========================================================================
    print("=" * 60)
    print("1. VOTE_EVENTS FANTASMA (0 votos)")
    print("=" * 60)

    phantom_ves = cur.execute("""
        SELECT ve.id, ve.legislatura, ve.organization_id
        FROM vote_event ve
        LEFT JOIN vote v ON v.vote_event_id = ve.id
        GROUP BY ve.id
        HAVING COUNT(v.id) = 0
    """).fetchall()

    if not phantom_ves:
        print("  No hay VEs fantasma. Nada que hacer.")
    else:
        print(f"  Encontrados {len(phantom_ves)} VEs fantasma:")
        for ve_id, leg, org in phantom_ves:
            print(f"    {ve_id} | leg={leg} | org={org}")

        # Check counts associated with these VEs
        ve_ids = [ve[0] for ve in phantom_ves]
        placeholders = ",".join(["?"] * len(ve_ids))
        counts_for_ves = cur.execute(
            f"SELECT COUNT(*) FROM count WHERE vote_event_id IN ({placeholders})",
            ve_ids,
        ).fetchone()[0]
        print(f"  Counts asociados: {counts_for_ves}")

        # Check motions associated (may be shared — do NOT delete motions)
        motions_for_ves = cur.execute(
            f"SELECT DISTINCT motion_id FROM vote_event WHERE id IN ({placeholders})",
            ve_ids,
        ).fetchall()
        print(f"  Motions referenciadas: {[m[0] for m in motions_for_ves]}")

        if args.dry_run:
            print(f"  [DRY-RUN] DELETE FROM count WHERE vote_event_id IN ({len(ve_ids)} VEs)")
            print(f"  [DRY-RUN] DELETE FROM vote_event WHERE id IN ({len(ve_ids)} VEs)")
        else:
            # Delete counts first (FK dependency)
            if counts_for_ves > 0:
                cur.execute(f"DELETE FROM count WHERE vote_event_id IN ({placeholders})", ve_ids)
                print(f"  ✓ Counts eliminados: {cur.rowcount}")

            # Delete VEs
            cur.execute(f"DELETE FROM vote_event WHERE id IN ({placeholders})", ve_ids)
            print(f"  ✓ VEs eliminados: {cur.rowcount}")

    # ========================================================================
    # 2. Limpiar orgs basura residuales
    # ========================================================================
    print()
    print("=" * 60)
    print("2. ORGANIZACIONES BASURA RESIDUALES")
    print("=" * 60)

    for org_id in sorted(BASURA_ORG_IDS):
        row = cur.execute(
            "SELECT id, nombre, clasificacion FROM organization WHERE id = ?", (org_id,)
        ).fetchone()
        if not row:
            print(f"  {org_id}: ya no existe, OK")
            continue

        print(f"  {org_id} '{row[1]}' encontrada")

        # Count associated records
        cnt_counts = cur.execute(
            "SELECT COUNT(*) FROM count WHERE group_id = ?", (org_id,)
        ).fetchone()[0]
        cnt_votes = cur.execute(
            'SELECT COUNT(*) FROM vote WHERE "group" = ?', (org_id,)
        ).fetchone()[0]
        cnt_memberships = cur.execute(
            "SELECT COUNT(*) FROM membership WHERE org_id = ?", (org_id,)
        ).fetchone()[0]

        print(f"    counts={cnt_counts}, votes={cnt_votes}, memberships={cnt_memberships}")

        if args.dry_run:
            print(f"    [DRY-RUN] DELETE FROM count WHERE group_id = '{org_id}'")
            print(f"    [DRY-RUN] DELETE FROM organization WHERE id = '{org_id}'")
        else:
            if cnt_counts > 0:
                cur.execute("DELETE FROM count WHERE group_id = ?", (org_id,))
                print(f"    ✓ Counts eliminados: {cur.rowcount}")
            if cnt_memberships > 0:
                print(f"    ⚠ Memberships encontrados ({cnt_memberships}) — revisar manualmente")
            else:
                cur.execute("DELETE FROM organization WHERE id = ?", (org_id,))
                print(f"    ✓ Org eliminada: {cur.rowcount}")

    # ========================================================================
    # 3. Resumen final
    # ========================================================================
    if not args.dry_run:
        conn.commit()

    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)

    total_ve = cur.execute("SELECT COUNT(*) FROM vote_event").fetchone()[0]
    total_counts = cur.execute("SELECT COUNT(*) FROM count").fetchone()[0]
    total_orgs = cur.execute("SELECT COUNT(*) FROM organization").fetchone()[0]
    total_votes = cur.execute("SELECT COUNT(*) FROM vote").fetchone()[0]

    print(f"  vote_events: {total_ve}")
    print(f"  votes: {total_votes}")
    print(f"  counts: {total_counts}")
    print(f"  organizations: {total_orgs}")

    if args.dry_run:
        print("\n  (DRY-RUN — no se hicieron cambios)")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
