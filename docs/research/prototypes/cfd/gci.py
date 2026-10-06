"""Richardson extrapolation / Roache GCI for the 3-level uniform refinement study (u2.8 -> u2.0 -> u1.4).
r = representative cell-size ratio = (N_fine/N_coarse)^(1/3) from node counts.
p = ln((f3-f2)/(f2-f1)) / ln(r)   (constant r), f_ext = f1 + (f1-f2)/(r^p-1), GCI_fine = 1.25 |(f1-f2)/f1| / (r^p-1)
"""
import json
import math
import re

levels = ["2.8", "2.0", "1.4"]
nodes = {}
for s in levels:
    log = open(f"meshes/rocket_u{s}_small.log").read()
    nodes[s] = int(re.search(r"nodes=(\d+)", log).group(1))


def get(aoa, key):
    out = []
    for s in levels:
        p = json.load(open(f"runs/m2_a{aoa}_u{s}/post.json"))
        if key == "x_cp":
            out.append(-p["CMy"] / p["CFz"])
        elif "." in key and not key.startswith("nose_Cp"):
            a, b = key.split(".")
            out.append(p[a][b])
        else:
            out.append(p[key])
    return out


r21 = (nodes["1.4"] / nodes["2.0"]) ** (1 / 3)
r32 = (nodes["2.0"] / nodes["2.8"]) ** (1 / 3)
print(f"nodes {nodes}, r21={r21:.3f}, r32={r32:.3f}")
for aoa, key, ref in [(0, "nose.CFx", 0.09553), (0, "nose_Cp_area_avg_x>0.2Ln", 0.09553), (0, "CFx", None),
                      (4, "CFz", None), (4, "x_cp", None), (4, "nose.CFz", None), (4, "fins.CFz", None),
                      (4, "CFx", None), (4, "base.CFx", None)]:
    f3, f2, f1 = get(aoa, key)
    e21, e32 = f1 - f2, f2 - f3
    r = math.sqrt(r21 * r32)
    if e21 * e32 > 0:
        p = math.log(abs(e32 / e21)) / math.log(r)
        fext = f1 + e21 / (r ** p - 1)
        gci = 1.25 * abs(e21 / f1) / (r ** p - 1) * 100
        tail = f"p={p:.2f} f_ext={fext:.5f} GCI_fine={gci:.2f}%"
    else:
        tail = "oscillatory convergence (no Richardson)"
    refs = f"  exact={ref:.5f} err_fine={100*(f1-ref)/ref:+.2f}%" if ref else ""
    print(f"AoA{aoa} {key:28s} coarse={f3:.5f} medium={f2:.5f} fine={f1:.5f}  {tail}{refs}")
