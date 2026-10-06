"""Case (g): geometrically nonlinear collapse of the [0/90/45/-45]s tube with an eigenmode-shaped
imperfection (amplitude XI * t), *STATIC NLGEOM with prescribed end shortening.
Compares collapse load with linear *BUCKLE and with the NASA SP-8007 knockdown.
"""
import os, sys, json, re, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HEL", "4.0")
import test_a_tube_buckle as ta
from fea_common import *

W = os.path.join(HERE, "case_g"); os.makedirs(W, exist_ok=True)
ta.W = W
XI = float(os.environ.get("XI", 0.1))
NMODES = int(os.environ.get("NMODES", 5))


def composite_header(f, ids, xyz, conn):
    write_nodes(f, ids, xyz)
    f.write("*ELEMENT, TYPE=S8R, ELSET=EALL\n")
    for e, c in enumerate(conn, 1):
        f.write(f"{e}," + ",".join(str(int(v)) for v in c) + "\n")
    bot = ids[np.isclose(xyz[:, 2], 0)]; top = ids[np.isclose(xyz[:, 2], ta.L)]
    write_nset(f, "BOT", bot); write_nset(f, "TOP", top)
    f.write("*ORIENTATION, NAME=OAX, SYSTEM=RECTANGULAR\n0.,0.,1.,1.,0.,0.\n")
    for th in sorted(set(ta.LAYUP)):
        f.write(f"*MATERIAL, NAME=PLY{th + 100}\n*ELASTIC, TYPE=ANISO\n" + ta.aniso_card(th))
    f.write("*SHELL SECTION, ELSET=EALL, COMPOSITE, ORIENTATION=OAX\n")
    for th in ta.LAYUP:
        f.write(f"{ta.TPLY},,PLY{th + 100}\n")
    f.write("*BOUNDARY\nBOT,1,6\nTOP,1,2\nTOP,4,6\n")


def main():
    ids, xyz, els, nth, nz = ta.tube_mesh()
    (gt, (eids, conn)), = els.items()
    # 1) linear buckling with 2D (shell-node) mode output
    f = open(os.path.join(W, "g0_buckle.inp"), "w"); composite_header(f, ids, xyz, conn)
    topn = ids[np.isclose(xyz[:, 2], ta.L)]
    f.write(f"*STEP\n*BUCKLE\n{NMODES}\n*CLOAD\n")
    # uniform reference load 1000 N with consistent edge weights (reuse ta logic via quick recompute)
    X = dict(zip(ids, xyz)); topset = set(topn.tolist()); w = {}
    for c in conn:
        for a, m, b in ((0, 4, 1), (1, 5, 2), (2, 6, 3), (3, 7, 0)):
            if c[a] in topset and c[b] in topset and c[m] in topset:
                le = np.linalg.norm(X[c[a]] - X[c[b]])
                for n_, wt in ((c[a], 1 / 6), (c[m], 2 / 3), (c[b], 1 / 6)):
                    w[n_] = w.get(n_, 0.0) + wt * le
    tot = sum(w.values())
    for n_, v in w.items():
        f.write(f"{n_},3,{-1000.0 * v / tot:.10g}\n")
    f.write("*NODE FILE, OUTPUT=2D\nU\n*END STEP\n"); f.close()
    dt0, _ = run_ccx(W, "g0_buckle")
    lams = read_dat_eigen(os.path.join(W, "g0_buckle.dat"))["buckle"]
    lam = min(lams); print("buckling factors:", lams)
    fr = read_frd(os.path.join(W, "g0_buckle.frd"))
    disp = [r for r in fr["results"] if r["name"] == "DISP" and r["value"] and r["value"] > 0]
    mode = min(disp, key=lambda r: r["value"])["data"]
    phi = np.array([mode.get(int(n), np.zeros(3))[:3] for n in ids])
    amp = np.abs(np.hypot(phi[:, 0], phi[:, 1])).max()
    print(f"linear buckle: P_cr = {lam * 1000:.0f} N ({dt0:.1f}s); mode max radial {amp:.3g}")
    xyz_imp = xyz + XI * ta.T * phi / np.abs(phi).max()
    # 2) nonlinear static, displacement controlled
    A11 = ta.laminate_abd()[0][0, 0]
    d_cr = lam * 1000 * ta.L / (A11 * 2 * np.pi * ta.R)
    dmax = 1.4 * d_cr
    f = open(os.path.join(W, "g1_nlgeom.inp"), "w"); composite_header(f, ids, xyz_imp, conn)
    f.write(f"*STEP, NLGEOM, INC=400\n*STATIC\n0.05,1.0,1e-5,0.05\n*BOUNDARY\nTOP,3,3,{-dmax:.6g}\n")
    f.write("*NODE PRINT, NSET=TOP, TOTALS=ONLY\nRF\n*NODE FILE, OUTPUT=2D\nU\n*END STEP\n"); f.close()
    t0 = time.perf_counter()
    try:
        dt1, out = run_ccx(W, "g1_nlgeom", timeout=1500)
        status = "completed"
    except Exception as ex:
        dt1 = time.perf_counter() - t0; status = "stopped: " + str(ex)[-300:].replace("\n", " ")
    txt = open(os.path.join(W, "g1_nlgeom.dat")).read()
    rf = re.findall(r"total force \(fx,fy,fz\) for set TOP and time\s+([\dE\.\+\-]+)\s*\n\s*\n?\s*([-\dE\.\+]+)\s+([-\dE\.\+]+)\s+([-\dE\.\+]+)", txt)
    tt = np.array([float(a[0]) for a in rf]); Fz = np.array([abs(float(a[3])) for a in rf])
    Pmax = Fz.max() if len(Fz) else np.nan
    g_sp, phi_sp = ta.sp8007_gamma_ortho(*[ta.laminate_abd()[i] for i in (0, 2)])
    print(f"NLGEOM XI={XI}: {status[:120]} ({dt1:.0f}s, {len(tt)} increments). Peak load {Pmax:.0f} N = "
          f"{Pmax / (lam * 1000):.3f} x linear; SP-8007 gamma = {g_sp:.3f}")
    print("load path (end shortening mm, N):", [(round(t * dmax, 3), round(v)) for t, v in zip(tt, Fz)])
    json.dump(dict(XI=XI, P_lin=lam * 1000, P_peak=Pmax, ratio=Pmax / (lam * 1000), gamma_sp8007=g_sp,
                   status=status, time_s=dt1, path=[(t * dmax, v) for t, v in zip(tt, Fz)]),
              open(os.path.join(W, f"results_XI{XI}.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
