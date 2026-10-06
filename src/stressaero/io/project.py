"""Stress & Aero project files (``.saproj``).

A project is a ZIP archive containing ``project.json`` (schema-versioned settings) and ``assets/`` (the embedded
OpenRocket file, later CAD files and cached results). Saving is atomic: the archive is written to a temporary file
next to the target and moved into place only after it is complete.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from stressaero.io.ork import OrkImport, load_ork

PROJECT_SCHEMA_VERSION = 1
_META = "project.json"
_ASSETS = "assets/"


class ProjectFormatError(ValueError):
    """The file is not a readable Stress & Aero project."""


@dataclass
class Project:
    ork_name: str | None = None
    ork_bytes: bytes | None = None
    selected_config_id: str | None = None
    unit_system: str = "metric"
    unit_overrides: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def load_rocket(self) -> OrkImport:
        if not self.ork_bytes:
            raise ValueError("project has no rocket")
        return load_ork(self.ork_bytes, name=self.ork_name)


def save_project(project: Project, path: Path | str) -> None:
    path = Path(path)
    meta = asdict(project)
    meta.pop("ork_bytes")
    meta["schema_version"] = PROJECT_SCHEMA_VERSION
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(_META, json.dumps(meta, indent=2, ensure_ascii=False))
            if project.ork_bytes is not None:
                z.writestr(_ASSETS + _asset_name(project.ork_name), project.ork_bytes)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _asset_name(name: str | None) -> str:
    base = Path(name or "rocket.ork").name  # never allow directories in asset names
    return base or "rocket.ork"


def load_project(path: Path | str) -> Project:
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read(_META).decode("utf-8"))
            version = int(meta.get("schema_version", 0))
            if version > PROJECT_SCHEMA_VERSION:
                raise ProjectFormatError(
                    f"project was saved by a newer version of Stress & Aero (schema {version}); please update"
                )
            ork_name = meta.get("ork_name")
            ork_bytes = None
            if ork_name is not None:
                member = _ASSETS + _asset_name(ork_name)
                if member in z.namelist():
                    ork_bytes = z.read(member)
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
        if isinstance(e, ProjectFormatError):
            raise
        raise ProjectFormatError(f"not a Stress & Aero project: {e}") from e
    return Project(
        ork_name=ork_name,
        ork_bytes=ork_bytes,
        selected_config_id=meta.get("selected_config_id"),
        unit_system=meta.get("unit_system", "metric"),
        unit_overrides=dict(meta.get("unit_overrides", {})),
        settings=dict(meta.get("settings", {})),
    )
