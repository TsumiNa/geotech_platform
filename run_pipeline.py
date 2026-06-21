#!/usr/bin/env python3
"""
One-command build for the v2 platform.

    python run_pipeline.py

Reads raw GSJ data from ../sample_geology_reports (override with GEO_RAW_ROOT),
builds boundaries, normalized geology, the layered inference chains, the
GeoPackage/SQLite database, and the PDF figure index. Raw data is only READ.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))

import build  # noqa

if __name__ == "__main__":
    summary = build.build()
    print("\nDone:", summary)
    print("Next: streamlit run app/streamlit_app.py")
