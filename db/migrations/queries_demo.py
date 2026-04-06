#!/usr/bin/env python3
"""
queries_demo.py — Consultas de ejemplo contra la base de datos congreso.db.

Ejecuta 6 queries de demostración que muestran los datos poblados:
conteos por tipo, listas completas y métricas simples.

Sin dependencias externas (solo sqlite3 de stdlib).
"""

import os
import sqlite3
import sys

# Ruta a la base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")


def format_table(headers, rows):
    """Formatear una tabla de resultados con headers de columna.

    Calcula el ancho de cada columna automáticamente y usa
    separadores para legibilidad. Sin dependencias externas.
    """
    if not rows:
        return "  (sin resultados)"

    # Calcular ancho de cada columna
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in rows:
            if i < len(row):
                cell_str = str(row[i]) if row[i] is not None else "NULL"
                max_width = max(max_width, len(cell_str))
        col_widths.append(max_width)

    # Construir líneas
    lines = []

    # Header
    header_parts = []
    for i, header in enumerate(headers):
        header_parts.append(header.ljust(col_widths[i]))
    lines.append("  " + " | ".join(header_parts))

    # Separador
    sep_parts = []
    for w in col_widths:
        sep_parts.append("-" * w)
    lines.append("  " + "-+-".join(sep_parts))

    # Filas
    for row in rows:
        row_parts = []
        for i, cell in enumerate(row):
            cell_str = str(cell) if cell is not None else "NULL"
            row_parts.append(cell_str.ljust(col_widths[i]))
        lines.append("  " + " | ".join(row_parts))

    return "\n".join(lines)


def run_query(conn, title, query, headers):
    """Ejecutar una query e imprimir los resultados formateados."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")
    print(f"  SQL: {query}")
    print()

    try:
        cur = conn.execute(query)
        rows = cur.fetchall()
        print(format_table(headers, rows))
        print(f"\n  Total filas: {len(rows)}")
    except sqlite3.Error as e:
        print(f"  ERROR: {e}")
        return False

    return True


def main():
    """Ejecutar todas las queries de demostración."""
    # Verificar que la BD existe
    if not os.path.exists(DB_PATH):
        print(f"ERROR: No se encontró {DB_PATH}")
        print("Ejecuta primero init_db.py para crear la base de datos.")
        return 1

    print("Observatorio del Congreso — Queries de demostración")
    print(f"Base de datos: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    queries = [
        (
            "1. Conteo de organizaciones por tipo",
            "SELECT clasificacion, COUNT(*) as total "
            "FROM organization GROUP BY clasificacion ORDER BY total DESC;",
            ["clasificacion", "total"],
        ),
        (
            "2. Áreas por tipo (estado)",
            "SELECT clasificacion, COUNT(*) as total FROM area GROUP BY clasificacion;",
            ["clasificacion", "total"],
        ),
        (
            "3. Actores externos por tipo",
            "SELECT tipo, COUNT(*) as total, "
            "GROUP_CONCAT(nombre, '; ') as actores "
            "FROM actor_externo GROUP BY tipo ORDER BY total DESC;",
            ["tipo", "total", "actores"],
        ),
        (
            "4. Lista completa de organizaciones",
            "SELECT id, nombre, clasificacion FROM organization ORDER BY clasificacion, nombre;",
            ["id", "nombre", "clasificacion"],
        ),
        (
            "5. Lista completa de actores externos",
            "SELECT id, nombre, tipo, observaciones FROM actor_externo ORDER BY tipo, nombre;",
            ["id", "nombre", "tipo", "observaciones"],
        ),
        (
            "6. Top 5 actores por longitud de observaciones (proxy de relevancia)",
            "SELECT nombre, tipo, LENGTH(observaciones) as chars_observaciones "
            "FROM actor_externo ORDER BY chars_observaciones DESC LIMIT 5;",
            ["nombre", "tipo", "chars_observaciones"],
        ),
    ]

    exit_code = 0
    for title, query, headers in queries:
        success = run_query(conn, title, query, headers)
        if not success:
            exit_code = 1

    conn.close()

    if exit_code == 0:
        print(f"\n{'=' * 60}")
        print(" Todas las queries ejecutadas exitosamente.")
        print(f"{'=' * 60}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
