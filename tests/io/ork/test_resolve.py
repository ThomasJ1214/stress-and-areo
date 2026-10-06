import pytest

from stressaero.core.rocket import Kind
from stressaero.io.ork import load_ork
from tests.oracle_data import find


def test_dual_parachute_stale_auto_radius_recomputed():
    imp = load_ork(find("Dual parachute"))
    comps = list(imp.rocket.root.walk())
    tube = comps[5]
    assert tube.kind is Kind.BODYTUBE
    assert tube.resolved["fore_radius"] == pytest.approx(0.028321, abs=1e-9)
    stale = [i for i in imp.issues if i.code == "ORK_STALE_AUTO" and i.component_id == tube.id]
    assert stale, "stale auto radius must be reported"


def test_dual_parachute_drogue_position_matches_openrocket_quirk():
    comps = list(load_ork(find("Dual parachute")).rocket.root.walk())
    drogue = comps[10]
    assert drogue.kind is Kind.PARACHUTE
    assert drogue.x_abs == pytest.approx(0.842975869, abs=1e-7)


def test_stale_mass_object_position_quirk_in_format_1_8_file():
    # In the 1.8 copy the saved packed length is stale: OpenRocket positions the drogue with the saved length
    # (0.832485) while the self-consistent geometry puts it at 0.842976 (research: ork-format, AUTO DIMENSIONS).
    path = find("Dual parachute", "v2309")
    emulated = list(load_ork(path).rocket.root.walk())[10]
    consistent = list(load_ork(path, emulate_or_stale_positions=False).rocket.root.walk())[10]
    assert emulated.x_abs == pytest.approx(0.832485, abs=1e-7)
    assert consistent.x_abs == pytest.approx(0.842976, abs=1e-6)


def test_load_from_bytes_with_name():
    path = find("A simple model rocket")
    imp = load_ork(path.read_bytes(), name=path.name)
    assert imp.container.kind == "zip"
    assert imp.format_version
    assert imp.source_name == path.name
