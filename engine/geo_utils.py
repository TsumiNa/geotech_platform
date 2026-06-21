"""
Lightweight geometry utilities (pure Python / math only).

All polygon inputs use the shapefile convention from ``shapefile_io.Shape``:
a list of rings, each ring a list of (lon, lat) tuples in decimal degrees
(JGD2000 ~ WGS84 for these purposes). Outer rings are clockwise, holes
counter-clockwise per the shapefile spec, but for screening-level point-in-
polygon and area we treat all rings as boundaries and subtract holes by sign.

Distances and areas are approximate. We use a local equirectangular projection
about a reference latitude to convert degrees to metres, which is accurate
enough for a 1:50,000 desktop-screening tool over a single map sheet.
"""

from __future__ import annotations

import math

EARTH_R = 6371000.0  # mean Earth radius (m)
DEG = math.pi / 180.0


def deg_to_m(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """Local equirectangular projection (metres) about (lon0, lat0)."""
    x = (lon - lon0) * DEG * EARTH_R * math.cos(lat0 * DEG)
    y = (lat - lat0) * DEG * EARTH_R
    return x, y


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    dlat = (lat2 - lat1) * DEG
    dlon = (lon2 - lon1) * DEG
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * DEG) * math.cos(lat2 * DEG) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def ring_area_m2(ring: list[tuple[float, float]], lat0: float) -> float:
    """Signed planar area (m^2) of a ring using a local projection."""
    if len(ring) < 3:
        return 0.0
    lon0 = ring[0][0]
    pts = [deg_to_m(lon, lat, lon0, lat0) for lon, lat in ring]
    s = 0.0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        s += x1 * y2 - x2 * y1
    # close
    x1, y1 = pts[-1]
    x2, y2 = pts[0]
    s += x1 * y2 - x2 * y1
    return s / 2.0


def polygon_area_m2(parts: list[list[tuple[float, float]]], lat0: float | None = None) -> float:
    """Area of a polygon (outer rings positive, holes subtracted via sign)."""
    if not parts:
        return 0.0
    if lat0 is None:
        lat0 = parts[0][0][1]
    total = 0.0
    for ring in parts:
        total += ring_area_m2(ring, lat0)
    return abs(total)


def point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test (lon/lat space, fine for screening)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-300) + xi):
            inside = not inside
        j = i
    return inside


def point_in_polygon(x: float, y: float, parts: list[list[tuple[float, float]]]) -> bool:
    """Point-in-polygon honouring holes (odd-even across all rings)."""
    inside = False
    for ring in parts:
        if point_in_ring(x, y, ring):
            inside = not inside
    return inside


def bbox_of_parts(parts) -> tuple[float, float, float, float]:
    xs = [p[0] for ring in parts for p in ring]
    ys = [p[1] for ring in parts for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_bbox(x, y, box, pad=0.0) -> bool:
    return (box[0] - pad) <= x <= (box[2] + pad) and (box[1] - pad) <= y <= (box[3] + pad)


def _dist_point_seg_m(px, py, ax, ay, bx, by, lon0, lat0) -> float:
    """Distance (m) from point P to segment AB, in local metres."""
    pX, pY = deg_to_m(px, py, lon0, lat0)
    aX, aY = deg_to_m(ax, ay, lon0, lat0)
    bX, bY = deg_to_m(bx, by, lon0, lat0)
    dx, dy = bX - aX, bY - aY
    if dx == 0 and dy == 0:
        return math.hypot(pX - aX, pY - aY)
    t = ((pX - aX) * dx + (pY - aY) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = aX + t * dx, aY + t * dy
    return math.hypot(pX - cx, pY - cy)


def distance_to_boundary_m(x: float, y: float, parts) -> float:
    """Minimum distance (m) from a point to a polygon's boundary rings."""
    lon0, lat0 = x, y
    best = float("inf")
    for ring in parts:
        for i in range(len(ring) - 1):
            ax, ay = ring[i]
            bx, by = ring[i + 1]
            d = _dist_point_seg_m(x, y, ax, ay, bx, by, lon0, lat0)
            if d < best:
                best = d
    return best


# --------------------------------------------------------------------------- #
# Line / corridor sampling
# --------------------------------------------------------------------------- #

def sample_line(lat1, lon1, lat2, lon2, step_m=50.0):
    """Return list of (lon, lat) samples along a great-circle-ish straight line."""
    total = haversine_m(lon1, lat1, lon2, lat2)
    n = max(2, int(total / step_m) + 1)
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t))
    return pts, total
