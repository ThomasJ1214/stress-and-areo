"""Test 4: cross-sectional area distribution along the axis (B-rep exact vs mesh slicing) + timing."""
import os, sys, json, time, io, contextlib, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import trimesh
import manifold3d as mf
from scipy.integrate import quad
import analytic as A
from occ_util import *
from sections import slice_trimesh, slice_manifold, slice_brep, slice_parts

ROOT = os.path.join(os.path.dirname(__file__), "..")
STEP = f"{ROOT}/step"
RES = {}


def load(path):
    with contextlib.redirect_stdout(io.StringIO()):
        return read_step(path)


def mesh_of(shape, d=0.02, a=0.2):
    V, F, _ = tessellate(shape, d, a)
    m = trimesh.Trimesh(V, F, process=False); m.merge_vertices()
    return m


# ------------------------------------------------------------ analytic section props
o = A.OGIVE
rho_, y = A.tangent_ogive(o["L"], o["R"])


def ogive_exact(x, hollow=False):
    yo = y(x); yi = max(yo - o["t"], 0.0) if hollow else 0.0
    return dict(A_enc=math.pi * yo ** 2, A_mat=math.pi * (yo ** 2 - yi ** 2), I=math.pi / 4 * (yo ** 4 - yi ** 4))


def payload_exact(x):
    parts = []  # (A, int y dA, int z dA, int y^2 dA, int z^2 dA)
    def disk(R, yc=0.0, zc=0.0):
        a = math.pi * R * R; i0 = math.pi * R ** 4 / 4
        return (a, a * yc, a * zc, i0 + a * yc * yc, i0 + a * zc * zc)
    if 0 < x < 250:
        a_o, a_i = disk(40.0), disk(38.0)
        parts.append(tuple(p - q for p, q in zip(a_o, a_i)))
    if 0 < x < 6 or 244 < x < 250:
        parts.append(disk(38.0))
    if 6 < x < 244:
        parts += [disk(3.0, -25.0, 12.0), disk(3.0, 25.0, 12.0)]
    def rect(y0, y1, z0, z1):
        a = (y1 - y0) * (z1 - z0)
        return (a, a * (y0 + y1) / 2, a * (z0 + z1) / 2, (z1 - z0) * (y1 ** 3 - y0 ** 3) / 3, (y1 - y0) * (z1 ** 3 - z0 ** 3) / 3)
    if 30 < x < 220:
        parts.append(rect(-30, 30, -2, 2))
    if 60 < x < 130:
        parts.append(rect(-12, 12, 2, 27))
    shroud_a = 0.0
    if 150 < x < 200:
        g = lambda t: math.sqrt(1600 - t * t)
        q = lambda f: quad(f, -10, 10, epsabs=0, epsrel=1e-13)[0]
        a = q(lambda t: 50 - g(t))
        shroud_a = a
        parts.append((a, 0.0, q(lambda t: (2500 - g(t) ** 2) / 2), q(lambda t: t * t * (50 - g(t))), q(lambda t: (50 ** 3 - g(t) ** 3) / 3)))
    S = np.sum(np.array(parts), axis=0) if parts else np.zeros(5)
    Am, Sy, Sz, Iy2, Iz2 = S
    yc, zc = Sy / Am, Sz / Am
    return dict(A_mat=Am, A_enc=math.pi * 1600 + shroud_a if 0 < x < 250 else 0.0,
                Izz=Iy2 - Am * yc * yc, Iyy=Iz2 - Am * zc * zc)


def rel(a, b):
    return abs(a - b) / abs(b) if b else abs(a)


N = 200
xs_og = np.linspace(0.731, 239.37, N)
xs_pl = np.linspace(0.37, 249.63, N)

# ------------------------------------------------------------ OGIVE (solid & hollow)
for name, hollow in (("ogive_solid", False), ("ogive_hollow", True)):
    shp = load(f"{STEP}/{name}.step")
    ex = [ogive_exact(x, hollow) for x in xs_og]
    t0 = time.perf_counter(); br = slice_brep(shp, xs_og); t_b = time.perf_counter() - t0
    RES[f"{name}/brep_exact"] = dict(t=t_b, max_rel_A_mat=max(rel(b["A_mat"], e["A_mat"]) for b, e in zip(br, ex)),
                                     max_rel_I=max(rel(b["Iyy"], e["I"]) for b, e in zip(br, ex)))
    for d in (0.1, 0.02):
        m = mesh_of(load(f"{STEP}/{name}.step"), d)
        t0 = time.perf_counter(); tm = slice_trimesh(m, xs_og); t_t = time.perf_counter() - t0
        RES[f"{name}/trimesh d={d}"] = dict(t=t_t, tris=len(m.faces),
                                             max_rel_A_mat=max(rel(b["A_mat"], e["A_mat"]) for b, e in zip(tm, ex)),
                                             max_rel_A_enc=max(rel(b["A_enc"], e["A_enc"]) for b, e in zip(tm, ex)),
                                             max_rel_I=max(rel(b["Iyy"], e["I"]) for b, e in zip(tm, ex)),
                                             median_rel_A_mat=float(np.median([rel(b["A_mat"], e["A_mat"]) for b, e in zip(tm, ex)])))
        # manifold3d: rotate x->z
        man = mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))
        man_z = man.rotate([0, -90, 0])   # maps +X to +Z
        t0 = time.perf_counter(); ms = slice_manifold(man_z, xs_og); t_m = time.perf_counter() - t0
        RES[f"{name}/manifold3d d={d}"] = dict(t=t_m, status=str(man.status()),
                                                max_rel_A_mat=max(rel(b["A_mat"], e["A_mat"]) for b, e in zip(ms, ex)),
                                                max_rel_A_enc=max(rel(b["A_enc"], e["A_enc"]) for b, e in zip(ms, ex)))

# ------------------------------------------------------------ PAYLOAD (multi-solid)
from xcaf_util import read_xcaf
leaves = read_xcaf(f"{STEP}/payload_assembly.step")
comp = compound([s for _, _, s in leaves])
ex = [payload_exact(x) for x in xs_pl]
t0 = time.perf_counter(); br = slice_brep(comp, xs_pl); t_b = time.perf_counter() - t0
RES["payload/brep_exact"] = dict(t=t_b, max_rel_A_mat=max(rel(b["A_mat"], e["A_mat"]) for b, e in zip(br, ex)),
                                 max_rel_Iyy=max(rel(b["Iyy"], e["Iyy"]) for b, e in zip(br, ex)),
                                 max_rel_Izz=max(rel(b["Izz"], e["Izz"]) for b, e in zip(br, ex)))
# mesh: concatenate per-part meshes (not unioned: sections of touching parts are unioned in 2D)
pm = [mesh_of(s, 0.02) for _, _, s in leaves]
mp = trimesh.util.concatenate(pm)
t0 = time.perf_counter(); tm = slice_parts(pm, xs_pl); t_t = time.perf_counter() - t0
RES["payload/trimesh d=0.02 (per-part slices, 2D union)"] = dict(
    t=t_t, tris=len(mp.faces),
    max_rel_A_mat=max(rel(b["A_mat"], e["A_mat"]) for b, e in zip(tm, ex)),
    max_rel_A_enc=max(rel(b["A_enc"], e["A_enc"]) for b, e in zip(tm, ex)),
    max_rel_Iyy=max(rel(b["Iyy"], e["Iyy"]) for b, e in zip(tm, ex)),
    max_rel_Izz=max(rel(b["Izz"], e["Izz"]) for b, e in zip(tm, ex)))
np.savetxt(f"{ROOT}/out/payload_sections.csv",
           np.array([[e_x, e["A_enc"], b["A_enc"], e["A_mat"], b["A_mat"], br_["A_mat"], e["Iyy"], b["Iyy"], br_["Iyy"]]
                     for e_x, e, b, br_ in zip(xs_pl, ex, tm, br)]),
           delimiter=",", header="x_mm,Aenc_exact,Aenc_mesh,Amat_exact,Amat_mesh,Amat_brep,Iyy_exact,Iyy_mesh,Iyy_brep")

print(json.dumps(RES, indent=1, default=float))
json.dump(RES, open(f"{ROOT}/out/test_slice.json", "w"), indent=1, default=float)
