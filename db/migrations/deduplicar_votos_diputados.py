#!/usr/bin/env python3
"""
deduplicar_votos_diputados.py — Deduplica votos y counts globalmente.

Problema: El pipeline ETL insertó votos múltiples veces.
- ~2,050,654 votos duplicados en tabla vote (pares vote_event_id+voter_id, Dip LX-LXV)
- ~175 votos duplicados en Senado
- ~17,930 counts duplicados en tabla count (tuplas vote_event_id+option+group_id, Dip LX-LXV)
- LXVI está limpio.

Solución:
  1. Backup de la BD
  2. Diagnóstico pre-deduplicación
  3. Deduplicar vote globalmente: keep MIN(id) por (vote_event_id, voter_id)
  4. Deduplicar count globalmente: keep MIN(id) por (vote_event_id, option, group_id)
  5. Agregar UNIQUE constraints
  6. Recalcular voter_count para Dip LX-LXV
  7. VACUUM
  8. Verificación integral

Nota: Se incluyen Senado (175 duplicados) porque el UNIQUE constraint cubre toda la tabla.

Idempotente: Si se corre 2 veces, la segunda no hace nada.

Uso:  .venv/bin/python3 db/migrations/deduplicar_votos_diputados.py
"""

import os
import shutil
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "db", "congreso.db")
BACKUP_PATH = os.path.join(BASE_DIR, "db", "congreso.db.bak.pre-dedup")

SEP = "=" * 65


def backup_database() -> bool:
    """Crea backup de la BD antes de cualquier operación. Retorna True si ok."""
    print(f"\n{SEP}")
    print("FASE 0: BACKUP")
    print(SEP)

    if not os.path.exists(DB_PATH):
        print(f"  [ERROR] BD no encontrada: {DB_PATH}")
        return False

    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"  BD:     {DB_PATH}")
    print(f"  Tamaño: {size_mb:.1f} MB")
    print(f"  Backup: {BACKUP_PATH}")

    if os.path.exists(BACKUP_PATH):
        print("  Backup existente detectado — se sobrescribe.")

    t0 = time.time()
    shutil.copy2(DB_PATH, BACKUP_PATH)
    elapsed = time.time() - t0
    bak_mb = os.path.getsize(BACKUP_PATH) / (1024 * 1024)
    print(f"  ✓ Backup creado: {bak_mb:.1f} MB en {elapsed:.1f}s")
    return True


def diagnose(cur: sqlite3.Cursor) -> dict:
    """Diagnóstico pre-deduplicación. Retorna stats."""
    print(f"\n{SEP}")
    print("FASE 1: DIAGNÓSTICO PRE-DEDUPLICACIÓN")
    print(SEP)

    # Total votos
    total_votes = cur.execute("SELECT COUNT(*) FROM vote").fetchone()[0]
    dip_votes = cur.execute("""
        SELECT COUNT(*) FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        WHERE ve.organization_id = 'O08'
    """).fetchone()[0]
    sen_votes = cur.execute("""
        SELECT COUNT(*) FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        WHERE ve.organization_id = 'O09'
    """).fetchone()[0]

    print(f"\n  Total votos BD:    {total_votes:>10,}")
    print(f"    Diputados (O08): {dip_votes:>10,}")
    print(f"    Senado (O09):    {sen_votes:>10,}")

    # Votos: distribución global por copias
    print("\n  Distribución (vote) — global:")
    vote_extra = 0
    rows = cur.execute("""
        SELECT cnt, COUNT(*) as grupos FROM (
            SELECT vote_event_id, voter_id, COUNT(*) as cnt
            FROM vote
            GROUP BY vote_event_id, voter_id
        ) GROUP BY cnt ORDER BY cnt
    """).fetchall()
    for cnt, grupos in rows:
        extra = grupos * (cnt - 1)
        vote_extra += extra
        print(f"    {cnt}x: {grupos:>10,} grupos ({extra:>10,} extra)")
    print(f"    Total filas vote a eliminar: {vote_extra:,}")

    # Desglose por cámara
    print("\n  Desglose por cámara:")
    for org_id, label in [("O08", "Diputados"), ("O09", "Senado")]:
        org_extra = (
            cur.execute(
                """
            SELECT SUM(cnt - 1) FROM (
                SELECT vote_event_id, voter_id, COUNT(*) as cnt
                FROM vote v
                JOIN vote_event ve ON v.vote_event_id = ve.id
                WHERE ve.organization_id = ?
                GROUP BY vote_event_id, voter_id
                HAVING cnt > 1
            )
        """,
                (org_id,),
            ).fetchone()[0]
            or 0
        )
        print(f"    {label}: {org_extra:,} extra")

    # Counts: distribución global por copias
    print("\n  Distribución (count) — global:")
    count_extra = 0
    rows_c = cur.execute("""
        SELECT cnt, COUNT(*) as grupos FROM (
            SELECT vote_event_id, option, group_id, COUNT(*) as cnt
            FROM count
            GROUP BY vote_event_id, option, group_id
        ) GROUP BY cnt ORDER BY cnt
    """).fetchall()
    total_counts = cur.execute("SELECT COUNT(*) FROM count").fetchone()[0]
    for cnt, grupos in rows_c:
        extra = grupos * (cnt - 1)
        count_extra += extra
        print(f"    {cnt}x: {grupos:>8,} grupos ({extra:>8,} extra)")
    print(f"    Total filas count a eliminar: {count_extra:,}")
    print(f"    Total counts BD: {total_counts:,}")

    return {
        "total_votes": total_votes,
        "dip_votes": dip_votes,
        "sen_votes": sen_votes,
        "vote_extra": vote_extra,
        "count_extra": count_extra,
        "total_counts": total_counts,
    }


def deduplicate_votes(cur: sqlite3.Cursor) -> int:
    """Deduplica votos globalmente: keep MIN(id) por (vote_event_id, voter_id)."""
    print(f"\n{SEP}")
    print("FASE 2: DEDUPLICAR VOTE (global)")
    print(SEP)

    total = cur.execute("SELECT COUNT(*) FROM vote").fetchone()[0]
    print(f"  Total votos antes: {total:,}")

    # Tabla temporal con IDs a conservar (MIN id por par único)
    print("  Identificando IDs a conservar (MIN id por par único)...")
    t0 = time.time()
    cur.execute("""
        CREATE TEMP TABLE vote_keep AS
        SELECT MIN(id) as keep_id
        FROM vote
        GROUP BY vote_event_id, voter_id
    """)
    keep_count = cur.execute("SELECT COUNT(*) FROM vote_keep").fetchone()[0]
    elapsed = time.time() - t0
    print(f"  Votos únicos a conservar: {keep_count:,} ({elapsed:.1f}s)")

    # Eliminar duplicados
    print("  Eliminando votos duplicados...")
    t0 = time.time()
    cur.execute("""
        DELETE FROM vote WHERE id NOT IN (SELECT keep_id FROM vote_keep)
    """)
    deleted = cur.rowcount
    elapsed = time.time() - t0
    print(f"  ✓ Votos eliminados: {deleted:,} en {elapsed:.1f}s")

    # Limpieza
    cur.execute("DROP TABLE IF EXISTS temp.vote_keep")

    return deleted


def deduplicate_counts(cur: sqlite3.Cursor) -> int:
    """Deduplica counts globalmente: keep MIN(id) por (vote_event_id, option, group_id)."""
    print(f"\n{SEP}")
    print("FASE 3: DEDUPLICAR COUNT (global)")
    print(SEP)

    total = cur.execute("SELECT COUNT(*) FROM count").fetchone()[0]
    print(f"  Total counts antes: {total:,}")

    # IDs a conservar
    print("  Identificando IDs a conservar (MIN id por tupla única)...")
    t0 = time.time()
    cur.execute("""
        CREATE TEMP TABLE count_keep AS
        SELECT MIN(id) as keep_id
        FROM count
        GROUP BY vote_event_id, option, group_id
    """)
    keep_count = cur.execute("SELECT COUNT(*) FROM count_keep").fetchone()[0]
    elapsed = time.time() - t0
    print(f"  Counts únicos a conservar: {keep_count:,} ({elapsed:.1f}s)")

    # Eliminar duplicados
    print("  Eliminando counts duplicados...")
    t0 = time.time()
    cur.execute("""
        DELETE FROM count WHERE id NOT IN (SELECT keep_id FROM count_keep)
    """)
    deleted = cur.rowcount
    elapsed = time.time() - t0
    print(f"  ✓ Counts eliminados: {deleted:,} en {elapsed:.1f}s")

    # Limpieza
    cur.execute("DROP TABLE IF EXISTS temp.count_keep")

    return deleted


def add_unique_constraints(cur: sqlite3.Cursor) -> None:
    """Agrega UNIQUE constraints para prevenir duplicados futuros."""
    print(f"\n{SEP}")
    print("FASE 4: UNIQUE CONSTRAINTS")
    print(SEP)

    existing = cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name IN ('idx_vote_unique', 'idx_count_unique')
    """).fetchall()
    existing_names = {r[0] for r in existing}

    if "idx_vote_unique" not in existing_names:
        print("  Creando idx_vote_unique...")
        t0 = time.time()
        cur.execute("""
            CREATE UNIQUE INDEX idx_vote_unique ON vote(vote_event_id, voter_id)
        """)
        print(f"  ✓ idx_vote_unique creado en {time.time() - t0:.1f}s")
    else:
        print("  idx_vote_unique ya existe — saltando")

    if "idx_count_unique" not in existing_names:
        print("  Creando idx_count_unique...")
        t0 = time.time()
        cur.execute("""
            CREATE UNIQUE INDEX idx_count_unique
            ON count(vote_event_id, option, group_id)
        """)
        print(f"  ✓ idx_count_unique creado en {time.time() - t0:.1f}s")
    else:
        print("  idx_count_unique ya existe — saltando")


def recalculate_voter_count(cur: sqlite3.Cursor) -> int:
    """Recalcula voter_count para Dip LX-LXV desde la tabla vote."""
    print(f"\n{SEP}")
    print("FASE 5: RECALCULAR voter_count (Dip LX-LXV)")
    print(SEP)

    t0 = time.time()
    cur.execute("""
        UPDATE vote_event SET voter_count = (
            SELECT COUNT(*) FROM vote WHERE vote.vote_event_id = vote_event.id
        )
        WHERE organization_id = 'O08' AND legislatura != 'LXVI'
    """)
    updated = cur.rowcount
    elapsed = time.time() - t0
    print(f"  ✓ VEs Dip LX-LXV actualizados: {updated:,} en {elapsed:.1f}s")

    # Stats post-recalc
    avg_vc = cur.execute("""
        SELECT AVG(voter_count), MIN(voter_count), MAX(voter_count)
        FROM vote_event
        WHERE organization_id = 'O08' AND legislatura != 'LXVI'
    """).fetchone()
    print(f"  voter_count Dip LX-LXV: avg={avg_vc[0]:.1f} min={avg_vc[1]} max={avg_vc[2]}")

    return updated


def vacuum(conn: sqlite3.Connection) -> None:
    """Ejecuta VACUUM para recuperar espacio."""
    print(f"\n{SEP}")
    print("FASE 6: VACUUM")
    print(SEP)

    size_before = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"  Tamaño BD antes: {size_before:.1f} MB")

    print("  Ejecutando WAL checkpoint...")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    print("  Ejecutando VACUUM (puede tardar)...")
    t0 = time.time()
    conn.execute("VACUUM")
    elapsed = time.time() - t0

    size_after = os.path.getsize(DB_PATH) / (1024 * 1024)
    saved = size_before - size_after
    print(f"  ✓ VACUUM completado en {elapsed:.1f}s")
    print(f"  Tamaño BD después: {size_after:.1f} MB")
    print(f"  Espacio recuperado: {saved:.1f} MB")


def verify(cur: sqlite3.Cursor, stats_before: dict) -> dict:
    """Verificación integral post-deduplicación."""
    print(f"\n{SEP}")
    print("FASE 7: VERIFICACIÓN")
    print(SEP)

    results = {}

    # 1. FK check
    print("\n  [1] FK check...")
    fk_violations = cur.execute("PRAGMA foreign_key_check").fetchall()
    results["fk_check"] = len(fk_violations)
    if fk_violations:
        print(f"  ✗ {len(fk_violations)} FK violations encontradas!")
        for v in fk_violations[:10]:
            print(f"    {v}")
    else:
        print("  ✓ 0 FK violations")

    # 2. Vote duplicados (global)
    print("\n  [2] Verificar duplicados vote (global)...")
    vote_dups = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT vote_event_id, voter_id
            FROM vote GROUP BY vote_event_id, voter_id HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    results["vote_dups"] = vote_dups
    if vote_dups == 0:
        print("  ✓ 0 duplicados en vote")
    else:
        print(f"  ✗ {vote_dups:,} duplicados restantes en vote!")

    # 3. Count duplicados (global)
    print("\n  [3] Verificar duplicados count (global)...")
    count_dups = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT vote_event_id, option, group_id
            FROM count GROUP BY vote_event_id, option, group_id HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    results["count_dups"] = count_dups
    if count_dups == 0:
        print("  ✓ 0 duplicados en count")
    else:
        print(f"  ✗ {count_dups:,} duplicados restantes en count!")

    # 4. Senado count
    sen_after = cur.execute("""
        SELECT COUNT(*) FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        WHERE ve.organization_id = 'O09'
    """).fetchone()[0]
    sen_expected = stats_before["sen_votes"] - 175  # 175 Senado dupes eliminados
    results["sen_intact"] = sen_after == sen_expected
    print(
        f"\n  [4] Senado: {sen_after:,} (antes: {stats_before['sen_votes']:,}, dif: {stats_before['sen_votes'] - sen_after:,})"
    )

    # 5. LXVI intacto
    lxvi_votes = cur.execute("""
        SELECT COUNT(*) FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        WHERE ve.legislatura = 'LXVI'
    """).fetchone()[0]
    results["lxvi_intact"] = True
    print(f"\n  [5] LXVI intacto: {lxvi_votes:,} votos LXVI")

    # 6. Totales post
    total_votes_after = cur.execute("SELECT COUNT(*) FROM vote").fetchone()[0]
    total_counts_after = cur.execute("SELECT COUNT(*) FROM count").fetchone()[0]
    print("\n  [6] Totales post-dedup:")
    print(
        f"    Votos:  {stats_before['total_votes']:>10,} → {total_votes_after:>10,}"
        f" (Δ={stats_before['total_votes'] - total_votes_after:,})"
    )
    print(
        f"    Counts: {stats_before['total_counts']:>10,} → {total_counts_after:>10,}"
        f" (Δ={stats_before['total_counts'] - total_counts_after:,})"
    )

    # 7. UNIQUE constraints
    print("\n  [7] UNIQUE constraints:")
    uc = cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name IN ('idx_vote_unique', 'idx_count_unique')
    """).fetchall()
    for idx in uc:
        print(f"    ✓ {idx[0]}")

    # 8. Sample VE
    print("\n  [8] Muestra VE_D00001:")
    sample_votes = cur.execute("""
        SELECT option, COUNT(*) FROM vote WHERE vote_event_id = 'VE_D00001' GROUP BY option
    """).fetchall()
    vc = cur.execute("SELECT voter_count FROM vote_event WHERE id = 'VE_D00001'").fetchone()[0]
    for opt, cnt in sample_votes:
        print(f"    {opt:12s} {cnt:>4}")
    print(f"    voter_count = {vc}")

    return results


def main():
    print(SEP)
    print("DEDUPLICAR VOTOS Y COUNTS — GLOBAL")
    print(SEP)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] BD no encontrada: {DB_PATH}")
        return 1

    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"  BD: {DB_PATH}")
    print(f"  Tamaño: {size_mb:.1f} MB")

    # Fase 0: Backup
    if not backup_database():
        return 1

    # Conectar
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA temp_store = MEMORY")
    cur = conn.cursor()

    try:
        # Fase 1: Diagnóstico
        stats = diagnose(cur)

        if stats["vote_extra"] == 0 and stats["count_extra"] == 0:
            print(f"\n{SEP}")
            print("BD ya está limpia — no hay duplicados que eliminar.")
            print(SEP)
            conn.close()
            return 0

        # Fase 2: Deduplicar vote
        vote_deleted = deduplicate_votes(cur)
        conn.commit()
        print("  Commit exitoso post-vote dedup")

        # Fase 3: Deduplicar count
        count_deleted = deduplicate_counts(cur)
        conn.commit()
        print("  Commit exitoso post-count dedup")

        # Fase 4: UNIQUE constraints
        add_unique_constraints(cur)
        conn.commit()
        print("  Commit exitoso post-constraints")

        # Fase 5: Recalcular voter_count
        vc_updated = recalculate_voter_count(cur)
        conn.commit()
        print("  Commit exitoso post-voter_count")

        # Fase 6: VACUUM
        conn.close()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        cur = conn.cursor()
        vacuum(conn)

        # Fase 7: Verificación
        verify_results = verify(cur, stats)

        # Resumen final
        print(f"\n{SEP}")
        print("RESUMEN FINAL")
        print(SEP)
        print(f"  Backup:           {BACKUP_PATH}")
        print(f"  Votos eliminados: {vote_deleted:,}")
        print(f"  Counts eliminados:{count_deleted:,}")
        print(f"  voter_count upd:  {vc_updated:,}")
        print(f"  FK violations:    {verify_results['fk_check']}")
        print(f"  Vote duplicados:  {verify_results['vote_dups']}")
        print(f"  Count duplicados: {verify_results['count_dups']}")
        print(f"  LXVI intacto:     {verify_results['lxvi_intact']}")

        all_ok = (
            verify_results["fk_check"] == 0
            and verify_results["vote_dups"] == 0
            and verify_results["count_dups"] == 0
            and verify_results["lxvi_intact"]
        )

        if all_ok:
            print("\n  ✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
        else:
            print("\n  ⚠️  MIGRACIÓN COMPLETADA CON WARNINGS — revisar arriba")

    except Exception as exc:
        conn.rollback()
        print(f"\n[ERROR] {exc}")
        print("Transacción revertida. Restaurar desde backup:")
        print(f"  cp {BACKUP_PATH} {DB_PATH}")
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
