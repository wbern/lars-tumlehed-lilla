"""Build a flat 2D DXF (all Z = 0) from the 3D contour DXF.

3D POLYLINEs become LWPOLYLINEs at elevation 0; texts and circles are
flattened. Contour heights stay readable via HOJDKURVOR_TEXT labels, which
are regenerated here: one label every LABEL_SPACING m along each index
contour (HOJDKURVOR_STOD, 2.5 m interval), rotated to follow the line.
The saved view opens on the contour area, not the 4 km property extents.
Convert both DXFs to DWG with ODA File Converter (libredwg's dxf2dwg writes
DWGs with invalid handles):
  ODAFileConverter <dir with dxfs> <out dir> ACAD2013 DWG 0 1 "*.dxf"
"""
import math
import sys
import ezdxf
from ezdxf import bbox, zoom
from ezdxf.enums import TextEntityAlignment

SRC = "Tumlehed_Lilla_1_18_Hojdkurvor_3D.dxf"
DST = "Tumlehed_Lilla_1_18_Hojdkurvor_2D.dxf"
LABEL_LAYER = "HOJDKURVOR_TEXT"
LABEL_SPACING = 100.0  # m along the contour between height labels
LABEL_MIN_LEN = 15.0   # contours shorter than this get no label
LABEL_HEIGHT = 1.5     # m (3 mm at 1:500)
VIEW_MARGIN = 30.0     # m around the contour area in the saved view

src = ezdxf.readfile(SRC)
doc = ezdxf.new("R2000")
doc.units = ezdxf.units.M
doc.header["$INSUNITS"] = 6
msp = doc.modelspace()

for layer in src.layers:
    name = layer.dxf.name
    if name not in doc.layers:
        doc.layers.add(name, color=layer.dxf.color)


def polyline_length(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_along(pts, target):
    """Return (x, y, angle_deg) at distance `target` along the polyline."""
    walked = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if seg == 0:
            continue
        if walked + seg >= target:
            f = (target - walked) / seg
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            if ang > 90 or ang <= -90:  # keep text readable (never upside down)
                ang += 180
            return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), ang
        walked += seg
    return pts[-1][0], pts[-1][1], 0.0


def add_contour_labels(pts, z):
    """Label an index contour every LABEL_SPACING m, centred within its length."""
    length = polyline_length(pts)
    if length < LABEL_MIN_LEN:
        return 0
    n = max(1, int(length // LABEL_SPACING))
    step = length / n
    for i in range(n):
        x, y, ang = point_along(pts, step * (i + 0.5))
        msp.add_text(f"{z:.1f}", height=LABEL_HEIGHT,
                     dxfattribs={"layer": LABEL_LAYER, "rotation": ang}
                     ).set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    return n


dropped = labels = 0
for e in src.modelspace():
    t = e.dxftype()
    layer = e.dxf.layer
    if t in ("POLYLINE", "LWPOLYLINE"):
        if t == "POLYLINE":
            raw = list(e.points())
            z = raw[0][2] if raw else 0.0
        else:
            raw = list(e.get_points("xy"))
            z = e.dxf.elevation
        pts = [(p[0], p[1]) for p in raw]
        if polyline_length(pts) == 0:  # zero-length fragments from contouring
            dropped += 1
            continue
        msp.add_lwpolyline(pts, close=e.is_closed if t == "POLYLINE" else e.closed,
                           dxfattribs={"layer": layer})
        if layer == "HOJDKURVOR_STOD":
            labels += add_contour_labels(pts, z)
    elif t == "TEXT":
        if layer == LABEL_LAYER:
            continue  # regenerated from the index contours above
        x, y, _ = e.dxf.insert
        msp.add_text(e.dxf.text, height=e.dxf.height,
                     dxfattribs={"layer": layer, "insert": (x, y),
                                 "rotation": e.dxf.get("rotation", 0)})
    elif t == "CIRCLE":
        x, y, _ = e.dxf.center
        msp.add_circle((x, y), e.dxf.radius, dxfattribs={"layer": layer})
    else:
        sys.exit(f"unhandled entity type {t}")

# Drawing extents = everything; saved view = the contour area so the plot is
# what you see when the file opens (the property boundaries span ~4 km).
ext = bbox.extents(msp)
msp.dxf.extmin = ext.extmin  # copied to $EXTMIN/$EXTMAX on save
msp.dxf.extmax = ext.extmax
contours = msp.query('LWPOLYLINE[layer=="HOJDKURVOR_STOD" | layer=="HOJDKURVOR_GRUND"]')
xs = [p[0] for e in contours for p in e.get_points("xy")]
ys = [p[1] for e in contours for p in e.get_points("xy")]
zoom.window(msp, (min(xs) - VIEW_MARGIN, min(ys) - VIEW_MARGIN),
            (max(xs) + VIEW_MARGIN, max(ys) + VIEW_MARGIN))
doc.saveas(DST)
print("wrote", DST, len(msp), "entities;", labels, "height labels;",
      dropped, "zero-length polylines dropped")
