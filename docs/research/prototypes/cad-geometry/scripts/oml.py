"""Outer-mold-line (wetted outer skin) extraction from a detailed multi-part assembly.

B-rep path (exact, OCP):
  1. (optional) add thin 'interface plugs' at the component's forward/aft interface planes so that a
     cavity that is open at an end (open body tube) becomes closed (adjacent rocket components plug it).
  2. General-fuse all solids (BRepAlgoAPI_Fuse, arguments+tools) -> union, then UnifySameDomain.
  3. For every resulting solid take its OUTER shell (BRepClass3d::OuterShell) -> solid without voids.
  4. Discard solids that lie inside another outer-shell solid (floating internal parts: sled, battery ...).
  5. Union of remaining outer-shell solids = OML solid; its faces = wetted surface (minus interface caps).
Mesh path (manifold3d / trimesh):
  1. Manifold union of all (welded, watertight) part meshes.
  2. Split result into connected closed surfaces; signed volume < 0 -> inner void boundary (drop);
     positive surfaces contained in another positive surface -> internal part (drop).
"""
import numpy as np
import trimesh
import manifold3d as mf
from occ_util import *
from OCP.BRepClass3d import BRepClass3d, BRepClass3d_SolidClassifier
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_IN, TopAbs_ON
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
try:
    from OCP.TopTools import TopTools_ListOfShape
except ImportError:
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape


def fuse_all(shapes, fuzzy=0.0):
    if len(shapes) == 1:
        return shapes[0]
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(shapes[0])
    for s in shapes[1:]:
        tools.Append(s)
    f = BRepAlgoAPI_Fuse()
    f.SetArguments(args); f.SetTools(tools)
    f.SetRunParallel(False)
    if fuzzy:
        f.SetFuzzyValue(fuzzy)
    f.Build()
    assert f.IsDone()
    u = ShapeUpgrade_UnifySameDomain(f.Shape(), True, True, False)
    u.Build()
    return u.Shape()


def outer_shell_solid(solid):
    sh = BRepClass3d.OuterShell_s(solid)
    return BRepBuilderAPI_MakeSolid(sh).Solid()


def point_inside(solid, pnt, tol=1e-6):
    c = BRepClass3d_SolidClassifier(solid, gp_Pnt(*pnt), tol)
    return c.State() in (TopAbs_IN,)


def any_vertex(solid):
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    cast = getattr(TopoDS, "Vertex_s", None) or getattr(TopoDS, "Vertex")
    for v in iter_type(solid, TopAbs_VERTEX):
        p = BRep_Tool.Pnt_s(cast(v))
        return (p.X(), p.Y(), p.Z())


def interior_point(solid):
    """A point strictly inside 'solid' (centroid if inside, else nudged vertex)."""
    V, c, _ = volume_props(solid)
    if point_inside(solid, c):
        return c
    # fallback: sample bounding box
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box(); BRepBndLib.Add_s(solid, b)
    lo, hi = b.CornerMin(), b.CornerMax()   # OCP 8: Bnd_Box.Get() returns an unbound struct
    x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
    rng = np.random.default_rng(0)
    for _ in range(2000):
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(z0, z1))
        if point_inside(solid, p):
            return p
    return c


def oml_brep(part_shapes, plugs=()):
    """part_shapes: list of located solids (mm). plugs: list of extra solids (interface caps)."""
    fused = fuse_all(list(part_shapes) + list(plugs))
    sols = solids(fused)
    outers = [outer_shell_solid(s) for s in sols]
    keep = []
    for i, s in enumerate(outers):
        p = interior_point(s)
        inside_other = any(point_inside(outers[j], p) for j in range(len(outers)) if j != i
                           and volume_props(outers[j])[0] > volume_props(s)[0])
        if not inside_other:
            keep.append(s)
    oml = keep[0] if len(keep) == 1 else fuse_all(keep)
    return oml, dict(n_fused_solids=len(sols), n_kept=len(keep))


# ------------------------------------------------------------------ mesh path
def to_manifold(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))


def from_manifold(man):
    mm = man.to_mesh()
    return trimesh.Trimesh(np.asarray(mm.vert_properties)[:, :3], np.asarray(mm.tri_verts), process=False)


def oml_mesh(part_meshes, plugs=()):
    mans = [to_manifold(m) for m in list(part_meshes) + list(plugs)]
    u = mf.Manifold.batch_boolean(mans, mf.OpType.Add)
    m = from_manifold(u)
    m.merge_vertices()
    bodies = m.split(only_watertight=False)
    vtot = sum(abs(b.volume) for b in bodies)
    tiny = [b for b in bodies if abs(b.volume) < 1e-6 * vtot]        # sliver artefacts of coincident faces
    bodies = [b for b in bodies if abs(b.volume) >= 1e-6 * vtot]
    pos = [b for b in bodies if b.volume > 0]
    neg = [b for b in bodies if b.volume <= 0]
    keep = []
    for i, b in enumerate(pos):
        p = b.vertices[0:1]
        inside = any(o.volume > b.volume and o.contains(p)[0] for j, o in enumerate(pos) if j != i)
        if not inside:
            keep.append(b)
    oml = trimesh.util.concatenate(keep)
    return oml, dict(n_bodies=len(bodies), n_slivers_dropped=len(tiny), n_void_surfaces=len(neg), n_kept=len(keep), union_status=str(u.status()))
