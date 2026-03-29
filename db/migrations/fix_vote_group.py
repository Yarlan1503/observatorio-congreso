#!/usr/bin/env python3
"""
fix_vote_group.py — Estandariza el campo `group` en la tabla vote.

Convierte nombres de texto ("Morena", "PT", "PVEM") a IDs de organización
("O01", "O02", "O03") para que el campo sea consistente con el resto de la BD.

DEPENDENCIA: Este script DEBE ejecutarse después de fix_duplicados.py.
Verifica la ausencia de duplicados antes de proceder.

Uso:
    python db/fix_vote_group.py            # ejecuta corrección
    python db/fix_vote_group.py --dry-run  # solo muestra cambios
    python db/fix_vote_group.py --stats    # muestra estado actual
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "congreso.db"

# --- Mapeo texto → ID org ---
GROUP_MAP = {
    "Morena": "O01",
    "PT": "O02",
    "PVEM": "O03",
}


def check_no_duplicates(conn: sqlite3.Connection) -> bool:
    """Verifica que no hay votos duplicados en la BD.

    Un voto duplicado = misma combinación (vote_event_id, voter_id, group, option)
    con >1 fila. Esto permite que un legislador aparezca en la misma votación con
    grupos distintos (ej. cambio de partido) — caso legítimo.

    Returns:
        True si NO hay duplicados (seguro proceder).
        False si HAY duplicados (abortar).
    """
    dup_count = conn.execute(
        "SELECT COUNT(*) FROM ("
        '  SELECT vote_event_id, voter_id, "group", option, COUNT(*) AS c'
        "  FROM vote"
        '  GROUP BY vote_event_id, voter_id, "group", option'
        "  HAVING c > 1"
        ")"
    ).fetchone()[0]
    return dup_count == 0


def count_non_org_groups(conn: sqlite3.Connection) -> int:
    """Cuenta registros con group no-Org (no empieza con 'O' y no es NULL)."""
    return conn.execute(
        "SELECT COUNT(*) FROM vote "
        'WHERE "group" IS NOT NULL AND "group" NOT LIKE \'O%\''
    ).fetchone()[0]


def show_stats(conn: sqlite3.Connection) -> None:
    """Muestra estado actual del campo group en la tabla vote."""
    print("=== Estado del campo `group` en vote ===")
    print()

    # Total y desglose
    total = conn.execute("SELECT COUNT(*) FROM vote").fetchone()[0]
    with_group = conn.execute(
        'SELECT COUNT(*) FROM vote WHERE "group" IS NOT NULL'
    ).fetchone()[0]
    null_group = total - with_group
    non_org = count_non_org_groups(conn)

    print(f"Total votos:              {total}")
    print(f"Con group:                {with_group}")
    print(f"Group NULL:               {null_group}")
    print(f"Group no-Org (a corregir): {non_org}")
    print()

    # Desglose por valor de group
    print("Desglose por valor de group:")
    for val, cnt in conn.execute(
        'SELECT "group", COUNT(*) FROM vote GROUP BY "group" ORDER BY COUNT(*) DESC'
    ):
        display = val if val else "(NULL)"
        print(f"  {display:25s} {cnt:>6d}")
    print()

    # Verificar duplicados
    if check_no_duplicates(conn):
        print("Duplicados (vote_event_id, voter_id): NO")
    else:
        print(
            "Duplicados (vote_event_id, voter_id): SI — ejecutar fix_duplicados.py primero"
        )


def run_fix(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Ejecuta la corrección de group en la tabla vote.

    Args:
        conn: Conexión activa a SQLite.
        dry_run: Si True, solo muestra cambios sin ejecutar UPDATEs.
    """
    # --- Pre-verificación 1: duplicados ---
    print("[Pre-check] Verificando duplicados...")
    if not check_no_duplicates(conn):
        print("\n[ABORT] Se detectaron votos duplicados (vote_event_id, voter_id).")
        print("        Ejecuta fix_duplicados.py PRIMERO antes de este script.")
        print("        Este script requiere que no existan duplicados.")
        sys.exit(1)
    print("[Pre-check] Sin duplicados. OK")

    # --- Pre-verificación 2: registros a corregir ---
    non_org = count_non_org_groups(conn)
    print(f"[Pre-check] Registros con group no-Org: {non_org}")

    if non_org == 0:
        print("\nNo hay registros para corregir. El campo group ya está estandarizado.")
        return

    # Mostrar detalle de qué se va a corregir
    print("\nRegistros a corregir (antes):")
    for val, cnt in conn.execute(
        'SELECT "group", COUNT(*) FROM vote '
        'WHERE "group" IS NOT NULL AND "group" NOT LIKE \'O%\' '
        'GROUP BY "group" ORDER BY COUNT(*) DESC'
    ):
        target = GROUP_MAP.get(val, "???")
        print(f"  '{val}' → '{target}' ({cnt} registros)")

    # --- Dry-run: solo reportar ---
    if dry_run:
        print(
            f"\n[DRY-RUN] Se actualizarían {non_org} registros. Sin cambios aplicados."
        )
        return

    # --- UPDATE con transacción ---
    print("\nActualizando...")
    total_updated = 0

    try:
        for text_name, org_id in GROUP_MAP.items():
            cnt = conn.execute(
                'UPDATE vote SET "group" = ? WHERE "group" = ?',
                (org_id, text_name),
            ).rowcount
            if cnt > 0:
                print(f"  '{text_name}' → '{org_id}': {cnt} registros actualizados")
            total_updated += cnt

        conn.commit()
        print(f"\nCommit exitoso. Total actualizados: {total_updated}")
    except Exception as exc:
        conn.rollback()
        print(f"\n[ERROR] Fallo durante UPDATE. Rollback ejecutado. Error: {exc}")
        raise

    # --- Verificación post-fix ---
    remaining = count_non_org_groups(conn)
    print(f"\n[Post-check] Registros con group no-Org: {remaining}")

    if remaining > 0:
        print("[AVISO] Aún quedan registros con group no-Org:")
        for val, cnt in conn.execute(
            'SELECT "group", COUNT(*) FROM vote '
            'WHERE "group" IS NOT NULL AND "group" NOT LIKE \'O%\' '
            'GROUP BY "group" ORDER BY COUNT(*) DESC'
        ):
            print(f"  '{val}': {cnt} registros")
        print("Estos valores no están en GROUP_MAP. Revisar manualmente.")
    else:
        print("[Post-check] Todos los registros con group usan IDs de organización. OK")


def main():
    parser = argparse.ArgumentParser(
        description="Estandariza el campo `group` en tabla vote (texto → ID org)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra cambios sin ejecutar UPDATEs",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Muestra estado actual del campo group",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[ERROR] Base de datos no encontrada: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        if args.stats:
            show_stats(conn)
        else:
            run_fix(conn, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
