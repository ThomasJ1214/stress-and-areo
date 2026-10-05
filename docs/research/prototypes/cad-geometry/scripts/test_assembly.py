"""Test 2b: multi-solid payload assembly import (names, instancing, units) + composite mass props."""
import os, sys, json, time, io, contextlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import analytic as A
from occ_util import *

from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
try:
    from OCP.TDF import TDF_LabelSequence  # OCP 7.x
except ImportError:
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence  # OCP 8.x
from OCP.STEPCAFControl import STEPCAFControl_Reader

STEP = os.path.join(os.path.dirname(__file__), "..", "step")
RES = {}
parts_ref, comp_ref = A.payload_analytic()
RHO = {n: rho for (n, k, p, rho) in A.PAYLOAD}
RHO["threaded_rod"] = 7850.0


from xcaf_util import read_xcaf, label_name


def composite_from(parts):
    mp = []
    for proto, (V, c, I) in parts:
        rho = RHO[proto]
        mp.append(A.MassProps(V * 1e-9 * rho, c * 1e-3, I * 1e-15 * rho))
    return A.combine(mp)


def cmp(comp):
    return dict(mass_kg=comp.V, dm_rel=(comp.V - comp_ref.V) / comp_ref.V,
                dcg_mm=float(np.linalg.norm(comp.c - comp_ref.c) * 1e3),
                dI_rel_fro=float(np.linalg.norm(comp.I - comp_ref.I) / np.linalg.norm(comp_ref.I)))


for fn in ("payload_assembly.step", "payload_assembly_inch.step"):
    t0 = time.perf_counter()
    leaves = read_xcaf(f"{STEP}/{fn}")
    t_read = time.perf_counter() - t0
    names = [(a, b) for a, b, _ in leaves]
    props = [(proto, volume_props(s)) for _, proto, s in leaves]
    comp = composite_from(props)
    RES[f"OCP-XCAF/{fn}"] = dict(**cmp(comp), t_read=t_read, leaves=names)
    # per-part check against analytic
    per = {}
    for (inst, proto, s), (_, (V, c, I)) in zip(leaves, props):
        key = inst if inst in parts_ref else proto
        if key in parts_ref:
            pr = parts_ref[key]
            per[key] = dict(dV_rel=(V - pr.V) / pr.V, dc_mm=float(np.linalg.norm(c - pr.c)))
    RES[f"OCP-XCAF/{fn}/per_part"] = per

# ------------------------------------------------------------- plain reader (no names)
with contextlib.redirect_stdout(io.StringIO()):
    sh = read_step(f"{STEP}/payload_assembly.step")
RES["OCP-plain/payload"] = dict(nsolids=len(solids(sh)), V_total=sum(volume_props(s)[0] for s in solids(sh)))

# ------------------------------------------------------------- gmsh
import gmsh
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
for fn in ("payload_assembly.step", "payload_assembly_inch.step"):
    gmsh.clear()
    t0 = time.perf_counter()
    ents = gmsh.model.occ.importShapes(f"{STEP}/{fn}")
    gmsh.model.occ.synchronize()
    t_read = time.perf_counter() - t0
    vols = [tg for d, tg in ents if d == 3]
    nm = [gmsh.model.getEntityName(3, tg) for tg in vols]
    props = []
    for tg, n in zip(vols, nm):
        proto = n.split("/")[-1] if n else None
        if proto in ("rod_left", "rod_right"):
            proto = "threaded_rod"
        props.append((proto, (gmsh.model.occ.getMass(3, tg), np.array(gmsh.model.occ.getCenterOfMass(3, tg)),
                              np.array(gmsh.model.occ.getMatrixOfInertia(3, tg)).reshape(3, 3))))
    try:
        comp = cmp(composite_from(props))
    except KeyError as e:
        comp = dict(error=f"name lookup failed: {e}")
    RES[f"gmsh/{fn}"] = dict(**comp, t_read=t_read, names=nm)
gmsh.finalize()

# ------------------------------------------------------------- build123d
import build123d as bd
t0 = time.perf_counter()
c = bd.import_step(f"{STEP}/payload_assembly.step")
t_read = time.perf_counter() - t0
leaf = list(c.leaves) if hasattr(c, "leaves") else []
RES["build123d/payload"] = dict(t_read=t_read, type=type(c).__name__, label=getattr(c, "label", None),
                                leaves=[(getattr(x, "label", None), round(x.volume, 3)) for x in leaf],
                                n_solids=len(c.solids()))

# ------------------------------------------------------------- trimesh / cascadio
import trimesh
t0 = time.perf_counter()
sc = trimesh.load(f"{STEP}/payload_assembly.step")
t_read = time.perf_counter() - t0
RES["trimesh-cascadio/payload"] = dict(t_read=t_read, geometry_names=list(sc.geometry.keys()),
                                       graph_nodes=[n for n in sc.graph.nodes_geometry])

print(json.dumps(RES, indent=1, default=float))
json.dump(RES, open(os.path.join(os.path.dirname(__file__), "..", "out", "test_assembly.json"), "w"), indent=1, default=float)
