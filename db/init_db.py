#!/usr/bin/env python3
"""
init_db.py — Crear y poblar la base de datos del Observatorio del Congreso.

- Crea congreso.db aplicando schema.sql
- Pobla datos estáticos: organizations, areas, actores externos
- Idempotente: si la BD ya existe, la borra y recrea desde cero
- Sin dependencias externas (solo sqlite3 de stdlib)
"""

import os
import sqlite3
import sys

# Ruta base del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def create_database():
    """Crear la base de datos aplicando el schema SQL."""
    # Idempotente: borrar BD existente si existe
    if os.path.exists(DB_PATH):
        print(f"[init] Eliminando base de datos existente: {DB_PATH}")
        os.remove(DB_PATH)

    print(f"[init] Creando base de datos: {DB_PATH}")

    # Leer el schema SQL
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema_sql = f.read()

    # Conectar y ejecutar schema
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema_sql)

    # Asegurar WAL mode y busy_timeout (ya incluidos en schema.sql,
    # pero executescript no siempre aplica PRAGMAs correctamente)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    # Verificar que foreign_keys estén habilitadas
    cur = conn.execute("PRAGMA foreign_keys;")
    fk_status = cur.fetchone()[0]
    print(f"[init] Foreign keys: {'ON' if fk_status else 'OFF'}")

    return conn


def populate_organizations(conn):
    """Poblar la tabla organization con instituciones y coaliciones.

    Los partidos políticos NO se siembran aquí — los loaders los crean
    dinámicamente al momento del scraping via get_or_create_organization().
    """
    organizations = [
        # Instituciones (estáticas)
        ("O08", "Cámara de Diputados", "Diputados", "institucion", None, None),
        ("O09", "Senado de la República", "Senado", "institucion", None, None),
        # Coaliciones (seed data, se actualiza manualmente si cambia)
        (
            "O10",
            "Sigamos Haciendo Historia",
            "Sigamos Haciendo Historia",
            "coalicion",
            "2024-01-01",
            None,
        ),
    ]

    conn.executemany(
        "INSERT INTO organization (id, nombre, abbr, clasificacion, fundacion, disolucion) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        organizations,
    )
    print(f"[init] Insertadas {len(organizations)} organizaciones (instituciones + coaliciones)")


def populate_areas(conn):
    """Poblar la tabla area con las 32 entidades federativas de México.

    Orden alfabético con IDs secuenciales A01-A32.
    """
    estados = [
        "Aguascalientes",
        "Baja California",
        "Baja California Sur",
        "Campeche",
        "Chiapas",
        "Chihuahua",
        "Coahuila",
        "Colima",
        "Ciudad de México",
        "Durango",
        "Estado de México",
        "Guanajuato",
        "Guerrero",
        "Hidalgo",
        "Jalisco",
        "Michoacán",
        "Morelos",
        "Nayarit",
        "Nuevo León",
        "Oaxaca",
        "Puebla",
        "Querétaro",
        "Quintana Roo",
        "San Luis Potosí",
        "Sinaloa",
        "Sonora",
        "Tabasco",
        "Tamaulipas",
        "Tlaxcala",
        "Veracruz",
        "Yucatán",
        "Zacatecas",
    ]

    areas = []
    for i, nombre in enumerate(estados, start=1):
        area_id = f"A{i:02d}"
        areas.append((area_id, nombre, "estado", None, None))

    conn.executemany(
        "INSERT INTO area (id, nombre, clasificacion, parent_id, geometry) VALUES (?, ?, ?, ?, ?)",
        areas,
    )
    print(f"[init] Insertadas {len(areas)} áreas (estados)")


def populate_actores_externos(conn):
    """Poblar la tabla actor_externo con actores relevantes del caso cero."""
    actores = [
        (
            "AE01",
            "Andrés Manuel López Obrador",
            "ex_presidente",
            None,
            None,
            None,
            "Influencia moral directa sobre coalición 4T",
        ),
        (
            "AE02",
            "Américo Villarreal",
            "gobernador",
            "A28",
            "2022-10-01",
            None,
            "Eje territorial principal; 3 diputados PVEM bajo su influencia",
        ),
        (
            "AE03",
            "Evelyn Salgado",
            "gobernador",
            "A13",
            "2021-10-27",
            None,
            "Gobernadora de Guerrero",
        ),
        (
            "AE04",
            "Clara Brugada",
            "alcalde",
            "A09",
            "2024-10-05",
            None,
            "Jefa de Gobierno de la CDMX",
        ),
        (
            "AE05",
            "Cruz Pérez Cuéllar",
            "alcalde",
            "A06",
            "2024-10-01",
            None,
            "Alcalde de Ciudad Juárez",
        ),
        (
            "AE06",
            "Claudia Pavlovich",
            "ex_presidente",
            "A26",
            None,
            None,
            "Ex gobernadora de Sonora, aliada 4T",
        ),
        (
            "AE07",
            "Ricardo Monreal",
            "otro",
            None,
            None,
            None,
            "Coordinador GPP Morena en Diputados",
        ),
        (
            "AE08",
            "Ignacio Mier",
            "otro",
            None,
            None,
            None,
            "Coordinador GPP Morena en Senado",
        ),
        (
            "AE09",
            "Laura Itzel Castillo",
            "otro",
            None,
            None,
            None,
            "Presidenta del Senado",
        ),
        (
            "AE10",
            "Rosa Icela Rodríguez",
            "otro",
            None,
            None,
            None,
            "Secretaria de Gobernación",
        ),
        (
            "AE11",
            "Arturo Zaldívar",
            "otro",
            None,
            None,
            None,
            "Coordinador de Política y Gobierno de la Presidencia",
        ),
        (
            "AE12",
            "Alberto Anaya",
            "dirigente",
            None,
            None,
            None,
            "Dirigente nacional del PT",
        ),
        (
            "AE13",
            "Karen Castrejón",
            "dirigente",
            None,
            None,
            None,
            "Presidenta nacional del PVEM",
        ),
        (
            "AE14",
            "Luisa María Alcalde",
            "dirigente",
            None,
            None,
            None,
            "Presidenta nacional de Morena",
        ),
        (
            "AE15",
            "Manuel Añorve",
            "otro",
            None,
            None,
            None,
            "Coordinador del PRI en el Senado",
        ),
        (
            "AE16",
            "Kenia López Rabadán",
            "otro",
            None,
            None,
            None,
            "Presidenta Mesa Directiva Diputados (PAN)",
        ),
    ]

    conn.executemany(
        "INSERT INTO actor_externo "
        "(id, nombre, tipo, area_id, start_date, end_date, observaciones) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        actores,
    )
    print(f"[init] Insertados {len(actores)} actores externos")


def verify_data(conn):
    """Verificar que los datos se insertaron correctamente."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM organization")
    org_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM area")
    area_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM actor_externo")
    actor_count = cur.fetchone()[0]

    print(f"[verify] Organizations: {org_count}")
    print(f"[verify] Areas: {area_count}")
    print(f"[verify] Actores externos: {actor_count}")

    # Verificar UTF-8 con un nombre con acento (Michoacán = A16)
    cur.execute("SELECT nombre FROM area WHERE id = 'A16'")
    utf8_test = cur.fetchone()[0]
    print(f"[verify] UTF-8 test: '{utf8_test}'")

    return org_count, area_count, actor_count


def main():
    """Función principal: crear BD, poblar datos, verificar."""
    print("=" * 60)
    print("Observatorio del Congreso — Inicialización de BD")
    print("=" * 60)

    # Paso 1: Crear base de datos con schema
    conn = create_database()

    # Paso 2: Poblar datos estáticos
    print("\n--- Poblando datos estáticos ---")
    populate_organizations(conn)
    populate_areas(conn)
    populate_actores_externos(conn)

    # Paso 3: Commit
    conn.commit()

    # Paso 4: Verificar
    print("\n--- Verificación ---")
    org_count, area_count, actor_count = verify_data(conn)

    # Cerrar conexión
    conn.close()

    # Resumen final
    print("\n" + "=" * 60)
    print(f"Base de datos creada exitosamente: {DB_PATH}")
    print(f"  Organizations: {org_count}")
    print(f"  Areas: {area_count}")
    print(f"  Actores externos: {actor_count}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
