"""Nose-cone and transition profile shapes, exactly as OpenRocket defines them (``Transition.Shape``).

``profile_radius`` returns the outer radius at axial position ``x`` measured from the component's fore end.
Formulas (R = radius rise, L = length, k = shape parameter):

* conical     ``R x / L``
* ogive       ``sqrt(ρ² − (Λ − x)²) − y0`` with ``ρ = sqrt((L²+R²)((2−k)²L² + k²R²) / (4k²R²))``, ``Λ = L/k``,
  ``y0 = sqrt(ρ² − Λ²)``; ``k = 1`` is a tangent ogive, ``k < 0.001`` degenerates to a cone; if ``L < R``
  the profile is computed on a stretched ``x`` (OpenRocket behaviour)
* ellipsoid   ``sqrt(2 R x' − x'²)``, ``x' = x R / L``
* power       ``R (x/L)^k``
* parabolic   ``R (2x/L − k (x/L)²) / (2 − k)``
* haack       ``R sqrt((θ − sin(2θ)/2 + k sin³θ) / π)``, ``θ = acos(1 − 2x/L)``; ``k = 0`` Von Kármán, ``1/3`` LV-Haack

Transitions between radii r1 < r2 are ``r1 + f(x; R = r2 − r1)`` unless *clipped* (ellipsoid/power/haack only):
then the full nose shape of base radius r2 is cut at the clip length ``c`` where ``f(c; r2, c+L) = r1``
(bisection on ``c`` to 1e-4 m, as OpenRocket). If r1 > r2 the profile is mirrored.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np


class Shape(StrEnum):
    CONICAL = "conical"
    OGIVE = "ogive"
    ELLIPSOID = "ellipsoid"
    POWER = "power"
    PARABOLIC = "parabolic"
    HAACK = "haack"


DEFAULT_PARAM: dict[Shape, float] = {Shape.OGIVE: 1.0, Shape.POWER: 0.5, Shape.PARABOLIC: 1.0, Shape.HAACK: 0.0}
CLIPPABLE = frozenset({Shape.ELLIPSOID, Shape.POWER, Shape.HAACK})


def _f(shape: Shape, x: np.ndarray, radius: float, length: float, k: float) -> np.ndarray:
    """Unclipped nose profile of base radius ``radius`` and length ``length`` (x from the tip)."""
    x = np.asarray(x, dtype=float)
    if shape is Shape.CONICAL:
        return radius * x / length
    if shape is Shape.OGIVE:
        if length < radius:
            x = x * radius / length
            length = radius
        if k < 0.001:
            return radius * x / length
        rho = np.sqrt(max(0.0, (length**2 + radius**2) * (((2 - k) * length) ** 2 + (k * radius) ** 2)
                          / (4 * (k * radius) ** 2)))
        lam = length / k
        y0 = np.sqrt(max(0.0, rho * rho - lam * lam))
        return np.sqrt(np.maximum(0.0, rho * rho - (lam - x) ** 2)) - y0
    if shape is Shape.ELLIPSOID:
        xs = x * radius / length
        return np.sqrt(np.maximum(0.0, 2 * radius * xs - xs * xs))
    if shape is Shape.POWER:
        if k <= 0.00001:
            return np.where(x <= 0.00001, 0.0, radius)
        return radius * np.power(np.maximum(x, 0.0) / length, k)
    if shape is Shape.PARABOLIC:
        return radius * ((2 * x / length - k * (x / length) ** 2) / (2 - k))
    if shape is Shape.HAACK:
        theta = np.arccos(np.clip(1 - 2 * x / length, -1.0, 1.0))
        v = theta - np.sin(2 * theta) / 2 + (k * np.sin(theta) ** 3 if k != 0 else 0.0)
        return radius * np.sqrt(np.maximum(0.0, v / np.pi))
    raise ValueError(f"unknown shape {shape!r}")


def clip_length(shape: Shape, length: float, r1: float, r2: float, k: float) -> float:
    """OpenRocket's clip length: bisection so that the clipped profile starts at ``r1`` (r1 < r2)."""
    if r1 == 0 or length <= 0:
        return 0.0

    def g(c: float) -> float:
        return float(_f(shape, np.asarray(c), r2, c + length, k)) - r1

    lo, hi, n = 0.0, length, 0
    while g(hi) < 0:
        lo, hi, n = hi, hi * 2, n + 1
        if n > 10:
            break
    while True:
        c = (lo + hi) / 2
        if hi - lo < 0.0001:
            return c
        if g(c) > 0:
            hi = c
        else:
            lo = c


def profile_radius(shape: Shape, x, length: float, r_fore: float, r_aft: float, param: float, clipped: bool):
    """Outer radius at ``x`` (scalar or array, measured from the fore end, clamped to [0, length])."""
    shape = Shape(shape)
    scalar = np.isscalar(x)
    xa = np.asarray(x, dtype=float)
    out = np.empty_like(xa)
    below, above = xa < 0, xa >= length
    inside = ~(below | above)
    out[below] = r_fore
    out[above] = r_aft
    if np.any(inside):
        xi = xa[inside]
        if r_fore == r_aft:
            out[inside] = r_fore
        else:
            r1, r2 = r_fore, r_aft
            if r1 > r2:
                xi = length - xi
                r1, r2 = r2, r1
            if clipped and shape in CLIPPABLE:
                c = clip_length(shape, length, r1, r2, param)
                out[inside] = _f(shape, c + xi, r2, c + length, param)
            else:
                out[inside] = r1 + _f(shape, xi, r2 - r1, length, param)
    return float(out) if scalar else out


def profile(shape: Shape, length: float, r_fore: float, r_aft: float, param: float, clipped: bool,
            n: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """Sampled profile ``(x, r)`` with ``n`` points from 0 to ``length``."""
    xs = np.linspace(0.0, length, n)
    rs = np.asarray(profile_radius(shape, xs, length, r_fore, r_aft, param, clipped), dtype=float)
    rs[-1] = r_aft  # exact end value
    rs[0] = r_fore if not (clipped and Shape(shape) in CLIPPABLE) else rs[0]
    return xs, rs
