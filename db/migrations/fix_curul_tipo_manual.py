#!/usr/bin/env python3
"""
fix_curul_tipo_manual.py — Corrige curul_tipo para 13 diputados sin sitl_id.

Estas personas fueron importadas manualmente (P10-P20 PVEM, P22 PVEM coord,
P24 PT coord, P25 PVEM, P26 PT) y no tienen sitl_id ni identifiers_json.

Estrategia:
  1. Scrapear listado_diputados_gpnp.php de PVEM y PT en LXVI
     para obtener nombre + sitl_id de todos los diputados de esos partidos.
  2. Match por nombre normalizado para encontrar el sitl_id de cada persona.
  3. Con el sitl_id, acceder a curricula.php para extraer principio de elección.
  4. Mapear a curul_tipo y actualizar la BD.

Fallback web: Si el SITL no funciona, se usa búsqueda web para encontrar
el tipo de elección de cada diputado.

Uso:
  python db/fix_curul_tipo_manual.py            # ejecuta corrección
  python db/fix_curul_tipo_manual.py --dry-run  # solo muestra cambios
  python db/fix_curul_tipo_manual.py --stats    # muestra estado actual
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

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================
# Datos de las 13 personas a corregir
# ============================================================

# 3 no-diputados (correctamente sin curul_tipo)
NO_DIPUTADOS = {"P21", "P23", "P27"}

# 13 diputados que necesitan corrección
# (person_id, nombre, partido_short, party_sitl_id)
DIPUTADOS_MANUALES = [
    # PVEM (party_sitl_id=5 en LXVI)
    ("P10", "Manuel Cota Cárdenas", "PVEM", 5),
    ("P11", "Mario López Hernández", "PVEM", 5),
    ("P12", "Anabel Acosta", "PVEM", 5),
    ("P13", "María del Carmen Cabrera Lagunas", "PVEM", 5),
    ("P14", "Iván Marín Rangel", "PVEM", 5),
    ("P15", "Alejandro Pérez Cuéllar", "PVEM", 5),
    ("P18", "Carlos Canturosas Villarreal", "PVEM", 5),
    ("P19", "Blanca Hernández Rodríguez", "PVEM", 5),
    ("P20", "Hilda Licerio Valdés", "PVEM", 5),
    ("P22", "Carlos Puente Salas", "PVEM", 5),
    ("P25", "Raúl Bolaños Cacho", "PVEM", 5),
    # PT (party_sitl_id=4 en LXVI)
    ("P24", "Reginaldo Sandoval", "PT", 4),
    ("P26", "Pedro Vázquez González", "PT", 4),
]


# ============================================================
# Mapeo principio_eleccion → curul_tipo (reutilizado de fix_curul_tipo.py)
# ============================================================


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparación: sin acentos, lowercase, sin espacios extra."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos.lower().strip())


def mapear_curul_tipo(principio_eleccion: str) -> str | None:
    """Mapea el texto de principio de elección del SITL al valor curul_tipo."""
    if not principio_eleccion or not principio_eleccion.strip():
        return None

    norm = _normalizar_texto(principio_eleccion)

    if "primera minoria" in norm:
        return "mayoria_relativa"
    if "mayoria relativa" in norm:
        return "mayoria_relativa"
    if "representacion proporcional" in norm:
        return "plurinominal"

    # Patrones garbled del servidor LX
    if "mayor a relativa" in norm or "mayor a relativ" in norm:
        return "mayoria_relativa"
    if "representaci n proporcional" in norm or ("representaci" in norm and "proporcional" in norm):
        return "plurinominal"

    return None


# ============================================================
# Funciones de búsqueda SITL
# ============================================================


def _parse_listado_diputados(html: str) -> list[tuple[str, int]]:
    """Parsea listado_diputados_gpnp.php y extrae (nombre, sitl_id).

    Esta página lista todos los diputados de un partido con links
    a su curricula: <a href="curricula.php?dipt=NNN">Nombre</a>

    Returns:
        Lista de tuplas (nombre, sitl_id).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    resultados = []

    # Buscar todos los links a curricula.php con parámetro dipt
    for link in soup.find_all("a", href=True):
        href = link["href"]
        match = re.search(r"curricula\.php\?dipt=(\d+)", href)
        if match:
            sitl_id = int(match.group(1))
            nombre = link.get_text(strip=True)
            # Limpiar prefijo "Dip. " si existe
            if nombre.upper().startswith("DIP."):
                nombre = nombre[4:].strip()
            if nombre:
                resultados.append((nombre, sitl_id))

    return resultados


def _buscar_sitl_id_por_nombre(
    nombre_buscar: str,
    listado: list[tuple[str, int]],
) -> int | None:
    """Busca un diputado por nombre normalizado en el listado del SITL.

    Args:
        nombre_buscar: Nombre a buscar.
        listado: Lista de (nombre, sitl_id) del SITL.

    Returns:
        sitl_id si encuentra match, None si no.
    """
    nombre_norm = normalizar_nombre(nombre_buscar)

    # 1. Match exacto por nombre normalizado completo
    for nombre_sitl, sitl_id in listado:
        if normalizar_nombre(nombre_sitl) == nombre_norm:
            return sitl_id

    # 2. Match por apellidos (últimas 2+ palabras del nombre)
    partes = nombre_norm.split()
    if len(partes) >= 2:
        apellidos = " ".join(partes[-2:])
        for nombre_sitl, sitl_id in listado:
            sitl_parts = normalizar_nombre(nombre_sitl).split()
            if len(sitl_parts) >= 2:
                sitl_apellidos = " ".join(sitl_parts[-2:])
                if apellidos == sitl_apellidos:
                    return sitl_id

    # 3. Match por primer apellido
    if len(partes) >= 1:
        primer_apellido = partes[-1]  # En México: Nombre Apellido1 Apellido2
        for nombre_sitl, sitl_id in listado:
            sitl_parts = normalizar_nombre(nombre_sitl).split()
            for sp in sitl_parts:
                if sp == primer_apellido:
                    overlap = any(p in normalizar_nombre(nombre_sitl) for p in partes)
                    if overlap:
                        return sitl_id

    # 4. Match fuzzy: quitar guiones del nombre SITL y reintentar
    # (el SITL a veces usa "Bolaños-Cacho" vs nuestro "Bolaños Cacho")
    nombre_norm_sin_guiones = nombre_norm.replace("-", " ")
    nombre_norm_sin_guiones = re.sub(r"\s+", " ", nombre_norm_sin_guiones)
    for nombre_sitl, sitl_id in listado:
        sitl_norm = normalizar_nombre(nombre_sitl).replace("-", " ")
        sitl_norm = re.sub(r"\s+", " ", sitl_norm)
        if sitl_norm == nombre_norm_sin_guiones:
            return sitl_id

    # 5. Match fuzzy por substring (al menos 2 palabras del nombre aparecen)
    if len(partes) >= 2:
        for nombre_sitl, sitl_id in listado:
            sitl_norm = normalizar_nombre(nombre_sitl).replace("-", " ")
            sitl_norm = re.sub(r"\s+", " ", sitl_norm)
            # Contar cuántas palabras del nombre buscar están en el nombre SITL
            matches = sum(1 for p in partes if p in sitl_norm)
            if matches >= max(2, len(partes) - 1):
                return sitl_id

    return None


def _fetch_principio_eleccion(
    client: SITLClient, sitl_id: int, legislatura: str = "LXVI"
) -> tuple[str | None, str | None]:
    """Obtiene el principio de elección de un diputado desde su curricula.

    Args:
        client: SITLClient con caché.
        sitl_id: ID del diputado en el SITL.
        legislatura: Legislatura a consultar.

    Returns:
        Tupla (principio_eleccion_raw, curul_tipo_mapeado).
        (None, None) si no se encuentra.
    """
    # Probar legislaturas en orden de recencia
    legs = sorted(
        LEGISLATURAS.keys(),
        key=lambda l: LEGISLATURAS[l]["num"],
        reverse=True,
    )
    # Solo LXVI para estos diputados (todos son LXVI)
    if legislatura:
        legs = [legislatura] + [l for l in legs if l != legislatura]

    for leg in legs:
        url = url_curricula(leg, sitl_id)
        try:
            html = client.get_html(url)
            ficha = parse_diputado(html, sitl_id)

            if ficha is None:
                continue

            if ficha.principio_eleccion:
                curul_tipo = mapear_curul_tipo(ficha.principio_eleccion)
                return ficha.principio_eleccion, curul_tipo

        except Exception as exc:
            logger.debug(f"Error accediendo curricula de sitl_id={sitl_id} en {leg}: {exc}")
            continue

    return None, None


# ============================================================
# Función principal
# ============================================================


def show_stats(conn: sqlite3.Connection) -> None:
    """Muestra estado actual de curul_tipo para las personas relevantes."""
    print("=== Estado de curul_tipo (personas relevantes) ===")
    print()

    # Las 16 con NULL
    rows = conn.execute(
        "SELECT id, nombre, identifiers_json FROM person WHERE curul_tipo IS NULL ORDER BY id"
    ).fetchall()
    print(f"Personas con curul_tipo NULL: {len(rows)}")
    for pid, nombre, ids_json in rows:
        ids = json.loads(ids_json) if ids_json else {}
        sitl = ids.get("sitl_id", "N/A")
        categoria = "NO-DIPUTADO" if pid in NO_DIPUTADOS else "DIPUTADO"
        print(f"  {pid} | {categoria:12s} | sitl_id={sitl} | {nombre}")
    print()

    # Totales generales
    total = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    con_tipo = conn.execute("SELECT COUNT(*) FROM person WHERE curul_tipo IS NOT NULL").fetchone()[
        0
    ]
    sin_tipo = total - con_tipo
    print(f"Total personas: {total}")
    print(f"Con curul_tipo: {con_tipo} ({con_tipo / total * 100:.1f}%)")
    print(f"Sin curul_tipo: {sin_tipo} ({sin_tipo / total * 100:.1f}%)")


def run_fix(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Ejecuta la corrección de curul_tipo para los 13 diputados manuales."""
    print(f"\n{'=' * 60}")
    print(f"fix_curul_tipo_manual.py — {('[DRY-RUN]' if dry_run else '[EJECUTADO]')}")
    print(f"{'=' * 60}\n")

    client = SITLClient(use_cache=True)
    resultados: list[dict] = []

    try:
        # --- Fase 1: Obtener listados del SITL por partido ---
        print("Fase 1: Obteniendo listados de diputados del SITL...")

        listado_pvem: list[tuple[str, int]] = []
        listado_pt: list[tuple[str, int]] = []

        base_url = LEGISLATURAS["LXVI"]["base_url"]

        # PVEM
        pvem_url = f"{base_url}/listado_diputados_gpnp.php?tipot=5"
        try:
            pvem_html = client.get_html(pvem_url)
            listado_pvem = _parse_listado_diputados(pvem_html)
            logger.info(f"PVEM: {len(listado_pvem)} diputados encontrados en listado")
        except Exception as exc:
            logger.error(f"Error obteniendo listado PVEM: {exc}")

        # PT
        pt_url = f"{base_url}/listado_diputados_gpnp.php?tipot=4"
        try:
            pt_html = client.get_html(pt_url)
            listado_pt = _parse_listado_diputados(pt_html)
            logger.info(f"PT: {len(listado_pt)} diputados encontrados en listado")
        except Exception as exc:
            logger.error(f"Error obteniendo listado PT: {exc}")

        print(f"  PVEM: {len(listado_pvem)} diputados en listado")
        print(f"  PT:   {len(listado_pt)} diputados en listado")
        print()

        # --- Fase 2: Buscar sitl_id por nombre para cada persona ---
        print("Fase 2: Buscando sitl_id por nombre...")
        personas_con_sitl: list[tuple[str, str, int]] = []  # pid, nombre, sitl_id

        for pid, nombre, partido, _party_id in DIPUTADOS_MANUALES:
            listado = listado_pvem if partido == "PVEM" else listado_pt
            sitl_id = _buscar_sitl_id_por_nombre(nombre, listado)

            if sitl_id:
                logger.info(f"  ✓ {pid} {nombre} → sitl_id={sitl_id}")
                personas_con_sitl.append((pid, nombre, sitl_id))
            else:
                logger.warning(f"  ✗ {pid} {nombre} — NO encontrado en listado {partido}")
                resultados.append(
                    {
                        "pid": pid,
                        "nombre": nombre,
                        "status": "no_encontrado_listado",
                        "sitl_id": None,
                        "principio": None,
                        "curul_tipo": None,
                    }
                )

        print(f"  Encontrados: {len(personas_con_sitl)}/{len(DIPUTADOS_MANUALES)}")
        print()

        # --- Fase 3: Scrapear curricula y extraer principio de elección ---
        print("Fase 3: Extrayendo principio de elección de curriculas...")
        actualizadas = 0

        for i, (pid, nombre, sitl_id) in enumerate(personas_con_sitl, 1):
            principio_raw, curul_tipo = _fetch_principio_eleccion(client, sitl_id)

            if curul_tipo:
                logger.info(
                    f"  [{i}/{len(personas_con_sitl)}] {pid} {nombre}: "
                    f"'{principio_raw}' → {curul_tipo}"
                )
                resultados.append(
                    {
                        "pid": pid,
                        "nombre": nombre,
                        "status": "ok",
                        "sitl_id": sitl_id,
                        "principio": principio_raw,
                        "curul_tipo": curul_tipo,
                    }
                )

                if not dry_run:
                    # Actualizar curul_tipo
                    conn.execute(
                        "UPDATE person SET curul_tipo = ? WHERE id = ?",
                        (curul_tipo, pid),
                    )
                    # También actualizar identifiers_json con el sitl_id encontrado
                    row = conn.execute(
                        "SELECT identifiers_json FROM person WHERE id = ?", (pid,)
                    ).fetchone()
                    if row and row[0]:
                        ids = json.loads(row[0])
                    else:
                        ids = {}
                    ids["sitl_id"] = sitl_id
                    conn.execute(
                        "UPDATE person SET identifiers_json = ? WHERE id = ?",
                        (json.dumps(ids), pid),
                    )

                actualizadas += 1
            else:
                principio_str = principio_raw or "(vacío)"
                logger.warning(
                    f"  [{i}/{len(personas_con_sitl)}] {pid} {nombre}: "
                    f"principio='{principio_str}' → NO MAPEABLE"
                )
                resultados.append(
                    {
                        "pid": pid,
                        "nombre": nombre,
                        "status": "principio_no_mapeable",
                        "sitl_id": sitl_id,
                        "principio": principio_raw,
                        "curul_tipo": None,
                    }
                )

        if not dry_run and actualizadas > 0:
            conn.commit()
            logger.info(f"Commit: {actualizadas} actualizaciones")

        # --- Fase 4: Fallback web para los no encontrados ---
        no_encontrados = [r for r in resultados if r["status"] != "ok"]
        if no_encontrados:
            print(f"\nFase 4: {len(no_encontrados)} personas sin resolver via SITL.")
            print("  Estas personas necesitarán lookup manual o búsqueda web:")
            for r in no_encontrados:
                print(f"    {r['pid']} {r['nombre']} — {r['status']}")

    finally:
        client.close()

    # --- Resumen ---
    print(f"\n{'=' * 60}")
    print(f"RESUMEN {('[DRY-RUN]' if dry_run else '[EJECUTADO]')}")
    print(f"{'=' * 60}")
    print()

    ok = [r for r in resultados if r["status"] == "ok"]
    no_listado = [r for r in resultados if r["status"] == "no_encontrado_listado"]
    no_mapeable = [r for r in resultados if r["status"] == "principio_no_mapeable"]

    print(f"Corregidos:       {len(ok)}")
    for r in ok:
        print(
            f"  {r['pid']} {r['nombre']} → {r['curul_tipo']} (sitl_id={r['sitl_id']}, principio='{r['principio']}')"
        )

    print(f"\nNo encontrados:   {len(no_listado)}")
    for r in no_listado:
        print(f"  {r['pid']} {r['nombre']}")

    print(f"\nNo mapeables:     {len(no_mapeable)}")
    for r in no_mapeable:
        print(f"  {r['pid']} {r['nombre']} (principio='{r['principio']}')")

    print(f"\nTotal: {len(ok)}/{len(DIPUTADOS_MANUALES)} corregidos")

    return resultados


def main():
    parser = argparse.ArgumentParser(
        description="Corrige curul_tipo para 13 diputados manuales sin sitl_id"
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
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    try:
        if args.stats:
            show_stats(conn)
        else:
            run_fix(conn, dry_run=args.dry_run)
            # Mostrar stats finales
            print()
            show_stats(conn)
    except Exception as exc:
        logger.error(f"Error fatal: {exc}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
