"""
Point query for v2: returns the geology unit at a point AND its full inference
chain (so the app can drill from conclusion down to source evidence).

Geometry is read from the raw shapefiles (exact polygons); attributes + chains
come from the processed outputs. Region assignment uses the reviewable nominal
quadrangles (engine/boundaries.py).
"""

from __future__ import annotations

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config
import map_config as MC
import geo_utils as G
import boundaries as B
from shapefile_io import read_shapefile

DISCLAIMER_EN = ("Screening-level only: plausible ground-condition hypotheses, risk "
                 "flags, uncertainty and recommended investigation. NOT design values.")
DISCLAIMER_JA = ("机上スクリーニング用：想定地盤条件・リスク・不確実性・推奨調査のみ。"
                 "設計値ではありません。")


class V2Index:
    def __init__(self):
        self.features = []
        self.cards = {}
        self._load()

    def _load(self):
        # chains/cards
        chains = json.load(open(os.path.join(config.PROC, "inference_chains.json"), encoding="utf-8"))
        self.cards = {c["geology_unit_card_id"]: c for c in chains}
        # feature attributes
        attrs = {}
        with open(os.path.join(config.PROC, "geotech_features.csv"), encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                attrs[r["feature_id"]] = r
        # geometry
        for m in MC.MAPS:
            shp = MC.raw_path(m["shp_dir"], m["geo_a"])
            shapes, _, _, _ = read_shapefile(shp)
            for i, sh in enumerate(shapes):
                fid = f"{m['region']}_A_{i:04d}"
                if fid in attrs and sh.parts:
                    a = dict(attrs[fid]); a["parts"] = sh.parts
                    a["bbox"] = G.bbox_of_parts(sh.parts)
                    self.features.append(a)
        self.regions = B.load()

    def containing(self, lon, lat):
        for f in self.features:
            if G.point_in_bbox(lon, lat, f["bbox"]) and G.point_in_polygon(lon, lat, f["parts"]):
                return f
        return None


_IDX = None


def get_index():
    global _IDX
    if _IDX is None:
        _IDX = V2Index()
    return _IDX


def query_point(lat, lon):
    idx = get_index()
    region_hits = B.region_for_point(lon, lat, idx.regions)
    f = idx.containing(lon, lat)
    out = {
        "query": {"lat": lat, "lon": lon},
        "region_by_quadrangle": region_hits,
        "disclaimer_en": DISCLAIMER_EN, "disclaimer_ja": DISCLAIMER_JA,
        "found": bool(f),
    }
    if not f:
        out["message_en"] = ("Inside sheet %s but no polygon at point" % region_hits) if region_hits \
            else "Outside the mapped extent of the three sheets."
        return out
    card = idx.cards.get(f.get("geology_unit_card_id"))
    try:
        dist = round(G.distance_to_boundary_m(lon, lat, f["parts"]), 1)
    except Exception:
        dist = None
    out.update({
        "feature_id": f["feature_id"],
        "source_region": f["source_region"],
        "distance_to_boundary_m": dist,
        "raw": {k: f.get(k) for k in ("raw_unit_code", "raw_unit_name_ja", "raw_unit_name_en",
                                      "raw_lithology", "raw_age")},
        "ground_type": f.get("engineering_ground_type"),
        "geotech_term_ja": f.get("geotech_term_ja"),
        "geotech_term_en": f.get("geotech_term_en"),
        "confidence": f.get("interpretation_confidence"),
        "unit_card_id": f.get("geology_unit_card_id"),
        "chain": card["chain"] if card else [],
        "risk_flags": card["risk_flags"] if card else [],
        "source_evidence": card["source_evidence"] if card else {},
    })
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("lat", type=float); ap.add_argument("lon", type=float)
    a = ap.parse_args()
    print(json.dumps(query_point(a.lat, a.lon), ensure_ascii=False, indent=2)[:1500])
