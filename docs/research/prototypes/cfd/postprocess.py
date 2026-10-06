"""Post-process an SU2 run of the finned cone-cylinder test case.

python postprocess.py <case_dir> [--aoa 4] [--mach 2] [--png]

* final coefficients from history.csv (total + per marker), x_cp from CMy/CFz
* independent re-integration of surface Cp from surface_flow.vtu with pyvista (checks SU2 force integration
  and demonstrates the surface-pressure -> structural-load path)
* Cp along the cone generator lines vs Taylor-Maccoll (alpha=0 reference)
* optional off-screen PNG renderings (run under xvfb-run)
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pyvista as pv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taylor_maccoll import solve_cone  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("case")
ap.add_argument("--aoa", type=float, default=4.0)
ap.add_argument("--mach", type=float, default=2.0)
ap.add_argument("--png", action="store_true")
a = ap.parse_args()

R, LN, L, D = 0.05, 0.30, 1.0, 0.1
AREF = math.pi * R * R
res = {"case": a.case}

# ---------------- history ----------------
import csv
with open(os.path.join(a.case, "history.csv")) as fh:
    rd = csv.reader(fh)
    hdr = [h.strip().strip('"') for h in next(rd)]
    rows = [[float(x) for x in r] for r in rd if r]
H = {h: np.array([r[i] for r in rows]) for i, h in enumerate(hdr)}
n = len(rows)
last = {h: H[h][-1] for h in hdr}
res["iterations"] = int(H["Inner_Iter"][-1]) + 1
res["wall_time_s"] = float(H["Time(sec)"][-1]) if "Time(sec)" in H else None
for k in ["CD", "CL", "CMy", "CFx", "CFy", "CFz", "relrms[Rho]"]:
    if k in last:
        res[k] = float(last[k])
for surf in ["nose", "body", "fins", "base"]:
    d = {}
    for k in ["CD", "CL", "CMy", "CFx", "CFz"]:
        key = f"{k}({surf})"
        if key in last:
            d[k] = float(last[key])
    res[surf] = d
if "CFz" in last and abs(last["CFz"]) > 1e-9:
    res["x_cp_over_D_from_nose"] = float(-last["CMy"] / last["CFz"])
    res["x_cp_m"] = res["x_cp_over_D_from_nose"] * D
# stationarity of the integrated loads over the last 10% of iterations
w = max(5, n // 10)
for k in ["CFz", "CFx", "CMy"]:
    if k in H:
        seg = H[k][-w:]
        res[f"{k}_last10pct_range"] = float(seg.max() - seg.min())

# ---------------- surface re-integration ----------------
s = pv.read(os.path.join(a.case, "surface_flow.vtu")).extract_surface(algorithm="dataset_surface")
s = s.triangulate()
s = s.compute_normals(cell_normals=True, point_normals=False, auto_orient_normals=True, consistent_normals=True)
s = s.compute_cell_sizes(length=False, area=True, volume=False)
cp_cell = s.point_data_to_cell_data()["Pressure_Coefficient"]
nrm = np.array(s.cell_data["Normals"])
area = np.array(s.cell_data["Area"])
ctr = s.cell_centers().points
# enforce outward orientation for the closed body surface (divergence theorem: V = 1/3 sum(c.n A) > 0)
vol_est = (np.einsum("ij,ij->i", ctr - ctr.mean(0), nrm) * area).sum() / 3.0
if vol_est < 0:
    nrm = -nrm
    vol_est = -vol_est
res["enclosed_volume_m3_from_surface"] = float(vol_est)
rr = np.hypot(ctr[:, 1], ctr[:, 2])
tag = np.full(len(area), "body", dtype=object)
tag[ctr[:, 0] <= LN - 1e-4] = "nose"
tag[np.abs(nrm[:, 0] - 1.0) < 1e-3] = "base"
tag[(rr > R + 1e-4) & (tag != "base")] = "fins"
# body-fin junction: triangles on the cylinder near fins are body; fin root faces have rr > R
dF = -(cp_cell[:, None] * nrm) * area[:, None] / AREF       # force coefficient contribution
dM = np.cross(ctr, dF) / D                                   # moment about nose tip, ref length D
integ = {}
for t in ["nose", "body", "fins", "base", "all"]:
    m = np.ones(len(area), bool) if t == "all" else (tag == t)
    F = dF[m].sum(0)
    M = dM[m].sum(0)
    integ[t] = {"CFx": float(F[0]), "CFy": float(F[1]), "CFz": float(F[2]), "CMy": float(M[1]), "area_m2": float(area[m].sum())}
res["pyvista_integration"] = integ
res["surface_closed_area_m2"] = float(area.sum())

# ---------------- cone Cp vs Taylor-Maccoll ----------------
if a.mach > 1.2:
    tm = solve_cone(a.mach, math.degrees(math.atan(R / LN)))
    res["taylor_maccoll"] = {"beta_deg": math.degrees(tm["beta"]), "Cp_cone": tm["Cp"], "Mc": tm["Mc"]}
else:
    tm = {"Cp": float("nan")}
nose = tag == "nose"
phi = np.degrees(np.arctan2(ctr[:, 1], ctr[:, 2]))          # 0 = top (+z), 180 = bottom (-z)
xn = ctr[:, 0] / LN
band = nose & (xn > 0.2)
res["nose_Cp_area_avg_x>0.2Ln"] = float(np.average(cp_cell[band], weights=area[band]))
res["nose_Cp_windward_avg"] = float(np.mean(cp_cell[band & (np.abs(np.abs(phi) - 180) < 15)]))
res["nose_Cp_leeward_avg"] = float(np.mean(cp_cell[band & (np.abs(phi) < 15)]))
res["nose_axial_CF_vs_TM"] = {"CFx_nose_su2": res["nose"].get("CFx"), "Cp_TM_(=CA_nose at alpha=0)": tm["Cp"]}

# simple theory for comparison (supersonic slender-body nose CN_alpha = 2/rad on base area)
al = math.radians(a.aoa)
res["slender_body_nose_CN"] = 2.0 * math.sin(al) * math.cos(al)

print(json.dumps(res, indent=2))
with open(os.path.join(a.case, "post.json"), "w") as fh:
    json.dump(res, fh, indent=2)

# cone Cp distribution file
order = np.argsort(xn[nose])
np.savetxt(os.path.join(a.case, "nose_cp.csv"),
           np.c_[ctr[nose][order], phi[nose][order], cp_cell[nose][order]],
           delimiter=",", header="x,y,z,phi_deg,Cp", comments="")

if a.png:
    pv.OFF_SCREEN = True
    p = pv.Plotter(off_screen=True, window_size=(1600, 900))
    p.add_mesh(s, scalars=s.point_data["Pressure_Coefficient"], cmap="turbo", show_scalar_bar=True,
               clim=[-0.3, 0.5], scalar_bar_args={"title": "Cp (clipped to [-0.3, 0.5])"})
    p.camera_position = [(0.25, -1.3, -0.55), (0.5, 0, 0), (0, 0, 1)]
    p.screenshot(os.path.join(a.case, "surface_cp.png"))
    p.close()
    vol = pv.read(os.path.join(a.case, "flow.vtu"))
    sl = vol.slice(normal="y", origin=(0, 0, 0))
    p = pv.Plotter(off_screen=True, window_size=(1600, 900))
    p.add_mesh(sl, scalars="Mach", cmap="turbo", clim=[0, a.mach * 1.15 if a.mach > 1 else a.mach * 2])
    p.add_mesh(s, color="white")
    p.camera_position = "xz"
    p.camera.zoom(1.0)
    p.reset_camera(bounds=(-0.2, 1.6, 0, 0, -0.45, 0.45))
    p.camera.zoom(1.4)
    p.screenshot(os.path.join(a.case, "symplane_mach.png"))
    p.close()
    print("wrote PNGs")
