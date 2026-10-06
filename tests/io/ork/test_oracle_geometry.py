"""Resolved geometry vs OpenRocket 24.12's own values for every component of every fixture file."""

import pytest

from stressaero.core.rocket import FINS
from stressaero.io.ork import load_ork
from tests.oracle_data import iter_cases

TOL = 1e-7
TOL_CANTED = 1e-4
SYMMETRIC_CLS = {"NoseCone", "BodyTube", "Transition"}
RING_CLS = {"InnerTube", "TubeCoupler", "EngineBlock", "CenteringRing", "Bulkhead"}


@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c.id)
def test_geometry_matches_openrocket(case):
    imp = load_ork(case.ork_path)
    comps = list(imp.rocket.root.walk())
    errors = []
    for c, ref in zip(comps, case.components, strict=True):
        canted = c.kind in FINS and abs(c.values.get("cant") or 0.0) > 0
        checks = {"x": (c.x_abs, ref["x"], TOL_CANTED if canted else TOL)}
        if ref["cls"] != "Rocket":  # OR's Rocket.getLength() is the configuration bounding span (Task 10)
            checks["length"] = (c.length, ref["length"], TOL)
        if ref["cls"] in SYMMETRIC_CLS:
            checks["fore"] = (c.resolved["fore_radius"], ref["fore"], TOL)
            checks["aft"] = (c.resolved["aft_radius"], ref["aft"], TOL)
        if ref["cls"] in RING_CLS:
            checks["ro"] = (c.resolved["outer_radius"], ref["ro"], TOL)
            checks["ri"] = (c.resolved["inner_radius"], ref["ri"], TOL)
        if ref["cls"] == "TubeFinSet":
            checks["ro"] = (c.resolved["outer_radius"], ref["ro"], TOL)
        if "bodyr" in ref:
            checks["bodyr"] = (c.resolved["body_radius"], ref["bodyr"], TOL)
        for key, (ours, theirs, tol) in checks.items():
            if abs(ours - theirs) > tol:
                errors.append(f"#{ref['index']} {ref['cls']} {ref['name']!r} {key}: ours={ours!r} OR={theirs!r}")
    assert errors == []
