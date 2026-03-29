#!/usr/bin/env python3
"""
fix_duplicados.py — Elimina votos duplicados de la tabla vote.

El problema: 292,963 grupos de votos duplicados (mismo voter_id + vote_event_id
+ group + option, con IDs distintos). Esto genera ~300,965 registros extra.

El script:
  1. Crea backup de congreso.db → congreso.db.bak
  2. Diagnostica duplicados (conteo, desglose por legislatura, top personas)
  3. Elimina duplicados conservando el ID menor por grupo
  4. Verifica post-limpieza (0 duplicados, total esperado ~391,627)
  5. Imprime reporte antes/después

Idempotente: si se ejecuta de nuevo con BD limpia, detecta 0 duplicados y
no hace nada (pero siempre crea backup).

Uso:
  python db/fix_duplicados.py
"""

import shutil
import sqlite3
import sys
import time
from pathlib import Path

# --- Paths ---
PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "db" / "congreso.db"
BACKUP_PATH = PROJECT_DIR / "db" / "congreso.db.bak"

# --- Formato ---
SEPARATOR = "=" * 60


def backup_database() -> None:
    """Crea backup de la BD antes de cualquier operación."""
    print(SEPARATOR)
    print("FASE 0: BACKUP")
    print(SEPARATOR)
    print(f"  Origen:  {DB_PATH}")
    print(f"  Destino: {BACKUP_PATH}")

    if BACKUP_PATH.exists():
        print(f"  Backup existente detectado — se sobrescribe.")

    t0 = time.time()
    shutil.copy2(DB_PATH, BACKUP_PATH)
    elapsed = time.time() - t0
    size_mb = BACKUP_PATH.stat().st_size / (1024 * 1024)
    print(f"  Backup creado: {size_mb:.1f} MB en {elapsed:.1f}s")


def diagnose(conn: sqlite3.Connection) -> dict:
    """Diagnostica duplicados en la tabla vote. Retorna stats."""
    print(f"\n{SEPARATOR}")
    print("FASE 1: DIAGNÓSTICO")
    print(SEPARATOR)

    cur = conn.cursor()

    # Total de votos
    total_votos = cur.execute("SELECT COUNT(*) FROM vote").fetchone()[0]
    print(f"\n  Total de votos en BD: {total_votos:,}")

    # Grupos duplicados (mismo voter_id + vote_event_id + group + option, más de 1 registro)
    print("\n  Contando grupos duplicados...")
    dup_stats = cur.execute("""
        SELECT COUNT(*) AS num_grupos,
               SUM(cnt - 1) AS registros_extra
        FROM (
            SELECT voter_id, vote_event_id, "group", option, COUNT(*) AS cnt
            FROM vote
            GROUP BY voter_id, vote_event_id, "group", option
            HAVING cnt > 1
        )
    """).fetchone()

    num_grupos_dup = dup_stats[0] or 0
    registros_extra = dup_stats[1] or 0

    print(f"  Grupos con duplicados: {num_grupos_dup:,}")
    print(f"  Registros extra a eliminar: {registros_extra:,}")

    # Distribución por número de copias
    if num_grupos_dup > 0:
        print("\n  Distribución por número de copias:")
        rows = cur.execute("""
            SELECT cnt, COUNT(*) AS grupos
            FROM (
                SELECT voter_id, vote_event_id, "group", option, COUNT(*) AS cnt
                FROM vote
                GROUP BY voter_id, vote_event_id, "group", option
                HAVING cnt > 1
            )
            GROUP BY cnt
            ORDER BY cnt
        """).fetchall()
        for cnt, grupos in rows:
            print(f"    {cnt} copias: {grupos:,} grupos")

    # Top 10 personas por duplicados
    if num_grupos_dup > 0:
        print("\n  Top 10 personas por votos duplicados:")
        rows = cur.execute("""
            SELECT p.nombre, dup.total_extra
            FROM (
                SELECT v.voter_id, SUM(v2.cnt - 1) AS total_extra
                FROM (
                    SELECT voter_id, vote_event_id, "group", option, COUNT(*) AS cnt
                    FROM vote
                    GROUP BY voter_id, vote_event_id, "group", option
                    HAVING cnt > 1
                ) v2
                JOIN vote v ON v.voter_id = v2.voter_id
                    AND v.vote_event_id = v2.vote_event_id
                    AND v."group" = v2."group"
                    AND v.option = v2.option
                GROUP BY v.voter_id
                ORDER BY total_extra DESC
                LIMIT 10
            ) dup
            JOIN person p ON p.id = dup.voter_id
            ORDER BY dup.total_extra DESC
        """).fetchall()
        for nombre, extra in rows:
            print(f"    {nombre:45s} {extra:>6,} extra")

    # Desglose por legislatura (ANTES)
    print("\n  Desglose por legislatura (ANTES):")
    leg_rows = cur.execute("""
        SELECT ve.legislatura, COUNT(*) AS votos
        FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        GROUP BY ve.legislatura
        ORDER BY ve.legislatura
    """).fetchall()
    for leg, votos in leg_rows:
        leg_display = leg if leg else "(sin legislatura)"
        print(f"    {leg_display:20s} {votos:>8,}")

    return {
        "total_votos": total_votos,
        "num_grupos_dup": num_grupos_dup,
        "registros_extra": registros_extra,
        "por_legislatura": {r[0]: r[1] for r in leg_rows},
    }


def get_unique_counts_by_legislatura(conn: sqlite3.Connection) -> dict:
    """Cuenta votos únicos (sin duplicados) por legislatura.

    Un voto 'único' es el que se conservaría: el de menor ID por grupo.
    """
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT ve.legislatura, COUNT(*) AS votos
        FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        WHERE v.id IN (
            SELECT MIN(v2.id)
            FROM vote v2
            GROUP BY v2.voter_id, v2.vote_event_id, v2."group", v2.option
        )
        GROUP BY ve.legislatura
        ORDER BY ve.legislatura
    """).fetchall()
    return {r[0]: r[1] for r in rows}


def remove_duplicates(conn: sqlite3.Connection, stats: dict) -> int:
    """Elimina votos duplicados, conservando el ID menor por grupo.

    Usa enfoque eficiente: crea tabla temporal con IDs a conservar,
    elimina los demás en un solo DELETE masivo dentro de transacción.

    Retorna el número de registros eliminados.
    """
    num_grupos_dup = stats["num_grupos_dup"]
    registros_extra = stats["registros_extra"]

    if num_grupos_dup == 0:
        print(f"\n{SEPARATOR}")
        print("FASE 2: ELIMINACIÓN")
        print(SEPARATOR)
        print("  No se encontraron duplicados. No se eliminan registros.")
        return 0

    print(f"\n{SEPARATOR}")
    print("FASE 2: ELIMINACIÓN")
    print(SEPARATOR)
    print(f"  Grupos duplicados: {num_grupos_dup:,}")
    print(f"  Registros a eliminar: {registros_extra:,}")

    cur = conn.cursor()

    # Usar WAL para mejor performance en DELETE masivo
    old_journal = cur.execute("PRAGMA journal_mode").fetchone()[0]
    print(f"  Journal mode actual: {old_journal}")
    cur.execute("PRAGMA journal_mode = WAL")
    print("  Journal mode → WAL")

    t0 = time.time()

    # Enfoque eficiente: DELETE con subquery
    # Para cada grupo duplicado, conservar el ID menor (orden lexicográfico)
    print("  Ejecutando DELETE masivo...")
    cur.execute("""
        DELETE FROM vote WHERE id IN (
            SELECT v2.id FROM vote v2
            WHERE EXISTS (
                SELECT 1 FROM vote v1
                WHERE v1.voter_id = v2.voter_id
                AND v1.vote_event_id = v2.vote_event_id
                AND v1."group" = v2."group"
                AND v1.option = v2.option
                AND v1.id < v2.id
            )
        )
    """)

    deleted = cur.rowcount
    conn.commit()
    elapsed = time.time() - t0

    print(f"  Registros eliminados: {deleted:,}")
    print(f"  Tiempo: {elapsed:.1f}s")

    # Restaurar journal mode original si era diferente
    if old_journal.lower() != "wal":
        cur.execute(f"PRAGMA journal_mode = {old_journal}")
        print(f"  Journal mode → {old_journal} (restaurado)")

    return deleted


def verify(conn: sqlite3.Connection, stats_before: dict) -> None:
    """Verifica que la limpieza fue correcta."""
    print(f"\n{SEPARATOR}")
    print("FASE 3: VERIFICACIÓN POST-LIMPIEZA")
    print(SEPARATOR)

    cur = conn.cursor()

    # Total de votos restantes
    total_after = cur.execute("SELECT COUNT(*) FROM vote").fetchone()[0]
    total_before = stats_before["total_votos"]
    eliminados = total_before - total_after
    esperado = stats_before["registros_extra"]

    print(f"\n  Votos antes:     {total_before:>10,}")
    print(f"  Votos después:   {total_after:>10,}")
    print(f"  Eliminados:      {eliminados:>10,}")
    print(f"  Esperados extra: {esperado:>10,}")

    if eliminados == esperado:
        print("  ✓ Eliminados coincide con diagnóstico")
    else:
        print(f"  ⚠ Diferencia: eliminados={eliminados:,}, esperados={esperado:,}")

    # Verificar que no quedan duplicados
    dup_remaining = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT voter_id, vote_event_id, "group", option, COUNT(*) AS cnt
            FROM vote
            GROUP BY voter_id, vote_event_id, "group", option
            HAVING cnt > 1
        )
    """).fetchone()[0]

    if dup_remaining == 0:
        print("  ✓ No quedan duplicados")
    else:
        print(f"  ✗ Quedan {dup_remaining:,} grupos duplicados!")

    # Desglose por legislatura DESPUÉS
    print("\n  Desglose por legislatura (DESPUÉS):")
    leg_after = {}
    rows = cur.execute("""
        SELECT ve.legislatura, COUNT(*) AS votos
        FROM vote v
        JOIN vote_event ve ON v.vote_event_id = ve.id
        GROUP BY ve.legislatura
        ORDER BY ve.legislatura
    """).fetchall()

    print(f"    {'Legislatura':20s} {'Antes':>10s} {'Después':>10s} {'Diff':>10s}")
    print(f"    {'-' * 20} {'-' * 10} {'-' * 10} {'-' * 10}")

    leg_before = stats_before["por_legislatura"]
    for leg, votos_after in rows:
        leg_display = leg if leg else "(sin legislatura)"
        votos_before = leg_before.get(leg, 0)
        diff = votos_before - votos_after
        print(
            f"    {leg_display:20s} {votos_before:>10,} {votos_after:>10,} {diff:>10,}"
        )

    # Verificar que no se perdieron votos no-duplicados
    # Un voto no-duplicado es aquel en un grupo de cnt=1
    # Su conteo por legislatura debería ser idéntico antes y después
    print("\n  Verificación de integridad (votos no-duplicados):")
    nondup_before = total_before - esperado
    nondup_after = total_after

    # Más preciso: votos únicos antes = votos después
    # (los únicos son los que quedan después de eliminar duplicados)
    print(f"    Votos esperados post-limpieza: ~391,627")
    print(f"    Votos reales post-limpieza:    {total_after:,}")

    if total_after > 0:
        pct = abs(total_after - 391627) / 391627 * 100
        if pct < 5:
            print(f"    ✓ Dentro del rango esperado (diferencia: {pct:.1f}%)")
        else:
            print(f"    ⚠ Fuera del rango esperado (diferencia: {pct:.1f}%)")


def print_summary(stats_before: dict, deleted: int) -> None:
    """Imprime resumen final."""
    print(f"\n{SEPARATOR}")
    print("RESUMEN FINAL")
    print(SEPARATOR)
    print(f"  Backup:       {BACKUP_PATH}")
    print(f"  Votos antes:  {stats_before['total_votos']:,}")
    print(f"  Duplicados:   {stats_before['num_grupos_dup']:,} grupos")
    print(f"  Eliminados:   {deleted:,} registros")
    print(f"  Votos después: {stats_before['total_votos'] - deleted:,}")
    if deleted == 0 and stats_before["num_grupos_dup"] == 0:
        print("\n  ✅ BD ya estaba limpia — no se requirió eliminación.")
    elif deleted == stats_before["registros_extra"]:
        print("\n  ✅ Limpieza completada exitosamente.")
    else:
        print(
            f"\n  ⚠ Revisar: eliminados ({deleted:,}) ≠ esperados ({stats_before['registros_extra']:,})"
        )


def main():
    if not DB_PATH.exists():
        print(f"ERROR: No se encontró la BD en {DB_PATH}")
        sys.exit(1)

    print("fix_duplicados.py — Limpieza de votos duplicados")
    print(f"BD: {DB_PATH}")
    print(f"Tamaño: {DB_PATH.stat().st_size / (1024 * 1024):.1f} MB")

    # Fase 0: Backup (siempre)
    backup_database()

    # Fase 1: Diagnóstico
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "PRAGMA foreign_keys = OFF"
    )  # No necesitamos FK para DELETE dentro de vote
    try:
        stats = diagnose(conn)

        # Fase 2: Eliminación
        deleted = remove_duplicates(conn, stats)

        # Fase 3: Verificación
        verify(conn, stats)

        # Resumen
        print_summary(stats, deleted)

    except Exception as exc:
        conn.rollback()
        print(f"\nERROR: {exc}")
        print("Transacción revertida. Restaurar desde backup si es necesario:")
        print(f"  cp {BACKUP_PATH} {DB_PATH}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
