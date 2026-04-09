#!/bin/bash
# Re-ejecutar todos los análisis de Diputados (post-dedup)
# Orden: co-votación → NOMINATE → poder → poder_empírico → dinámica → visualización
cd /home/cachorro/Documentos/Proyectos/observatorio-congreso
export PYTHONPATH="/home/cachorro/Documentos/Proyectos/observatorio-congreso"
export PYTHONUNBUFFERED=1

OUTDIR="analysis/analisis-diputados/output"
LOGFILE="logs/analisis_diputados_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOGFILE"
echo "ANÁLISIS DIPUTADOS - $(date)" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"

echo "--- 1/6 Co-votación + Comunidades ---" | tee -a "$LOGFILE"
.venv/bin/python3 -m analysis.run_analysis --camara diputados --output-dir "$OUTDIR" 2>&1 | tee -a "$LOGFILE"

echo "--- 2/6 NOMINATE ---" | tee -a "$LOGFILE"
.venv/bin/python3 -m analysis.run_nominate --camara diputados --output-dir "$OUTDIR" 2>&1 | tee -a "$LOGFILE"

echo "--- 3/6 Poder Partidos (Shapley-Shubik) ---" | tee -a "$LOGFILE"
.venv/bin/python3 -m analysis.poder_partidos --camara diputados --output-dir "$OUTDIR" 2>&1 | tee -a "$LOGFILE"

echo "--- 4/6 Poder Empírico (Banzhaf) ---" | tee -a "$LOGFILE"
.venv/bin/python3 -m analysis.poder_empirico --camara diputados --output-dir "$OUTDIR" 2>&1 | tee -a "$LOGFILE"

echo "--- 5/6 Co-votación Dinámica ---" | tee -a "$LOGFILE"
.venv/bin/python3 -m analysis.run_covotacion_dinamica --camara diputados --output-dir "$OUTDIR" 2>&1 | tee -a "$LOGFILE"

echo "--- 6/6 Visualización ---" | tee -a "$LOGFILE"
.venv/bin/python3 -m analysis.visualizacion_poder --camara diputados --output-dir "$OUTDIR" 2>&1 | tee -a "$LOGFILE"

echo "========================================" | tee -a "$LOGFILE"
echo "ANÁLISIS COMPLETADO - $(date)" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"
