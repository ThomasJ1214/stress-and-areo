"""OpenRocket-compatible mass and CG model (OpenRocket 24.12 ``MassCalculation`` / component ``calculateProperties``).

Tier ``ENGINEERING_OR``: geometry × material density exactly as OpenRocket computes it, so results can be
compared one-to-one. Inertia is added in Milestone 3.

* Symmetric parts: 128 conical frusta, wall thickness measured normal to the surface (filled bodies honoured),
  shoulders and caps for transitions / nose cones.
* Fins: planform between the fin outline and the body surface (strip integration), × thickness × cross-section
  volume factor (square 1.00, rounded 0.99, airfoil 0.85), plus tab rectangle and fillets.
* Rings, tubes, lugs, rail buttons, mass objects, recovery devices: closed-form volumes × density.
* Overrides follow ``MassCalculation.calculateStructure`` (mass/CG overrides with sub-component flags).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from stressaero.core.configuration import FlightConfiguration
from stressaero.core.provenance import Provenance, Tier
from stressaero.core.rocket import (
    ASSEMBLIES,
    FINS,
    MASS_OBJECTS,
    RINGS,
    SYMMETRIC,
    Component,
    Kind,
    Material,
    Rocket,
)
from stressaero.geometry.components import (
    fin_points,
    instance_axial_offsets,
    radius_at,
    shape_params,
    wall_thickness,
)
from stressaero.geometry.shapes import Shape

PROVENANCE = Provenance(
    Tier.ENGINEERING_OR,
    "mass.or_compat.24_12",
    references=("OpenRocket 24.12 MassCalculation / RocketComponent.getComponentMass",),
)
CROSS_SECTION_VOLUME = {"square": 1.00, "rounded": 0.99, "airfoil": 0.85}
_N_FRUSTA = 128


@dataclass(frozen=True)
class MassProps:
    mass: float
    cg_x: float
    provenance: Provenance = PROVENANCE


def _rho(m: Material | None) -> float:
    return m.density if m is not None else 0.0


def _frustum(length: float, r1: float, r2: float) -> tuple[float, float]:
    """(cg from the small end, volume/(π/3)) of a solid conical frustum."""
    vol = length * (r1 * r1 + r1 * r2 + r2 * r2)
    if vol < 1e-8:
        return length / 2, vol
    return length * (r1 * r1 + 2 * r1 * r2 + 3 * r2 * r2) / (4 * (r1 * r1 + r1 * r2 + r2 * r2)), vol


def _symmetric(c: Component) -> tuple[float, float]:
    length, rho = c.length, _rho(c.material)
    th = wall_thickness(c)
    filled = th is None
    if c.kind is Kind.BODYTUBE:
        ro = c.resolved["fore_radius"]
        ri = 0.0 if filled else max(ro - th, 0.0)
        return math.pi * (ro * ro - ri * ri) * length * rho, length / 2
    vol = cgx = 0.0
    if length > 1e-8:
        for n in range(_N_FRUSTA):
            x1, x2 = n * length / _N_FRUSTA, (n + 1) * length / _N_FRUSTA
            dl = x2 - x1
            r1o, r2o = float(radius_at(c, x1)), float(radius_at(c, x2))
            if filled:
                r1i = r2i = 0.0
            else:
                h = th * math.hypot(r2o - r1o, dl) / dl
                r1i, r2i = max(r1o - h, 0.0), max(r2o - h, 0.0)
            fcg, fv = _frustum(dl, r1o, r2o)
            icg, iv = _frustum(dl, r1i, r2i)
            dv = fv - iv
            if dv != 0:
                cgx += dv * (x1 + (fcg * fv - icg * iv) / dv)
            vol += dv
        vol *= math.pi / 3
        cgx *= math.pi / 3
    parts = [(0.0, length / 2) if vol < 1e-10 else (rho * vol, cgx / vol)]

    def shoulder(prefix: str) -> tuple[float, float, float, bool]:
        return (
            c.num(prefix + "shoulderradius"),
            c.num(prefix + "shoulderlength"),
            c.num(prefix + "shoulderthickness"),
            bool(c.values.get(prefix + "shouldercapped", False)),
        )

    sh = {"fore": shoulder("fore"), "aft": shoulder("aft")}
    if c.kind is Kind.NOSECONE and c.values.get("isflipped"):
        sh = {"fore": sh["aft"], "aft": (0.0, 0.0, 0.0, False)}
    for side in ("fore", "aft"):
        radius, sl, st, cap = sh[side]
        ir = max(radius - st, 0.0)
        if sl > 0.001:
            parts.append(
                (
                    math.pi * max(radius * radius - ir * ir, 0.0) * sl * rho,
                    -sl / 2 if side == "fore" else length + sl / 2,
                )
            )
        if cap:
            xc = (-sl + st - sl) / 2 if side == "fore" else (length + sl - st + length + sl) / 2
            parts.append((math.pi * ir * ir * st * rho, xc))
    total = sum(p[0] for p in parts)
    return total, (sum(p[0] * p[1] for p in parts) / total if total > 0 else length / 2)


def _curve_integral(points: list[tuple[float, float]]) -> tuple[float, float]:
    """FinSet.calculateCurveIntegral: area and x-centroid under a closed polyline (strip integration)."""
    cx = w = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        area = (x1 - x0) * (y1 + y0) * 0.5
        if abs(area) < 0.5e-8:  # MathUtil.equals(0, area): |area| < EPSILON/2
            continue
        xc = (x0 * (2 * y0 + y1) + x1 * (2 * y1 + y0)) / (3 * (y1 + y0))
        nw = w + area
        if nw != 0:
            cx = (cx * w + xc * area) / nw
        w = nw
    return abs(w), cx


def _cant_y_offset(par: Component, cant: float, xs: float, xe: float, x: float) -> float:
    """FinSet.getFinCantYOffset: lowers the root so a canted (rotated) fin root still touches the body."""
    plen = par.length
    if abs(cant) < 1e-12 or (xs > plen and xe > plen) or (xs < 0 and xe < 0):
        return 0.0
    xc = min(max(x, 0.0), plen)
    center = (xs + xe) / 2
    dx = xc - center
    r_rot = float(radius_at(par, center + dx * abs(math.cos(cant))))
    dz = abs(math.sin(cant)) * dx
    return 0.0 if dz >= r_rot else -(r_rot - math.sqrt(r_rot * r_rot - dz * dz))


def _mount_points(c: Component, xs: float, xe: float) -> list[tuple[float, float]]:
    """FinSet.getMountPoints: body surface under the fin root (x relative to xs, y = body radius)."""
    par = c.parent
    if par is None or par.kind not in SYMMETRIC:
        return [(0.0, 0.0), (xe - xs, 0.0)]
    n = 1
    curved = par.kind in (Kind.TRANSITION, Kind.NOSECONE) and shape_params(par)[0] is not Shape.CONICAL
    if abs(c.values.get("cant") or 0.0) > 1e-12 or curved:
        n = min(100, int(math.ceil((xe - xs) / 0.0025)))
    n = max(n, 1)
    cant = c.values.get("cant") or 0.0
    pts = []
    for i in range(n + 1):
        x = xs + (xe - xs) * i / n
        pts.append((x, float(radius_at(par, x)) + _cant_y_offset(par, cant, xs, xe, x)))
    if xs < 0 < xe:
        pts.insert(1, (0.0, pts[0][1]))
    if xs < par.length < xe:
        pts.insert(len(pts) - 1, (par.length, pts[-1][1]))
    return [(x - xs, y) for x, y in pts]


def _fins(c: Component) -> tuple[float, float]:
    rho, rho_f = _rho(c.material), _rho(c.fillet_material)
    t = c.num("thickness")
    factor = CROSS_SECTION_VOLUME.get((c.values.get("crosssection") or "square").strip(), 1.0)
    length, xf = c.length, c.x_rel
    rf = c.resolved.get("body_radius", 0.0)
    mount = _mount_points(c, xf, xf + length)
    pts = fin_points(c)
    if c.kind in (Kind.TRAPEZOIDFINSET, Kind.ELLIPTICALFINSET) and len(mount) > 1 and pts:
        pts[0] = (mount[0][0], mount[0][1] - rf)
        pts[-1] = (mount[-1][0], mount[-1][1] - rf)
    upper = [(x, y + rf) for x, y in pts]
    area, cx = _curve_integral(upper + list(reversed(mount)))
    parts = [(area * t * factor * rho, cx)]
    th, tl = c.num("tabheight"), c.num("tablength")
    if th * tl > 1e-10:
        rel, off = "top", 0.0
        for attrs, text in c.multi.get("tabposition", []):  # last <tabposition> wins
            r = attrs.get("relativeto", "top")
            rel = {"front": "top", "center": "middle", "end": "bottom"}.get(r, r)
            off = float(text.strip() or 0.0)
        front = {"top": off, "middle": off + (length - tl) / 2, "bottom": off + (length - tl)}.get(rel, off)
        front = max(0.0, min(front, length))
        tl = max(0.0, min(tl, length - front))
        parts.append((tl * th * t * rho, front + tl / 2))
    fr = c.num("filletradius")
    if fr > 0 and c.parent is not None and c.parent.kind in SYMMETRIC:
        vol = mx = 0.0
        for (x0, y0), (x1, y1) in zip(mount, mount[1:], strict=False):
            xa = (x0 + x1) / 2
            rb = float(radius_at(c.parent, xf + xa))
            hyp = fr + rb
            inner, outer = math.asin(fr / hyp), math.acos(fr / hyp)
            csa = 2 * (math.tan(outer) * fr * fr / 2 - outer * fr * fr / 2 - inner * rb * rb / 2)
            seg = math.hypot(x1 - x0, y1 - y0) * csa
            vol += seg
            mx += seg * xa
        if vol > 0:
            parts.append((vol * rho_f, mx / vol))
    total = sum(p[0] for p in parts)
    x = sum(p[0] * p[1] for p in parts) / total if total > 0 else length / 2
    return total * c.instance_count, x


def component_mass_cg(c: Component) -> tuple[float, float]:
    """Mass of all the component's own instances and CG x relative to the component front."""
    k, length, n = c.kind, c.length, c.instance_count
    sep_mid = c.num("instanceseparation") * (n - 1) / 2
    if k in SYMMETRIC:
        return _symmetric(c)
    if k in FINS:
        return _fins(c)
    if k is Kind.TUBEFINSET:
        ro = c.resolved["outer_radius"]
        ri = max(ro - c.num("thickness"), 0.0)
        return math.pi * (ro * ro - ri * ri) * length * n * _rho(c.material), length / 2
    if k is Kind.LAUNCHLUG:
        r, th = c.num("radius"), c.num("thickness")
        return length * math.pi * (r * r - (r - th) ** 2) * n * _rho(c.material), length / 2 + sep_mid
    if k is Kind.RAILBUTTON:
        od, idd = c.num("outerdiameter"), c.num("innerdiameter")
        h, bh, fh, sh = c.num("height"), c.num("baseheight"), c.num("flangeheight"), c.num("screwheight")
        vol = math.pi * (
            (od / 2) ** 2 * fh + (idd / 2) ** 2 * (h - fh - bh) + (od / 2) ** 2 * bh + 2.0 / 3 * (od / 2) ** 2 * sh
        )
        return vol * n * _rho(c.material), sep_mid
    if k in RINGS:
        ro, ri = c.resolved["outer_radius"], c.resolved["inner_radius"]
        m1 = math.pi * max(ro * ro - ri * ri, 0.0) * length * _rho(c.material)
        if k is Kind.INNERTUBE:
            return m1 * n, length / 2  # cluster offsets are radial only
        return m1 * n, length / 2 + sep_mid
    if k is Kind.MASSCOMPONENT:
        return c.num("mass"), length / 2
    if k is Kind.SHOCKCORD:
        return c.num("cordlength") * _rho(c.material), length / 2
    if k is Kind.PARACHUTE:
        d = c.num("diameter")
        m = math.pi * (d / 2) ** 2 * _rho(c.material) + c.num("linecount") * c.num("linelength") * _rho(c.line_material)
        return m, length / 2
    if k is Kind.STREAMER:
        return c.num("striplength") * c.num("stripwidth") * _rho(c.material), length / 2
    return 0.0, length / 2


def _is_active(c: Component, active_stages: frozenset[int] | None) -> bool:
    if c.kind is Kind.ROCKET or active_stages is None or c.stage_index is None:
        return True
    return c.stage_index in active_stages


def _structure(c: Component, active: frozenset[int] | None, mult: float) -> tuple[float, float]:
    """(mass, x-moment) in absolute coordinates with MassCalculation.calculateStructure semantics."""
    child_mult = mult * (c.instance_count if (c.kind in ASSEMBLIES or c.kind is Kind.INNERTUBE) else 1)
    cm = cx = 0.0
    for ch in c.children:
        m, x = _structure(ch, active, child_mult)
        cm += m
        cx += x
    own_m = own_x = 0.0
    if _is_active(c, active):
        m, xl = component_mass_cg(c)
        xcm = c.x_abs + xl
        w = m * mult
        ov = c.override
        if ov.mass is not None:
            if c.kind in ASSEMBLIES:
                xcm = cx / cm if cm > 0 else c.x_abs
            w = ov.mass * mult
            if ov.mass_sub:
                cm = cx = 0.0
        if ov.cg is not None:
            xcm = c.x_abs + ov.cg
            if ov.cg_sub:
                cx = cm * xcm
        own_m, own_x = w, w * xcm
    return own_m + cm, own_x + cx


def structure_mass(rocket: Rocket, config: FlightConfiguration | None) -> MassProps:
    """Dry structure mass and CG (no motors) of the active stages of ``config``."""
    active = config.active_stages if config is not None else None
    m, mx = _structure(rocket.root, active, 1.0)
    return MassProps(m, mx / m if m > 0 else 0.0)


def _active_symmetric(rocket: Rocket, config: FlightConfiguration | None) -> list[Component]:
    active = config.active_stages if config is not None else None
    return [c for c in rocket.root.walk() if c.kind in SYMMETRIC and _is_active(c, active)]


def reference_length(rocket: Rocket, config: FlightConfiguration | None) -> float:
    """OpenRocket reference length (diameter): maximum body diameter, nose-cone base, or custom."""
    root = rocket.root
    rtype = (root.values.get("referencetype") or "maximum").strip()
    if rtype == "custom":
        return root.num("customreference")
    syms = _active_symmetric(rocket, config)
    if rtype == "nosecone":
        for s in syms:
            if s.resolved["fore_radius"] >= 0.0005:
                return 2 * s.resolved["fore_radius"]
            if s.resolved["aft_radius"] >= 0.0005:
                return 2 * s.resolved["aft_radius"]
        return 2 * 0.025
    return 2 * max([max(s.resolved["fore_radius"], s.resolved["aft_radius"]) for s in syms] or [0.0])


def rocket_length(rocket: Rocket, config: FlightConfiguration | None) -> float:
    """Overall length = x-span of all active component bounds (OpenRocket ``FlightConfiguration.getLength``).

    Mass objects contribute their *untransformed* local bounds [0, L] (OpenRocket's legacy-bounds behaviour).
    """
    active = config.active_stages if config is not None else None
    xs: list[float] = []
    for c in rocket.root.walk():
        if c.kind in ASSEMBLIES or not _is_active(c, active):
            continue
        if c.kind in MASS_OBJECTS:
            xs += [0.0, c.length]
            continue
        for off in instance_axial_offsets(c):
            x0 = c.x_abs + off
            if c.kind in FINS:
                px = [p[0] for p in fin_points(c)] or [0.0]
                xs += [x0 + min(px), x0 + max(px)]
            elif c.kind is Kind.RAILBUTTON:
                r = c.num("outerdiameter") / 2
                xs += [x0 - r, x0 + r]
            else:
                xs += [x0, x0 + c.length]
    return (max(xs) - min(xs)) if xs else 0.0
