"""Display meshes for resolved rocket components (world frame: +x aft from the nose tip, metres).

Each mesh carries ``cell_data["component_index"]`` (pre-order index of the component, for picking) and
``field_data["internal"]`` (1 for internal components drawn semi-transparent) and, when the file defines one,
``field_data["color"]`` (RGB 0–1). Pod / parallel-stage instances are applied as OpenRocket does: rotate the
pod-local geometry by the instance angle about x, then translate it radially.
"""

from __future__ import annotations

import math

import numpy as np
import pyvista as pv

from stressaero.core.configuration import FlightConfiguration
from stressaero.core.rocket import (
    ASSEMBLIES,
    FINS,
    MASS_OBJECTS,
    RINGS,
    SYMMETRIC,
    Component,
    Kind,
    Rocket,
)
from stressaero.geometry.components import fin_points, instance_axial_offsets, radius_at, wall_thickness
from stressaero.io.ork.parse import CLUSTERS

INTERNAL = frozenset(RINGS | MASS_OBJECTS)
_POD_KINDS = (Kind.PODSET, Kind.PARALLELSTAGE, Kind.BOOSTERSET)


def _revolve(xs: np.ndarray, r_out: np.ndarray, r_in: np.ndarray, segments: int) -> pv.PolyData:
    """Closed shell of revolution about x from outer/inner profiles (inner may be all zeros = solid)."""
    xs = np.asarray(xs, float)
    ro = np.asarray(r_out, float)
    ri = np.minimum(np.asarray(r_in, float), ro)
    solid = bool(np.all(ri <= 1e-12))
    prof_x = list(xs) + ([xs[-1], xs[0]] if solid else list(xs[::-1]))
    prof_r = list(ro) + ([0.0, 0.0] if solid else list(ri[::-1]))
    m = len(prof_x)
    th = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    pts = np.empty((m * segments, 3))
    for j, t in enumerate(th):
        pts[j * m : (j + 1) * m, 0] = prof_x
        pts[j * m : (j + 1) * m, 1] = np.asarray(prof_r) * np.cos(t)
        pts[j * m : (j + 1) * m, 2] = np.asarray(prof_r) * np.sin(t)
    faces = []
    for j in range(segments):
        a, b = j * m, ((j + 1) % segments) * m
        for i in range(m):
            i2 = (i + 1) % m
            faces += [4, a + i, a + i2, b + i2, b + i]
    mesh = pv.PolyData(pts, np.array(faces)).triangulate().clean(tolerance=1e-12)
    areas = mesh.compute_cell_sizes(length=False, volume=False)["Area"]
    if np.any(areas <= 1e-18):  # zero-area triangles where the profile touches the axis (nose tip)
        mesh = (
            mesh.extract_cells(np.flatnonzero(areas > 1e-18)).extract_surface(algorithm="dataset_surface").triangulate()
        )
    return mesh


def _annulus(x0: float, length: float, ro: float, ri: float, segments: int) -> pv.PolyData:
    return _revolve(np.array([x0, x0 + length]), np.array([ro, ro]), np.array([ri, ri]), segments)


def _symmetric(c: Component, segments: int) -> pv.PolyData:
    n = 2 if c.kind is Kind.BODYTUBE else 96
    xs = np.linspace(0.0, c.length, n)
    ro = np.asarray(radius_at(c, xs), float)
    th = wall_thickness(c)
    ri = np.zeros_like(ro) if th is None else np.maximum(ro - th, 0.0)
    parts = [_revolve(xs, ro, ri, segments)]
    for prefix, at_fore in (("fore", True), ("aft", False)):
        sl, sr = c.num(prefix + "shoulderlength"), c.num(prefix + "shoulderradius")
        if c.kind is Kind.NOSECONE and c.values.get("isflipped"):
            at_fore = prefix == "aft"
            if prefix == "fore":
                continue
        if sl > 0.001 and sr > 0:
            st = c.num(prefix + "shoulderthickness")
            inner = 0.0 if c.values.get(prefix + "shouldercapped") and st >= sr else max(sr - st, 0.0)
            x0 = -sl if at_fore else c.length
            parts.append(_annulus(x0, sl, sr, inner, segments))
    mesh = parts[0]
    for p in parts[1:]:
        mesh = mesh.merge(p)
    return mesh.translate((c.x_abs, 0, 0))


def _fin_set(c: Component) -> pv.PolyData:
    rb = c.resolved.get("body_radius", 0.0)
    pts = fin_points(c)
    if len(pts) < 3:
        return pv.PolyData()
    t = max(c.num("thickness"), 1e-5)
    poly = np.array([[x, y + rb, 0.0] for x, y in pts])
    face = np.hstack([[len(poly)], np.arange(len(poly))])
    plate = pv.PolyData(poly, face).triangulate()
    fin = plate.extrude((0, 0, t), capping=True).translate((0, 0, -t / 2)).triangulate().clean()
    cant = c.values.get("cant") or 0.0
    if cant:
        fin = fin.rotate_vector((0, 1, 0), math.degrees(cant), point=(c.length / 2, 0, 0))
    base = math.degrees(c.values.get("angleoffset", c.values.get("rotation", 0.0)) or 0.0)
    out = pv.PolyData()
    for i in range(c.instance_count):
        out = out.merge(fin.rotate_x(base + 360.0 * i / c.instance_count, point=(0, 0, 0)))
    return out.translate((c.x_abs, 0, 0))


def _radial(c: Component) -> tuple[float, float]:
    return c.num("radialposition"), c.values.get("radialdirection", 0.0) or 0.0


def _parent_radius(c: Component) -> float:
    par = c.parent
    if par is not None and par.kind in SYMMETRIC:
        return float(radius_at(par, c.x_rel))
    return 0.0


def _other(c: Component, segments: int) -> pv.PolyData:
    k = c.kind
    out = pv.PolyData()
    if k is Kind.TUBEFINSET:
        ro = c.resolved["outer_radius"]
        ri = max(ro - c.num("thickness"), 0.0)
        rb = c.resolved.get("body_radius", 0.0)
        tube = _annulus(0.0, c.length, ro, ri, segments)
        base = c.values.get("angleoffset", 0.0) or 0.0
        for i in range(c.instance_count):
            a = base + 2 * math.pi * i / c.instance_count
            out = out.merge(tube.translate((0, (rb + ro) * math.cos(a), (rb + ro) * math.sin(a))))
    elif k is Kind.LAUNCHLUG:
        r = c.num("radius")
        tube = _annulus(0.0, c.length, r, max(r - c.num("thickness"), 0.0), 24)
        a = c.values.get("angleoffset", 0.0) or 0.0
        rr = _parent_radius(c) + r
        for off in instance_axial_offsets(c):
            out = out.merge(tube.translate((off, rr * math.cos(a), rr * math.sin(a))))
    elif k is Kind.RAILBUTTON:
        od, h = c.num("outerdiameter"), max(c.num("height"), 1e-4)
        a = c.values.get("angleoffset", 0.0) or 0.0
        rb = _parent_radius(c)
        button = pv.Cylinder(
            center=(0, rb + h / 2, 0), direction=(0, 1, 0), radius=od / 2, height=h, resolution=24
        ).triangulate()
        button = button.rotate_x(math.degrees(a), point=(0, 0, 0))
        for off in instance_axial_offsets(c):
            out = out.merge(button.translate((off, 0, 0)))
    elif k in RINGS:
        ro, ri = c.resolved["outer_radius"], c.resolved["inner_radius"]
        ring = _annulus(0.0, max(c.length, 1e-4), ro, ri, segments)
        rpos, rdir = _radial(c)
        centers = [(rpos * math.cos(rdir), rpos * math.sin(rdir))]
        if k is Kind.INNERTUBE:
            pts = CLUSTERS.get(c.values.get("clusterconfiguration") or "single", [0, 0])
            scale = 2 * ro * (c.num("clusterscale", 1.0) or 1.0)
            rot = (c.values.get("clusterrotation", 0.0) or 0.0) - rdir
            cr, sr = math.cos(rot), math.sin(rot)
            centers = []
            for px, py in zip(pts[0::2], pts[1::2], strict=True):
                y, z = px * scale, py * scale
                centers.append((y * cr - z * sr + rpos * math.cos(rdir), y * sr + z * cr + rpos * math.sin(rdir)))
        for off in instance_axial_offsets(c) if k is not Kind.INNERTUBE else [0.0]:
            for y, z in centers:
                out = out.merge(ring.translate((off, y, z)))
    elif k in MASS_OBJECTS:
        r = max(c.resolved.get("packed_radius", 0.0), 1e-4)
        rpos, rdir = _radial(c)
        body = pv.Cylinder(
            center=(c.length / 2, rpos * math.cos(rdir), rpos * math.sin(rdir)),
            direction=(1, 0, 0),
            radius=r,
            height=max(c.length, 1e-4),
            resolution=segments,
        ).triangulate()
        out = body
    return out.translate((c.x_abs, 0, 0)) if out.n_points else out


def _pod_transforms(c: Component) -> list[tuple[float, float, float]]:
    """(angle about x, y, z) for every pod/parallel-stage instance the component sits in (nested pods compose)."""
    transforms = [(0.0, 0.0, 0.0)]
    for anc in reversed(list(c.ancestors())):
        if anc.kind not in _POD_KINDS:
            continue
        method = (anc.attrs.get("radiusoffset", {}).get("method") or "free").lower()
        try:
            off = float(anc.values.get("radiusoffset") or 0.0)
        except ValueError:
            off = 0.0
        par_r = _parent_radius(anc)
        r_bound = max(
            [
                max(ch.resolved.get("fore_radius", 0.0), ch.resolved.get("aft_radius", 0.0))
                for ch in anc.children
                if ch.kind in SYMMETRIC
            ]
            or [0.0]
        )
        radius = {"coaxial": 0.0, "free": off, "relative": off + par_r + r_bound, "surface": par_r + r_bound}.get(
            method, off
        )
        base = anc.values.get("angleoffset", 0.0) or 0.0
        new = []
        for a0, y0, z0 in transforms:
            for i in range(anc.instance_count):
                th = base + 2 * math.pi * i / anc.instance_count
                ca, sa = math.cos(a0), math.sin(a0)
                y, z = radius * math.cos(th), radius * math.sin(th)
                new.append((a0 + th, y0 + y * ca - z * sa, z0 + y * sa + z * ca))
        transforms = new
    return transforms


def component_mesh(c: Component, *, segments: int = 96) -> pv.PolyData | None:
    """World-frame display mesh of all instances of ``c`` (None for assemblies / empty geometry)."""
    if c.kind in ASSEMBLIES:
        return None
    if c.kind in SYMMETRIC:
        local = _symmetric(c, segments)
    elif c.kind in FINS:
        local = _fin_set(c)
    else:
        local = _other(c, segments)
    if local is None or local.n_points == 0:
        return None
    mesh = pv.PolyData()
    for angle, y, z in _pod_transforms(c):
        mesh = mesh.merge(local.rotate_x(math.degrees(angle), point=(0, 0, 0)).translate((0, y, z)))
    index = next(i for i, comp in enumerate(_root(c).walk()) if comp is c)
    mesh.cell_data["component_index"] = np.full(mesh.n_cells, index, dtype=np.int32)
    mesh.field_data["internal"] = np.array([1 if c.kind in INTERNAL else 0], dtype=np.int8)
    paint = (c.appearance or {}).get("paint")
    if paint:
        try:
            mesh.field_data["color"] = np.array([float(paint.get(k, 0)) / 255.0 for k in ("red", "green", "blue")])
        except ValueError:
            pass
    return mesh


def _root(c: Component) -> Component:
    while c.parent is not None:
        c = c.parent
    return c


def rocket_meshes(rocket: Rocket, config: FlightConfiguration | None, *, segments: int = 96) -> dict[str, pv.PolyData]:
    """Meshes of all components in the active stages of ``config`` keyed by component id."""
    active = config.active_stages if config is not None else None
    out: dict[str, pv.PolyData] = {}
    for c in rocket.root.walk():
        if active is not None and c.stage_index is not None and c.stage_index not in active:
            continue
        mesh = component_mesh(c, segments=segments)
        if mesh is not None:
            out[c.id] = mesh
    return out
