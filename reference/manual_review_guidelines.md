# Manual Review Guidelines

This prototype turns raw GSJ 1:50,000 geology into **screening-level geotechnical
hypotheses**. Automated interpretation is deliberately conservative and leaves a
clear human-review pathway. This document explains *when* a unit is flagged for
review and *how* a reviewer should act.

## Guiding principle

The pipeline never produces final design parameters. Outputs are *plausible
ground-condition hypotheses, risk flags, uncertainty, and recommended
investigation*. A geotechnical engineer remains responsible for interpretation
and for any design decision.

## When the pipeline flags a unit for manual review

A geology unit / feature is flagged (`needs_manual_review = true`) when any of:

1. **Missing unit name** — no raw unit name in the source attributes.
2. **Unclear lithology** — lithology field is empty or non-specific.
3. **Unclear age** — stratigraphic age missing or ambiguous.
4. **Multiple plausible classes** — more than one ontology class could apply
   (e.g. tuffaceous sandstone could be pyroclastic or weak sedimentary rock).
5. **Context-dependent interpretation** — behaviour depends on depth, thickness
   or groundwater that the map cannot resolve.
6. **No PDF/explanation evidence** — the explanatory sheet could not be text-
   extracted (scanned / CID-font PDFs), so the unit relies on attributes only.
7. **Low confidence** — the matched rule produced `low` or `very_low` confidence.
8. **Large low-confidence area** — a unit covers a large mapped area *and* has
   low confidence (high impact if the interpretation is wrong).

## How to review a flagged unit

For each flagged unit (see `outputs/processed/manual_review_required.csv` and the
unit cards in `outputs/processed/geology_unit_cards.*`):

1. Open the matching **unit card** and read `raw_*` fields + `source_evidence`.
2. Cross-check against the **source legend** (DBF attributes) and the GSJ
   **explanation sheet** (PDF). For scanned PDFs, consult the original document.
3. Decide whether the assigned `engineering_ground_type` is reasonable:
   - If correct, raise `interpretation_confidence` and clear the flag.
   - If wrong, override `engineering_ground_type` (use an ontology class from
     `geotech_ontology.yaml`) and record the reason.
   - If genuinely ambiguous, keep it as `mixed_or_uncertain_geology` and note the
     competing classes.
4. Confirm the `geotechnical_risk_flags` and `recommended_investigation` make
   sense for the corrected class; edit if needed.
5. Record the reviewer, date and decision (recommended columns:
   `reviewer`, `review_date`, `review_decision`, `review_notes`).

## How to extend / correct the knowledge base

- **New geology terms**: add to `lithology_dictionary_ja_en.csv` and, if needed,
  add keywords to a rule in `geology_to_geotech_rules.yaml`.
- **New mapping logic**: add or adjust a rule; keep `priority` ordering sensible
  (specific before generic; fault/fracture first).
- **New ground category**: add a class to `geotech_ontology.yaml` and a rule that
  targets it.
- **New map sheet**: add an entry (and a field profile if its DBF layout differs)
  in `src/map_config.py`, then re-run the pipeline.

## What reviewers must NOT do

- Do not convert a screening flag into a design conclusion.
- Do not state bearing capacity, pile length, settlement magnitude, liquefaction
  factor of safety, or slope-stability results based on this database.
- Do not treat mapped boundaries or fault positions as survey-accurate; 1:50,000
  boundaries carry tens-of-metres positional uncertainty.
