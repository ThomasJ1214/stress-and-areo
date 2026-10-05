"""Analytic (exact / high-precision quadrature) mass properties of the test bodies.

Conventions
-----------
* Lengths in mm, rocket axis = +X, origin at forward end (nose tip) unless stated.
* "per unit density" quantities: V [mm^3], first moments [mm^4], inertia [mm^5].
* Inertia tensor I = [[Ixx, -Pxy, -Pxz], [-Pxy, Iyy, -Pyz], [-Pxz, -Pyz, Izz]]
  with Ixx = int(y^2+z^2) dV and Pxy = int(x*y) dV  (the "true" tensor, same as OCCT).
"""
import math
import numpy as np
from scipy.integrate import quad

Q = dict(epsabs=0.0, epsrel=1e-13, limit=500)


def _q(f, a, b):
    return quad(f, a, b, **Q)[0]


class MassProps:
    def __init__(self, V, c, I_cg):
        self.V = float(V)            # volume (or mass if density applied)
        self.c = np.asarray(c, float)
        self.I = np.asarray(I_cg, float)  # about CG, global axes

    def scaled(self, rho):
        return MassProps(self.V * rho, self.c, self.I * rho)

    def __repr__(self):
        return f"MassProps(V={self.V:.10g}, c={self.c}, Idiag={np.diag(self.I)})"


def shift_to_cg(V, c, I_origin):
    c = np.asarray(c, float)
    return I_origin - V * (np.dot(c, c) * np.eye(3) - np.outer(c, c))


def combine(parts):
    """parts: list of MassProps already multiplied by density (V=mass)."""
    M = sum(p.V for p in parts)
    c = sum(p.V * p.c for p in parts) / M
    I = np.zeros((3, 3))
    for p in parts:
        d = p.c - c
        I += p.I + p.V * (np.dot(d, d) * np.eye(3) - np.outer(d, d))
    return MassProps(M, c, I)


# ---------------------------------------------------------------- solids of revolution
def revolution(y, a, b, yi=None, x_shift=0.0):
    """Solid of revolution about X of region yi(x) <= r <= y(x), x in [a,b]."""
    yi = yi or (lambda x: 0.0)
    f2 = lambda x: y(x) ** 2 - yi(x) ** 2
    f4 = lambda x: y(x) ** 4 - yi(x) ** 4
    V = math.pi * _q(f2, a, b)
    Sx = math.pi * _q(lambda x: x * f2(x), a, b)
    xc = Sx / V
    Iax = 0.5 * math.pi * _q(f4, a, b)
    It_o = math.pi * _q(lambda x: x * x * f2(x) + 0.25 * f4(x), a, b)
    It = It_o - V * xc * xc
    return MassProps(V, [xc + x_shift, 0, 0], np.diag([Iax, It, It]))


def tangent_ogive(L, R):
    rho = (R * R + L * L) / (2 * R)
    return rho, (lambda x: math.sqrt(max(rho * rho - (L - x) ** 2, 0.0)) + R - rho)


def ogive_solid(L, R):
    _, y = tangent_ogive(L, R)
    return revolution(y, 0.0, L)


def ogive_hollow_vertical(L, R, t):
    """Outer tangent ogive, inner = outer shifted down by t (also a circular arc)."""
    rho, y = tangent_ogive(L, R)
    yi = lambda x: max(y(x) - t, 0.0)
    # find x0 where y(x0) = t for better quadrature split
    from scipy.optimize import brentq
    x0 = brentq(lambda x: y(x) - t, 1e-12, L)
    p1 = revolution(y, 0.0, x0)
    p2 = revolution(y, x0, L, yi)
    return combine([p1, p2]), x0


def ogive_section_area(L, R, x):
    _, y = tangent_ogive(L, R)
    return math.pi * y(x) ** 2


# ---------------------------------------------------------------- cylinders / boxes
def hollow_cyl_x(Ro, Ri, x0, x1, yc=0.0, zc=0.0):
    Lx = x1 - x0
    V = math.pi * (Ro ** 2 - Ri ** 2) * Lx
    Iax = V * (Ro ** 2 + Ri ** 2) / 2
    It = V * (3 * (Ro ** 2 + Ri ** 2) + Lx ** 2) / 12
    return MassProps(V, [(x0 + x1) / 2, yc, zc], np.diag([Iax, It, It]))


def box(x0, x1, y0, y1, z0, z1):
    a, b, c = x1 - x0, y1 - y0, z1 - z0
    V = a * b * c
    I = V / 12 * np.diag([b * b + c * c, a * a + c * c, a * a + b * b])
    return MassProps(V, [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], I)


# ---------------------------------------------------------------- planar polygon fin
def polygon_moments(P):
    P = np.asarray(P, float)
    x, y = P[:, 0], P[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cr = x * yn - xn * y
    A = cr.sum() / 2
    Cx = ((x + xn) * cr).sum() / (6 * A)
    Cy = ((y + yn) * cr).sum() / (6 * A)
    Iyy_a = ((x * x + x * xn + xn * xn) * cr).sum() / 12   # int x^2 dA
    Ixx_a = ((y * y + y * yn + yn * yn) * cr).sum() / 12   # int y^2 dA
    Pxy_a = ((x * yn + 2 * x * y + 2 * xn * yn + xn * y) * cr).sum() / 24  # int xy dA
    return A, Cx, Cy, Ixx_a, Iyy_a, Pxy_a


def fin_plate(P, t):
    """Polygon P in XY plane, extruded symmetric in z (-t/2..t/2)."""
    A, Cx, Cy, Ixx_a, Iyy_a, Pxy_a = polygon_moments(P)
    V = A * t
    Iz2 = A * t ** 3 / 12
    I_o = np.array([[t * Ixx_a + Iz2, -t * Pxy_a, 0],
                    [-t * Pxy_a, t * Iyy_a + Iz2, 0],
                    [0, 0, t * (Ixx_a + Iyy_a)]])
    c = [Cx, Cy, 0]
    return MassProps(V, c, shift_to_cg(V, c, I_o)), A


def trapezoid_fin_pts(cr, ct, s, m):
    return [(0, 0), (cr, 0), (m + ct, s), (m, s)]


# ---------------------------------------------------------------- saddle (shroud)
def saddle(x0, x1, w, Ro, zt):
    """{x0<x<x1, |y|<w/2, sqrt(Ro^2-y^2) < z < zt} (box minus cylinder radius Ro about X)."""
    Lx = x1 - x0
    g = lambda y: math.sqrt(Ro * Ro - y * y)
    h = w / 2
    A = _q(lambda y: zt - g(y), -h, h)
    V = Lx * A
    Sz = Lx * _q(lambda y: (zt ** 2 - g(y) ** 2) / 2, -h, h)
    xm = (x0 + x1) / 2
    c = np.array([xm, 0.0, Sz / V])
    Iy2 = Lx * _q(lambda y: y * y * (zt - g(y)), -h, h)
    Iz2 = Lx * _q(lambda y: (zt ** 3 - g(y) ** 3) / 3, -h, h)
    Ix2 = A * (x1 ** 3 - x0 ** 3) / 3
    Pxz = xm * Sz
    I_o = np.array([[Iy2 + Iz2, 0, -Pxz], [0, Ix2 + Iz2, 0], [-Pxz, 0, Ix2 + Iy2]])
    return MassProps(V, c, shift_to_cg(V, c, I_o))


# ---------------------------------------------------------------- test-case definitions (mm)
OGIVE = dict(L=240.0, R=40.0, t=2.0)
FIN = dict(cr=120.0, ct=60.0, s=80.0, m=40.0, t=3.175)
TUBE = dict(Ro=40.0, Ri=38.0, L=300.0)

# payload assembly: (name, kind, params, density kg/m^3)
PAYLOAD = [
    ("body_tube", "hcyl", dict(Ro=40.0, Ri=38.0, x0=0.0, x1=250.0), 1850.0),
    ("fwd_bulkhead", "hcyl", dict(Ro=38.0, Ri=0.0, x0=0.0, x1=6.0), 680.0),
    ("aft_bulkhead", "hcyl", dict(Ro=38.0, Ri=0.0, x0=244.0, x1=250.0), 680.0),
    ("rod_left", "hcyl", dict(Ro=3.0, Ri=0.0, x0=6.0, x1=244.0, yc=-25.0, zc=12.0), 7850.0),
    ("rod_right", "hcyl", dict(Ro=3.0, Ri=0.0, x0=6.0, x1=244.0, yc=25.0, zc=12.0), 7850.0),
    ("sled", "box", dict(x0=30.0, x1=220.0, y0=-30.0, y1=30.0, z0=-2.0, z1=2.0), 680.0),
    ("battery", "box", dict(x0=60.0, x1=130.0, y0=-12.0, y1=12.0, z0=2.0, z1=27.0), 2000.0),
    ("camera_shroud", "saddle", dict(x0=150.0, x1=200.0, w=20.0, Ro=40.0, zt=50.0), 1040.0),
]


def payload_part_props(kind, p):
    if kind == "hcyl":
        return hollow_cyl_x(**p)
    if kind == "box":
        return box(**p)
    if kind == "saddle":
        return saddle(**p)
    raise ValueError(kind)


def payload_analytic():
    """Returns per-part (unit density) props and the composite with densities (mass in kg, I in kg m^2)."""
    parts = {}
    mparts = []
    for name, kind, p, rho in PAYLOAD:
        mp = payload_part_props(kind, p)
        parts[name] = mp
        # mm^3 -> m^3 : 1e-9 ; mm^5 -> m^5 : 1e-15 ; c in mm -> m
        mparts.append(MassProps(mp.V * 1e-9 * rho, mp.c * 1e-3, mp.I * 1e-15 * rho))
    return parts, combine(mparts)


def payload_oml_analytic():
    """Outer-mold-line solid of the closed payload: full cylinder R=40 L=250 plus the shroud."""
    cyl = hollow_cyl_x(40.0, 0.0, 0.0, 250.0)
    sh = saddle(150.0, 200.0, 20.0, 40.0, 50.0)
    return combine([cyl, sh])


if __name__ == "__main__":
    o = OGIVE
    print("ogive solid", ogive_solid(o["L"], o["R"]))
    print("ogive hollow", ogive_hollow_vertical(o["L"], o["R"], o["t"]))
    f = FIN
    print("fin", fin_plate(trapezoid_fin_pts(f["cr"], f["ct"], f["s"], f["m"]), f["t"]))
    t = TUBE
    print("tube", hollow_cyl_x(t["Ro"], t["Ri"], 0, t["L"]))
    parts, comp = payload_analytic()
    for k, v in parts.items():
        print(k, v)
    print("payload composite (kg, m, kg m^2):", comp.V, comp.c, "\n", comp.I)
    print("payload OML", payload_oml_analytic())
