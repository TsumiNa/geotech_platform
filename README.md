# Geotechnical Geology Platform v2

A standalone redesign of the geology→geotech screening prototype, built around
four pieces of feedback:

1. **Reviewable region boundaries** — both the actual data extent and the official
   1:50,000 quadrangle frame are derived and written to a file you can inspect and
   correct.
2. **Structured PDF asset layer** — embedded figures/photos are extracted from the
   explanatory PDFs, labelled (a curated sample by vision), clustered by content
   type, and indexed in an AI-ready form; text/tables are separated and scanned
   pages flagged.
3. **Layered inference engine** — geology term → rock/soil type + stratigraphy →
   geotech translation (the terms engineers use) → indicative properties
   (mechanical/chemical, with citations) → geotechnical considerations. Shown only
   when expanded.
4. **Hierarchical drill-down** — every conclusion can be opened layer by layer,
   down to the raw map attributes and the source report figures.

Bilingual (English / 日本語) throughout, using Japanese geotechnical vocabulary.

> **Screening only.** Outputs are plausible ground-condition hypotheses, risk
> flags, uncertainty and recommended investigation — never bearing capacity, pile
> length, settlement, liquefaction factor of safety, or slope-stability results.
> L3 property bands are indicative literature/judgement ranges (`design_use:false`).

## The inference chain (the core)

```
L1  Geology identification   raw unit/lithology/age  → geological material, lithology,
    (knowledge/L1_geology_terms.csv)                   depositional env, consolidation, group
        │  (age-aware: pre-Holocene granular → overconsolidated, not soft alluvium)
L2  Geotech translation      → engineering ground type + the terms geotech engineers use
    (knowledge/L2_geology_to_geotech.csv)
L3  Indicative properties    → SPT-N / unit weight / strength / UCS / compressibility /
    (knowledge/L3_property_ranges.yaml)               permeability + chemical notes  [+ sources]
L4  Considerations & advice  → per-application screening considerations + investigation
    (knowledge/L4_recommendations.yaml)
        │
   Source evidence: raw map attributes  +  linked report figures
```

Each step records inputs, the knowledge row used, outputs, evidence, a confidence,
and citable sources (`knowledge/sources.yaml`). This is what the app drills into.

## Quick start

```bash
pip install pyyaml pillow            # core (pillow enables figure previews)
python run_pipeline.py               # build everything (reads ../sample_geology_reports)

# point query with full chain:
python engine/query.py 35.62 139.40

# drill-down UI (bilingual):
pip install streamlit pandas
streamlit run app/streamlit_app.py
```

## Standalone & raw data

This folder is self-contained for code, knowledge base and outputs. The **raw
geology data is referenced, not copied**, from the sibling `sample_geology_reports/`
folder (override with `GEO_RAW_ROOT`). Raw files are only ever read.

## Layout

```
reference/
  knowledge/
    L1_geology_terms.csv          geology term → rock/soil, lithology, strat, consolidation
    L2_geology_to_geotech.csv     geological character → engineering ground type + terms
    L3_property_ranges.yaml       indicative property bands (mechanical/chemical) + provenance
    L4_recommendations.yaml       per-application considerations + investigation
    sources.yaml                  citable provenance registry (GSJ, JGS, JSCE, etc.)
    pdf_curated_labels.csv        vision-reviewed figure labels (sample)
  region_boundaries.yaml          reviewable boundaries (written by the build)
  geotech_ontology.yaml, geology_to_geotech_rules.yaml, engineering_risk_dictionary.yaml,
  lithology_dictionary_ja_en.csv, i18n_ja.yaml, manual_review_guidelines.md   (copied, standalone)

engine/
  config.py            paths (raw data → ../sample_geology_reports)
  map_config.py        per-sheet field profiles
  shapefile_io.py geo_utils.py gpkg_writer.py io_utils.py pdf_text.py i18n.py   (pure-Python core)
  boundaries.py        region boundary derivation + region_for_point()
  inference.py         the layered L1–L4 engine (evidence-linked chains)
  pdf_assets.py        figure extraction + AI-ready index + clustering summary
  query.py             point query returning the full chain
  build.py             orchestrator

app/streamlit_app.py   bilingual hierarchical drill-down UI
database/              tokyo_geotech_v2.gpkg + .sqlite
outputs/
  boundaries/          region_boundaries_review.md
  pdf_assets/          extracted figures, _preview_png/, pdf_asset_index.csv/json,
                       pdf_assets_clustering_summary.md, pdf_text_blocks.csv
  processed/           geology_features.csv, geotech_features.csv,
                       inference_chains.json, geology_unit_cards.csv/json,
                       manual_review_required.csv
  build_log.md
```

## Extending (accuracy improves with data)

The mappings are deliberately first-version and **data-driven**, so accuracy grows
by editing/adding rows — no code changes:

- **New geology terms / formations** → add rows to `L1_geology_terms.csv`.
- **New geotech mappings** → `L2_geology_to_geotech.csv`.
- **Better properties** → edit `L3_property_ranges.yaml` and point `source_ref` at a
  new entry in `sources.yaml` (e.g. your forthcoming textbook PDFs). Provenance and
  `design_use:false` keep every value auditable.
- **New ground category** → add to `geotech_ontology.yaml` + a rule.
- **Figure labels** → fill `pdf_curated_labels.csv` (or let a vision/OCR model do it).

This structure is intended to be backed later by a knowledge graph / database for
inference; the CSV/YAML tables are the seed of that graph.

## Known limitations (honest)

- **PDF figures**: 45 figures extracted from the 2013 Hachioji monograph (JPEG2000).
  The 1984 Tokyo-Seinambu monograph is **scanned (JBIG2)** and the 1982 Yokohama
  monograph uses **non-standard JPX** that the dependency-free extractor cannot
  safely decode — both are flagged for an OCR/vision pass.
- **Figure captioning** is partial: a curated sample was labelled by vision; the
  rest are `pending_ai_or_manual`. There is no OCR engine in the build environment,
  so bulk auto-captioning is left for a later vision/OCR step.
- **Property bands are indicative**, not design values, by design.
