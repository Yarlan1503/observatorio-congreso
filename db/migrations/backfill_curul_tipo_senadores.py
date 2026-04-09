#!/usr/bin/env python3
"""
Backfill de curul_tipo para senadores en la tabla person.

Los senadores tienen tipos de curul que no siempre están poblados.
Este script analiza los labels de membership para inferir el tipo:
  - "Lista Nacional" → plurinominal
  - "por [Estado]" → mayoria_relativa
  - "Suplente" → suplente
  - Labels genéricos ("Senador, PARTIDO") → no asignar

El campo curul_tipo es una propiedad de la PERSONA, no del membership.
Si algún membership de la persona tiene info de tipo, se usa esa.
Solo actualiza personas con curul_tipo IS NULL (idempotente).

Uso:
    python -m db.migrations.backfill_curul_tipo_senadores
"""

import re
import sqlite3
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO / "db" / "congreso.db"


def infer_curul_tipo(labels: list[str]) -> str | None:
    """Infers curul_tipo from a list of membership labels.

    Prioridad:
      1. Si ALGÚN label contiene "Lista Nacional" → plurinominal
      2. Si ALGÚN label contiene "por [Estado]" pero NO "Lista Nacional" → mayoria_relativa
      3. Si ALGÚN label contiene "Suplente" → suplente
      4. Todos los labels son genéricos → None (no asignar)
    """
    has_lista_nacional = False
    has_por_estado = False
    has_suplente = False

    for label in labels:
        if not label:
            continue
        lower = label.lower()

        # Detectar "Lista Nacional" (varias codificaciones posibles)
        if "lista nacional" in lower:
            has_lista_nacional = True
            continue  # No puede ser "por Estado" si ya es Lista Nacional

        # Detectar "por [Estado]" — ej: "por Aguascalientes", "por Yucatán"
        # También maneja encoding roto: "por YucatÃ¡n", "por Estado de MÃ©xico"
        if re.search(r"por\s+[A-ZÁÉÍÓÚÑa-záéíóúñÃ]", label) and "lista nacional" not in lower:
            has_por_estado = True

        # Detectar "Suplente"
        if "suplente" in lower:
            has_suplente = True

    if has_lista_nacional:
        return "plurinominal"
    if has_por_estado:
        return "mayoria_relativa"
    if has_suplente:
        return "suplente"
    return None


def main():
    print("Backfill curul_tipo para Senadores — Observatorio del Congreso")
    print(f"BD: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"ERROR: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA foreign_keys = ON")

    # ── Estado inicial ──────────────────────────────────────────────────────
    print("\n--- Estado Inicial ---")
    total_senadores = db.execute(
        "SELECT COUNT(DISTINCT p.id) FROM person p "
        "JOIN membership m ON m.person_id = p.id "
        "WHERE m.rol = 'senador'"
    ).fetchone()[0]
    print(f"  Total senadores (personas): {total_senadores}")

    for val in ("mayoria_relativa", "plurinominal", "suplente", None):
        label = val if val else "(NULL)"
        cnt = db.execute(
            "SELECT COUNT(DISTINCT p.id) FROM person p "
            "JOIN membership m ON m.person_id = p.id "
            "WHERE m.rol = 'senador' AND p.curul_tipo IS ?",
            (val,),
        ).fetchone()[0]
        print(f"  {label:25s} {cnt}")

    # ── Obtener senadores con curul_tipo NULL ───────────────────────────────
    rows = db.execute(
        "SELECT DISTINCT p.id, p.nombre "
        "FROM person p "
        "JOIN membership m ON m.person_id = p.id "
        "WHERE p.curul_tipo IS NULL AND m.rol = 'senador'"
    ).fetchall()

    print(f"\nSenadores con curul_tipo NULL: {len(rows)}")

    if not rows:
        print("No hay senadores sin curul_tipo. Nada que hacer.")
        db.close()
        return

    # ── Procesar cada persona ───────────────────────────────────────────────
    stats = {
        "mayoria_relativa": 0,
        "plurinominal": 0,
        "suplente": 0,
        "no_determinado": 0,
    }
    no_determinados: list[tuple[str, str, list[str]]] = []  # (id, nombre, labels)
    updates: list[tuple[str, str]] = []  # (curul_tipo, person_id)

    for person_id, nombre in rows:
        # Obtener todos los memberships de senador de esta persona
        membership_rows = db.execute(
            "SELECT label FROM membership WHERE person_id = ? AND rol = 'senador'",
            (person_id,),
        ).fetchall()

        labels = [row[0] for row in membership_rows if row[0]]

        curul_tipo = infer_curul_tipo(labels)

        if curul_tipo:
            updates.append((curul_tipo, person_id))
            stats[curul_tipo] += 1
        else:
            stats["no_determinado"] += 1
            no_determinados.append((person_id, nombre, labels))

    # ── Aplicar updates ─────────────────────────────────────────────────────
    if updates:
        for curul_tipo, person_id in updates:
            db.execute(
                "UPDATE person SET curul_tipo = ? WHERE id = ? AND curul_tipo IS NULL",
                (curul_tipo, person_id),
            )
        db.commit()
        print(f"\n  ✓ {len(updates)} registros actualizados en BD")

    # ── Reporte ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("REPORTE")
    print("=" * 60)
    print(f"  Total procesados:          {len(rows)}")
    print(f"  → mayoria_relativa:        {stats['mayoria_relativa']}")
    print(f"  → plurinominal:            {stats['plurinominal']}")
    print(f"  → suplente:                {stats['suplente']}")
    print(f"  → no determinado:          {stats['no_determinado']}")

    # ── Estado final ────────────────────────────────────────────────────────
    print("\n--- Estado Final ---")
    for val in ("mayoria_relativa", "plurinominal", "suplente", None):
        label = val if val else "(NULL)"
        cnt = db.execute(
            "SELECT COUNT(DISTINCT p.id) FROM person p "
            "JOIN membership m ON m.person_id = p.id "
            "WHERE m.rol = 'senador' AND p.curul_tipo IS ?",
            (val,),
        ).fetchone()[0]
        print(f"  {label:25s} {cnt}")

    # ── Mostrar no determinados ─────────────────────────────────────────────
    if no_determinados:
        print(f"\n--- No determinados ({len(no_determinados)}) — muestra de labels ---")
        for person_id, nombre, labels in no_determinados[:40]:
            labels_str = " | ".join(labels[:3])
            print(f"  [{person_id}] {nombre}")
            print(f"       labels: {labels_str}")

    db.close()
    print("\n✓ Listo.")


if __name__ == "__main__":
    main()
