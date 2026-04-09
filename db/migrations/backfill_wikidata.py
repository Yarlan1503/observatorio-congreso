#!/usr/bin/env python3
"""Backfill fecha_nacimiento y genero desde Wikidata.

Consulta Wikidata vía SPARQL para obtener fecha_nacimiento y género de
diputados y senadores mexicanos, hace fuzzy matching contra la BD local,
y actualiza los campos vacíos (idempotente).

Uso:
    python db/migrations/backfill_wikidata.py            # ejecuta todo
    python db/migrations/backfill_wikidata.py --dry-run  # solo muestra, no actualiza
"""

import re
import sqlite3
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

try:
    import json
    import urllib.parse
    import urllib.request
except ImportError:
    print("ERROR: Se requiere urllib y json (stdlib)")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO / "db" / "congreso.db"

# ── Wikidata config ────────────────────────────────────────────────────────
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "ObservatorioCongreso/1.0 (https://github.com/observatorio-congreso; research)",
    "Accept": "application/sparql-results+json",
}

# Q-IDs verificados el 2026-04-09:
#   Q18534310 = "Member of the Chamber of Deputies of Mexico"
#   Q19971999 = "member of the Senate of Mexico"
Q_DIPUTADO = "Q18534310"
Q_SENADOR = "Q19971999"

FUZZY_THRESHOLD = 0.85
SPARQL_PAGE_SIZE = 5000
RATE_LIMIT_SECONDS = 2


# ── SPARQL Queries ─────────────────────────────────────────────────────────

SPARQL_TEMPLATE = """\
SELECT ?item ?itemLabel ?fechaNacimiento ?generoLabel WHERE {{
  ?item wdt:P39 wd:{qid} .
  OPTIONAL {{ ?item wdt:P569 ?fechaNacimiento . }}
  OPTIONAL {{ ?item wdt:P21 ?genero . ?genero rdfs:label ?generoLabel . FILTER(LANG(?generoLabel) = "es") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en" . }}
}}
LIMIT {limit}
OFFSET {offset}"""


# ── Normalización ──────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    """
    Normaliza un nombre para comparación fuzzy:
    - Lowercase
    - Quitar tildes (NFD + filtrar combining marks)
    - Quitar puntos
    - Quitar prefijos: Dip., Sen., Senadora, Diputada, Diputado
    - Quitar texto entre paréntesis como (LICENCIA), (DECESO)
    - Normalizar espacios
    """
    if not text:
        return ""
    n = text.strip()
    # Quitar prefijos comunes
    n = re.sub(
        r"^(Dip\.\s*|Sen\.\s*|Senadora\s+|Diputada\s+|Diputado\s+)",
        "",
        n,
        flags=re.IGNORECASE,
    )
    # Quitar texto entre paréntesis
    n = re.sub(r"\s*\([^)]*\)\s*", " ", n)
    # Quitar puntos
    n = n.replace(".", "")
    # Quitar comas
    n = n.replace(",", " ")
    # NFD: separar base chars de combining marks (tildes)
    n = unicodedata.normalize("NFD", n)
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    # Volver a NFC
    n = unicodedata.normalize("NFC", n)
    # Lowercase
    n = n.lower()
    # Normalizar espacios
    n = re.sub(r"\s+", " ", n).strip()
    return n


def extract_bd_sort_key(nombre: str) -> str:
    """
    Convierte nombre de BD "Apellido1 Apellido2, Nombre1 Nombre2"
    a formato normalizado "nombre1 nombre2 apellido1 apellido2"
    (mismo orden que Wikidata: Nombre primero, Apellidos después).
    """
    n = nombre.strip()
    # Quitar prefijos
    n = re.sub(
        r"^(Dip\.\s*|Sen\.\s*|Senadora\s+|Diputada\s+|Diputado\s+)",
        "",
        n,
        flags=re.IGNORECASE,
    )
    # Quitar texto entre paréntesis
    n = re.sub(r"\s*\([^)]*\)\s*", " ", n)
    n = n.strip()

    if "," in n:
        # Formato "Apellido, Nombre" → "Nombre Apellido" (reordenar)
        parts = n.split(",", 1)
        apellidos = parts[0].strip()
        nombres = parts[1].strip()
        n = nombres + " " + apellidos
    # else: ya está en formato "Nombre Apellido" o mixto

    # Normalizar (tildes, lowercase, etc.)
    n = n.replace(".", "")
    n = unicodedata.normalize("NFD", n)
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    n = unicodedata.normalize("NFC", n)
    n = n.lower()
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ── Parseo de respuestas ───────────────────────────────────────────────────


def extract_date(raw: str) -> str | None:
    """Convierte '+1956-03-28T00:00:00Z' → '1956-03-28'."""
    if not raw:
        return None
    # Quitar prefijo + y sufijo T00:00:00Z
    cleaned = raw.lstrip("+").split("T")[0]
    # Validar formato YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        return cleaned
    return None


def map_genero(label: str) -> str | None:
    """Mapea 'masculino' → 'M', 'femenino' → 'F', etc."""
    if not label:
        return None
    label_lower = label.lower().strip()
    if label_lower in ("masculino", "male", "hombre"):
        return "M"
    if label_lower in ("femenino", "female", "mujer"):
        return "F"
    # Intersex / non-binary
    if label_lower in ("intersex",):
        return "NB"
    return None


# ── Wikidata queries ───────────────────────────────────────────────────────


def query_wikidata(sparql: str) -> list[dict]:
    """Ejecuta query SPARQL contra Wikidata y retorna resultados."""
    url = WIKIDATA_ENDPOINT + "?" + urllib.parse.urlencode({"query": sparql, "format": "json"})
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", {}).get("bindings", [])
    except Exception as e:
        print(f"  ✗ Error SPARQL: {e}")
        return []


def fetch_all_results(qid: str, query_template: str, label: str) -> list[dict]:
    """Pagina resultados SPARQL para obtener todos los registros."""
    all_results = []
    offset = 0
    while True:
        sparql = query_template.format(qid=qid, limit=SPARQL_PAGE_SIZE, offset=offset)
        print(f"  Consultando {label} (offset={offset})...")
        batch = query_wikidata(sparql)
        if not batch:
            break
        all_results.extend(batch)
        print(f"    → {len(batch)} resultados (total acumulado: {len(all_results)})")
        if len(batch) < SPARQL_PAGE_SIZE:
            break
        offset += SPARQL_PAGE_SIZE
        time.sleep(RATE_LIMIT_SECONDS)
    return all_results


def parse_wikidata_results(bindings: list[dict]) -> list[dict]:
    """Convierte bindings SPARQL en dicts limpios."""
    parsed = []
    seen = set()  # deduplicar por Wikidata URI
    for b in bindings:
        uri = b.get("item", {}).get("value", "")
        if uri in seen:
            continue
        seen.add(uri)

        nombre = b.get("itemLabel", {}).get("value", "").strip()
        if not nombre or nombre.startswith("Q"):  # label vacío = sin etiqueta
            continue

        fecha_raw = b.get("fechaNacimiento", {}).get("value", "")
        fecha = extract_date(fecha_raw)

        genero_label = b.get("generoLabel", {}).get("value", "")
        genero = map_genero(genero_label)

        parsed.append(
            {
                "wikidata_uri": uri,
                "nombre": nombre,
                "nombre_norm": normalize(nombre),
                "fecha_nacimiento": fecha,
                "genero": genero,
            }
        )
    return parsed


# ── BD helpers ─────────────────────────────────────────────────────────────


def load_bd_persons(db: sqlite3.Connection) -> dict:
    """
    Retorna dict: {norm_key: [(id, nombre, fecha_nacimiento, genero)]}
    donde norm_key es el nombre normalizado en formato de sort.
    """
    cur = db.cursor()
    cur.execute("SELECT id, nombre, fecha_nacimiento, genero FROM person")
    persons = cur.fetchall()

    lookup: dict[str, list[tuple]] = {}
    for pid, nombre, fecha, genero in persons:
        key = extract_bd_sort_key(nombre)
        if key not in lookup:
            lookup[key] = []
        lookup[key].append((pid, nombre, fecha, genero))

    # También indexar por apellido (primer token) para fuzzy más eficiente
    by_apellido: dict[str, list[tuple]] = {}
    for pid, nombre, fecha, genero in persons:
        key = extract_bd_sort_key(nombre)
        first_token = key.split()[0] if key.split() else ""
        if first_token and len(first_token) >= 2:
            if first_token not in by_apellido:
                by_apellido[first_token] = []
            by_apellido[first_token].append((pid, nombre, fecha, genero, key))

    return {"by_full": lookup, "by_apellido": by_apellido}


def get_coverage(db: sqlite3.Connection) -> dict:
    """Retorna coverage actual de fecha_nacimiento y genero."""
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM person")
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM person WHERE fecha_nacimiento IS NOT NULL AND fecha_nacimiento != ''"
    )
    con_fecha = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM person WHERE genero IS NOT NULL")
    con_genero = cur.fetchone()[0]

    return {
        "total": total,
        "fecha_nacimiento": con_fecha,
        "fecha_nacimiento_pct": (con_fecha / total * 100) if total else 0,
        "genero": con_genero,
        "genero_pct": (con_genero / total * 100) if total else 0,
    }


# ── Matching ───────────────────────────────────────────────────────────────


def match_and_update(
    db: sqlite3.Connection,
    wikidata_persons: list[dict],
    bd_persons: dict,
    dry_run: bool = False,
) -> dict:
    """
    Para cada persona Wikidata:
    1. Intentar match exacto normalizado contra BD
    2. Si falla, usar fuzzy matching con threshold >= 0.85
    3. Actualizar solo campos vacíos (idempotente)
    """
    stats = {
        "total_wikidata": len(wikidata_persons),
        "exact_match": 0,
        "fuzzy_match": 0,
        "no_match": 0,
        "fecha_nacimiento_updated": 0,
        "genero_updated": 0,
        "fecha_conflict": 0,
        "genero_conflict": 0,
        "already_complete": 0,
        "no_new_data": 0,
        "fuzzy_details": [],
        "no_match_details": [],
    }

    by_full = bd_persons["by_full"]
    by_apellido = bd_persons["by_apellido"]

    updates_fecha: list[tuple[str, str]] = []  # (fecha, id)
    updates_genero: list[tuple[str, str]] = []  # (genero, id)

    for wd in wikidata_persons:
        wd_norm = wd["nombre_norm"]
        wd_fecha = wd["fecha_nacimiento"]
        wd_genero = wd["genero"]

        # Sin datos nuevos que aportar → skip
        if not wd_fecha and not wd_genero:
            stats["no_new_data"] += 1
            continue

        matched_id = None
        matched_nombre = None
        match_type = None

        # 1. Match exacto normalizado
        if wd_norm in by_full:
            candidates = by_full[wd_norm]
            if len(candidates) == 1:
                matched_id, matched_nombre, _, _ = candidates[0]
                match_type = "exact"
            else:
                # Múltiples candidatos exactos — tomar el primero que necesite datos
                for pid, nombre, fecha, genero in candidates:
                    needs_fecha = wd_fecha and (not fecha)
                    needs_genero = wd_genero and (not genero)
                    if needs_fecha or needs_genero:
                        matched_id = pid
                        matched_nombre = nombre
                        match_type = "exact"
                        break
                if not matched_id:
                    matched_id, matched_nombre, _, _ = candidates[0]
                    match_type = "exact"

        if not matched_id:
            # 2. Fuzzy matching — buscar dentro del grupo del mismo apellido
            wd_first = wd_norm.split()[0] if wd_norm.split() else ""
            candidates = by_apellido.get(wd_first, [])

            best_id = None
            best_nombre = None
            best_score = 0.0

            for pid, nombre, _, _, bd_norm in candidates:
                score = SequenceMatcher(None, wd_norm, bd_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_id = pid
                    best_nombre = nombre

            if best_score >= FUZZY_THRESHOLD and best_id:
                matched_id = best_id
                matched_nombre = best_nombre
                match_type = "fuzzy"
                stats["fuzzy_details"].append(
                    {
                        "wikidata": wd["nombre"],
                        "bd": best_nombre,
                        "score": round(best_score, 3),
                        "fecha": wd_fecha,
                        "genero": wd_genero,
                    }
                )
            else:
                stats["no_match"] += 1
                if wd_fecha or wd_genero:
                    stats["no_match_details"].append(
                        {
                            "wikidata": wd["nombre"],
                            "wd_norm": wd_norm,
                            "fecha": wd_fecha,
                            "genero": wd_genero,
                            "best_score": round(best_score, 3),
                            "best_match": best_nombre,
                        }
                    )
                continue

        # Registrar match
        if match_type == "exact":
            stats["exact_match"] += 1
        else:
            stats["fuzzy_match"] += 1

        # Verificar qué hay que actualizar
        # Obtener datos actuales de la BD
        cur = db.cursor()
        cur.execute(
            "SELECT fecha_nacimiento, genero FROM person WHERE id = ?",
            (matched_id,),
        )
        row = cur.fetchone()
        if not row:
            continue
        bd_fecha, bd_genero = row

        needs_update = False

        # Actualizar fecha_nacimiento (solo si BD tiene NULL o vacío)
        if wd_fecha and (bd_fecha is None or bd_fecha == ""):
            updates_fecha.append((wd_fecha, matched_id))
            stats["fecha_nacimiento_updated"] += 1
            needs_update = True
        elif wd_fecha and bd_fecha and wd_fecha != bd_fecha:
            stats["fecha_conflict"] += 1
            print(f"  ⚠ Conflicto fecha: BD[{matched_nombre}]={bd_fecha} vs WD={wd_fecha}")

        # Actualizar genero (solo si BD tiene NULL)
        if wd_genero and bd_genero is None:
            updates_genero.append((wd_genero, matched_id))
            stats["genero_updated"] += 1
            needs_update = True
        elif wd_genero and bd_genero and wd_genero != bd_genero:
            stats["genero_conflict"] += 1
            print(f"  ⚠ Conflicto género: BD[{matched_nombre}]={bd_genero} vs WD={wd_genero}")

        if not needs_update:
            stats["already_complete"] += 1

    # Aplicar updates
    if not dry_run:
        cur = db.cursor()
        for fecha, pid in updates_fecha:
            cur.execute(
                "UPDATE person SET fecha_nacimiento = ? WHERE id = ? AND (fecha_nacimiento IS NULL OR fecha_nacimiento = '')",
                (fecha, pid),
            )
        for genero, pid in updates_genero:
            cur.execute(
                "UPDATE person SET genero = ? WHERE id = ? AND genero IS NULL",
                (genero, pid),
            )
        db.commit()
        print(f"\n  ✓ {len(updates_fecha)} fechas + {len(updates_genero)} géneros actualizados")
    else:
        print("\n  [DRY RUN] Se actualizarían:")
        print(f"    - {len(updates_fecha)} fechas de nacimiento")
        print(f"    - {len(updates_genero)} géneros")

    return stats


# ── Reporte ────────────────────────────────────────────────────────────────


def print_report(
    coverage_pre: dict,
    coverage_post: dict,
    stats_dip: dict,
    stats_sen: dict,
):
    """Muestra reporte completo."""
    print("\n" + "=" * 70)
    print(" REPORTE FINAL — Backfill Wikidata")
    print("=" * 70)

    # Resumen Wikidata
    total_wd = stats_dip["total_wikidata"] + stats_sen["total_wikidata"]
    total_exact = stats_dip["exact_match"] + stats_sen["exact_match"]
    total_fuzzy = stats_dip["fuzzy_match"] + stats_sen["fuzzy_match"]
    total_no = stats_dip["no_match"] + stats_sen["no_match"]

    print("\n  Wikidata:")
    print(f"    Diputados: {stats_dip['total_wikidata']} resultados")
    print(f"    Senadores: {stats_sen['total_wikidata']} resultados")
    print(f"    Total:     {total_wd} resultados")

    print("\n  Matching:")
    print(f"    Matches exactos: {total_exact}")
    print(f"    Matches fuzzy:   {total_fuzzy}")
    print(f"    Sin match:       {total_no}")

    total_fecha = stats_dip["fecha_nacimiento_updated"] + stats_sen["fecha_nacimiento_updated"]
    total_genero = stats_dip["genero_updated"] + stats_sen["genero_updated"]
    total_conflict_fecha = stats_dip["fecha_conflict"] + stats_sen["fecha_conflict"]
    total_conflict_genero = stats_dip["genero_conflict"] + stats_sen["genero_conflict"]

    print("\n  Actualizaciones:")
    print(f"    fecha_nacimiento insertados: {total_fecha}")
    print(f"    genero insertados:           {total_genero}")
    print(f"    Conflictos fecha:            {total_conflict_fecha}")
    print(f"    Conflictos género:           {total_conflict_genero}")

    print("\n  Coverage:")
    print(
        f"    fecha_nacimiento: {coverage_pre['fecha_nacimiento']}/{coverage_pre['total']} ({coverage_pre['fecha_nacimiento_pct']:.1f}%) → "
        f"{coverage_post['fecha_nacimiento']}/{coverage_post['total']} ({coverage_post['fecha_nacimiento_pct']:.1f}%)"
    )
    print(
        f"    genero:           {coverage_pre['genero']}/{coverage_pre['total']} ({coverage_pre['genero_pct']:.1f}%) → "
        f"{coverage_post['genero']}/{coverage_post['total']} ({coverage_post['genero_pct']:.1f}%)"
    )

    # Fuzzy details
    all_fuzzy = stats_dip["fuzzy_details"] + stats_sen["fuzzy_details"]
    if all_fuzzy:
        print("\n  Matches fuzzy (muestra, máx 20):")
        for fd in all_fuzzy[:20]:
            print(f"    [{fd['score']:.3f}] WD='{fd['wikidata']}' → BD='{fd['bd']}'")

    # No match details
    all_no_match = stats_dip["no_match_details"] + stats_sen["no_match_details"]
    if all_no_match:
        print("\n  Sin match con datos (muestra, máx 30):")
        for nm in all_no_match[:30]:
            print(
                f"    WD='{nm['wikidata']}' (mejor: {nm['best_score']:.3f} → '{nm['best_match']}')"
            )


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    dry_run = "--dry-run" in sys.argv

    print("Backfill Wikidata — Observatorio del Congreso")
    print(f"BD: {DB_PATH}")
    print(f"Dry run: {dry_run}")
    print(f"Q-IDs: Diputados={Q_DIPUTADO}, Senadores={Q_SENADOR}")

    if not DB_PATH.exists():
        print(f"ERROR: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA foreign_keys = ON")

    # Coverage pre
    coverage_pre = get_coverage(db)
    print("\n  Coverage PRE:")
    print(
        f"    fecha_nacimiento: {coverage_pre['fecha_nacimiento']}/{coverage_pre['total']} ({coverage_pre['fecha_nacimiento_pct']:.1f}%)"
    )
    print(
        f"    genero:           {coverage_pre['genero']}/{coverage_pre['total']} ({coverage_pre['genero_pct']:.1f}%)"
    )

    # Cargar personas de la BD
    print("\n  Cargando personas de la BD...")
    bd_persons = load_bd_persons(db)
    total_bd = sum(len(v) for v in bd_persons["by_full"].values())
    print(f"    {total_bd} personas indexadas")

    # ── Diputados ──
    print("\n" + "-" * 50)
    print(" Consultando Diputados en Wikidata...")
    print("-" * 50)
    dip_bindings = fetch_all_results(Q_DIPUTADO, SPARQL_TEMPLATE, "Diputados")
    dip_parsed = parse_wikidata_results(dip_bindings)
    print(f"  Diputados parseados (únicos): {len(dip_parsed)}")
    time.sleep(RATE_LIMIT_SECONDS)

    # ── Senadores ──
    print("\n" + "-" * 50)
    print(" Consultando Senadores en Wikidata...")
    print("-" * 50)
    sen_bindings = fetch_all_results(Q_SENADOR, SPARQL_TEMPLATE, "Senadores")
    sen_parsed = parse_wikidata_results(sen_bindings)
    print(f"  Senadores parseados (únicos): {len(sen_parsed)}")

    # ── Matching y updates ──
    print("\n" + "=" * 50)
    print(" Matcheando Diputados contra BD...")
    print("=" * 50)
    stats_dip = match_and_update(db, dip_parsed, bd_persons, dry_run=dry_run)

    print("\n" + "=" * 50)
    print(" Matcheando Senadores contra BD...")
    print("=" * 50)
    stats_sen = match_and_update(db, sen_parsed, bd_persons, dry_run=dry_run)

    # Coverage post
    coverage_post = get_coverage(db)

    # Reporte final
    print_report(coverage_pre, coverage_post, stats_dip, stats_sen)

    db.close()
    print("\n✓ Listo.")


if __name__ == "__main__":
    main()
