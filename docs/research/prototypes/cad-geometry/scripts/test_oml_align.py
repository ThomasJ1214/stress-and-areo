"""Test 5: boolean union, outer-skin (OML) extraction, unit inference and alignment of an imported part."""
import os, sys, json, time, io, contextlib, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
import analytic as A
from occ_util import *
from xcaf_util import read_xcaf
from oml import oml_brep, oml_mesh, to_manifold
import align as AL

ROOT = os.path.join(os.path.dirname(__file__), "..")
STEP, STL = f"{ROOT}/step", f"{ROOT}/stl"
RES = {}
oml_ref = A.payload_oml_analytic()
V_tube_mat = math.pi * (40 ** 2 - 38 ** 2) * 250


def mesh_of(shape, d=0.02, a=0.2):
    V, F, _ = tessellate(shape, d, a)
    m = trimesh.Trimesh(V, F, process=False); m.merge_vertices()
    return m


leaves = read_xcaf(f"{STEP}/payload_assembly.step")
byname = {inst if not inst.startswith("=>") else proto: s for inst, proto, s in leaves}
all_parts = list(byname.values())
open_parts = [byname[k] for k in ("body_tube", "sled", "battery", "camera_shroud")]
plugs = [make_cyl_x(38.0, 0.0, 0.5), make_cyl_x(38.0, 249.5, 250.0)]   # interface caps (inside the bore)

# ------------------------------------------------------------- B-rep OML
for label, parts, pl in (("closed (bulkheads)", all_parts, ()), ("open tube, no plugs", open_parts, ()),
                         ("open tube + interface plugs", open_parts, plugs)):
    t0 = time.perf_counter()
    oml, info = oml_brep(parts, pl)
    t = time.perf_counter() - t0
    V, c, I = volume_props(oml)
    RES[f"brep_oml/{label}"] = dict(**info, t=t, V=V, V_ref=oml_ref.V, dV_rel=(V - oml_ref.V) / oml_ref.V,
                                    dc_mm=float(np.linalg.norm(c - oml_ref.c)),
                                    dI_rel=float(np.linalg.norm(I - oml_ref.I) / np.linalg.norm(oml_ref.I)),
                                    wetted_area_incl_end_caps=surface_area(oml))
    if label == "closed (bulkheads)":
        oml_closed = oml
        write_step(oml, f"{STEP}/payload_oml.step") if True else None

# exact wetted area: cylinder side - shroud footprint + shroud outer faces (excl. end caps at x=0,250)
# (reported for reference by the B-rep result; analytic below)
w = 10.0; Ro = 40.0; zt = 50.0; Lsh = 50.0
zb = math.sqrt(Ro ** 2 - w ** 2)
phi = 2 * math.asin(w / Ro)
A_cyl_side = 2 * math.pi * Ro * 250 - Ro * phi * Lsh
A_shroud = Lsh * 2 * w + 2 * Lsh * (zt - zb) + 2 * (2 * w * zt - (zb * w + Ro ** 2 * math.asin(w / Ro)) )
# shroud end faces: area between z=zb..zt and arc: = int_{-w}^{w} (zt - sqrt(Ro^2-y^2)) dy
A_end = 2 * w * zt - (w * math.sqrt(Ro ** 2 - w ** 2) + Ro ** 2 * math.asin(w / Ro))
A_shroud = Lsh * 2 * w + 2 * Lsh * (zt - zb) + 2 * A_end
RES["wetted_area_exact_no_end_caps"] = A_cyl_side + A_shroud
RES["end_caps_area"] = 2 * math.pi * Ro ** 2

import resource; print("STAGE", '# ----------------------------------------------------------', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, "MB", flush=True)
# ------------------------------------------------------------- mesh (manifold3d) OML
meshes = {k: mesh_of(s) for k, s in byname.items()}
for label, keys, pl in (("closed (bulkheads)", list(byname), ()),
                        ("open tube + interface plugs", ["body_tube", "sled", "battery", "camera_shroud"],
                         [mesh_of(p) for p in plugs])):
    t0 = time.perf_counter()
    oml_m, info = oml_mesh([meshes[k] for k in keys], pl)
    t = time.perf_counter() - t0
    RES[f"mesh_oml/{label}"] = dict(**info, t=t, V=float(oml_m.volume), dV_rel=float((oml_m.volume - oml_ref.V) / oml_ref.V),
                                    watertight=bool(oml_m.is_watertight), tris=len(oml_m.faces))
    if label == "closed (bulkheads)":
        oml_m.export(f"{STL}/payload_oml.stl")
        oml_mesh_closed = oml_m

import resource; print("STAGE", '# ----------------------------------------------------------', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, "MB", flush=True)
# ------------------------------------------------------------- voxel flood-fill fallback (dirty meshes)
asm_soup = trimesh.util.concatenate(list(meshes.values()))
for pitch in (3.0, 2.0) if os.environ.get('VOXEL', '1') == '1' else ():
    print("voxel pitch", pitch, flush=True)
    t0 = time.perf_counter()
    vg = asm_soup.voxelized(pitch).fill()
    mc = vg.marching_cubes
    mc.apply_transform(vg.transform)
    t = time.perf_counter() - t0
    RES[f"voxel_oml/pitch={pitch}"] = dict(t=t, V=float(mc.volume), dV_rel=float((mc.volume - oml_ref.V) / oml_ref.V),
                                           V_voxels=float(vg.volume), dVvox_rel=float((vg.volume - oml_ref.V) / oml_ref.V))

import resource; print("STAGE", '# ----------------------------------------------------------', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, "MB", flush=True)
# ------------------------------------------------------------- boolean union timing (B-rep vs mesh)
t0 = time.perf_counter(); u = fuse_all_ = None
from oml import fuse_all
u = fuse_all(all_parts); t_b = time.perf_counter() - t0
t0 = time.perf_counter()
import manifold3d as mf
um = mf.Manifold.batch_boolean([to_manifold(m) for m in meshes.values()], mf.OpType.Add)
t_m = time.perf_counter() - t0
RES["union/brep_fuse_8parts"] = dict(t=t_b, V=volume_props(u)[0], nsolids=len(solids(u)))
RES["union/manifold_8parts"] = dict(t=t_m, V=um.volume(), tris_in=sum(len(m.faces) for m in meshes.values()), tris_out=um.num_tri())

import resource; print("STAGE", '# ----------------------------------------------------------', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, "MB", flush=True)
# ------------------------------------------------------------- alignment + unit inference
rng = np.random.default_rng(42)
cases = []
for unit, s in (("in", 25.4), ("m", 1000.0), ("mm", 1.0), ("cm", 10.0)):
    Rt = Rotation.random(random_state=int(rng.integers(1e6))).as_matrix()
    tt = rng.uniform(-500, 500, 3)
    cases.append((unit, s, Rt, tt))

def circle_center(P):
    # algebraic (Kasa) circle fit of the fore-end ring vertices: x^2+y^2 + D x + E y + F = 0
    A_ = np.c_[P[:, 0], P[:, 1], np.ones(len(P))]
    b_ = -(P ** 2).sum(1)
    D_, E_, F_ = np.linalg.lstsq(A_, b_, rcond=None)[0]
    return np.array([-D_ / 2, -E_ / 2])


R_or, L_or, x_fore = 40.0, 250.0, 600.0      # OR body-tube component: OD 80, L 250, fore end at x=600 mm
for unit, s, Rt, tt in cases:
    m = oml_mesh_closed.copy()
    T_true = np.eye(4); T_true[:3, :3] = Rt / s; T_true[:3, 3] = tt / s     # rocket(mm, origin fore) -> native
    m.apply_transform(T_true)
    p = f"{STL}/payload_oml_pose_{unit}.stl"; m.export(p)
    mn = trimesh.load(p)
    t0 = time.perf_counter()
    T, rep, m_fit = AL.fit_to_component(mn, R_or, L_or, x_fore)
    t = time.perf_counter() - t0
    # truth: recovered axis vs true axis direction (sign-insensitive), axis offset, axial placement
    a_true_native = Rt[:, 0]
    a_fit_native = np.linalg.inv(T[:3, :3]) @ np.array([1.0, 0, 0]); a_fit_native /= np.linalg.norm(a_fit_native)
    ang = math.degrees(math.acos(min(1.0, abs(a_true_native @ a_fit_native))))
    # map the analytic OML (rocket frame) through truth then through fit -> compare bounding geometry
    v = m_fit.vertices
    RES[f"align/OML payload in '{unit}'"] = dict(
        t=t, unit_inferred=rep["unit"], unit_confident=rep["unit_confident"], axis_angle_err_deg=ang,
        R_fit_mm=rep["R_fit_mm"], dR_mm=rep["dR_mm"], L_fit_mm=rep["L_fit_mm"],
        x_range_after=[float(v[:, 0].min()), float(v[:, 0].max())],
        radial_center_offset_mm=float(np.hypot(*circle_center(v[np.abs(v[:, 0] - x_fore) < 1e-3][:, 1:]))),
        direction_ambiguous=rep["direction_ambiguous"], inertia_axis=rep["inertia_axis"])

import resource; print("STAGE", '# nose cone: direction resolved', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, "MB", flush=True)
# nose cone: direction resolved by profile matching against the OR ogive profile
o = A.OGIVE
rho_, yfun = A.tangent_ogive(o["L"], o["R"])
nst = 60
prof_or = np.array([yfun(min(o["L"], (i + 1) / nst * o["L"])) for i in range(nst)])
with contextlib.redirect_stdout(io.StringIO()):
    og = read_step(f"{STEP}/ogive_solid.step")
mo = mesh_of(og, 0.05, 0.3)
for k in range(3):
    Rt = Rotation.random(random_state=100 + k).as_matrix(); tt = rng.uniform(-300, 300, 3)
    m = mo.copy(); T_true = np.eye(4); T_true[:3, :3] = Rt / 25.4; T_true[:3, 3] = tt / 25.4
    m.apply_transform(T_true)
    T, rep, m_fit = AL.fit_to_component(m, o["R"], o["L"], 0.0, r_profile_or=prof_or)
    v = m_fit.vertices
    tip = v[np.argmin(v[:, 0])]
    RES[f"align/ogive nose (inch, random pose {k})"] = dict(
        unit=rep["unit"], direction_scores=rep["direction_scores"], direction_ambiguous=rep["direction_ambiguous"],
        tip_at=[float(x) for x in tip], base_r=float(np.hypot(v[:, 1], v[:, 2])[v[:, 0] > o["L"] - 1].max()),
        dR_mm=rep["dR_mm"], dL_mm=rep["L_fit_mm"] - o["L"])

print(json.dumps(RES, indent=1, default=float))
json.dump(RES, open(f"{ROOT}/out/test_oml_align.json", "w"), indent=1, default=float)
