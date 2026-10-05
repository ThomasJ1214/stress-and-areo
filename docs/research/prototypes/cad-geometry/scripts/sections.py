"""Cross-section (station) properties along the rocket axis (+X).

For every station x we want, for BOTH aero and structures:
  A_enc(x)  : area enclosed by the outer contour(s)   -> aero (slender-body dA/dx, wave-drag area ruling, r_eq)
  A_mat(x)  : material area (outer minus holes)       -> axial stress  sigma = N/A_mat
  Iyy, Izz  : second moments of the material section about the section centroid -> bending stress
  r_max(x)  : max radial extent                       -> envelope / OpenRocket-style radius
"""
import math
import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union


# ------------------------------------------------------------------ polygon helpers
def ring_moments(coords):
    """Signed area & second moments (about origin) of a closed ring (Green's theorem, exact for polygons)."""
    P = np.asarray(coords)[:-1] if np.allclose(coords[0], coords[-1]) else np.asarray(coords)
    y, z = P[:, 0], P[:, 1]
    yn, zn = np.roll(y, -1), np.roll(z, -1)
    cr = y * zn - yn * z
    A = cr.sum() / 2
    Sy = ((y + yn) * cr).sum() / 6          # int y dA
    Sz = ((z + zn) * cr).sum() / 6          # int z dA
    Iyy0 = ((z * z + z * zn + zn * zn) * cr).sum() / 12   # int z^2 dA (bending about y)
    Izz0 = ((y * y + y * yn + yn * yn) * cr).sum() / 12   # int y^2 dA (bending about z)
    return A, Sy, Sz, Iyy0, Izz0


def polygon_section_props(geom):
    """geom: shapely (Multi)Polygon in the section plane (coords = (y, z))."""
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else ([geom] if not geom.is_empty else [])
    A = Sy = Sz = Iyy0 = Izz0 = 0.0
    for p in polys:
        for ring, sgn in [(p.exterior, 1.0)] + [(h, -1.0) for h in p.interiors]:
            a, sy, sz, iy, iz = ring_moments(np.asarray(ring.coords))
            s = sgn * (1.0 if a > 0 else -1.0)
            A += s * a; Sy += s * sy; Sz += s * sz; Iyy0 += s * iy; Izz0 += s * iz
    if A <= 0:
        return dict(A_mat=0.0, yc=0.0, zc=0.0, Iyy=0.0, Izz=0.0)
    yc, zc = Sy / A, Sz / A
    return dict(A_mat=A, yc=yc, zc=zc, Iyy=Iyy0 - A * zc * zc, Izz=Izz0 - A * yc * yc)


def enclosed_area(geom):
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else ([geom] if not geom.is_empty else [])
    if not polys:
        return 0.0
    return unary_union([Polygon(p.exterior) for p in polys]).area


# ------------------------------------------------------------------ trimesh-based slicing
def section_geoms(mesh, xs):
    """Shapely (Multi)Polygon in (y,z) world coords of mesh ∩ {x = xs[i]} for each station."""
    secs = mesh.section_multiplane(plane_origin=[0, 0, 0], plane_normal=[1, 0, 0], heights=list(xs))
    out = []
    for s in secs:
        if s is None:
            out.append(Polygon()); continue
        T = s.metadata.get("to_3D", np.eye(4))
        def to_yz(c):
            c = np.asarray(c)
            w = (T[:3, :2] @ c.T).T + T[:3, 3]
            return w[:, 1:3]
        try:
            polys = s.polygons_full
            geoms = [Polygon(to_yz(p.exterior.coords), [to_yz(h.coords) for h in p.interiors]) for p in polys]
            g = unary_union(geoms) if geoms else Polygon()
        except ValueError:
            # fallback: even-odd combination of closed loops
            g = Polygon()
            for ring in s.discrete:
                g = g.symmetric_difference(Polygon(to_yz(ring)).buffer(0))
        out.append(g)
    return out


def props_from_geom(x, g):
    pr = polygon_section_props(g)
    gg = [p for p in (g.geoms if isinstance(g, MultiPolygon) else [g]) if not p.is_empty]
    rmax = max((np.hypot(*np.asarray(p.exterior.coords).T).max() for p in gg), default=0.0)
    return dict(x=x, A_enc=enclosed_area(g), A_mat=pr["A_mat"], Iyy=pr["Iyy"], Izz=pr["Izz"], r_max=rmax)


def slice_trimesh(mesh, xs):
    """Slice a single watertight mesh at planes x = xs."""
    return [props_from_geom(x, g) for x, g in zip(xs, section_geoms(mesh, xs))]


def slice_parts(meshes, xs):
    """Slice several part meshes independently and union the sections in 2D (robust for touching parts)."""
    per = [section_geoms(m, xs) for m in meshes]
    return [props_from_geom(x, unary_union([p[i] for p in per])) for i, x in enumerate(xs)]


# ------------------------------------------------------------------ manifold3d slicing (z-axis slices)
def slice_manifold(man_x_to_z, xs):
    """man_x_to_z: manifold3d.Manifold already rotated so the rocket axis is +Z."""
    out = []
    for x in xs:
        cs = man_x_to_z.slice(float(x))
        polys = cs.to_polygons()
        # to_polygons returns list of rings (CCW outer, CW holes); build shapely via even-odd union
        rings = [np.asarray(r) for r in polys]
        A_mat = sum(ring_moments(np.vstack([r, r[:1]]))[0] for r in rings)
        outer = [Polygon(r) for r in rings if ring_moments(np.vstack([r, r[:1]]))[0] > 0]
        A_enc = unary_union(outer).area if outer else 0.0
        out.append(dict(x=x, A_mat=A_mat, A_enc=A_enc, A_cs=cs.area()))
    return out


# ------------------------------------------------------------------ exact B-rep slicing (OCP)
def slice_brep(shape, xs, big=1e4):
    """Exact planar sections of an OCC solid/compound: cut away x > xs and measure the planar cap faces."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from occ_util import iter_type, solids, TO_FACE
    from OCP.TopAbs import TopAbs_FACE
    out = []
    sols = solids(shape)
    for x in xs:
        A_mat = 0.0; Iyy = Izz = 0.0; Sy = Sz = 0.0; caps = []
        for so in sols:
            box = BRepPrimAPI_MakeBox(gp_Pnt(x, -big, -big), gp_Pnt(x + 2 * big, big, big)).Shape()
            res = BRepAlgoAPI_Cut(so, box).Shape()
            for f in iter_type(res, TopAbs_FACE):
                fc = TO_FACE(f)
                ad = BRepAdaptor_Surface(fc)
                if ad.GetType() != GeomAbs_Plane:
                    continue
                pl = ad.Plane()
                if abs(abs(pl.Axis().Direction().X()) - 1) > 1e-9 or abs(pl.Location().X() - x) > 1e-7:
                    continue
                p = GProp_GProps(); BRepGProp.SurfaceProperties_s(fc, p)
                a = p.Mass(); c = p.CentreOfMass()
                # second moments about the global axis (y=z=0) : I_cg + A d^2
                M = p.MatrixOfInertia()   # about centroid; for a plane x=const: M(2,2)=int(z^2+x^2..)
                A_mat += a; Sy += a * c.Y(); Sz += a * c.Z()
                # For a planar face in plane x=const: int (dz)^2 dA = (M11 + M33 - M22)/2 etc. Use direct:
                Izz_c = (M.Value(1, 1) + M.Value(3, 3) - M.Value(2, 2)) / 2   # int dy^2 dA
                Iyy_c = (M.Value(1, 1) + M.Value(2, 2) - M.Value(3, 3)) / 2   # int dz^2 dA
                Izz += Izz_c + a * c.Y() ** 2
                Iyy += Iyy_c + a * c.Z() ** 2
                caps.append(fc)
        # enclosed area: union of outer wires of cap faces (as shapely polygons via sampled wires)
        out.append(dict(x=x, A_mat=A_mat, yc=Sy / A_mat if A_mat else 0, zc=Sz / A_mat if A_mat else 0,
                        Iyy=Iyy - (Sz ** 2 / A_mat if A_mat else 0), Izz=Izz - (Sy ** 2 / A_mat if A_mat else 0),
                        ncaps=len(caps)))
    return out
