"""
Central configuration for the geotech platform.

The package keeps code under src/ while reference data, database files, and
outputs remain at the project root. Raw geology data is referenced, not copied,
from the project-root geology_reports/ folder by default. Override with the env
var GEO_RAW_ROOT to point elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_project_root() -> str:
    env_root = os.environ.get("GEOTECH_PLATFORM_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.append(Path.cwd())
    candidates.extend(Path(__file__).resolve().parents)

    for candidate in candidates:
        if (candidate / "reference" / "knowledge").is_dir() and (
            candidate / "pyproject.toml"
        ).exists():
            return str(candidate)
    return str(Path(__file__).resolve().parents[3])


ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = _find_project_root()
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

# Raw geology data (referenced, not copied). Default: project-root folder.
RAW_ROOT = os.environ.get("GEO_RAW_ROOT", os.path.join(ROOT, "geology_reports"))


def raw_path(*parts) -> str:
    return os.path.join(RAW_ROOT, *parts)


def ensure_dirs():
    for d in (DATABASE, OUTPUTS, PROC, PDF_ASSETS, BOUNDARIES, QA, DEMOS):
        os.makedirs(d, exist_ok=True)
