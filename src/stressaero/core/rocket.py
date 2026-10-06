"""Rocket component model (mirrors OpenRocket's component tree).

Values are SI with angles in radians. ``values`` holds the typed file values; fields filled by
:func:`stressaero.io.ork.resolve.resolve` (``length``, ``x_rel``, ``x_abs``, ``resolved``) hold the
re-derived geometry, which is what all engines use (stored ``auto`` values may be stale).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from stressaero.core.provenance import Issue


class Kind(StrEnum):
    ROCKET = "rocket"
    STAGE = "stage"
    PARALLELSTAGE = "parallelstage"
    BOOSTERSET = "boosterset"
    PODSET = "podset"
    NOSECONE = "nosecone"
    BODYTUBE = "bodytube"
    TRANSITION = "transition"
    TRAPEZOIDFINSET = "trapezoidfinset"
    ELLIPTICALFINSET = "ellipticalfinset"
    FREEFORMFINSET = "freeformfinset"
    TUBEFINSET = "tubefinset"
    LAUNCHLUG = "launchlug"
    RAILBUTTON = "railbutton"
    INNERTUBE = "innertube"
    TUBECOUPLER = "tubecoupler"
    ENGINEBLOCK = "engineblock"
    CENTERINGRING = "centeringring"
    BULKHEAD = "bulkhead"
    MASSCOMPONENT = "masscomponent"
    SHOCKCORD = "shockcord"
    PARACHUTE = "parachute"
    STREAMER = "streamer"


SYMMETRIC = frozenset({Kind.NOSECONE, Kind.BODYTUBE, Kind.TRANSITION})
FINS = frozenset({Kind.TRAPEZOIDFINSET, Kind.ELLIPTICALFINSET, Kind.FREEFORMFINSET})
RINGS = frozenset({Kind.ENGINEBLOCK, Kind.INNERTUBE, Kind.TUBECOUPLER, Kind.BULKHEAD, Kind.CENTERINGRING})
MASS_OBJECTS = frozenset({Kind.MASSCOMPONENT, Kind.SHOCKCORD, Kind.PARACHUTE, Kind.STREAMER})
RECOVERY = frozenset({Kind.PARACHUTE, Kind.STREAMER})
ASSEMBLIES = frozenset({Kind.ROCKET, Kind.STAGE, Kind.BOOSTERSET, Kind.PARALLELSTAGE, Kind.PODSET})
STAGES = frozenset({Kind.STAGE, Kind.BOOSTERSET, Kind.PARALLELSTAGE})
MOUNTS = frozenset({Kind.BODYTUBE, Kind.INNERTUBE})
EXTERNAL = frozenset(SYMMETRIC | FINS | {Kind.TUBEFINSET, Kind.LAUNCHLUG, Kind.RAILBUTTON})

FILLED = "filled"


@dataclass(frozen=True)
class AutoValue:
    """A value marked ``auto`` in the file; ``cached`` is the (possibly stale) number saved after it."""

    cached: float | None


@dataclass
class Material:
    name: str
    kind: str  # "bulk" (kg/m³) | "surface" (kg/m²) | "line" (kg/m)
    density: float
    group: str = "Custom"


@dataclass
class MassOverride:
    mass: float | None = None
    cg: float | None = None
    cd: float | None = None
    mass_sub: bool = False
    cg_sub: bool = False
    cd_sub: bool = False


@dataclass
class AxialPlacement:
    method: str = "after"  # after | top | middle | bottom | absolute
    offset: float = 0.0


@dataclass(eq=False)
class Component:
    id: str
    kind: Kind
    name: str
    parent: Component | None = field(default=None, repr=False)
    children: list[Component] = field(default_factory=list, repr=False)
    path: str = ""
    placement: AxialPlacement = field(default_factory=AxialPlacement)
    values: dict[str, Any] = field(default_factory=dict)
    attrs: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    multi: dict[str, list[tuple[dict[str, str], str]]] = field(default_factory=dict, repr=False)
    material: Material | None = None
    fillet_material: Material | None = None
    line_material: Material | None = None
    override: MassOverride = field(default_factory=MassOverride)
    finish_roughness: float | None = None
    instance_count: int = 1
    fin_points: list[tuple[float, float]] | None = None
    motor_mount: dict[str, Any] | None = None
    deploy_overrides: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    separation_overrides: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    appearance: dict[str, Any] | None = field(default=None, repr=False)
    preset: dict[str, str] | None = field(default=None, repr=False)
    stage_index: int | None = None
    # --- resolved geometry (filled by io.ork.resolve) ---
    length: float = 0.0
    x_rel: float = 0.0
    x_abs: float = 0.0
    resolved: dict[str, float] = field(default_factory=dict)

    def walk(self) -> Iterator[Component]:
        """Pre-order traversal including self (same order as OpenRocket's component iterator)."""
        yield self
        for ch in self.children:
            yield from ch.walk()

    def ancestors(self) -> Iterator[Component]:
        c = self.parent
        while c is not None:
            yield c
            c = c.parent

    def num(self, key: str, default: float = 0.0) -> float:
        v = self.values.get(key)
        if isinstance(v, AutoValue):
            return default if v.cached is None else v.cached
        return default if v is None or isinstance(v, str) else float(v)


@dataclass
class Rocket:
    root: Component
    by_id: dict[str, Component]
    issues: list[Issue] = field(default_factory=list)
    stage_count: int = 1
    flight_config_entries: list[dict[str, Any]] = field(default_factory=list)

    def components(self) -> Iterator[Component]:
        return self.root.walk()
