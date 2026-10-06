"""OR-compatible mass model vs OpenRocket 24.12's own values on every fixture file."""

import pytest

from stressaero.core.rocket import FINS
from stressaero.io.ork import load_ork
from stressaero.physics.massmodel import component_mass_cg, reference_length, rocket_length, structure_mass
from tests.oracle_data import iter_cases

MASS_REL, MASS_ABS = 1e-5, 1e-9
CG_TOL = 1e-5
CG_TOL_CANTED = 1e-4  # OpenRocket offsets the root curve of canted fins (research: ≤3e-5 m)
KNOWN_GAPS = {"logo_rocket"}  # freeform fin extending beyond its parent's end (research: known gap)

CASES = list(iter_cases())


def _close_mass(ours, theirs):
    return abs(ours - theirs) <= MASS_ABS + MASS_REL * abs(theirs)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_component_mass_and_cg(case):
    if any(g in case.ork_path.name for g in KNOWN_GAPS):
        pytest.xfail("fin beyond parent end: known gap")
    imp = load_ork(case.ork_path)
    errors = []
    for c, ref in zip(imp.rocket.root.walk(), case.components, strict=True):
        m, cgx = component_mass_cg(c)
        tol = CG_TOL_CANTED if (c.kind in FINS and c.values.get("cant")) else CG_TOL
        if not _close_mass(m, ref["compmass"]):
            errors.append(f"#{ref['index']} {ref['cls']} {ref['name']!r} mass ours={m!r} OR={ref['compmass']!r}")
        if ref["compmass"] > 0 and abs(cgx - ref["compcgx"]) > tol:
            errors.append(f"#{ref['index']} {ref['cls']} {ref['name']!r} cgx ours={cgx!r} OR={ref['compcgx']!r}")
    assert errors == []


@pytest.mark.parametrize("case", [c for c in CASES if c.sims], ids=lambda c: c.id)
def test_configuration_mass_cg_reference_and_length(case):
    if any(g in case.ork_path.name for g in KNOWN_GAPS):
        pytest.xfail("fin beyond parent end: known gap")
    imp = load_ork(case.ork_path)
    by_id = {c.id: c for c in imp.configurations}
    default = next((c for c in imp.configurations if c.is_default), None)
    errors = []
    for sim, ref in zip(imp.simulations, case.sims, strict=True):
        cfg = by_id.get(sim.config_id, default)
        mp = structure_mass(imp.rocket, cfg)
        if not _close_mass(mp.mass, ref["structMass"]):
            errors.append(f"sim {ref['index']} structMass ours={mp.mass!r} OR={ref['structMass']!r}")
        if abs(mp.cg_x - ref["structCG"]) > CG_TOL:
            errors.append(f"sim {ref['index']} structCG ours={mp.cg_x!r} OR={ref['structCG']!r}")
        if abs(reference_length(imp.rocket, cfg) - ref["refLen"]) > 1e-9:
            errors.append(f"sim {ref['index']} refLen ours={reference_length(imp.rocket, cfg)!r} OR={ref['refLen']!r}")
        if abs(rocket_length(imp.rocket, cfg) - ref["length"]) > 1e-7:
            errors.append(f"sim {ref['index']} length ours={rocket_length(imp.rocket, cfg)!r} OR={ref['length']!r}")
    assert errors == []
