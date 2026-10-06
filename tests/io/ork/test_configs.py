import math

import numpy as np
import pytest

from stressaero.core.provenance import Tier
from stressaero.io.ork import load_ork
from tests.oracle_data import find


@pytest.fixture(scope="module")
def dual():
    return load_ork(find("Dual parachute"))


def test_dual_parachute_configurations(dual):
    assert len(dual.configurations) == 6
    default = [c for c in dual.configurations if c.is_default]
    assert len(default) == 1
    designations = {m.designation for c in dual.configurations for m in c.motors}
    assert "J570W" in designations
    j570 = next(m for c in dual.configurations for m in c.motors if m.designation == "J570W")
    assert j570.manufacturer == "AeroTech"
    assert j570.digest
    assert j570.diameter == pytest.approx(0.038, abs=1e-3)
    assert j570.count == 1


def test_dual_parachute_recovery(dual):
    cfg = dual.configurations[0]
    events = {d.event for d in cfg.deployments}
    assert events == {"apogee", "altitude"}
    main = next(d for d in cfg.deployments if d.event == "altitude")
    assert main.altitude == pytest.approx(152.4)


def test_dual_parachute_stored_simulation(dual):
    sim = dual.simulations[2]
    assert sim.summary["maxaltitude"] == pytest.approx(2223.846, abs=1e-3)
    assert sim.provenance.tier is Tier.OR_STORED
    b = sim.branches[0]
    assert "altitude" in b.columns and "time" in b.columns
    assert isinstance(b.columns["altitude"], np.ndarray)
    assert np.nanmax(b.columns["altitude"]) == pytest.approx(2223.846, abs=2e-3)
    assert any(kind == "apogee" for _t, kind in b.events)
    cond = sim.conditions
    assert 0 <= cond["launchrodangle"] < math.radians(30)  # converted from degrees
    assert cond["launchrodlength"] > 0
    assert sim.config_id in {c.id for c in dual.configurations}


def test_display_name_for_unnamed_config(dual):
    cfg = next(c for c in dual.configurations if any(m.designation == "J570W" for m in c.motors))
    assert "J570W" in cfg.display_name()


def test_all_stages_active_for_old_files():
    imp = load_ork(find("simplerocket", "v2412"))
    assert imp.configurations, "format 1.2 motor configurations must be read"
    for c in imp.configurations:
        assert 0 in c.active_stages


def test_cluster_motor_count():
    imp = load_ork(find("Clustered motors"))
    counts = {m.count for c in imp.configurations for m in c.motors}
    assert max(counts) > 1


SIM_XML = """<?xml version="1.0" encoding="utf-8"?>
<openrocket version="1.10" creator="test"><rocket><name>R</name>
<motorconfiguration configid="c1" default="true"><stage number="0" active="true"/></motorconfiguration>
<subcomponents><stage><name>S</name><subcomponents>
<bodytube><name>T</name><length>0.5</length><thickness>0.002</thickness><radius>0.03</radius></bodytube>
</subcomponents></stage></subcomponents></rocket>
<simulations><simulation status="loaded"><name>Sim</name><conditions><configid>c1</configid>
<launchrodlength>1.0</launchrodlength><launchrodangle>5.0</launchrodangle></conditions>
<flightdata maxaltitude="10.0"><databranch name="B" types="Time,Höhe">
<datapoint>0,0</datapoint><datapoint>1,10</datapoint></databranch></flightdata>
</simulation></simulations></openrocket>""".encode()


def test_unknown_localized_column_kept_with_issue():
    imp = load_ork(SIM_XML)
    b = imp.simulations[0].branches[0]
    assert list(b.columns["Höhe"]) == [0.0, 10.0]
    assert "time" in b.columns
    assert any(i.code == "ORK_UNKNOWN_COLUMN" for i in imp.issues)
    assert imp.simulations[0].conditions["launchrodangle"] == pytest.approx(math.radians(5.0))
