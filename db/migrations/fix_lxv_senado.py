#!/usr/bin/env python3
"""
fix_lxv_senado.py — Reclasifica 835 VEs del Senado LXV mal clasificadas como LXVI.

Problema:
    El parser lxvi_portal.py tiene un fallback que hardcodea "LXVI" cuando no
    detecta texto de legislatura en el HTML. Esto causó que ~835 VEs de la LXV
    Legislatura (2021-09-01 a 2024-08-31) se clasificaran como LXVI.

    El portal /66/ sirve votaciones de LX a LXVI, pero solo las legislaturas
    LX-LXV incluyen explícitamente "LX LEGISLATURA" en el <h3>. La LXVI
    (actual al momento del scraping) no lo hace.

Criterio de reclasificación:
    - id LIKE 'VE_S%' (solo Senado)
    - legislatura = 'LXVI' (mal clasificadas)
    - start_date >= '2021-09-01' AND start_date < '2024-09-01' (rango LXV)

Esperado:
    - LXV: 6 → ~841
    - LXVI: 1,192 → ~357

Seguridad:
    - Solo UPDATE, no INSERT/DELETE.
    - Transacción con commit explícito.
    - Verificación de counts antes y después.

Uso:  .venv/bin/python3 db/migrations/fix_lxv_senado.py
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")


def main():
    print("=" * 65)
    print("Fix LXV Senado — Reclasificar VEs mal clasificadas como LXVI")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] Base de datos no encontrada: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # ── 1. Estado ANTES ──────────────────────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("ESTADO ANTES")
    print(f"{'─' * 65}")
    cur.execute("""
        SELECT legislatura, COUNT(*), MIN(start_date), MAX(start_date)
        FROM vote_event
        WHERE id LIKE 'VE_S%'
        GROUP BY legislatura
        ORDER BY legislatura
    """)
    for leg, cnt, dmin, dmax in cur.fetchall():
        print(f"  {leg}: {cnt} VEs | {dmin} → {dmax}")

    # ── 2. Contar candidatas ─────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*), MIN(id), MAX(id), MIN(source_id), MAX(source_id)
        FROM vote_event
        WHERE id LIKE 'VE_S%'
          AND legislatura = 'LXVI'
          AND start_date >= '2021-09-01'
          AND start_date < '2024-09-01'
    """)
    count, id_min, id_max, sid_min, sid_max = cur.fetchone()
    print(f"\n  VEs a reclasificar: {count}")
    print(f"  ID range: {id_min} → {id_max}")
    print(f"  source_id range: {sid_min} → {sid_max}")

    if count == 0:
        print("\n  ✓ No hay VEs que reclasificar. Nada que hacer.")
        conn.close()
        return 0

    # ── 3. Aplicar UPDATE ─────────────────────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("APLICANDO CAMBIOS")
    print(f"{'─' * 65}")

    cur.execute("""
        UPDATE vote_event
        SET legislatura = 'LXV'
        WHERE id LIKE 'VE_S%'
          AND legislatura = 'LXVI'
          AND start_date >= '2021-09-01'
          AND start_date < '2024-09-01'
    """)
    updated = cur.rowcount
    print(f"  Filas actualizadas: {updated}")

    conn.commit()
    print("  ✓ Commit exitoso.")

    # ── 4. Estado DESPUÉS ─────────────────────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("ESTADO DESPUÉS")
    print(f"{'─' * 65}")
    cur.execute("""
        SELECT legislatura, COUNT(*), MIN(start_date), MAX(start_date)
        FROM vote_event
        WHERE id LIKE 'VE_S%'
        GROUP BY legislatura
        ORDER BY legislatura
    """)
    for leg, cnt, dmin, dmax in cur.fetchall():
        print(f"  {leg}: {cnt} VEs | {dmin} → {dmax}")

    # ── 5. Sanity check ──────────────────────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("SANITY CHECK")
    print(f"{'─' * 65}")

    # LXV debe tener fechas exclusivamente en el rango 2021-09-01 a 2024-08-31
    cur.execute("""
        SELECT COUNT(*) FROM vote_event
        WHERE id LIKE 'VE_S%'
          AND legislatura = 'LXV'
          AND (start_date < '2021-09-01' OR start_date >= '2024-09-01')
    """)
    fuera_rango = cur.fetchone()[0]
    if fuera_rango > 0:
        print(f"  ⚠ LXV tiene {fuera_rango} VEs fuera del rango esperado!")
    else:
        print("  ✓ LXV: todas las VEs en rango 2021-09-01 a 2024-08-31")

    # LXVI no debe tener VEs antes de 2024-09-01
    cur.execute("""
        SELECT COUNT(*) FROM vote_event
        WHERE id LIKE 'VE_S%'
          AND legislatura = 'LXVI'
          AND start_date < '2024-09-01'
    """)
    lxvi_antes = cur.fetchone()[0]
    if lxvi_antes > 0:
        print(f"  ⚠ LXVI aún tiene {lxvi_antes} VEs antes de 2024-09-01!")
    else:
        print("  ✓ LXVI: sin VEs antes de 2024-09-01")

    # Total debe mantenerse
    cur.execute("SELECT COUNT(*) FROM vote_event WHERE id LIKE 'VE_S%'")
    total = cur.fetchone()[0]
    print(f"  ✓ Total VEs Senado: {total}")

    conn.close()
    print(f"\n{'=' * 65}")
    print("Migración completada exitosamente")
    print(f"{'=' * 65}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
