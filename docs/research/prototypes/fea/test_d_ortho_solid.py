"""Case (d): solid C3D10 bar with *ORIENTATION orthotropic (3D-print-like) material.

Two load cases on the same gmsh 10-node tet mesh:
  d1  uniaxial tension with material axes rotated (print direction tilted)
      -> homogeneous stress state, EXACT analytic answer from rotated compliance.
  d2  tip-loaded cantilever, material axes aligned with the bar
      -> Timoshenko beam estimate (bending + shear).
Each solved with CalculiX (C3D10) and with scikit-fem (P2 tets, in-process).
"""
import os, sys, json, time
import numpy as np
import gmsh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fea_common import *

W = os.path.join(HERE, "case_d"); os.makedirs(W, exist_ok=True)
L, B, H = 100.0, 20.0, 10.0          # mm
LC = float(os.environ.get("LC", 3.0))

# --- 3D-print-like transversely isotropic material (illustrative PLA-ish values, MPa)
# 1,2 = in the printed layer plane, 3 = build (z) direction -> weaker, interlayer shear lower
E1, E2, E3 = 3200.0, 3200.0, 2400.0
nu12, nu13, nu23 = 0.35, 0.30, 0.30
G12 = E1 / (2 * (1 + nu12)); G13 = G23 = 900.0
RHO = 1.24e-9


def compliance_local():
    S = np.zeros((6, 6))
    S[0, 0], S[1, 1], S[2, 2] = 1 / E1, 1 / E2, 1 / E3
    S[0, 1] = S[1, 0] = -nu12 / E1
    S[0, 2] = S[2, 0] = -nu13 / E1
    S[1, 2] = S[2, 1] = -nu23 / E2
    S[3, 3], S[4, 4], S[5, 5] = 1 / G12, 1 / G13, 1 / G23   # Voigt: 12, 13, 23 (engineering)
    return S


def voigt_to_tensor_C(C):
    """C (6x6, order 11,22,33,12,13,23 with engineering shear) -> C_ijkl."""
    idx = {(0, 0): 0, (1, 1): 1, (2, 2): 2, (0, 1): 3, (1, 0): 3, (0, 2): 4, (2, 0): 4,
           (1, 2): 5, (2, 1): 5}
    C4 = np.zeros((3, 3, 3, 3))
    for i in range(3):
        for j in range(3):
            for k in range(3):
                for l in range(3):
                    C4[i, j, k, l] = C[idx[i, j], idx[k, l]]
    return C4


def rot(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    if axis == "z":
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def global_C4(R):
    C4l = voigt_to_tensor_C(np.linalg.inv(compliance_local()))
    # columns of R are local axes expressed in global coords
    return np.einsum("ia,jb,kc,ld,abcd->ijkl", R, R, R, R, C4l)


def mesh():
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("bar")
    gmsh.model.occ.addBox(0, 0, 0, L, B, H); gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", LC)
    gmsh.option.setNumber("Mesh.MeshSizeMin", LC)
    gmsh.model.mesh.generate(3); gmsh.model.mesh.setOrder(2)
    ids, xyz, els = gmsh_nodes_elements(gmsh, 3)
    gmsh.finalize()
    eids, conn = els[11]
    return ids, xyz, eids, conn


TET_FACES = {1: (0, 1, 2), 2: (0, 3, 1), 3: (1, 3, 2), 4: (2, 3, 0)}   # ccx C3D10 faces


def faces_on(xyz_of, conn_ccx, eids, pred):
    out = []
    for e, c in zip(eids, conn_ccx):
        for fno, (a, b, d) in TET_FACES.items():
            if all(pred(xyz_of[c[k]]) for k in (a, b, d)):
                out.append((e, fno))
    return out


def write_inp(job, ids, xyz, eids, conn, R, load):
    perm = GMSH2CCX[11][1]
    connc = conn[:, perm]
    X = dict(zip(ids, xyz))
    f = open(os.path.join(W, job + ".inp"), "w")
    write_nodes(f, ids, xyz)
    write_elements(f, 11, eids, conn, "EALL")
    x0 = ids[np.isclose(xyz[:, 0], 0)]
    write_nset(f, "X0", x0)
    o = ids[np.argmin(np.linalg.norm(xyz - [0, 0, 0], axis=1))]
    ob = ids[np.argmin(np.linalg.norm(xyz - [0, B, 0], axis=1))]
    a, b = R[:, 0], R[:, 1]
    f.write(f"*ORIENTATION, NAME=OR1, SYSTEM=RECTANGULAR\n{a[0]:.12g},{a[1]:.12g},{a[2]:.12g},{b[0]:.12g},{b[1]:.12g},{b[2]:.12g}\n")
    f.write("*MATERIAL, NAME=PRINT\n*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
    f.write(f"{E1},{E2},{E3},{nu12},{nu13},{nu23},{G12},{G13}\n{G23},0.\n")
    f.write(f"*DENSITY\n{RHO}\n")
    f.write("*SOLID SECTION, ELSET=EALL, MATERIAL=PRINT, ORIENTATION=OR1\n")
    f.write("*BOUNDARY\n")
    if load == "tension":
        f.write("X0,1\n"); f.write(f"{o},2,3\n{ob},3\n")
    else:
        f.write("X0,1,3\n")
    f.write("*STEP\n*STATIC\n")
    if load == "tension":
        fl = faces_on(X, connc, eids, lambda p: abs(p[0] - L) < 1e-9)
        f.write("*DLOAD\n")
        for e, fn in fl:
            f.write(f"{e},P{fn},{-SIG}\n")        # negative pressure = tension
    else:
        fl = faces_on(X, connc, eids, lambda p: abs(p[0] - L) < 1e-9)
        # tip shear: uniform traction in -z over end face via *DLOAD is normal-only, so
        # use consistent nodal loads: for 6-node triangle faces, corner 0, midside 1/3 of F_face
        f.write("*CLOAD\n")
        # distribute P with tributary weights computed from face triangles
        w = tip_weights(X, connc, eids, fl)
        for n_, wt in w.items():
            f.write(f"{n_},3,{-P_TIP * wt:.10g}\n")
    f.write("*NODE FILE\nU\n*EL FILE\nS,E\n*NODE PRINT, NSET=NALL\nU\n*END STEP\n")
    f.close()


def tip_weights(X, connc, eids, fl):
    """Consistent nodal weights of a uniform traction on 6-node triangle faces
    (corner nodes 0, mid-edge nodes A/3)."""
    pos = {e: i for i, e in enumerate(eids)}
    mid = {(0, 1): 4, (1, 2): 5, (0, 2): 6, (0, 3): 7, (1, 3): 8, (2, 3): 9}
    w = {}; Atot = 0.0
    for e, fn in fl:
        c = connc[pos[e]]
        a, b, d = TET_FACES[fn]
        pa, pb, pd = X[c[a]], X[c[b]], X[c[d]]
        A = 0.5 * np.linalg.norm(np.cross(pb - pa, pd - pa)); Atot += A
        for (i, j) in ((a, b), (b, d), (d, a)):
            key = (min(i, j), max(i, j))
            m = c[mid[key]]
            w[m] = w.get(m, 0.0) + A / 3
    return {k: v / Atot for k, v in w.items()}


SIG = 10.0      # MPa tension
P_TIP = 50.0    # N tip shear


def analytic_tension(R):
    C4 = global_C4(R)
    # solve for strain under sigma = SIG e_x e_x
    Cv = np.zeros((6, 6)); pairs = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]
    for I, (i, j) in enumerate(pairs):
        for J, (k, l) in enumerate(pairs):
            Cv[I, J] = C4[i, j, k, l]   # unknowns: engineering strains (gamma = 2 eps_ij)
    eps = np.linalg.solve(Cv, np.array([SIG, 0, 0, 0, 0, 0]))   # [exx,eyy,ezz,gamma_xy,gamma_xz,gamma_yz]
    return eps


def skfem_solve(ids, xyz, conn, R, load):
    from skfem import MeshTet, Basis, FacetBasis, ElementVector, ElementTetP2, \
        BilinearForm, LinearForm, asm, solve, condense
    from skfem.helpers import sym_grad, ddot
    corner = conn[:, :4]
    used = np.unique(corner)
    remap = -np.ones(ids.max() + 1, dtype=np.int64)
    pos = {n: i for i, n in enumerate(ids)}
    p = np.array([xyz[pos[n]] for n in used]).T
    remap[used] = np.arange(len(used))
    t = remap[corner].T
    m = MeshTet(p, t)
    e = ElementVector(ElementTetP2())
    basis = Basis(m, e, intorder=4)
    C4 = global_C4(R)

    @BilinearForm
    def a(u, v, w):
        eu = sym_grad(u)
        sig = np.einsum("ijkl,kl...->ij...", C4, eu)
        return ddot(sig, sym_grad(v))

    t0 = time.perf_counter()
    K = asm(a, basis)
    fb = FacetBasis(m, e, facets=m.facets_satisfying(lambda x: np.isclose(x[0], L)), intorder=4)
    if load == "tension":
        @LinearForm
        def lf(v, w):
            return SIG * v[0]
    else:
        AREA = B * H
        @LinearForm
        def lf(v, w):
            return -P_TIP / AREA * v[2]
    f = asm(lf, fb)
    if load == "tension":
        D = basis.get_dofs(lambda x: np.isclose(x[0], 0.0)).all(["u^1"])
        io = np.argmin(np.linalg.norm(m.p.T - [0, 0, 0], axis=1))
        ib = np.argmin(np.linalg.norm(m.p.T - [0, B, 0], axis=1))
        D = np.concatenate([D, basis.nodal_dofs[1:3, io], basis.nodal_dofs[2:3, ib]])
    else:
        D = basis.get_dofs(lambda x: np.isclose(x[0], 0.0)).all()
    u = solve(*condense(K, f, D=D), solver=None)
    dt = time.perf_counter() - t0
    return m, basis, u, dt, K.shape[0]


def main():
    ids, xyz, eids, conn = mesh()
    print(f"mesh: {len(ids)} nodes, {len(eids)} C3D10, LC={LC}")
    results = {"nodes": int(len(ids)), "elements": int(len(eids)), "LC": LC}
    # ---------------- d1 tension, tilted print axes
    R = rot("z", 30.0) @ rot("y", 40.0)          # print-axes tilt: 40 deg about y then 30 deg about z
    write_inp("d1_tension", ids, xyz, eids, conn, R, "tension")
    dt, out = run_ccx(W, "d1_tension")
    frd = read_frd(os.path.join(W, "d1_tension.frd"))
    nid, U, _ = frd_field(frd, "DISP")
    P = np.array([frd["nodes"][k] for k in nid])
    eps = analytic_tension(R)
    tip = np.isclose(P[:, 0], L)
    ux_tip = U[tip, 0].mean()
    i_l00 = np.argmin(np.linalg.norm(P - [L, 0, 0], axis=1))
    ana = dict(ux=eps[0] * L, uy=eps[3] * L, uz=eps[4] * L, Ex_eff=SIG / eps[0])
    fe = dict(ux=ux_tip, uy=U[i_l00, 1], uz=U[i_l00, 2], Ex_eff=SIG * L / ux_tip)
    _, S, _ = frd_field(frd, "STRESS")
    print("d1 ccx time %.2fs" % dt)
    print("d1 analytic", ana); print("d1 ccx     ", fe)
    print("d1 stress sxx range", S[:, 0].min(), S[:, 0].max(), " max|other|", np.abs(S[:, 1:]).max())
    results["d1"] = dict(R=R.tolist(), analytic=ana, ccx=fe, ccx_time_s=dt,
                         sxx_min=float(S[:, 0].min()), sxx_max=float(S[:, 0].max()),
                         max_abs_other_stress=float(np.abs(S[:, 1:]).max()))
    frd_to_vtu(frd, os.path.join(W, "d1_tension.vtu"))
    # scikit-fem
    m, basis, u, dts, ndof = skfem_solve(ids, xyz, conn, R, "tension")
    ux = u[basis.nodal_dofs[0]]; uy = u[basis.nodal_dofs[1]]; uz = u[basis.nodal_dofs[2]]
    tipn = np.isclose(m.p[0], L)
    j = np.argmin(np.linalg.norm(m.p.T - [L, 0, 0], axis=1))
    sk = dict(ux=ux[tipn].mean(), uy=uy[j], uz=uz[j], Ex_eff=SIG * L / ux[tipn].mean())
    print("d1 skfem    ", sk, "time %.2fs ndof %d" % (dts, ndof))
    results["d1"]["skfem"] = sk; results["d1"]["skfem_time_s"] = dts; results["d1"]["ndof"] = ndof

    # ---------------- d2 cantilever, aligned axes but build dir = global z (bending about y)
    R2 = np.eye(3)
    write_inp("d2_cantilever", ids, xyz, eids, conn, R2, "cantilever")
    dt2, out = run_ccx(W, "d2_cantilever")
    frd2 = read_frd(os.path.join(W, "d2_cantilever.frd"))
    nid, U2, _ = frd_field(frd2, "DISP")
    P2 = np.array([frd2["nodes"][k] for k in nid])
    tip = np.isclose(P2[:, 0], L)
    w_fe = U2[tip, 2].mean()
    I = B * H ** 3 / 12; A = B * H; kappa = 5 / 6
    w_b = -P_TIP * L ** 3 / (3 * E1 * I)
    w_s = -P_TIP * L / (kappa * G13 * A)
    _, S2, _ = frd_field(frd2, "STRESS")
    # root bending stress at x = 0.25L (away from clamped-face singular region), top fibre
    xs = 0.25 * L
    sel = np.isclose(P2[:, 0], xs, atol=LC / 2) & np.isclose(P2[:, 2], H)
    sb_fe = S2[sel, 0].mean() if sel.any() else np.nan
    sb_an = P_TIP * (L - xs) * (H / 2) / I
    m2, basis2, u2, dts2, ndof2 = skfem_solve(ids, xyz, conn, R2, "cantilever")
    tipn = np.isclose(m2.p[0], L)
    w_sk = u2[basis2.nodal_dofs[2]][tipn].mean()
    print("d2 ccx time %.2fs, tip w ccx %.5f skfem %.5f  Timoshenko %.5f (bending %.5f + shear %.5f)" %
          (dt2, w_fe, w_sk, w_b + w_s, w_b, w_s))
    print("d2 bending stress at x=L/4 top: ccx %.3f analytic %.3f (n=%d nodes)" % (sb_fe, sb_an, sel.sum()))
    results["d2"] = dict(w_ccx=w_fe, w_skfem=w_sk, w_timoshenko=w_b + w_s, w_bending=w_b,
                         w_shear=w_s, sigma_x_L4_ccx=sb_fe, sigma_x_L4_beam=sb_an,
                         ccx_time_s=dt2, skfem_time_s=dts2)
    frd_to_vtu(frd2, os.path.join(W, "d2_cantilever.vtu"))
    json.dump(results, open(os.path.join(W, f"results_LC{LC}.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
