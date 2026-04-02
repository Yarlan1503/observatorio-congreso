#!/usr/bin/env python3
"""
fix_curul_tipo.py — Corrige el campo curul_tipo NULL en la tabla person.

El SITL proporciona el principio de elección en las páginas de curricula.
Este script:
  1. Lee personas con curul_tipo NULL que tengan sitl_id
  2. Descarga/lee (cache) la curricula de cada una
  3. Parsea el principio de elección y lo mapea a curul_tipo
  4. Para personas sin sitl_id (suplentes), intenta match por nombre normalizado

Uso:
  python db/fix_curul_tipo.py            # ejecuta corrección
  python db/fix_curul_tipo.py --dry-run  # solo muestra cambios
  python db/fix_curul_tipo.py --stats    # muestra estado actual
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

# Asegurar que el directorio del proyecto está en sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from diputados.scraper.client import SITLClient
from diputados.scraper.config import DB_PATH, LEGISLATURAS
from diputados.scraper.legislatura import url_curricula
from diputados.scraper.parsers.diputado import parse_diputado
from diputados.scraper.utils.text_utils import normalize_name

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Mapeo principio_eleccion → curul_tipo ---
# Se usa normalización sin acentos para comparación robusta


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparación: sin acentos, lowercase, sin espacios extra."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos.lower().strip())


def mapear_curul_tipo(principio_eleccion: str) -> str | None:
    """Mapea el texto de principio de elección del SITL al valor curul_tipo de la BD.

    Reglas:
      - Contiene "mayoria relativa" (sin acentos) → "mayoria_relativa"
      - Contiene "representacion proporcional" (sin acentos) → "plurinominal"
      - Contiene "primera minoria" (sin acentos) → "mayoria_relativa"
      - Vacío o no reconocido → None

    Args:
        principio_eleccion: Texto crudo del SITL (ej: "Mayoría Relativa").

    Returns:
        Valor para curul_tipo o None si no se puede mapear.
    """
    if not principio_eleccion or not principio_eleccion.strip():
        return None

    norm = _normalizar_texto(principio_eleccion)

    if "primera minoria" in norm:
        return "mayoria_relativa"
    if "mayoria relativa" in norm:
        return "mayoria_relativa"
    if "representacion proporcional" in norm:
        return "plurinominal"

    # Patrones garbled del servidor LX (acentos reemplazados por espacios)
    if "mayor a relativa" in norm or "mayor a relativ" in norm:
        return "mayoria_relativa"
    if "representaci n proporcional" in norm or (
        "representaci" in norm and "proporcional" in norm
    ):
        return "plurinominal"

    return None


# --- Orden de recencia: LXVI > LXV > ... > LX ---
_ORDERED_LEGS = sorted(
    LEGISLATURAS.keys(), key=lambda l: LEGISLATURAS[l]["num"], reverse=True
)


def _determinar_legislaturas_persona(
    conn: sqlite3.Connection, person_id: str
) -> list[str]:
    """Determina en qué legislaturas votó una persona, ordenadas por recencia.

    Consulta la relación vote → vote_event para obtener las legislaturas.
    Retorna la lista ordenada de más reciente a más antigua.
    Si no hay votos, retorna todas las legislaturas (fallback).
    """
    rows = conn.execute(
        "SELECT DISTINCT ve.legislatura FROM vote v "
        "JOIN vote_event ve ON v.vote_event_id = ve.id "
        "WHERE v.voter_id = ? AND ve.legislatura IS NOT NULL",
        (person_id,),
    ).fetchall()
    legs_encontradas = {r[0] for r in rows}

    if not legs_encontradas:
        # Sin votos registrados: intentar con todas las legislaturas
        return list(_ORDERED_LEGS)

    # Ordenar por recencia usando el dict LEGISLATURAS
    return sorted(
        legs_encontradas,
        key=lambda l: LEGISLATURAS.get(l, {"num": 0})["num"],
        reverse=True,
    )


def show_stats(conn: sqlite3.Connection) -> None:
    """Muestra estadísticas del campo curul_tipo en la tabla person."""
    row = conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN curul_tipo IS NULL THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN curul_tipo IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM person"
    ).fetchone()
    total, null_count, has_value = row
    print(f"=== Estado de curul_tipo ===")
    print(f"Total personas:    {total}")
    print(f"Con curul_tipo:    {has_value}")
    print(f"Sin curul_tipo:    {null_count}")
    print()

    # Desglose por valor
    print("Desglose por valor:")
    for row in conn.execute(
        "SELECT curul_tipo, COUNT(*) FROM person GROUP BY curul_tipo "
        "ORDER BY COUNT(*) DESC"
    ):
        val = row[0] if row[0] else "(NULL)"
        print(f"  {val:25s} {row[1]:>4d}")
    print()

    # Personas sin sitl_id
    sin_sitl = conn.execute(
        "SELECT id, nombre FROM person WHERE identifiers_json NOT LIKE '%sitl_id%' "
        "OR identifiers_json IS NULL"
    ).fetchall()
    print(f"Personas sin sitl_id: {len(sin_sitl)}")
    for pid, nombre in sin_sitl:
        print(f"  {pid} | {nombre}")


def run_fix(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Ejecuta la corrección de curul_tipo.

    Args:
        conn: Conexión activa a SQLite.
        dry_run: Si True, solo muestra cambios sin ejecutar UPDATEs.
    """
    # --- Fase 1: Personas con sitl_id ---
    rows = conn.execute(
        "SELECT id, nombre, identifiers_json FROM person WHERE curul_tipo IS NULL"
    ).fetchall()

    con_sitl = []
    sin_sitl = []
    for pid, nombre, ids_json in rows:
        ids = json.loads(ids_json) if ids_json else {}
        sitl_id = ids.get("sitl_id")
        if sitl_id is not None:
            con_sitl.append((pid, nombre, sitl_id))
        else:
            sin_sitl.append((pid, nombre))

    logger.info(f"Personas sin curul_tipo: {len(rows)}")
    logger.info(f"  Con sitl_id: {len(con_sitl)}")
    logger.info(f"  Sin sitl_id: {len(sin_sitl)}")

    if not con_sitl and not sin_sitl:
        logger.info("No hay personas sin curul_tipo. Nada que hacer.")
        return

    # --- Scrapear y actualizar personas con sitl_id ---
    actualizadas = 0
    fallidas = 0
    saltadas = 0
    updates: list[tuple[str, str, str]] = []  # (curul_tipo, id, nombre) para log

    client = SITLClient(use_cache=True)

    try:
        for i, (pid, nombre, sitl_id) in enumerate(con_sitl, 1):
            legislaturas = _determinar_legislaturas_persona(conn, pid)
            exito = False

            for leg in legislaturas:
                url = url_curricula(leg, sitl_id)
                try:
                    html = client.get_html(url)
                    ficha = parse_diputado(html, sitl_id)

                    if ficha is None:
                        logger.debug(
                            f"[{i}/{len(con_sitl)}] {pid} {nombre}: "
                            f"parse_diputado retornó None en {leg} (sitl_id={sitl_id})"
                        )
                        continue  # intentar siguiente legislatura

                    curul_tipo = mapear_curul_tipo(ficha.principio_eleccion)

                    if curul_tipo is None:
                        logger.warning(
                            f"[{i}/{len(con_sitl)}] {pid} {nombre}: "
                            f"principio_eleccion no reconocido en {leg}: "
                            f"'{ficha.principio_eleccion}'"
                        )
                        saltadas += 1
                        exito = True  # se parseó pero no se pudo mapear; no reintentar
                        break

                    logger.debug(
                        f"[{i}/{len(con_sitl)}] {pid} {nombre}: "
                        f"leg={leg} principio='{ficha.principio_eleccion}' → {curul_tipo}"
                    )

                    if dry_run:
                        updates.append((curul_tipo, pid, nombre))
                    else:
                        conn.execute(
                            "UPDATE person SET curul_tipo = ? WHERE id = ?",
                            (curul_tipo, pid),
                        )
                        # Commit incremental cada 50 registros
                        if actualizadas > 0 and actualizadas % 50 == 0:
                            conn.commit()
                            logger.info(
                                f"Commit incremental: {actualizadas} actualizadas"
                            )
                    actualizadas += 1
                    exito = True
                    break  # éxito, no intentar más legislaturas

                except Exception as exc:
                    logger.debug(
                        f"[{i}/{len(con_sitl)}] {pid} {nombre}: error en {leg}: {exc}"
                    )
                    continue  # intentar siguiente legislatura

            if not exito:
                logger.warning(
                    f"[{i}/{len(con_sitl)}] {pid} {nombre}: "
                    f"falló en todas las legislaturas (sitl_id={sitl_id}, legs={legislaturas})"
                )
                fallidas += 1
    finally:
        client.close()

    if not dry_run and actualizadas > 0:
        conn.commit()
        logger.info(f"Commit final fase 1: {actualizadas} actualizadas")

    # --- Fase 2: Match por nombre para personas sin sitl_id ---
    match_exitoso = 0
    match_fallido = 0

    if sin_sitl:
        # Construir índice de nombres normalizados → curul_tipo
        # de personas que YA tienen curul_tipo (originales + recién actualizadas)
        indice: dict[str, str] = {}
        for row in conn.execute(
            "SELECT nombre, curul_tipo FROM person WHERE curul_tipo IS NOT NULL"
        ):
            nombre_norm = normalizar_nombre(row[0])
            indice[nombre_norm] = row[1]

        for pid, nombre in sin_sitl:
            nombre_norm = normalizar_nombre(nombre)
            if nombre_norm in indice:
                curul_tipo = indice[nombre_norm]
                logger.info(
                    f"Match por nombre: {pid} '{nombre}' → curul_tipo={curul_tipo}"
                )
                if not dry_run:
                    conn.execute(
                        "UPDATE person SET curul_tipo = ? WHERE id = ?",
                        (curul_tipo, pid),
                    )
                match_exitoso += 1
            else:
                logger.info(
                    f"Sin match por nombre: {pid} '{nombre}' "
                    f"(normalizado: '{nombre_norm}')"
                )
                match_fallido += 1

        if not dry_run:
            conn.commit()

    # --- Resumen ---
    modo = "[DRY-RUN]" if dry_run else "[EJECUTADO]"
    print(f"\n=== Resumen {modo} ===")
    print(f"Con sitl_id:")
    print(f"  Actualizadas: {actualizadas}")
    print(f"  Fallidas:     {fallidas}")
    print(f"  Saltadas:     {saltadas}")
    print(f"Sin sitl_id (match por nombre):")
    print(f"  Match:        {match_exitoso}")
    print(f"  Sin match:    {match_fallido}")

    if dry_run and updates:
        print(f"\nCambios propuestos (primeros 20):")
        for curul_tipo, pid, nombre in updates[:20]:
            print(f"  {pid} | {nombre} → {curul_tipo}")
        if len(updates) > 20:
            print(f"  ... y {len(updates) - 20} más")


def main():
    parser = argparse.ArgumentParser(
        description="Corrige curul_tipo NULL en tabla person"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra cambios sin ejecutar UPDATEs",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Muestra estado actual del campo curul_tipo",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))

    try:
        if args.stats:
            show_stats(conn)
        else:
            run_fix(conn, dry_run=args.dry_run)
    except Exception as exc:
        logger.error(f"Error fatal: {exc}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
