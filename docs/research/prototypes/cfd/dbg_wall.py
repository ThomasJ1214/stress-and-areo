import gmsh, math, numpy as np, sys
sys.argv=['x','o.su2','3.0']
src=open('bl_mesh.py').read()
src=src[:src.index('gmsh.model.remove()')]
exec(src)
from collections import Counter
e=Counter()
for t in allc:
    for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])):
        e[(min(a,b),max(a,b))]+=1
print('edge valence histogram', Counter(e.values()))
P=X[allc]; A=0.5*np.linalg.norm(np.cross(P[:,1]-P[:,0],P[:,2]-P[:,0]),axis=1)
print('degenerate tris (area<1e-12):', (A<1e-12).sum(), 'min area', A.min())
s=set(); dup=0
for t in allc:
    k=tuple(sorted(t)); dup+= k in s; s.add(k)
print('duplicate tris', dup)
bad=[k for k,v in e.items() if v!=2]
print('nonmanifold edge sample coords', [X[list(k)].round(4).tolist() for k in bad[:4]])
