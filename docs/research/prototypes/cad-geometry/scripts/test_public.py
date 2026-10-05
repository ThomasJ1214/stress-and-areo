"""Test 6: real-world public CAD files (OCCT sample data), inertia transform check, gmsh conformal tet mesh."""
import os, sys, json, time, io, contextlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
import analytic as A
from occ_util import *
from OCP.BRepCheck import BRepCheck_Analyzer

ROOT = os.path.join(os.path.dirname(__file__), "..")
RES = {}

# ------------------------------------------------------------- public files
for fn in ("screw.step", "linkrods.step", "bearing.iges"):
    p = f"{ROOT}/public/{fn}"
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        shp = read_step(p) if fn.endswith("step") else read_iges(p)
    t_read = time.perf_counter() - t0
    sols = solids(shp)
    t0 = time.perf_counter(); valid = bool(BRepCheck_Analyzer(shp).IsValid()); t_chk = time.perf_counter() - t0
    t0 = time.perf_counter(); Vb, cb, Ib = volume_props(shp); t_mp = time.perf_counter() - t0
    bb = trimesh.Trimesh()
    t0 = time.perf_counter(); V, F, fid = tessellate(shp, 0.01, 0.3, relative=True); t_tess = time.perf_counter() - t0
    m = trimesh.Trimesh(V, F, process=False); m.merge_vertices()
    m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()
    parts = m.split(only_watertight=False)
    RES[fn] = dict(size_MB=os.path.getsize(p) / 1e6, t_read=t_read, n_solids=len(sols), n_faces=int(fid.max() + 1) if len(fid) else 0,
                   brep_valid=valid, t_check=t_chk, V_brep=Vb, t_massprops=t_mp, t_tess_rel0_01=t_tess, tris=len(m.faces),
                   mesh_watertight=bool(m.is_watertight), V_mesh=float(m.volume),
                   dV_mesh_vs_brep=float((m.volume - Vb) / Vb) if Vb else None,
                   extents=[float(e) for e in m.extents])

# ------------------------------------------------------------- inertia transform check  I' = R I R^T, c' = R c + t
f = A.FIN
fin = make_fin(A.trapezoid_fin_pts(f["cr"], f["ct"], f["s"], f["m"]), f["t"])
V0, c0, I0 = volume_props(fin)
R = Rotation.random(random_state=7).as_matrix(); t = np.array([12.3, -45.6, 789.0])
tr = gp_Trsf()
tr.SetValues(*R[0], t[0], *R[1], t[1], *R[2], t[2])
fin2 = BRepBuilderAPI_Transform(fin, tr, True).Shape()
V1, c1, I1 = volume_props(fin2)
RES["inertia_transform_check"] = dict(dV=float(V1 - V0), dc=float(np.linalg.norm(c1 - (R @ c0 + t))),
                                      dI_rel=float(np.linalg.norm(I1 - R @ I0 @ R.T) / np.linalg.norm(I0)))

# ------------------------------------------------------------- gmsh: conformal tet mesh of the payload assembly by part name
import gmsh
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0); gmsh.option.setNumber("General.NumThreads", 2)
gmsh.model.add("payload")
t0 = time.perf_counter()
ents = gmsh.model.occ.importShapes(f"{ROOT}/step/payload_assembly.step")
gmsh.model.occ.synchronize()
names = {tg: gmsh.model.getEntityName(3, tg).split("/")[-1] for d, tg in ents if d == 3}
out, omap = gmsh.model.occ.fragment(ents, [])       # make touching parts share faces (conformal mesh)
gmsh.model.occ.synchronize()
for (d, tg), children in zip(ents, omap):
    if d == 3:
        gmsh.model.addPhysicalGroup(3, [c[1] for c in children if c[0] == 3], name=names[tg])
gmsh.option.setNumber("Mesh.MeshSizeMax", 4.0)
gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
gmsh.option.setNumber("Mesh.ElementOrder", 2)
gmsh.model.mesh.generate(3)
t_mesh = time.perf_counter() - t0
et, etags, _ = gmsh.model.mesh.getElements(3)
ntet = sum(len(x) for x in etags)
nn = len(gmsh.model.mesh.getNodes()[0])
vol_by_name = {}
for d, pg in gmsh.model.getPhysicalGroups(3):
    nm = gmsh.model.getPhysicalName(d, pg)
    vol_by_name[nm] = sum(gmsh.model.occ.getMass(3, e) for e in gmsh.model.getEntitiesForPhysicalGroup(d, pg))
gmsh.write(f"{ROOT}/out/payload_tet10.msh")
gmsh.finalize()
RES["gmsh_tet10_payload"] = dict(t=t_mesh, n_tet10=ntet, n_nodes=nn, physical_groups=vol_by_name)

print(json.dumps(RES, indent=1, default=float))
json.dump(RES, open(f"{ROOT}/out/test_public.json", "w"), indent=1, default=float)
