"""Element validity/quality check (VTK scaled Jacobian). Detects inverted cells as the minority sign
(each mesher may use the opposite node-ordering convention to VTK, so a uniform sign flip is fixed first)."""
import sys, numpy as np, pyvista as pv, meshio
f = sys.argv[1]
g = pv.from_meshio(meshio.read(f)) if f.endswith('.su2') else pv.read(f)
perm = {pv.CellType.TETRA: [0, 2, 1, 3], pv.CellType.WEDGE: [0, 2, 1, 3, 5, 4]}
for ct, name in [(pv.CellType.TETRA, 'tet'), (pv.CellType.WEDGE, 'prism')]:
    idx = np.where(g.celltypes == ct)[0]
    if len(idx) == 0:
        continue
    sub = g.extract_cells(idx)
    q = sub.cell_quality('scaled_jacobian')['scaled_jacobian']
    if np.median(q) < 0:   # opposite ordering convention -> permute and recompute
        conn = sub.cells.reshape(-1, len(perm[ct]) + 1)[:, 1:][:, perm[ct]]
        sub = pv.UnstructuredGrid(np.hstack([np.full((len(conn), 1), conn.shape[1]), conn]).ravel(),
                                  np.full(len(conn), ct, np.uint8), sub.points)
        q = sub.cell_quality('scaled_jacobian')['scaled_jacobian']
    print(f"{f} {name}: n={sub.n_cells} scaledJac min={q.min():.4f} p1={np.percentile(q,1):.4f} "
          f"median={np.median(q):.4f} inverted(SJ<=0)={(q<=0).sum()}")
