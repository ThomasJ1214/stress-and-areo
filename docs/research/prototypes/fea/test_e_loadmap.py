"""Case (e): map a 'CFD' surface pressure field + thrust + D'Alembert inertial loads onto a
C3D10 model of a closed-end airframe section, solved free-free ("inertia relief" by hand).

* CFD surrogate: separate, finer linear-triangle mesh of the outer skin with vertex pressures
  p = p0 + p1*cos(theta)*(1 - z/L)   (asymmetric, gives lateral force + pitching moment)
* Mapping: closest-point projection onto CFD triangles + barycentric interpolation at the
  6-point quadrature points of every FE outer face; consistent nodal forces
  f_i = int N_i p (-n) dA  (6-node triangle shape functions) -> *CLOAD
* Thrust: uniform pressure on the aft bulkhead face (*DLOAD P on tet faces).
* Inertia: rigid-body a and alpha from total external force/moment; translational part via
  *DLOAD GRAV, rotational part as consistent nodal forces of rho*(-(alpha x r)) over all tets.
* Support: statically determinate 3-2-1 constraint -> reactions must be ~0 if balanced.
"""
import os, sys, json, time
import numpy as np
import gmsh
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fea_common import *

W = os.path.join(HERE, "case_e"); os.makedirs(W, exist_ok=True)
RO, RI, L, TB = 49.0, 47.0, 200.0, 6.0          # mm; closed (bulkhead) at z=0
RHO = 1.85e-9                                     # fiberglass-ish t/mm^3
E, NU = 20000.0, 0.15
P0, P1 = 0.02, 0.03                               # MPa
THRUST = 2000.0                                   # N, pushes +z on aft face z=0
LC = float(os.environ.get("LC", 4.0))


def pressure(x):
    th = np.arctan2(x[..., 1], x[..., 0])
    return P0 + P1 * np.cos(th) * (1 - x[..., 2] / L)


def fe_mesh():
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("cup")
    o = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, RO)
    i = gmsh.model.occ.addCylinder(0, 0, TB, 0, 0, L, RI)
    gmsh.model.occ.cut([(3, o)], [(3, i)]); gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", LC); gmsh.option.setNumber("Mesh.MeshSizeMin", LC / 2)
    gmsh.model.mesh.generate(3); gmsh.model.mesh.setOrder(2)
    ids, xyz, els = gmsh_nodes_elements(gmsh, 3)
    gmsh.finalize()
    return ids, xyz, els[11]


def cfd_surface_mesh(lc=2.0):
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("cfd")
    o = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, RO); gmsh.model.occ.synchronize()
    # keep only the lateral skin (exclude end caps)
    gmsh.option.setNumber("Mesh.MeshSizeMax", lc)
    gmsh.model.mesh.generate(2)
    tri_nodes = []; xyz_all = {}
    ntags, coords, _ = gmsh.model.mesh.getNodes(); coords = np.reshape(coords, (-1, 3))
    for t_, c_ in zip(ntags, coords):
        xyz_all[int(t_)] = c_
    for (d, s) in gmsh.model.getEntities(2):
        com = gmsh.model.occ.getCenterOfMass(d, s)
        if abs(com[2] - L / 2) > 1e-6:      # end caps have COM at z=0 or z=L
            continue
        et, etags, enodes = gmsh.model.mesh.getElements(2, s)
        tri_nodes.append(np.reshape(enodes[0], (-1, 3)))
    gmsh.finalize()
    tri = np.vstack(tri_nodes)
    used = np.unique(tri); m = {n: k for k, n in enumerate(used)}
    pts = np.array([xyz_all[n] for n in used]); tri = np.vectorize(m.get)(tri)
    return pts, tri


def closest_point_tri(p, a, b, c):
    """Ericson's closest point on triangle; returns barycentric (u,v,w)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0: return np.array([1, 0, 0.])
    bp = p - b; d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3: return np.array([0, 1, 0.])
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3); return np.array([1 - v, v, 0])
    cp = p - c; d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6: return np.array([0, 0, 1.])
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6); return np.array([1 - w, 0, w])
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); return np.array([0, 1 - w, w])
    den = 1 / (va + vb + vc); v = vb * den; w = vc * den
    return np.array([1 - v - w, v, w])


class SurfaceInterpolator:
    def __init__(self, pts, tri, vals):
        self.pts, self.tri, self.vals = pts, tri, vals
        self.tree = cKDTree(pts[tri].mean(axis=1))

    def __call__(self, q):
        out = np.empty(len(q)); dist = np.empty(len(q))
        _, cand = self.tree.query(q, k=8)
        for i, (p, cs) in enumerate(zip(q, cand)):
            best = (np.inf, 0.0)
            for t in cs:
                a, b, c = self.pts[self.tri[t]]
                bc = closest_point_tri(p, a, b, c)
                x = bc[0] * a + bc[1] * b + bc[2] * c
                d = np.linalg.norm(x - p)
                if d < best[0]:
                    best = (d, bc @ self.vals[self.tri[t]])
            dist[i], out[i] = best
        return out, dist


# 6-node triangle: corners 0,1,2 ; mids 3:(0-1) 4:(1-2) 5:(2-0); Dunavant degree-4 (6 pts)
TRI_QP = np.array([[0.445948490915965, 0.445948490915965], [0.445948490915965, 0.108103018168070],
                   [0.108103018168070, 0.445948490915965], [0.091576213509771, 0.091576213509771],
                   [0.091576213509771, 0.816847572980459], [0.816847572980459, 0.091576213509771]])
TRI_QW = np.array([0.223381589678011] * 3 + [0.109951743655322] * 3) * 0.5


def tri6_N(r, s):
    t = 1 - r - s
    N = np.array([t * (2 * t - 1), r * (2 * r - 1), s * (2 * s - 1), 4 * t * r, 4 * r * s, 4 * s * t])
    dNr = np.array([-(4 * t - 1), 4 * r - 1, 0, 4 * (t - r), 4 * s, -4 * s])
    dNs = np.array([-(4 * t - 1), 0, 4 * s - 1, -4 * r, 4 * r, 4 * (t - s)])
    return N, dNr, dNs


TET_FACES6 = {1: (0, 1, 2, 4, 5, 6), 2: (0, 3, 1, 7, 8, 4), 3: (1, 3, 2, 8, 9, 5), 4: (2, 3, 0, 9, 7, 6)}


def boundary_faces(conn_ccx, eids):
    """faces (elem, faceno, 6 node ids) that appear once (outer boundary)."""
    cnt = {}
    for e, c in zip(eids, conn_ccx):
        for fn, loc in TET_FACES6.items():
            key = tuple(sorted(c[list(loc[:3])]))
            cnt.setdefault(key, []).append((e, fn, c[list(loc)]))
    return [v[0] for v in cnt.values() if len(v) == 1]


def main():
    t0 = time.perf_counter()
    ids, xyz, (eids, conn) = fe_mesh()
    connc = conn[:, GMSH2CCX[11][1]]
    X = {int(n): p for n, p in zip(ids, xyz)}
    print(f"FE mesh {len(ids)} nodes {len(eids)} C3D10")
    pts, tri = cfd_surface_mesh()
    pv_ = pressure(pts)
    interp = SurfaceInterpolator(pts, tri, pv_)
    print(f"CFD surrogate surface: {len(pts)} vertices, {len(tri)} triangles")
    # reference integrals on the CFD mesh (piecewise-linear p, flat triangles), force = -p n dA
    Fc = np.zeros(3); Mc = np.zeros(3)
    for t in tri:
        a, b, c = pts[t]; n2 = np.cross(b - a, c - a)
        cen = (a + b + c) / 3
        if n2 @ np.array([cen[0], cen[1], 0]) < 0: n2 = -n2       # outward
        pm = pv_[t].mean()
        f = -pm * n2 / 2; Fc += f; Mc += np.cross(cen, f)
    # ---- map onto FE outer lateral faces, consistent nodal forces
    faces = boundary_faces(connc, eids)
    lat = [f for f in faces if all(abs(np.hypot(*X[n][:2]) - RO) < 1e-3 for n in f[2][:3])]
    aft = [f for f in faces if all(abs(X[n][2]) < 1e-9 for n in f[2][:3])]
    fnod = {}; Ff = np.zeros(3); Mf = np.zeros(3); maxd = 0.0
    qpts_all = []
    for (e, fn, nodes6) in lat:
        P6 = np.array([X[n] for n in nodes6])
        for (r, s), w in zip(TRI_QP, TRI_QW):
            N, dr, ds = tri6_N(r, s)
            x = N @ P6; jr = dr @ P6; js = ds @ P6
            n2 = np.cross(jr, js)
            if n2 @ np.array([x[0], x[1], 0]) < 0: n2 = -n2
            qpts_all.append((x, n2 * w, nodes6, N))
    q = np.array([v[0] for v in qpts_all])
    pq, dq = interp(q)
    for (x, ndA, nodes6, N), p in zip(qpts_all, pq):
        f = -p * ndA
        Ff += f; Mf += np.cross(x, f)
        for n, Ni in zip(nodes6, N):
            fnod[n] = fnod.get(n, np.zeros(3)) + Ni * f
    print(f"mapping: {len(lat)} lateral FE faces, {len(q)} quadrature pts, max projection distance {dq.max():.4f} mm")
    print("CFD integral F", Fc, "M", Mc); print("FE mapped  F", Ff, "M", Mf)
    # ---- thrust as pressure on aft face (negative pressure pulls outward? face normal points -z,
    # pressure acts along -normal = +z)
    A_aft = np.pi * RO ** 2
    p_thrust = THRUST / A_aft
    F_ext = Ff + np.array([0, 0, THRUST]); M_ext = Mf.copy()   # thrust acts on axis -> no moment about origin x,y? (uniform on disc centred on axis)
    # ---- mass properties via quadrature over tets
    from skfem.quadrature import get_quadrature
    from skfem.refdom import RefTet
    qp, qw = get_quadrature(RefTet, 4)

    def tet10_N(l):
        x, y, z = l; t = 1 - x - y - z
        return np.array([t * (2 * t - 1), x * (2 * x - 1), y * (2 * y - 1), z * (2 * z - 1),
                         4 * t * x, 4 * x * y, 4 * y * t, 4 * t * z, 4 * x * z, 4 * y * z])
    Nq = np.array([tet10_N(qp[:, k]) for k in range(qp.shape[1])])       # (nq, 10)
    mass = 0.0; mx = np.zeros(3); elem_q = []
    for e, c in zip(eids, connc):
        P = np.array([X[n] for n in c])
        J = np.array([P[1] - P[0], P[2] - P[0], P[3] - P[0]]).T
        dV = abs(np.linalg.det(J)) * qw
        xq = Nq @ P
        mass += RHO * dV.sum(); mx += RHO * (dV[:, None] * xq).sum(0)
        elem_q.append((c, xq, dV))
    xcg = mx / mass
    Icg = np.zeros((3, 3))
    for c, xq, dV in elem_q:
        r = xq - xcg
        for k in range(len(dV)):
            Icg += RHO * dV[k] * ((r[k] @ r[k]) * np.eye(3) - np.outer(r[k], r[k]))
    M_cg = M_ext - np.cross(xcg, F_ext)
    acc = F_ext / mass
    alpha = np.linalg.solve(Icg, M_cg)
    print(f"mass {mass * 1000:.4f} kg, xcg {xcg}, a = {acc / 9810} g, alpha = {alpha} rad/s^2")
    # rotational inertial nodal forces: f_i = -int N_i rho (alpha x (x - xcg)) dV
    frot = {}
    for c, xq, dV in elem_q:
        b = -np.cross(alpha, xq - xcg) * RHO                      # (nq,3) force per volume
        fe = (Nq * dV[:, None]).T @ b                              # (10,3)
        for n, f in zip(c, fe):
            frot[n] = frot.get(n, np.zeros(3)) + f
    # ---- write deck
    job = "e_loadmap"
    f = open(os.path.join(W, job + ".inp"), "w")
    write_nodes(f, ids, xyz); write_elements(f, 11, eids, conn, "EALL")
    # 3-2-1 support at three skin nodes far from each other on the forward rim (z=L)
    rim = [n for n in ids if abs(X[n][2] - L) < 1e-9 and abs(np.hypot(*X[n][:2]) - RO) < 1e-3]
    rp = np.array([X[n] for n in rim]); ang = np.arctan2(rp[:, 1], rp[:, 0])
    n1 = rim[np.argmin(np.abs(ang - 0))]; n2 = rim[np.argmin(np.abs(ang - 2.0944))]; n3 = rim[np.argmin(np.abs(ang + 2.0944))]
    f.write(f"*MATERIAL, NAME=GF\n*ELASTIC\n{E},{NU}\n*DENSITY\n{RHO}\n")
    f.write("*SOLID SECTION, ELSET=EALL, MATERIAL=GF\n")
    f.write(f"*BOUNDARY\n{n1},1,3\n{n2},2,3\n{n3},3\n")
    write_nset(f, "SUP", [n1, n2, n3])
    f.write("*STEP\n*STATIC\n*DLOAD\n")
    for (e, fn, nodes6) in aft:
        f.write(f"{e},P{fn},{p_thrust:.10g}\n")
    an = np.linalg.norm(acc)
    f.write(f"EALL,GRAV,{an:.10g},{-acc[0] / an:.10g},{-acc[1] / an:.10g},{-acc[2] / an:.10g}\n")
    f.write("*CLOAD\n")
    tot = {}
    for d in (fnod, frot):
        for n, v in d.items():
            tot[n] = tot.get(n, np.zeros(3)) + v
    for n, v in tot.items():
        for k in range(3):
            if v[k] != 0.0:
                f.write(f"{n},{k + 1},{v[k]:.10g}\n")
    f.write("*NODE PRINT, NSET=SUP, TOTALS=YES\nRF\n*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n")
    f.close()
    dt, out = run_ccx(W, job)
    dat = open(os.path.join(W, job + ".dat")).read()
    rf_tot = [float(v) for v in dat.strip().splitlines()[-1].split()]
    frd = read_frd(os.path.join(W, job + ".frd"))
    nidS, S, _ = frd_field(frd, "STRESS")
    vm = von_mises(S)
    print(f"ccx {dt:.2f}s; support reaction totals {rf_tot}  (applied |F| ~ {np.linalg.norm(F_ext):.1f} N)")
    print(f"max von Mises {vm.max():.3f} MPa")
    frd_to_vtu(frd, os.path.join(W, job + ".vtu"))
    res = dict(nodes=len(ids), elements=len(eids), cfd_vertices=len(pts), cfd_tris=len(tri),
               F_cfd=Fc.tolist(), M_cfd=Mc.tolist(), F_mapped=Ff.tolist(), M_mapped=Mf.tolist(),
               max_projection_mm=float(dq.max()), mass_kg=mass * 1000, xcg=xcg.tolist(),
               acc_g=(acc / 9810).tolist(), alpha=alpha.tolist(), reaction_totals=rf_tot,
               F_ext=F_ext.tolist(), ccx_time_s=dt, vm_max=float(vm.max()),
               total_script_time_s=time.perf_counter() - t0)
    json.dump(res, open(os.path.join(W, "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
