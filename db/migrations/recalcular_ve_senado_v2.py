#!/usr/bin/env python3
"""
recalcular_ve_senado_v2.py — Recalcula 206 VEs del Senado usando COUNT(vote).

Problema: 164 empates + 42 rechazadas del Senado tienen counts=0 en la tabla
count (el scraper no capturó counts globales en LXII/LXIV/LXVI), pero los votos
individuales en la tabla vote muestran mayoría a favor. El recálculo anterior
(recalcular_resultados.py) usó la tabla count, que estaba vacía para estos VEs.

Solución: Usa COUNT(*) FROM vote para calcular presentes, pro, contra y abst,
luego aplica determinar_resultado() con los datos reales.

Seguridad:
- Solo actualiza VEs donde el resultado calculado difiere del actual.
- No toca VEs ya correctamente recalculados (mismo resultado con vote counts).
- Actualiza vote_event.result, vote_event.voter_count y motion.result.
- Transacción con commit explícito al final.

Uso:  uv run python db/migrations/recalcular_ve_senado_v2.py
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")


def determinar_resultado(
    pro_count: int,
    contra_count: int,
    requirement: str = "mayoria_simple",
    abstention_count: int = 0,
) -> str:
    """Determina el resultado de una votación según el tipo de mayoría.

    Replica la lógica de senado.scrapers.votaciones.transformers.determinar_resultado.
    """
    if requirement == "mayoria_calificada":
        presentes = pro_count + contra_count + abstention_count
        if presentes == 0:
            return "rechazada"
        if abstention_count == 0:
            # Fallback a mayoría simple si no hay datos de abstención
            if pro_count > contra_count:
                return "aprobada"
            elif pro_count < contra_count:
                return "rechazada"
            else:
                return "empate"
        umbral = (2 / 3) * presentes
        if pro_count >= umbral:
            return "aprobada"
        else:
            return "rechazada"
    else:
        if pro_count > contra_count:
            return "aprobada"
        elif pro_count < contra_count:
            return "rechazada"
        else:
            return "empate"


def main():
    print("=" * 65)
    print("Recalcular VEs del Senado v2 — usando COUNT(vote)")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] Base de datos no encontrada: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    cur = conn.cursor()

    # 1. Obtener todos los vote_events del Senado con resultado no-NULL
    cur.execute("""
        SELECT ve.id, ve.result, ve.voter_count, ve.requirement, m.requirement as motion_req
        FROM vote_event ve
        JOIN motion m ON ve.motion_id = m.id
        WHERE ve.organization_id = 'O09'
        AND ve.result IS NOT NULL
        ORDER BY ve.id
    """)
    vote_events = cur.fetchall()
    print(f"\nVote_events del Senado (result IS NOT NULL): {len(vote_events)}")

    cambios = []

    for ve_id, ve_result, voter_count, ve_requirement, motion_req in vote_events:
        # 2. Contar votos individuales (fuente de verdad)
        cur.execute(
            """
            SELECT option, COUNT(*) as cnt
            FROM vote
            WHERE vote_event_id = ?
            GROUP BY option
        """,
            (ve_id,),
        )
        votos = {option: cnt for option, cnt in cur.fetchall()}

        pro = votos.get("a_favor", 0)
        contra = votos.get("en_contra", 0)
        abst = votos.get("abstencion", 0)
        ausente = votos.get("ausente", 0)
        presentes = pro + contra + abst

        # Skip VEs sin votos individuales (fantasmas — ya handled)
        if presentes == 0:
            continue

        # 3. Usar requirement del motion (fuente de verdad) o del vote_event
        requirement = motion_req or ve_requirement or "mayoria_simple"

        # 4. Calcular resultado
        resultado_nuevo = determinar_resultado(pro, contra, requirement, abst)

        # 5. Comparar con resultado actual
        if resultado_nuevo != ve_result:
            cambio = {
                "ve_id": ve_id,
                "resultado_anterior": ve_result,
                "resultado_nuevo": resultado_nuevo,
                "requirement": requirement,
                "pro": pro,
                "contra": contra,
                "abst": abst,
                "ausente": ausente,
                "presentes": presentes,
                "voter_count_anterior": voter_count,
            }
            cambios.append(cambio)

    # 6. Mostrar resumen
    print(f"\n{'─' * 65}")
    print("RESUMEN DE CAMBIOS")
    print(f"{'─' * 65}")
    print(f"VEs procesados: {len(vote_events)}")
    print("VEs sin votos (fantasmas, skip): omitidos")
    print(f"Resultados que cambian: {len(cambios)}")

    if cambios:
        print("\nDetalle de cambios:")
        for c in cambios:
            print(f"\n  [{c['ve_id']}] req={c['requirement']}")
            print(f"    {c['resultado_anterior']} → {c['resultado_nuevo']}")
            print(
                f"    Pro={c['pro']} Contra={c['contra']} Abst={c['abst']} Aus={c['ausente']} Presentes={c['presentes']}"
            )
            if c["requirement"] == "mayoria_calificada":
                umbral = (2.0 / 3.0) * c["presentes"]
                print(f"    Umbral 2/3={umbral:.1f}")

    # 7. Aplicar cambios
    if cambios:
        print(f"\n{'─' * 65}")
        print("Aplicando cambios...")

        for c in cambios:
            # Actualizar vote_event
            cur.execute(
                "UPDATE vote_event SET result = ?, voter_count = ? WHERE id = ?",
                (c["resultado_nuevo"], c["presentes"], c["ve_id"]),
            )

            # Actualizar motion
            cur.execute(
                """UPDATE motion SET result = ?
                WHERE id = (SELECT motion_id FROM vote_event WHERE id = ?)""",
                (c["resultado_nuevo"], c["ve_id"]),
            )

            print(
                f"  [UPDATE] {c['ve_id']}: {c['resultado_anterior']} → {c['resultado_nuevo']} (presentes={c['presentes']})"
            )

        conn.commit()
        print(f"\n  ✓ Commit exitoso. {len(cambios)} registros actualizados.")
    else:
        print("\n  ✓ No se requieren cambios.")

    # 8. Estadísticas finales
    print(f"\n{'─' * 65}")
    print("ESTADÍSTICAS POST-RECALCULO")
    print(f"{'─' * 65}")
    cur.execute("""
        SELECT ve.result, COUNT(*)
        FROM vote_event ve
        WHERE ve.organization_id = 'O09' AND ve.result IS NOT NULL
        GROUP BY ve.result
        ORDER BY COUNT(*) DESC
    """)
    for res, cnt in cur.fetchall():
        print(f"  {res}: {cnt}")

    conn.close()
    print(f"\n{'=' * 65}")
    print("Recálculo completado exitosamente")
    print(f"{'=' * 65}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
