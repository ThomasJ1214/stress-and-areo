"""Units and unit systems.

All engineering code works in SI (angles in radians). Conversion to display units happens only at the
UI/report boundary through a :class:`UnitSystem`.

Conversion: ``si = scale * value + offset``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class Dim(StrEnum):
    """Physical dimension / quantity kind used to choose a display unit."""

    LENGTH = "length"  # component dimensions
    DISTANCE = "distance"  # altitudes, ranges, trajectories
    MASS = "mass"
    TIME = "time"
    ANGLE = "angle"
    VELOCITY = "velocity"
    ACCELERATION = "acceleration"
    FORCE = "force"
    PRESSURE = "pressure"  # also stress
    DENSITY = "density"
    AREA = "area"
    VOLUME = "volume"
    TEMPERATURE = "temperature"
    INERTIA = "inertia"
    MOMENT = "moment"
    AREAL_DENSITY = "areal_density"
    LINEAR_DENSITY = "linear_density"
    ANGULAR_RATE = "angular_rate"
    IMPULSE = "impulse"
    FREQUENCY = "frequency"
    DIMENSIONLESS = "dimensionless"


@dataclass(frozen=True)
class Unit:
    symbol: str
    dim: Dim
    scale: float
    offset: float = 0.0


_IN = 0.0254
_FT = 0.3048
_LB = 0.45359237
_LBF = 4.4482216152605
_OZ = _LB / 16.0
_G0 = 9.80665

_DEFINITIONS: list[tuple[str, Dim, float, float, tuple[str, ...]]] = [
    # symbol, dim, scale, offset, ascii aliases
    ("m", Dim.LENGTH, 1.0, 0.0, ()),
    ("mm", Dim.LENGTH, 1e-3, 0.0, ()),
    ("cm", Dim.LENGTH, 1e-2, 0.0, ()),
    ("µm", Dim.LENGTH, 1e-6, 0.0, ("um",)),
    ("in", Dim.LENGTH, _IN, 0.0, ()),
    ("ft", Dim.LENGTH, _FT, 0.0, ()),
    ("mil", Dim.LENGTH, _IN * 1e-3, 0.0, ()),
    ("m ", Dim.DISTANCE, 1.0, 0.0, ()),  # distance variants are keyed with a trailing space; see _by_dim
    ("km", Dim.DISTANCE, 1e3, 0.0, ()),
    ("ft ", Dim.DISTANCE, _FT, 0.0, ()),
    ("mi", Dim.DISTANCE, 1609.344, 0.0, ()),
    ("kg", Dim.MASS, 1.0, 0.0, ()),
    ("g", Dim.MASS, 1e-3, 0.0, ()),
    ("lb", Dim.MASS, _LB, 0.0, ("lbm",)),
    ("oz", Dim.MASS, _OZ, 0.0, ()),
    ("slug", Dim.MASS, _LBF / _FT, 0.0, ()),
    ("s", Dim.TIME, 1.0, 0.0, ()),
    ("ms", Dim.TIME, 1e-3, 0.0, ()),
    ("min", Dim.TIME, 60.0, 0.0, ()),
    ("rad", Dim.ANGLE, 1.0, 0.0, ()),
    ("°", Dim.ANGLE, math.pi / 180.0, 0.0, ("deg",)),
    ("m/s", Dim.VELOCITY, 1.0, 0.0, ()),
    ("km/h", Dim.VELOCITY, 1000.0 / 3600.0, 0.0, ()),
    ("ft/s", Dim.VELOCITY, _FT, 0.0, ()),
    ("mph", Dim.VELOCITY, 0.44704, 0.0, ()),
    ("kn", Dim.VELOCITY, 1852.0 / 3600.0, 0.0, ()),
    ("m/s²", Dim.ACCELERATION, 1.0, 0.0, ("m/s^2",)),
    ("ft/s²", Dim.ACCELERATION, _FT, 0.0, ("ft/s^2",)),
    ("G", Dim.ACCELERATION, _G0, 0.0, ()),
    ("N", Dim.FORCE, 1.0, 0.0, ()),
    ("kN", Dim.FORCE, 1e3, 0.0, ()),
    ("lbf", Dim.FORCE, _LBF, 0.0, ()),
    ("Pa", Dim.PRESSURE, 1.0, 0.0, ()),
    ("kPa", Dim.PRESSURE, 1e3, 0.0, ()),
    ("MPa", Dim.PRESSURE, 1e6, 0.0, ()),
    ("GPa", Dim.PRESSURE, 1e9, 0.0, ()),
    ("bar", Dim.PRESSURE, 1e5, 0.0, ()),
    ("psi", Dim.PRESSURE, _LBF / _IN**2, 0.0, ()),
    ("ksi", Dim.PRESSURE, 1e3 * _LBF / _IN**2, 0.0, ()),
    ("psf", Dim.PRESSURE, _LBF / _FT**2, 0.0, ("lbf/ft^2",)),
    ("kg/m³", Dim.DENSITY, 1.0, 0.0, ("kg/m^3",)),
    ("g/cm³", Dim.DENSITY, 1000.0, 0.0, ("g/cm^3",)),
    ("lb/ft³", Dim.DENSITY, _LB / _FT**3, 0.0, ("lb/ft^3",)),
    ("lb/in³", Dim.DENSITY, _LB / _IN**3, 0.0, ("lb/in^3",)),
    ("m²", Dim.AREA, 1.0, 0.0, ("m^2",)),
    ("cm²", Dim.AREA, 1e-4, 0.0, ("cm^2",)),
    ("mm²", Dim.AREA, 1e-6, 0.0, ("mm^2",)),
    ("in²", Dim.AREA, _IN**2, 0.0, ("in^2",)),
    ("ft²", Dim.AREA, _FT**2, 0.0, ("ft^2",)),
    ("m³", Dim.VOLUME, 1.0, 0.0, ("m^3",)),
    ("cm³", Dim.VOLUME, 1e-6, 0.0, ("cm^3",)),
    ("L", Dim.VOLUME, 1e-3, 0.0, ()),
    ("in³", Dim.VOLUME, _IN**3, 0.0, ("in^3",)),
    ("K", Dim.TEMPERATURE, 1.0, 0.0, ()),
    ("°C", Dim.TEMPERATURE, 1.0, 273.15, ("degC",)),
    ("°F", Dim.TEMPERATURE, 5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0, ("degF",)),
    ("kg·m²", Dim.INERTIA, 1.0, 0.0, ("kg*m^2", "kg m^2")),
    ("g·cm²", Dim.INERTIA, 1e-7, 0.0, ("g*cm^2",)),
    ("lb·in²", Dim.INERTIA, _LB * _IN**2, 0.0, ("lb*in^2",)),
    ("lb·ft²", Dim.INERTIA, _LB * _FT**2, 0.0, ("lb*ft^2",)),
    ("N·m", Dim.MOMENT, 1.0, 0.0, ("N*m", "Nm")),
    ("lbf·ft", Dim.MOMENT, _LBF * _FT, 0.0, ("lbf*ft",)),
    ("lbf·in", Dim.MOMENT, _LBF * _IN, 0.0, ("lbf*in",)),
    ("kg/m²", Dim.AREAL_DENSITY, 1.0, 0.0, ("kg/m^2",)),
    ("g/m²", Dim.AREAL_DENSITY, 1e-3, 0.0, ("g/m^2",)),
    ("oz/yd²", Dim.AREAL_DENSITY, _OZ / 0.9144**2, 0.0, ("oz/yd^2",)),
    ("kg/m", Dim.LINEAR_DENSITY, 1.0, 0.0, ()),
    ("g/m", Dim.LINEAR_DENSITY, 1e-3, 0.0, ()),
    ("oz/ft", Dim.LINEAR_DENSITY, _OZ / _FT, 0.0, ()),
    ("rad/s", Dim.ANGULAR_RATE, 1.0, 0.0, ()),
    ("°/s", Dim.ANGULAR_RATE, math.pi / 180.0, 0.0, ("deg/s",)),
    ("rpm", Dim.ANGULAR_RATE, 2.0 * math.pi / 60.0, 0.0, ()),
    ("N·s", Dim.IMPULSE, 1.0, 0.0, ("N*s", "Ns")),
    ("lbf·s", Dim.IMPULSE, _LBF, 0.0, ("lbf*s",)),
    ("Hz", Dim.FREQUENCY, 1.0, 0.0, ()),
    ("—", Dim.DIMENSIONLESS, 1.0, 0.0, ("-",)),
    ("%", Dim.DIMENSIONLESS, 0.01, 0.0, ()),
]


def _build() -> dict[str, Unit]:
    table: dict[str, Unit] = {}
    for symbol, dim, scale, offset, aliases in _DEFINITIONS:
        unit = Unit(symbol.strip(), dim, scale, offset)
        key = symbol  # distance variants keep a distinct key ("m ", "ft ")
        if key in table:
            raise RuntimeError(f"duplicate unit symbol {key!r}")
        table[key] = unit
        for alias in aliases:
            table[alias] = unit
    return table


_TABLE = _build()
UNITS: Mapping[str, Unit] = MappingProxyType(_TABLE)


def _lookup(symbol: str, dim: Dim | None = None) -> Unit:
    if dim is Dim.DISTANCE and symbol + " " in _TABLE:
        return _TABLE[symbol + " "]
    try:
        unit = _TABLE[symbol]
    except KeyError:
        raise ValueError(f"unknown unit {symbol!r}") from None
    if dim is not None and unit.dim is not dim:
        alt = _TABLE.get(symbol + " ")
        if alt is not None and alt.dim is dim:
            return alt
        raise ValueError(f"unit {symbol!r} is a {unit.dim.value} unit, not {dim.value}")
    return unit


def to_si(value: float, unit: str) -> float:
    u = _lookup(unit)
    return u.scale * value + u.offset


def from_si(value_si: float, unit: str) -> float:
    u = _lookup(unit)
    return (value_si - u.offset) / u.scale


@dataclass(frozen=True)
class UnitSystem:
    """Preferred display unit per dimension."""

    name: str
    preferred: Mapping[Dim, str] = field(default_factory=dict)

    def unit(self, dim: Dim) -> Unit:
        return _lookup(self.preferred[dim], dim)

    def with_override(self, dim: Dim, symbol: str) -> UnitSystem:
        _lookup(symbol, dim)  # validates dimension
        new = dict(self.preferred)
        new[dim] = symbol
        return UnitSystem(self.name, MappingProxyType(new))

    def convert(self, value_si: float, dim: Dim) -> float:
        u = self.unit(dim)
        return (value_si - u.offset) / u.scale


def _system(name: str, mapping: dict[Dim, str]) -> UnitSystem:
    missing = [d for d in Dim if d not in mapping]
    if missing:
        raise RuntimeError(f"unit system {name} misses {missing}")
    for d, s in mapping.items():
        _lookup(s, d)
    return UnitSystem(name, MappingProxyType(mapping))


METRIC = _system(
    "metric",
    {
        Dim.LENGTH: "mm",
        Dim.DISTANCE: "m",
        Dim.MASS: "g",
        Dim.TIME: "s",
        Dim.ANGLE: "°",
        Dim.VELOCITY: "m/s",
        Dim.ACCELERATION: "m/s²",
        Dim.FORCE: "N",
        Dim.PRESSURE: "kPa",
        Dim.DENSITY: "kg/m³",
        Dim.AREA: "cm²",
        Dim.VOLUME: "cm³",
        Dim.TEMPERATURE: "°C",
        Dim.INERTIA: "kg·m²",
        Dim.MOMENT: "N·m",
        Dim.AREAL_DENSITY: "g/m²",
        Dim.LINEAR_DENSITY: "g/m",
        Dim.ANGULAR_RATE: "°/s",
        Dim.IMPULSE: "N·s",
        Dim.FREQUENCY: "Hz",
        Dim.DIMENSIONLESS: "—",
    },
)

US_CUSTOMARY = _system(
    "us",
    {
        Dim.LENGTH: "in",
        Dim.DISTANCE: "ft",
        Dim.MASS: "oz",
        Dim.TIME: "s",
        Dim.ANGLE: "°",
        Dim.VELOCITY: "ft/s",
        Dim.ACCELERATION: "ft/s²",
        Dim.FORCE: "lbf",
        Dim.PRESSURE: "psi",
        Dim.DENSITY: "lb/ft³",
        Dim.AREA: "in²",
        Dim.VOLUME: "in³",
        Dim.TEMPERATURE: "°F",
        Dim.INERTIA: "lb·in²",
        Dim.MOMENT: "lbf·ft",
        Dim.AREAL_DENSITY: "oz/yd²",
        Dim.LINEAR_DENSITY: "oz/ft",
        Dim.ANGULAR_RATE: "°/s",
        Dim.IMPULSE: "lbf·s",
        Dim.FREQUENCY: "Hz",
        Dim.DIMENSIONLESS: "—",
    },
)

SYSTEMS: Mapping[str, UnitSystem] = MappingProxyType({"metric": METRIC, "us": US_CUSTOMARY})


def format_number(value: float, sig: int = 4) -> str:
    """Format with ``sig`` significant figures, keeping trailing zeros; scientific outside [1e-4, 1e6)."""
    if value == 0 or not math.isfinite(value):
        return "0" if value == 0 else str(value)
    mag = abs(value)
    if mag >= 1e6 or mag < 1e-4:
        return f"{value:.{sig - 1}e}"
    rounded = float(f"{value:.{sig - 1}e}")
    exponent = math.floor(math.log10(abs(rounded)))
    decimals = max(0, sig - 1 - exponent)
    return f"{rounded:.{decimals}f}"


def format_quantity(value_si: float, dim: Dim, system: UnitSystem, sig: int = 4) -> str:
    unit = system.unit(dim)
    shown = (value_si - unit.offset) / unit.scale
    if dim is Dim.DIMENSIONLESS and unit.symbol == "—":
        return format_number(shown, sig)
    return f"{format_number(shown, sig)} {unit.symbol}"
