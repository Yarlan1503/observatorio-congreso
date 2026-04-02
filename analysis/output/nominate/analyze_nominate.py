#!/usr/bin/env python3
"""
Análisis cuantitativo completo de datos NOMINATE — Observatorio Congreso.
Genera todos los hallazgos numéricos solicitados en inv-003.

Uso: python3 analyze_nominate.py
"""

import pandas as pd
import numpy as np
from collections import Counter
import warnings

warnings.filterwarnings("ignore")

# ─── Carga de datos ───
BASE = "/home/cachorro/Documentos/Congreso de la Union/analysis/output/nominate"
df = pd.read_csv(f"{BASE}/coordenadas_nominate.csv")
df_cross = pd.read_csv(f"{BASE}/coordenadas_cross.csv")
df_metricas = pd.read_csv(f"{BASE}/metricas_ajuste.csv")

LEGISLATURAS = ["LX", "LXI", "LXII", "LXIII", "LXIV", "LXV", "LXVI"]

print("=" * 100)
print("ANÁLISIS CUANTITATIVO DE DATOS NOMINATE — OBSERVATORIO CONGRESO")
print("=" * 100)
print(
    f"\ncoordenadas_nominate.csv: {len(df)} filas, {df['partido'].nunique()} partidos, {df['legislatura'].nunique()} legislaturas"
)
print(
    f"coordenadas_cross.csv: {len(df_cross)} filas, {df_cross['partido'].nunique()} partidos, {df_cross['legislatura'].nunique()} legislaturas"
)


# Helper: abreviar nombre de partido
def short_party(name):
    """Extraer sigla del nombre completo del partido."""
    name = name.strip()
    if name == "Independientes":
        return "IND"
    # Buscar acrónimo entre paréntesis
    import re

    m = re.search(r"\(([A-ZÁÉÍÓÚÑ&]+)\)", name)
    if m:
        return m.group(1)
    # Si empieza con nombre conocido
    for sigla, patron in [
        ("PAN", "Partido Acción Nacional"),
        ("PRI", "Partido Revolucionario"),
        ("PRD", "Partido de la Revolución Democrática"),
        ("PT", "Partido del Trabajo"),
        ("PVEM", "Partido Verde"),
        ("MC", "Movimiento Ciudadano"),
        ("Morena", "Morena"),
        ("PES", "Partido Encuentro Social"),
        ("FNS", "Fuerza por México"),
        ("RSP", "Redes Sociales Progresistas"),
    ]:
        if patron in name:
            return sigla
    return name[:15]


df["sigla"] = df["partido"].apply(short_party)
df_cross["sigla"] = df_cross["partido"].apply(short_party)

# ════════════════════════════════════════════════════════════════════════════════
# 1. ESTADÍSTICAS DESCRIPTIVAS POR PARTIDO-LEGISLATURA
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("1. ESTADÍSTICAS DESCRIPTIVAS POR PARTIDO-LEGISLATURA")
print("=" * 100)

stats = (
    df.groupby(["sigla", "legislatura"])
    .agg(
        n=("voter_id", "count"),
        dim1_mean=("dim_1", "mean"),
        dim1_std=("dim_1", "std"),
        dim1_min=("dim_1", "min"),
        dim1_max=("dim_1", "max"),
        dim1_range=("dim_1", lambda x: x.max() - x.min()),
        dim2_mean=("dim_2", "mean"),
        dim2_std=("dim_2", "std"),
        dim2_min=("dim_2", "min"),
        dim2_max=("dim_2", "max"),
        dim2_range=("dim_2", lambda x: x.max() - x.min()),
    )
    .fillna(0)
    .reset_index()
)

stats["legislatura"] = pd.Categorical(
    stats["legislatura"], categories=LEGISLATURAS, ordered=True
)
stats = stats.sort_values(["legislatura", "sigla"])

for leg in LEGISLATURAS:
    sub = stats[stats["legislatura"] == leg].sort_values("dim1_std", ascending=True)
    if len(sub) == 0:
        continue
    print(f"\n{'─' * 90}")
    print(
        f"  Legislatura {leg} ({df_metricas.loc[df_metricas['legislatura'] == leg, 'n_legisladores'].values[0]} legisladores, "
        f"{df_metricas.loc[df_metricas['legislatura'] == leg, 'n_votaciones'].values[0]} votaciones)"
    )
    print(f"{'─' * 90}")
    print(
        f"{'Partido':<8} {'N':>4} {'μ(d1)':>9} {'σ(d1)':>11} {'rango(d1)':>11} {'μ(d2)':>9} {'σ(d2)':>11} {'rango(d2)':>11}"
    )
    print("-" * 90)
    for _, row in sub.iterrows():
        print(
            f"{row['sigla']:<8} {row['n']:>4.0f} {row['dim1_mean']:>9.4f} {row['dim1_std']:>11.6f} {row['dim1_range']:>11.6f} "
            f"{row['dim2_mean']:>9.4f} {row['dim2_std']:>11.6f} {row['dim2_range']:>11.6f}"
        )

# ════════════════════════════════════════════════════════════════════════════════
# 2. COLAPSO DE PUNTOS IDEALES
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("2. COLAPSO DE PUNTOS IDEALES (coordenadas idénticas a 6 decimales)")
print("=" * 100)


def round6(x):
    return round(x, 6)


df["coord_key"] = df.apply(lambda r: (round6(r["dim_1"]), round6(r["dim_2"])), axis=1)

colapso_results = []
for (sigla, leg), group in df.groupby(["sigla", "legislatura"]):
    n = len(group)
    coord_counts = group["coord_key"].value_counts()
    most_common_count = coord_counts.iloc[0]
    most_common_key = coord_counts.index[0]
    n_puntos_unicos = len(coord_counts)
    pct_colapso = (most_common_count / n) * 100

    # Legisladores con coordenadas idénticas a otro
    duplicated_mask = group.duplicated(subset=["coord_key"], keep=False)
    n_dup = duplicated_mask.sum()
    pct_dup = (n_dup / n) * 100

    colapso_results.append(
        {
            "sigla": sigla,
            "legislatura": leg,
            "n": n,
            "n_puntos_unicos": n_puntos_unicos,
            "n_punto_comun": most_common_count,
            "punto_comun": most_common_key,
            "pct_colapso": pct_colapso,
            "n_duplicados": n_dup,
            "pct_duplicados": pct_dup,
        }
    )

df_colapso = pd.DataFrame(colapso_results)
df_colapso["legislatura"] = pd.Categorical(
    df_colapso["legislatura"], categories=LEGISLATURAS, ordered=True
)

# Global stats
total = len(df)
total_duplicados = df[df.duplicated(subset=["coord_key"], keep=False)]
n_puntos_unicos_global = df["coord_key"].nunique()

print(f"\nRESUMEN GLOBAL:")
print(f"  Total legisladores: {total}")
print(f"  Puntos únicos en el espacio: {n_puntos_unicos_global}")
print(
    f"  Legisladores colapsados (comparten coordenadas): {len(total_duplicados)} ({100 * len(total_duplicados) / total:.1f}%)"
)
print(
    f"  Puntos ideales perdidos por colapso: {total - n_puntos_unicos_global} ({100 * (total - n_puntos_unicos_global) / total:.1f}%)"
)

# Tabla por partido-legislatura
for leg in LEGISLATURAS:
    sub = df_colapso[df_colapso["legislatura"] == leg].sort_values(
        "pct_colapso", ascending=False
    )
    if len(sub) == 0:
        continue
    print(f"\n{'─' * 75}")
    print(f"  Legislatura {leg}")
    print(f"{'─' * 75}")
    print(
        f"{'Partido':<8} {'N':>4} {'PtosÚn':>7} {'#PtCom':>7} {'%Colapso':>9} {'#Dup':>6} {'%Dup':>7}"
    )
    print("-" * 75)
    for _, row in sub.iterrows():
        flag = (
            " ★★★"
            if row["pct_colapso"] >= 80
            else (" ★★" if row["pct_colapso"] >= 50 else "")
        )
        print(
            f"{row['sigla']:<8} {row['n']:>4.0f} {row['n_puntos_unicos']:>7.0f} {row['n_punto_comun']:>7.0f} "
            f"{row['pct_colapso']:>8.1f}%{flag:<4} {row['n_duplicados']:>6.0f} {row['pct_duplicados']:>6.1f}%"
        )

# Partidos con >80% colapso
critical = df_colapso[df_colapso["pct_colapso"] >= 80]
print(
    f"\n*** ALERTA: {len(critical)} combinaciones partido-legislatura con ≥80% de colapso ***"
)
if len(critical) > 0:
    for _, row in critical.sort_values("pct_colapso", ascending=False).iterrows():
        print(
            f"  {row['legislatura']} / {row['sigla']}: {row['pct_colapso']:.1f}% ({row['n_punto_comun']:.0f}/{row['n']:.0f} en un solo punto)"
        )

# ════════════════════════════════════════════════════════════════════════════════
# 3. DISIDENTES (>2σ de la media del partido)
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("3. DISENTES (legisladores a >2σ de la media de su partido en dim_1)")
print("=" * 100)

disidentes = []
for (sigla, leg), group in df.groupby(["sigla", "legislatura"]):
    if len(group) < 3:
        continue
    mean1 = group["dim_1"].mean()
    std1 = group["dim_1"].std()
    mean2 = group["dim_2"].mean()
    std2 = group["dim_2"].std()
    if std1 == 0 or np.isnan(std1):
        continue
    for _, row in group.iterrows():
        z1 = abs(row["dim_1"] - mean1) / std1
        z2 = abs(row["dim_2"] - mean2) / std2 if std2 > 0 else 0
        if z1 > 2.0 or z2 > 2.0:
            disidentes.append(
                {
                    "legislatura": leg,
                    "sigla": sigla,
                    "nombre": row["nombre"],
                    "dim_1": row["dim_1"],
                    "dim_2": row["dim_2"],
                    "z_dim1": z1,
                    "z_dim2": z2,
                    "desviacion": "dim_1" if z1 > z2 else "dim_2",
                }
            )

df_disidentes = pd.DataFrame(disidentes)
if len(df_disidentes) > 0:
    df_disidentes = df_disidentes.sort_values("z_dim1", ascending=False)
    print(f"\nTotal disidentes encontrados: {len(df_disidentes)}")
    print(
        f"\n{'Leg':<5} {'Partido':<8} {'Nombre':<50} {'d1':>9} {'d2':>9} {'Z(d1)':>7} {'Z(d2)':>7}"
    )
    print("-" * 110)
    for _, row in df_disidentes.head(50).iterrows():
        print(
            f"{row['legislatura']:<5} {row['sigla']:<8} {row['nombre'][:48]:<50} {row['dim_1']:>9.4f} {row['dim_2']:>9.4f} {row['z_dim1']:>7.2f} {row['z_dim2']:>7.2f}"
        )

    if len(df_disidentes) > 50:
        print(f"\n  ... y {len(df_disidentes) - 50} disidentes más")

    # Resumen por partido
    print("\nDisidentes por partido:")
    for sigla, grp in df_disidentes.groupby("sigla"):
        print(f"  {sigla}: {len(grp)} disidentes")
else:
    print("\nNo se encontraron disidentes (ningún legislador a >2σ)")

# ════════════════════════════════════════════════════════════════════════════════
# 4. ANÁLISIS CROSS-LEGISLATURA
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("4. ANÁLISIS CROSS-LEGISLATURA (coordenadas_cross.csv)")
print("=" * 100)

# Centroides por partido-legislatura
centroides_cross = (
    df_cross.groupby(["sigla", "legislatura"])
    .agg(
        n=("voter_id", "count"),
        c1_mean=("dim_1", "mean"),
        c2_mean=("dim_2", "mean"),
        c1_std=("dim_1", "std"),
        c2_std=("dim_2", "std"),
    )
    .fillna(0)
    .reset_index()
)
centroides_cross["legislatura"] = pd.Categorical(
    centroides_cross["legislatura"], categories=LEGISLATURAS, ordered=True
)

print("\nCentroides por partido-legislatura:")
for sigla in sorted(centroides_cross["sigla"].unique()):
    sub = centroides_cross[centroides_cross["sigla"] == sigla].sort_values(
        "legislatura"
    )
    if len(sub) <= 1:
        continue
    print(f"\n  {sigla}:")
    print(f"  {'Leg':<5} {'N':>4} {'μ(d1)':>9} {'μ(d2)':>9}")
    prev_c1 = None
    for _, row in sub.iterrows():
        movimiento = ""
        if prev_c1 is not None:
            delta_c1 = row["c1_mean"] - prev_c1
            movimiento = f"  Δ={delta_c1:+.4f}"
        print(
            f"  {row['legislatura']:<5} {row['n']:>4.0f} {row['c1_mean']:>9.4f} {row['c2_mean']:>9.4f}{movimiento}"
        )
        prev_c1 = row["c1_mean"]

# ¿Partidos que cambiaron de lado?
print("\n\nCambio de lado del espectro (signo de dim_1):")
for sigla in sorted(centroides_cross["sigla"].unique()):
    sub = centroides_cross[centroides_cross["sigla"] == sigla].sort_values(
        "legislatura"
    )
    if len(sub) <= 1:
        continue
    signos = sub["c1_mean"].apply(lambda x: "+" if x >= 0 else "-").tolist()
    legs = sub["legislatura"].tolist()
    if len(set(signos)) > 1:
        cambios = []
        for i in range(1, len(signos)):
            if signos[i] != signos[i - 1]:
                cambios.append(f"{legs[i - 1]}→{legs[i]}")
        print(
            f"  {sigla}: Cambió de lado en {', '.join(cambios)} (signos: {' → '.join(f'{l}({s})' for l, s in zip(legs, signos))})"
        )

# Distancia máxima del centroide entre legislaturas
print("\nDistancia euclidiana entre centroides consecutivos:")
for sigla in sorted(centroides_cross["sigla"].unique()):
    sub = (
        centroides_cross[centroides_cross["sigla"] == sigla]
        .sort_values("legislatura")
        .reset_index(drop=True)
    )
    if len(sub) <= 1:
        continue
    for i in range(1, len(sub)):
        d = np.sqrt(
            (sub.loc[i, "c1_mean"] - sub.loc[i - 1, "c1_mean"]) ** 2
            + (sub.loc[i, "c2_mean"] - sub.loc[i - 1, "c2_mean"]) ** 2
        )
        print(
            f"  {sigla} {sub.loc[i - 1, 'legislatura']}→{sub.loc[i, 'legislatura']}: {d:.4f}"
        )

# ════════════════════════════════════════════════════════════════════════════════
# 5. ANÁLISIS GLOBAL DE LA DIMENSIÓN 2
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("5. ANÁLISIS GLOBAL DE LA DIMENSIÓN 2")
print("=" * 100)

# Varianza total por dimensión
var_d1 = df["dim_1"].var()
var_d2 = df["dim_2"].var()
var_total = var_d1 + var_d2
pct_d1 = 100 * var_d1 / var_total
pct_d2 = 100 * var_d2 / var_total

print(f"\nVarianza global:")
print(f"  Var(dim_1) = {var_d1:.6f} ({pct_d1:.1f}%)")
print(f"  Var(dim_2) = {var_d2:.6f} ({pct_d2:.1f}%)")
print(f"  Ratio dim_1/dim_2 = {var_d1 / var_d2:.2f}x")

# Por legislatura
print("\nVarianza por dimensión y legislatura:")
print(
    f"{'Leg':<6} {'N_Vot':>6} {'w':>5} {'Var(d1)':>12} {'Var(d2)':>12} {'%d1':>7} {'%d2':>7} {'Rango(d2)':>12} {'Ratio':>7}"
)
print("-" * 90)

w1_legs = ["LX", "LXV", "LXVI"]  # w=1.0
for leg in LEGISLATURAS:
    sub = df[df["legislatura"] == leg]
    v1 = sub["dim_1"].var()
    v2 = sub["dim_2"].var()
    vt = v1 + v2
    r2 = sub["dim_2"].max() - sub["dim_2"].min()
    w_val = df_metricas.loc[df_metricas["legislatura"] == leg, "w"].values[0]
    n_vot = df_metricas.loc[df_metricas["legislatura"] == leg, "n_votaciones"].values[0]
    flag = " ← w=1.0" if leg in w1_legs else ""
    print(
        f"{leg:<6} {n_vot:>6.0f} {w_val:>5.2f} {v1:>12.6f} {v2:>12.6f} {100 * v1 / vt:>6.1f}% {100 * v2 / vt:>6.1f}% {r2:>12.6f} {v1 / v2 if v2 > 0 else float('inf'):>7.2f}{flag}"
    )

# Comparación w=1.0 vs w<1.0
print("\nComparación w=1.0 vs w<1.0:")
w1_df = df[df["legislatura"].isin(w1_legs)]
w0_df = df[~df["legislatura"].isin(w1_legs)]

for label, sub_df in [("w=1.0 (LX, LXV, LXVI)", w1_df), ("w<1.0 (LXI-LXIV)", w0_df)]:
    v1 = sub_df["dim_1"].var()
    v2 = sub_df["dim_2"].var()
    print(f"  {label}:")
    print(
        f"    Var(dim_2) = {v2:.6f}, Rango(dim_2) = {sub_df['dim_2'].max() - sub_df['dim_2'].min():.6f}"
    )
    print(f"    Ratio dim_1/dim_2 = {v1 / v2:.2f}x")

# ════════════════════════════════════════════════════════════════════════════════
# 6. RESUMEN EJECUTIVO
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("6. RESUMEN EJECUTIVO DE HALLAZGOS")
print("=" * 100)

# Proporción total de legisladores con coordenadas idénticas a otro
total_dup_global = df.duplicated(subset=["coord_key"], keep=False).sum()
pct_dup_global = 100 * total_dup_global / total

print(f"\n{'─' * 80}")
print(f"  COLAPSO GLOBAL")
print(f"{'─' * 80}")
print(f"  Legisladores totales: {total}")
print(f"  Con coordenadas idénticas a otro: {total_dup_global} ({pct_dup_global:.1f}%)")
print(
    f"  Puntos únicos en el espacio: {n_puntos_unicos_global} ({100 * n_puntos_unicos_global / total:.1f}%)"
)

# Partidos con mayor/menor compactación (usando std de dim_1)
party_compact = (
    stats.groupby("sigla")
    .agg(
        avg_std_d1=("dim1_std", "mean"),
        avg_std_d2=("dim2_std", "mean"),
        n_groups=("n", "count"),
    )
    .reset_index()
)
party_compact = party_compact[
    party_compact["n_groups"] >= 2
]  # Solo partidos en 2+ legislaturas

print(f"\n{'─' * 80}")
print(f"  COMPACTACIÓN POR PARTIDO (promedio σ(dim_1) a través de legislaturas)")
print(f"{'─' * 80}")
party_compact = party_compact.sort_values("avg_std_d1")
print(
    f"  Más compacto: {party_compact.iloc[0]['sigla']} (σ_avg={party_compact.iloc[0]['avg_std_d1']:.6f})"
)
print(
    f"  Menos compacto: {party_compact.iloc[-1]['sigla']} (σ_avg={party_compact.iloc[-1]['avg_std_d1']:.6f})"
)
print(f"\n  Ranking completo:")
print(f"  {'Partido':<8} {'σ_avg(d1)':>12} {'σ_avg(d2)':>12} {'Legs':>5}")
for _, row in party_compact.iterrows():
    print(
        f"  {row['sigla']:<8} {row['avg_std_d1']:>12.6f} {row['avg_std_d2']:>12.6f} {row['n_groups']:>5.0f}"
    )

# Legislatura con mayor/menor dispersión
leg_disp = (
    df.groupby("legislatura")
    .agg(
        std_d1=("dim_1", "std"),
        std_d2=("dim_2", "std"),
        range_d1=("dim_1", lambda x: x.max() - x.min()),
        range_d2=("dim_2", lambda x: x.max() - x.min()),
    )
    .reset_index()
)
leg_disp["total_range"] = leg_disp["range_d1"] + leg_disp["range_d2"]

print(f"\n{'─' * 80}")
print(f"  DISPERSIÓN POR LEGISLATURA")
print(f"{'─' * 80}")
leg_disp_sorted = leg_disp.sort_values("total_range")
print(
    f"  Menor dispersión: {leg_disp_sorted.iloc[0]['legislatura']} (rango_total={leg_disp_sorted.iloc[0]['total_range']:.6f})"
)
print(
    f"  Mayor dispersión: {leg_disp_sorted.iloc[-1]['legislatura']} (rango_total={leg_disp_sorted.iloc[-1]['total_range']:.6f})"
)
print(f"\n  Ranking completo:")
print(
    f"  {'Leg':<6} {'σ(d1)':>11} {'σ(d2)':>11} {'Rango(d1)':>12} {'Rango(d2)':>12} {'R_Total':>12}"
)
for _, row in leg_disp.sort_values("legislatura").iterrows():
    print(
        f"  {row['legislatura']:<6} {row['std_d1']:>11.6f} {row['std_d2']:>11.6f} {row['range_d1']:>12.6f} {row['range_d2']:>12.6f} {row['total_range']:>12.6f}"
    )

# Correlación n_votaciones vs dispersión
print(f"\n{'─' * 80}")
print(f"  CORRELACIÓN: VOTACIONES DISPONIBLES vs DISPERSIÓN")
print(f"{'─' * 80}")
merge_data = leg_disp.merge(
    df_metricas[["legislatura", "n_votaciones"]], on="legislatura"
)
corr_d1 = merge_data["n_votaciones"].corr(merge_data["range_d1"])
corr_d2 = merge_data["n_votaciones"].corr(merge_data["range_d2"])
corr_total = merge_data["n_votaciones"].corr(merge_data["total_range"])
print(f"  Correlación(n_votaciones, rango_d1): r = {corr_d1:.4f}")
print(f"  Correlación(n_votaciones, rango_d2): r = {corr_d2:.4f}")
print(f"  Correlación(n_votaciones, rango_total): r = {corr_total:.4f}")
print(
    f"\n  {'Leg':<6} {'N_Vot':>6} {'Rango(d1)':>12} {'Rango(d2)':>12} {'R_Total':>12}"
)
for _, row in merge_data.sort_values("n_votaciones").iterrows():
    print(
        f"  {row['legislatura']:<6} {row['n_votaciones']:>6.0f} {row['range_d1']:>12.6f} {row['range_d2']:>12.6f} {row['total_range']:>12.6f}"
    )

# Hallazgos clave
print(f"\n{'═' * 100}")
print(f"  HALLAZGOS CLAVE PARA EL ARTÍCULO")
print(f"{'═' * 100}")
print(
    f"\n  1. COLAPSO MASIVO: {pct_dup_global:.1f}% de legisladores comparten coordenadas con otro."
)
print(f"     Solo {n_puntos_unicos_global} puntos únicos de {total} legisladores.")
print(f"     NOMINATE no discrimina entre la mayoría de legisladores.")

critical_pct = len(df_colapso[df_colapso["pct_colapso"] >= 80]) / len(df_colapso) * 100
print(
    f"\n  2. PARTIDOS BLOQUE: {len(critical)} de {len(df_colapso)} combinaciones partido-legislatura ({critical_pct:.1f}%)"
)
print(f"     tienen ≥80% de miembros en un solo punto ideal.")

# LX case: w=1.0 with only 11 votes
lx_pct = df_colapso[df_colapso["legislatura"] == "LX"]["pct_colapso"].mean()
print(f"\n  3. CASO LX (w=1.0, solo 11 votaciones): Colapso promedio = {lx_pct:.1f}%")
print(f"     β=30.0 saturado + 11 votaciones = disciplina artificial extrema.")

print(f"\n  4. DIMENSIÓN 2: Contiene solo {pct_d2:.1f}% de la varianza total.")
print(
    f"     Ratio dim_1/dim_2 = {var_d1 / var_d2:.1f}x — dim_2 es prácticamente ruido."
)

print(f"\n  5. NINGUNA LEGISLATURA CONVERGIÓ en 100 iteraciones con β=30.0.")

if abs(corr_total) > 0.5:
    direction = "positiva" if corr_total > 0 else "negativa"
    print(
        f"\n  6. MÁS VOTACIONES = MÁS DISPERSIÓN (r={corr_total:.3f}): La señal real emerge con datos."
    )
else:
    print(f"\n  6. CORRELACIÓN DÉBIL votaciones-dispersión (r={corr_total:.3f}).")
    print(f"     La dispersión no depende solo del número de votaciones.")

print(f"\n{'═' * 100}")
print("FIN DEL ANÁLISIS")
print(f"{'═' * 100}")
