"""
scraper — Scraper del SITL/INFOPAL para el Observatorio del Congreso.

Obtiene votaciones nominales de la Cámara de Diputados desde el
Sistema de Información para la Estadística Parlamentaria (INFOPAL).

Arquitectura por capas:
    client → parsers → models → transformers → loader → pipeline
"""
