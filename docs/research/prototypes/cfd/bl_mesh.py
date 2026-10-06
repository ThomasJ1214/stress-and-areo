"""3D prismatic boundary-layer mesh around the finned cone-cylinder with gmsh.

gmsh's 'BoundaryLayer' *field* is 2D-only (verified: no SurfacesList option in 4.15.2), so 3D prism layers
are produced with gmsh.model.geo.extrudeBoundaryLayer() on the (discrete) wall surface mesh:
  1. OCC solid of the rocket -> 2D wall mesh (sizes like make_mesh.py)
  2. reload the wall mesh as discrete surfaces, extrude N prism layers along averaged mesh normals
  3. build a farfield box with the built-in kernel, volume = box minus BL top surface, tet mesh
  4. export SU2 (markers nose/body/fins/base/farfield)

python bl_mesh.py out.su2 [sf=3.0] [h1=4e-5] [N=10] [ratio=1.2] [--small-domain]
"""
import math
import sys
import time

import gmsh
import numpy as np

out = sys.argv[1]
args = [a for a in sys.argv[2:] if not a.startswith("--")]
sf = float(args[0]) if len(args) > 0 else 3.0
h1 = float(args[1]) if len(args) > 1 else 4e-5
N = int(args[2]) if len(args) > 2 else 10
ratio = float(args[3]) if len(args) > 3 else 1.2
small = "--small-domain" in sys.argv

R, LN, L, CR, SPAN, T = 0.05, 0.30, 1.0, 0.12, 0.08, 0.004
X_LE_ROOT, X_LE_TIP = L - CR, 0.94
if small:
    X0, X1, Y = -0.6, 2.5, 1.2
else:
    X0, X1, Y = -6.0, 12.0, 6.0

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)
gmsh.option.setNumber("General.NumThreads", 1)

# ---------- step 1: wall mesh of the rocket solid ----------
gmsh.model.add("walls")
occ = gmsh.model.occ
R_TIP = 0.00025; X_TIP = R_TIP * LN / R   # meplat: a true OCC apex gives a non-manifold surface mesh
parts = [(3, occ.addCone(X_TIP, 0, 0, LN - X_TIP, 0, 0, R_TIP, R)), (3, occ.addCylinder(LN, 0, 0, L - LN, 0, 0, R))]
r_in = 0.9 * R
slope = (X_LE_TIP - X_LE_ROOT) / SPAN
pts = [(X_LE_ROOT - slope * (R - r_in), r_in), (L, r_in), (L, R + SPAN), (X_LE_TIP, R + SPAN)]
for ang in [45.0, 135.0, 225.0, 315.0]:
    p = [occ.addPoint(x, -T / 2, r) for (x, r) in pts]
    lt = [occ.addLine(p[i], p[(i + 1) % 4]) for i in range(4)]
    s = occ.addPlaneSurface([occ.addCurveLoop(lt)])
    vol = [e for e in occ.extrude([(2, s)], 0, T, 0) if e[0] == 3]
    occ.rotate(vol, 0, 0, 0, 1, 0, 0, math.radians(ang - 90.0))
    parts += vol
rocket, _ = occ.fuse([parts[0]], parts[1:])
occ.synchronize()
walls = [t for (d, t) in gmsh.model.getBoundary(rocket, oriented=False)]


def classify(tag):
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, tag)
    rmax = max(abs(ymin), abs(ymax), abs(zmin), abs(zmax))
    if xmax <= LN + 1e-4 and rmax <= R + 1e-4:
        return "nose"
    if abs(xmin - L) < 1e-6 and abs(xmax - L) < 1e-6:
        return "base"
    if rmax <= R + 1e-4:
        return "body"
    return "fins"


wall_group = {t: classify(t) for t in walls}
f = gmsh.model.mesh.field
fd = f.add("Distance"); f.setNumbers(fd, "SurfacesList", [t for t in walls if wall_group[t] == "fins"])
fe = f.add("MathEval"); f.setString(fe, "F", f"{0.003*sf} + 0.15*F{fd}")
fb = f.add("MathEval"); f.setString(fb, "F", f"{0.006*sf}")
fm = f.add("Min"); f.setNumbers(fm, "FieldsList", [fe, fb])
f.setAsBackgroundMesh(fm)
for k, v in {"Mesh.MeshSizeExtendFromBoundary": 0, "Mesh.MeshSizeFromPoints": 0, "Mesh.MeshSizeFromCurvature": 16,
             "Mesh.MeshSizeMin": 2e-4, "Mesh.Algorithm": 6}.items():
    gmsh.option.setNumber(k, v)
gmsh.model.mesh.generate(2)
# store wall triangles per group (node coords + connectivity)
tris = {}
nodeTags, coord, _ = gmsh.model.mesh.getNodes()
X = coord.reshape(-1, 3)
idx = {int(t): i for i, t in enumerate(nodeTags)}
for t in walls:
    et, _, en = gmsh.model.mesh.getElements(2, t)
    conn = np.array([idx[int(n)] for n in en[0]]).reshape(-1, 3)
    tris.setdefault(wall_group[t], []).append(conn)
tris = {k: np.vstack(v) for k, v in tris.items()}
# orient all triangles outward (divergence theorem check per triangle is not possible -> use centroid rule
# for the convex-ish body: normal must point away from the axis or along +x on the base / -x nowhere)
allc = np.vstack(list(tris.values()))
print(f"[bl] wall triangles: {len(allc)}  wall nodes: {len(np.unique(allc))}")
gmsh.model.remove()

# ---------- step 2: discrete wall surfaces, oriented outward ----------
gmsh.model.add("bl")
used = np.unique(allc)
new_id = {int(o): i + 1 for i, o in enumerate(used)}
surf_tags = {}
ntag0 = 1
single = "--single" in sys.argv
if single:
    tris = {"wall": np.vstack(list(tris.values()))}
for k, (name, conn) in enumerate(tris.items()):
    s = gmsh.model.addDiscreteEntity(2)
    surf_tags[name] = s
    if k == 0:
        gmsh.model.mesh.addNodes(2, s, [new_id[int(o)] for o in used], X[used].ravel().tolist())
    c = conn.copy()
    # OCC solid boundary triangles are already consistently outward-oriented (verified: enclosed volume > 0);
    # only check the sign and the closure. (VTK auto-orient is NOT robust if the mesh has non-manifold edges.)
    from collections import Counter
    ecount = Counter()
    for t in c:
        for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ecount[(min(u, v), max(u, v))] += 1
    bad = sum(1 for v in ecount.values() if v != 2)
    P = X[c]
    vol6 = np.einsum("ij,ij->i", P[:, 0], np.cross(P[:, 1], P[:, 2])).sum()
    if vol6 < 0:
        c = c[:, [0, 2, 1]]
    print(f"[bl] {name}: {len(c)} tris, enclosed volume {abs(vol6)/6:.6e} m^3, non-manifold/open edges: {bad}")
    gmsh.model.mesh.addElementsByType(s, 2, [], [new_id[int(o)] for o in c.ravel()])
gmsh.model.mesh.reclassifyNodes()
if not single:
    gmsh.model.mesh.createTopology()   # boundary curves/points between the discrete wall patches
print("[bl] topology:", {d: len(gmsh.model.getEntities(d)) for d in range(3)})

# ---------- step 3: extrude BL ----------
heights = [h1]
for i in range(1, N):
    heights.append(heights[-1] + h1 * ratio ** i)
print(f"[bl] layers={N} h1={h1:g} ratio={ratio} total={heights[-1]:.4e} m")
gmsh.option.setNumber("Geometry.ExtrudeReturnLateralEntities", 0)
t0 = time.time()
wall_ents = gmsh.model.getEntities(2)
ext = gmsh.model.geo.extrudeBoundaryLayer(wall_ents, [1] * N, heights, True)
gmsh.model.geo.synchronize()
top = [e for e in ext if e[0] == 2]
bl_vols = [e[1] for e in ext if e[0] == 3]
print(f"[bl] extrusion: {len(top)} top surfaces, {len(bl_vols)} BL volumes")

# farfield box (built-in kernel)
g = gmsh.model.geo
P = [g.addPoint(x, y, z) for x in (X0, X1) for y in (-Y, Y) for z in (-Y, Y)]
def ln(a, b): return g.addLine(P[a], P[b])
# vertices index: i = 4*ix + 2*iy + iz
edges = {}
for a in range(8):
    for b in range(a + 1, 8):
        d = a ^ b
        if d in (1, 2, 4):
            edges[(a, b)] = ln(a, b)
def E(a, b): return edges[(a, b)] if (a, b) in edges else -edges[(b, a)]
faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
far_s = []
for fc in faces:
    cl = g.addCurveLoop([E(fc[i], fc[(i + 1) % 4]) for i in range(4)])
    far_s.append(g.addPlaneSurface([cl]))
outer = g.addSurfaceLoop(far_s)
inner = g.addSurfaceLoop([t[1] for t in top])
vol = g.addVolume([outer, inner])
g.synchronize()

# sizes in the tet region
f = gmsh.model.mesh.field
fd = f.add("Distance"); f.setNumbers(fd, "SurfacesList", [t[1] for t in top]); f.setNumber(fd, "Sampling", 20)
fe = f.add("MathEval"); f.setString(fe, "F", f"{0.006*sf} + 0.15*F{fd}")
fc = f.add("MathEval"); f.setString(fc, "F", "0.6")
fm = f.add("Min"); f.setNumbers(fm, "FieldsList", [fe, fc])
f.setAsBackgroundMesh(fm)
gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
gmsh.option.setNumber("Mesh.Algorithm3D", 1)

def classify_disc(tag):
    nt, xyz, _ = gmsh.model.mesh.getNodes(2, tag, includeBoundary=True)
    P = np.asarray(xyz).reshape(-1, 3)
    rmax = np.hypot(P[:, 1], P[:, 2]).max()
    if P[:, 0].max() <= LN + 1e-4 and rmax <= R + 1e-4: return "nose"
    if np.ptp(P[:, 0]) < 1e-6 and abs(P[0, 0] - L) < 1e-6: return "base"
    if rmax <= R + 1e-4: return "body"
    return "fins"
grp = {}
for (_, t) in wall_ents:
    grp.setdefault("wall" if single else classify_disc(t), []).append(t)
print("[bl] wall patches per marker:", {k: len(v) for k, v in grp.items()})
for name, ss in grp.items():
    pg = gmsh.model.addPhysicalGroup(2, ss); gmsh.model.setPhysicalName(2, pg, name)
pg = gmsh.model.addPhysicalGroup(2, far_s); gmsh.model.setPhysicalName(2, pg, "farfield")
pg = gmsh.model.addPhysicalGroup(3, bl_vols + [vol]); gmsh.model.setPhysicalName(3, pg, "fluid")

t1 = time.time()
gmsh.model.mesh.generate(3)
print(f"[bl] 3D meshing {time.time()-t1:.1f}s")
etypes, etags, _ = gmsh.model.mesh.getElements(3)
for et, tg in zip(etypes, etags):
    name = gmsh.model.mesh.getElementProperties(et)[0]
    q = np.asarray(gmsh.model.mesh.getElementQualities(tg, "minSICN"))
    vq = np.asarray(gmsh.model.mesh.getElementQualities(tg, "volume"))
    print(f"[bl]   {name}: n={len(tg)} minSICN min={q.min():.4g} p1={np.percentile(q,1):.4g} "
          f"mean={q.mean():.4f} nonpositive={int((q<=0).sum())} negvol={int((vq<=0).sum())}")
print(f"[bl] nodes={len(gmsh.model.mesh.getNodes()[0])}")
gmsh.option.setNumber("Mesh.SaveAll", 0)
gmsh.write(out)
gmsh.finalize()
print("[bl] wrote", out)
