#!/bin/bash
# Scraper Diputados: todas las legislaturas LX-LXVI
# Cada legislatura se scrapea con --all-periods
cd /home/cachorro/Documentos/Proyectos/observatorio-congreso
export PYTHONUNBUFFERED=1

LOGFILE="logs/diputados_scrape_$(date +%Y%m%d_%H%M%S).log"

for LEG in LX LXI LXII LXIII LXIV LXV LXVI; do
    echo "========================================" | tee -a "$LOGFILE"
    echo "LEGISLATURA: $LEG - $(date)" | tee -a "$LOGFILE"
    echo "========================================" | tee -a "$LOGFILE"
    .venv/bin/python3 -m scraper_congreso.diputados --leg "$LEG" --all-periods --delay 2.0 2>&1 | tee -a "$LOGFILE"
    echo "" | tee -a "$LOGFILE"
done

echo "========================================" | tee -a "$LOGFILE"
echo "SCRAPING COMPLETADO - $(date)" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"
