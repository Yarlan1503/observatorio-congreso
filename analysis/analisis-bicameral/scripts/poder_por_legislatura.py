"""
poder_por_legislatura.py — Poder Empírico por Legislatura
=========================================================
Calcula poder empírico desagregado por legislatura para ambas cámaras
(Diputados y Senado), generando un CSV con la evolución histórica y una
gráfica comparativa.

Salidas:
  - analysis/analisis-bicameral/output/poder_empirico_por_legislatura.csv
  - analysis/analisis-bicameral/output/poder_empirico_evolucion.png

Uso:
    cd /path/to/observatorio-congreso
    .venv/bin/python analysis/analisis-bicameral/scripts/poder_por_legislatura.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent

import csv
import sqlite3
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --- Importar infraestructura existente ---
from analysis.poder_empirico import (
    analyze_vote_event,
    calc_empirical_power,
    get_seat_counts,
    get_requirement,
)
import analysis.poder_empirico as pe
from db.constants import (
    _ORG_TO_SHORT,
    CAMARA_DIPUTADOS_ID,
    CAMARA_SENADO_ID,
    get_total_seats,
    init_constants_from_db,
)

# --- Rutas ---
DB_PATH = ROOT / "db" / "congreso.db"
BIC_OUTPUT = ROOT / "analysis" / "analisis-bicameral" / "output"

# --- Colores y orden de partidos para la gráfica ---
PARTY_COLORS = {
    "MORENA": "#8B0000",
    "PAN": "#003399",
    "PRI": "#00A650",
    "PVEM": "#006633",
    "PT": "#CC0000",
    "MC": "#FF6600",
    "PRD": "#FFD700",
}
COMMON_PARTIES = ["MORENA", "PAN", "PRI", "PVEM", "PT", "MC", "PRD"]

LEG_ORDER = ["LX", "LXI", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]

# Asientos constitucionales por cámara (para mayoría calificada)
SEATS_CONST = {"D": 500, "S": 128}


def _build_party_short():
    """Construye mapeo completo org_id → sigla, incluyendo IDs legacy (O01-O07).

    Después de init_constants_from_db(), _ORG_TO_SHORT solo tiene los IDs de
    la tabla organization (O11+). Los IDs legacy O01-O07 usados en LXVI
    también necesitan mapearse manualmente.
    """
    import db.constants as c

    mapping = dict(c._ORG_TO_SHORT)  # DB-based: O11=MORENA, O12=PAN, etc.
    # Legacy IDs (hardcoded en constants.py, usados en votos de LXVI)
    mapping.update(
        {
            "O01": "MORENA",
            "O02": "PT",
            "O03": "PVEM",
            "O04": "PAN",
            "O05": "PRI",
            "O06": "MC",
            "O07": "PRD",
        }
    )
    return mapping


def get_ve_ids_by_legislatura(conn, camara, legislatura):
    """Obtiene VE IDs con resultado para una legislatura y cámara específicas."""
    org_id = CAMARA_DIPUTADOS_ID if camara == "D" else CAMARA_SENADO_ID
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM vote_event "
        "WHERE result IS NOT NULL AND organization_id = ? AND legislatura = ? "
        "ORDER BY id",
        (org_id, legislatura),
    )
    return [row[0] for row in cur.fetchall()]


def calc_power_for_legislatura(conn, legislatura, camara, party_short):
    """Calcula poder empírico para una legislatura y cámara.

    Returns:
        Lista de dicts con poder empírico por partido (antes de merge).
    """
    # Ajustar total de asientos para mayoría calificada
    pe._total_seats_for_analysis = SEATS_CONST[camara]

    ve_ids = get_ve_ids_by_legislatura(conn, camara, legislatura)
    if not ve_ids:
        return []

    # Analizar cada VE
    analyses = [analyze_vote_event(conn, ve_id) for ve_id in ve_ids]

    # Poder empírico: {org_id: veces_crítico / total_votaciones}
    empirical_power = calc_empirical_power(analyses)

    # Escaños por partido
    seats = get_seat_counts(conn, camara=camara, legislatura=legislatura)

    # Total de asientos (constitucional para poder nominal)
    total_seats = SEATS_CONST[camara]

    # Contar votaciones calificadas
    n_calificadas = sum(1 for a in analyses if a.get("requirement") == "mayoria_calificada")

    # Construir resultados por partido (una fila por org_id)
    results = []
    for org_id, seat_count in seats.items():
        if seat_count <= 0:
            continue

        short_name = party_short.get(org_id, org_id)
        poder_emp = empirical_power.get(org_id, 0)
        poder_nom = seat_count / total_seats if total_seats > 0 else 0

        results.append(
            {
                "legislatura": legislatura,
                "partido": short_name,
                "camara": "Diputados" if camara == "D" else "Senado",
                "escanos": seat_count,
                "poder_nominal": round(poder_nom * 100, 2),
                "poder_empirico": round(poder_emp * 100, 2),
                "n_votaciones": len(ve_ids),
                "n_calificadas": n_calificadas,
                "org_id": org_id,
            }
        )

    return results


def merge_rows(all_results):
    """Merge filas con mismo partido normalizado (e.g., O01 + O11 → MORENA).

    Cuando un mismo partido tiene múltiples org_ids en una legislatura
    (caso LXVI: O01 y O11 ambos son MORENA), se suman escaños y poder empírico.
    El poder empírico se suma (no se promedia) porque cada org_id refleja
    veces-crítico / total, y la suma da el poder combinado correcto.
    """
    merged = defaultdict(
        lambda: {
            "escanos": 0,
            "poder_empirico": 0.0,
            "poder_nominal": 0.0,
            "n_votaciones": 0,
            "n_calificadas": 0,
        }
    )

    for r in all_results:
        key = (r["legislatura"], r["partido"], r["camara"])
        m = merged[key]
        m["escanos"] += r["escanos"]
        # Sumar poderes (cada fracción es veces_crítico / total_votaciones)
        m["poder_empirico"] += r["poder_empirico"]
        m["poder_nominal"] += r["poder_nominal"]
        m["n_votaciones"] = max(m["n_votaciones"], r["n_votaciones"])
        m["n_calificadas"] = max(m["n_calificadas"], r["n_calificadas"])
        m["legislatura"] = r["legislatura"]
        m["partido"] = r["partido"]
        m["camara"] = r["camara"]

    final_rows = []
    for key, m in merged.items():
        final_rows.append(
            {
                "legislatura": m["legislatura"],
                "partido": m["partido"],
                "camara": m["camara"],
                "escanos": m["escanos"],
                "poder_nominal": round(m["poder_nominal"], 2),
                "poder_empirico": round(m["poder_empirico"], 2),
                "n_votaciones": m["n_votaciones"],
                "n_calificadas": m["n_calificadas"],
            }
        )

    return final_rows


def save_csv(final_rows, csv_path):
    """Guarda el CSV desagregado."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "legislatura",
                "partido",
                "camara",
                "escanos",
                "poder_nominal",
                "poder_empirico",
                "n_votaciones",
                "n_calificadas",
            ],
        )
        writer.writeheader()
        writer.writerows(final_rows)


def plot_evolution(final_rows, png_path):
    """Genera gráfica de evolución del poder empírico (2 subplots por cámara)."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharey=True)

    for ax_idx, camara in enumerate(["Diputados", "Senado"]):
        ax = axes[ax_idx]
        camara_rows = [r for r in final_rows if r["camara"] == camara]

        # Pivot: {partido: {legislatura: poder_empirico}}
        pivot = defaultdict(dict)
        for r in camara_rows:
            pivot[r["partido"]][r["legislatura"]] = r["poder_empirico"]

        for party in COMMON_PARTIES:
            if party not in pivot:
                continue
            vals = [pivot[party].get(leg, None) for leg in LEG_ORDER]
            color = PARTY_COLORS.get(party, "#888888")
            ax.plot(
                LEG_ORDER,
                vals,
                marker="o",
                markersize=5,
                linewidth=2,
                label=party,
                color=color,
                alpha=0.85,
            )

        ax.set_title(camara, fontsize=14, fontweight="bold")
        ax.set_xlabel("Legislatura", fontsize=11)
        if ax_idx == 0:
            ax.set_ylabel("Poder Empírico (%)", fontsize=11)
        ax.grid(True, axis="y", alpha=0.3, linestyle="--")
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=9, loc="upper left", framealpha=0.9)

    fig.suptitle(
        "Evolución del Poder Empírico por Legislatura",
        fontsize=16,
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def print_summary(final_rows):
    """Imprime tabla resumen en consola."""
    print(f"\n  Total registros: {len(final_rows)}")
    for camara in ["Diputados", "Senado"]:
        print(f"\n  === {camara} ===")
        camara_rows = [r for r in final_rows if r["camara"] == camara]
        parties = sorted(set(r["partido"] for r in camara_rows if r["partido"] in COMMON_PARTIES))
        header = f"  {'Partido':<10}" + "".join(f"  {leg:>6}" for leg in LEG_ORDER)
        print(header)
        for party in parties:
            vals = {
                r["legislatura"]: r["poder_empirico"] for r in camara_rows if r["partido"] == party
            }
            row_str = f"  {party:<10}" + "".join(f"  {vals.get(leg, 0):>6.1f}" for leg in LEG_ORDER)
            print(row_str)


def main():
    print("  Inicializando constantes...")
    init_constants_from_db(str(DB_PATH))
    import db.constants as c

    # Actualizar módulo de poder_empirico con los mapeos dinámicos
    pe.GROUP_TO_ORG = c._NAME_TO_ORG

    # Mapeo completo de org_id → sigla corta
    party_short = _build_party_short()

    BIC_OUTPUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    all_results = []

    for leg in LEG_ORDER:
        for camara in ["D", "S"]:
            camara_label = "Diputados" if camara == "D" else "Senado"
            ve_count = len(get_ve_ids_by_legislatura(conn, camara, leg))
            print(f"  {leg} {camara_label}: {ve_count} VEs...", end="", flush=True)

            results = calc_power_for_legislatura(conn, leg, camara, party_short)
            all_results.extend(results)
            print(f" {len(results)} partidos")

    conn.close()

    # Merge duplicados (O01 + O11 → MORENA, etc.)
    final_rows = merge_rows(all_results)

    # Guardar CSV
    csv_path = BIC_OUTPUT / "poder_empirico_por_legislatura.csv"
    save_csv(final_rows, csv_path)
    print(f"\n  → CSV guardado: {csv_path}")

    # Generar gráfica
    png_path = BIC_OUTPUT / "poder_empirico_evolucion.png"
    plot_evolution(final_rows, png_path)
    print(f"  → Gráfica guardada: {png_path}")

    # Resumen en consola
    print_summary(final_rows)

    return final_rows


if __name__ == "__main__":
    main()
