"""Build one simplified terrain surface (TIN) from the 2 m height grid.

  1. smooth the grid (3x3 median kills single-cell spikes, gaussian removes
     2-cell noise); sea is clamped to 0 m (RH2000)
  2. adaptive TIN by greedy insertion until max |error| <= TOL vs the
     smoothed grid: many triangles on cliffs, few on flat ground
  3. write
     - Tumlehed_Lilla_1_18_Terrang.xyz: TIN vertices "E N Z" for Archicad's
       "Place Mesh from Surveyors Data" (one native, editable Mesh)
     - Tumlehed_Lilla_1_18_Terrang_3D.dxf: the same TIN as ONE POLYFACE MESH,
       with the 1945 plots, Lilleby 4:8 and boundary markers draped on it

Covers the full grid rectangle on purpose: Archicad re-triangulates the
XYZ points over their convex hull, so a concave clip would get filled with
long bogus triangles.
Convert to DWG with ODA File Converter (see export_2d_cad.py).
"""
import json
import numpy as np
import ezdxf
from ezdxf import zoom
from ezdxf.render import MeshBuilder
from scipy.ndimage import gaussian_filter, median_filter
from scipy.spatial import ConvexHull, Delaunay

TOL = 0.15          # m, max vertical deviation from the smoothed grid
DXF_OUT = "Tumlehed_Lilla_1_18_Terrang_3D.dxf"
XYZ_OUT = "Tumlehed_Lilla_1_18_Terrang.xyz"

g = json.load(open("data/grid.json"))
Zraw = np.array(g["elevations"]).reshape(g["ny"], g["nx"])
ox, oy = g["origin"]
step = g["step"]
ny, nx = Zraw.shape
XX, YY = np.meshgrid(ox + np.arange(nx) * step, oy + np.arange(ny) * step)

# --- 1. smoothing -----------------------------------------------------------
Z = gaussian_filter(median_filter(Zraw, size=3), sigma=0.8)
Z = np.maximum(Z, 0.0)

pts_xy = np.column_stack([XX.ravel(), YY.ravel()])
pts_z = Z.ravel()
raw_z = Zraw.ravel()
n = len(pts_z)


def interp(tri, xy, zv):
    """Linear interpolation of vertex heights zv on triangulation tri."""
    s = tri.find_simplex(xy)
    ok = s >= 0
    out = np.full(len(xy), np.nan)
    T = tri.transform[s[ok]]
    b = np.einsum("ijk,ik->ij", T[:, :2], xy[ok] - T[:, 2])
    w = np.column_stack([b, 1 - b.sum(1)])
    out[ok] = (zv[tri.simplices[s[ok]]] * w).sum(1)
    return out


# --- 2. greedy-insertion TIN --------------------------------------------------
# seed: rectangle border + coarse lattice, then add the worst point per
# violating triangle until every grid point is within TOL
sel = np.zeros(n, bool)
sel[ConvexHull(pts_xy).vertices] = True
border = (XX == XX.min()) | (XX == XX.max()) | (YY == YY.min()) | (YY == YY.max())
sel[np.flatnonzero(border.ravel())[::5]] = True
sel[::40] = True
for _ in range(200):
    tri = Delaunay(pts_xy[sel])
    err = np.abs(interp(tri, pts_xy, pts_z[sel]) - pts_z)
    err[sel] = 0
    if err.max() <= TOL:
        break
    simplex = tri.find_simplex(pts_xy)
    bad = np.flatnonzero(err > TOL)
    seen, add = set(), []
    for i in bad[np.argsort(-err[bad])]:
        if simplex[i] not in seen:
            seen.add(simplex[i])
            add.append(i)
    sel[add] = True

tri = Delaunay(pts_xy[sel])
V = np.column_stack([pts_xy[sel], pts_z[sel]])
F = tri.simplices.copy()
a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
cw = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]) < 0
F[cw] = F[cw][:, ::-1]  # normals up

zi = interp(tri, pts_xy, pts_z[sel])
err_s, err_r = np.abs(zi - pts_z), np.abs(zi - raw_z)
print(f"{len(V)} vertices, {len(F)} triangles; error vs smoothed max {err_s.max():.2f} m, "
      f"vs raw mean {err_r.mean():.2f} / p95 {np.percentile(err_r, 95):.2f} / max {err_r.max():.2f} m")

# --- 3a. XYZ for Archicad -------------------------------------------------------
np.savetxt(XYZ_OUT, V, fmt="%.3f", delimiter=" ")

# --- 3b. DXF: one polyface + draped plots and markers ----------------------------
def drape(xy):
    return interp(tri, np.asarray(xy, float), pts_z[sel])


doc = ezdxf.new("R2013")
doc.units = ezdxf.units.M
doc.header["$INSUNITS"] = 6
msp = doc.modelspace()
for name, color in [("TERRANG", 8), ("TOMTER_1945", 1), ("LILLEBY_4_8", 5),
                    ("TOMTBETECKNINGAR", 3), ("GRANSPUNKTER", 1)]:
    doc.layers.add(name, color=color)

mb = MeshBuilder()
mb.vertices = [tuple(v) for v in V]
mb.faces = [tuple(int(i) for i in f) for f in F]
mb.render_polyface(msp, dxfattribs={"layer": "TERRANG"})

for p in json.load(open("data/parcels.json")):
    if not (p["is_1945"] or p["is_lilleby"]):
        continue
    layer = "LILLEBY_4_8" if p["is_lilleby"] else "TOMTER_1945"
    for ring in p["rings"]:
        xy = np.array([(ox + x, oy + y) for x, y in ring])
        dense = [xy[0]]  # 2 m steps so the line follows the surface
        for p0, p1 in zip(xy, xy[1:]):
            k = max(1, int(np.hypot(*(p1 - p0)) // 2))
            dense += [p0 + (p1 - p0) * i / k for i in range(1, k + 1)]
        dense = np.array(dense)
        z = drape(dense)
        ok = ~np.isnan(z)
        if ok.sum() >= 2:
            msp.add_polyline3d([(x, y, zz + 0.05) for (x, y), zz in zip(dense[ok], z[ok])],
                               dxfattribs={"layer": layer})
    if p["is_1945"]:
        cx, cy = np.array(p["rings"][0])[:-1].mean(0) + (ox, oy)
        cz = drape([[cx, cy]])[0]
        if not np.isnan(cz):
            msp.add_text(p["etikett"], height=2.0, dxfattribs={"layer": "TOMTBETECKNINGAR"}
                         ).set_placement((cx, cy, cz + 0.5))

for m in json.load(open("data/markers.json")):
    z = drape([[m["x_abs"], m["y_abs"]]])[0]
    if not np.isnan(z):
        msp.add_point((m["x_abs"], m["y_abs"], z), dxfattribs={"layer": "GRANSPUNKTER"})
        msp.add_circle((m["x_abs"], m["y_abs"], z), 0.6, dxfattribs={"layer": "GRANSPUNKTER"})

zoom.extents(msp)
doc.saveas(DXF_OUT)
print("wrote", DXF_OUT, "and", XYZ_OUT)
