"""Case (a): thin-walled tube, S8R shells, *BUCKLE under axial compression.

a0  isotropic aluminium tube  -> classical sigma_cr = E t / (R sqrt(3(1-nu^2)))
a1  [0/90/+45/-45]s E-glass/epoxy laminate via *SHELL SECTION, COMPOSITE
    -> classical Donnell orthotropic formula (ABD, D16=D26 neglected), NASA SP-8007 knockdown
"""
import os, sys, json
import numpy as np
import gmsh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fea_common import *

W = os.path.join(HERE, "case_a"); os.makedirs(W, exist_ok=True)
R, T, L = 49.0, 1.0, 150.0             # mm  (98 mm OD-ish airframe, 1 mm wall)
H_EL = float(os.environ.get("HEL", 3.0))  # target element edge length (mm)
P_REF = 1000.0                          # N reference axial load
BC = os.environ.get("BC", "clamped")    # clamped | hinged

# E-glass/epoxy UD ply (illustrative textbook-type values, MPa)
PLY = dict(E1=39000.0, E2=8600.0, E3=8600.0, nu12=0.28, nu13=0.28, nu23=0.40,
           G12=3800.0, G13=3800.0)
PLY["G23"] = PLY["E2"] / (2 * (1 + PLY["nu23"]))
LAYUP = [int(v) for v in os.environ.get("LAYUP", "0,90,45,-45,-45,45,90,0").split(",")]
TAG = os.environ.get("TAG", "qi")
TPLY = T / len(LAYUP)


def tube_mesh():
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("tube")
    c = gmsh.model.occ.addCircle(0, 0, 0, R)
    gmsh.model.occ.synchronize()
    nth = int(round(2 * np.pi * R / H_EL)); nz = int(round(L / H_EL))
    gmsh.model.mesh.setTransfiniteCurve(c, nth + 1)
    gmsh.model.occ.extrude([(1, c)], 0, 0, L, numElements=[nz], recombine=True)
    gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.model.mesh.generate(2); gmsh.model.mesh.setOrder(2)
    ids, xyz, els = gmsh_nodes_elements(gmsh, 2)
    gmsh.finalize()
    return ids, xyz, els, nth, nz


def C3d_local(p):
    S = np.zeros((6, 6))
    S[0, 0], S[1, 1], S[2, 2] = 1 / p["E1"], 1 / p["E2"], 1 / p["E3"]
    S[0, 1] = S[1, 0] = -p["nu12"] / p["E1"]; S[0, 2] = S[2, 0] = -p["nu13"] / p["E1"]
    S[1, 2] = S[2, 1] = -p["nu23"] / p["E2"]
    S[3, 3], S[4, 4], S[5, 5] = 1 / p["G12"], 1 / p["G13"], 1 / p["G23"]  # 12,13,23
    Cv = np.linalg.inv(S)
    idx = {(0, 0): 0, (1, 1): 1, (2, 2): 2, (0, 1): 3, (1, 0): 3, (0, 2): 4, (2, 0): 4, (1, 2): 5, (2, 1): 5}
    C4 = np.zeros((3, 3, 3, 3))
    for i in range(3):
        for j in range(3):
            for k in range(3):
                for l in range(3):
                    C4[i, j, k, l] = Cv[idx[i, j], idx[k, l]]
    return C4


def aniso_card(theta):
    a = np.radians(theta); c, s = np.cos(a), np.sin(a)
    Rm = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    C4 = np.einsum("ia,jb,kc,ld,abcd->ijkl", Rm, Rm, Rm, Rm, C3d_local(PLY))
    order = [(0, 0, 0, 0), (0, 0, 1, 1), (1, 1, 1, 1), (0, 0, 2, 2), (1, 1, 2, 2), (2, 2, 2, 2),
             (0, 0, 0, 1), (1, 1, 0, 1), (2, 2, 0, 1), (0, 1, 0, 1), (0, 0, 0, 2), (1, 1, 0, 2),
             (2, 2, 0, 2), (0, 1, 0, 2), (0, 2, 0, 2), (0, 0, 1, 2), (1, 1, 1, 2), (2, 2, 1, 2),
             (0, 1, 1, 2), (0, 2, 1, 2), (1, 2, 1, 2)]
    v = [C4[o] for o in order]
    fmt = lambda xs: ",".join(f"{x:.8g}" for x in xs)
    return f"{fmt(v[:8])}\n{fmt(v[8:16])}\n{fmt(v[16:21])},0.\n"


def write_inp(job, ids, xyz, els, composite):
    f = open(os.path.join(W, job + ".inp"), "w")
    write_nodes(f, ids, xyz)
    (gt, (eids, conn)), = els.items()
    write_elements(f, gt, eids, conn, "EALL")
    bot = ids[np.isclose(xyz[:, 2], 0)]; top = ids[np.isclose(xyz[:, 2], L)]
    write_nset(f, "BOT", bot); write_nset(f, "TOP", top)
    if composite:
        f.write("*ORIENTATION, NAME=OAX, SYSTEM=RECTANGULAR\n0.,0.,1.,1.,0.,0.\n")   # local x = tube axis
        for th in sorted(set(LAYUP)):
            f.write(f"*MATERIAL, NAME=PLY{th + 100}\n*ELASTIC, TYPE=ANISO\n" + aniso_card(th))
        f.write("*SHELL SECTION, ELSET=EALL, COMPOSITE, ORIENTATION=OAX\n")
        for th in LAYUP:
            f.write(f"{TPLY},,PLY{th + 100}\n")
    else:
        f.write("*MATERIAL, NAME=AL\n*ELASTIC\n70000.,0.3\n")
        f.write(f"*SHELL SECTION, ELSET=EALL, MATERIAL=AL\n{T}\n")
    f.write("*BOUNDARY\n")
    if BC == "clamped":
        f.write("BOT,1,6\nTOP,1,2\nTOP,4,6\n")
    else:
        f.write("BOT,1,3\nTOP,1,2\n")
    # consistent edge loads on the top ring (quadratic edges: 1/6, 2/3, 1/6)
    X = dict(zip(ids, xyz)); topset = set(top.tolist()); w = {}
    for c in conn:
        for a, m, b in ((0, 4, 1), (1, 5, 2), (2, 6, 3), (3, 7, 0)):
            if c[a] in topset and c[b] in topset and c[m] in topset:
                le = np.linalg.norm(X[c[a]] - X[c[b]])
                for n_, wt in ((c[a], 1 / 6), (c[m], 2 / 3), (c[b], 1 / 6)):
                    w[n_] = w.get(n_, 0.0) + wt * le
    tot = sum(w.values())
    f.write("*STEP\n*BUCKLE\n10\n*CLOAD\n")
    for n_, v in w.items():
        f.write(f"{n_},3,{-P_REF * v / tot:.10g}\n")
    f.write("*NODE FILE\nU\n*END STEP\n")
    f.close()


def laminate_abd():
    E1, E2, n12, G12 = PLY["E1"], PLY["E2"], PLY["nu12"], PLY["G12"]
    n21 = n12 * E2 / E1; d = 1 - n12 * n21
    Q = np.array([[E1 / d, n12 * E2 / d, 0], [n12 * E2 / d, E2 / d, 0], [0, 0, G12]])
    A = np.zeros((3, 3)); Bm = np.zeros((3, 3)); D = np.zeros((3, 3))
    z = -T / 2
    for th in LAYUP:
        a = np.radians(th); c, s = np.cos(a), np.sin(a)
        Tm = np.array([[c * c, s * s, 2 * c * s], [s * s, c * c, -2 * c * s], [-c * s, c * s, c * c - s * s]])
        Rr = np.diag([1, 1, 2])
        Qb = np.linalg.inv(Tm) @ Q @ Rr @ Tm @ np.linalg.inv(Rr)
        z1 = z + TPLY
        A += Qb * (z1 - z); Bm += Qb * (z1 ** 2 - z ** 2) / 2; D += Qb * (z1 ** 3 - z ** 3) / 3
        z = z1
    return A, Bm, D


def classical_ortho(A, D):
    """Donnell orthotropic cylinder (NASA SP-8007 eq. form), B=0, A16=A26=D16=D26=0.
    Minimise over m (axial half waves, SS ends) and n (circumferential full waves)."""
    best = (np.inf, None)
    for m in range(1, 200):
        lam = m * np.pi / L
        for n in range(0, 60):
            be = n / R
            C11 = A[0, 0] * lam ** 2 + A[2, 2] * be ** 2
            C22 = A[2, 2] * lam ** 2 + A[1, 1] * be ** 2
            C12 = (A[0, 1] + A[2, 2]) * lam * be
            C13 = A[0, 1] * lam / R
            C23 = A[1, 1] * be / R
            C33 = (D[0, 0] * lam ** 4 + 2 * (D[0, 1] + 2 * D[2, 2]) * lam ** 2 * be ** 2
                   + D[1, 1] * be ** 4 + A[1, 1] / R ** 2)
            det = C11 * C22 - C12 ** 2
            Nx = (C33 - (C13 ** 2 * C22 - 2 * C12 * C13 * C23 + C23 ** 2 * C11) / det) / lam ** 2
            if Nx < best[0]:
                best = (Nx, (m, n))
    return best


def sp8007_gamma_ortho(A, D):
    phi = (1 / 29.8) * np.sqrt(R / (D[0, 0] * D[1, 1] / (A[0, 0] * A[1, 1])) ** 0.25)
    return 1 - 0.901 * (1 - np.exp(-phi)), phi


def main():
    ids, xyz, els, nth, nz = tube_mesh()
    ne = sum(len(v[0]) for v in els.values())
    print(f"tube mesh: {len(ids)} nodes, {ne} S8R ({nth} x {nz}), h={H_EL} mm, BC={BC}")
    res = dict(nodes=len(ids), elements=ne, h=H_EL, BC=BC)
    # a0 isotropic
    write_inp("a0_iso", ids, xyz, els, composite=False)
    dt, out = run_ccx(W, "a0_iso")
    bf = read_dat_eigen(os.path.join(W, "a0_iso.dat"))["buckle"]
    E, nu = 70000.0, 0.3
    s_cl = E * T / (R * np.sqrt(3 * (1 - nu ** 2))); P_cl = s_cl * 2 * np.pi * R * T
    g_iso = 1 - 0.901 * (1 - np.exp(-np.sqrt(R / T) / 16))
    print(f"a0 iso: {dt:.1f}s  P_cr FE {bf[0] * P_REF:.0f} N  classical {P_cl:.0f} N  ratio {bf[0] * P_REF / P_cl:.4f}"
          f"  | SP-8007 gamma {g_iso:.3f} -> design {g_iso * P_cl:.0f} N")
    res["a0"] = dict(time_s=dt, factors=bf, P_fe=bf[0] * P_REF, P_classical=P_cl, gamma=g_iso)
    frd_to_vtu(read_frd(os.path.join(W, "a0_iso.frd")), os.path.join(W, f"a0_iso_{BC}.vtu"))
    # a1 composite
    A, Bm, D = laminate_abd()
    Ncl, mn = classical_ortho(A, D)
    P_lam = Ncl * 2 * np.pi * R
    g, phi = sp8007_gamma_ortho(A, D)
    write_inp("a1_comp", ids, xyz, els, composite=True)
    dt, out = run_ccx(W, "a1_comp")
    bf = read_dat_eigen(os.path.join(W, "a1_comp.dat"))["buckle"]
    print("A=\n", np.round(A, 1), "\nB max", np.abs(Bm).max(), "\nD=\n", np.round(D, 2))
    print(f"a1 comp: {dt:.1f}s  P_cr FE {bf[0] * P_REF:.0f} N  classical {P_lam:.0f} N (m,n)={mn}  ratio {bf[0] * P_REF / P_lam:.4f}"
          f"  | SP-8007 gamma {g:.3f} (phi {phi:.3f}) -> design {g * P_lam:.0f} N")
    res["a1"] = dict(time_s=dt, factors=bf, P_fe=bf[0] * P_REF, P_classical=P_lam, mn=mn, gamma=g,
                     A=A.tolist(), D=D.tolist(), B_max=float(np.abs(Bm).max()))
    frd_to_vtu(read_frd(os.path.join(W, "a1_comp.frd")), os.path.join(W, f"a1_comp_{BC}_{TAG}.vtu"))
    res["layup"] = LAYUP
    json.dump(res, open(os.path.join(W, f"results_h{H_EL}_{BC}_{TAG}.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
