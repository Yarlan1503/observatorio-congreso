#!/usr/bin/env python3
"""
Backfill de género para la tabla person del Observatorio del Congreso.

Fuentes:
  1. CSVs de Nolan (diputados/diputados-x-genero/) → LXV + LXVI
  2. Heurística de primer nombre → LX-LXIV

Uso:
    python db/migrations/backfill_genero.py            # ejecuta todo
    python db/migrations/backfill_genero.py --dry-run  # solo muestra
    python db/migrations/backfill_genero.py --csv-only # solo CSVs de Nolan
    python db/migrations/backfill_genero.py --names-only # solo heurística
"""

import argparse
import csv
import re
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO / "db" / "congreso.db"
CSV_DIR = REPO / "diputados" / "diputados-x-genero"

CSV_MASCULINO = CSV_DIR / "Dip-Masculino-LXV-LXVI.csv"
CSV_FEMENINO = CSV_DIR / "Dip-Femenino-LXV-LXVI.csv"

FUZZY_THRESHOLD = 0.85

# Nombres ambivalentes que no se deben asignar automáticamente
# (pueden ser tanto masculinos como femeninos, o son partículas)
# Incluye nombres de pila que aparecen en compound names de género opuesto:
# "María José" (F), "José María" (M), "María del Carmen" (F), etc.
NOMBRES_AMBIGUOS = {
    "Ángel",
    "Angel",
    "Guadalupe",
    "Rosario",
    "Refugio",
    "Esperanza",
    "Soledad",
    "Concepción",
    "Concepcion",
    "Trinidad",
    "Carmen",
    "Mercedes",
    "Pilar",
    "Dolores",
    "Milagro",
    "Milagros",
    "Cruz",
    "Luz",
    "Sol",
    "Maria",
    "María",
    "Ma.",
    "José",
    "Jose",
    "Jesús",
    "Jesus",
    "Del",
    "De",
    "La",
    "Los",
    "Las",
    "El",  # partículas, no nombres
}

# Diccionario hardcodeado de nombres hispanos con género conocido.
# Fuente: análisis de 1516 personas sin género en BD del Observatorio.
# Cubre nombres que no alcanzan frecuencia suficiente en la BD/CSVs.
NOMBRES_MASCULINOS: set[str] = {
    # Nombres comunes
    "antonio",
    "luis",
    "carlos",
    "javier",
    "enrique",
    "roberto",
    "alejandro",
    "alberto",
    "miguel",
    "manuel",
    "fernando",
    "gerardo",
    "eduardo",
    "arturo",
    "humberto",
    "armando",
    "daniel",
    "ricardo",
    "raúl",
    "raul",
    "sergio",
    "francisco",
    "alfredo",
    "octavio",
    "rodrigo",
    "jaime",
    "israel",
    "abel",
    "joel",
    "genaro",
    "salvador",
    "gilberto",
    "juan",
    "ariel",
    "ernesto",
    "edgardo",
    "rafael",
    "guillermo",
    "mauricio",
    "gonzalo",
    "mario",
    "ivan",
    "iván",
    "adrián",
    "adrian",
    "rolando",
    "tomás",
    "tomas",
    "efraín",
    "efrain",
    "agustín",
    "agustin",
    "césar",
    "cesar",
    "ramón",
    "ramon",
    # Nombres tradicionales
    "wenceslao",
    "bonifacio",
    "sebastián",
    "sebastian",
    "noel",
    "vicente",
    "silvio",
    "tonatiuh",
    "amador",
    "eleazar",
    "irineo",
    "alan",
    "silvano",
    "secundino",
    "alain",
    "nazario",
    "desiderio",
    "domitilo",
    "antolín",
    "simón",
    "simon",
    "rubén",
    "ruben",
    "fausto",
    "gumercindo",
    "telésforo",
    "isaías",
    "isaias",
    "hugo",
    "emilio",
    "emiliano",
    "nabor",
    "salomón",
    "salomon",
    "rené",
    "rene",
    "jorge",
    "andres",
    "andrés",
    "gustavo",
    "christian",
    "cristian",
    "gabriel",
    "martín",
    "martin",
    "emanuel",
    "benito",
    "teodoro",
    "hermilo",
    "felipe",
    "cipriano",
    "gregorio",
    "higinio",
    "modesto",
    "braulio",
    "adán",
    "adan",
    "cirilo",
    "joaquín",
    "joaquin",
    "mateo",
    "pedro",
    "pablo",
    "lázaro",
    "lazaro",
    "ezequiel",
    "gildardo",
    "hector",
    "héctor",
    "horacio",
    "librado",
    "wadi",
    "damián",
    "damian",
    "clemente",
    "virgilio",
    "porfirio",
    "macario",
    "maurilio",
    "jacinto",
    "eliseo",
    "lidio",
    "valentín",
    "valentin",
    "remberto",
    "maximiano",
    "noé",
    "noe",
    "marco",
    "dante",
    "apolonio",
    "benjamín",
    "benjamin",
    "nemesio",
    "cuitlahuac",
    "cuitláhuac",
    "netzahualcóyotl",
    "rutilio",
    "vidal",
    "waldo",
    "lucio",
    "macedonio",
    "leonel",
    "aurelio",
    "esteban",
    "ismael",
    "eugenio",
    "david",
    "ramiro",
    "xavier",
    "herminio",
    "adolfo",
    "ulises",
    "ventura",
    "fidel",
    "silvestre",
    "arnulfo",
    "abraham",
    "rogelio",
    "raymundo",
    "augusto",
    "álvaro",
    "alvaro",
    "santiago",
    "mariano",
    "german",
    "germán",
    "nicolás",
    "bernardino",
    "bernardo",
    "leopoldo",
    "ponciano",
    "leobardo",
    "gastón",
    "valdemar",
    "ovidio",
    "luciano",
    "pavel",
    "everardo",
    "gaudencio",
    "cesario",
    "marcelo",
    "liborio",
    "benigno",
    "camilo",
    "margarito",
    "domingo",
    "robinson",
    "abundio",
    "nicanor",
    "victorino",
    "silvino",
    "oracio",
    "ascención",
    "asención",
    "orlando",
    "adalberto",
    "jonathan",
    "misael",
    "julian",
    "julián",
    "moisés",
    "rodolfo",
    "albino",
    "exequiel",
    "julio",
    "cecilio",
    "napoleón",
    "hernando",
    "nivardo",
    "josafat",
    "eudoxio",
    "edmundo",
    "amílcar",
    "tolentino",
    "melchor",
    "fabio",
    "fluvio",
    "raciel",
    "darinel",
    "emigdio",
    "delio",
    "serafín",
    "pascual",
    "eviel",
    "fortino",
    "onésimo",
    "canek",
    "sabino",
    "victor",
    "víctor",
    "oscar",
    "erick",
    "kamel",
    "theodoros",
    "uwe",
    "husain",
    "celerino",
    "irugami",
    "amarildo",
    "alex",
    "jeshua",
    "jair",
    "aciel",
    "asael",
    "feliciano",
    "amayrani",
    "hirepan",
    "isaac",
    "ciro",
    "marcos",
    "epigmenio",
    "aristides",
    "arístides",
    "eruviel",
    "eder",
    "uriel",
    "litz",
    "gil",
    # Nombres extranjeros/peculiares masculinos
    "marko",
    "christopher",
    "kevin",
    "osvaldo",
    "renato",
    "omar",
    "bruno",
    "harry",
    "harvey",
    # Nombres adicionales v2
    "demetrio",
    "artemio",
    "silbestre",
    "neftalí",
    "neftali",
    "odilón",
    "odilon",
    "arnoldo",
    "margelis",
}

NOMBRES_FEMENINOS: set[str] = {
    # Nombres comunes
    "patricia",
    "leticia",
    "alejandra",
    "elena",
    "laura",
    "teresa",
    "gabriela",
    "carolina",
    "rocío",
    "rocio",
    "adriana",
    "verónica",
    "veronica",
    "silvia",
    "erika",
    "carla",
    "nancy",
    "gina",
    "marisol",
    "yesenia",
    "lidia",
    "clara",
    "jessica",
    "diana",
    "yolanda",
    "elizabeth",
    "cynthia",
    "elsa",
    "julieta",
    "karla",
    "claudia",
    "maricela",
    "miriam",
    "celia",
    "irma",
    "socorro",
    "gloria",
    "sonia",
    "monica",
    "mónica",
    "ana",
    "lilia",
    "isabel",
    "esther",
    "nadia",
    "edith",
    "teresita",
    "ofelia",
    "paola",
    "violeta",
    "sandra",
    "maribel",
    "susana",
    "julia",
    "alma",
    "martha",
    "lucía",
    "lucia",
    "elisa",
    "natalia",
    "wendy",
    "estefanía",
    "estefania",
    "vanessa",
    "dulce",
    "mirna",
    "janeth",
    "herminia",
    "catalina",
    "beatriz",
    "paloma",
    "nora",
    "mireya",
    "delfina",
    "iveth",
    "irene",
    "virginia",
    "paulina",
    "marisela",
    "natividad",
    "celeste",
    "eugenia",
    "reyna",
    # Nombres tradicionales
    "miroslava",
    "soraya",
    "fernanda",
    "cristina",
    "magdalena",
    "angélica",
    "mariana",
    "leonor",
    "andrea",
    "berenice",
    "alicia",
    "araceli",
    "maricruz",
    "montserrat",
    "monserrat",
    "abigail",
    "amalia",
    "selene",
    "perla",
    "idalia",
    "florentina",
    "tatiana",
    "anita",
    "salma",
    "nohemí",
    "nohemi",
    "zulma",
    "hildelisa",
    "roxana",
    "fátima",
    "fatima",
    "damaris",
    "rufina",
    "consuelo",
    "anay",
    "graciela",
    "juana",
    "lorena",
    "rosalba",
    "esmeralda",
    "lizeth",
    "karina",
    "azucena",
    "guillermina",
    "josefina",
    "ester",
    "elvia",
    "lourdes",
    "aracely",
    "luisa",
    "marcela",
    "georgina",
    "anabel",
    "aurora",
    "joaquina",
    "agustina",
    "nayeli",
    "valeria",
    "roselia",
    "ivonne",
    "mariela",
    "marlen",
    "fabiola",
    "celina",
    "gisell",
    "arcelia",
    "bertha",
    "carina",
    "felicita",
    "marilú",
    "belinda",
    "yadira",
    "gricelda",
    "liliana",
    "tania",
    "mayra",
    "estela",
    "coyolxauhqui",
    "haydee",
    "zobeida",
    "zoraida",
    "rebeca",
    "sayuri",
    "yolis",
    "sofía",
    "sofia",
    "yareli",
    "arely",
    "honoria",
    "giovanna",
    "zoraya",
    "sarabel",
    "brissa",
    "emma",
    "fidelia",
    "sayonara",
    "sara",
    "caritina",
    "rosalinda",
    "yesica",
    "mercedes",
    "madeleine",
    "anilú",
    "micaela",
    "genoveva",
    "exaltación",
    "amparo",
    "regina",
    "jorgina",
    "adela",
    "rafaela",
    "fabiana",
    "elodia",
    "áurea",
    "lucrecia",
    "cleotilde",
    "ainara",
    "citlalli",
    "angelina",
    "maura",
    "brisa",
    "rosa",
    "olimpia",
    "nuvia",
    "layda",
    "melba",
    "febe",
    "gretel",
    "dania",
    "zaria",
    "anais",
    "zayra",
    "anayeli",
    "nayely",
    "nallely",
    "marbella",
    "soralla",
    "gissel",
    "jacquelina",
    "iris",
    "tanya",
    "prisilla",
    "deliamaria",
    "marivel",
    "jannet",
    "iliana",
    "celenia",
    "libier",
    "irasema",
    "zulema",
    "nayeri",
    "nabetse",
    "natalí",
    "janicie",
    "estrella",
    "olivia",
    "tamara",
    "anahí",
    "jocabeth",
    "cecilia",
    "evangelina",
    "yeidckol",
    "brenda",
    "griselda",
    "elva",
    "gerardina",
    "anabey",
    "licet",
    "marcia",
    "yazmín",
    "shamir",
    "erandi",
    "reynel",
    "aleli",
    "lynn",
    "alexis",
    "santy",
    "eunice",
    "yamile",
    "yordana",
    "betzabé",
    "yessica",
    "angeles",
    "mishel",
    "michell",
    "amancay",
    "irais",
    "yunueen",
    "magaly",
    "haidyd",
    "leide",
    "venustiano",
    "yaiti",
    "melva",
    "viridiana",
    "carmelo",
    "cintia",
    "lizbeth",
    "linette",
    "briceyda",
    "vianey",
    "lucero",
    "manuela",
    "jacobo",
    "tonantzin",
    "saray",
    "aremy",
    "yaneli",
    "marybel",
    "abril",
    "lucresia",
    "rocelia",
    "nivardo",
    "janneth",
    "rosember",
    "litz",
    "aciel",
    "anabella",
    "itania",
    # Nombres extranjeros/peculiares femeninos
    "holly",
    "omeheira",
    "crystal",
    "cindy",
    "sarahi",
    "yareth",
    "yarith",
    "monserrath",
    "lillian",
    "wendolin",
    "dennisse",
    "mara",
    "irere",
    "lluvia",
    "yatziri",
    "alvany",
    # Nombres adicionales v2
    "judit",
    "zoé",
    "zoe",
    "mely",
    "ninfa",
    "paula",
    "diva",
    "hadamira",
    "lariza",
    "bibiana",
    "rosalina",
    "sasil",
    "margelis",
    "yeimi",
    "verenice",
    "yadhira",
}


# ── Normalización ──────────────────────────────────────────────────────────


def normalize_name(name: str) -> str:
    """Normaliza un nombre para comparación: quita prefijos, sufijos, comas."""
    n = name.strip()
    # Quitar prefijos comunes
    n = re.sub(
        r"^(Dip\.\s*|Sen\.\s*|Senadora\s+|Diputada\s+|Diputado\s+)", "", n, flags=re.IGNORECASE
    )
    # Quitar sufijos como (LICENCIA), (DECESO)
    n = re.sub(r"\s*\(LICENCIA\)\s*", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s*\(DECESO\)\s*", "", n, flags=re.IGNORECASE)
    # Quitar comas y puntos
    n = n.replace(",", " ").replace(".", " ")
    # Normalizar espacios
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _extract_primary_name_no_comma(nombre: str) -> str | None:
    """
    Extrae el primer nombre de pila de un nombre sin coma, intentando
    posición 2 (después de 2 apellidos) con skip de partículas.
    Fallback para cuando extract_first_name (último token) no encuentra match.
    """
    n = nombre.strip()
    n = re.sub(
        r"^(Dip\.\s*|Sen\.\s*|Senadora\s+|Diputada\s+|Diputado\s+)", "", n, flags=re.IGNORECASE
    )
    n = re.sub(r"\s*\(LICENCIA\)\s*", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s*\(DECESO\)\s*", "", n, flags=re.IGNORECASE)
    if "," in n:
        return None  # No aplica para nombres con coma

    tokens = n.split()
    if not tokens:
        return None

    # Skip partículas al inicio (De, Del, La...)
    particles = {"de", "del", "la", "las", "los", "el", "van", "von", "di", "da"}
    skip = 0
    for t in tokens:
        if t.lower() in particles:
            skip += 1
        else:
            break

    # Posición del primer nombre de pila: skip + 2 (apellido1 + apellido2)
    pos = skip + 2
    if pos < len(tokens):
        name = tokens[pos].strip(".,")
        if name.lower() not in particles:
            return name
    return None


def extract_first_name(nombre: str) -> str | None:
    """
    Extrae el primer nombre de pila de un nombre en formato BD.

    Formato BD con coma:  "Apellido1 Apellido2, Nombre1 Nombre2"
      → primer token después de la coma.

    Formato BD sin coma:  "Apellido1 Apellido2 Nombre1 Nombre2"
      → saltar partículas (De, Del, La...) al inicio, luego 2 apellidos,
      tomar el siguiente token como nombre de pila.

    Si no hay suficientes tokens, usa el último como fallback.
    """
    n = nombre.strip()
    # Quitar prefijos
    n = re.sub(
        r"^(Dip\.\s*|Sen\.\s*|Senadora\s+|Diputada\s+|Diputado\s+)", "", n, flags=re.IGNORECASE
    )
    n = re.sub(r"\s*\(LICENCIA\)\s*", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s*\(DECESO\)\s*", "", n, flags=re.IGNORECASE)

    if "," in n:
        # Formato "Apellidos, Nombres"
        after_comma = n.split(",", 1)[1].strip()
        first_token = after_comma.split()[0] if after_comma.split() else None
    else:
        # Sin coma — formato "Apellido1 [Apellido2] Nombre1 [Nombre2]"
        # El ÚLTIMO token es casi siempre un nombre de pila en formato mexicano.
        # Esto maneja correctamente apellidos compuestos (De la, Del, Díaz de León, etc.)
        # Ej: "Del Toro del Villar Tomás" → "Tomás" ✓
        #     "Díaz de León Torres Leticia" → "Leticia" ✓
        tokens = n.split()
        if not tokens:
            return None

        first_token = tokens[-1]

    # Limpiar
    if first_token:
        first_token = first_token.strip(".,")
        # Si es una partícula, no es un nombre de pila útil
        if first_token.lower() in (
            "de",
            "del",
            "de la",
            "el",
            "la",
            "los",
            "las",
            "van",
            "von",
            "di",
            "da",
            "mac",
            "mc",
            "o'",
        ):
            return None

    return first_token


# ── CSV Loading ────────────────────────────────────────────────────────────


def load_csv_names(csv_path: Path) -> list[dict]:
    """
    Lee un CSV de género. Formato: #,Diputadas,Entidad,Distrito / Circunscripción
    Retorna lista de dicts con 'nombre', 'entidad', 'legislatura'.
    """
    records = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 4:
                continue
            _num, nombre, entidad, legislatura = row[0], row[1], row[2], row[3]
            # Limpiar (LICENCIA) del nombre
            nombre = re.sub(r"\s*\(LICENCIA\)\s*", "", nombre).strip()
            if nombre:
                records.append(
                    {
                        "nombre": nombre,
                        "nombre_norm": normalize_name(nombre),
                        "entidad": entidad.strip(),
                        "legislatura": legislatura.strip(),
                    }
                )
    return records


# ── Fase 1: CSV Matching ──────────────────────────────────────────────────


def fase1_csv(db: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    Lee CSVs de Nolan, matchea contra BD, actualiza género.
    Retorna stats.
    """
    print("\n" + "=" * 60)
    print("FASE 1: Matching desde CSVs de Nolan (LXV + LXVI)")
    print("=" * 60)

    # Cargar personas de la BD sin género (o todas, para verificar)
    cursor = db.cursor()
    cursor.execute("SELECT id, nombre, genero FROM person")
    bd_persons = cursor.fetchall()

    # Build lookups:
    #   bd_by_norm: nombre_norm -> [(id, nombre, genero)]
    #   bd_by_apellido: primer_token_norm -> [(id, nombre, genero, nombre_norm)]
    bd_by_norm: dict[str, list[tuple]] = {}
    bd_by_apellido: dict[str, list[tuple]] = {}
    for pid, nombre, genero in bd_persons:
        norm = normalize_name(nombre)
        if norm not in bd_by_norm:
            bd_by_norm[norm] = []
        bd_by_norm[norm].append((pid, nombre, genero))
        # Indexar por primer token (apellido paterno)
        first_token = norm.split()[0].lower() if norm.split() else ""
        if first_token and len(first_token) >= 2:
            if first_token not in bd_by_apellido:
                bd_by_apellido[first_token] = []
            bd_by_apellido[first_token].append((pid, nombre, genero, norm))

    # Cargar CSVs
    masc_records = load_csv_names(CSV_MASCULINO)
    fem_records = load_csv_names(CSV_FEMENINO)

    print(f"  CSVs cargados: {len(masc_records)} masculinos, {len(fem_records)} femeninos")

    all_records = [(r, "M") for r in masc_records] + [(r, "F") for r in fem_records]

    stats = {
        "csv_total": len(all_records),
        "exact_match": 0,
        "norm_match": 0,
        "fuzzy_match": 0,
        "no_match": [],
        "already_has_gender": 0,
        "gender_conflict": 0,
        "updated": 0,
    }

    updates: list[tuple[str, str]] = []  # (id, genero)

    for record, genero_csv in all_records:
        csv_norm = record["nombre_norm"]
        matched = False

        # 1. Match exacto normalizado
        if csv_norm in bd_by_norm:
            candidates = bd_by_norm[csv_norm]
            if len(candidates) == 1:
                pid, bd_nombre, bd_genero = candidates[0]
                if bd_genero is not None:
                    if bd_genero != genero_csv:
                        stats["gender_conflict"] += 1
                        print(f"  ⚠ CONFLICTO: {bd_nombre} (BD={bd_genero}) vs CSV={genero_csv}")
                    else:
                        stats["already_has_gender"] += 1
                    matched = True
                    stats["exact_match"] += 1
                else:
                    updates.append((pid, genero_csv))
                    stats["exact_match"] += 1
                    stats["updated"] += 1
                    matched = True
            else:
                # Múltiples candidatos — todos son match exacto, tomar primero sin género
                for pid, _bd_nombre, bd_genero in candidates:
                    if bd_genero is None:
                        updates.append((pid, genero_csv))
                        stats["updated"] += 1
                        break
                    elif bd_genero == genero_csv:
                        stats["already_has_gender"] += 1
                        break
                else:
                    # Todos tenían género conflictivo
                    if any(g != genero_csv for _, _, g in candidates):
                        stats["gender_conflict"] += 1
                matched = True
                stats["exact_match"] += 1

        if matched:
            continue

        # 2. Fuzzy matching — SOLO dentro del grupo del mismo apellido (primer token)
        csv_first = csv_norm.split()[0].lower() if csv_norm.split() else ""
        fuzzy_candidates = bd_by_apellido.get(csv_first, [])

        best_pid = None
        best_nombre = None
        best_genero = None
        best_score = 0.0

        for pid, bd_nombre, bd_genero, bd_norm in fuzzy_candidates:
            score = SequenceMatcher(None, csv_norm, bd_norm).ratio()
            if score > best_score:
                best_score = score
                best_pid = pid
                best_nombre = bd_nombre
                best_genero = bd_genero

        if best_score >= FUZZY_THRESHOLD and best_pid:
            if best_genero is not None:
                if best_genero != genero_csv:
                    stats["gender_conflict"] += 1
                    print(
                        f"  ⚠ CONFLICTO (fuzzy {best_score:.2f}): {best_nombre} (BD={best_genero}) vs CSV={genero_csv}"
                    )
                else:
                    stats["already_has_gender"] += 1
                stats["fuzzy_match"] += 1
            else:
                updates.append((best_pid, genero_csv))
                stats["fuzzy_match"] += 1
                stats["updated"] += 1
                print(
                    f"  ✓ Fuzzy ({best_score:.2f}): CSV='{record['nombre']}' → BD='{best_nombre}' [{genero_csv}]"
                )
        else:
            stats["no_match"].append(
                {
                    "csv_nombre": record["nombre"],
                    "csv_norm": csv_norm,
                    "genero": genero_csv,
                    "legislatura": record["legislatura"],
                    "best_score": best_score,
                    "best_match": best_nombre,
                }
            )

    # Aplicar updates
    if not dry_run and updates:
        cursor = db.cursor()
        for pid, genero in updates:
            cursor.execute("UPDATE person SET genero = ? WHERE id = ?", (genero, pid))
        db.commit()
        print(f"\n  ✓ {len(updates)} registros actualizados en BD")

    # Reporte
    print("\n  --- Reporte Fase 1 ---")
    print(f"  Total CSV:           {stats['csv_total']}")
    print(f"  Match exacto:        {stats['exact_match']}")
    print(f"  Match fuzzy:         {stats['fuzzy_match']}")
    print(f"  Ya tenían género:    {stats['already_has_gender']}")
    print(f"  Conflictos género:   {stats['gender_conflict']}")
    print(f"  Actualizados:        {stats['updated']}")
    print(f"  Sin match:           {len(stats['no_match'])}")

    if stats["no_match"]:
        print("\n  --- Sin match (revisar manualmente) ---")
        for nm in stats["no_match"]:
            print(
                f"    [{nm['genero']}] '{nm['csv_nombre']}' (mejor: {nm['best_score']:.2f} → '{nm['best_match']}') [{nm['legislatura']}]"
            )

    return stats


# ── Fase 2: Heurística de Nombres ─────────────────────────────────────────


def build_name_gender_dict(
    db: sqlite3.Connection, masc_records: list, fem_records: list
) -> dict[str, str]:
    """
    Construye diccionario nombre → género a partir de:
    1. Personas con género conocido en la BD
    2. CSVs de Nolan
    Retorna dict: nombre_en_minúsculas → 'M' o 'F'
    """
    name_dict: dict[str, list[str]] = {}  # name -> [generos observados]

    # 1. Desde la BD
    cursor = db.cursor()
    cursor.execute("SELECT nombre, genero FROM person WHERE genero IS NOT NULL")
    for nombre, genero in cursor.fetchall():
        first = extract_first_name(nombre)
        if first and first not in NOMBRES_AMBIGUOS:
            key = first.lower()
            if key not in name_dict:
                name_dict[key] = []
            name_dict[key].append(genero)

    # 2. Desde CSVs — extraer TODOS los tokens que son nombres de pila
    # CSV format: "Apellido1 Apellido2 Nombre1 Nombre2"
    # Añadimos tanto el primer nombre de pila (tokens[2]) como el último token
    # para maximizar cobertura del diccionario.
    for record, genero_csv in [
        *[(r, "M") for r in masc_records],
        *[(r, "F") for r in fem_records],
    ]:
        nombre = record["nombre"]
        tokens = nombre.strip().split()
        if len(tokens) < 3:
            continue

        # Estrategia: tomar tokens desde posición 2 hasta el final como nombres de pila
        # (posición 0-1 = apellidos para formato estándar mexicano)
        # Para apellidos compuestos al inicio (De la, Del), saltar las partículas
        particles = {"de", "del", "la", "las", "los", "el", "van", "von", "di", "da"}
        skip = 0
        i = 0
        while i < len(tokens):
            if tokens[i].lower() in particles:
                skip += 1
                i += 1
            else:
                break

        # Después de partículas, asumimos 2 apellidos → nombres empiezan en skip+2
        name_start = skip + 2
        if name_start >= len(tokens):
            # Fallback: usar último token
            name_start = len(tokens) - 1

        # Agregar cada token de nombre de pila al diccionario
        for j in range(name_start, len(tokens)):
            token = tokens[j].strip(".,")
            if token and token not in NOMBRES_AMBIGUOS and token.lower() not in particles:
                key = token.lower()
                if key not in name_dict:
                    name_dict[key] = []
                name_dict[key].append(genero_csv)

    # Resolver: solo nombres unívocos
    # Reglas:
    #   - Nombres con ratio M/F entre 0.3 y 0.7 → no asignar
    #   - Nombres que aparecen tanto como M como F → solo si ratio claro
    #   - Threshold de frecuencia bajado a 1 (nombres raros pero unívocos se asignan)
    gender_map: dict[str, str] = {}
    ambiguous: list[str] = []
    too_rare: int = 0

    for name, genders in name_dict.items():
        m_count = genders.count("M")
        genders.count("F")
        total = len(genders)
        ratio_m = m_count / total if total > 0 else 0

        if total < 1:
            # Imposible pero por seguridad
            too_rare += 1
            continue

        if 0.3 <= ratio_m <= 0.7:
            # Ambiguo — aparece en ambos géneros con frecuencia similar
            ambiguous.append(name)
        elif ratio_m > 0.7:
            gender_map[name] = "M"
        else:
            gender_map[name] = "F"

    # Incorporar diccionario hardcodeado (no sobreescribe datos de BD/CSV)
    for name in NOMBRES_MASCULINOS:
        if name not in gender_map:
            gender_map[name] = "M"
    for name in NOMBRES_FEMENINOS:
        if name not in gender_map:
            gender_map[name] = "F"

    if ambiguous:
        print(
            f"  Nombres ambiguos excluidos ({len(ambiguous)}): {', '.join(sorted(ambiguous)[:20])}{'...' if len(ambiguous) > 20 else ''}"
        )
    if too_rare:
        print(f"  Nombres con <3 ocurrencias excluidos: {too_rare}")

    return gender_map


def fase2_heuristica(db: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    Aplica heurística de primer nombre a personas sin género (LX-LXIV).
    """
    print("\n" + "=" * 60)
    print("FASE 2: Heurística de Primer Nombre (LX-LXIV)")
    print("=" * 60)

    # Cargar CSVs para enriquecer diccionario
    masc_records = load_csv_names(CSV_MASCULINO)
    fem_records = load_csv_names(CSV_FEMENINO)

    gender_map = build_name_gender_dict(db, masc_records, fem_records)
    print(f"  Diccionario de nombres: {len(gender_map)} nombres → género")

    # Obtener personas sin género
    cursor = db.cursor()
    cursor.execute("SELECT id, nombre FROM person WHERE genero IS NULL")
    sin_genero = cursor.fetchall()
    print(f"  Personas sin género: {len(sin_genero)}")

    stats = {
        "total_sin_genero": len(sin_genero),
        "assigned": 0,
        "ambiguous_name": 0,
        "not_in_dict": 0,
        "updates": [],
    }

    updates: list[tuple[str, str]] = []  # (id, genero)
    not_found: list[dict] = []

    for pid, nombre in sin_genero:
        first = extract_first_name(nombre)
        if not first:
            stats["ambiguous_name"] += 1
            not_found.append(
                {"id": pid, "nombre": nombre, "razon": "no se pudo extraer primer nombre"}
            )
            continue

        # Verificar si es ambiguo conocido
        if first in NOMBRES_AMBIGUOS:
            # Fallback: intentar nombre primario (posición 2) si no es ambiguo
            primary = _extract_primary_name_no_comma(nombre)
            if primary and primary not in NOMBRES_AMBIGUOS:
                pkey = primary.lower()
                if pkey in gender_map:
                    updates.append((pid, gender_map[pkey]))
                    stats["assigned"] += 1
                    stats["updates"].append((pid, nombre, gender_map[pkey]))
                    continue
            stats["ambiguous_name"] += 1
            not_found.append({"id": pid, "nombre": nombre, "razon": f"nombre ambiguo: {first}"})
            continue

        key = first.lower()
        if key in gender_map:
            genero = gender_map[key]
            updates.append((pid, genero))
            stats["assigned"] += 1
            stats["updates"].append((pid, nombre, genero))
        else:
            # Fallback: intentar nombre primario (posición 2)
            primary = _extract_primary_name_no_comma(nombre)
            if primary and primary not in NOMBRES_AMBIGUOS:
                pkey = primary.lower()
                if pkey in gender_map:
                    updates.append((pid, gender_map[pkey]))
                    stats["assigned"] += 1
                    stats["updates"].append((pid, nombre, gender_map[pkey]))
                    continue
            stats["not_in_dict"] += 1
            not_found.append(
                {"id": pid, "nombre": nombre, "razon": f"{first} no está en diccionario"}
            )

    # Aplicar updates
    if not dry_run and updates:
        cursor = db.cursor()
        for pid, genero in updates:
            cursor.execute("UPDATE person SET genero = ? WHERE id = ?", (genero, pid))
        db.commit()
        print(f"\n  ✓ {len(updates)} registros actualizados en BD")

    # Reporte
    print("\n  --- Reporte Fase 2 ---")
    print(f"  Total sin género:     {stats['total_sin_genero']}")
    print(f"  Asignados:            {stats['assigned']}")
    print(f"  Nombres ambiguos:     {stats['ambiguous_name']}")
    print(f"  No en diccionario:    {stats['not_in_dict']}")

    # Mostrar muestra de no encontrados
    if not_found:
        print("\n  --- Muestra de no asignados (primeros 30) ---")
        for nf in not_found[:30]:
            print(f"    [{nf['id']}] {nf['nombre']} — {nf['razon']}")

    return stats


# ── Reporte Final ─────────────────────────────────────────────────────────


def reporte_final(db: sqlite3.Connection):
    """Muestra el estado final de la BD."""
    print("\n" + "=" * 60)
    print("REPORTE FINAL")
    print("=" * 60)

    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM person")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM person WHERE genero IS NOT NULL")
    con_genero = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM person WHERE genero IS NULL")
    sin_genero = cursor.fetchone()[0]

    cursor.execute(
        "SELECT genero, COUNT(*) FROM person WHERE genero IS NOT NULL GROUP BY genero ORDER BY genero"
    )
    dist = cursor.fetchall()

    pct = (con_genero / total * 100) if total > 0 else 0

    print(f"  Total personas:      {total}")
    print(f"  Con género:          {con_genero} ({pct:.1f}%)")
    print(f"  Sin género:          {sin_genero} ({100 - pct:.1f}%)")
    print("  Distribución:")
    for g, c in dist:
        print(f"    {g}: {c}")


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Backfill de género en tabla person")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no actualizar BD")
    parser.add_argument("--csv-only", action="store_true", help="Solo ejecutar Fase 1 (CSVs)")
    parser.add_argument(
        "--names-only", action="store_true", help="Solo ejecutar Fase 2 (heurística)"
    )
    args = parser.parse_args()

    print("Backfill de Género — Observatorio del Congreso")
    print(f"BD: {DB_PATH}")
    print(f"Dry run: {args.dry_run}")

    if not DB_PATH.exists():
        print(f"ERROR: BD no encontrada en {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH))

    # Estado inicial
    print("\n--- Estado Inicial ---")
    reporte_final(db)

    # Ejecutar fases
    if not args.names_only:
        fase1_csv(db, dry_run=args.dry_run)

    if not args.csv_only:
        fase2_heuristica(db, dry_run=args.dry_run)

    # Estado final
    print("\n--- Estado Final ---")
    reporte_final(db)

    db.close()
    print("\n✓ Listo.")


if __name__ == "__main__":
    main()
