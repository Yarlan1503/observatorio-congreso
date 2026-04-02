#!/usr/bin/env python3
"""
init_senado_db.py — Crear y poblar la base de datos del Senado.

- Crea senado.db aplicando senado_schema.sql
- Pobla datos estáticos: organizaciones (partidos de la LXVI)
- Idempotente: si la BD ya existe, la borra y recrea desde cero
- Sin dependencias externas (solo sqlite3 de stdlib)
"""

import os
import sqlite3
import sys

# Ruta base del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "senado.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "senado_schema.sql")


def create_database():
    """Crear la base de datos aplicando el schema SQL."""
    # Idempotente: borrar BD existente si existe
    if os.path.exists(DB_PATH):
        print(f"[init] Eliminando base de datos existente: {DB_PATH}")
        os.remove(DB_PATH)

    print(f"[init] Creando base de datos: {DB_PATH}")

    # Leer el schema SQL
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Conectar y ejecutar schema
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema_sql)

    # Verificar que foreign_keys estén habilitadas
    cur = conn.execute("PRAGMA foreign_keys;")
    fk_status = cur.fetchone()[0]
    print(f"[init] Foreign keys: {'ON' if fk_status else 'OFF'}")

    return conn


def populate_organizations(conn):
    """Poblar la tabla senado_organizacion con los partidos de la LXVI Legislatura.

    Incluye los 7 grupos: MORENA, PAN, PRI, PVEM, PT, MC y
    Sin Grupo Parlamentario (SG).
    """
    organizations = [
        ("Morena", "partido", "MORENA"),
        ("Partido Acción Nacional", "partido", "PAN"),
        ("Partido Revolucionario Institucional", "partido", "PRI"),
        ("Partido Verde Ecologista de México", "partido", "PVEM"),
        ("Partido del Trabajo", "partido", "PT"),
        ("Movimiento Ciudadano", "partido", "MC"),
        ("Sin Grupo Parlamentario", "otro", "SG"),
    ]

    conn.executemany(
        "INSERT INTO senado_organizacion (nombre, clasificacion, abreviatura) "
        "VALUES (?, ?, ?)",
        organizations,
    )
    print(f"[init] Insertadas {len(organizations)} organizaciones")


def verify_data(conn):
    """Verificar que los datos se insertaron correctamente."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM senado_organizacion")
    org_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM senado_persona")
    persona_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM senado_votacion")
    votacion_count = cur.fetchone()[0]

    print(f"[verify] Organizaciones: {org_count}")
    print(f"[verify] Personas: {persona_count}")
    print(f"[verify] Votaciones: {votacion_count}")

    return org_count, persona_count, votacion_count


def main():
    """Función principal: crear BD, poblar datos, verificar."""
    print("=" * 60)
    print("Observatorio del Congreso — Inicialización BD del Senado")
    print("=" * 60)

    # Paso 1: Crear base de datos con schema
    conn = create_database()

    # Paso 2: Poblar datos estáticos
    print("\n--- Poblando datos estáticos ---")
    populate_organizations(conn)

    # Paso 3: Commit
    conn.commit()

    # Paso 4: Verificar
    print("\n--- Verificación ---")
    org_count, persona_count, votacion_count = verify_data(conn)

    # Cerrar conexión
    conn.close()

    # Resumen final
    print("\n" + "=" * 60)
    print(f"Base de datos creada exitosamente: {DB_PATH}")
    print(f"  Organizaciones: {org_count}")
    print(f"  Personas: {persona_count}")
    print(f"  Votaciones: {votacion_count}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
