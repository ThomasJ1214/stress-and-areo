"""Split one SU2 boundary marker into several markers by element-centroid classification.

Needed because gmsh's extrudeBoundaryLayer only worked robustly on a single discrete wall surface
(multi-patch extrusion failed at patch junctions, see REPORT.md). Component markers (nose/body/fins/base)
are recovered afterwards so SU2 still reports per-component forces.

python split_markers.py in.su2 out.su2 wall
"""
import sys
import numpy as np

src, dst, marker = sys.argv[1], sys.argv[2], sys.argv[3]
R, LN, L = 0.05, 0.30, 1.0

lines = open(src).read().splitlines()
i_poin = next(i for i, l in enumerate(lines) if l.startswith("NPOIN="))
npoin = int(lines[i_poin].split("=")[1].split()[0])
X = np.array([[float(v) for v in lines[i_poin + 1 + k].split()[:3]] for k in range(npoin)])
i_mark = next(i for i, l in enumerate(lines) if l.startswith("NMARK="))
nmark = int(lines[i_mark].split("=")[1])
markers = []
i = i_mark + 1
for _ in range(nmark):
    tag = lines[i].split("=")[1].strip()
    ne = int(lines[i + 1].split("=")[1])
    elems = lines[i + 2:i + 2 + ne]
    markers.append((tag, elems))
    i += 2 + ne
out_markers = []
for tag, elems in markers:
    if tag != marker:
        out_markers.append((tag, elems))
        continue
    groups = {"nose": [], "body": [], "fins": [], "base": []}
    for e in elems:
        nodes = [int(v) for v in e.split()[1:]]
        c = X[nodes].mean(0)
        P = X[nodes]
        n = np.cross(P[1] - P[0], P[2] - P[0])
        n /= np.linalg.norm(n) + 1e-300
        r = np.hypot(c[1], c[2])
        if c[0] <= LN - 1e-6 and r <= R + 1e-4:
            g = "nose"
        elif abs(c[0] - L) < 1e-7 and abs(abs(n[0]) - 1) < 1e-6:
            g = "base"
        elif r <= R + 1e-5 and abs(np.hypot(P[:, 1], P[:, 2]).max() - R) < 2e-4:
            g = "body"
        else:
            g = "fins"
        groups[g].append(e)
    for g, el in groups.items():
        print(f"{g}: {len(el)} elements")
        out_markers.append((g, el))
with open(dst, "w") as fh:
    fh.write("\n".join(lines[:i_mark]) + "\n")
    fh.write(f"NMARK= {len(out_markers)}\n")
    for tag, el in out_markers:
        fh.write(f"MARKER_TAG= {tag}\nMARKER_ELEMS= {len(el)}\n")
        fh.write("\n".join(el) + "\n")
    rest = lines[i:]
    if rest:
        fh.write("\n".join(rest) + "\n")
print("wrote", dst)
