"""Re-derive lengths, axial positions and ``auto`` dimensions exactly as OpenRocket 23.09/24.12 does.

The numbers stored after ``auto`` in ``.ork`` files are save-time caches and are frequently stale
(155 of 252 in the official samples), so every automatic dimension is recomputed from its neighbours.
Rules (verified against OpenRocket 24.12 on all fixture files, see docs/research/ork-format.md):

* Axial placement (relative to the parent's front, instance 0): ``after`` = previous sibling's x + length
  (0 for the first child); ``top`` = offset; ``middle`` = offset + (Lp − L)/2; ``bottom`` = offset + (Lp − L);
  ``absolute`` = offset − x_abs(parent). |x| < 1e-6 snaps to 0. Lp = 0 when the parent is the rocket.
* Length: body parts/rings/lugs/tube fins = <length>; trapezoid/elliptical fins = root chord;
  freeform fins = x_last − x_first; mass objects = packed length (volume-preserving with an auto radius);
  rail buttons = 0; assemblies = Σ lengths of children placed ``after``.
* Auto radii chain for body tubes/transitions/nose cones (OpenRocket's ``refComp`` logic re-implemented
  statelessly), ring outer radius = parent's inner radius, centering-ring inner radius = overlapping inner
  tubes, tube-fin radius, and OpenRocket's load-time position quirk for auto-radius mass objects.
"""

from __future__ import annotations

import math

from stressaero.core.provenance import Issue, Severity
from stressaero.core.rocket import (
    ASSEMBLIES,
    FILLED,
    FINS,
    MASS_OBJECTS,
    RINGS,
    SYMMETRIC,
    AutoValue,
    Component,
    Kind,
    Rocket,
)
from stressaero.geometry.shapes import CLIPPABLE, DEFAULT_PARAM, Shape, profile_radius

DEFAULT_RADIUS = 0.025


class _Resolver:
    def __init__(self, rocket: Rocket, emulate_or_stale_positions: bool) -> None:
        self.rocket = rocket
        self.emulate = emulate_or_stale_positions
        self._len: dict[int, float] = {}
        self._xrel: dict[int, float] = {}
        self._xabs: dict[int, float] = {}
        self._foreaft: dict[int, tuple[float, float, bool, bool]] = {}
        self._ro: dict[int, float] = {}

    # ---------------------------------------------------------------- stored values
    @staticmethod
    def _auto(c: Component, key: str) -> tuple[bool, float | None]:
        v = c.values.get(key)
        if isinstance(v, AutoValue):
            return True, v.cached
        if v is None or isinstance(v, str):
            return False, None
        return False, float(v)

    def _fore_aft_stored(self, c: Component) -> tuple[float, float, bool, bool]:
        if c.kind is Kind.BODYTUBE:
            a, r = self._auto(c, "radius")
            r = DEFAULT_RADIUS if r is None else r
            return r, r, a, a
        if c.kind is Kind.NOSECONE:
            a, rb = self._auto(c, "aftradius")
            rb = DEFAULT_RADIUS if rb is None else rb
            if c.values.get("isflipped"):
                return rb, 0.0, a, False
            return 0.0, rb, False, a
        af, rf = self._auto(c, "foreradius")
        aa, ra = self._auto(c, "aftradius")
        return (DEFAULT_RADIUS if rf is None else rf, DEFAULT_RADIUS if ra is None else ra, af, aa)

    # ---------------------------------------------------------------- inline chain
    @staticmethod
    def _inline_sequence(c: Component) -> list[Component]:
        par = c.parent
        if par is None:
            return [c]
        if par.kind is Kind.STAGE and par.parent is not None and par.parent.kind is Kind.ROCKET:
            seq: list[Component] = []
            for st in par.parent.children:
                seq += [x for x in st.children if x.kind in SYMMETRIC]
            return seq
        return [x for x in par.children if x.kind in SYMMETRIC]

    def _prev(self, c: Component) -> Component | None:
        seq = self._inline_sequence(c)
        i = seq.index(c)
        return seq[i - 1] if i > 0 else None

    def _next(self, c: Component) -> Component | None:
        seq = self._inline_sequence(c)
        i = seq.index(c)
        return seq[i + 1] if i + 1 < len(seq) else None

    def _front_auto(self, c: Component, guard: frozenset[int]) -> float:
        """Radius ``c`` offers to the NEXT component (−1 = none)."""
        f, _a, fa, aa = self._fore_aft_stored(c)
        if c.kind is Kind.BODYTUBE:
            if fa:
                p = self._prev(c)
                return self._front_auto(p, guard) if p is not None else -1.0
            return f
        return -1.0 if aa else self.aft_radius(c)

    def _rear_auto(self, c: Component, guard: frozenset[int]) -> float:
        """Radius ``c`` offers to the PREVIOUS component (−1 = none)."""
        f, _a, fa, _aa = self._fore_aft_stored(c)
        if c.kind is Kind.BODYTUBE:
            if fa:
                n = self._next(c)
                return self._rear_auto(n, guard) if n is not None else -1.0
            return f
        return -1.0 if fa else self.fore_radius(c)

    def _uses_next(self, c: Component, guard: frozenset[int]) -> bool:
        _f, _a, fa, aa = self._fore_aft_stored(c)
        if c.kind is Kind.BODYTUBE:
            return fa and self._bt_auto(c, guard)[1] == "next"
        return aa

    def _uses_prev(self, c: Component, guard: frozenset[int]) -> bool:
        _f, _a, fa, _aa = self._fore_aft_stored(c)
        if c.kind is Kind.BODYTUBE:
            return fa and self._bt_auto(c, guard)[1] == "prev"
        return fa

    def _bt_auto(self, bt: Component, guard: frozenset[int]) -> tuple[float, str | None]:
        """BodyTube.getAutoOuterRadius() → (radius, side used); cycles resolve like a fresh refComp."""
        if id(bt) in guard:
            return -1.0, None
        guard = guard | {id(bt)}
        p, n = self._prev(bt), self._next(bt)
        if p is not None and not self._uses_next(p, guard):
            r = self._front_auto(p, guard)
            if r >= 0:
                return r, "prev"
        if n is not None and not self._uses_prev(n, guard):
            r = self._rear_auto(n, guard)
            if r >= 0:
                return r, "next"
        return DEFAULT_RADIUS, None

    def _fore_aft(self, c: Component) -> tuple[float, float, bool, bool]:
        key = id(c)
        if key not in self._foreaft:
            f, a, fa, aa = self._fore_aft_stored(c)
            if c.kind is Kind.BODYTUBE:
                if fa:
                    r, _side = self._bt_auto(c, frozenset())
                    f = a = r
            else:
                if fa:
                    p = self._prev(c)
                    f = self._front_auto(p, frozenset()) if p is not None else DEFAULT_RADIUS
                if aa:
                    n = self._next(c)
                    a = self._rear_auto(n, frozenset()) if n is not None else DEFAULT_RADIUS
            self._foreaft[key] = (f, a, fa, aa)
        return self._foreaft[key]

    def fore_radius(self, c: Component) -> float:
        return self._fore_aft(c)[0]

    def aft_radius(self, c: Component) -> float:
        return self._fore_aft(c)[1]

    # ---------------------------------------------------------------- symmetric profile
    @staticmethod
    def shape_of(c: Component) -> tuple[Shape, float, bool]:
        shape = Shape((c.values.get("shape") or "conical").strip().lower())
        param = c.values.get("shapeparameter")
        param = DEFAULT_PARAM.get(shape, 0.0) if not isinstance(param, float) else param
        clipped = bool(c.values.get("shapeclipped", True)) and shape in CLIPPABLE
        return shape, param, clipped

    def radius_at(self, c: Component, x: float) -> float:
        if c.kind is Kind.BODYTUBE:
            return self.fore_radius(c)
        shape, param, clipped = self.shape_of(c)
        return float(profile_radius(shape, x, self.length(c), self.fore_radius(c), self.aft_radius(c), param, clipped))

    @staticmethod
    def thickness_sym(c: Component) -> float | None:
        t = c.values.get("thickness")
        if t == FILLED:
            return None
        return float(t) if isinstance(t, float) else 0.0

    def inner_radius_at(self, c: Component, x: float) -> float | None:
        if c.kind is Kind.BODYTUBE:
            th = self.thickness_sym(c)
            return 0.0 if th is None else max(self.fore_radius(c) - th, 0.0)
        if c.kind in (Kind.TRANSITION, Kind.NOSECONE):
            th = self.thickness_sym(c)
            return 0.0 if th is None else max(self.radius_at(c, x) - th, 0.0)
        if c.kind in (Kind.INNERTUBE, Kind.TUBECOUPLER):
            return max(self.outer_radius(c) - c.num("thickness"), 0.0)
        return None

    # ---------------------------------------------------------------- mass objects
    def massobject_auto_radius(self, c: Component) -> float | None:
        par = c.parent
        if par is None:
            return None
        if par.kind is Kind.NOSECONE:
            return self.fore_radius(par) if par.values.get("isflipped") else self.aft_radius(par)
        if par.kind is Kind.TRANSITION:
            return max(self.fore_radius(par), self.aft_radius(par))
        if par.kind is Kind.BODYTUBE:
            return self.inner_radius_at(par, 0.0)
        if par.kind in RINGS:
            return self.ring_inner_radius(par)
        return 0.0

    def packed_radius(self, c: Component) -> float:
        a, r = self._auto(c, "packedradius")
        if a:
            ra = self.massobject_auto_radius(c)
            if ra:
                return ra
        return r or 0.0

    # ---------------------------------------------------------------- lengths & positions
    def length(self, c: Component) -> float:
        key = id(c)
        if key in self._len:
            return self._len[key]
        k = c.kind
        if k in SYMMETRIC or k in RINGS or k in (Kind.TUBEFINSET, Kind.LAUNCHLUG):
            length = c.num("length")
        elif k in (Kind.TRAPEZOIDFINSET, Kind.ELLIPTICALFINSET):
            length = c.num("rootchord")
        elif k is Kind.FREEFORMFINSET:
            pts = c.fin_points or [(0.0, 0.0)]
            length = pts[-1][0] - pts[0][0]
        elif k in MASS_OBJECTS:
            length = c.num("packedlength")
            a, r_saved = self._auto(c, "packedradius")
            if a and r_saved:
                r_auto = self.massobject_auto_radius(c)
                if r_auto and r_auto > 0:
                    length = r_saved * r_saved * length / (r_auto * r_auto)
        elif k is Kind.RAILBUTTON:
            length = 0.0
        elif k in ASSEMBLIES:
            length = sum(self.length(ch) for ch in c.children if ch.placement.method == "after")
        else:
            length = 0.0
        self._len[key] = length
        return length

    def x_rel(self, c: Component) -> float:
        key = id(c)
        if key in self._xrel:
            return self._xrel[key]
        par = c.parent
        if par is None:
            x = 0.0
        else:
            m, off = c.placement.method, c.placement.offset
            if m == "after":
                idx = par.children.index(c)
                if idx == 0:
                    x = 0.0
                else:
                    prev = par.children[idx - 1]
                    x = self.x_rel(prev) + self.length(prev)
            elif m == "absolute":
                x = off - self.x_abs(par)
            else:
                plen = 0.0 if par.kind is Kind.ROCKET else self.length(par)
                length = self.length(c)
                if self.emulate and c.kind in MASS_OBJECTS and self._auto(c, "packedradius")[0]:
                    # OpenRocket positions such objects at load time with the SAVED packed length but uses
                    # the auto-radius-derived length afterwards (stateful quirk, reproduced for parity).
                    length = c.num("packedlength", length)
                if m == "top":
                    x = off
                elif m == "middle":
                    x = off + (plen - length) / 2
                elif m == "bottom":
                    x = off + (plen - length)
                else:
                    raise ValueError(f"unknown axial method {m!r} on {c.name!r}")
            if abs(x) < 1e-6:
                x = 0.0
        self._xrel[key] = x
        return x

    def x_abs(self, c: Component) -> float:
        key = id(c)
        if key not in self._xabs:
            self._xabs[key] = 0.0 if c.parent is None else self.x_abs(c.parent) + self.x_rel(c)
        return self._xabs[key]

    # ---------------------------------------------------------------- rings
    def outer_radius(self, c: Component) -> float:
        key = id(c)
        if key in self._ro:
            return self._ro[key]
        a, v = self._auto(c, "outerradius")
        par = c.parent
        if a and par is not None and self.inner_radius_at(par, 0.0) is not None:
            plen = self.length(par)
            pos1 = min(max(self.x_rel(c), 0.0), plen)
            pos2 = min(max(self.x_rel(c) + self.length(c), 0.0), plen)
            v = min(self.inner_radius_at(par, pos1), self.inner_radius_at(par, pos2))
        self._ro[key] = 0.0 if v is None else v
        return self._ro[key]

    def ring_inner_radius(self, c: Component) -> float:
        ro = self.outer_radius(c)
        if c.kind in (Kind.INNERTUBE, Kind.TUBECOUPLER, Kind.ENGINEBLOCK):
            return max(ro - c.num("thickness"), 0.0)
        if c.kind is Kind.CENTERINGRING:
            a, v = self._auto(c, "innerradius")
            if a:
                v = 0.0
                if c.parent is not None:
                    for sib in c.parent.children:
                        if sib.kind is not Kind.INNERTUBE:
                            continue
                        p1 = self.x_abs(c) - self.x_abs(sib)
                        p2 = p1 + self.length(c)
                        if p2 < 0 or p1 > self.length(sib):
                            continue
                        v = max(v, self.outer_radius(sib))
                v = min(v, ro)
            return v or 0.0
        return 0.0

    # ---------------------------------------------------------------- fins
    def body_radius_at_fin(self, c: Component) -> float:
        par = c.parent
        if par is not None and par.kind in SYMMETRIC:
            return self.radius_at(par, self.x_rel(c))
        return 0.0

    def tubefin_outer_radius(self, c: Component) -> float:
        a, v = self._auto(c, "radius")
        if a:
            rb = self.body_radius_at_fin(c)
            n = c.instance_count
            if n < 3:
                return rb
            s = math.sin(math.pi / n)
            return rb * s / (1 - s)
        return v or 0.0

    # ---------------------------------------------------------------- driver
    def run(self) -> None:
        issues = self.rocket.issues
        for c in self.rocket.root.walk():
            c.length = self.length(c)
            c.x_rel = self.x_rel(c)
            c.x_abs = self.x_abs(c)
            res: dict[str, float] = {}
            k = c.kind
            if k in SYMMETRIC:
                f, a, _fa, _aa = self._fore_aft(c)
                res["fore_radius"], res["aft_radius"] = f, a
            elif k in RINGS:
                res["outer_radius"] = self.outer_radius(c)
                res["inner_radius"] = self.ring_inner_radius(c)
            elif k is Kind.TUBEFINSET:
                res["outer_radius"] = self.tubefin_outer_radius(c)
                res["body_radius"] = self.body_radius_at_fin(c)
            elif k in FINS:
                res["body_radius"] = self.body_radius_at_fin(c)
            elif k in MASS_OBJECTS:
                res["packed_length"] = self.length(c)
                res["packed_radius"] = self.packed_radius(c)
            c.resolved = res
            self._check_stale(c, issues)

    def _check_stale(self, c: Component, issues: list[Issue]) -> None:
        """Report automatic values whose saved cache differs from the recomputed value."""
        r = c.resolved
        k = c.kind
        if k is Kind.BODYTUBE:
            pairs = [("radius", r["fore_radius"])]
        elif k is Kind.NOSECONE:
            pairs = [("aftradius", r["fore_radius"] if c.values.get("isflipped") else r["aft_radius"])]
        elif k is Kind.TRANSITION:
            pairs = [("foreradius", r["fore_radius"]), ("aftradius", r["aft_radius"])]
        elif k in RINGS:
            pairs = [("outerradius", r["outer_radius"]), ("innerradius", r["inner_radius"])]
        elif k is Kind.TUBEFINSET:
            pairs = [("radius", r["outer_radius"])]
        elif k in MASS_OBJECTS:
            pairs = [("packedradius", r["packed_radius"])]
        else:
            return
        for key, value in pairs:
            v = c.values.get(key)
            if isinstance(v, AutoValue) and v.cached is not None and abs(v.cached - value) > 1e-9:
                issues.append(
                    Issue(
                        Severity.INFO,
                        "ORK_STALE_AUTO",
                        f"{c.name}: automatic {key} saved as {v.cached:.6g} m resolves to {value:.6g} m;"
                        " using the resolved value",
                        c.id,
                    )
                )


def resolve(rocket: Rocket, *, emulate_or_stale_positions: bool = True) -> _Resolver:
    """Fill ``length``, ``x_rel``, ``x_abs`` and ``resolved`` on every component; returns the resolver so
    callers (mass model, meshing) can query profile radii consistently."""
    r = _Resolver(rocket, emulate_or_stale_positions)
    r.run()
    return r
