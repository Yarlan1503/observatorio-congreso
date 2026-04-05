#!/usr/bin/env python3
"""
add_source_id.py — Migración: agregar columna source_id a vote_event.

La columna source_id (TEXT, nullable) almacena el ID original del portal
de origen (senado.gob.mx o SITL) para deduplicación confiable.

Idempotente: safe to run multiple times.
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")


def migrate(conn: sqlite3.Connection):
    """Agrega source_id y su índice a vote_event."""
    cur = conn.cursor()

    # Check if column already exists
    cur.execute("PRAGMA table_info(vote_event)")
    columns = [row[1] for row in cur.fetchall()]

    if "source_id" in columns:
        print("[migrate] source_id already exists in vote_event, skipping.")
        return

    print("[migrate] Adding source_id TEXT to vote_event...")
    cur.execute("ALTER TABLE vote_event ADD COLUMN source_id TEXT")

    print("[migrate] Creating index idx_vote_event_source...")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_vote_event_source ON vote_event(source_id)"
    )

    conn.commit()
    print("[migrate] Done.")


def main():
    if not os.path.exists(DB_PATH):
        print(f"[migrate] Database not found at {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        migrate(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
