"""
Minimal OGC GeoPackage writer (pure Python, sqlite3 from the standard library).

A GeoPackage is an SQLite database with a small set of required metadata tables
plus one table per feature layer whose geometry column holds "GeoPackageBinary"
blobs (a short header followed by standard OGC WKB).

This writer implements just what the prototype needs: MultiPolygon feature layers
in a geographic CRS (default JGD2000 / EPSG:4612). The output opens directly in
QGIS and other GIS software. It is deliberately dependency-free because GDAL /
geopandas are not available in the build environment.

Only polygon layers are written here; attribute columns are typed as TEXT, REAL,
or INTEGER based on Python values.
"""

from __future__ import annotations

import sqlite3
import struct

APP_ID = 0x47504B47  # 'GPKG'


def _signed_area_deg(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def parts_to_polygons(parts):
    """Group shapefile rings into polygons (outer + holes) by orientation.

    Shapefile outer rings are clockwise (negative shoelace), holes are CCW.
    """
    polygons = []
    current = None
    for ring in parts:
        if len(ring) < 4:
            # ensure closed ring of >=4 pts; skip degenerate
            if len(ring) < 3:
                continue
        area = _signed_area_deg(ring)
        if area < 0 or current is None:  # outer ring
            current = [ring]
            polygons.append(current)
        else:  # hole
            current.append(ring)
    return polygons


def polygon_wkb_multipolygon(parts) -> bytes:
    """Encode shapefile polygon parts as little-endian WKB MultiPolygon."""
    polys = parts_to_polygons(parts)
    out = bytearray()
    out += struct.pack("<BI", 1, 6)          # byte order LE, type 6 = MultiPolygon
    out += struct.pack("<I", len(polys))
    for rings in polys:
        out += struct.pack("<BI", 1, 3)      # Polygon
        out += struct.pack("<I", len(rings))
        for ring in rings:
            r = list(ring)
            if r[0] != r[-1]:
                r = r + [r[0]]               # close ring
            out += struct.pack("<I", len(r))
            for x, y in r:
                out += struct.pack("<2d", float(x), float(y))
    return bytes(out)


def gpkg_geom_blob(parts, srs_id: int) -> bytes:
    """GeoPackageBinary: 'GP' + version + flags + srs_id + WKB (no envelope)."""
    header = struct.pack("<2sBBi", b"GP", 0, 0x01, srs_id)  # LE header, no envelope
    return header + polygon_wkb_multipolygon(parts)


def _sql_type(values):
    has_float = False
    for v in values:
        if v is None or v == "":
            continue
        if isinstance(v, bool):
            return "INTEGER"
        if isinstance(v, float):
            has_float = True
        elif not isinstance(v, int):
            return "TEXT"
    return "REAL" if has_float else "INTEGER"


def write_gpkg(path: str, layers: dict, srs_id: int = 4612,
               srs_org: str = "EPSG", srs_wkt: str = ""):
    """Write one or more polygon feature layers to a GeoPackage.

    layers: { layer_name: { "rows": [ {attr: value, ..., "_parts": parts} ] } }
            Each row must contain "_parts" (shapefile rings); other keys are
            attribute columns. Geometry is stored under column "geom".
    """
    import os
    import tempfile
    # Build on local disk first: SQLite is unreliable on networked/mounted FS.
    tmpfd, tmppath = tempfile.mkstemp(suffix=".gpkg")
    os.close(tmpfd)
    os.remove(tmppath)
    con = sqlite3.connect(tmppath)
    cur = con.cursor()
    cur.execute(f"PRAGMA application_id = {APP_ID};")
    cur.execute("PRAGMA user_version = 10300;")

    # --- required metadata tables ---
    cur.execute("""CREATE TABLE gpkg_spatial_ref_sys (
        srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY,
        organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
        definition TEXT NOT NULL, description TEXT);""")
    cur.execute("""CREATE TABLE gpkg_contents (
        table_name TEXT PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
        description TEXT DEFAULT '', last_change TEXT, min_x DOUBLE, min_y DOUBLE,
        max_x DOUBLE, max_y DOUBLE, srs_id INTEGER);""")
    cur.execute("""CREATE TABLE gpkg_geometry_columns (
        table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL,
        srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
        PRIMARY KEY (table_name, column_name));""")

    # mandatory SRS rows + our CRS
    base_srs = [
        ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
        ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
        ("WGS 84 geodetic", 4326, "EPSG", 4326,
         'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
         'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]', None),
    ]
    if srs_id not in (-1, 0, 4326):
        wkt = srs_wkt or ('GEOGCS["JGD2000",DATUM["Japanese_Geodetic_Datum_2000",'
                          'SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],'
                          'UNIT["degree",0.0174532925199433]]')
        base_srs.append((f"{srs_org}:{srs_id}", srs_id, srs_org, srs_id, wkt, "map CRS"))
    cur.executemany("INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)", base_srs)

    for layer_name, spec in layers.items():
        rows = spec["rows"]
        attr_keys = [k for k in (rows[0].keys() if rows else []) if k != "_parts"]
        col_defs = []
        for k in attr_keys:
            t = _sql_type([r.get(k) for r in rows])
            col_defs.append(f'"{k}" {t}')
        cols_sql = ", ".join(col_defs)
        cur.execute(
            f'CREATE TABLE "{layer_name}" (fid INTEGER PRIMARY KEY AUTOINCREMENT, '
            f'geom BLOB{", " + cols_sql if cols_sql else ""});')

        minx = miny = float("inf")
        maxx = maxy = float("-inf")
        insert_cols = ["geom"] + [f'"{k}"' for k in attr_keys]
        placeholders = ",".join(["?"] * len(insert_cols))
        sql = f'INSERT INTO "{layer_name}" ({",".join(insert_cols)}) VALUES ({placeholders})'
        for r in rows:
            parts = r["_parts"]
            blob = gpkg_geom_blob(parts, srs_id)
            for ring in parts:
                for x, y in ring:
                    minx, miny = min(minx, x), min(miny, y)
                    maxx, maxy = max(maxx, x), max(maxy, y)
            vals = [blob] + [_coerce(r.get(k)) for k in attr_keys]
            cur.execute(sql, vals)

        if minx == float("inf"):
            minx = miny = maxx = maxy = 0.0
        cur.execute(
            "INSERT INTO gpkg_contents VALUES (?,?,?,?,datetime('now'),?,?,?,?,?)",
            (layer_name, "features", layer_name, layer_name, minx, miny, maxx, maxy, srs_id))
        cur.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
            (layer_name, "geom", "MULTIPOLYGON", srs_id, 0, 0))

    con.commit()
    con.close()
    _publish(tmppath, path)


def _publish(tmppath: str, path: str):
    """Copy a locally-built SQLite/GPKG file onto the (possibly networked) mount.

    The mount may forbid deletes, so we overwrite by writing bytes, and we blank
    any stale -journal / -wal sidecars so SQLite does not treat them as hot."""
    import os
    with open(tmppath, "rb") as fh:
        data = fh.read()
    with open(path, "wb") as fh:
        fh.write(data)
    for side in ("-journal", "-wal", "-shm"):
        sp = path + side
        if os.path.exists(sp):
            try:
                open(sp, "wb").close()  # truncate to 0 bytes -> not a hot journal
            except Exception:
                pass
    try:
        os.remove(tmppath)
    except Exception:
        pass


def _coerce(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (list, dict)):
        import json
        return json.dumps(v, ensure_ascii=False)
    return v
