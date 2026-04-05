"""db/helpers.py — Shared helpers for database operations.

Contains reusable functions for creating and looking up organizations,
shared between Senado and Diputados loaders/transformers.
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def get_or_create_organization(org_ref: str, conn: sqlite3.Connection) -> Optional[str]:
    """Get or create an organization by abbr, name, or ID.

    Resolution order:
    1. Direct ID lookup (O01, O09, etc.)
    2. Exact abbr lookup
    3. Exact nombre lookup
    4. Case-insensitive abbr lookup
    5. Create new organization with sequential O## ID (last resort)

    When creating a new organization, sets clasificacion='partido'.
    Callers must commit the connection for the INSERT to persist.

    Args:
        org_ref: Abbreviation (MORENA, PAN) or ID (O09).
        conn: Active SQLite connection.

    Returns:
        Organization ID (existing or new), or None if org_ref is empty.
    """
    if not org_ref or not org_ref.strip():
        return None

    org_ref = org_ref.strip()

    # 1. Direct ID
    row = conn.execute(
        "SELECT id FROM organization WHERE id = ?", (org_ref,)
    ).fetchone()
    if row:
        return row[0]

    # 2. Exact abbr
    row = conn.execute(
        "SELECT id FROM organization WHERE abbr = ?", (org_ref,)
    ).fetchone()
    if row:
        return row[0]

    # 3. Exact nombre
    row = conn.execute(
        "SELECT id FROM organization WHERE nombre = ?", (org_ref,)
    ).fetchone()
    if row:
        return row[0]

    # 4. Case-insensitive abbr
    row = conn.execute(
        "SELECT id FROM organization WHERE UPPER(abbr) = UPPER(?)", (org_ref,)
    ).fetchone()
    if row:
        return row[0]

    # 5. Create new organization
    if org_ref.startswith("O") and len(org_ref) > 1 and org_ref[1:].isdigit():
        org_id = org_ref
        nombre = org_ref
        abbr = None
    else:
        # Generate sequential O## ID
        max_row = conn.execute(
            "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) "
            "FROM organization WHERE id LIKE 'O%'"
        ).fetchone()
        next_num = (max_row[0] if max_row[0] is not None else 0) + 1
        org_id = f"O{next_num:02d}"
        nombre = org_ref
        abbr = org_ref

    clasificacion = "partido"

    conn.execute(
        """INSERT OR IGNORE INTO organization
           (id, nombre, abbr, clasificacion)
           VALUES (?, ?, ?, ?)""",
        (org_id, nombre, abbr, clasificacion),
    )
    logger.info(f"Organización creada: {org_id} ({nombre}, abbr={abbr})")
    return org_id
