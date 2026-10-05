"""Thin OCP (OpenCASCADE 8.0 via cadquery-ocp) helpers used by the tests."""
import math
import time
import numpy as np

from OCP.gp import gp_Pnt, gp_Ax1, gp_Ax2, gp_Dir, gp_Vec, gp_Trsf, gp_Pln
from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform,
                                BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid,
                                BRepBuilderAPI_Sewing)
from OCP.BRepPrimAPI import (BRepPrimAPI_MakeRevol, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeCylinder,
                             BRepPrimAPI_MakeBox)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
# OCP 8 (OCCT 8.0) exposes TopoDS casts as module functions (TopoDS.Solid); OCP 7.x used TopoDS.Solid_s
_cast = lambda n: getattr(TopoDS, n + '_s', None) or getattr(TopoDS, n)
TO_SOLID, TO_FACE, TO_SHELL = _cast('Solid'), _cast('Face'), _cast('Shell')
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_SHELL, TopAbs_REVERSED
from OCP.TopLoc import TopLoc_Location
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
from OCP.IGESControl import IGESControl_Writer, IGESControl_Reader
from OCP.Interface import Interface_Static
from OCP.IFSelect import IFSelect_RetDone


# ------------------------------------------------------------------ construction
def revolve_profile_xy(edges):
    """edges: list of TopoDS_Edge forming closed profile in XY-plane (y>=0); revolve about X."""
    mw = BRepBuilderAPI_MakeWire()
    for e in edges:
        mw.Add(e)
    face = BRepBuilderAPI_MakeFace(mw.Wire(), True).Face()
    ax = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))
    return BRepPrimAPI_MakeRevol(face, ax, 2 * math.pi).Shape()


def seg(p, q):
    return BRepBuilderAPI_MakeEdge(GC_MakeSegment(gp_Pnt(*p), gp_Pnt(*q)).Value()).Edge()


def arc3(p, m, q):
    return BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(gp_Pnt(*p), gp_Pnt(*m), gp_Pnt(*q)).Value()).Edge()


def make_ogive_solid(L, R):
    rho = (R * R + L * L) / (2 * R)
    y = lambda x: math.sqrt(rho * rho - (L - x) ** 2) + R - rho
    edges = [arc3((0, 0, 0), (L / 2, y(L / 2), 0), (L, R, 0)), seg((L, R, 0), (L, 0, 0)), seg((L, 0, 0), (0, 0, 0))]
    return revolve_profile_xy(edges)


def make_ogive_hollow(L, R, t, x0):
    """Hollow ogive built as outer solid minus inner solid (round-trips through STEP correctly)."""
    rho = (R * R + L * L) / (2 * R)
    y = lambda x: math.sqrt(rho * rho - (L - x) ** 2) + R - rho
    xm = (x0 + L) / 2
    outer = make_ogive_solid(L, R)
    edges = [arc3((x0, 0, 0), (xm, y(xm) - t, 0), (L, R - t, 0)), seg((L, R - t, 0), (L + 1, R - t, 0)),
             seg((L + 1, R - t, 0), (L + 1, 0, 0)), seg((L + 1, 0, 0), (x0, 0, 0))]
    inner = revolve_profile_xy(edges)
    return BRepAlgoAPI_Cut(outer, inner).Shape()


def make_ogive_hollow_revolve(L, R, t, x0):
    """Direct single-profile revolve. VALID in memory, but OCCT 8.0.1 STEP export of it reads back
    INVALID (inner face area 0, volume 7x too large). IGES export of the same shape is fine."""
    rho = (R * R + L * L) / (2 * R)
    y = lambda x: math.sqrt(rho * rho - (L - x) ** 2) + R - rho
    xm = (x0 + L) / 2
    edges = [arc3((0, 0, 0), (L / 2, y(L / 2), 0), (L, R, 0)),
             seg((L, R, 0), (L, R - t, 0)),
             arc3((L, R - t, 0), (xm, y(xm) - t, 0), (x0, 0, 0)),
             seg((x0, 0, 0), (0, 0, 0))]
    return revolve_profile_xy(edges)


def make_fin(pts2d, t):
    poly = BRepBuilderAPI_MakePolygon()
    for (x, y) in pts2d:
        poly.Add(gp_Pnt(x, y, -t / 2))
    poly.Close()
    face = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, t)).Shape()


def make_cyl_x(R, x0, x1, yc=0.0, zc=0.0):
    ax = gp_Ax2(gp_Pnt(x0, yc, zc), gp_Dir(1, 0, 0))
    return BRepPrimAPI_MakeCylinder(ax, R, x1 - x0).Shape()


def make_hcyl_x(Ro, Ri, x0, x1, yc=0.0, zc=0.0):
    o = make_cyl_x(Ro, x0, x1, yc, zc)
    if Ri <= 0:
        return o
    i = make_cyl_x(Ri, x0 - 1.0, x1 + 1.0, yc, zc)
    return BRepAlgoAPI_Cut(o, i).Shape()


def make_box(x0, x1, y0, y1, z0, z1):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()


def make_saddle(x0, x1, w, Ro, zt):
    zb = math.sqrt(Ro * Ro - (w / 2) ** 2) - 0.5
    b = make_box(x0, x1, -w / 2, w / 2, zb, zt)
    c = make_cyl_x(Ro, x0 - 1, x1 + 1)
    return BRepAlgoAPI_Cut(b, c).Shape()


def translated(shape, dx, dy, dz):
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def compound(shapes):
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


# ------------------------------------------------------------------ topology iteration
def iter_type(shape, typ):
    exp = TopExp_Explorer(shape, typ)
    while exp.More():
        yield exp.Current()
        exp.Next()


def solids(shape):
    return [TO_SOLID(s) for s in iter_type(shape, TopAbs_SOLID)]


# ------------------------------------------------------------------ mass properties
def gp_mat_to_np(m):
    return np.array([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])


def volume_props(shape, gk_tol=None):
    """Returns V, c, I_cg (OCCT 'matrix of inertia' at centre of mass, unit density)."""
    p = GProp_GProps()
    if gk_tol is None:
        BRepGProp.VolumeProperties_s(shape, p)
    else:
        BRepGProp.VolumePropertiesGK_s(shape, p, gk_tol, False, False, True, True)  # OnlyClosed, IsUseSpan, CGFlag, IFlag
    c = p.CentreOfMass()
    return p.Mass(), np.array([c.X(), c.Y(), c.Z()]), gp_mat_to_np(p.MatrixOfInertia())


def surface_area(shape):
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, p)
    return p.Mass()


# ------------------------------------------------------------------ tessellation
def tessellate(shape, lin_defl=0.1, ang_defl=0.3, relative=False, parallel=True):
    """Mesh B-rep and return (V, F, face_id) arrays with consistent outward winding.
    Vertices along shared edges are duplicated per face; weld afterwards (trimesh.merge_vertices)."""
    BRepMesh_IncrementalMesh(shape, lin_defl, relative, ang_defl, parallel)
    verts, faces, fids = [], [], []
    off = 0
    for fi, f in enumerate(iter_type(shape, TopAbs_FACE)):
        face = TO_FACE(f)
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        n = tri.NbNodes()
        pts = np.empty((n, 3))
        for i in range(1, n + 1):
            p = tri.Node(i).Transformed(trsf)
            pts[i - 1] = (p.X(), p.Y(), p.Z())
        m = tri.NbTriangles()
        tris = np.empty((m, 3), dtype=np.int64)
        for i in range(1, m + 1):
            a, b, c = tri.Triangle(i).Get()
            tris[i - 1] = (a - 1, b - 1, c - 1)
        if face.Orientation() == TopAbs_REVERSED:
            tris = tris[:, ::-1]
        verts.append(pts)
        faces.append(tris + off)
        fids.append(np.full(m, fi))
        off += n
    return np.vstack(verts), np.vstack(faces), np.concatenate(fids)


# ------------------------------------------------------------------ IO
def write_step(shape, path, unit="MM", schema="AP214IS"):
    Interface_Static.SetCVal_s("write.step.unit", unit)
    Interface_Static.SetCVal_s("write.step.schema", schema)
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    assert w.Write(path) == IFSelect_RetDone


def read_step(path):
    r = STEPControl_Reader()
    assert r.ReadFile(path) == IFSelect_RetDone
    r.TransferRoots()
    return r.OneShape()


def write_iges(shape, path):
    w = IGESControl_Writer("MM", 1)  # 1 = BRep mode (faces), 0 = faces as trimmed surfaces
    w.AddShape(shape)
    w.ComputeModel()
    assert w.Write(path)


def read_iges(path):
    r = IGESControl_Reader()
    assert r.ReadFile(path) == IFSelect_RetDone
    r.TransferRoots()
    return r.OneShape()


class Timer:
    def __init__(self):
        self.t = time.perf_counter()

    def lap(self):
        t = time.perf_counter()
        d = t - self.t
        self.t = t
        return d
