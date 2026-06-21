"""
Pure-Python ESRI Shapefile + DBF reader.

This module exists because the prototype environment does not have geopandas /
GDAL / fiona available. It implements just enough of the shapefile (.shp / .shx)
and dBASE (.dbf) specifications to read the GSJ 1:50,000 geology polygon layers
(shape type 5 = Polygon) together with their attribute tables.

It is intentionally dependency-free (Python standard library only) so the
preprocessing pipeline can run anywhere.

References:
  - ESRI Shapefile Technical Description (1998)
  - dBASE (.dbf) file structure

Geometry is returned in the file's native coordinates. For the GSJ data this is
geographic longitude/latitude in JGD2000 (EPSG:4612), per the .prj files.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------- #
# DBF (attribute table) reader
# --------------------------------------------------------------------------- #

def _detect_encoding(dbf_path: str) -> str:
    """Pick a text encoding for a .dbf using its sidecar .cpg if present.

    GSJ files mix UTF-8 (newer, e.g. 2013 Hachioji) and Shift-JIS (older 1982/
    1984 sheets). The .cpg file, when present, states the encoding.
    """
    cpg = os.path.splitext(dbf_path)[0] + ".cpg"
    if os.path.exists(cpg):
        try:
            val = open(cpg, "r", encoding="ascii", errors="ignore").read().strip().lower()
        except Exception:
            val = ""
        if "utf" in val:
            return "utf-8"
        if "932" in val or "shift" in val or "sjis" in val:
            return "shift_jis"
    # Heuristic fallback: try utf-8 strict, else shift_jis.
    return "auto"


def _decode(raw: bytes, enc: str) -> str:
    if enc == "auto":
        for cand in ("utf-8", "shift_jis", "cp932"):
            try:
                return raw.decode(cand)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
    try:
        return raw.decode(enc)
    except UnicodeDecodeError:
        return raw.decode(enc, errors="replace")


def read_dbf(dbf_path: str) -> list[dict[str, Any]]:
    """Read a .dbf file into a list of ordered dicts (one per record)."""
    enc = _detect_encoding(dbf_path)
    with open(dbf_path, "rb") as fh:
        data = fh.read()

    n_records = struct.unpack("<I", data[4:8])[0]
    header_size = struct.unpack("<H", data[8:10])[0]
    record_size = struct.unpack("<H", data[10:12])[0]

    # Field descriptors run from byte 32 until a 0x0D terminator.
    fields = []
    pos = 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\x00")[0].decode("ascii", errors="replace")
        ftype = chr(data[pos + 11])
        flen = data[pos + 16]
        fdec = data[pos + 17]
        fields.append((name, ftype, flen, fdec))
        pos += 32

    records = []
    start = header_size
    for i in range(n_records):
        rec = data[start + i * record_size: start + (i + 1) * record_size]
        if not rec or rec[:1] == b"\x1a":
            break
        deleted = rec[:1] == b"*"
        off = 1
        row: dict[str, Any] = {}
        for name, ftype, flen, fdec in fields:
            raw = rec[off:off + flen]
            off += flen
            text = _decode(raw, enc).strip()
            if ftype in ("N", "F"):
                if text == "":
                    val: Any = None
                else:
                    try:
                        val = int(text) if fdec == 0 and "." not in text else float(text)
                    except ValueError:
                        val = None
            elif ftype == "L":
                val = True if text in ("Y", "y", "T", "t") else (False if text in ("N", "n", "F", "f") else None)
            else:  # C (character) and anything else
                val = text
            row[name] = val
        row["_deleted"] = deleted
        records.append(row)
    return records


def dbf_field_names(dbf_path: str) -> list[str]:
    with open(dbf_path, "rb") as fh:
        data = fh.read(2048)
    fields = []
    pos = 32
    while pos < len(data) and data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\x00")[0].decode("ascii", errors="replace")
        fields.append(name)
        pos += 32
    return fields


# --------------------------------------------------------------------------- #
# SHP (geometry) reader  -- Polygon (type 5) and PolyLine (type 3) supported
# --------------------------------------------------------------------------- #

SHAPE_TYPES = {
    0: "Null", 1: "Point", 3: "PolyLine", 5: "Polygon",
    8: "MultiPoint", 11: "PointZ", 13: "PolyLineZ", 15: "PolygonZ",
}


@dataclass
class Shape:
    shape_type: int
    # For Polygon/PolyLine: list of rings; each ring is a list of (x, y) tuples.
    parts: list = field(default_factory=list)
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)  # xmin, ymin, xmax, ymax

    @property
    def is_polygon(self) -> bool:
        return self.shape_type in (5, 15)

    @property
    def is_line(self) -> bool:
        return self.shape_type in (3, 13)


def read_shp(shp_path: str) -> list[Shape]:
    """Read geometries from a .shp file. Supports Polygon/PolyLine/Point."""
    with open(shp_path, "rb") as fh:
        data = fh.read()

    file_type = struct.unpack("<i", data[32:36])[0]
    shapes: list[Shape] = []
    pos = 100  # skip 100-byte header
    n = len(data)
    while pos < n:
        # Record header (big-endian): record number, content length (16-bit words)
        if pos + 8 > n:
            break
        content_len = struct.unpack(">i", data[pos + 4:pos + 8])[0]
        pos += 8
        rec_end = pos + content_len * 2
        stype = struct.unpack("<i", data[pos:pos + 4])[0]

        if stype == 0:  # Null
            shapes.append(Shape(shape_type=0, parts=[], bbox=(0, 0, 0, 0)))
            pos = rec_end
            continue

        if stype in (5, 3, 15, 13):  # Polygon / PolyLine (+Z)
            box = struct.unpack("<4d", data[pos + 4:pos + 36])
            num_parts = struct.unpack("<i", data[pos + 36:pos + 40])[0]
            num_points = struct.unpack("<i", data[pos + 40:pos + 44])[0]
            pp = pos + 44
            part_index = list(struct.unpack(f"<{num_parts}i", data[pp:pp + 4 * num_parts]))
            pp += 4 * num_parts
            coords = struct.unpack(f"<{2 * num_points}d", data[pp:pp + 16 * num_points])
            pts = [(coords[2 * k], coords[2 * k + 1]) for k in range(num_points)]
            part_index.append(num_points)
            parts = [pts[part_index[j]:part_index[j + 1]] for j in range(num_parts)]
            shapes.append(Shape(shape_type=stype, parts=parts, bbox=tuple(box)))
        elif stype in (1, 11):  # Point
            x, y = struct.unpack("<2d", data[pos + 4:pos + 20])
            shapes.append(Shape(shape_type=stype, parts=[[(x, y)]], bbox=(x, y, x, y)))
        else:
            shapes.append(Shape(shape_type=stype, parts=[], bbox=(0, 0, 0, 0)))
        pos = rec_end
    return shapes


# --------------------------------------------------------------------------- #
# Combined reader
# --------------------------------------------------------------------------- #

def read_prj(shp_path: str) -> str:
    prj = os.path.splitext(shp_path)[0] + ".prj"
    if os.path.exists(prj):
        return open(prj, "r", encoding="ascii", errors="replace").read().strip()
    return ""


def crs_from_prj_text(prj_text: str) -> str:
    """Map a few known GSJ PRJ strings to an EPSG code string."""
    t = prj_text.upper()
    if "JGD_2000" in t or "JGD2000" in t:
        return "EPSG:4612"  # JGD2000 geographic
    if "JGD_2011" in t or "JGD2011" in t:
        return "EPSG:6668"  # JGD2011 geographic
    if "WGS_1984" in t or "WGS84" in t:
        return "EPSG:4326"
    if "TOKYO" in t and "GCS" in t:
        return "EPSG:4301"  # Tokyo datum
    return "UNKNOWN"


def read_shapefile(shp_path: str) -> tuple[list[Shape], list[dict], str, int]:
    """Read a shapefile triple. Returns (shapes, records, crs, shape_type)."""
    shapes = read_shp(shp_path)
    dbf_path = os.path.splitext(shp_path)[0] + ".dbf"
    records = read_dbf(dbf_path) if os.path.exists(dbf_path) else [{} for _ in shapes]
    crs = crs_from_prj_text(read_prj(shp_path))
    stype = shapes[0].shape_type if shapes else 0
    return shapes, records, crs, stype


if __name__ == "__main__":
    import sys
    shapes, records, crs, stype = read_shapefile(sys.argv[1])
    print(f"shapes={len(shapes)} records={len(records)} crs={crs} type={SHAPE_TYPES.get(stype, stype)}")
    if records:
        print("fields:", list(records[0].keys()))
