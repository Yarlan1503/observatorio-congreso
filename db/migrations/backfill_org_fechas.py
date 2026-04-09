#!/usr/bin/env python3
"""
Backfill de fundacion/disolucion para la tabla organization del Observatorio del Congreso.

Fuentes:
  - Fechas de registro IFE/INE (oficiales).
  - Fechas de pérdida de registro (INE / resoluciones).

Regla: NO se inventan fechas. Solo se usan fechas confirmadas. Si la fecha no
es confiable al día exacto, se redondea al primer día del mes.

Uso:
    python db/migrations/backfill_org_fechas.py
    .venv/bin/python3 -m db.migrations.backfill_org_fechas
"""

import sqlite3
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO / "db" / "congreso.db"

# ── Datos verificados ──────────────────────────────────────────────────────
# org_id: (fundacion, disolucion)
# NULL = no tocar o no aplica.
# Las fechas de disolución son aproximadas (fin de agosto del año que pierden registro).
# Las fechas de fundación provienen de registros públicos del IFE/INE.

ORG_FECHAS: dict[str, tuple[str | None, str | None]] = {
    # Partidos actuales con registro vigente
    "O11": ("2014-07-29", None),  # MORENA — registro INE 29 jul 2014
    "O12": ("1939-09-17", None),  # PAN — fundado 17 sep 1939
    "O13": ("1991-01-29", None),  # PVEM — registro como Partido Verde Mexicano 29 ene 1991
    "O14": ("1990-12-16", None),  # PT — registro IFE 16 dic 1990
    "O15": ("1929-03-04", None),  # PRI — fundado como PNR 4 mar 1929
    "O16": ("2014-08-12", None),  # MC — registro como Movimiento Ciudadano ago 2014
    # Partidos que perdieron registro
    "O18": ("1989-05-05", "2024-08-29"),  # PRD — fundado 5 may 1989, perdió registro jun 2024
    "O20": ("1999-08-17", "2014-07-22"),  # Convergencia — fundada 17 ago 1999, fusionó en MC 2014
    "O21": (
        "2005-01-30",
        "2018-08-29",
    ),  # Nueva Alianza (NA) — registro 30 ene 2005, perdió registro 2018
    "O22": (
        "2005-01-14",
        "2009-08-29",
    ),  # Alternativa Socialdemócrata — registro ene 2005, perdió registro 2009
    "O25": ("2014-07-09", "2018-08-29"),  # PES — registro jul 2014, perdió registro 2018
    # NO tocar:
    # O08: Cámara de Diputados — institución
    # O09: Senado — institución
    # O10: Coalición — ya tiene fundacion=2024-01-01
    # O17: IND — no es partido formal
    # O19: SG — coalición
    # O26: NUEVA ALIANZA — duplicado de O21
    # O28: SP — no es partido formal
}


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    print("Backfill de Fechas de Organización — Observatorio del Congreso")
    print(f"BD: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"ERROR: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA foreign_keys=ON")

    # ── Estado inicial ──────────────────────────────────────────────────
    print("\n--- Estado Inicial ---")
    cur = db.cursor()
    cur.execute(
        "SELECT id, nombre, abbr, clasificacion, fundacion, disolucion "
        "FROM organization ORDER BY id"
    )
    orgs_before = cur.fetchall()
    for oid, nombre, _abbr, clasif, fund, disol in orgs_before:
        fund_str = fund or "NULL"
        disol_str = disol or "NULL"
        print(f"  {oid}: {nombre} [{clasif}] fund={fund_str} disol={disol_str}")

    # ── Aplicar updates ─────────────────────────────────────────────────
    print(f"\n--- Aplicando {len(ORG_FECHAS)} actualizaciones ---")
    actualizados = 0
    sin_cambio = 0
    errores = []

    for org_id, (fundacion, disolucion) in ORG_FECHAS.items():
        # Verificar que la org existe
        cur.execute(
            "SELECT nombre, fundacion, disolucion FROM organization WHERE id = ?", (org_id,)
        )
        row = cur.fetchone()
        if row is None:
            errores.append(f"{org_id}: NO encontrada en BD")
            continue

        nombre, cur_fund, cur_disol = row

        # Idempotente: solo actualizar si hay diferencia
        if cur_fund == fundacion and cur_disol == disolucion:
            sin_cambio += 1
            print(f"  {org_id} ({nombre}): sin cambios")
            continue

        # Verificar que no sobreescribimos fechas ya existentes con valores NULL
        if cur_fund is not None and fundacion is None:
            errores.append(
                f"{org_id} ({nombre}): fundacion existente '{cur_fund}' no se sobreescribe con NULL"
            )
            continue
        if cur_disol is not None and disolucion is None:
            errores.append(
                f"{org_id} ({nombre}): disolucion existente '{cur_disol}' no se sobreescribe con NULL"
            )
            continue

        # Verificar que no sobreescribimos fechas ya existentes con valores diferentes
        if cur_fund is not None and fundacion is not None and cur_fund != fundacion:
            errores.append(
                f"{org_id} ({nombre}): fundacion conflictiva BD='{cur_fund}' vs nueva='{fundacion}'"
            )
            continue
        if cur_disol is not None and disolucion is not None and cur_disol != disolucion:
            errores.append(
                f"{org_id} ({nombre}): disolucion conflictiva BD='{cur_disol}' vs nueva='{disolucion}'"
            )
            continue

        cur.execute(
            "UPDATE organization SET fundacion = ?, disolucion = ? WHERE id = ?",
            (fundacion, disolucion, org_id),
        )
        actualizados += 1
        cambios = []
        if cur_fund != fundacion:
            cambios.append(f"fundacion: {cur_fund or 'NULL'} → {fundacion}")
        if cur_disol != disolucion:
            cambios.append(f"disolucion: {cur_disol or 'NULL'} → {disolucion}")
        print(f"  {org_id} ({nombre}): actualizado — {', '.join(cambios)}")

    db.commit()

    # ── Reporte ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("REPORTE FINAL")
    print("=" * 60)
    print(f"  Organizaciones procesadas: {len(ORG_FECHAS)}")
    print(f"  Actualizados:              {actualizados}")
    print(f"  Sin cambio:                {sin_cambio}")
    print(f"  Errores/advertencias:      {len(errores)}")

    if errores:
        print("\n  Errores:")
        for e in errores:
            print(f"    ⚠ {e}")

    # ── Orgs sin fecha ──────────────────────────────────────────────────
    cur.execute(
        "SELECT id, nombre, clasificacion FROM organization "
        "WHERE fundacion IS NULL AND clasificacion = 'partido' ORDER BY id"
    )
    sin_fecha = cur.fetchall()
    if sin_fecha:
        print(f"\n  Partidos sin fecha de fundación ({len(sin_fecha)}):")
        for oid, nombre, _ in sin_fecha:
            print(f"    {oid}: {nombre}")

    # ── Estado final ────────────────────────────────────────────────────
    print("\n--- Estado Final ---")
    cur.execute(
        "SELECT id, nombre, abbr, clasificacion, fundacion, disolucion "
        "FROM organization ORDER BY id"
    )
    for oid, nombre, _abbr, clasif, fund, disol in cur.fetchall():
        fund_str = fund or "NULL"
        disol_str = disol or "NULL"
        print(f"  {oid}: {nombre} [{clasif}] fund={fund_str} disol={disol_str}")

    db.close()
    print("\n✓ Listo.")


if __name__ == "__main__":
    main()
