"""Geometry queries on *resolved* rocket components (after :func:`stressaero.io.ork.resolve.resolve`).

Shared by the mass model, display meshing and aerodynamics so every consumer sees the same shape.
Positions are relative to the component's own front unless stated otherwise.
"""

from __future__ import annotations

import math

from stressaero.core.rocket import FILLED, RINGS, SYMMETRIC, Component, Kind
from stressaero.geometry.shapes import CLIPPABLE, DEFAULT_PARAM, Shape, profile_radius


def shape_params(c: Component) -> tuple[Shape, float, bool]:
    """(shape, shape parameter, clipped) of a nose cone / transition (body tubes are cylinders)."""
    shape = Shape((c.values.get("shape") or "conical").strip().lower())
    param = c.values.get("shapeparameter")
    param = DEFAULT_PARAM.get(shape, 0.0) if not isinstance(param, float) else param
    clipped = bool(c.values.get("shapeclipped", True)) and shape in CLIPPABLE
    return shape, param, clipped


def radius_at(c: Component, x):
    """Outer radius of a symmetric component at ``x`` (scalar or array) from its front."""
    fore, aft = c.resolved["fore_radius"], c.resolved["aft_radius"]
    if c.kind is Kind.BODYTUBE:
        return fore if not hasattr(x, "__len__") else fore + 0.0 * x
    shape, param, clipped = shape_params(c)
    return profile_radius(shape, x, c.length, fore, aft, param, clipped)


def wall_thickness(c: Component) -> float | None:
    """Wall thickness of a symmetric component, or None if it is filled."""
    t = c.values.get("thickness")
    if t == FILLED:
        return None
    return float(t) if isinstance(t, float) else 0.0


def inner_radius_at(c: Component, x: float) -> float | None:
    """Inner radius offered to internal children (``RadialParent.getInnerRadius``)."""
    if c.kind in SYMMETRIC:
        th = wall_thickness(c)
        if th is None:
            return 0.0
        return max(float(radius_at(c, x)) - th, 0.0)
    if c.kind in (Kind.INNERTUBE, Kind.TUBECOUPLER):
        return max(c.resolved["outer_radius"] - c.num("thickness"), 0.0)
    if c.kind in RINGS:
        return c.resolved.get("inner_radius", 0.0)
    return None


def fin_points(c: Component) -> list[tuple[float, float]]:
    """Single-fin planform outline (x from the fin's root leading edge, y outward), OpenRocket ordering."""
    if c.kind is Kind.TRAPEZOIDFINSET:
        root, tip = c.num("rootchord"), c.num("tipchord")
        sweep, h = c.num("sweeplength"), c.num("height")
        pts = [(0.0, 0.0), (sweep, h)]
        if tip > 0.0001:
            pts.append((sweep + tip, h))
        pts.append((max(root, 0.0001), 0.0))
        return pts
    if c.kind is Kind.ELLIPTICALFINSET:
        length, h, n = max(c.num("rootchord"), 0.0001), c.num("height"), 31
        pts = []
        for i in range(n):
            a = math.pi * (n - 1 - i) / (n - 1)
            pts.append(((math.cos(a) + 1) / 2 * length, math.sin(a) * h))
        pts[0] = (0.0, 0.0)
        pts[-1] = (length, 0.0)
        return pts
    if c.kind is Kind.FREEFORMFINSET:
        return list(c.fin_points or [])
    return []


def instance_axial_offsets(c: Component) -> list[float]:
    """Axial offsets of the component's own instances (lugs, rail buttons, rings with separation)."""
    n = c.instance_count
    if c.kind in (Kind.LAUNCHLUG, Kind.RAILBUTTON, Kind.CENTERINGRING, Kind.BULKHEAD) and n > 1:
        sep = c.num("instanceseparation")
        return [i * sep for i in range(n)]
    return [0.0]
