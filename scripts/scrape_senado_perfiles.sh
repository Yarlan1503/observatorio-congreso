#!/bin/bash
# Scraper Senado: perfiles de senadores
cd /home/cachorro/Documentos/Proyectos/observatorio-congreso
export PYTHONPATH="/home/cachorro/Documentos/Proyectos/observatorio-congreso"
export PYTHONUNBUFFERED=1

.venv/bin/python3 -m scraper_congreso.senadores.perfiles "$@"
