"""Command-line entry points for the geotech platform."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path


def build() -> int:
    """Build the platform outputs from the configured raw geology data."""
    from .engine import build as build_engine

    summary = build_engine.build()
    print("\nDone:", summary)
    print("Next: uv run geotech-app")
    return 0


def query() -> int:
    """Query the geotechnical interpretation at a point."""
    parser = argparse.ArgumentParser(
        prog="geotech-query",
        description="Return the geology unit and full inference chain at a latitude/longitude point.",
    )
    parser.add_argument("lat", type=float, help="Latitude in decimal degrees.")
    parser.add_argument("lon", type=float, help="Longitude in decimal degrees.")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help="Optionally truncate the JSON output to this many characters.",
    )
    args = parser.parse_args()

    from .engine import config
    from .engine.query import query_point

    try:
        result = query_point(args.lat, args.lon)
    except FileNotFoundError as exc:
        missing_path = exc.filename or str(exc)
        print(f"Required data file not found: {missing_path}", file=sys.stderr)
        print(
            "Run `uv run geotech-build` after placing raw GSJ data at "
            f"{config.RAW_ROOT}, or set GEO_RAW_ROOT to the raw data directory.",
            file=sys.stderr,
        )
        return 1

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.max_chars is not None:
        output = output[: args.max_chars]
    print(output)
    return 0


def app() -> int:
    """Launch the Streamlit drill-down UI."""
    if find_spec("streamlit") is None:
        print(
            "Streamlit is not installed. Run `uv sync` to install project dependencies.",
            file=sys.stderr,
        )
        return 1

    app_path = Path(__file__).resolve().parent / "app" / "streamlit_app.py"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)]
        )
    except KeyboardInterrupt:
        return 130
    return result.returncode
