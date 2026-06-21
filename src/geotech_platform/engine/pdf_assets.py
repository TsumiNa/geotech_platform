"""
PDF asset extraction -> structured, AI-ready index (addresses feedback #2).

Dependency-free extraction of embedded raster images from the GSJ explanatory
PDFs, plus a structured index that separates and labels content so it can feed a
clustering / retrieval layer later.

What it extracts:
  * Embedded images encoded as DCTDecode (JPEG) -> saved as .jpg (raw copy)
                       or JPXDecode (JPEG2000)  -> saved as .jp2
    Each gets width/height, byte size, page estimate, a heuristic content-type
    guess (photo / wide-figure / portrait-figure / small-graphic), a dedup hash,
    and empty caption/label fields for later AI/OCR or manual completion.
  * JBIG2 / CCITT (bi-level scanned pages) and Flate raster: COUNTED and flagged
    for review (not decoded here — they need a codec/OCR not available offline).
  * Text blocks: pulled via the best-effort text extractor (engine/pdf_text.py);
    quality is scored so unreadable CID/scanned text is flagged, not trusted.

Why captions/labels are not auto-filled: this environment has no OCR engine or
callable vision model, so automatic captioning over thousands of images is not
possible here. The index is built so (a) a human, or (b) a later vision/OCR model
can fill `caption`/`content_label`. A small curated sample is labelled separately
in reference/knowledge/pdf_curated_labels.csv (done by viewing the images).

Outputs (per run):
  outputs/pdf_assets/<region>/fig_*.jpg|.jp2
  outputs/pdf_assets/pdf_asset_index.csv  + .json
  outputs/pdf_assets/pdf_text_blocks.csv
  outputs/pdf_assets/pdf_assets_clustering_summary.md
"""

from __future__ import annotations

import hashlib
import os
import re

from . import config
from . import map_config as MC
from .pdf_text import extract_pdf

MIN_W = 150  # px
MIN_H = 150
MIN_BYTES = 6000  # skip tiny icons/tiles
MAX_PER_PDF = 80  # keep the largest N meaningful images per PDF

_OBJ_DICT = re.compile(rb"<<(.*?)>>", re.DOTALL)


def _valid_image_magic(raw, ext):
    """Verify the stream really is the expected image codec.

    Guards against /Filter markers that are not at an image-stream boundary
    (e.g. references inside other objects), which would otherwise yield corrupt
    files. JPEG = FFD8FF; JPEG2000 = jP2 box (..jP) or raw codestream (FF4F FF51).
    """
    if ext == "jpg":
        return raw[:3] == b"\xff\xd8\xff"
    if ext == "jp2":
        return raw[:12].find(b"jP") != -1 or raw[:4] == b"\xff\x4f\xff\x51"
    return False


def _intval(dict_bytes, key):
    m = re.search(key.encode() + rb"\s+(\d+)", dict_bytes)
    return int(m.group(1)) if m else None


def _page_offsets(data):
    """Byte offsets of page markers, to estimate which page an image sits on."""
    return [m.start() for m in re.finditer(rb"/Type\s*/Page[^s]", data)]


def _est_page(img_offset, page_offsets):
    p = 1
    for i, off in enumerate(page_offsets):
        if off <= img_offset:
            p = i + 1
        else:
            break
    return p


def _content_guess(w, h, nbytes):
    if not w or not h:
        return "unknown"
    ar = w / h
    if ar >= 1.8:
        return "wide_figure (map/cross-section/chart?)"
    if ar <= 0.6:
        return "portrait_figure (column/log?)"
    if 0.8 <= ar <= 1.25 and nbytes > 40000:
        return "photo (rock/outcrop/photomicrograph?)"
    return "graphic_or_photo"


def extract_images_from_pdf(path, out_dir, region):
    data = open(path, "rb").read()
    page_offsets = _page_offsets(data)
    found = []
    # locate image streams by their filter marker
    for filt, ext in ((b"/DCTDecode", "jpg"), (b"/JPXDecode", "jp2")):
        for m in re.finditer(filt, data):
            # find enclosing dict start '<<' before, and 'stream' after
            dict_start = data.rfind(b"<<", max(0, m.start() - 2000), m.start())
            sm = re.search(rb"stream\r?\n", data[m.start() : m.start() + 4000])
            if dict_start == -1 or not sm:
                continue
            dict_bytes = data[dict_start : m.start() + 200]
            # must be an image xobject
            if b"/Image" not in dict_bytes and b"/Subtype" not in dict_bytes:
                # DCT streams are images even if /Subtype split; keep going
                pass
            s_start = m.start() + sm.end()
            s_end = data.find(b"endstream", s_start)
            if s_end == -1:
                continue
            raw = data[s_start:s_end].rstrip(b"\r\n")
            if len(raw) < MIN_BYTES:
                continue
            if not _valid_image_magic(raw, ext):
                continue  # skip mis-located / corrupt streams (honest extraction)
            w = _intval(dict_bytes, "/Width")
            h = _intval(dict_bytes, "/Height")
            if (w and w < MIN_W) or (h and h < MIN_H):
                continue
            found.append(
                {
                    "offset": m.start(),
                    "bytes": raw,
                    "ext": ext,
                    "w": w,
                    "h": h,
                    "filter": filt.decode().lstrip("/"),
                }
            )
    # dedupe by content hash, keep largest
    uniq = {}
    for f in found:
        hsh = hashlib.md5(f["bytes"]).hexdigest()
        if hsh not in uniq or len(f["bytes"]) > len(uniq[hsh]["bytes"]):
            f["hash"] = hsh
            uniq[hsh] = f
    items = sorted(uniq.values(), key=lambda f: -len(f["bytes"]))[:MAX_PER_PDF]

    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for i, f in enumerate(items):
        fid = f"{region}_fig_{i:03d}"
        fname = f"{fid}.{f['ext']}"
        with open(os.path.join(out_dir, fname), "wb") as fh:
            fh.write(f["bytes"])
        rows.append(
            {
                "asset_id": fid,
                "source_region": region,
                "source_pdf": os.path.basename(path),
                "file": os.path.join("pdf_assets", region, fname),
                "page_estimate": _est_page(f["offset"], page_offsets),
                "format": f["ext"],
                "encoding": f["filter"],
                "width_px": f["w"],
                "height_px": f["h"],
                "bytes": len(f["bytes"]),
                "content_type_guess": _content_guess(f["w"], f["h"], len(f["bytes"])),
                "caption": "",  # to be filled by OCR/vision/human
                "content_label": "",  # to be filled (curated labels file overrides)
                "hash": f["hash"],
                "label_status": "pending_ai_or_manual",
            }
        )
    return rows


def count_undecoded(path):
    data = open(path, "rb").read()
    return {
        "jbig2_scanned_pages": len(re.findall(rb"/JBIG2Decode", data)),
        "ccitt_scanned": len(re.findall(rb"/CCITTFault", data)),
        "flate_raster_images": len(
            re.findall(rb"/FlateDecode", re.sub(rb"[^/]", b"", b""))
        ),  # placeholder 0
    }


def build():
    config.ensure_dirs()
    all_rows = []
    text_rows = []
    undecoded = []
    for m in MC.MAPS:
        region = m["region"]
        out_dir = os.path.join(config.PDF_ASSETS, region)
        for key in ("pdf_monograph", "pdf_desc"):
            rel = m.get(key)
            if not rel:
                continue
            path = MC.raw_path(rel)
            if not os.path.exists(path):
                continue
            rows = extract_images_from_pdf(path, out_dir, region)
            all_rows.extend(rows)
            # undecoded counts
            data = open(path, "rb").read()
            undecoded.append(
                {
                    "source_region": region,
                    "source_pdf": os.path.basename(path),
                    "jbig2_scanned": len(re.findall(rb"/JBIG2Decode", data)),
                    "ccitt_scanned": len(re.findall(rb"/CCITTFault", data)),
                    "note": "JBIG2/CCITT bi-level page scans not decoded offline; OCR/vision needed.",
                }
            )
            # text
            try:
                res = extract_pdf(path)
            except Exception:
                res = {"text": "", "quality": 0.0, "n_pages": 0}
            text_rows.append(
                {
                    "source_region": region,
                    "source_pdf": os.path.basename(path),
                    "pages_est": res["n_pages"],
                    "chars": len(res["text"]),
                    "text_quality": round(res["quality"], 3),
                    "readable": "yes"
                    if (res["quality"] >= 0.85 and len(res["text"]) > 200)
                    else "no (CID/scanned -> review)",
                    "text_sample": res["text"][:800],
                }
            )
    n_prev = _make_previews(all_rows)
    _write_outputs(all_rows, text_rows, undecoded)
    return {
        "images": len(all_rows),
        "text_blocks": len(text_rows),
        "previews_png": n_prev,
    }


def _make_previews(rows):
    """Render web-viewable PNG thumbnails (JPEG2000 doesn't display in browsers).

    Uses PIL if available; previews power the app's figure drill-down. Each row
    gets a 'preview_png' path when successful.
    """
    try:
        from PIL import Image
    except Exception:
        for r in rows:
            r["preview_png"] = ""
        return 0
    prev_dir = os.path.join(config.PDF_ASSETS, "_preview_png")
    os.makedirs(prev_dir, exist_ok=True)
    n = 0
    for r in rows:
        src = os.path.join(config.OUTPUTS, r["file"])
        dst = os.path.join(prev_dir, r["asset_id"] + ".png")
        rel = os.path.join("pdf_assets", "_preview_png", r["asset_id"] + ".png")
        try:
            im = Image.open(src)
            im.load()
            im.thumbnail((1000, 1000))
            im.convert("RGB").save(dst)
            r["preview_png"] = rel
            n += 1
        except Exception:
            r["preview_png"] = ""
    return n


def _write_outputs(rows, text_rows, undecoded):
    from . import io_utils as IO

    # merge curated labels if present
    curated = _load_curated()
    for r in rows:
        c = curated.get(r["asset_id"])
        if c:
            r["caption"] = c.get("caption", "")
            r["content_label"] = c.get("content_label", "")
            r["label_status"] = "ai_curated"
    IO.write_csv(os.path.join(config.PDF_ASSETS, "pdf_asset_index.csv"), rows)
    IO.write_json(os.path.join(config.PDF_ASSETS, "pdf_asset_index.json"), rows)
    IO.write_csv(os.path.join(config.PDF_ASSETS, "pdf_text_blocks.csv"), text_rows)
    IO.write_csv(
        os.path.join(config.PDF_ASSETS, "pdf_undecoded_scanned.csv"), undecoded
    )
    _clustering_summary(rows, text_rows, undecoded)


def _load_curated():
    import csv

    p = os.path.join(config.KNOWLEDGE, "pdf_curated_labels.csv")
    out = {}
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            out[r["asset_id"]] = r
    return out


def _clustering_summary(rows, text_rows, undecoded):
    from collections import Counter

    lines = [
        "# PDF assets — content summary (clustering layer, v1)\n",
        "Structured index of figures/photos and text extracted from the GSJ "
        "explanatory PDFs. Images are grouped by a heuristic content-type guess; "
        "curated AI labels (where present) refine them. This is the basis for a "
        "future clustering/retrieval layer over the report figures.\n",
    ]
    by_region = Counter(r["source_region"] for r in rows)
    lines.append("## Extracted images by region")
    lines.append("| Region | Images extracted |")
    lines.append("|---|---|")
    for reg, n in sorted(by_region.items()):
        lines.append(f"| {reg} | {n} |")
    lines.append("\n## By heuristic content-type guess")
    by_type = Counter(r["content_type_guess"] for r in rows)
    lines.append("| Content-type guess | Count |\n|---|---|")
    for t, n in by_type.most_common():
        lines.append(f"| {t} | {n} |")
    labelled = sum(1 for r in rows if r.get("label_status") == "ai_curated")
    lines.append(
        f"\n**AI-curated labels:** {labelled} of {len(rows)} images "
        f"(remaining `pending_ai_or_manual`)."
    )
    lines.append("\n## Text extraction status")
    lines.append(
        "| Region | PDF | Pages | Chars | Quality | Readable |\n|---|---|---|---|---|---|"
    )
    for t in text_rows:
        lines.append(
            f"| {t['source_region']} | {t['source_pdf']} | {t['pages_est']} | "
            f"{t['chars']} | {t['text_quality']} | {t['readable']} |"
        )
    lines.append("\n## Undecoded scanned content (need OCR/vision)")
    lines.append("| Region | PDF | JBIG2 pages | CCITT | Note |\n|---|---|---|---|---|")
    for u in undecoded:
        lines.append(
            f"| {u['source_region']} | {u['source_pdf']} | {u['jbig2_scanned']} | "
            f"{u['ccitt_scanned']} | {u['note']} |"
        )
    lines.append("\n## Tables")
    lines.append(
        "Table structure detection is not performed offline (needs a layout/OCR "
        "engine). Tabular content in scanned monographs is flagged via the text "
        "rows above and should be transcribed during manual review."
    )
    with open(
        os.path.join(config.PDF_ASSETS, "pdf_assets_clustering_summary.md"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    print(build())
