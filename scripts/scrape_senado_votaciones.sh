#!/bin/bash
# Scraper Senado: votaciones
cd /home/cachorro/Documentos/Proyectos/observatorio-congreso
export PYTHONUNBUFFERED=1

.venv/bin/python3 -m scraper_congreso.senadores.votaciones "$@"
