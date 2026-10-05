"""Test 3: tessellation (OCP BRepMesh, gmsh), watertightness, mesh mass properties vs analytic,
mesh-format round trips (STL/OBJ/PLY/3MF/GLB) with trimesh, numpy-stl, meshio, pyvista."""
import os, sys, json, time, io, contextlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import trimesh
import analytic as A
from occ_util import *

ROOT = os.path.join(os.path.dirname(__file__), "..")
STEP, STL = f"{ROOT}/step", f"{ROOT}/stl"
os.makedirs(STL, exist_ok=True)
RES = {}
o, f, t = A.OGIVE, A.FIN, A.TUBE
REF = {
    "ogive_solid": (A.ogive_solid(o["L"], o["R"]), o["L"]),
    "ogive_hollow": (A.ogive_hollow_vertical(o["L"], o["R"], o["t"])[0], o["L"]),
    "fin": (A.fin_plate(A.trapezoid_fin_pts(f["cr"], f["ct"], f["s"], f["m"]), f["t"])[0], f["cr"]),
    "tube": (A.hollow_cyl_x(t["Ro"], t["Ri"], 0, t["L"]), t["L"]),
}


def err(m, ref, L):
    return dict(dV_rel=float((m.volume - ref.V) / ref.V),
                dc_over_L=float(np.linalg.norm(m.center_mass - ref.c) / L),
                dI_rel_fro=float(np.linalg.norm(m.moment_inertia - ref.I) / np.linalg.norm(ref.I)))


def load_shape(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return read_step(f"{STEP}/{name}.step")


# ---------------------------------------------------------------- OCP BRepMesh convergence
for name, (ref, L) in REF.items():
    for defl, ang in [(0.5, 0.5), (0.1, 0.3), (0.02, 0.2), (0.01, 0.15)]:
        shp = load_shape(name)          # fresh shape (BRepMesh caches triangulation on the shape)
        t0 = time.perf_counter()
        V, F, fid = tessellate(shp, defl, ang)
        t_mesh = time.perf_counter() - t0
        m = trimesh.Trimesh(V, F, process=False)
        raw_wt = bool(m.is_watertight)
        m.merge_vertices()
        print("BRepMesh", name, defl, time.perf_counter() - t0, flush=True)
        RES[f"BRepMesh/{name}/d={defl}"] = dict(**err(m, ref, L), tris=len(m.faces), t_mesh=t_mesh,
                                                watertight_raw=raw_wt, watertight_welded=bool(m.is_watertight),
                                                winding_ok=bool(m.is_winding_consistent),
                                                euler=int(m.euler_number), n_faces_brep=int(fid.max() + 1))
        if defl == 0.02:
            m.export(f"{STL}/{name}.stl")

# ---------------------------------------------------------------- gmsh surface mesh
import gmsh
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
gmsh.option.setNumber("General.NumThreads", 2)
for name, (ref, L) in REF.items():
    for n_per_2pi in (30, 90):
        gmsh.clear()
        gmsh.model.occ.importShapes(f"{STEP}/{name}.step"); gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", n_per_2pi)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 10.0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.25)
        t0 = time.perf_counter()
        gmsh.model.mesh.generate(2)
        t_mesh = time.perf_counter() - t0
        nodeTags, coords, _ = gmsh.model.mesh.getNodes()
        P = coords.reshape(-1, 3)
        idx = {tg: i for i, tg in enumerate(nodeTags)}
        tris = []
        for (d, tg) in gmsh.model.getEntities(2):
            et, _, en = gmsh.model.mesh.getElements(2, tg)
            for e, nodes in zip(et, en):
                if e == 2:
                    tri = np.vectorize(idx.get)(nodes.reshape(-1, 3))
                    tris.append(tri)
        Fm = np.vstack(tris)
        m = trimesh.Trimesh(P, Fm, process=True)
        trimesh.repair.fix_normals(m)   # gmsh surface orientation follows the B-rep face param, not outward
        print("gmsh", name, n_per_2pi, t_mesh, flush=True)
        RES[f"gmsh2D/{name}/curv={n_per_2pi}"] = dict(**err(m, ref, L), tris=len(m.faces), t_mesh=t_mesh,
                                                       watertight=bool(m.is_watertight))
gmsh.finalize()

# ---------------------------------------------------------------- OCC StlAPI writer + readers
from OCP.StlAPI import StlAPI_Writer
shp = load_shape("ogive_solid")
BRepMesh_IncrementalMesh(shp, 0.02, False, 0.2, True)
w = StlAPI_Writer(); w.ASCIIMode = False
w.Write(shp, f"{STL}/ogive_solid_stlapi.stl")
ref, L = REF["ogive_solid"]
for reader in ("trimesh", "numpy-stl", "meshio", "pyvista"):
    t0 = time.perf_counter()
    if reader == "trimesh":
        m = trimesh.load(f"{STL}/ogive_solid_stlapi.stl")
        r = dict(**err(m, ref, L), watertight=bool(m.is_watertight), verts=len(m.vertices))
    elif reader == "numpy-stl":
        from stl import mesh as npstl
        mm = npstl.Mesh.from_file(f"{STL}/ogive_solid_stlapi.stl")
        vol, cog, inertia = mm.get_mass_properties()
        r = dict(dV_rel=float((vol - ref.V) / ref.V), dc_over_L=float(np.linalg.norm(cog - ref.c) / L),
                 dI_rel_fro=float(np.linalg.norm(inertia - ref.I) / np.linalg.norm(ref.I)),
                 note="numpy-stl: triangle soup, no topology/watertight check")
    elif reader == "meshio":
        import meshio
        mm = meshio.read(f"{STL}/ogive_solid_stlapi.stl")
        m = trimesh.Trimesh(mm.points, mm.cells_dict["triangle"])
        r = dict(**err(m, ref, L), watertight=bool(m.is_watertight), verts=len(mm.points),
                 note="meshio returns raw points (duplicated per triangle?)")
    else:
        import pyvista as pv
        pm = pv.read(f"{STL}/ogive_solid_stlapi.stl")
        r = dict(dV_rel=float((pm.volume - ref.V) / ref.V), n_points=pm.n_points,
                 open_edges=int(pm.extract_feature_edges(boundary_edges=True, feature_edges=False,
                                                         manifold_edges=False, non_manifold_edges=False).n_cells))
    r["t_read"] = time.perf_counter() - t0
    RES[f"STLread/{reader}"] = r

# ---------------------------------------------------------------- other mesh formats round trip (trimesh)
m0 = trimesh.load(f"{STL}/ogive_solid.stl")
for ext in ("obj", "ply", "off", "3mf", "glb"):
    p = f"{STL}/ogive_solid_rt.{ext}"
    try:
        m0.export(p)
        m1 = trimesh.load(p, force="mesh")
        RES[f"roundtrip/{ext}"] = dict(ok=True, dV_rel_vs_stl=float((m1.volume - m0.volume) / m0.volume),
                                       watertight=bool(m1.is_watertight), size=os.path.getsize(p))
    except Exception as e:
        RES[f"roundtrip/{ext}"] = dict(ok=False, error=repr(e)[:200])

print(json.dumps(RES, indent=1, default=float))
json.dump(RES, open(f"{ROOT}/out/test_tess.json", "w"), indent=1, default=float)
