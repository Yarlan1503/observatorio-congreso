#!/usr/bin/env python3
"""Backfill fecha_nacimiento y curul_tipo desde fichas SITL de diputados.

Scrapea las fichas curriculares (curricula.php) del SITL para cada diputado
que tenga sitl_id en identifiers_json y que aún no tenga fecha_nacimiento
o curul_tipo poblados.

Usa SITLClient (caché file-based + rate limiting) y parse_diputado() para
extraer los datos.

Uso:
    python db/migrations/backfill_fichas_diputados.py            # ejecuta todo
    python db/migrations/backfill_fichas_diputados.py --dry-run  # solo muestra
    python db/migrations/backfill_fichas_diputados.py --legislatura LXVI
    python db/migrations/backfill_fichas_diputados.py --limit 10
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path

# Añadir proyecto al path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bs4 import BeautifulSoup

from diputados.scraper.client import SITLClient
from diputados.scraper.config import LEGISLATURAS
from diputados.scraper.parsers.diputado import parse_diputado

REPO = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO / "db" / "congreso.db"

# Orden de procesamiento: LXVI primero (disponible), luego LXV, LXIV,
# y finalmente legacy (LX-LXIII que pueden estar caídos)
LEGISLATURA_ORDER = ["LXVI", "LXV", "LXIV", "LX", "LXI", "LXII", "LXIII"]

# Meses en español para parsear fechas del SITL ("28-marzo - 1976")
MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# Mapeo de principio_eleccion (texto del SITL) → curul_tipo (valor en BD)
CURUL_MAP = {
    "mayoria_relativa": "mayoria_relativa",
    "mayoría relativa": "mayoria_relativa",
    "representación proporcional": "plurinominal",
    "representacion proporcional": "plurinominal",
    "primera minoría": "mayoria_relativa",
    "primera minoria": "mayoria_relativa",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_sitl_fecha(raw: str) -> str | None:
    """Parsea fecha del SITL '28-marzo - 1976' → '1976-03-28' (ISO)."""
    if not raw:
        return None
    raw = raw.strip()
    # Patrón: DD-mes[- ]YYYY (con guiones y espacios variables)
    match = re.match(r"(\d{1,2})\s*-\s*(\w+)\s*[- ]+\s*(\d{4})", raw)
    if not match:
        return None
    dia_str, mes_nombre, anio = match.groups()
    mes = MESES.get(mes_nombre.lower())
    if not mes:
        return None
    return f"{anio}-{mes:02d}-{int(dia_str):02d}"


def map_curul_tipo(principio: str) -> str | None:
    """Mapea principio_eleccion del SITL a curul_tipo de la BD.

    Usa comparación case-insensitive y maneja encoding roto en legacy:
      - "Mayor a Relativa" → "mayoría relativa" (LX-LXII sin acentos)
      - "Representaci n proporcional" → "representación proporcional"
    """
    if not principio:
        return None
    val = principio.lower().strip()
    # Normalizar encoding roto: letras sueltas rodeadas de espacios
    # "Mayor a Relativa" → "mayor a relativa" → match
    if "mayor" in val and "relativa" in val:
        return "mayoria_relativa"
    if "representaci" in val and "proporcional" in val:
        return "plurinominal"
    if "primera minor" in val:
        return "mayoria_relativa"
    # Fallback: match exacto con el mapa
    return CURUL_MAP.get(val)


def extract_fecha_nacimiento_legacy(html: str) -> str | None:
    """Extrae fecha de nacimiento del HTML legacy (LX-LXV).

    Las fichas LX-LXV usan templates con tablas y <font> tags:
        LX-LXIII: <td><font>Fecha Nacimiento: </font></td>
        LXIV:     <td>Onomástico: </td>
        LXV:      <td><font>Fecha Nacimiento: </font></td>
    El valor siempre está en el <td> hermano siguiente.

    A diferencia de LXVI que usa iconos Font Awesome.
    """
    soup = BeautifulSoup(html, "lxml")
    keywords = ("Nacimiento", "nacimiento", "Onomástico", "Onomastico", "onomástico", "onomastico")
    for text in soup.find_all(string=lambda t: t and any(kw in t for kw in keywords)):
        td = text.find_parent("td")
        if td:
            next_td = td.find_next_sibling("td")
            if next_td:
                raw = next_td.get_text(strip=True)
                if raw:
                    return parse_sitl_fecha(raw)
    return None


def extract_principio_legacy(html: str) -> str | None:
    """Extrae principio de elección del HTML legacy (LX-LXV).

    Busca texto 'Tipo de elección' o 'Principio de elección' en celdas.
    """
    soup = BeautifulSoup(html, "lxml")
    for text in soup.find_all(
        string=lambda t: t and ("tipo de elecci" in t.lower() or "principio de elecci" in t.lower())
    ):
        td = text.find_parent("td")
        if td:
            next_td = td.find_next_sibling("td")
            if next_td:
                strong = next_td.find("strong")
                valor = strong.get_text(strip=True) if strong else next_td.get_text(strip=True)
                if valor:
                    return valor
    return None


def build_ficha_url(legislatura: str, sitl_id: int) -> str | None:
    """Construye la URL de la ficha curricular.

    Ejemplo: https://sitl.diputados.gob.mx/LXVI_leg/curricula.php?dipt=112
    """
    leg_data = LEGISLATURAS.get(legislatura)
    if not leg_data:
        return None
    base_url = leg_data["base_url"]
    return f"{base_url}/curricula.php?dipt={sitl_id}"


def connect_db() -> sqlite3.Connection:
    """Conecta a la BD con PRAGMAs correctos."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA foreign_keys = ON")
    return db


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def get_diputados_to_process(db: sqlite3.Connection) -> list[dict]:
    """Obtiene diputados con sitl_id, tomando la legislatura donde más votó.

    Returns:
        Lista de dicts con keys: id, nombre, identifiers_json,
        fecha_nacimiento, curul_tipo, legislatura, num_votes
    """
    rows = db.execute(
        """
        SELECT p.id, p.nombre, p.identifiers_json, p.fecha_nacimiento,
               p.curul_tipo, ve.legislatura, COUNT(*) as num_votes
        FROM person p
        JOIN vote v ON v.voter_id = p.id
        JOIN vote_event ve ON v.vote_event_id = ve.id
        WHERE ve.id LIKE 'VE_D%'
          AND p.identifiers_json LIKE '%sitl_id%'
        GROUP BY p.id, ve.legislatura
        ORDER BY p.id, num_votes DESC
        """
    ).fetchall()

    # Para cada persona, quedarse solo con la legislatura donde más votó
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        pid = row["id"]
        if pid in seen:
            continue
        seen.add(pid)
        result.append(dict(row))

    return result


def get_coverage(db: sqlite3.Connection) -> dict:
    """Retorna coverage actual de fecha_nacimiento y curul_tipo."""
    row = db.execute(
        """
        SELECT
            COUNT(*) as total,
            COUNT(fecha_nacimiento) as con_fnac,
            COUNT(curul_tipo) as con_curul
        FROM person
        WHERE identifiers_json LIKE '%sitl_id%'
        """
    ).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# Procesamiento
# ---------------------------------------------------------------------------


def process_ficha(
    db: sqlite3.Connection,
    client: SITLClient,
    diputado: dict,
    dry_run: bool = False,
) -> dict:
    """Scrapea, parsea y actualiza la ficha de un diputado.

    Returns:
        Dict con resultado: {status, fecha_nacimiento, curul_tipo, error}
    """
    pid = diputado["id"]
    nombre = diputado["nombre"]
    legislatura = diputado["legislatura"]
    has_fnac = diputado["fecha_nacimiento"] is not None and diputado["fecha_nacimiento"] != ""
    has_curul = diputado["curul_tipo"] is not None

    # Si ya tiene ambos, skip
    if has_fnac and has_curul:
        return {"status": "skip_complete", "fecha_nacimiento": None, "curul_tipo": None}

    # Extraer sitl_id
    try:
        ids = json.loads(diputado["identifiers_json"])
        sitl_id = ids.get("sitl_id")
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "error": "identifiers_json inválido"}

    if not sitl_id:
        return {"status": "error", "error": "sitl_id no encontrado"}

    # Construir URL
    url = build_ficha_url(legislatura, sitl_id)
    if not url:
        return {"status": "error", "error": f"Legislatura {legislatura} no configurada"}

    # Scrapear
    try:
        html = client.get_html(url)
    except Exception as exc:
        err_msg = str(exc)
        # Detectar 404 específicamente
        if "404" in err_msg or "Not Found" in err_msg:
            logger.warning(
                f"[{legislatura}] {pid}: {nombre} (sitl_id={sitl_id}) → ficha no disponible (HTTP 404)"
            )
        else:
            logger.warning(
                f"[{legislatura}] {pid}: {nombre} (sitl_id={sitl_id}) → error HTTP: {exc}"
            )
        return {"status": "error_http", "error": str(exc)}

    # Parsear
    ficha = parse_diputado(html, sitl_id=sitl_id)
    if not ficha:
        logger.warning(
            f"[{legislatura}] {pid}: {nombre} (sitl_id={sitl_id}) → ficha vacía (sin nombre)"
        )
        return {"status": "error_parse", "error": "ficha vacía"}

    # Extraer fecha_nacimiento
    fnac_iso = None
    if not has_fnac:
        # Intentar con el parser principal (LXVI: iconos Font Awesome)
        if ficha.fecha_nacimiento:
            fnac_iso = parse_sitl_fecha(ficha.fecha_nacimiento)
        # Fallback: parser legacy (LX-LXV: tablas con <font>)
        if not fnac_iso:
            fnac_raw = extract_fecha_nacimiento_legacy(html)
            if fnac_raw:
                fnac_iso = fnac_raw  # Ya viene en formato ISO de parse_sitl_fecha

    # Mapear curul_tipo
    curul_tipo = None
    if not has_curul:
        # Intentar con el parser principal
        if ficha.principio_eleccion:
            curul_tipo = map_curul_tipo(ficha.principio_eleccion)
        # Fallback: parser legacy (LX-LXV)
        if not curul_tipo:
            principio_legacy = extract_principio_legacy(html)
            if principio_legacy:
                curul_tipo = map_curul_tipo(principio_legacy)

    # Log del resultado
    parts = []
    if fnac_iso:
        parts.append(f"fnac={fnac_iso}")
    if curul_tipo:
        parts.append(f"curul={curul_tipo}")
    if not parts:
        parts.append("sin datos nuevos")
    logger.info(f"[{legislatura}] {pid}: {nombre} (sitl_id={sitl_id}) → {', '.join(parts)}")

    # Actualizar BD
    updated_fnac = False
    updated_curul = False

    if not dry_run:
        if fnac_iso:
            cursor = db.execute(
                "UPDATE person SET fecha_nacimiento = ? WHERE id = ? AND (fecha_nacimiento IS NULL OR fecha_nacimiento = '')",
                (fnac_iso, pid),
            )
            updated_fnac = cursor.rowcount > 0

        if curul_tipo:
            cursor = db.execute(
                "UPDATE person SET curul_tipo = ? WHERE id = ? AND curul_tipo IS NULL",
                (curul_tipo, pid),
            )
            updated_curul = cursor.rowcount > 0

        db.commit()

    return {
        "status": "ok",
        "fecha_nacimiento": fnac_iso if (fnac_iso and not has_fnac) else None,
        "curul_tipo": curul_tipo if (curul_tipo and not has_curul) else None,
        "updated_fnac": updated_fnac,
        "updated_curul": updated_curul,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill fecha_nacimiento y curul_tipo desde fichas SITL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar qué se haría, sin actualizar la BD",
    )
    parser.add_argument(
        "--legislatura",
        type=str,
        default=None,
        help="Solo procesar una legislatura específica (ej: LXVI)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar solo N diputados",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logger.info(f"BD: {DB_PATH}")
    logger.info(f"Dry run: {args.dry_run}")
    if args.legislatura:
        logger.info(f"Legislatura filtro: {args.legislatura}")
    if args.limit:
        logger.info(f"Límite: {args.limit} diputados")

    db = connect_db()

    # Coverage pre
    cov_pre = get_coverage(db)
    logger.info(
        f"Coverage PRE → total: {cov_pre['total']}, "
        f"fecha_nacimiento: {cov_pre['con_fnac']}/{cov_pre['total']} "
        f"({cov_pre['con_fnac'] / cov_pre['total'] * 100:.1f}%), "
        f"curul_tipo: {cov_pre['con_curul']}/{cov_pre['total']} "
        f"({cov_pre['con_curul'] / cov_pre['total'] * 100:.1f}%)"
    )

    # Obtener diputados a procesar
    diputados = get_diputados_to_process(db)
    logger.info(f"Diputados con sitl_id encontrados: {len(diputados)}")

    # Filtrar por legislatura si se especifica
    if args.legislatura:
        leg_filter = args.legislatura.upper()
        diputados = [d for d in diputados if d["legislatura"] == leg_filter]
        logger.info(f"Filtrado a legislatura {leg_filter}: {len(diputados)} diputados")
    else:
        # Ordenar por legislatura según LEGISLATURA_ORDER
        leg_order = {leg: i for i, leg in enumerate(LEGISLATURA_ORDER)}
        diputados.sort(key=lambda d: leg_order.get(d["legislatura"], 99))

    # Aplicar límite
    if args.limit:
        diputados = diputados[: args.limit]
        logger.info(f"Limited a {args.limit} diputados")

    # Procesar
    stats = {
        "total": 0,
        "ok": 0,
        "skip_complete": 0,
        "error_http": 0,
        "error_parse": 0,
        "error": 0,
        "fnac_inserted": 0,
        "curul_inserted": 0,
    }
    errors_by_leg: dict[str, int] = {}

    with SITLClient(use_cache=True, delay=2.0, timeout=30.0) as client:
        for dip in diputados:
            stats["total"] += 1
            leg = dip["legislatura"]

            # Para legislaturas legacy, usar try/except amplio
            is_legacy = leg in ("LX", "LXI", "LXII", "LXIII")
            try:
                result = process_ficha(db, client, dip, dry_run=args.dry_run)
            except Exception as exc:
                if is_legacy:
                    # Silencioso para legacy
                    logger.debug(f"[{leg}] {dip['id']}: {dip['nombre']} → skip (legacy): {exc}")
                    stats["error"] += 1
                    errors_by_leg[leg] = errors_by_leg.get(leg, 0) + 1
                    continue
                else:
                    raise

            status = result.get("status", "error")
            stats[status] = stats.get(status, 0) + 1

            if status == "error_http" or status == "error_parse" or status == "error":
                errors_by_leg[leg] = errors_by_leg.get(leg, 0) + 1

            if result.get("updated_fnac") or (result.get("fecha_nacimiento") and args.dry_run):
                stats["fnac_inserted"] += 1

            if result.get("updated_curul") or (result.get("curul_tipo") and args.dry_run):
                stats["curul_inserted"] += 1

    # Coverage post
    cov_post = get_coverage(db)

    # Reporte final
    print("\n" + "=" * 60)
    print("REPORTE BACKFILL FICHAS DIPUTADOS")
    print("=" * 60)
    print(f"Modo:                {'DRY RUN' if args.dry_run else 'EJECUCIÓN'}")
    print(f"Total procesados:    {stats['total']}")
    print(f"Fichas OK:           {stats.get('ok', 0)}")
    print(f"Skip (ya completo):  {stats.get('skip_complete', 0)}")
    print(f"Errores HTTP:        {stats.get('error_http', 0)}")
    print(f"Errores parseo:      {stats.get('error_parse', 0)}")
    print(f"Otros errores:       {stats.get('error', 0)}")
    print("---")
    fnac_label = "nuevos" if not args.dry_run else "pendientes"
    curul_label = "nuevos" if not args.dry_run else "pendientes"
    print(f"fecha_nacimiento {fnac_label}: {stats['fnac_inserted']}")
    print(f"curul_tipo {curul_label}:       {stats['curul_inserted']}")
    print("---")
    print(
        f"Coverage PRE  → fnac: {cov_pre['con_fnac']}/{cov_pre['total']} ({cov_pre['con_fnac'] / cov_pre['total'] * 100:.1f}%), curul: {cov_pre['con_curul']}/{cov_pre['total']} ({cov_pre['con_curul'] / cov_pre['total'] * 100:.1f}%)"
    )
    print(
        f"Coverage POST → fnac: {cov_post['con_fnac']}/{cov_post['total']} ({cov_post['con_fnac'] / cov_post['total'] * 100:.1f}%), curul: {cov_post['con_curul']}/{cov_post['total']} ({cov_post['con_curul'] / cov_post['total'] * 100:.1f}%)"
    )
    if errors_by_leg:
        print("---")
        print("Errores por legislatura:")
        for leg, count in sorted(errors_by_leg.items()):
            print(f"  {leg}: {count}")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
