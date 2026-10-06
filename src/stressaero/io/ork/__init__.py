"""OpenRocket ``.ork`` import: :func:`load_ork` returns a fully resolved rocket model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from stressaero.core.provenance import Issue
from stressaero.core.rocket import Rocket
from stressaero.io.ork.configs import FlightConfiguration, StoredSimulation, parse_configurations, parse_simulations
from stressaero.io.ork.container import Container, read_container
from stressaero.io.ork.errors import OrkFormatError
from stressaero.io.ork.parse import parse_document
from stressaero.io.ork.resolve import resolve

__all__ = ["OrkFormatError", "OrkImport", "load_ork"]


@dataclass
class OrkImport:
    rocket: Rocket
    format_version: str
    creator: str
    container: Container
    source_name: str
    configurations: list[FlightConfiguration] = field(default_factory=list)
    simulations: list[StoredSimulation] = field(default_factory=list)

    @property
    def issues(self) -> list[Issue]:
        return self.rocket.issues


def load_ork(source: Path | str | bytes, *, name: str | None = None,
             emulate_or_stale_positions: bool = True) -> OrkImport:
    """Read, parse and resolve an OpenRocket document from a path or bytes."""
    container = read_container(source)
    doc = parse_document(container.xml)
    resolve(doc.rocket, emulate_or_stale_positions=emulate_or_stale_positions)
    source_name = name or (Path(source).name if not isinstance(source, bytes | bytearray) else "rocket.ork")
    return OrkImport(rocket=doc.rocket, format_version=doc.version, creator=doc.creator, container=container,
                     source_name=source_name, configurations=parse_configurations(doc),
                     simulations=parse_simulations(doc, doc.rocket.issues))
