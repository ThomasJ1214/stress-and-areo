"""Shared helpers for the FEA research tests: gmsh -> CalculiX .inp writing,
running ccx, and a minimal ASCII .frd / .dat reader.

Units used throughout the tests: mm, N, MPa, tonne/mm^3, s  (consistent set).
"""
import os, re, subprocess, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CCX = os.environ.get("CCX_EXE", os.path.join(HERE, "ccxenv", "bin", "ccx"))

# gmsh element type -> (ccx name, node permutation gmsh->ccx)
GMSH2CCX = {
    16: ("S8R", [0, 1, 2, 3, 4, 5, 6, 7]),          # 8-node quad (serendipity)
    9:  ("S6", [0, 1, 2, 3, 4, 5]),                  # 6-node triangle
    11: ("C3D10", [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]),   # 10-node tet: swap last two
    4:  ("C3D4", [0, 1, 2, 3]),
}


def gmsh_nodes_elements(gmsh, dim, phys_tag=None):
    """Return (node_ids, coords[N,3], {gmsh_type: (elem_ids, conn[nE,nn])})."""
    ntags, coords, _ = gmsh.model.mesh.getNodes()
    coords = np.asarray(coords).reshape(-1, 3)
    order = np.argsort(ntags)
    ntags = np.asarray(ntags)[order]
    coords = coords[order]
    etypes, etags, enodes = gmsh.model.mesh.getElements(dim)
    out = {}
    for et, tags, nodes in zip(etypes, etags, enodes):
        name, nn, *_ = gmsh.model.mesh.getElementProperties(et)
        out[int(et)] = (np.asarray(tags, dtype=np.int64),
                        np.asarray(nodes, dtype=np.int64).reshape(len(tags), -1))
    return ntags.astype(np.int64), coords, out


def write_nodes(f, ids, xyz):
    f.write("*NODE, NSET=NALL\n")
    for i, (x, y, z) in zip(ids, xyz):
        f.write(f"{i},{x:.10g},{y:.10g},{z:.10g}\n")


def write_elements(f, gmsh_type, eids, conn, elset):
    name, perm = GMSH2CCX[gmsh_type]
    f.write(f"*ELEMENT, TYPE={name}, ELSET={elset}\n")
    for e, c in zip(eids, conn):
        c = c[perm]
        vals = [str(e)] + [str(int(v)) for v in c]
        # ccx accepts max 16 entries per line; continue with trailing comma
        line = ",".join(vals[:16])
        if len(vals) > 16:
            line += ",\n" + ",".join(vals[16:])
        f.write(line + "\n")


def write_nset(f, name, ids):
    f.write(f"*NSET, NSET={name}\n")
    ids = list(map(int, ids))
    for k in range(0, len(ids), 10):
        f.write(",".join(map(str, ids[k:k + 10])) + "\n")


def write_elset(f, name, ids):
    f.write(f"*ELSET, ELSET={name}\n")
    ids = list(map(int, ids))
    for k in range(0, len(ids), 10):
        f.write(",".join(map(str, ids[k:k + 10])) + "\n")


def run_ccx(workdir, job, threads=2, exe=None, extra_env=None, timeout=1800):
    """Run ccx -i job in workdir. Returns (wall_seconds, stdout_text)."""
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(threads)
    env["CCX_NPROC_EQUATION_SOLVER"] = str(threads)
    if extra_env:
        env.update(extra_env)
    cmd = (exe or CCX).split() + ["-i", job]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True,
                       timeout=timeout)
    dt = time.perf_counter() - t0
    out = p.stdout + p.stderr
    with open(os.path.join(workdir, job + ".log"), "w") as fh:
        fh.write(out)
    if p.returncode != 0 or "*ERROR" in out:
        raise RuntimeError(f"ccx failed (rc={p.returncode}):\n" + out[-3000:])
    return dt, out


# ---------------------------------------------------------------- FRD reader
FRD_ETYPE = {1: "he8", 2: "pe6", 3: "te4", 4: "he20", 5: "pe15", 6: "te10",
             7: "tr3", 8: "tr6", 9: "qu4", 10: "qu8", 11: "be2", 12: "be3"}
FRD_NNODES = {1: 8, 2: 6, 3: 4, 4: 20, 5: 15, 6: 10, 7: 3, 8: 6, 9: 4, 10: 8, 11: 2, 12: 3}


def _floats_fixed(s, width=12):
    s = s.rstrip("\n")
    return [float(s[i:i + width]) for i in range(0, len(s), width) if s[i:i + width].strip()]


def read_frd(path):
    """Minimal ASCII .frd reader.

    Returns dict(nodes={id: xyz}, elements={id: (frd_type, [node ids])},
                 results=[dict(name, step, value(=freq/time), comps, data{node: array})])
    """
    nodes, elems, results = {}, {}, []
    with open(path, errors="replace") as fh:
        lines = fh.readlines()
    i, n = 0, len(lines)
    cur_step_value, cur_step = None, None
    while i < n:
        L = lines[i]
        key = L[:6].strip()
        if L.startswith("    2C"):            # node block
            i += 1
            while not lines[i].startswith(" -3"):
                s = lines[i]
                nid = int(s[3:13])
                xyz = _floats_fixed(s[13:])
                nodes[nid] = np.array(xyz[:3])
                i += 1
        elif L.startswith("    3C"):          # element block
            i += 1
            cur = None
            while not lines[i].startswith(" -3"):
                s = lines[i]
                if s.startswith(" -1"):
                    parts = s.split()
                    cur = int(parts[1]); et = int(parts[2])
                    elems[cur] = (et, [])
                elif s.startswith(" -2"):
                    elems[cur][1].extend(int(v) for v in s.split()[1:])
                i += 1
        elif L.startswith("  100C"):          # result block header
            # e.g. "  100CL  101 1.000000000           1  ..." ; value in cols 12-24
            try:
                cur_step_value = float(L[12:24])
            except ValueError:
                cur_step_value = None
            parts = L.split()
            i += 1
            h = lines[i]                        # " -4  DISP        4    1"
            name = h[5:13].strip()
            ncomp = int(h[13:18])
            comps = []
            i += 1
            while lines[i].startswith(" -5"):
                comps.append(lines[i][5:13].strip())
                i += 1
            data = {}
            last = None
            while not lines[i].startswith(" -3"):
                s = lines[i]
                if s.startswith(" -1"):
                    last = int(s[3:13])
                    data[last] = _floats_fixed(s[13:])
                elif s.startswith(" -2"):
                    data[last].extend(_floats_fixed(s[13:]))
                i += 1
            results.append(dict(name=name, value=cur_step_value, comps=comps,
                                data={k: np.array(v) for k, v in data.items()},
                                header=L.rstrip()))
        i += 1
    return dict(nodes=nodes, elements=elems, results=results)


def frd_field(frd, name, index=0):
    """Return (node_ids, array) for the index-th result block with given name."""
    blocks = [r for r in frd["results"] if r["name"] == name]
    b = blocks[index]
    ids = np.array(sorted(b["data"]))
    arr = np.array([b["data"][k] for k in ids])
    return ids, arr, b


def von_mises(s):
    sxx, syy, szz, sxy, syz, szx = s.T[:6]
    return np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                   + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))


def read_dat_eigen(path):
    """Parse buckling factors or eigenfrequencies from a ccx .dat file."""
    txt = open(path, errors="replace").read()
    out = {}
    m = re.search(r"B U C K L I N G   F A C T O R   O U T P U T(.*?)(\n\s*\n\s*\n|\Z)", txt, re.S)
    if m:
        vals = []
        for line in m.group(1).splitlines():
            p = line.split()
            if len(p) == 2 and p[0].isdigit():
                vals.append(float(p[1]))
        out["buckle"] = vals
    m = re.search(r"E I G E N V A L U E   O U T P U T(.*?)P A R T I C I P", txt, re.S)
    if m:
        freqs = []
        for line in m.group(1).splitlines():
            p = line.split()
            if len(p) == 5 and p[0].isdigit():
                freqs.append(float(p[3]))   # CYCLES/TIME column
        out["freq_hz"] = freqs
    return out


def frd_to_vtu(frd, path, step_filter=None):
    """Convert parsed frd (3D/2D elements) to a VTU with all point results (pyvista)."""
    import pyvista as pv
    vtk_type = {4: pv.CellType.QUADRATIC_HEXAHEDRON, 6: pv.CellType.QUADRATIC_TETRA,
                1: pv.CellType.HEXAHEDRON, 3: pv.CellType.TETRA,
                10: pv.CellType.QUADRATIC_QUAD, 8: pv.CellType.QUADRATIC_TRIANGLE,
                9: pv.CellType.QUAD, 7: pv.CellType.TRIANGLE}
    # frd he20 node order is [0..11, 16..19, 12..15] relative to VTK_QUADRATIC_HEXAHEDRON
    # (same permutation as used by ccx2paraview); te10 is identical to VTK_QUADRATIC_TETRA;
    # pe15 is written as a linear VTK_WEDGE with reversed orientation (as ccx2paraview does).
    vtk_type[5] = pv.CellType.WEDGE; vtk_type[2] = pv.CellType.WEDGE
    perm = {4: list(range(12)) + list(range(16, 20)) + list(range(12, 16)),
            6: list(range(10)), 5: [0, 2, 1, 3, 5, 4], 2: [0, 2, 1, 3, 5, 4]}
    nid = np.array(sorted(frd["nodes"]))
    idx = {k: i for i, k in enumerate(nid)}
    pts = np.array([frd["nodes"][k] for k in nid])
    cells, types = [], []
    for eid, (et, conn) in sorted(frd["elements"].items()):
        if et not in vtk_type:
            continue
        c = [idx[v] for v in conn[:FRD_NNODES[et]]]
        if et in (5, 2):
            c = c[:6]
        if et in perm:
            c = [c[j] for j in perm[et]]
        cells += [len(c)] + c
        types.append(vtk_type[et])
    grid = pv.UnstructuredGrid(np.array(cells), np.array(types, dtype=np.uint8), pts)
    counts = {}
    for r in frd["results"]:
        nm = r["name"]
        k = counts.get(nm, 0); counts[nm] = k + 1
        ncomp = max(len(v) for v in r["data"].values())
        arr = np.zeros((len(nid), ncomp))
        for node, v in r["data"].items():
            if node in idx:
                arr[idx[node], :len(v)] = v
        grid.point_data[f"{nm}_{k}"] = arr
        if nm == "STRESS":
            grid.point_data[f"VONMISES_{k}"] = von_mises(arr)
    grid.save(path)
    return grid
