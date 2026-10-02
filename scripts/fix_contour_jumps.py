"""Split contours where separate pieces of a level were joined by a chord.

The original contouring stitched separate pieces of the same level into one
polyline, producing long straight lines across the terrain (the "stripes").
A segment is a chord when it is longer than MAX_SEG or when the terrain
along it deviates more than MAX_DEV from the contour level. Fixes both
data/contours.json (viewer) and the 3D contour DXF (source of the 2D export).
"""
import json
import numpy as np
import ezdxf
from scipy.ndimage import map_coordinates

MAX_SEG = 12.0  # m; real segments are <= ~12 m, chords are 12-541 m
MAX_DEV = 0.5   # m
DXF = "Tumlehed_Lilla_1_18_Hojdkurvor_3D.dxf"

g = json.load(open("data/grid.json"))
Z = np.array(g["elevations"]).reshape(g["ny"], g["nx"])
ox, oy = g["origin"]
step = g["step"]


def is_chord(a, b, level):
    """a, b: absolute (x, y)."""
    length = np.hypot(b[0] - a[0], b[1] - a[1])
    if length > MAX_SEG:
        return True
    t = np.linspace(0, 1, max(3, int(length / step) + 2))[1:-1]
    cols = (a[0] + (b[0] - a[0]) * t - ox) / step
    rows = (a[1] + (b[1] - a[1]) * t - oy) / step
    z = map_coordinates(Z, [rows, cols], order=1, mode="nearest")
    return np.abs(z - level).max() > MAX_DEV


def split(pts, level, to_abs):
    """Split a point list at chords; drop pieces with fewer than 2 points."""
    pieces, cur = [], [pts[0]]
    for p0, p1 in zip(pts, pts[1:]):
        if is_chord(to_abs(p0), to_abs(p1), level):
            pieces.append(cur)
            cur = []
        cur.append(p1)
    pieces.append(cur)
    return [p for p in pieces if len(p) >= 2]


# --- viewer data (relative coordinates) -----------------------------------------
contours = json.load(open("data/contours.json"))
out = []
for c in contours:
    pieces = split(c["pts"], c["z"], lambda p: (ox + p[0], oy + p[1]))
    out += [dict(c, pts=p) for p in pieces]
json.dump(out, open("data/contours.json", "w"))
print(f"contours.json: {len(contours)} -> {len(out)} polylines")

# --- 3D DXF ---------------------------------------------------------------------
doc = ezdxf.readfile(DXF)
msp = doc.modelspace()
before = after = 0
for e in list(msp.query("POLYLINE")):
    pts = [tuple(p) for p in e.points()]
    pieces = split(pts, pts[0][2], lambda p: p)
    before += 1
    after += len(pieces)
    if len(pieces) == 1 and len(pieces[0]) == len(pts):
        continue
    layer = e.dxf.layer
    msp.delete_entity(e)
    for p in pieces:
        msp.add_polyline3d(p, dxfattribs={"layer": layer})
doc.saveas(DXF)
print(f"{DXF}: {before} -> {after} polylines")
