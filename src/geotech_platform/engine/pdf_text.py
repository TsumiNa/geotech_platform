"""
Best-effort, dependency-free PDF text extraction.

The environment has no PyMuPDF / pdfminer, so this module does a pragmatic job:
it inflates FlateDecode content streams (zlib is in the stdlib) and pulls text
operands from Tj / TJ operators. This works for PDFs with simple text encodings.

GSJ explanatory sheets are typeset with Japanese CID fonts, for which byte→glyph
mapping requires the embedded ToUnicode CMaps; reconstructing readable Japanese
without a font library is unreliable. We therefore also compute an
``extraction_quality`` score per page so the pipeline can route low-quality pages
to a manual-review list instead of emitting garbled text. This matches the
project guidance: "If PDF text extraction is poor, do not spend excessive time on
OCR."
"""

from __future__ import annotations

import re
import zlib


def _iter_streams(data: bytes):
    """Yield decompressed stream bytes from a PDF (FlateDecode only)."""
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        raw = data[start:end]
        # strip trailing EOL before endstream
        raw = raw.rstrip(b"\r\n")
        try:
            yield zlib.decompress(raw)
        except Exception:
            # not flate (maybe raw or other filter) -- try raw if printable
            continue


_TEXT_OP = re.compile(rb"\((?:\\.|[^\\()])*\)|\<[0-9A-Fa-f\s]+\>")


def _decode_pdf_string(tok: bytes) -> str:
    if tok.startswith(b"<"):
        hexs = re.sub(rb"\s+", b"", tok[1:-1])
        try:
            b = bytes.fromhex(hexs.decode("ascii"))
        except Exception:
            return ""
        # try utf-16be then latin
        try:
            return b.decode("utf-16-be")
        except Exception:
            return b.decode("latin-1", errors="ignore")
    inner = tok[1:-1]
    # unescape common sequences
    inner = inner.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
    try:
        return inner.decode("latin-1", errors="ignore")
    except Exception:
        return ""


def _extract_text_from_stream(s: bytes) -> str:
    out = []
    for m in re.finditer(rb"BT(.*?)ET", s, re.DOTALL):
        block = m.group(1)
        for tm in _TEXT_OP.finditer(block):
            out.append(_decode_pdf_string(tm.group(0)))
    return "".join(out)


def quality_score(text: str) -> float:
    """Fraction of characters that are 'meaningful' (CJK or ascii letters)."""
    if not text:
        return 0.0
    good = 0
    for ch in text:
        o = ord(ch)
        if ch.isalnum() or ch.isspace() or ch in "、。・，．（）「」":
            good += 1
        elif 0x3000 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF:
            good += 1
    return good / max(1, len(text))


def extract_pdf(path: str) -> dict:
    """Return {'n_pages': int(estimate), 'text': str, 'quality': float}."""
    with open(path, "rb") as fh:
        data = fh.read()
    # crude page count: count /Type /Page (not Pages)
    n_pages = len(re.findall(rb"/Type\s*/Page[^s]", data)) or 1
    chunks = []
    for s in _iter_streams(data):
        if b"BT" in s and b"ET" in s:
            chunks.append(_extract_text_from_stream(s))
    text = "\n".join(c for c in chunks if c.strip())
    return {"n_pages": n_pages, "text": text, "quality": quality_score(text)}


if __name__ == "__main__":
    import sys
    r = extract_pdf(sys.argv[1])
    print("pages(est):", r["n_pages"], "quality:", round(r["quality"], 3),
          "chars:", len(r["text"]))
    print(repr(r["text"][:500]))
