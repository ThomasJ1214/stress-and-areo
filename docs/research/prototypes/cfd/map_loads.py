"""Demo: map CFD surface pressure (SU2 surface_flow.vtu, Cp) onto an independent structural surface mesh
(re-meshed from the STEP geometry with gmsh at a different resolution) and check force/moment conservation.

python map_loads.py <case_dir> <mach> <h_struct_m>
Outputs <case_dir>/struct_loads.vtp with nodal force vectors [N] and pressure [Pa].
"""
import math
import sys

import gmsh
import numpy as np
import pyvista as pv

case, M, h = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G, pinf = 1.4, 101325.0
qinf = 0.5 * G * pinf * M * M

# --- structural surface mesh from STEP (different discretisation than the CFD wall) ---
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.occ.importShapes("meshes/rocket.step")
gmsh.model.occ.synchronize()
gmsh.option.setNumber("Mesh.MeshSizeMax", h)
gmsh.option.setNumber("Mesh.MeshSizeMin", h / 10)
gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 16)
gmsh.model.mesh.generate(2)
tags, xyz, _ = gmsh.model.mesh.getNodes()
X = xyz.reshape(-1, 3)
idx = {int(t): i for i, t in enumerate(tags)}
_, _, en = gmsh.model.mesh.getElements(2)
T = np.array([idx[int(n)] for n in np.concatenate(en)]).reshape(-1, 3)
gmsh.finalize()
st = pv.PolyData(X, np.hstack([np.full((len(T), 1), 3), T]).ravel())

# --- CFD surface ---
cfd = pv.read(f"{case}/surface_flow.vtu").extract_surface(algorithm="dataset_surface").triangulate()
cfd.point_data["dp"] = cfd.point_data["Pressure_Coefficient"] * qinf   # p - p_inf [Pa]

# --- interpolate p - p_inf to structural nodes ---
# method "kernel": pyvista Gaussian-kernel point interpolation (mixes both sides of thin fins -> WRONG)
# method "project": closest-point projection onto the CFD triangle + barycentric interpolation (correct)
method = sys.argv[4] if len(sys.argv) > 4 else "project"
if method == "kernel":
    st = st.interpolate(cfd, n_points=3, sharpness=4.0, strategy="closest_point")
    dp = np.asarray(st.point_data["dp"])
else:
    cid, cp = cfd.find_closest_cell(st.points, return_closest_point=True)
    tri = cfd.faces.reshape(-1, 4)[:, 1:][cid]
    A, B, C = (cfd.points[tri[:, k]] for k in range(3))
    v0, v1, v2 = B - A, C - A, cp - A
    d00 = np.einsum("ij,ij->i", v0, v0); d01 = np.einsum("ij,ij->i", v0, v1); d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("ij,ij->i", v2, v0); d21 = np.einsum("ij,ij->i", v2, v1)
    den = d00 * d11 - d01 * d01
    wb = (d11 * d20 - d01 * d21) / den; wc = (d00 * d21 - d01 * d20) / den; wa = 1 - wb - wc
    f = cfd.point_data["dp"]
    dp = wa * f[tri[:, 0]] + wb * f[tri[:, 1]] + wc * f[tri[:, 2]]
    print(f"projection distance: max {np.linalg.norm(cp - st.points, axis=1).max()*1e3:.3f} mm")

# --- consistent nodal forces: F_node = sum over adjacent triangles of (-dp_avg * n * A / 3) ---
st = st.compute_normals(cell_normals=True, point_normals=False, auto_orient_normals=False, consistent_normals=False)
P = st.points[T]
nA = 0.5 * np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])     # area-weighted normal (outward for OCC solid)
sgn = 1.0 if np.einsum("ij,ij->i", P[:, 0], 2 * nA).sum() > 0 else -1.0
nA *= sgn
dp_tri = dp[T].mean(1)
Ftri = -dp_tri[:, None] * nA
Fn = np.zeros_like(st.points)
for k in range(3):
    np.add.at(Fn, T[:, k], Ftri / 3.0)
st.point_data["force_N"] = Fn
st.point_data["p_minus_pinf_Pa"] = dp
st.save(f"{case}/struct_loads.vtp")

# --- reference integration on the CFD mesh itself ---
Pc = cfd.points[cfd.faces.reshape(-1, 4)[:, 1:]]
nAc = 0.5 * np.cross(Pc[:, 1] - Pc[:, 0], Pc[:, 2] - Pc[:, 0])
sgc = 1.0 if np.einsum("ij,ij->i", Pc[:, 0], 2 * nAc).sum() > 0 else -1.0
nAc *= sgc
Fc_tri = -cfd.point_data["dp"][cfd.faces.reshape(-1, 4)[:, 1:]].mean(1)[:, None] * nAc
F_cfd = Fc_tri.sum(0)
M_cfd = np.cross(Pc.mean(1), Fc_tri).sum(0)
F_st = Fn.sum(0)
M_st = np.cross(st.points, Fn).sum(0)
print(f"q_inf = {qinf:.1f} Pa; structural mesh: {st.n_points} nodes / {len(T)} tris (h={h} m); CFD wall: {cfd.n_points} nodes")
print(f"Force CFD  [N]: {F_cfd.round(3)}   Moment about nose tip [N m]: {M_cfd.round(4)}")
print(f"Force STRUC[N]: {F_st.round(3)}   Moment about nose tip [N m]: {M_st.round(4)}")
print(f"normal-force error {100*(F_st[2]-F_cfd[2])/F_cfd[2]:+.3f} %, axial-force error {100*(F_st[0]-F_cfd[0])/F_cfd[0]:+.3f} %, "
      f"pitch-moment error {100*(M_st[1]-M_cfd[1])/M_cfd[1]:+.3f} %")

# --- conservative (force-based) mapping: each CFD face force goes to the structural triangle under its
#     centroid, split with barycentric weights -> total force conserved exactly, moment to O(projection offset)
cent = Pc.mean(1)
cid2, cp2 = st.find_closest_cell(cent, return_closest_point=True)
tri2 = T[cid2]
A, B, C = (st.points[tri2[:, k]] for k in range(3))
v0, v1, v2 = B - A, C - A, cp2 - A
d00 = np.einsum("ij,ij->i", v0, v0); d01 = np.einsum("ij,ij->i", v0, v1); d11 = np.einsum("ij,ij->i", v1, v1)
d20 = np.einsum("ij,ij->i", v2, v0); d21 = np.einsum("ij,ij->i", v2, v1)
den = d00 * d11 - d01 * d01
wb = (d11 * d20 - d01 * d21) / den; wc = (d00 * d21 - d01 * d20) / den; wa = 1 - wb - wc
Fcons = np.zeros_like(st.points)
for w, k in ((wa, 0), (wb, 1), (wc, 2)):
    np.add.at(Fcons, tri2[:, k], w[:, None] * Fc_tri)
F2 = Fcons.sum(0); M2 = np.cross(st.points, Fcons).sum(0)
print(f"CONSERVATIVE: Force [N]: {F2.round(3)}  Moment [N m]: {M2.round(4)}")
print(f"  normal-force error {100*(F2[2]-F_cfd[2])/F_cfd[2]:+.4f} %, axial {100*(F2[0]-F_cfd[0])/F_cfd[0]:+.4f} %, "
      f"pitch-moment error {100*(M2[1]-M_cfd[1])/M_cfd[1]:+.4f} %")
st.point_data["force_conservative_N"] = Fcons
st.save(f"{case}/struct_loads.vtp")
