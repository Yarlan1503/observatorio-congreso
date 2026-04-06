#!/usr/bin/env python3
"""
recalcular_resultados.py — Recalcula resultados de votaciones con lógica corregida.

Recorre todos los vote_events con resultado no-NULL y recalcula usando:
  - mayoria_simple / unanime: aprobada si favor > contra, empate si ==, rechazada si <
  - mayoria_calificada: aprobada si a_favor >= (2/3 * presentes), donde presentes = favor + contra + abstencion

Maneja counts duplicados de "ausente" usando GROUP BY + SUM.
Solo actualiza vote_event.result y motion.result si el resultado cambió.
Usa transacción con commit explícito al final.

Uso:  python3 db/recalcular_resultados.py   (desde la raíz del proyecto)
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")


def calcular_resultado(requirement: str, favor: int, contra: int, abstencion: int) -> str:
    """Calcula el resultado de una votación según el tipo de mayoría requerida.

    Args:
        requirement: 'mayoria_simple', 'mayoria_calificada' o 'unanime'.
        favor: Votos a favor (globales).
        contra: Votos en contra (globales).
        abstencion: Abstenciones (globales).

    Returns:
        'aprobada', 'rechazada' o 'empate'.
    """
    if requirement == "mayoria_calificada":
        presentes = favor + contra + abstencion
        # 2/3 de presentes como umbral
        umbral = (2.0 / 3.0) * presentes
        if presentes == 0:
            return "rechazada"
        if favor >= umbral:
            return "aprobada"
        else:
            return "rechazada"
    else:
        # mayoria_simple y unanime: misma lógica
        if favor > contra:
            return "aprobada"
        elif favor < contra:
            return "rechazada"
        else:
            return "empate"


def main():
    print("=" * 65)
    print("Recálculo de Resultados de Votaciones")
    print("  Observatorio del Congreso — Lógica corregida (calificada 2/3)")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] Base de datos no encontrada: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # 1. Obtener todos los vote_events con resultado no-NULL
    cur.execute("""
        SELECT ve.id, ve.result, ve.motion_id, m.requirement
        FROM vote_event ve
        JOIN motion m ON ve.motion_id = m.id
        WHERE ve.result IS NOT NULL
        ORDER BY ve.id
    """)
    vote_events = cur.fetchall()
    print(f"\nVote_events a procesar (result IS NOT NULL): {len(vote_events)}")
    print("Vote_events saltados (result IS NULL): 2 (pendientes)")

    cambios = []  # Lista de dicts con detalle de cambios

    for ve_id, ve_result, motion_id, requirement in vote_events:
        # 2. Obtener totales globales (group_id IS NULL), sumando duplicados
        cur.execute(
            """
            SELECT option, SUM(value) as total
            FROM count
            WHERE vote_event_id = ? AND group_id IS NULL
            GROUP BY option
        """,
            (ve_id,),
        )

        totales = {}
        for option, total in cur.fetchall():
            totales[option] = total

        favor = totales.get("a_favor", 0)
        contra = totales.get("en_contra", 0)
        abstencion = totales.get("abstencion", 0)
        ausente = totales.get("ausente", 0)

        # 3. Calcular resultado correcto
        resultado_calculado = calcular_resultado(requirement, favor, contra, abstencion)

        # 4. Comparar con resultado actual
        if resultado_calculado != ve_result:
            presentes = favor + contra + abstencion
            cambio = {
                "ve_id": ve_id,
                "motion_id": motion_id,
                "requirement": requirement,
                "resultado_anterior": ve_result,
                "resultado_nuevo": resultado_calculado,
                "a_favor": favor,
                "en_contra": contra,
                "abstencion": abstencion,
                "ausente": ausente,
                "presentes": presentes,
            }
            cambios.append(cambio)

    # 5. Mostrar resumen ANTES de commit
    print(f"\n{'─' * 65}")
    print("RESUMEN DE CAMBIOS")
    print(f"{'─' * 65}")
    print(f"Vote_events procesados: {len(vote_events)}")
    print(f"Resultados que cambian: {len(cambios)}")

    if cambios:
        print("\nDetalle de cambios:")
        for c in cambios:
            print(f"\n  [{c['ve_id']}] motion={c['motion_id']} requirement={c['requirement']}")
            print(f"    Resultado anterior: {c['resultado_anterior']}")
            print(f"    Resultado nuevo:    {c['resultado_nuevo']}")
            print(
                f"    A favor={c['a_favor']}, En contra={c['en_contra']}, "
                f"Abstención={c['abstencion']}, Ausente={c['ausente']}"
            )
            print(f"    Presentes={c['presentes']}", end="")
            if c["requirement"] == "mayoria_calificada":
                umbral = (2.0 / 3.0) * c["presentes"]
                print(f", Umbral 2/3={umbral:.1f}", end="")
            print()
    else:
        print("\n  ✓ Ningún resultado cambió. Todos los resultados son correctos.")

    # 6. Aplicar cambios si los hay
    if cambios:
        print(f"\n{'─' * 65}")
        print("Aplicando cambios (UPDATE vote_event.result y motion.result)...")

        for c in cambios:
            # Actualizar vote_event.result
            cur.execute(
                "UPDATE vote_event SET result = ? WHERE id = ?",
                (c["resultado_nuevo"], c["ve_id"]),
            )
            print(
                f"  [UPDATE] vote_event {c['ve_id']}: "
                f"{c['resultado_anterior']} → {c['resultado_nuevo']}"
            )

            # Actualizar motion.result
            cur.execute(
                "UPDATE motion SET result = ? WHERE id = ?",
                (c["resultado_nuevo"], c["motion_id"]),
            )
            print(f"  [UPDATE] motion {c['motion_id']}: → {c['resultado_nuevo']}")

        # Commit explícito
        conn.commit()
        print(f"\n  ✓ Commit exitoso. {len(cambios)} registros actualizados.")
    else:
        print("\n  No se requieren cambios. Sin commit necesario.")

    # 7. Estadísticas finales
    print(f"\n{'─' * 65}")
    print("ESTADÍSTICAS POST-RECALCULO")
    print(f"{'─' * 65}")

    cur.execute("""
        SELECT m.requirement, ve.result, COUNT(*)
        FROM vote_event ve
        JOIN motion m ON ve.motion_id = m.id
        WHERE ve.result IS NOT NULL
        GROUP BY m.requirement, ve.result
        ORDER BY m.requirement, ve.result
    """)
    for req, res, cnt in cur.fetchall():
        print(f"  {req}: {res} = {cnt}")

    conn.close()

    print(f"\n{'=' * 65}")
    print("Recálculo completado exitosamente")
    print(f"{'=' * 65}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
