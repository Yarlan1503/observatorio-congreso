#!/usr/bin/env python3
"""
deduplicar_counts_diputados.py — Deduplica counts globales de Diputados.

Problema: 2,870 VEs de Diputados tienen counts globales (group_id IS NULL)
multiplicados ×2-3. Cada VE tiene: 1 set correcto + 1 duplicado exacto +
1 set multiplicado (valor × N). Los per-party counts también están duplicados.

Resultado: ~14K filas redundantes en count, voter_count inflado ~2×.

Solución:
1. Para cada VE, deduplicar per-party counts (same option + group_id → keep MIN id)
2. Eliminar TODOS los counts globales duplicados
3. Recrear counts globales correctos (SUM de per-party counts)
4. Recalcular voter_count desde global counts deduplicados

Precaución: Los counts por partido (PAN, PRI, etc.) son legítimos — solo
los globales están duplicados.

Uso:  uv run python db/migrations/deduplicar_counts_diputados.py
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")


def main():
    print("=" * 65)
    print("Deduplicar counts globales de Diputados")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] Base de datos no encontrada: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # ── Phase 1: Stats before ──────────────────────────────────────
    total_counts = cur.execute(
        "SELECT COUNT(*) FROM count WHERE vote_event_id LIKE 'VE_D%'"
    ).fetchone()[0]
    total_global = cur.execute(
        "SELECT COUNT(*) FROM count WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NULL"
    ).fetchone()[0]
    total_per_party = cur.execute(
        "SELECT COUNT(*) FROM count WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NOT NULL"
    ).fetchone()[0]
    dup_ves = cur.execute(
        "SELECT COUNT(DISTINCT vote_event_id) FROM count "
        "WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NULL "
        "GROUP BY vote_event_id HAVING COUNT(*) > 4"
    ).fetchone()[0]

    print("\nCounts Diputados — ANTES:")
    print(f"  Total filas:        {total_counts:,}")
    print(f"  Globales (NULL):    {total_global:,}")
    print(f"  Por partido:        {total_per_party:,}")
    print(f"  VEs duplicados:     {dup_ves}")

    # ── Phase 2: Deduplicate per-party counts ──────────────────────
    print(f"\n{'─' * 65}")
    print("Phase 2: Deduplicar counts por partido")

    # Find duplicate per-party counts: same (vote_event_id, option, group_id)
    # but different IDs. Keep MIN(id), delete the rest.
    total_changes_before = conn.total_changes
    cur.execute("""
        DELETE FROM count
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM count
            WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NOT NULL
            GROUP BY vote_event_id, option, group_id
        )
        AND vote_event_id LIKE 'VE_D%'
        AND group_id IS NOT NULL
    """)
    deleted_per_party = conn.total_changes - total_changes_before
    print(f"  Counts por partido eliminados (duplicados): {deleted_per_party:,}")

    # ── Phase 3: Recreate global counts ────────────────────────────
    print(f"\n{'─' * 65}")
    print("Phase 3: Recrear counts globales correctos")

    # Delete ALL existing global counts for Diputados
    total_changes_before = conn.total_changes
    cur.execute("DELETE FROM count WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NULL")
    deleted_global = conn.total_changes - total_changes_before
    print(f"  Counts globales eliminados (todos): {deleted_global:,}")

    # Recreate from SUM of per-party counts
    # Get next available count ID
    max_id_row = cur.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM count WHERE id LIKE 'C%'"
    ).fetchone()
    max_id = max_id_row[0] if max_id_row[0] is not None else 0

    cur.execute(f"""
        INSERT INTO count (id, vote_event_id, option, value, group_id)
        SELECT
            'C' || printf('%05d', {max_id} + ROW_NUMBER() OVER (ORDER BY ve_id, opt)),
            ve_id,
            opt,
            SUM(val),
            NULL
        FROM (
            SELECT vote_event_id as ve_id, option as opt, value as val
            FROM count
            WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NOT NULL
        )
        GROUP BY ve_id, opt
        ORDER BY ve_id, opt
    """)
    inserted_global = conn.total_changes - total_changes_before
    print(f"  Counts globales insertados (correctos): {inserted_global:,}")

    # ── Phase 4: Handle VEs without per-party counts ──────────────
    # Some VEs might only have global counts (no per-party breakdown).
    # For those, use the vote table.
    ves_without_per_party = cur.execute("""
        SELECT DISTINCT ve.id
        FROM vote_event ve
        WHERE ve.id LIKE 'VE_D%'
        AND ve.id NOT IN (
            SELECT DISTINCT vote_event_id FROM count
            WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NOT NULL
        )
        AND ve.id IN (
            SELECT DISTINCT vote_event_id FROM vote WHERE vote_event_id LIKE 'VE_D%'
        )
    """).fetchall()

    if ves_without_per_party:
        print(f"\n  VEs sin counts por partido (usando vote table): {len(ves_without_per_party)}")
        # Update max_id after Phase 3 inserts
        max_id = cur.execute(
            "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM count WHERE id LIKE 'C%'"
        ).fetchone()[0]
        next_id = max_id + 1 if max_id else 1
        for (ve_id,) in ves_without_per_party:
            for opt_row in cur.execute(
                "SELECT option, COUNT(*) FROM vote WHERE vote_event_id = ? GROUP BY option",
                (ve_id,),
            ).fetchall():
                count_id = f"C{next_id:05d}"
                cur.execute(
                    "INSERT INTO count (id, vote_event_id, option, value, group_id) VALUES (?, ?, ?, ?, NULL)",
                    (count_id, ve_id, opt_row[0], opt_row[1]),
                )
                next_id += 1

    # ── Phase 5: Recalculate voter_count ───────────────────────────
    print(f"\n{'─' * 65}")
    print("Phase 5: Recalcular voter_count")

    total_changes_before = conn.total_changes
    cur.execute("""
        UPDATE vote_event
        SET voter_count = (
            SELECT COALESCE(SUM(value), 0)
            FROM count
            WHERE count.vote_event_id = vote_event.id
            AND count.group_id IS NULL
            AND count.option IN ('a_favor', 'en_contra', 'abstencion', 'ausente')
        )
        WHERE vote_event.id LIKE 'VE_D%'
    """)
    updated_voter_count = conn.total_changes - total_changes_before
    print(f"  VEs Diputados con voter_count actualizado: {updated_voter_count:,}")

    # ── Commit ─────────────────────────────────────────────────────
    conn.commit()
    print("\n  ✓ Commit exitoso.")

    # ── Phase 6: Stats after ───────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("ESTADÍSTICAS POST-DEDUPLICACIÓN")
    print(f"{'─' * 65}")

    total_counts_after = cur.execute(
        "SELECT COUNT(*) FROM count WHERE vote_event_id LIKE 'VE_D%'"
    ).fetchone()[0]
    total_global_after = cur.execute(
        "SELECT COUNT(*) FROM count WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NULL"
    ).fetchone()[0]
    total_per_party_after = cur.execute(
        "SELECT COUNT(*) FROM count WHERE vote_event_id LIKE 'VE_D%' AND group_id IS NOT NULL"
    ).fetchone()[0]

    print("\nCounts Diputados — DESPUÉS:")
    print(f"  Total filas:        {total_counts_after:,}")
    print(f"  Globales (NULL):    {total_global_after:,}")
    print(f"  Por partido:        {total_per_party_after:,}")
    print("\nDiferencia:")
    print(f"  Filas eliminadas:   {total_counts - total_counts_after:,}")
    print(f"  Counts globales:    {total_global} → {total_global_after}")
    print(f"  Counts por partido: {total_per_party} → {total_per_party_after}")

    # Sample verification
    print(f"\n{'─' * 65}")
    print("VERIFICACIÓN — VE_D00001")
    rows = cur.execute("""
        SELECT option, value, group_id FROM count
        WHERE vote_event_id = 'VE_D00001'
        ORDER BY group_id IS NULL, option, value
    """).fetchall()
    for r in rows:
        g = "GLOBAL" if r[2] is None else r[2]
        print(f"  {r[0]:12s} {r[1]:6d}  ({g})")

    vc = cur.execute("SELECT voter_count FROM vote_event WHERE id = 'VE_D00001'").fetchone()[0]
    print(f"  voter_count = {vc}")

    conn.close()
    print(f"\n{'=' * 65}")
    print("Deduplicación completada exitosamente")
    print(f"{'=' * 65}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
