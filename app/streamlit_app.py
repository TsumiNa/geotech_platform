"""
Geotech Geology Platform v2 — hierarchical, bilingual drill-down app.

Addresses the feedback:
  #3  shows the layered geology -> geotech -> properties -> recommendation
      inference (only when the user expands it).
  #4  every conclusion drills DOWN layer by layer (L4 -> L3 -> L2 -> L1) to the
      raw geology attributes and the source PDF figures.
  bilingual English / 日本語 throughout (Japanese geotech terms).

Run:
    pip install streamlit pandas pyyaml pillow
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import csv
import json
import os
import sys

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)
sys.path.insert(0, os.path.join(ROOT, "engine"))

import config           # noqa
import i18n             # noqa
import query as Q       # noqa
import boundaries as B  # noqa

PROC = config.PROC
OUTPUTS = config.OUTPUTS

st.set_page_config(page_title="Geotech Geology Platform v2", layout="wide")

# ----------------------------------------------------------------- i18n -----
LANGS = {"English": "en", "日本語": "ja"}
with st.sidebar:
    LANG = LANGS[st.radio("Language / 言語", list(LANGS.keys()))]

# v2-specific UI strings (ground types/flags/etc. come from engine/i18n.py)
TT = {
    "title": {"en": "Geotechnical Geology Platform v2", "ja": "地質→地盤工学プラットフォーム v2"},
    "subtitle": {"en": "Geology → geotech inference with full drill-down to source evidence",
                 "ja": "地質から地盤工学への推論。根拠資料まで階層的に辿れます。"},
    "disclaimer": {"en": Q.DISCLAIMER_EN, "ja": Q.DISCLAIMER_JA},
    "tab_overview": {"en": "Overview & boundaries", "ja": "概要・図幅境界"},
    "tab_layer": {"en": "Geotech layer", "ja": "地盤工学レイヤ"},
    "tab_point": {"en": "Point query (drill-down)", "ja": "地点クエリ（階層表示）"},
    "tab_unit": {"en": "Unit explorer", "ja": "地質単元エクスプローラ"},
    "tab_figs": {"en": "PDF figures", "ja": "PDF図表"},
    "tab_review": {"en": "Manual review", "ja": "要レビュー"},
    "conclusion": {"en": "Screening conclusion", "ja": "スクリーニング結論"},
    "ground_type": {"en": "Ground type", "ja": "地盤タイプ"},
    "geotech_term": {"en": "Geotech term", "ja": "地盤工学用語"},
    "confidence": {"en": "Confidence", "ja": "確信度"},
    "risk": {"en": "Risk flags (screening)", "ja": "地盤リスク要因（スクリーニング）"},
    "drilldown": {"en": "How this conclusion was reached (drill down)",
                  "ja": "結論に至った経緯（クリックで掘り下げ）"},
    "inputs": {"en": "Inputs", "ja": "入力"},
    "outputs": {"en": "Outputs", "ja": "出力"},
    "evidence": {"en": "Evidence / reasoning", "ja": "根拠・推論"},
    "sources": {"en": "Sources (citable)", "ja": "出典（引用可）"},
    "knowledge": {"en": "Knowledge used", "ja": "使用した知識"},
    "src_evidence": {"en": "Source evidence (raw attributes + report figures)",
                     "ja": "根拠資料（生属性＋報告書の図表）"},
    "raw_attrs": {"en": "Raw map attributes", "ja": "地質図の生属性"},
    "related_figs": {"en": "Related report figures (same sheet)", "ja": "関連する報告書図表（同一図幅）"},
    "no_design": {"en": "Indicative screening bands — NOT design values.",
                  "ja": "想定スクリーニング値であり、設計値ではありません。"},
    "outside": {"en": "Outside mapped extent / no polygon at this point.",
                "ja": "地質図範囲外、またはこの地点にポリゴンがありません。"},
    "lat": {"en": "Latitude", "ja": "緯度"}, "lon": {"en": "Longitude", "ja": "経度"},
    "run": {"en": "Query", "ja": "照会"},
    "dist_boundary": {"en": "Distance to geology boundary", "ja": "地質境界までの距離"},
    "pick_unit": {"en": "Pick a geology unit", "ja": "地質単元を選択"},
    "filter_label": {"en": "Filter figures by content label", "ja": "内容ラベルで図を絞り込み"},
}


def T(k):
    return TT[k][LANG]


def GT(c):
    return i18n.ground_type(c, LANG)


def FAM(c):
    return i18n.material_family(c, LANG)


def CONF(c):
    return i18n.confidence(c, LANG)


def FLAGS(codes):
    return i18n.risk_flags(codes or [], LANG)


@st.cache_data
def load_chains():
    return json.load(open(os.path.join(PROC, "inference_chains.json"), encoding="utf-8"))


@st.cache_data
def load_features():
    return pd.read_csv(os.path.join(PROC, "geotech_features.csv"))


@st.cache_data
def load_assets():
    p = os.path.join(config.PDF_ASSETS, "pdf_asset_index.csv")
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


# ---------------------------------------------------------------- render ----
def render_step(step, idx):
    title = step["title_ja"] if LANG == "ja" else step["title_en"]
    badge = {"high": "🟢", "medium": "🟡", "low": "🟠", "very_low": "🔴"}.get(step["confidence"], "⚪")
    with st.expander(f"{idx}. {title}  {badge} {CONF(step['confidence'])}"):
        c1, c2 = st.columns(2)
        c1.markdown(f"**{T('inputs')}**"); c1.json(step.get("inputs", {}))
        c2.markdown(f"**{T('outputs')}**"); c2.json(step.get("outputs", {}))
        if step.get("knowledge_ref"):
            st.caption(f"{T('knowledge')}: `{step['knowledge_ref']}`")
        st.markdown(f"**{T('evidence')}**")
        for e in step.get("evidence", []):
            st.write("• " + e)
        if step.get("step") == "L3_indicative_properties":
            st.info(T("no_design"))
        if step.get("sources"):
            st.markdown(f"**{T('sources')}**")
            for s in step["sources"]:
                if s.get("url"):
                    st.write(f"• [{s['id']}] [{s['title']}]({s['url']}) — *{s.get('tier','')}*")
                else:
                    st.write(f"• [{s['id']}] {s['title']} — *{s.get('tier','')}*")


def render_chain(card, region):
    gt = card["engineering_ground_type"]
    term = card["geotech_term_ja"] if LANG == "ja" else card["geotech_term_en"]
    st.subheader(T("conclusion"))
    c1, c2, c3 = st.columns(3)
    c1.metric(T("ground_type"), GT(gt))
    c2.metric(T("geotech_term"), term or "-")
    c3.metric(T("confidence"), CONF(card["overall_confidence"]))
    flags = FLAGS(card["risk_flags"])
    if flags:
        st.markdown(f"**{T('risk')}:** " + ("、".join(flags) if LANG == "ja" else ", ".join(flags)))

    st.markdown(f"### {T('drilldown')}")
    # show in conclusion-first order: L4, L3, L2, L1
    order = {"L4_considerations": 0, "L3_indicative_properties": 1,
             "L2_geotech_translation": 2, "L1_geology": 3}
    steps = sorted(card["chain"], key=lambda s: order.get(s["step"], 9))
    for i, s in enumerate(steps, 1):
        render_step(s, i)

    # source evidence + figures
    with st.expander(f"5. {T('src_evidence')}"):
        st.markdown(f"**{T('raw_attrs')}**")
        st.json(card.get("source_evidence", {}).get("raw_attributes", {}))
        _show_region_figures(region, limit=6)


def _show_region_figures(region, limit=6, label_filter=None):
    assets = load_assets()
    if assets.empty:
        return
    a = assets[assets.source_region.astype(str) == str(region)]
    if "preview_png" in a.columns:
        a = a[a.preview_png.notna() & (a.preview_png.astype(str) != "")]
    if label_filter:
        a = a[a.content_label.astype(str).str.contains(label_filter, case=False, na=False)]
    a = a.head(limit)
    if a.empty:
        st.caption("— no extracted figures for this sheet (08063/08074 monographs flagged for OCR).")
        return
    st.markdown(f"**{T('related_figs')}**")
    cols = st.columns(3)
    for i, (_, r) in enumerate(a.iterrows()):
        path = os.path.join(OUTPUTS, str(r["preview_png"]))
        cap = (r.get("content_label") or r.get("content_type_guess") or "")
        if r.get("caption"):
            cap = f"{cap} — {r['caption']}"
        if os.path.exists(path):
            cols[i % 3].image(path, caption=f"{r['asset_id']} (p{r.get('page_estimate','?')}): {cap}",
                              use_container_width=True)


# ------------------------------------------------------------------- UI -----
st.title(T("title"))
st.caption(T("subtitle"))
st.warning(T("disclaimer"))

tabs = st.tabs([T("tab_overview"), T("tab_layer"), T("tab_point"),
                T("tab_unit"), T("tab_figs"), T("tab_review")])

# --- overview & boundaries ---
with tabs[0]:
    st.markdown(
        "**Raw GSJ 1:50,000 geology → L1 geology ID → L2 geotech translation → "
        "L3 indicative properties → L4 considerations → drill-down to evidence.**"
        if LANG == "en" else
        "**GSJ 5万分の1地質図 → L1 地質同定 → L2 地盤工学翻訳 → L3 想定物性 → "
        "L4 留意点 → 根拠資料へドリルダウン**")
    st.subheader(T("tab_overview"))
    regs = B.load()
    rows = []
    for r in regs:
        q = r["nominal_quadrangle"]; d = r["actual_data_bbox"]
        rows.append({
            "region": r["region"], "map": f"{r['map_name_en']} / {r['map_name_ja']}",
            "nominal_lon": f"{q['lon_min']}–{q['lon_max']}",
            "nominal_lat": f"{q['lat_min']}–{q['lat_max']}",
            "data_lon": f"{d['lon_min']:.3f}–{d['lon_max']:.3f}",
            "data_lat": f"{d['lat_min']:.3f}–{d['lat_max']:.3f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.caption("Nominal = official 1:50k quadrangle frame (used for region assignment). "
               "Data = actual polygon extent. Review/edit reference/region_boundaries.yaml."
               if LANG == "en" else
               "Nominal＝正式な5万分の1図幅枠（図幅判定に使用）。Data＝実ポリゴン範囲。"
               "reference/region_boundaries.yaml で確認・修正できます。")

# --- geotech layer ---
with tabs[1]:
    df = load_features()
    st.subheader(T("tab_layer"))
    codes = sorted(df.engineering_ground_type.unique())
    lab2code = {GT(c): c for c in codes}
    picked = st.multiselect(T("ground_type"), list(lab2code.keys()), default=list(lab2code.keys()))
    d = df[df.engineering_ground_type.isin([lab2code[l] for l in picked])].copy()
    counts = d.engineering_ground_type.value_counts()
    counts.index = [GT(c) for c in counts.index]
    st.bar_chart(counts)
    disp = pd.DataFrame({
        "feature_id": d.feature_id, "region": d.source_region,
        T("ground_type"): d.engineering_ground_type.map(GT),
        T("geotech_term"): d.geotech_term_ja if LANG == "ja" else d.geotech_term_en,
        T("confidence"): d.interpretation_confidence.map(CONF),
        T("pick_unit"): d.raw_unit_name_ja if LANG == "ja" else d.raw_unit_name_en,
    })
    st.dataframe(disp, use_container_width=True, height=460)

# --- point query (drill-down) ---
with tabs[2]:
    st.subheader(T("tab_point"))
    c1, c2 = st.columns(2)
    lat = c1.number_input(T("lat"), value=35.62, format="%.5f")
    lon = c2.number_input(T("lon"), value=139.40, format="%.5f")
    if st.button(T("run")):
        r = Q.query_point(lat, lon)
        if not r["found"]:
            st.error(T("outside"))
        else:
            raw = r["raw"]
            nm = raw["raw_unit_name_ja"] if LANG == "ja" else (raw["raw_unit_name_en"] or raw["raw_unit_name_ja"])
            st.info(f"**{nm}** ({raw['raw_unit_code']}) · {raw['raw_lithology']} · {raw['raw_age']}  \n"
                    f"{T('dist_boundary')}: {r['distance_to_boundary_m']} m · region {r['source_region']}")
            chains = {c["geology_unit_card_id"]: c for c in load_chains()}
            card = chains.get(r["unit_card_id"])
            if card:
                render_chain(card, r["source_region"])

# --- unit explorer ---
with tabs[3]:
    st.subheader(T("tab_unit"))
    chains = load_chains()
    labels = [f"{c['source_region']} · {c['raw_unit_name_ja']} ({c['raw_unit_code']}) → {GT(c['engineering_ground_type'])}"
              for c in chains]
    pick = st.selectbox(T("pick_unit"), range(len(labels)), format_func=lambda i: labels[i])
    render_chain(chains[pick], chains[pick]["source_region"])

# --- pdf figures ---
with tabs[4]:
    st.subheader(T("tab_figs"))
    assets = load_assets()
    if assets.empty:
        st.info("No figures extracted yet — run the pipeline.")
    else:
        st.caption(f"{len(assets)} figures extracted (08062 monograph). "
                   "08063 is scanned (JBIG2) and 08074_D uses non-standard JPX — flagged for OCR.")
        labels = ["(all)"] + sorted(x for x in assets.content_label.dropna().unique() if x)
        pick = st.selectbox(T("filter_label"), labels)
        a = assets if pick == "(all)" else assets[assets.content_label == pick]
        a = a[a.preview_png.notna() & (a.preview_png.astype(str) != "")]
        cols = st.columns(3)
        for i, (_, r) in enumerate(a.head(30).iterrows()):
            path = os.path.join(OUTPUTS, str(r["preview_png"]))
            if os.path.exists(path):
                cap = f"{r['asset_id']} (p{r.get('page_estimate','?')}) {r.get('content_label') or r.get('content_type_guess')}"
                cols[i % 3].image(path, caption=cap, use_container_width=True)

# --- manual review ---
with tabs[5]:
    st.subheader(T("tab_review"))
    p = os.path.join(PROC, "manual_review_required.csv")
    df = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
    if df.empty:
        st.success("No units flagged." if LANG == "en" else "要レビューの単元はありません。")
    else:
        st.dataframe(df, use_container_width=True, height=420)
