"""Cases (b) and (c): fin plates as S8R shells (gmsh quads, 2nd order serendipity).

b1  wide rectangular cantilever plate (chord 4x span), uniform pressure
    -> root stress & deflection at mid-chord vs exact cylindrical-bending plate theory
b2  realistic trapezoidal swept fin, uniform pressure
    -> statics check (root shear + moment), beam-theory average root stress vs FE peak
c1  square cantilever plate (CFFF) *FREQUENCY vs Leissa (1969) exact plate values
c2  trapezoidal fin *FREQUENCY vs simple beam/torsion estimates
"""
import os, sys, json
import numpy as np
import gmsh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fea_common import *

W = os.path.join(HERE, "case_bc"); os.makedirs(W, exist_ok=True)
E, NU, RHO = 70000.0, 0.30, 2.70e-9         # aluminium-ish, MPa, t/mm^3
T = 3.0                                       # plate thickness mm
P = 0.01                                      # 10 kPa uniform pressure
NSEG = int(os.environ.get("NSEG", 1))         # mesh refinement multiplier


def plate_mesh(poly, lc):
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("plate")
    pts = [gmsh.model.occ.addPoint(x, y, 0) for x, y in poly]
    lines = [gmsh.model.occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    cl = gmsh.model.occ.addCurveLoop(lines)
    s = gmsh.model.occ.addPlaneSurface([cl]); gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", lc); gmsh.option.setNumber("Mesh.MeshSizeMin", lc)
    gmsh.option.setNumber("Mesh.Algorithm", 8)
    gmsh.option.setNumber("Mesh.RecombineAll", 1)
    gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)    # 8-node serendipity quads
    gmsh.model.mesh.generate(2); gmsh.model.mesh.setOrder(2)
    ids, xyz, els = gmsh_nodes_elements(gmsh, 2)
    gmsh.finalize()
    return ids, xyz, els


def write_plate_inp(job, ids, xyz, els, step):
    f = open(os.path.join(W, job + ".inp"), "w")
    write_nodes(f, ids, xyz)
    for gt, (eids, conn) in els.items():
        write_elements(f, gt, eids, conn, "EALL")
    root = ids[np.isclose(xyz[:, 1], 0.0)]
    write_nset(f, "ROOT", root)
    f.write(f"*MATERIAL, NAME=AL\n*ELASTIC\n{E},{NU}\n*DENSITY\n{RHO}\n")
    f.write(f"*SHELL SECTION, ELSET=EALL, MATERIAL=AL\n{T}\n")
    f.write("*BOUNDARY\nROOT,1,6\n")
    f.write("*STEP\n")
    if step == "static":
        f.write(f"*STATIC\n*DLOAD\nEALL,P,{P}\n")
        f.write("*NODE FILE\nU\n*EL FILE\nS\n*NODE PRINT, NSET=ROOT, TOTALS=ONLY\nRF\n")
    else:
        f.write("*FREQUENCY\n8\n*NODE FILE\nU\n")
    f.write("*END STEP\n")
    f.close()
    return root


def leissa_cfff_square():
    # Leissa, Vibration of Plates (NASA SP-160, 1969), Table 4.53 (a/b=1, nu=0.3):
    # omega*a^2*sqrt(rho h / D)
    return [3.4917, 8.5246, 21.429, 27.331, 31.111]


def dat_reactions(path):
    txt = open(path).read()
    import re
    m = re.findall(r"total force \(fx,fy,fz\).*?\n\s*\n?\s*([-\dE\.\+ ]+)\n", txt)
    return m


def main():
    res = {}
    D = E * T ** 3 / (12 * (1 - NU ** 2))
    # ------------------------------------------------------------ b1 wide plate
    s, c = 100.0, 400.0
    ids, xyz, els = plate_mesh([(0, 0), (c, 0), (c, s), (0, s)], 10.0 / NSEG)
    write_plate_inp("b1_wide", ids, xyz, els, "static")
    dt, _ = run_ccx(W, "b1_wide")
    frd = read_frd(os.path.join(W, "b1_wide.frd"))
    nid, U, _ = frd_field(frd, "DISP"); Pn = np.array([frd["nodes"][k] for k in nid])
    nidS, S, _ = frd_field(frd, "STRESS"); PS = np.array([frd["nodes"][k] for k in nidS])
    tipmid = np.argmin(np.linalg.norm(Pn - [c / 2, s, 0], axis=1))
    w_fe = abs(U[tipmid, 2])
    rootmid = np.isclose(PS[:, 1], 0) & np.isclose(PS[:, 0], c / 2)
    s_fe = np.abs(S[rootmid, 1]).max()
    w_th = P * s ** 4 / (8 * D)                    # cylindrical bending, clamped-free strip
    s_th = 6 * (P * s ** 2 / 2) / T ** 2
    print(f"b1 ({len(ids)} nodes, {dt:.2f}s): tip w mid-chord FE {w_fe:.5f} plate-strip {w_th:.5f} "
          f"| root sigma_y mid-chord FE {s_fe:.3f} theory {s_th:.3f}")
    res["b1"] = dict(nodes=len(ids), time_s=dt, w_fe=w_fe, w_theory=w_th, s_fe=s_fe, s_theory=s_th,
                     beam_w_no_poisson=P * s ** 4 / (8 * E * T ** 3 / 12))
    frd_to_vtu(frd, os.path.join(W, "b1_wide.vtu"))

    # ------------------------------------------------------------ b2 trapezoidal fin
    cr, ct, span, sweep = 150.0, 60.0, 100.0, 90.0       # LE sweep distance
    poly = [(0, 0), (cr, 0), (sweep + ct, span), (sweep, span)]
    ids, xyz, els = plate_mesh(poly, 5.0 / NSEG)
    write_plate_inp("b2_fin", ids, xyz, els, "static")
    dt, _ = run_ccx(W, "b2_fin")
    frd = read_frd(os.path.join(W, "b2_fin.frd"))
    nidS, S, _ = frd_field(frd, "STRESS"); PS = np.array([frd["nodes"][k] for k in nidS])
    # exact statics: area and moment of pressure about the root line (y=0)
    A = 0.5 * (cr + ct) * span
    ybar = span * (cr + 2 * ct) / (3 * (cr + ct))
    F = P * A; M = F * ybar
    s_avg = 6 * M / (cr * T ** 2)                 # beam theory, moment spread over root chord
    root = np.isclose(PS[:, 1], 0)
    vm = von_mises(S)
    s_root_peak = np.abs(S[root, 1]).max()
    vm_peak = vm.max(); loc = PS[np.argmax(vm)]
    # root bending stress distribution along chord (surface nodes): average of |sigma_y|
    xr = PS[root, 0]; sy = np.abs(S[root, 1])
    order = np.argsort(xr)
    # integrate sigma_y * t^2/6 along chord using surface nodes (only top surface: z>0)
    top = root & (PS[:, 2] > 0)
    xs = PS[top, 0]; sys_ = S[top, 1]; o = np.argsort(xs)
    M_fe = np.trapezoid(np.abs(sys_[o]) * T ** 2 / 6, xs[o])
    # reactions from .dat totals
    dat = open(os.path.join(W, "b2_fin.dat")).read()
    print(f"b2 ({len(ids)} nodes, {dt:.2f}s): F={F:.3f} N, M_root={M:.3f} N.mm, beam avg root sigma {s_avg:.2f} MPa;"
          f" FE root sigma_y peak {s_root_peak:.2f}, vM peak {vm_peak:.2f} at {loc}; M from FE root stress {M_fe:.2f}")
    print(dat[-600:])
    res["b2"] = dict(nodes=len(ids), time_s=dt, F=F, M=M, sigma_beam_avg=s_avg, sigma_root_peak_fe=s_root_peak,
                     vm_peak=vm_peak, vm_peak_loc=loc.tolist(), M_from_fe_root_stress=M_fe,
                     root_profile=[xs[o].tolist(), sys_[o].tolist()])
    frd_to_vtu(frd, os.path.join(W, "b2_fin.vtu"))

    # ------------------------------------------------------------ c1 square CFFF modal
    a = 100.0
    ids, xyz, els = plate_mesh([(0, 0), (a, 0), (a, a), (0, a)], 5.0 / NSEG)
    write_plate_inp("c1_square_modal", ids, xyz, els, "freq")
    dt, _ = run_ccx(W, "c1_square_modal")
    ev = read_dat_eigen(os.path.join(W, "c1_square_modal.dat"))
    lam = leissa_cfff_square()
    f_an = [l / a ** 2 * np.sqrt(D / (RHO * T)) / (2 * np.pi) for l in lam]
    print(f"c1 ({len(ids)} nodes, {dt:.2f}s) FE Hz:", np.round(ev["freq_hz"][:5], 2), " Leissa Hz:", np.round(f_an, 2))
    res["c1"] = dict(nodes=len(ids), time_s=dt, f_fe=ev["freq_hz"], f_leissa=f_an)

    # ------------------------------------------------------------ c2 trapezoid fin modal
    ids, xyz, els = plate_mesh(poly, 5.0 / NSEG)
    write_plate_inp("c2_fin_modal", ids, xyz, els, "freq")
    dt, _ = run_ccx(W, "c2_fin_modal")
    ev = read_dat_eigen(os.path.join(W, "c2_fin_modal.dat"))
    frd = read_frd(os.path.join(W, "c2_fin_modal.frd"))
    frd_to_vtu(frd, os.path.join(W, "c2_fin_modal.vtu"))
    # crude estimates: equivalent uniform cantilever strip with mean chord
    cm = 0.5 * (cr + ct); G = E / (2 * (1 + NU))
    f_bend_beam = 1.8751 ** 2 / (2 * np.pi * span ** 2) * np.sqrt(E * T ** 2 / (12 * RHO))
    f_tors_strip = 1 / (4 * span) * np.sqrt(G * (cm * T ** 3 / 3) / (RHO * (cm ** 3 * T + cm * T ** 3) / 12))
    # classify FE modes: bending vs torsion by sign pattern of tip LE/TE displacement
    modes = []
    for k, r in enumerate([r for r in frd["results"] if r["name"] == "DISP"][:5]):
        ids_ = np.array(sorted(r["data"])); Uk = np.array([r["data"][i] for i in ids_])
        Pk = np.array([frd["nodes"][i] for i in ids_])
        le = np.argmin(np.linalg.norm(Pk - [sweep, span, 0], axis=1))
        te = np.argmin(np.linalg.norm(Pk - [sweep + ct, span, 0], axis=1))
        modes.append("bending-like" if Uk[le, 2] * Uk[te, 2] > 0 else "torsion-like")
    print(f"c2 ({len(ids)} nodes, {dt:.2f}s) FE Hz:", np.round(ev["freq_hz"][:5], 2), modes,
          f" | uniform-strip estimates: 1st bending {f_bend_beam:.1f} Hz (no taper), 1st torsion {f_tors_strip:.1f} Hz")
    res["c2"] = dict(nodes=len(ids), time_s=dt, f_fe=ev["freq_hz"], modes=modes,
                     f_bend_uniform_strip=f_bend_beam, f_tors_uniform_strip=f_tors_strip)
    json.dump(res, open(os.path.join(W, f"results_NSEG{NSEG}.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
