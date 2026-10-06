import gmsh, math
R, LN, L, CR, SPAN, T = 0.05, 0.30, 1.0, 0.12, 0.08, 0.004
R_TIP=0.00025; X_TIP=R_TIP*LN/R
gmsh.initialize(); gmsh.option.setNumber("General.Terminal",0)
occ=gmsh.model.occ
parts=[(3,occ.addCone(X_TIP,0,0,LN-X_TIP,0,0,R_TIP,R)),(3,occ.addCylinder(LN,0,0,L-LN,0,0,R))]
r_in=0.9*R; slope=(0.94-0.88)/SPAN
pts=[(0.88-slope*(R-r_in),r_in),(L,r_in),(L,R+SPAN),(0.94,R+SPAN)]
for ang in [45,135,225,315]:
    p=[occ.addPoint(x,-T/2,r) for (x,r) in pts]
    lt=[occ.addLine(p[i],p[(i+1)%4]) for i in range(4)]
    s=occ.addPlaneSurface([occ.addCurveLoop(lt)])
    v=[e for e in occ.extrude([(2,s)],0,T,0) if e[0]==3]
    occ.rotate(v,0,0,0,1,0,0,math.radians(ang-90)); parts+=v
occ.fuse([parts[0]],parts[1:]); occ.synchronize()
gmsh.write("meshes/rocket.step"); gmsh.write("meshes/rocket.brep")
gmsh.finalize(); print("ok")
