"""Case (f): recovery-shock bulkhead.

f1  clamped circular plate (S8R), uniform pressure -> Roark/Timoshenko plate formulas
    w0 = p a^4 / (64 D),  sigma_r(edge) = 3 p a^2 / (4 t^2),  sigma(centre) = 3 (1+nu) p a^2 / (8 t^2)
f2  same plate, suddenly applied (step) load, *FREQUENCY + *MODAL DYNAMIC, no damping
    -> peak/static centre deflection should approach the SDOF dynamic load factor 2.0
"""
import os, sys, json, re
import numpy as np
import gmsh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fea_common import *

W = os.path.join(HERE, "case_f"); os.makedirs(W, exist_ok=True)
A_R, T = 47.0, 3.0                       # radius, thickness (mm)
E, NU, RHO = 8000.0, 0.30, 0.68e-9      # plywood-like isotropic approximation
P = 0.05                                 # MPa (50 kPa)  ~ 347 N on the plate


def disk_mesh(lc):
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("disk")
    gmsh.model.occ.addDisk(0, 0, 0, A_R, A_R); gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", lc); gmsh.option.setNumber("Mesh.MeshSizeMin", lc)
    gmsh.option.setNumber("Mesh.Algorithm", 8); gmsh.option.setNumber("Mesh.RecombineAll", 1)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.model.mesh.generate(2); gmsh.model.mesh.setOrder(2)
    ids, xyz, els = gmsh_nodes_elements(gmsh, 2)
    gmsh.finalize()
    return ids, xyz, els


def header(f, ids, xyz, els, bc="1,6"):
    write_nodes(f, ids, xyz)
    for gt, (eids, conn) in els.items():
        write_elements(f, gt, eids, conn, "EALL")
    edge = ids[np.isclose(np.hypot(xyz[:, 0], xyz[:, 1]), A_R, atol=1e-6)]
    c = ids[np.argmin(np.hypot(xyz[:, 0], xyz[:, 1]))]
    write_nset(f, "EDGE", edge); write_nset(f, "CEN", [c])
    f.write(f"*MATERIAL, NAME=PLY\n*ELASTIC\n{E},{NU}\n*DENSITY\n{RHO}\n")
    f.write(f"*SHELL SECTION, ELSET=EALL, MATERIAL=PLY\n{T}\n*BOUNDARY\nEDGE,{bc}\n")
    return c


def main():
    ids, xyz, els = disk_mesh(3.0)
    D = E * T ** 3 / (12 * (1 - NU ** 2))
    w_th = P * A_R ** 4 / (64 * D)
    s_edge = 3 * P * A_R ** 2 / (4 * T ** 2)
    s_cen = 3 * (1 + NU) * P * A_R ** 2 / (8 * T ** 2)
    # ---- f1 static
    f = open(os.path.join(W, "f1_static.inp"), "w"); c = header(f, ids, xyz, els)
    f.write(f"*STEP\n*STATIC\n*DLOAD\nEALL,P,{P}\n*NODE FILE\nU\n*EL FILE\nS\n*NODE PRINT,NSET=CEN\nU\n*END STEP\n"); f.close()
    dt, _ = run_ccx(W, "f1_static")
    fr = read_frd(os.path.join(W, "f1_static.frd"))
    nid, U, _ = frd_field(fr, "DISP"); Pn = np.array([fr["nodes"][k] for k in nid])
    w_fe = np.abs(U[np.argmin(np.hypot(Pn[:, 0], Pn[:, 1]) + np.abs(Pn[:, 2]))][2]); print('centre node r =', np.hypot(Pn[:, 0], Pn[:, 1]).min())
    nidS, S, _ = frd_field(fr, "STRESS"); PS = np.array([fr["nodes"][k] for k in nidS])
    r = np.hypot(PS[:, 0], PS[:, 1])
    # radial stress at edge: sigma_rr = (sxx x^2 + syy y^2 + 2 sxy x y)/r^2 on surface nodes
    e = (np.abs(r - A_R) < 1e-6) & (np.abs(np.abs(PS[:, 2]) - T / 2) < 1e-6)
    x, y = PS[e, 0], PS[e, 1]
    srr = (S[e, 0] * x ** 2 + S[e, 1] * y ** 2 + 2 * S[e, 3] * x * y) / A_R ** 2
    surf = np.abs(np.abs(PS[:, 2]) - T / 2) < 1e-6
    rc = r[surf].min(); cen = surf & (r <= rc + 1e-9)
    s_c_fe = np.abs(0.5 * (S[cen, 0] + S[cen, 1])).max()      # sigma_r = sigma_t at centre; node at r=%.2f
    print(f"f1 ({len(ids)} nodes, {dt:.2f}s): w0 FE {w_fe:.5f} theory {w_th:.5f} | sigma_r edge FE {np.abs(srr).mean():.3f} "
          f"theory {s_edge:.3f} | centre FE {s_c_fe:.3f} theory {s_cen:.3f}")
    # ---- f2: simply supported (hinged) plate: static + *FREQUENCY + step-load *MODAL DYNAMIC
    # NOTE: clamped shells (rotational DOFs constrained) segfault in *MODAL DYNAMIC with ccx 2.23
    # (both conda-forge Linux build and dhondt Windows build) -> verified; hinged shells work.
    w_ss = (5 + NU) / (1 + NU) * P * A_R ** 4 / (64 * D)
    s_ss = 3 * (3 + NU) * P * A_R ** 2 / (8 * T ** 2)
    lam2_ss = 4.935149   # exact root of J1/J0 + I1/I0 = 2 lam/(1-nu), nu=0.3
    f_ss = lam2_ss / (2 * np.pi * A_R ** 2) * np.sqrt(D / (RHO * T))
    f = open(os.path.join(W, "f2_ss_static.inp"), "w"); c = header(f, ids, xyz, els, bc="1,3")
    f.write(f"*STEP\n*STATIC\n*DLOAD\nEALL,P,{P}\n*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n"); f.close()
    dts, _ = run_ccx(W, "f2_ss_static")
    fr = read_frd(os.path.join(W, "f2_ss_static.frd"))
    nid, U, _ = frd_field(fr, "DISP"); Pn = np.array([fr["nodes"][k] for k in nid])
    w_ss_fe = np.abs(U[np.argmin(np.hypot(Pn[:, 0], Pn[:, 1]) + np.abs(Pn[:, 2]))][2])
    nidS, S, _ = frd_field(fr, "STRESS"); PS = np.array([fr["nodes"][k] for k in nidS])
    r = np.hypot(PS[:, 0], PS[:, 1]); surf = np.abs(np.abs(PS[:, 2]) - T / 2) < 1e-6
    cen = surf & (r <= r[surf].min() + 1e-9)
    s_ss_fe = np.abs(0.5 * (S[cen, 0] + S[cen, 1])).max()
    f = open(os.path.join(W, "f2_dyn.inp"), "w"); c = header(f, ids, xyz, els, bc="1,3")
    f.write("*AMPLITUDE, NAME=STEPA\n0.,1.,1.,1.\n")
    f.write("*STEP\n*FREQUENCY, STORAGE=YES\n20\n*END STEP\n")
    Tper = 1 / f_ss
    f.write(f"*STEP, INC=10000\n*MODAL DYNAMIC\n{Tper / 200:.6g},{3 * Tper:.6g}\n*DLOAD, AMPLITUDE=STEPA\nEALL,P,{P}\n")
    f.write("*NODE PRINT, NSET=CEN, FREQUENCY=1\nU\n*END STEP\n"); f.close()
    dt2, _ = run_ccx(W, "f2_dyn")
    ev = read_dat_eigen(os.path.join(W, "f2_dyn.dat"))
    txt = open(os.path.join(W, "f2_dyn.dat")).read()
    blocks = re.findall(r"displacements \(vx,vy,vz\) for set CEN and time\s+([\dE\.\+\-]+)\s*\n\s*\n\s*\d+\s+[-\dE\.\+]+\s+[-\dE\.\+]+\s+([-\dE\.\+]+)", txt)
    tt = np.array([float(a) for a, b in blocks]); wz = np.array([float(b) for a, b in blocks])
    dlf = np.abs(wz).max() / w_ss_fe
    print(f"f2 SS static ({dts:.2f}s): w0 FE {w_ss_fe:.5f} theory {w_ss:.5f} | centre sigma FE {s_ss_fe:.3f} theory {s_ss:.3f}")
    print(f"f2 dyn ({dt2:.2f}s): f1 FE {ev['freq_hz'][0]:.1f} Hz exact {f_ss:.1f} Hz; {len(tt)} time pts, "
          f"peak |w| {np.abs(wz).max():.5f} at t={tt[np.argmax(np.abs(wz))]:.3e}s -> DLF {dlf:.3f} (undamped step SDOF = 2.0)")
    json.dump(dict(nodes=len(ids), clamped=dict(w_fe=w_fe, w_theory=w_th, s_edge_fe=float(np.abs(srr).mean()),
                   s_edge_theory=s_edge, s_cen_fe=s_c_fe, s_cen_theory=s_cen, time=dt),
                   ss=dict(w_fe=w_ss_fe, w_theory=w_ss, s_cen_fe=s_ss_fe, s_cen_theory=s_ss, f1_fe=ev["freq_hz"][0],
                   f1_exact=f_ss, dlf=dlf, time_dyn=dt2), t=tt.tolist(), w=wz.tolist()),
              open(os.path.join(W, "results.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
