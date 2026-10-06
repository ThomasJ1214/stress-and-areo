"""netgen (pip netgen-mesher 6.2.2608) STEP import + fluid domain + 3D boundary layer test."""
import os, time, math
os.environ["OMP_NUM_THREADS"] = "1"
from netgen.occ import *
from collections import Counter
rocket = OCCGeometry("meshes/rocket.step").shape
rocket.faces.name = "wall"
print("rocket bbox", rocket.bounding_box, "faces", len(rocket.faces))
box = Box(Pnt(-0.6, -1.2, -1.2), Pnt(2.5, 1.2, 1.2)); box.faces.name = "farfield"
fluid = box - rocket
geo = OCCGeometry(fluid)
from netgen.meshing import BoundaryLayerParameters
h1, ratio, N = 4e-5, 1.2, 10
th = [h1 * ratio ** i for i in range(N)]
cum = [sum(th[:i + 1]) for i in range(N)]
t = time.time()
try:
    mesh = geo.GenerateMesh(maxh=0.15, grading=0.3,
                            boundary_layers=[BoundaryLayerParameters(boundary="wall", thickness=th, new_material="bl")])
    print(f"mesh with boundary layer OK: {mesh.ne} elements, {len(mesh.Points())} points, {time.time()-t:.1f}s")
except Exception as ex:
    print("boundary layer FAILED:", ex)
    raise
print(Counter(str(el.type) for el in mesh.Elements3D()))
import numpy as np, pyvista as pv
P = np.array([p.p for p in mesh.Points()])
cells, types = [], []
for el in mesh.Elements3D():
    v = [int(x.nr) - 1 for x in el.vertices]
    if len(v) == 4:
        cells += [4] + v; types.append(pv.CellType.TETRA)
    elif len(v) == 6:
        cells += [6] + v; types.append(pv.CellType.WEDGE)
g = pv.UnstructuredGrid(np.array(cells), np.array(types, dtype=np.uint8), P)
g.save("meshes/ng_bl.vtu")
print("saved meshes/ng_bl.vtu", g)
