"""Build a cone-cylinder rocket with 4 trapezoidal fins ("x" configuration) inside a cylindrical
farfield domain with gmsh (OpenCASCADE kernel), generate an unstructured tet mesh and export it in
SU2 format with named markers: nose, body, fins, base, farfield.

Usage: python make_mesh.py <out.su2> [size_factor=1.0] [--bl] [--nofins]
  size_factor scales all target sizes (2.0 = coarser, 0.7 = finer).
  --bl adds prismatic boundary-layer layers on all rocket walls (gmsh 'BoundaryLayer' field, 3D).
"""
import math
import sys
import time
import gmsh

out = sys.argv[1]
sf = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 1.0
use_bl = "--bl" in sys.argv
no_fins = "--nofins" in sys.argv
nthreads = 2

# ---------------- geometry (metres) ----------------
R = 0.05          # body radius (D = 0.1 m = reference length)
LN = 0.30         # conical nose length -> half-angle atan(0.05/0.30) = 9.4623 deg
L = 1.00          # overall length (nose tip at x=0, base at x=1)
CR, SPAN, T = 0.12, 0.08, 0.004   # fin root chord, span, thickness
X_LE_ROOT = L - CR                 # 0.88
X_LE_TIP = 0.94                    # LE sweep: tip LE at 0.94, TE unswept at base x=1.0
# farfield cylinder (large enough for subsonic runs as well)
X0, X1, RFAR = -6.0, 12.0, 6.0
if "--small-domain" in sys.argv:      # supersonic-only domain (no upstream influence) to save cells
    X0, X1, RFAR = -0.3, 1.8, 0.9

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)
gmsh.option.setNumber("General.NumThreads", nthreads)
gmsh.model.add("rocket")
occ = gmsh.model.occ

# NOTE: an OCC cone with a true apex (r1=0) yields duplicated/non-manifold triangles at the apex with every
# gmsh 2D algorithm (verified) -> HXT failure. Use a tiny flat tip (meplat) of radius R_TIP instead.
R_TIP = 0.00025
X_TIP = R_TIP * LN / R
cone = occ.addCone(X_TIP, 0, 0, LN - X_TIP, 0, 0, R_TIP, R)
cyl = occ.addCylinder(LN, 0, 0, L - LN, 0, 0, R)
parts = [(3, cone), (3, cyl)]

if not no_fins:
    # fin planform in the (x, r) half-plane, root embedded slightly into the body for a clean union
    r_in = 0.9 * R
    slope = (X_LE_TIP - X_LE_ROOT) / SPAN          # dx/dr along the leading edge
    x_le_in = X_LE_ROOT - slope * (R - r_in)
    pts = [(x_le_in, r_in), (L, r_in), (L, R + SPAN), (X_LE_TIP, R + SPAN)]
    for k, ang in enumerate([45.0, 135.0, 225.0, 315.0]):
        # build the fin in the x-z plane (r along +z), thickness along y, then rotate about x
        ptags = [occ.addPoint(x, -T / 2, r) for (x, r) in pts]
        ltags = [occ.addLine(ptags[i], ptags[(i + 1) % 4]) for i in range(4)]
        cl = occ.addCurveLoop(ltags)
        s = occ.addPlaneSurface([cl])
        ext = occ.extrude([(2, s)], 0, T, 0)
        vol = [e for e in ext if e[0] == 3]
        occ.rotate(vol, 0, 0, 0, 1, 0, 0, math.radians(ang - 90.0))
        parts += vol

rocket, _ = occ.fuse([parts[0]], parts[1:])
domain = occ.addCylinder(X0, 0, 0, X1 - X0, 0, 0, RFAR)
fluid, _ = occ.cut([(3, domain)], rocket)
occ.synchronize()

vols = gmsh.model.getEntities(3)
assert len(vols) == 1, vols
fluid_tag = vols[0][1]

# ---------------- classify boundary surfaces ----------------
groups = {"nose": [], "body": [], "fins": [], "base": [], "farfield": []}
eps = 1e-6
for (dim, tag) in gmsh.model.getBoundary([(3, fluid_tag)], oriented=False):
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(dim, tag)
    rmax = max(abs(ymin), abs(ymax), abs(zmin), abs(zmax))
    if xmin < X0 + 1e-3 or xmax > X1 - 1e-3 or rmax > RFAR - 1e-3:
        groups["farfield"].append(tag)
    elif xmax <= LN + 1e-4 and rmax <= R + 1e-4:
        groups["nose"].append(tag)
    elif abs(xmin - L) < 1e-6 and abs(xmax - L) < 1e-6:
        groups["base"].append(tag)
    elif rmax <= R + 1e-4:
        groups["body"].append(tag)
    else:
        groups["fins"].append(tag)
for name, tags in groups.items():
    print(f"[mesh] marker {name}: {len(tags)} surfaces")
    if tags:
        pg = gmsh.model.addPhysicalGroup(2, tags)
        gmsh.model.setPhysicalName(2, pg, name)
pg = gmsh.model.addPhysicalGroup(3, [fluid_tag])
gmsh.model.setPhysicalName(3, pg, "fluid")

wall_surfs = groups["nose"] + groups["body"] + groups["fins"] + groups["base"]

# ---------------- mesh size fields ----------------
h_body = 0.006 * sf
h_fin = 0.003 * sf
h_edge = 0.0015 * sf
h_tip = 0.0015 * sf
h_far = 0.6
growth = 0.12      # size increase per unit distance (approx. geometric growth ~ 1 + growth)
if "--uniform" in sys.argv:   # systematic refinement: scale ALL length scales incl. growth rate and far size
    growth = 0.06 * sf
    h_far = 0.3 * sf

f = gmsh.model.mesh.field
f_dw = f.add("Distance")
f.setNumbers(f_dw, "SurfacesList", wall_surfs)
f.setNumber(f_dw, "Sampling", 60)
f_body = f.add("MathEval")
f.setString(f_body, "F", f"{h_body} + {growth}*F{f_dw}")

fields = [f_body]
if groups["fins"]:
    f_df = f.add("Distance")
    f.setNumbers(f_df, "SurfacesList", groups["fins"])
    f.setNumber(f_df, "Sampling", 40)
    f_fin = f.add("MathEval")
    f.setString(f_fin, "F", f"{h_fin} + {growth}*F{f_df}")
    fields.append(f_fin)
    # fin edges (leading/trailing/tip edges) -> finest
    fin_curves = set()
    for t in groups["fins"]:
        for (_, c) in gmsh.model.getBoundary([(2, t)], oriented=False):
            fin_curves.add(abs(c))
    f_de = f.add("Distance")
    f.setNumbers(f_de, "CurvesList", sorted(fin_curves))
    f.setNumber(f_de, "Sampling", 100)
    f_edge = f.add("MathEval")
    f.setString(f_edge, "F", f"{h_edge} + {growth}*F{f_de}")
    fields.append(f_edge)
# nose tip (meplat edge curve) and conical shock layer: size ~ proportional to x (self-similar conical flow)
tip_curves = [t for (d, t) in gmsh.model.getEntities(1) if gmsh.model.getBoundingBox(1, t)[3] < 2 * X_TIP]
f_dt = f.add("Distance")
f.setNumbers(f_dt, "CurvesList", tip_curves)
f_tip = f.add("MathEval")
f.setString(f_tip, "F", f"{h_tip/3} + {growth}*F{f_dt}")
fields.append(f_tip)
f_fr = f.add("Frustum")
for k, v in dict(X1=-0.01, Y1=0, Z1=0, X2=LN + 0.02, Y2=0, Z2=0, R1_inner=0, R1_outer=0.02, R2_inner=0,
                 R2_outer=0.22, V1_inner=0.0008 * sf, V1_outer=0.0008 * sf, V2_inner=0.0066 * sf,
                 V2_outer=0.0066 * sf).items():
    f.setNumber(f_fr, k, v)
fields.append(f_fr)
# base edge / wake region just behind the base (Euler base flow) - moderate
f_box = f.add("Box")
f.setNumber(f_box, "VIn", 0.02 * sf)
f.setNumber(f_box, "VOut", h_far)
for k, v in dict(XMin=L, XMax=L + 0.5, YMin=-0.15, YMax=0.15, ZMin=-0.15, ZMax=0.15, Thickness=0.3).items():
    f.setNumber(f_box, k, v)
fields.append(f_box)
# NOTE: MathEval "Min(F1, c)" hangs gmsh 4.15 (verified) -> cap with a constant field inside a Min field
f_const = f.add("MathEval")
f.setString(f_const, "F", f"{h_far}")
fields.append(f_const)
f_min = f.add("Min")
f.setNumbers(f_min, "FieldsList", fields)
f.setAsBackgroundMesh(f_min)

gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
# curvature-based sizing is REQUIRED near the cone tip: without it the periodic cone surface gets
# duplicated triangles where the local radius < target size (verified failure mode) -> HXT/Delaunay fail
gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
gmsh.option.setNumber("Mesh.Algorithm", 6)       # Frontal-Delaunay 2D
gmsh.option.setNumber("Mesh.Algorithm3D", 10)    # HXT (parallel Delaunay)
gmsh.option.setNumber("Mesh.Optimize", 1)
gmsh.option.setNumber("Mesh.OptimizeNetgen", 0)

if use_bl:
    # 3D boundary layer: prisms extruded from the wall surfaces
    f_bl = f.add("BoundaryLayer")
    f.setNumbers(f_bl, "SurfacesList", wall_surfs)
    f.setNumber(f_bl, "Size", 2e-5)
    f.setNumber(f_bl, "Ratio", 1.25)
    f.setNumber(f_bl, "Thickness", 0.004)
    f.setNumber(f_bl, "Quads", 1)
    f.setAsBoundaryLayer(f_bl)

t0 = time.time()
stop_dim = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--dim=")), "3"))
for d in range(1, stop_dim + 1):
    ts = time.time()
    try:
        gmsh.model.mesh.generate(d)
    except Exception as ex:
        if d != 3:
            raise
        print(f"[mesh] 3D meshing failed: {ex}", flush=True)
        raise SystemExit(2)
    print(f"[mesh] generate({d}) done in {time.time()-ts:.1f}s", flush=True)
    if d == 2:
        print(f"[mesh] surface triangles on walls:", sum(len(gmsh.model.mesh.getElements(2, s)[1][0]) for s in wall_surfs), flush=True)
t1 = time.time()

# quality statistics
etypes, etags, _ = gmsh.model.mesh.getElements(3)
ncells = sum(len(t) for t in etags)
nodes, _, _ = gmsh.model.mesh.getNodes()
print(f"[mesh] elements3D={ncells}  nodes={len(nodes)}  time={t1 - t0:.1f}s")
for et, tg in zip(etypes, etags):
    name = gmsh.model.mesh.getElementProperties(et)[0]
    q = gmsh.model.mesh.getElementQualities(tg, "minSICN")
    import numpy as np
    q = np.asarray(q)
    print(f"[mesh]   {name}: n={len(tg)} minSICN min={q.min():.4f} p1={np.percentile(q,1):.4f} mean={q.mean():.4f} neg={int((q<=0).sum())}")

gmsh.option.setNumber("Mesh.SaveAll", 0)
gmsh.write(out)
if "--msh" in sys.argv:
    gmsh.write(out.replace(".su2", ".msh"))
gmsh.finalize()
print(f"[mesh] wrote {out}")
