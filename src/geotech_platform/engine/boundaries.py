"""
Region boundary derivation & review (addresses feedback #1).

How the per-region boundary is determined, and how to review it:

  * actual_data_bbox : the exact min/max lon/lat of the geo_A polygons in the
    sheet's shapefile (what the data really covers). Computed here from geometry.
  * nominal_quadrangle: the official GSJ 1:50,000 map frame. The Japanese 1:50k
    grid divides each 1:200,000 sheet (1deg lon x 40' lat) into 4x4 tiles, so a
    1:50k quad spans 15' lon (0.25 deg) x 10' lat (1/6 deg). We snap the data
    bbox to that grid to recover the intended frame.

The previous version reported only the data bbox (slightly inset from the frame),
which is why region extents looked off. For point->region assignment we use the
nominal quadrangle (so any point inside the published sheet maps to that sheet);
the actual polygon geometry still decides the specific geology unit.

This module writes a REVIEWABLE record (reference + outputs) so the boundaries can
be inspected and corrected by hand.
"""

from __future__ import annotations

import os

import yaml

from . import config
from . import map_config as MC
from .shapefile_io import read_shp

QUAD_LON = 0.25  # 15 arc-minutes
QUAD_LAT = 1.0 / 6.0  # 10 arc-minutes


def _snap_quad(bbox):
    """Snap each corner of the data bbox to the nearest GSJ 1:50k grid line.

    The data extent spans almost exactly one quad but can overhang the neatline
    by a few hundred metres, so we snap each corner to its nearest grid multiple
    (not force-contain, which would jump a whole tile)."""
    xmin, ymin, xmax, ymax = bbox
    lon0 = round(xmin / QUAD_LON) * QUAD_LON
    lon1 = round(xmax / QUAD_LON) * QUAD_LON
    lat0 = round(ymin / QUAD_LAT) * QUAD_LAT
    lat1 = round(ymax / QUAD_LAT) * QUAD_LAT
    return (round(lon0, 6), round(lat0, 6), round(lon1, 6), round(lat1, 6))


def compute():
    regions = []
    for m in MC.MAPS:
        shp = MC.raw_path(m["shp_dir"], m["geo_a"])
        shapes = read_shp(shp)
        xs, ys = [], []
        for sh in shapes:
            for ring in sh.parts:
                for x, y in ring:
                    xs.append(x)
                    ys.append(y)
        data_bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)
        nominal = _snap_quad(data_bbox)
        regions.append(
            {
                "region": m["region"],
                "map_name_en": m["map_name_en"],
                "map_name_ja": m["map_name_ja"],
                "year": m["year"],
                "crs": "EPSG:4612 (JGD2000 geographic, lon/lat)",
                "n_polygons": len(shapes),
                "actual_data_bbox": {
                    "lon_min": round(data_bbox[0], 6),
                    "lat_min": round(data_bbox[1], 6),
                    "lon_max": round(data_bbox[2], 6),
                    "lat_max": round(data_bbox[3], 6),
                },
                "nominal_quadrangle": {
                    "lon_min": nominal[0],
                    "lat_min": nominal[1],
                    "lon_max": nominal[2],
                    "lat_max": nominal[3],
                    "span_deg": {"lon": QUAD_LON, "lat": round(QUAD_LAT, 6)},
                },
                "review_status": "auto-derived (please verify against the GSJ sheet frame)",
            }
        )
    return regions


def region_for_point(lon, lat, regions=None):
    """Assign a point to a region using the NOMINAL quadrangle frames."""
    regions = regions or load()
    hits = []
    for r in regions:
        q = r["nominal_quadrangle"]
        if q["lon_min"] <= lon <= q["lon_max"] and q["lat_min"] <= lat <= q["lat_max"]:
            hits.append(r["region"])
    return hits


def write(regions):
    config.ensure_dirs()
    doc = {
        "meta": {
            "version": "0.1.0",
            "derivation": "actual_data_bbox from geo_A polygons; nominal_quadrangle "
            "snapped to the GSJ 1:50,000 grid (0.25 deg lon x 1/6 deg lat).",
            "review_required": True,
            "note": "Edit nominal_quadrangle here if it does not match the official "
            "sheet frame; region_for_point() uses these values.",
        },
        "regions": regions,
    }
    out_yaml = os.path.join(config.REFERENCE, "region_boundaries.yaml")
    with open(out_yaml, "w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)

    # human review markdown
    lines = [
        "# Region boundaries — review sheet\n",
        "Both the **actual data extent** (from the polygons) and the **nominal "
        "1:50,000 quadrangle frame** are listed. Point→region assignment uses the "
        "nominal frame. Verify these against the official GSJ sheets and correct "
        "`reference/region_boundaries.yaml` if needed.\n",
        "| Region | Map | Data lon range | Data lat range | Nominal lon | Nominal lat |",
        "|---|---|---|---|---|---|",
    ]
    for r in regions:
        d = r["actual_data_bbox"]
        q = r["nominal_quadrangle"]
        lines.append(
            f"| {r['region']} | {r['map_name_en']} ({r['map_name_ja']}) | "
            f"{d['lon_min']}–{d['lon_max']} | {d['lat_min']}–{d['lat_max']} | "
            f"{q['lon_min']}–{q['lon_max']} | {q['lat_min']}–{q['lat_max']} |"
        )
    lines += [
        "",
        "Each GSJ 1:50,000 quadrangle spans 15′ longitude (0.25°) × 10′ latitude "
        "(≈0.16667°). The three sheets tile together: Hachioji (NW) and "
        "Tokyo-Seinambu (NE) share the northern row; Yokohama sits south of "
        "Tokyo-Seinambu.\n",
    ]
    with open(
        os.path.join(config.BOUNDARIES, "region_boundaries_review.md"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write("\n".join(lines))
    return out_yaml


def load():
    p = os.path.join(config.REFERENCE, "region_boundaries.yaml")
    if not os.path.exists(p):
        return compute()
    with open(p, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["regions"]


if __name__ == "__main__":
    regs = compute()
    write(regs)
    for r in regs:
        d = r["actual_data_bbox"]
        q = r["nominal_quadrangle"]
        print(
            f"{r['region']} {r['map_name_en']:20s} data lon {d['lon_min']}-{d['lon_max']} "
            f"lat {d['lat_min']}-{d['lat_max']} | nominal lon {q['lon_min']}-{q['lon_max']} "
            f"lat {q['lat_min']}-{q['lat_max']}"
        )
