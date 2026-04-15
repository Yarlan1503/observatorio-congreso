#!/usr/bin/env python3
"""Pipeline CSV -> JSON para el Observatorio del Congreso (CachorroSpace).

Lee 7 CSVs del directorio analysis/output/ y exporta JSONs listos para
consumo por ECharts en ~/Documentos/CachorroSpace/public/data/observatorio/.

Uso:
    python analysis/scripts/export_observatorio_json.py
"""

import json
from pathlib import Path

import polars as pl

from analysis.constants import COLORES_WEB, PARTIDO_MAP

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent.parent  # Project root
OUTPUT_DIR = Path("/home/cachorro/Documentos/CachorroSpace/public/data/observatorio")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_partido(df: pl.DataFrame, col: str = "partido") -> pl.DataFrame:
    """Normaliza nombres completos de partido a siglas cortas.

    Valores ya normalizados (siglas) se conservan gracias a default=pl.col(col).
    """
    return df.with_columns(pl.col(col).replace_strict(PARTIDO_MAP, default=pl.col(col)))


def round_records(records: list[dict], decimals: int = 6) -> list[dict]:
    """Redondea valores float en una lista de dicts in-place."""
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, float):
                rec[k] = round(v, decimals)
    return records


def write_json(obj, path: Path) -> None:
    """Escribe objeto Python como JSON UTF-8 indentado."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------


def export_nominate() -> int:
    """1. nominate.json -- Coordenadas NOMINATE por legislatura."""
    df = pl.read_csv(
        BASE_DIR / "analysis/analisis-diputados/output/nominate/coordenadas_nominate.csv"
    )
    df = normalize_partido(df)

    legislaturas = sorted(df["legislatura"].unique().to_list())
    legislators = round_records(df.to_dicts())

    data = {
        "legislaturas": legislaturas,
        "colores": COLORES_WEB,
        "legisladores": legislators,
    }
    write_json(data, OUTPUT_DIR / "nominate.json")
    return len(legislators)


def export_nominate_cross() -> int:
    """2. nominate_cross.json -- Coordenadas cross-legislatura."""
    df = pl.read_csv(BASE_DIR / "analysis/analisis-diputados/output/nominate/coordenadas_cross.csv")
    df = normalize_partido(df)

    legislaturas = sorted(df["legislatura"].unique().to_list())
    legislators = round_records(df.to_dicts())

    data = {
        "legislaturas": legislaturas,
        "colores": COLORES_WEB,
        "legisladores": legislators,
    }
    write_json(data, OUTPUT_DIR / "nominate_cross.json")
    return len(legislators)


def export_nominate_metrics() -> int:
    """3. nominate_metrics.json -- Metricas de ajuste por legislatura."""
    df = pl.read_csv(BASE_DIR / "analysis/analisis-diputados/output/nominate/metricas_ajuste.csv")
    records = round_records(df.to_dicts())
    write_json(records, OUTPUT_DIR / "nominate_metrics.json")
    return len(records)


def export_covotacion_disciplina() -> int:
    """4. covotacion_disciplina.json -- Disciplina partidista por ventana.

    El CSV tiene ventanas en filas y partidos en columnas. Se reestructura
    a formato consumible por ECharts heatmap.
    """
    df = pl.read_csv(
        BASE_DIR / "analysis/analisis-diputados/output/dinamica/disciplina_partidista.csv"
    )

    party_cols = [c for c in df.columns if c != "partido"]
    # Redondear columnas float de partidos
    df = df.with_columns(pl.col(party_cols).round(6))

    ventanas = df["partido"].to_list()
    partidos = party_cols
    # rows() devuelve tuplas; las celdas vacias (null) se convierten a None -> null en JSON
    disciplina = [list(row) for row in df.select(party_cols).rows()]

    data = {
        "ventanas": ventanas,
        "partidos": partidos,
        "disciplina": disciplina,
    }
    write_json(data, OUTPUT_DIR / "covotacion_disciplina.json")
    return len(ventanas)


def export_covotacion_evolucion() -> int:
    """5. covotacion_evolucion.json -- Evolucion de metricas de co-votacion."""
    df = pl.read_csv(
        BASE_DIR / "analysis/analisis-diputados/output/dinamica/evolucion_metricas.csv"
    )
    records = round_records(df.to_dicts())
    write_json(records, OUTPUT_DIR / "covotacion_evolucion.json")
    return len(records)


def export_covotacion_stability() -> int:
    """6. covotacion_stability.json -- Stability index entre periodos."""
    df = pl.read_csv(BASE_DIR / "analysis/analisis-diputados/output/dinamica/stability_index.csv")
    records = round_records(df.to_dicts())
    write_json(records, OUTPUT_DIR / "covotacion_stability.json")
    return len(records)


def export_poder_completo() -> int:
    """7. poder_completo.json -- Indices de poder por partido y umbral."""
    df = pl.read_csv(BASE_DIR / "analysis/analisis-diputados/output/poder_completo.csv")
    # Renombrar columnas con caracteres especiales a snake_case para JSON keys
    df = df.rename(
        {
            "Partido": "partido",
            "Org_ID": "org_id",
            "Esca\u00f1os": "escanos",  # sin tilde para key consistente
            "Umbral": "umbral",
            "Nominal_%": "nominal_pct",
            "Shapley_Shubik_%": "shapley_pct",
            "Banzhaf_%": "banzhaf_pct",
        }
    )
    records = round_records(df.to_dicts())
    write_json(records, OUTPUT_DIR / "poder_completo.json")
    return len(records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

EXPORTS = [
    ("nominate.json", export_nominate),
    ("nominate_cross.json", export_nominate_cross),
    ("nominate_metrics.json", export_nominate_metrics),
    ("covotacion_disciplina.json", export_covotacion_disciplina),
    ("covotacion_evolucion.json", export_covotacion_evolucion),
    ("covotacion_stability.json", export_covotacion_stability),
    ("poder_completo.json", export_poder_completo),
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Observatorio: CSV -> JSON Pipeline ===\n")
    total = 0
    for filename, func in EXPORTS:
        n = func()
        total += n
        print(f"  {filename:<30s} {n:>5d} registros")

    print(f"\n  Total: {total} registros en {len(EXPORTS)} archivos")
    print(f"  Output: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
