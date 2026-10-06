import math

import pytest

from stressaero.core.provenance import Tier
from stressaero.io.ork import load_ork
from stressaero.physics.massmodel import component_mass_cg, structure_mass
from tests.oracle_data import find

TUBE = b"""<?xml version="1.0" encoding="utf-8"?>
<openrocket version="1.10" creator="test"><rocket><name>R</name>
<motorconfiguration configid="c1" default="true"><stage number="0" active="true"/></motorconfiguration>
<subcomponents><stage><name>S</name><subcomponents>
<bodytube><name>T</name><material type="bulk" density="2700">Aluminium</material>
<length>1.0</length><thickness>0.002</thickness><radius>0.05</radius></bodytube>
</subcomponents></stage></subcomponents></rocket></openrocket>"""


def test_aluminium_tube_exact():
    imp = load_ork(TUBE)
    tube = list(imp.rocket.root.walk())[2]
    m, cg = component_mass_cg(tube)
    assert m == pytest.approx(2700 * math.pi * (0.05**2 - 0.048**2) * 1.0, rel=1e-12)
    assert cg == pytest.approx(0.5)
    mp = structure_mass(imp.rocket, imp.configurations[0])
    assert mp.mass == pytest.approx(m, rel=1e-12)
    assert mp.cg_x == pytest.approx(0.5)
    assert mp.provenance.tier is Tier.ENGINEERING_OR
    assert mp.provenance.method_id == "mass.or_compat.24_12"


def test_dual_parachute_structure_mass():
    imp = load_ork(find("Dual parachute"))
    cfg = next(c for c in imp.configurations if c.is_default)
    assert structure_mass(imp.rocket, cfg).mass == pytest.approx(1.36077711, rel=1e-6)
