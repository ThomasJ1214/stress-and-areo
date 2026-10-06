"""Flight configuration model: which motors fly in which mount, ignition, and recovery deployment."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MotorAssignment:
    mount_id: str
    manufacturer: str
    designation: str
    digest: str | None
    diameter: float
    length: float
    delay: float | None  # None = plugged
    ignition_event: str
    ignition_delay: float
    overhang: float
    count: int
    motor_type: str = "single"


@dataclass
class Deployment:
    device_id: str
    event: str
    altitude: float
    delay: float


@dataclass
class FlightConfiguration:
    id: str
    name: str | None
    is_default: bool
    active_stages: frozenset[int]
    motors: list[MotorAssignment] = field(default_factory=list)
    deployments: list[Deployment] = field(default_factory=list)

    def display_name(self) -> str:
        if self.name:
            return self.name
        if not self.motors:
            return "[No motors]"
        parts = []
        for m in self.motors:
            delay = "P" if m.delay is None else f"{m.delay:g}"
            prefix = f"{m.count}×" if m.count > 1 else ""
            parts.append(f"{prefix}{m.designation}-{delay}")
        return "[" + "; ".join(parts) + "]"
