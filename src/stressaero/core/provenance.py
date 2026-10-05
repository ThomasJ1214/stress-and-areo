"""Provenance of results: which fidelity tier and method produced a number, and where it is valid.

This is the mechanism behind the spec's honesty rules (§4.2): every engineering result carries a
:class:`Provenance`, and the UI shows its badge next to the value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Tier(StrEnum):
    ESTIMATE = "estimate"
    OR_STORED = "or_stored"
    ENGINEERING_OR = "engineering_or"
    ENGINEERING = "engineering"
    GEOMETRIC = "geometric"
    CFD = "cfd"
    FEA = "fea"

    @property
    def badge(self) -> str:
        return _BADGES[self]


_BADGES = {
    Tier.ESTIMATE: "Estimate",
    Tier.OR_STORED: "OpenRocket stored result",
    Tier.ENGINEERING_OR: "Engineering (OpenRocket method)",
    Tier.ENGINEERING: "Engineering",
    Tier.GEOMETRIC: "Geometry-based",
    Tier.CFD: "CFD (SU2)",
    Tier.FEA: "FEA (CalculiX)",
}


@dataclass(frozen=True)
class ValidityBand:
    """Range of flow conditions where a method is considered valid. ``None`` = unconstrained."""

    mach: tuple[float, float] | None = None
    aoa_rad: tuple[float, float] | None = None
    note: str = ""

    def contains(self, mach: float | None = None, aoa_rad: float | None = None) -> bool:
        if mach is not None and self.mach is not None and not (self.mach[0] <= mach <= self.mach[1]):
            return False
        if aoa_rad is not None and self.aoa_rad is not None and not (
            self.aoa_rad[0] <= abs(aoa_rad) <= self.aoa_rad[1]
        ):
            return False
        return True


@dataclass(frozen=True)
class Provenance:
    tier: Tier
    method_id: str
    method_version: str = "1"
    references: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    validity: ValidityBand | None = None
    interpolated: bool = False

    def label(self) -> str:
        return self.tier.badge + (" · interpolated" if self.interpolated else "")


class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2


@dataclass(frozen=True)
class Issue:
    """A structured, user-visible message (import warnings, validity flags, solver notes)."""

    severity: Severity
    code: str
    message: str
    component_id: str | None = None
