#!/usr/bin/env python3
"""
purge_lxv_diputados.py — Purga datos corruptos de LXV Diputados.

Elimina vote_events, votes, counts y motions de la legislatura LXV
de la Cámara de Diputados (O08), para permitir re-scrape limpio.

Contexto: el scraper nominal.py sobreescribía el partido correcto con texto
del HTML span, causando memberships inflados 2.72x (1,437 vs 529 personas).

IDEMPOTENTE: puede ejecutarse múltiples veces sin error.
NO toca: person, membership, organization (datos de otras legislaturas intactos).
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "congreso.db"


def get_counts(conn, ve_ids: list[str]) -> dict:
    """Cuenta registros que serían eliminados para los VE dados."""
    if not ve_ids:
        return {"vote_events": 0, "votes": 0, "counts": 0, "motions": 0}

    placeholders = ",".join("?" * len(ve_ids))

    n_votes = conn.execute(
        f"SELECT COUNT(*) FROM vote WHERE vote_event_id IN ({placeholders})",
        ve_ids,
    ).fetchone()[0]

    n_counts = conn.execute(
        f"SELECT COUNT(*) FROM count WHERE vote_event_id IN ({placeholders})",
        ve_ids,
    ).fetchone()[0]

    # Motions vinculadas a estos VEs (pueden compartirse con Senado, pero
    # filtramos solo las de Diputados por el prefix Y_D)
    motion_ids = [
        row[0]
        for row in conn.execute(
            f"SELECT DISTINCT motion_id FROM vote_event WHERE id IN ({placeholders})",
            ve_ids,
        ).fetchall()
        if row[0]  # ignorar NULLs
    ]

    return {
        "vote_events": len(ve_ids),
        "votes": n_votes,
        "counts": n_counts,
        "motions": len(motion_ids),
        "motion_ids": motion_ids,
    }


def purge(conn, ve_ids: list[str], motion_ids: list[str]) -> None:
    """Ejecuta DELETE en orden de dependencias FK dentro de una transacción."""
    placeholders = ",".join("?" * len(ve_ids))

    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(f"DELETE FROM vote WHERE vote_event_id IN ({placeholders})", ve_ids)
        print("  ✓ Votes eliminados")

        conn.execute(f"DELETE FROM count WHERE vote_event_id IN ({placeholders})", ve_ids)
        print("  ✓ Counts eliminados")

        # Eliminar vote_events PRIMERO (para liberar FK references a motions)
        conn.execute(f"DELETE FROM vote_event WHERE id IN ({placeholders})", ve_ids)
        print("  ✓ Vote events eliminados")

        # Solo eliminar motions que ya NO están referenciadas por ningún vote_event
        if motion_ids:
            m_ph = ",".join("?" * len(motion_ids))
            orphan_motions = [
                row[0]
                for row in conn.execute(
                    f"""
                    SELECT m.id FROM motion m
                    WHERE m.id IN ({m_ph})
                      AND NOT EXISTS (
                      SELECT 1 FROM vote_event ve WHERE ve.motion_id = m.id
                    )
                    """,
                    motion_ids,
                ).fetchall()
            ]
            if orphan_motions:
                o_ph = ",".join("?" * len(orphan_motions))
                conn.execute(f"DELETE FROM motion WHERE id IN ({o_ph})", orphan_motions)
                print(
                    f"  ✓ Motions huérfanas eliminadas ({len(orphan_motions)} de {len(motion_ids)})"
                )
            else:
                print(
                    f"  ⓘ Motions compartidas — no eliminadas ({len(motion_ids)} referenciadas por otros VEs)"
                )

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purga datos corruptos de LXV Diputados (vote_events, votes, counts, motions)"
    )
    parser.add_argument("--force", action="store_true", help="Saltar confirmación interactiva")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se eliminaría")
    args = parser.parse_args()

    # --- Verificar BD ---
    if not DB_PATH.exists():
        print(f"ERROR: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    # --- Identificar vote_events de LXV Diputados ---
    ve_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM vote_event WHERE legislatura = 'LXV' AND organization_id = 'O08'"
        ).fetchall()
    ]

    if not ve_ids:
        print("No hay datos de LXV Diputados para purgar. Saliendo.")
        conn.close()
        return

    # --- Contar registros afectados ---
    info = get_counts(conn, ve_ids)
    print("=" * 50)
    print("DATOS LXV DIPUTADOS A PURGAR:")
    print(f"  Vote events : {info['vote_events']:,}")
    print(f"  Votes       : {info['votes']:,}")
    print(f"  Counts      : {info['counts']:,}")
    print(f"  Motions     : {info['motions']:,}")
    print("=" * 50)

    # --- Dry-run ---
    if args.dry_run:
        print("\n[DRY RUN] No se eliminaron registros.")
        conn.close()
        return

    # --- Confirmación ---
    if not args.force:
        try:
            resp = input("\n¿Proceder con la purga? (s/N): ")
        except EOFError:
            resp = "n"
        if resp.strip().lower() != "s":
            print("Cancelado.")
            conn.close()
            return

    # --- Backup ---
    backup_path = DB_PATH.parent / (DB_PATH.name + ".bak.pre-lxv-purge")
    shutil.copy2(str(DB_PATH), str(backup_path))
    print(f"\nBackup creado: {backup_path}")

    # --- Ejecutar purga ---
    print("\nEliminando registros...")
    purge(conn, ve_ids, info["motion_ids"])
    print("\n✓ Purga completada.")

    # --- Verificar integridad referencial ---
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        print(f"\n⚠ {len(violations)} violaciones de FK detectadas:")
        for v in violations[:10]:
            print(f"  tabla={v[0]}, rowid={v[1]}, parent={v[2]}, fkid={v[3]}")
    else:
        print("✓ Integridad referencial OK (foreign_key_check limpio).")

    # --- Verificar conteos post-purga ---
    remaining = conn.execute(
        "SELECT COUNT(*) FROM vote_event WHERE legislatura = 'LXV' AND organization_id = 'O08'"
    ).fetchone()[0]
    print(f"\nVEs LXV Diputados restantes: {remaining}")

    conn.close()


if __name__ == "__main__":
    main()
