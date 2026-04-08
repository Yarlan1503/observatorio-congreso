#!/usr/bin/env python3
"""
Migración: Fix FK violations post-scraping Diputados

Problema: El scraper dejó memberships con org_ids legacy (O01-O07)
que no existen en la tabla organization, tanto en org_id como en
on_behalf_of. También dejó counts con group_ids legacy.

Solución:
1. UPDATE memberships: org_id y on_behalf_of legacy → org_id real
2. UPDATE counts: group_id legacy → org_id real (VE01 sí existe)
3. DELETE cualquier registro que quede huérfano tras el mapeo

Idempotente: se puede ejecutar múltiples veces sin efectos secundarios.

Ejecutar: .venv/bin/python3 db/migrations/fix_fk_violations.py
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "congreso.db"

# Mapeo verificado contra la BD: org_ids legacy del scraper Diputados → IDs reales
LEGACY_ORG_MAP = {
    "O01": "O11",  # MORENA
    "O02": "O14",  # PT
    "O03": "O13",  # PVEM
    "O04": "O12",  # PAN
    "O05": "O15",  # PRI
    "O06": "O16",  # MC
    "O07": "O18",  # PRD
}


def verify_mapping(cur) -> dict[str, str]:
    """Verifica que todos los org_ids destino existen en la BD."""
    valid = {}
    for legacy_id, real_id in LEGACY_ORG_MAP.items():
        cur.execute("SELECT id, abbr FROM organization WHERE id = ?", (real_id,))
        row = cur.fetchone()
        if row:
            valid[legacy_id] = real_id
            print(f"  OK {legacy_id} -> {real_id} ({row[1]})")
        else:
            print(f"  SKIP {legacy_id} -> {real_id} NO EXISTE en organization")
    return valid


def fix_membership_org_id(cur, valid_map: dict[str, str]) -> tuple[int, int]:
    """Fix membership.org_id FK violations: UPDATE con mapeo válido."""
    updates = 0
    deletes = 0

    for legacy_id, real_id in valid_map.items():
        cur.execute(
            "SELECT rowid, person_id, label FROM membership WHERE org_id = ?",
            (legacy_id,),
        )
        rows = cur.fetchall()
        for rowid, person_id, label in rows:
            cur.execute(
                "UPDATE membership SET org_id = ? WHERE rowid = ?",
                (real_id, rowid),
            )
            updates += 1
            print(f"  UPDATE org_id rowid={rowid}: {legacy_id}->{real_id} | {person_id} | {label}")

    # Eliminar org_ids huérfanos sin mapeo
    cur.execute(
        """
        SELECT m.rowid, m.org_id, m.person_id, m.label
        FROM membership m
        LEFT JOIN organization o ON m.org_id = o.id
        WHERE o.id IS NULL AND m.org_id IS NOT NULL
        """,
    )
    for rowid, org_id, person_id, label in cur.fetchall():
        cur.execute("DELETE FROM membership WHERE rowid = ?", (rowid,))
        deletes += 1
        print(f"  DELETE org_id rowid={rowid}: org_id={org_id} huérfano | {person_id} | {label}")

    return updates, deletes


def fix_membership_on_behalf_of(cur, valid_map: dict[str, str]) -> tuple[int, int]:
    """Fix membership.on_behalf_of FK violations: UPDATE con mapeo válido."""
    updates = 0
    deletes = 0

    for legacy_id, real_id in valid_map.items():
        cur.execute(
            "SELECT rowid, person_id, label, on_behalf_of FROM membership WHERE on_behalf_of = ?",
            (legacy_id,),
        )
        rows = cur.fetchall()
        for rowid, person_id, label, _obo in rows:
            cur.execute(
                "UPDATE membership SET on_behalf_of = ? WHERE rowid = ?",
                (real_id, rowid),
            )
            updates += 1
            print(
                f"  UPDATE on_behalf_of rowid={rowid}: {legacy_id}->{real_id} | {person_id} | {label}"
            )

    # NULLificar on_behalf_of que sigan huérfanos
    cur.execute(
        """
        SELECT m.rowid, m.on_behalf_of, m.person_id, m.label
        FROM membership m
        LEFT JOIN organization o ON m.on_behalf_of = o.id
        WHERE o.id IS NULL AND m.on_behalf_of IS NOT NULL
        """,
    )
    for rowid, obo, person_id, label in cur.fetchall():
        cur.execute("UPDATE membership SET on_behalf_of = NULL WHERE rowid = ?", (rowid,))
        deletes += 1  # Contamos como "limpieza" aunque sea SET NULL
        print(f"  SET NULL on_behalf_of rowid={rowid}: {obo} huérfano | {person_id} | {label}")

    return updates, deletes


def fix_counts(cur, valid_map: dict[str, str]) -> tuple[int, int]:
    """Fix count.group_id FK violations: UPDATE con mapeo válido, DELETE sin mapeo."""
    updates = 0
    deletes = 0

    for legacy_id, real_id in valid_map.items():
        cur.execute(
            'SELECT rowid, vote_event_id, option, value FROM "count" WHERE group_id = ?',
            (legacy_id,),
        )
        rows = cur.fetchall()
        for rowid, ve_id, option, value in rows:
            cur.execute(
                'UPDATE "count" SET group_id = ? WHERE rowid = ?',
                (real_id, rowid),
            )
            updates += 1
            print(
                f"  UPDATE count rowid={rowid}: {legacy_id}->{real_id} | ve={ve_id} | {option}={value}"
            )

    # Eliminar counts con group_id huérfano sin mapeo
    cur.execute(
        """
        SELECT c.rowid, c.group_id, c.vote_event_id, c.option, c.value
        FROM "count" c
        LEFT JOIN organization o ON c.group_id = o.id
        WHERE o.id IS NULL AND c.group_id IS NOT NULL
        """,
    )
    for rowid, group_id, ve_id, _option, _value in cur.fetchall():
        cur.execute('DELETE FROM "count" WHERE rowid = ?', (rowid,))
        deletes += 1
        print(f"  DELETE count rowid={rowid}: group_id={group_id} huérfano | ve={ve_id}")

    return updates, deletes


def main():
    if not DB_PATH.exists():
        print(f"BD no encontrada: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    print("=== Fix FK Violations Post-Scraping Diputados ===\n")

    # FK check antes
    cur.execute("PRAGMA foreign_key_check")
    violations_before = cur.fetchall()
    print(f"FK violations ANTES: {len(violations_before)}\n")

    # Paso 0: Verificar mapeo
    print("--- Verificando mapeo org_id legacy -> real ---")
    valid_map = verify_mapping(cur)
    print()

    # Paso 1: Fix membership.org_id
    print("--- Paso 1: Fix membership.org_id ---")
    org_updates, org_deletes = fix_membership_org_id(cur, valid_map)
    print(f"  org_id: {org_updates} UPDATEs, {org_deletes} DELETEs\n")

    # Paso 2: Fix membership.on_behalf_of
    print("--- Paso 2: Fix membership.on_behalf_of ---")
    obo_updates, obo_deletes = fix_membership_on_behalf_of(cur, valid_map)
    print(f"  on_behalf_of: {obo_updates} UPDATEs, {obo_deletes} SET NULLs\n")

    # Paso 3: Fix count.group_id
    print("--- Paso 3: Fix count.group_id ---")
    cnt_updates, cnt_deletes = fix_counts(cur, valid_map)
    print(f"  count: {cnt_updates} UPDATEs, {cnt_deletes} DELETEs\n")

    # Commit
    conn.commit()

    # FK check después
    cur.execute("PRAGMA foreign_key_check")
    violations_after = cur.fetchall()
    print(f"FK violations DESPUES: {len(violations_after)}")

    if violations_after:
        print("Violaciones restantes:")
        for v in violations_after:
            print(f"  {v}")
    else:
        print("0 FK violations - BD limpia")

    conn.close()

    # Resumen
    total_updates = org_updates + obo_updates + cnt_updates
    total_deletes = org_deletes + obo_deletes + cnt_deletes
    print("\n=== Resumen ===")
    print(f"  membership.org_id:       {org_updates} UPDATEs, {org_deletes} DELETEs")
    print(f"  membership.on_behalf_of: {obo_updates} UPDATEs, {obo_deletes} SET NULLs")
    print(f"  count.group_id:          {cnt_updates} UPDATEs, {cnt_deletes} DELETEs")
    print(f"  TOTAL: {total_updates} UPDATEs, {total_deletes} DELETEs/LIMPIAS")
    print(f"  FK violations: {len(violations_before)} -> {len(violations_after)}")

    if violations_after:
        sys.exit(1)


if __name__ == "__main__":
    main()
