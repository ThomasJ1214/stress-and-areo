"""Test 2: re-import STEP/IGES with OCP, OCP-XCAF, gmsh, build123d, trimesh(cascadio); compare mass props."""
import os, sys, json, time, io, contextlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import analytic as A
from occ_util import *

STEP = os.path.join(os.path.dirname(__file__), "..", "step")
RES = {}


def err(V, c, I, ref, Lref):
    return dict(V=V, dV_rel=(V - ref.V) / ref.V,
                dc_over_L=float(np.linalg.norm(c - ref.c) / Lref),
                dI_rel_fro=float(np.linalg.norm(I - ref.I) / np.linalg.norm(ref.I)))


o, f, t = A.OGIVE, A.FIN, A.TUBE
REF = {
    "ogive_solid": (A.ogive_solid(o["L"], o["R"]), o["L"]),
    "ogive_hollow": (A.ogive_hollow_vertical(o["L"], o["R"], o["t"])[0], o["L"]),
    "fin": (A.fin_plate(A.trapezoid_fin_pts(f["cr"], f["ct"], f["s"], f["m"]), f["t"])[0], f["cr"]),
    "tube": (A.hollow_cyl_x(t["Ro"], t["Ri"], 0, t["L"]), t["L"]),
}

# ------------------------------------------------------------- OCP plain reader
quiet = contextlib.redirect_stdout(io.StringIO())
for name, (ref, L) in REF.items():
    for ext in ("step", "iges"):
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            shp = read_step(f"{STEP}/{name}.step") if ext == "step" else read_iges(f"{STEP}/{name}.iges")
        t_read = time.perf_counter() - t0
        t0 = time.perf_counter(); V, c, I = volume_props(shp); t_mp = time.perf_counter() - t0
        RES[f"OCP/{ext}/{name}"] = dict(**err(V, c, I, ref, L), t_read=t_read, t_massprops=t_mp, nsolids=len(solids(shp)))
        V, c, I = volume_props(shp, gk_tol=1e-9)
        RES[f"OCP-GK1e-9/{ext}/{name}"] = err(V, c, I, ref, L)

# fin written in inches: OCP reader converts to its session unit (mm by default)
with contextlib.redirect_stdout(io.StringIO()):
    shp = read_step(f"{STEP}/fin_inch.step")
V, c, I = volume_props(shp)
RES["OCP/step/fin_inch(read back)"] = err(V, c, I, REF["fin"][0], f["cr"])

# ------------------------------------------------------------- gmsh
import gmsh
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
for name, (ref, L) in REF.items():
    for ext in ("step", "iges"):
        gmsh.clear()
        t0 = time.perf_counter()
        ents = gmsh.model.occ.importShapes(f"{STEP}/{name}.{ext}")
        gmsh.model.occ.synchronize()
        t_read = time.perf_counter() - t0
        vols = [tg for (d, tg) in ents if d == 3]
        tg = vols[0]
        V = gmsh.model.occ.getMass(3, tg)
        c = np.array(gmsh.model.occ.getCenterOfMass(3, tg))
        I = np.array(gmsh.model.occ.getMatrixOfInertia(3, tg)).reshape(3, 3)
        RES[f"gmsh/{ext}/{name}"] = dict(**err(V, c, I, ref, L), t_read=t_read, nvol=len(vols))
# unit handling: default vs OCCTargetUnit
for tu in ("", "M"):
    gmsh.clear()
    gmsh.option.setString("Geometry.OCCTargetUnit", tu)
    ents = gmsh.model.occ.importShapes(f"{STEP}/fin_inch.step")
    gmsh.model.occ.synchronize()
    V = gmsh.model.occ.getMass(3, ents[0][1])
    RES[f"gmsh/fin_inch OCCTargetUnit='{tu}'"] = dict(V=V, V_expected_mm3=REF['fin'][0].V)
gmsh.option.setString("Geometry.OCCTargetUnit", "")
gmsh.finalize()

# ------------------------------------------------------------- build123d
import build123d as bd
for name, (ref, L) in REF.items():
    t0 = time.perf_counter()
    s = bd.import_step(f"{STEP}/{name}.step")
    t_read = time.perf_counter() - t0
    V = s.volume
    c = np.array(tuple(s.center(bd.CenterOf.MASS)))
    try:
        I = np.array(s.matrix_of_inertia)
    except Exception as e:
        I = np.full((3, 3), np.nan)
    RES[f"build123d/step/{name}"] = dict(**err(V, c, I, ref, L), t_read=t_read)

# ------------------------------------------------------------- trimesh (cascadio STEP->GLB tessellation)
import trimesh
for name, (ref, L) in REF.items():
    t0 = time.perf_counter()
    sc = trimesh.load(f"{STEP}/{name}.step")
    t_read = time.perf_counter() - t0
    m = sc.to_geometry() if hasattr(sc, "to_geometry") else sc.dump(concatenate=True)
    units = str(getattr(sc, "units", None))
    m.apply_scale(1000.0 if units == "meters" else 1.0)   # cascadio emits metres
    wt0 = bool(m.is_watertight)
    m.merge_vertices(digits_vertex=4)                        # weld at 1e-4 mm
    RES[f"trimesh-cascadio/step/{name}"] = dict(**err(m.volume, m.center_mass, m.moment_inertia, ref, L),
                                                t_read=t_read, faces=len(m.faces), watertight_raw=wt0,
                                                watertight_after_weld=bool(m.is_watertight), units=units)

# ------------------------------------------------------------- detection of a corrupted STEP import
with contextlib.redirect_stdout(io.StringIO()):
    bad = read_step(f"{STEP}/ogive_hollow_badrevolve.step")
from OCP.BRepCheck import BRepCheck_Analyzer
import trimesh as _tm
Vb, cb, Ib = volume_props(bad)
v_, f_, _ = tessellate(bad, 0.01, 0.2)
mb = _tm.Trimesh(v_, f_)
mb.merge_vertices()
RES["detect/badrevolve"] = dict(brep_valid=bool(BRepCheck_Analyzer(bad).IsValid()), V_brep=Vb,
                                V_mesh=float(mb.volume), mesh_watertight=bool(mb.is_watertight), V_true=REF["ogive_hollow"][0].V)

print(json.dumps(RES, indent=1, default=float))
json.dump(RES, open(os.path.join(os.path.dirname(__file__), "..", "out", "test_import_singles.json"), "w"), indent=1, default=float)
