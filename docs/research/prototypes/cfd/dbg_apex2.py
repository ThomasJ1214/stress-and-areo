import gmsh, numpy as np, math
from collections import Counter
R,LN=0.05,0.30
th=math.atan(R/LN)
for rt in [0.00025, 0.0005]:
  for h in [0.012, 0.0084, 0.006, 0.004]:
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal",0)
    occ=gmsh.model.occ
    x0=rt/math.tan(th)
    c=occ.addCone(x0,0,0,LN-x0,0,0,rt,R); occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax",h); gmsh.option.setNumber("Mesh.MeshSizeMin",min(h, 4*rt))
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",0)
    gmsh.option.setNumber("Mesh.Algorithm",6)
    gmsh.model.mesh.generate(2)
    _,_,en=gmsh.model.mesh.getElements(2)
    T=np.concatenate([np.asarray(x) for x in en]).reshape(-1,3)
    e=Counter()
    for t in T:
        for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])): e[(min(a,b),max(a,b))]+=1
    dup=len(T)-len({tuple(sorted(t)) for t in T})
    print(f"r_tip={rt} h={h}: tris={len(T)} dup={dup} nonmanifold={sum(1 for v in e.values() if v>2)} open_edges={sum(1 for v in e.values() if v==1)}", flush=True)
    gmsh.finalize()
