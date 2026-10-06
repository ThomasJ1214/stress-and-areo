import gmsh, math, numpy as np, sys
from collections import Counter
sys.argv=['x','o.su2','3.0']
src=open('bl_mesh.py').read()
src=src[:src.index('gmsh.model.remove()')]
exec(src)
e=Counter()
for t in allc:
    for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])): e[(min(a,b),max(a,b))]+=1
print('edge valence', Counter(e.values()))
# directed-edge consistency
de=Counter()
for t in allc:
    for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])): de[(a,b)]+=1
print('inconsistent directed edges (same direction used twice):', sum(1 for v in de.values() if v>1))
P=X[allc]; print('raw vol', np.einsum("ij,ij->i", P[:,0], np.cross(P[:,1],P[:,2])).sum()/6)
import pyvista as pv
faces=np.hstack([np.full((len(allc),1),3),allc]).ravel()
pd=pv.PolyData(X,faces).clean()
print('pv n_open_edges', pd.n_open_edges, 'is_manifold', pd.is_manifold, 'volume', pd.volume)
pdn=pd.compute_normals(cell_normals=True, point_normals=False, consistent_normals=True, auto_orient_normals=True, split_vertices=False)
c2=pdn.faces.reshape(-1,4)[:,1:]; P=pdn.points[c2]
print('vtk-oriented vol', np.einsum("ij,ij->i", P[:,0], np.cross(P[:,1],P[:,2])).sum()/6, 'npts', pdn.n_points, 'vs X', len(X))
bad=[k for k,v in e.items() if v==4]
for k in bad: print('nonmanifold edge', X[list(k)].round(5).tolist())
tri_with=[i for i,t in enumerate(allc) if any((min(a,b),max(a,b)) in set(bad) for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])))]
print('n tris touching', len(tri_with)); print(sorted(set(tuple(sorted(allc[i])) for i in tri_with))[:10])
