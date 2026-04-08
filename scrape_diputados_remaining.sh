#!/bin/bash
# Scraper Diputados: completar LXIV + scrapear LXV + LXVI
# Lanzado: $(date)
cd /home/cachorro/Documentos/Proyectos/observatorio-congreso
export PYTHONPATH="/home/cachorro/Documentos/Proyectos/observatorio-congreso"
export PYTHONUNBUFFERED=1

LOGFILE="logs/diputados_remaining_$(date +%Y%m%d_%H%M%S).log"

for LEG in LXIV LXV LXVI; do
    echo "========================================" | tee -a "$LOGFILE"
    echo "LEGISLATURA: $LEG - $(date)" | tee -a "$LOGFILE"
    echo "========================================" | tee -a "$LOGFILE"
    .venv/bin/python3 -m diputados.scraper.pipeline --leg "$LEG" --all-periods --delay 2.0 2>&1 | tee -a "$LOGFILE"
    echo "" | tee -a "$LOGFILE"
done

echo "========================================" | tee -a "$LOGFILE"
echo "SCRAPING COMPLETADO - $(date)" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"
