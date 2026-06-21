"""
Layered geology -> geotech inference engine (the v2 backend).

Produces a transparent, evidence-linked INFERENCE CHAIN for a geology unit:

  L1  Geology identification   : raw unit/lithology/age  -> geological material,
                                 lithology, depositional environment, consolidation
  L2  Geotech translation      : geological character     -> engineering ground type
                                 + the terms geotech engineers use
  L3  Indicative properties    : ground type              -> screening property bands
                                 (mechanical / chemical) WITH provenance (non-design)
  L4  Considerations & advice  : ground type + properties -> per-application screening
                                 considerations + recommended investigation

Each step records inputs, the knowledge row/section used, outputs, evidence
(source attributes + citations + optional PDF asset ids), and a confidence.
The chain is what the app drills into, layer by layer, down to source evidence.

Design rules:
  * Conservative & explainable. Ambiguity -> lower confidence / manual review.
  * NEVER emits design parameters. L3 bands are screening-only (design_use:false).
"""

from __future__ import annotations

import csv
import os
import yaml

import config

KB = config.KNOWLEDGE
REF = config.REFERENCE

_CONF_ORDER = ["high", "medium", "low", "very_low"]


def _min_conf(*levels):
    idx = max((_CONF_ORDER.index(l) for l in levels if l in _CONF_ORDER), default=3)
    return _CONF_ORDER[idx]


def _load_csv(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if not r.get("term_id", r.get("map_id", "x")).startswith("#")]


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class InferenceEngine:
    def __init__(self):
        self.L1 = sorted(_load_csv(os.path.join(KB, "L1_geology_terms.csv")),
                         key=lambda r: int(r["priority"]))
        self.L2 = sorted(_load_csv(os.path.join(KB, "L2_geology_to_geotech.csv")),
                         key=lambda r: int(r["priority"]))
        self.L3 = _load_yaml(os.path.join(KB, "L3_property_ranges.yaml"))["ground_types"]
        self.L4 = _load_yaml(os.path.join(KB, "L4_recommendations.yaml"))["ground_types"]
        self.sources = _load_yaml(os.path.join(KB, "sources.yaml"))["sources"]
        self.ontology = _load_yaml(os.path.join(REF, "geotech_ontology.yaml"))["classes"]
        self.risk = _load_yaml(os.path.join(REF, "engineering_risk_dictionary.yaml"))["flags"]
        self.rules = _load_yaml(os.path.join(REF, "geology_to_geotech_rules.yaml"))["rules"]

    # ---------------------------------------------------------------- L1 ----
    def step_geology(self, unit):
        name = str(unit.get("raw_unit_name_ja") or "")
        litho = str(unit.get("raw_lithology") or "")
        age = str(unit.get("raw_age") or "")
        matched = None
        matched_kw = None
        where = None
        for row in self.L1:
            kws = [k.strip() for k in (row.get("match_keywords_ja") or "").split(";") if k.strip()]
            hay = name if row["match_on"] == "name" else litho
            for kw in kws:
                if kw and kw in hay:
                    matched, matched_kw, where = row, kw, row["match_on"]
                    break
            if matched:
                break
        if matched is None:
            # try lithology on the name match rows too (last resort: scan all on litho+name)
            for row in self.L1:
                kws = [k.strip() for k in (row.get("match_keywords_ja") or "").split(";") if k.strip()]
                hay = name + " " + litho
                for kw in kws:
                    if kw and kw in hay:
                        matched, matched_kw, where = row, kw, "name+litho"
                        break
                if matched:
                    break

        if matched is None:
            return {
                "step": "L1_geology",
                "title_en": "Geology identification", "title_ja": "地質の同定",
                "inputs": {"raw_unit_name_ja": name, "raw_lithology": litho, "raw_age": age},
                "knowledge_ref": None,
                "outputs": {"geological_material": "unknown"},
                "evidence": ["No L1 geology term matched the unit name or lithology."],
                "sources": [], "confidence": "very_low",
            }

        conf = "high" if where == "name" else ("medium" if where == "litho" else "low")
        out = {
            "geological_material": matched["geological_material"],
            "primary_lithology_ja": matched["primary_lithology_ja"],
            "primary_lithology_en": matched["primary_lithology_en"],
            "grain_or_rock": matched["grain_or_rock"],
            "depositional_environment_ja": matched["depositional_environment_ja"],
            "depositional_environment_en": matched["depositional_environment_en"],
            "typical_consolidation": matched["typical_consolidation"],
            "formation_group_ja": matched.get("formation_group_ja", ""),
            "stratigraphic_note_en": matched["stratigraphic_note_en"],
        }
        evidence = [f"Matched '{matched_kw}' in {where} -> {matched['term_id']} "
                    f"({matched['primary_lithology_en']}, {matched['typical_consolidation']})."]

        # --- age refinement -------------------------------------------------
        # A geology map's age is a strong geotech signal: pre-Holocene granular
        # deposits are overconsolidated ("diluvial"), not soft Holocene alluvium.
        # Applied only to generic lithology fallbacks so named units keep their
        # curated mapping. Transparent: recorded as its own evidence line.
        old_markers = ["更新世", "鮮新世", "中新世", "Pleistocene", "Pliocene", "Miocene"]
        is_old = any(mk in age for mk in old_markers)
        if matched["term_id"] in ("L1_litho_gravel", "L1_litho_sand") and is_old:
            out["grain_or_rock"] = "terrace_gravel"
            out["typical_consolidation"] = "overconsolidated (pre-Holocene)"
            out["age_refined"] = True
            evidence.append(
                f"Age refinement: '{age}' is pre-Holocene -> treated as overconsolidated "
                f"(diluvial) granular ground rather than soft Holocene alluvium.")
            conf = "medium"
        elif matched["term_id"] == "L1_litho_mud_silt" and is_old:
            out["typical_consolidation"] = "overconsolidated (pre-Holocene)"
            out["age_refined"] = True
            evidence.append(
                f"Age refinement: '{age}' is pre-Holocene -> fine soil likely "
                f"overconsolidated/stiff rather than soft normally-consolidated clay.")

        return {
            "step": "L1_geology",
            "title_en": "Geology identification", "title_ja": "地質の同定",
            "inputs": {"raw_unit_name_ja": name, "raw_lithology": litho, "raw_age": age},
            "knowledge_ref": f"L1_geology_terms.csv :: {matched['term_id']}",
            "matched_keyword": matched_kw, "matched_field": where,
            "outputs": out,
            "evidence": evidence,
            "sources": self._src(matched.get("source_ref")),
            "confidence": conf,
        }

    # ---------------------------------------------------------------- L2 ----
    def step_translate(self, geol_out):
        gm = geol_out.get("geological_material", "unknown")
        gor = geol_out.get("grain_or_rock", "")
        cons = geol_out.get("typical_consolidation", "")
        matched = None
        for row in self.L2:
            if row["match_geological_material"] != gm:
                continue
            mg = row["match_grain_or_rock"]
            if mg == "*" or mg == gor:
                matched = row
                break
        if matched is None:
            return {
                "step": "L2_geotech_translation",
                "title_en": "Geotechnical translation", "title_ja": "地盤工学への翻訳",
                "inputs": {"geological_material": gm, "grain_or_rock": gor, "consolidation": cons},
                "knowledge_ref": None,
                "outputs": {"engineering_ground_type": "mixed_or_uncertain_geology",
                            "engineering_material_family": "mixed_or_unknown"},
                "evidence": ["No L2 mapping matched; defaulted to uncertain geology."],
                "sources": [], "confidence": "very_low",
            }
        return {
            "step": "L2_geotech_translation",
            "title_en": "Geotechnical translation", "title_ja": "地盤工学への翻訳",
            "inputs": {"geological_material": gm, "grain_or_rock": gor, "consolidation": cons},
            "knowledge_ref": f"L2_geology_to_geotech.csv :: {matched['map_id']}",
            "outputs": {
                "engineering_material_family": matched["engineering_material_family"],
                "engineering_ground_type": matched["engineering_ground_type"],
                "geotech_term_ja": matched["geotech_term_ja"],
                "geotech_term_en": matched["geotech_term_en"],
                "geotech_synonyms_ja": matched.get("geotech_synonyms_ja", ""),
            },
            "evidence": [matched["rationale_en"]],
            "sources": self._src(matched.get("source_ref")),
            "confidence": "high" if matched["match_grain_or_rock"] != "*" else "medium",
        }

    # ---------------------------------------------------------------- L3 ----
    def step_properties(self, ground_type):
        p = self.L3.get(ground_type)
        if not p:
            return {
                "step": "L3_indicative_properties",
                "title_en": "Indicative properties (screening, non-design)",
                "title_ja": "想定物性（スクリーニング・非設計値）",
                "inputs": {"engineering_ground_type": ground_type},
                "knowledge_ref": None, "outputs": {}, "evidence": [], "sources": [],
                "confidence": "very_low",
            }
        return {
            "step": "L3_indicative_properties",
            "title_en": "Indicative properties (screening, non-design)",
            "title_ja": "想定物性（スクリーニング・非設計値）",
            "inputs": {"engineering_ground_type": ground_type},
            "knowledge_ref": f"L3_property_ranges.yaml :: {ground_type}",
            "outputs": {
                "summary_en": p.get("summary_en", ""),
                "mechanical": p.get("mechanical", {}),
                "chemical": p.get("chemical", {}),
                "key_concerns_en": p.get("key_concerns_en", []),
                "design_use": p.get("design_use", False),
            },
            "evidence": ["Indicative screening bands; NOT design values (design_use: false)."],
            "sources": self._src(p.get("source_ref")),
            "confidence": "medium",  # property bands are indicative by nature
        }

    # ---------------------------------------------------------------- L4 ----
    def step_recommendations(self, ground_type):
        r = self.L4.get(ground_type, {})
        return {
            "step": "L4_considerations",
            "title_en": "Geotechnical considerations & investigation",
            "title_ja": "地盤工学的留意点と推奨調査",
            "inputs": {"engineering_ground_type": ground_type},
            "knowledge_ref": f"L4_recommendations.yaml :: {ground_type}",
            "outputs": {
                "applications": r.get("applications", {}),
                "recommended_investigation": r.get("recommended_investigation", []),
                "residual_uncertainty": r.get("residual_uncertainty", ""),
            },
            "evidence": ["Conditional screening considerations ('may be relevant -> investigate'); not design conclusions."],
            "sources": [], "confidence": "medium",
        }

    # ------------------------------------------------------------- driver ---
    def infer(self, unit, asset_refs=None):
        s1 = self.step_geology(unit)
        s2 = self.step_translate(s1["outputs"])
        gt = s2["outputs"].get("engineering_ground_type", "mixed_or_uncertain_geology")
        s3 = self.step_properties(gt)
        s4 = self.step_recommendations(gt)

        # risk flags from the ontology rules (reuse the keyword rules for flags)
        risk_flags = self._risk_flags(unit, gt)
        overall_conf = _min_conf(s1["confidence"], s2["confidence"])
        needs_review = overall_conf in ("low", "very_low") or gt == "mixed_or_uncertain_geology" \
            or not unit.get("raw_unit_name_ja")

        # attach source-evidence pointers (raw attributes + optional pdf assets)
        source_evidence = {
            "raw_attributes": {k: unit.get(k) for k in
                               ("raw_unit_code", "raw_unit_name_ja", "raw_unit_name_en",
                                "raw_lithology", "raw_age", "source_region")},
            "pdf_asset_ids": asset_refs or [],
        }

        return {
            "engineering_ground_type": gt,
            "engineering_material_family": s2["outputs"].get("engineering_material_family"),
            "geotech_term_ja": s2["outputs"].get("geotech_term_ja"),
            "geotech_term_en": s2["outputs"].get("geotech_term_en"),
            "overall_confidence": overall_conf,
            "needs_manual_review": needs_review,
            "risk_flags": risk_flags,
            "chain": [s1, s2, s3, s4],
            "source_evidence": source_evidence,
        }

    # -------------------------------------------------------------- utils ---
    def _risk_flags(self, unit, ground_type):
        # map ground type -> a representative rule's risk flags (keyword rules)
        gt_to_rule = {
            "artificial_fill_reclaimed_ground": "R01_artificial_fill",
            "young_unconsolidated_soil": "R02_organic_swamp_soft",
            "alluvial_lowland_deposits": "R03_alluvium",
            "volcanic_ash_loam": "R04_loam_volcanic_ash",
            "terrace_deposits": "R05_terrace",
            "pyroclastic_tuffaceous_ground": "R06_tuff_pyroclastic",
            "weak_sedimentary_rock": "R07_weak_sedimentary_rock",
            "hard_crystalline_rock": "R08_hard_crystalline_rock",
            "fault_fracture_zone": "R09_fault_fracture",
            "mixed_or_uncertain_geology": "R99_unmatched",
        }
        rid = gt_to_rule.get(ground_type)
        for r in self.rules:
            if r["rule_id"] == rid:
                return r.get("risk_flags", [])
        return []

    def _src(self, refs):
        if not refs:
            return []
        if isinstance(refs, str):
            refs = [r.strip() for r in refs.split(";") if r.strip()]
        out = []
        for rid in refs:
            s = self.sources.get(rid)
            if s:
                out.append({"id": rid, "title": s.get("title"), "url": s.get("url", ""),
                            "tier": s.get("tier")})
            else:
                out.append({"id": rid, "title": rid, "url": "", "tier": "unknown"})
        return out


if __name__ == "__main__":
    eng = InferenceEngine()
    tests = [
        {"raw_unit_name_ja": "小山田層", "raw_lithology": "礫，砂及びシルト", "raw_age": "後期鮮新世-前期更新世", "source_region": "08062"},
        {"raw_unit_name_ja": "立川ローム層", "raw_lithology": "火山灰", "raw_age": "後期更新世", "source_region": "08063"},
        {"raw_unit_name_ja": "沖積層", "raw_lithology": "泥・砂及び礫", "raw_age": "完新世", "source_region": "08074"},
        {"raw_unit_name_ja": "埋立土", "raw_lithology": "砂及び泥", "raw_age": "完新世", "source_region": "08074"},
        {"raw_unit_name_ja": "柿生層", "raw_lithology": "泥岩", "raw_age": "前期更新世", "source_region": "08063"},
    ]
    for t in tests:
        r = eng.infer(t)
        print(f"\n=== {t['raw_unit_name_ja']} -> {r['engineering_ground_type']} "
              f"(conf {r['overall_confidence']}) ===")
        for s in r["chain"]:
            print(f"  [{s['step']}] {s['title_en']} | conf={s['confidence']} | {s['knowledge_ref']}")
