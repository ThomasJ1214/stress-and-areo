import gmsh, numpy as np
from collections import Counter
for alg in [1,2,5,6,8]:
  for h in [0.018, 0.012, 0.0084, 0.006, 0.004]:
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal",0)
    occ=gmsh.model.occ
    occ.addCone(0,0,0,0.3,0,0,0,0.05); occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax",h); gmsh.option.setNumber("Mesh.MeshSizeMin",h/4)
    gmsh.option.setNumber("Mesh.Algorithm",alg)
    try:
        gmsh.model.mesh.generate(2)
        _,_,en=gmsh.model.mesh.getElements(2)
        T=np.concatenate([np.asarray(x) for x in en]).reshape(-1,3)
        e=Counter()
        for t in T:
            for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])): e[(min(a,b),max(a,b))]+=1
        dup=len(T)-len({tuple(sorted(t)) for t in T})
        print(f"alg={alg} h={h}: tris={len(T)} dup={dup} nonmanifold_edges={sum(1 for v in e.values() if v>2)}")
    except Exception as ex:
        print(f"alg={alg} h={h}: FAILED {ex}")
    gmsh.finalize()
