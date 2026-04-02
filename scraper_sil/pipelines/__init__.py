"""
pipelines/__init__.py — Módulo de pipelines para el scraper SIL.
"""

from scraper_sil.pipelines.sil_pipeline import SILPipeline
from scraper_sil.pipelines.legislature_pipeline import LegislaturePipeline

__all__ = ["SILPipeline", "LegislaturePipeline"]
