import numpy as np
import pytest
from PySide6.QtWidgets import QMessageBox

from stressaero.core.rocket import FINS, Kind
from stressaero.ui.app import main
from tests.oracle_data import find

pytestmark = pytest.mark.gui


def _open_dual(window):
    window.open_path(find("Dual parachute"))
    return window.ork


def test_open_ork_populates_tree_and_configurations(window):
    imp = _open_dual(window)
    assert window.tree.component_count() == 20
    assert window.config_combo.count() == len(imp.configurations) == 6


def test_tree_selection_highlights_and_inspects(window, qtbot):
    imp = _open_dual(window)
    nose = next(c for c in imp.rocket.root.walk() if c.kind is Kind.NOSECONE)
    window.tree.select(nose.id)
    qtbot.waitUntil(lambda: window.viewport.highlighted == nose.id)
    assert window.inspector.row_values()["Length"] == "283.2 mm"
    window.set_unit_system("us")
    assert window.inspector.row_values()["Length"] == "11.15 in"
    assert "Engineering (OpenRocket method)" in window.inspector.row_sources()["Mass"]


def test_viewport_pick_selects_fin_set(window, qtbot):
    imp = _open_dual(window)
    fins = next(c for c in imp.rocket.root.walk() if c.kind in FINS)
    mesh = window.viewport.meshes[fins.id]
    target = np.asarray(mesh.split_bodies()[0].center)
    window.viewport.plotter.camera_position = "xz"
    window.viewport.plotter.reset_camera()
    window.viewport.plotter.render()
    x, y = window.viewport.world_to_display(target)
    with qtbot.waitSignal(window.viewport.componentPicked, timeout=3000) as sig:
        window.viewport.pick_at(x, y)
    assert sig.args == [fins.id]
    assert window.tree.selected_id() == fins.id


def test_summary_shows_structure_mass(window):
    _open_dual(window)
    assert "1361 g" in window.summary.text()
    assert "Engineering (OpenRocket method)" in window.summary.toolTip()


def test_project_round_trip_restores_units_and_configuration(window, qtbot, tmp_path):
    imp = _open_dual(window)
    other = imp.configurations[3].id
    window.set_configuration(other)
    window.set_unit_system("us")
    target = tmp_path / "proj.saproj"
    window.save_project(target)
    from stressaero.ui.main_window import MainWindow

    w2 = MainWindow()
    qtbot.addWidget(w2)
    w2.open_path(target)
    assert w2.unit_system_name == "us"
    assert w2.current_config_id() == other
    w2.viewport.close()


def test_corrupt_project_shows_error_and_keeps_window(window, monkeypatch, tmp_path):
    _open_dual(window)
    calls = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: calls.append(a))
    bad = tmp_path / "bad.saproj"
    bad.write_bytes(b"not a project")
    window.open_path(bad)
    assert calls, "an error dialog must be shown"
    assert window.ork is not None and window.isVisible()


def test_selftest_entry_point(capsys):
    assert main(["--selftest"]) == 0
    assert "SELFTEST OK" in capsys.readouterr().out


def test_selftest_writes_result_file(tmp_path):
    out = tmp_path / "selftest.txt"
    assert main(["--selftest", "--selftest-out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("SELFTEST OK")
