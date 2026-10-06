import gmsh, time, sys
variant=sys.argv[1]
gmsh.initialize(); gmsh.option.setNumber("General.Terminal",0)
occ=gmsh.model.occ
cone=occ.addCone(0,0,0,0.3,0,0,0,0.05); cyl=occ.addCylinder(0.3,0,0,0.7,0,0,0.05)
r,_=occ.fuse([(3,cone)],[(3,cyl)])
dom=occ.addCylinder(-6,0,0,18,0,0,6)
fl,_=occ.cut([(3,dom)],r); occ.synchronize()
walls=[t for (d,t) in gmsh.model.getBoundary(fl,oriented=False) if gmsh.model.getBoundingBox(2,t)[4]<0.1]
f=gmsh.model.mesh.field
d=f.add("Distance"); f.setNumbers(d,"SurfacesList",walls); f.setNumber(d,"Sampling",20)
if variant=="matheval":
    m=f.add("MathEval"); f.setString(m,"F",f"0.012 + 0.12*F{d}")
    c=f.add("MathEval"); f.setString(c,"F",f"Min(F{m}, 0.6)")
    bg=c
elif variant=="matheval_nomin":
    m=f.add("MathEval"); f.setString(m,"F",f"0.012 + 0.12*F{d}")
    bg=m
elif variant=="threshold":
    m=f.add("Threshold"); f.setNumber(m,"InField",d); f.setNumber(m,"SizeMin",0.012); f.setNumber(m,"SizeMax",0.6); f.setNumber(m,"DistMin",0); f.setNumber(m,"DistMax",(0.6-0.012)/0.12)
    bg=m
f.setAsBackgroundMesh(bg)
for k,v in {"Mesh.MeshSizeExtendFromBoundary":0,"Mesh.MeshSizeFromPoints":0,"Mesh.MeshSizeFromCurvature":0}.items(): gmsh.option.setNumber(k,v)
t=time.time(); gmsh.model.mesh.generate(1); print(variant,"1D",time.time()-t, flush=True)
t=time.time(); gmsh.model.mesh.generate(2); print(variant,"2D",time.time()-t, flush=True)
gmsh.finalize()
