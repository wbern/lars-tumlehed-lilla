"""Build a flat 2D DXF (all Z = 0) from the 3D contour DXF.

3D POLYLINEs become LWPOLYLINEs at elevation 0; texts and circles are
flattened. Contour heights stay readable via the HOJDKURVOR_TEXT labels.
Convert both DXFs to DWG with ODA File Converter (libredwg's dxf2dwg writes
DWGs with invalid handles):
  ODAFileConverter <dir with dxfs> <out dir> ACAD2013 DWG 0 1 "*.dxf"
"""
import sys
import ezdxf
from ezdxf import zoom

SRC = "Tumlehed_Lilla_1_18_Hojdkurvor_3D.dxf"
DST = "Tumlehed_Lilla_1_18_Hojdkurvor_2D.dxf"

src = ezdxf.readfile(SRC)
doc = ezdxf.new("R2000")
doc.units = ezdxf.units.M
doc.header["$INSUNITS"] = 6
msp = doc.modelspace()

for layer in src.layers:
    name = layer.dxf.name
    if name not in doc.layers:
        doc.layers.add(name, color=layer.dxf.color)

for e in src.modelspace():
    t = e.dxftype()
    layer = e.dxf.layer
    if t == "POLYLINE":
        pts = [(p[0], p[1]) for p in e.points()]
        msp.add_lwpolyline(pts, close=e.is_closed, dxfattribs={"layer": layer})
    elif t == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        msp.add_lwpolyline(pts, close=e.closed, dxfattribs={"layer": layer})
    elif t == "TEXT":
        x, y, _ = e.dxf.insert
        msp.add_text(e.dxf.text, height=e.dxf.height,
                     dxfattribs={"layer": layer, "insert": (x, y),
                                 "rotation": e.dxf.get("rotation", 0)})
    elif t == "CIRCLE":
        x, y, _ = e.dxf.center
        msp.add_circle((x, y), e.dxf.radius, dxfattribs={"layer": layer})
    else:
        sys.exit(f"unhandled entity type {t}")

zoom.extents(msp)
doc.saveas(DST)
print("wrote", DST, len(msp), "entities")
