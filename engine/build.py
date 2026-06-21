"""
v2 build orchestrator.

Produces the query-ready geotechnical geology database AND the evidence-linked
inference chains that the drill-down app exposes:

  outputs/processed/geology_features.csv          normalized geology (faithful)
  outputs/processed/geotech_features.csv          geology + geotech interpretation
  outputs/processed/inference_chains.json          full L1->L4 chain per unit
  outputs/processed/geology_unit_cards.json/csv    unit cards (with chain summary)
  database/tokyo_geotech_v2.gpkg                    geology + geotech polygon layers
  database/tokyo_geotech_v2.sqlite                  attribute mirror
  outputs/boundaries/region_boundaries(.yaml/.md)   reviewable boundaries
  outputs/pdf_assets/...                            figure index (via pdf_assets)

Raw data is only READ (referenced from sample_geology_reports via config).
"""

from __future__ import annotations

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config
import map_config as MC
import geo_utils as G
from shapefile_io import read_shapefile, SHAPE_TYPES
from inference import InferenceEngine
import boundaries as B
import io_utils as IO


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- {ts}  {msg}"
    print(line)
    with open(config.BUILD_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _first(rec, fields):
    for f in fields:
        v = rec.get(f)
        if v not in (None, "", 0):
            return str(v).strip()
    return ""


def _join(rec, fields):
    out = []
    for f in fields:
        v = rec.get(f)
        if v not in (None, "", 0) and str(v).strip() not in out:
            out.append(str(v).strip())
    return " / ".join(out)


def normalize(rec, prof):
    return {
        "raw_unit_code": str(rec.get(prof["symbol_field"]) or "").strip()
                         or str(rec.get(prof["code_field"]) or "").strip(),
        "raw_unit_name_ja": _first(rec, prof["name_fields_ja"]),
        "raw_unit_name_en": _first(rec, prof["name_fields_en"]),
        "raw_lithology": _join(rec, prof["litho_fields_ja"]),
        "raw_lithology_en": _join(rec, prof["litho_fields_en"]),
        "raw_age": _join(rec, prof["age_fields_ja"]),
        "raw_age_en": _join(rec, prof["age_fields_en"]),
    }


def centroid(parts):
    pts = [p for ring in parts for p in ring]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else (0, 0)


def build():
    config.ensure_dirs()
    with open(config.BUILD_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n## v2 build run {datetime.datetime.now().isoformat(timespec='seconds')}\n")

    # boundaries (feedback #1)
    regions = B.compute(); B.write(regions)
    log(f"Boundaries: derived nominal quadrangles for {len(regions)} sheets (reviewable).")

    eng = InferenceEngine()

    # which PDF figures exist per region (for source-evidence linking)
    region_assets = _assets_by_region()

    features = []
    geom = {}
    unit_cards = {}
    for m in MC.MAPS:
        prof = MC.get_profile(m["profile"])
        shp = MC.raw_path(m["shp_dir"], m["geo_a"])
        shapes, recs, crs, stype = read_shapefile(shp)
        n = 0
        for i, (sh, rec) in enumerate(zip(shapes, recs)):
            if not sh.parts:
                continue
            norm = normalize(rec, prof)
            fid = f"{m['region']}_A_{i:04d}"
            clon, clat = centroid(sh.parts)
            unit = dict(norm, source_region=m["region"])
            # unit card keyed by (region, code, name) - infer once per distinct unit
            key = (m["region"], norm["raw_unit_code"], norm["raw_unit_name_ja"])
            if key not in unit_cards:
                asset_ids = [a["asset_id"] for a in region_assets.get(m["region"], [])][:12]
                result = eng.infer(unit, asset_refs=asset_ids)
                unit_cards[key] = _make_card(m, norm, result, region_assets)
            card = unit_cards[key]
            feat = {
                "feature_id": fid, "source_region": m["region"],
                "source_map_name": f"{m['map_name_en']} ({m['map_name_ja']})",
                "source_file": os.path.relpath(shp, config.ROOT),
                "geometry_area_m2": round(G.polygon_area_m2(sh.parts), 1),
                "centroid_lon": round(clon, 6), "centroid_lat": round(clat, 6),
                **norm,
                "source_attribute_json": json.dumps({k: v for k, v in rec.items() if k != "_deleted"},
                                                    ensure_ascii=False),
                "geology_unit_card_id": card["geology_unit_card_id"],
                "engineering_material_family": card["engineering_material_family"],
                "engineering_ground_type": card["engineering_ground_type"],
                "geotech_term_ja": card["geotech_term_ja"],
                "geotech_term_en": card["geotech_term_en"],
                "geotechnical_risk_flags": card["risk_flags"],
                "interpretation_confidence": card["overall_confidence"],
                "needs_manual_review": card["needs_manual_review"],
            }
            features.append(feat)
            geom[fid] = sh.parts
            n += 1
        log(f"{m['region']} {m['map_name_en']}: {n} polygons normalized + inferred (CRS {crs}).")

    cards = list(unit_cards.values())
    log(f"Inference: {len(cards)} distinct unit cards from {len(features)} polygons.")

    # ----- write processed outputs -----
    feat_cols = ["feature_id", "source_region", "source_map_name", "source_file",
                 "geometry_area_m2", "centroid_lon", "centroid_lat", "raw_unit_code",
                 "raw_unit_name_ja", "raw_unit_name_en", "raw_lithology", "raw_age",
                 "engineering_material_family", "engineering_ground_type", "geotech_term_ja",
                 "geotech_term_en", "interpretation_confidence", "needs_manual_review",
                 "geology_unit_card_id"]
    IO.write_csv(os.path.join(config.PROC, "geology_features.csv"),
                 [{k: f.get(k) for k in feat_cols[:12]} for f in features], feat_cols[:12])
    IO.write_csv(os.path.join(config.PROC, "geotech_features.csv"),
                 [{k: f.get(k) for k in feat_cols} | {"geotechnical_risk_flags": f["geotechnical_risk_flags"]}
                  for f in features])
    IO.write_json(os.path.join(config.PROC, "inference_chains.json"), cards)
    IO.write_json(os.path.join(config.PROC, "geology_unit_cards.json"),
                  [_card_summary(c) for c in cards])
    IO.write_csv(os.path.join(config.PROC, "geology_unit_cards.csv"),
                 [_card_flat(c) for c in cards])
    manual = [_card_flat(c) for c in cards if c["needs_manual_review"]]
    IO.write_csv(os.path.join(config.PROC, "manual_review_required.csv"), manual)
    log(f"Wrote processed CSV/JSON; {len(manual)} unit cards flagged for manual review.")

    # ----- GeoPackage + SQLite -----
    from gpkg_writer import write_gpkg
    norm_rows, geotech_rows = [], []
    for f in features:
        base = {k: f.get(k) for k in ("feature_id", "source_region", "raw_unit_code",
                                      "raw_unit_name_ja", "raw_unit_name_en", "raw_lithology",
                                      "raw_age", "geometry_area_m2")}
        base["_parts"] = geom[f["feature_id"]]
        norm_rows.append(base)
        gt = {k: f.get(k) for k in ("feature_id", "source_region", "raw_unit_name_ja",
                                    "engineering_material_family", "engineering_ground_type",
                                    "geotech_term_ja", "geotech_term_en",
                                    "interpretation_confidence", "needs_manual_review",
                                    "geology_unit_card_id")}
        gt["risk_flags"] = ";".join(f["geotechnical_risk_flags"])
        gt["_parts"] = geom[f["feature_id"]]
        geotech_rows.append(gt)
    write_gpkg(os.path.join(config.DATABASE, "tokyo_geotech_v2.gpkg"),
               {"geology_features": {"rows": norm_rows},
                "geotech_features": {"rows": geotech_rows}}, srs_id=4612)
    IO.write_sqlite(os.path.join(config.DATABASE, "tokyo_geotech_v2.sqlite"), {
        "geotech_features": [{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                              for k, v in f.items()} for f in features],
        "geology_unit_cards": [_card_flat(c) for c in cards],
        "manual_review_required": manual,
    })
    log("Wrote GeoPackage (tokyo_geotech_v2.gpkg) + SQLite mirror.")

    # ----- PDF assets (figures) -----
    import pdf_assets
    pa = pdf_assets.build()
    log(f"PDF assets: extracted {pa['images']} figures, {pa.get('previews_png',0)} previews; "
        f"see outputs/pdf_assets/. (08063 scanned/JBIG2 & 08074_D non-standard JPX flagged.)")

    summary = {"features": len(features), "unit_cards": len(cards),
               "manual_review": len(manual), "pdf_figures": pa["images"]}
    log(f"v2 BUILD COMPLETE: {json.dumps(summary)}")
    return summary


def _assets_by_region():
    import csv as _csv
    p = os.path.join(config.PDF_ASSETS, "pdf_asset_index.csv")
    out = {}
    if os.path.exists(p):
        for r in _csv.DictReader(open(p, encoding="utf-8-sig")):
            out.setdefault(r["source_region"], []).append(r)
    return out


def _make_card(m, norm, result, region_assets):
    n = len(globals().setdefault("_card_seq", []))
    globals()["_card_seq"].append(1)
    cid = f"UC2_{m['region']}_{(norm['raw_unit_code'] or 'NA')}_{n:03d}"
    return {
        "geology_unit_card_id": cid,
        "source_region": m["region"],
        "raw_unit_code": norm["raw_unit_code"],
        "raw_unit_name_ja": norm["raw_unit_name_ja"],
        "raw_unit_name_en": norm["raw_unit_name_en"],
        "raw_lithology": norm["raw_lithology"],
        "raw_age": norm["raw_age"],
        "engineering_material_family": result["engineering_material_family"],
        "engineering_ground_type": result["engineering_ground_type"],
        "geotech_term_ja": result["geotech_term_ja"],
        "geotech_term_en": result["geotech_term_en"],
        "overall_confidence": result["overall_confidence"],
        "needs_manual_review": result["needs_manual_review"],
        "risk_flags": result["risk_flags"],
        "chain": result["chain"],
        "source_evidence": result["source_evidence"],
    }


def _card_summary(c):
    return {k: c[k] for k in ("geology_unit_card_id", "source_region", "raw_unit_code",
                              "raw_unit_name_ja", "raw_unit_name_en", "raw_lithology", "raw_age",
                              "engineering_material_family", "engineering_ground_type",
                              "geotech_term_ja", "geotech_term_en", "overall_confidence",
                              "needs_manual_review", "risk_flags", "chain", "source_evidence")}


def _card_flat(c):
    return {
        "geology_unit_card_id": c["geology_unit_card_id"], "source_region": c["source_region"],
        "raw_unit_code": c["raw_unit_code"], "raw_unit_name_ja": c["raw_unit_name_ja"],
        "raw_unit_name_en": c["raw_unit_name_en"], "raw_lithology": c["raw_lithology"],
        "raw_age": c["raw_age"], "engineering_ground_type": c["engineering_ground_type"],
        "geotech_term_ja": c["geotech_term_ja"], "overall_confidence": c["overall_confidence"],
        "risk_flags": ";".join(c["risk_flags"]), "needs_manual_review": c["needs_manual_review"],
        "geology_chain": " -> ".join(s["knowledge_ref"] or s["step"] for s in c["chain"]),
    }


if __name__ == "__main__":
    build()
