"""Collect results of all runs into a markdown table (results_table.txt)."""
import glob
import json
import os
import re

rows = []
for d in sorted(glob.glob("runs/*/")):
    d = d.rstrip("/")
    pj = os.path.join(d, "post.json")
    if not os.path.exists(pj):
        continue
    p = json.load(open(pj))
    wt = open(os.path.join(d, "walltime.txt")).read() if os.path.exists(os.path.join(d, "walltime.txt")) else ""
    rss = open(os.path.join(d, "peak_rss.txt")).read() if os.path.exists(os.path.join(d, "peak_rss.txt")) else ""
    w = re.search(r"wall_s=([\d.]+)", wt)
    r = re.search(r"peak_rss_kB=(\d+)", rss)
    log = open(os.path.join(d, "run.log")).read() if os.path.exists(os.path.join(d, "run.log")) else ""
    npts = re.search(r"(\d+) grid points", log) or re.search(r"(\d+) points", log)
    cfg = open(os.path.join(d, "case.cfg")).read()
    mesh = re.search(r"MESH_FILENAME= (.*)", cfg).group(1).split("/")[-1]
    rows.append(dict(case=os.path.basename(d), mesh=mesh, it=p.get("iterations"), wall=float(w.group(1)) if w else None,
                     rss=int(r.group(1)) / 1e6 if r else None, relrms=p.get("relrms[Rho]"),
                     CA=p.get("CFx"), CN=p.get("CFz"), CMy=p.get("CMy"), xcp=p.get("x_cp_over_D_from_nose"),
                     CA_nose=p["nose"].get("CFx"), CN_nose=p["nose"].get("CFz"), CA_fins=p["fins"].get("CFx"),
                     CN_fins=p["fins"].get("CFz"), CN_body=p["body"].get("CFz"), CA_base=p["base"].get("CFx"),
                     cp_nose=p.get("nose_Cp_area_avg_x>0.2Ln")))


def f(v, n=4):
    return "" if v is None else (f"{v:.{n}f}" if isinstance(v, float) else str(v))


hdr = "| case | mesh | iters | wall s | peak RSS GB | CA | CN | CMy (nose, D) | x_cp/D | CA_nose | CN_nose | CN_body | CN_fins | CA_fins | CA_base | mean Cp nose (x>0.06) |"
out = [hdr, "|" + "---|" * hdr.count("|")[:-1] if False else "|" + "---|" * (hdr.count("|") - 1)]
for r in rows:
    out.append(f"| {r['case']} | {r['mesh']} | {r['it']} | {f(r['wall'],0)} | {f(r['rss'],2)} | {f(r['CA'])} | {f(r['CN'])} | "
               f"{f(r['CMy'])} | {f(r['xcp'],3) if r['CN'] and abs(r['CN'])>0.05 else ''} | {f(r['CA_nose'])} | {f(r['CN_nose'])} | {f(r['CN_body'])} | "
               f"{f(r['CN_fins'])} | {f(r['CA_fins'])} | {f(r['CA_base'])} | {f(r['cp_nose'])} |")
open("results_table.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
