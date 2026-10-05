"""
Quantify suspected OpenRocket (23.09/24.12) supersonic-model gaps on the probe rocket using textbook
linear theory.  These are ESTIMATES for prioritising replacements, NOT validated truth.
"""
import math

import or_aero_py as P

g = dict(nose_len=0.30, R=0.04, body_len=1.0, fin_n=4, root=0.15, tip=0.075, sweep=0.06, span=0.08, fin_t=0.003)
Aref = math.pi * g["R"] ** 2
fg = P.trapezoid_fin_geometry(g["root"], g["tip"], g["sweep"], g["span"])
tau = g["R"] / (g["span"] + g["R"])
A_fin = fg["area"]
# exposed 2-panel wing aspect ratio (two opposite fins joined at root)
AR_w = (2 * g["span"]) ** 2 / (2 * A_fin)
fineness = g["nose_len"] / (2 * g["R"])
sin_eps = 1 / math.sqrt(1 + 4 * fineness ** 2)   # half-angle of cone with same L/D

print(f"fin area={A_fin:.5f} m2, exposed-wing AR={AR_w:.3f}, tau={tau:.3f}, nose fineness={fineness:.3f}")
print("M    | fin CNa1 (per fin, Aref) OR | Ackeret 2-sided | Ackeret*rect-tip-corr | ratio OR/corr | "
      "nose CDp OR tangent ogive | cone-equivalent (techdoc intent) | base OR (0.25/M)")
for M in (1.5, 1.75, 2.0, 2.5, 3.0):
    b = math.sqrt(M * M - 1)
    k1, k2, k3 = P.K123(M)
    or_cna1 = A_fin * k1 / Aref                      # OR: single-surface Busemann first-order term
    ack = A_fin * (4 / b) / Aref                     # flat plate, both surfaces: CLa = 4/beta
    corr = (1 - 1 / (2 * b * AR_w)) if b * AR_w >= 1 else float("nan")  # rectangular-wing tip-cone loss
    ack_c = ack * corr
    # nose
    sinphi = 0.0  # tangent ogive joint angle
    xs, ys = P.nose_pressure_table("OGIVE", 1.0, fineness, 1e-4)
    or_nose = P.lin_interp(xs, ys, M)
    cone = 2.1 * sin_eps ** 2 + 0.5 * sin_eps / b
    print(f"{M:4.2f} | {or_cna1:8.3f} | {ack:8.3f} | {ack_c:8.3f} | {or_cna1 / ack_c:5.2f} | "
          f"{or_nose:8.4f} | {cone:8.4f} | {0.25 / M:6.4f}")

# whole-rocket consequence at M=2 (OR vs corrected fins + cone-equivalent nose), CP shift
for M in (2.0, 3.0):
    o = P.rocket_aero(g | dict(wall=0.002), "OGIVE", 1.0, M)
    b = math.sqrt(M * M - 1)
    corr = 1 - 1 / (2 * b * AR_w)
    cna_f_corr = A_fin * (4 / b) * corr / Aref * (g["fin_n"] / 2) * (1 + tau)
    cp_nose = (o["CPx"] * o["CNa"] - (o["CNa"] - 2.0) * 0)  # placeholder
    # recompute CP with corrected fins (same fin CP location as OR)
    cna_f_or = o["CNa"] - 2.0
    x_f = (o["CPx"] * o["CNa"] - 2.0 * ((o["CPx"] * o["CNa"] - cna_f_or * 0) and 0)) if False else None
    # derive fin CP and nose CP from OR breakdown
    # nose CP (slender body): (L*A - V)/A
    nprop = P.symmetric_properties(lambda x: P.shape_radius("OGIVE", x, g["R"], g["nose_len"], 1.0), g["nose_len"])
    x_n = (g["nose_len"] * Aref - nprop["fullVolume"]) / Aref
    x_f = (o["CPx"] * o["CNa"] - 2.0 * x_n) / cna_f_or
    cna_new = 2.0 + cna_f_corr
    cp_new = (2.0 * x_n + cna_f_corr * x_f) / cna_new
    sin_eps = 1 / math.sqrt(1 + 4 * fineness ** 2)
    dcd = (2.1 * sin_eps ** 2 + 0.5 * sin_eps / b) - o["nosePr"]
    print(f"M={M}: OR CNa={o['CNa']:.2f}, CP={o['CPx']:.4f} m, CD={o['CD']:.4f} | with 2-sided+tip-corrected fins: "
          f"CNa={cna_new:.2f}, CP={cp_new:.4f} m (CP shift {1000 * (cp_new - o['CPx']):+.0f} mm = "
          f"{(cp_new - o['CPx']) / (2 * g['R']):+.2f} cal) | nose wave-drag deficit dCD={dcd:+.4f} "
          f"({100 * dcd / o['CD']:+.0f}% of OR CD)")
