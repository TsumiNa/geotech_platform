"""
Small IO helpers used across the pipeline: CSV / JSON writing, a SQLite mirror of
the processed tables, and a best-effort Parquet writer.

Parquet note: the build environment has no pyarrow / fastparquet (and no network
to install them), so `write_parquet` will normally be unavailable. In that case
the pipeline still produces the same data as CSV *and* in a real SQLite database
(`database/tokyo_geotech_geology.sqlite`) plus the GeoPackage, which together are
fully query-ready. Run `python src/export_parquet.py` once a Parquet engine is
installed to materialise the .parquet deliverables from the CSVs.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def write_csv(path: str, rows: list[dict], columns: list[str] | None = None):
    ensure_dir(os.path.dirname(path))
    if not rows:
        # still write header if columns given
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            if columns:
                csv.writer(fh).writerow(columns)
        return
    cols = columns or list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _csv_val(r.get(k)) for k in cols})


def _csv_val(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return ""
    return v


def write_json(path: str, obj):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def write_parquet(path: str, rows: list[dict]) -> bool:
    """Try to write Parquet via pandas. Returns True on success, False if no engine."""
    try:
        import pandas as pd
        df = pd.DataFrame([{k: _csv_val(v) for k, v in r.items()} for r in rows])
        df.to_parquet(path, index=False)
        return True
    except Exception:
        return False


def write_sqlite(db_path: str, tables: dict):
    """Write attribute tables to a SQLite DB (geometry stored as WKT text).

    tables: { table_name: [ row_dict, ... ] }  -- values are scalars/JSON strings.
    """
    ensure_dir(os.path.dirname(db_path))
    import tempfile
    # Build on local disk first: SQLite is unreliable on networked/mounted FS.
    tmpfd, tmppath = tempfile.mkstemp(suffix=".sqlite")
    os.close(tmpfd)
    os.remove(tmppath)
    con = sqlite3.connect(tmppath)
    cur = con.cursor()
    for name, rows in tables.items():
        cur.execute(f'DROP TABLE IF EXISTS "{name}"')
        if not rows:
            continue
        cols = list(rows[0].keys())
        col_sql = ", ".join(f'"{c}" TEXT' for c in cols)
        cur.execute(f'CREATE TABLE "{name}" ({col_sql})')
        ph = ",".join(["?"] * len(cols))
        cur.executemany(
            f'INSERT INTO "{name}" VALUES ({ph})',
            [[_sqlite_val(r.get(c)) for c in cols] for r in rows],
        )
    con.commit()
    con.close()
    from gpkg_writer import _publish
    _publish(tmppath, db_path)


def _sqlite_val(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return None
    return v if isinstance(v, (int, float, str)) else str(v)
