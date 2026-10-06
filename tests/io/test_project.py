import json
import zipfile

import pytest

from stressaero.io.ork import OrkFormatError
from stressaero.io.project import PROJECT_SCHEMA_VERSION, Project, ProjectFormatError, load_project, save_project
from tests.oracle_data import find


def _project():
    path = find("Dual parachute")
    return Project(
        ork_name=path.name,
        ork_bytes=path.read_bytes(),
        selected_config_id="cfg-1",
        unit_system="us",
        unit_overrides={"length": "cm"},
        settings={"opacity": 0.3, "tags": ["a", "ü"]},
    )


def test_round_trip(tmp_path):
    p = _project()
    target = tmp_path / "rocket.saproj"
    save_project(p, target)
    q = load_project(target)
    assert q == p
    assert q.load_rocket().rocket.root.name == "Dual parachute deployment"


def test_schema_version_written(tmp_path):
    target = tmp_path / "a.saproj"
    save_project(_project(), target)
    with zipfile.ZipFile(target) as z:
        meta = json.loads(z.read("project.json"))
    assert meta["schema_version"] == PROJECT_SCHEMA_VERSION == 1


def test_newer_schema_rejected(tmp_path):
    target = tmp_path / "new.saproj"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("project.json", json.dumps({"schema_version": 99}))
    with pytest.raises(ProjectFormatError, match="newer version"):
        load_project(target)


def test_not_a_project(tmp_path):
    target = tmp_path / "x.saproj"
    target.write_bytes(b"not a zip")
    with pytest.raises(ProjectFormatError):
        load_project(target)


def test_corrupt_embedded_ork(tmp_path):
    p = _project()
    p.ork_bytes = b"garbage" * 10
    target = tmp_path / "c.saproj"
    save_project(p, target)
    q = load_project(target)
    with pytest.raises(OrkFormatError):
        q.load_rocket()


def test_failed_save_keeps_original(tmp_path, monkeypatch):
    target = tmp_path / "keep.saproj"
    save_project(_project(), target)
    before = target.read_bytes()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(zipfile.ZipFile, "writestr", boom)
    with pytest.raises(OSError):
        save_project(_project(), target)
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_project_without_rocket(tmp_path):
    target = tmp_path / "empty.saproj"
    save_project(Project(), target)
    assert load_project(target) == Project()
    with pytest.raises(ValueError, match="no rocket"):
        Project().load_rocket()
