"""
Central configuration for the standalone v2 platform.

The v2 folder is self-contained for code, schema and outputs. The only external
dependency is the RAW geology data, which is referenced (not copied) from the
sibling sample_geology_reports/ folder by default. Override with the env var
GEO_RAW_ROOT to point elsewhere.
"""

from __future__ import annotations

import os

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE_DIR)                      # geotech_platform_v2/
WORKSPACE = os.path.dirname(ROOT)                       # geo_kg_platform/

REFERENCE = os.path.join(ROOT, "reference")
KNOWLEDGE = os.path.join(REFERENCE, "knowledge")
DATABASE = os.path.join(ROOT, "database")
OUTPUTS = os.path.join(ROOT, "outputs")
PROC = os.path.join(OUTPUTS, "processed")
PDF_ASSETS = os.path.join(OUTPUTS, "pdf_assets")
BOUNDARIES = os.path.join(OUTPUTS, "boundaries")
QA = os.path.join(OUTPUTS, "qa_maps")
DEMOS = os.path.join(OUTPUTS, "demo_reports")
BUILD_LOG = os.path.join(OUTPUTS, "build_log.md")

# Raw geology data (referenced, not copied). Default: sibling sample folder.
RAW_ROOT = os.environ.get("GEO_RAW_ROOT", os.path.join(WORKSPACE, "sample_geology_reports"))


def raw_path(*parts) -> str:
    return os.path.join(RAW_ROOT, *parts)


def ensure_dirs():
    for d in (DATABASE, OUTPUTS, PROC, PDF_ASSETS, BOUNDARIES, QA, DEMOS):
        os.makedirs(d, exist_ok=True)
