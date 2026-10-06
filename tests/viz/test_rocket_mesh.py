import math

import numpy as np
import pytest

from stressaero.core.rocket import FINS, Kind
from stressaero.io.ork import load_ork
from stressaero.viz.rocket_mesh import component_mesh, rocket_meshes
from tests.oracle_data import find

TUBE = b"""<?xml version="1.0" encoding="utf-8"?>
<openrocket version="1.10" creator="test"><rocket><name>R</name>
<motorconfiguration configid="c1" default="true"><stage number="0" active="true"/></motorconfiguration>
<subcomponents><stage><name>S</name><subcomponents>
<nosecone><name>N</name><length>0.3</length><thickness>0.002</thickness><shape>ogive</shape><aftradius>0.05</aftradius></nosecone>
<bodytube><name>T</name><length>1.0</length><thickness>0.002</thickness><radius>0.05</radius></bodytube>
</subcomponents></stage></subcomponents></rocket></openrocket>"""


@pytest.fixture(scope="module")
def simple():
    return list(load_ork(TUBE).rocket.root.walk())


def test_body_tube_closed_shell_volume(simple):
    tube = simple[3]
    mesh = component_mesh(tube)
    exact = math.pi * (0.05**2 - 0.048**2) * 1.0
    assert mesh.is_manifold
    assert mesh.volume == pytest.approx(exact, rel=1e-3)
    assert mesh.bounds[0] == pytest.approx(0.3) and mesh.bounds[1] == pytest.approx(1.3)


def test_nose_cone_bounds(simple):
    nose = simple[2]
    mesh = component_mesh(nose)
    assert mesh.bounds[0] == pytest.approx(0.0, abs=1e-9)
    assert mesh.bounds[1] == pytest.approx(0.3, abs=1e-9)
    assert max(abs(mesh.bounds[2]), mesh.bounds[3]) == pytest.approx(0.05, rel=1e-3)
    assert set(np.unique(mesh.cell_data["component_index"])) == {2}


def test_dual_parachute_fins():
    imp = load_ork(find("Dual parachute"))
    fins = next(c for c in imp.rocket.root.walk() if c.kind in FINS)
    mesh = component_mesh(fins)
    assert len(mesh.split_bodies()) == 3
    radial = np.hypot(mesh.points[:, 1], mesh.points[:, 2]).max()
    assert radial == pytest.approx(fins.resolved["body_radius"] + fins.num("height"), rel=1e-3)
    assert mesh.field_data["internal"][0] == 0


def test_rocket_meshes_cover_active_components():
    imp = load_ork(find("Dual parachute"))
    cfg = next(c for c in imp.configurations if c.is_default)
    meshes = rocket_meshes(imp.rocket, cfg)
    kinds = {imp.rocket.by_id[i].kind for i in meshes}
    assert Kind.NOSECONE in kinds and Kind.TRAPEZOIDFINSET in kinds and Kind.PARACHUTE in kinds
    assert all(imp.rocket.by_id[i].kind not in (Kind.ROCKET, Kind.STAGE) for i in meshes)
    internal = [i for i, m in meshes.items() if m.field_data["internal"][0] == 1]
    assert internal, "internal components flagged"


def test_pod_instances_are_offset_radially():
    imp = load_ork(find("Pods--airframes"))
    pods = [c for c in imp.rocket.root.walk() if c.kind is Kind.PODSET]
    assert pods
    child = next(ch for ch in pods[0].walk() if ch.kind is Kind.BODYTUBE)
    mesh = component_mesh(child)
    assert len(mesh.split_bodies()) == pods[0].instance_count
    centers = [r.center for r in mesh.split_bodies()]
    radii = [math.hypot(c[1], c[2]) for c in centers]
    assert min(radii) > 0.01  # every pod copy is off-axis


def test_inactive_stage_excluded():
    import dataclasses

    imp = load_ork(find("Two stage high power"))
    full_cfg = next(c for c in imp.configurations if len(c.active_stages) == 2)
    sustainer = dataclasses.replace(full_cfg, active_stages=frozenset({0}))
    full = rocket_meshes(imp.rocket, full_cfg)
    sust = rocket_meshes(imp.rocket, sustainer)
    booster_ids = {c.id for c in imp.rocket.root.walk() if c.stage_index == 1}
    assert booster_ids & set(full)
    assert not booster_ids & set(sust)
