"""Flight configurations (motors, ignition, recovery deployment) and stored simulations from ``.ork`` files.

Stored simulation data is OpenRocket's own output (rounded to 3 decimals / 4 significant figures, random wind
turbulence seed, instantaneous parachute opening); it is exposed with ``Tier.OR_STORED`` and never used as
ground truth. Column names are mapped to OpenRocket 26.xx stable save keys (``time``, ``altitude``,
``velocity_total`` …) from English display names, 26.xx keys and symbol-suffixed names; unknown (e.g.
localised) names are kept verbatim and reported.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from stressaero.core.configuration import Deployment, FlightConfiguration, MotorAssignment
from stressaero.core.provenance import Issue, Provenance, Severity, Tier
from stressaero.core.rocket import RECOVERY, Component, Kind
from stressaero.io.ork.parse import ParsedDocument, fnum

DEG = math.pi / 180.0

# English display names (OpenRocket 23.09/24.12 messages.properties) -> 26.xx save keys
_DISPLAY_TO_KEY = {
    "Time": "time",
    "Altitude": "altitude",
    "Altitude above sea level": "altitude_above_sea",
    "Vertical velocity": "velocity_z",
    "Total velocity": "velocity_total",
    "Vertical acceleration": "acceleration_z",
    "Total acceleration": "acceleration_total",
    "Position East of launch": "position_x",
    "Position North of launch": "position_y",
    "Lateral distance": "position_xy",
    "Lateral direction": "position_direction",
    "Lateral velocity": "velocity_xy",
    "Lateral acceleration": "acceleration_xy",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Angle of attack": "aoa",
    "Roll rate": "roll_rate",
    "Pitch rate": "pitch_rate",
    "Yaw rate": "yaw_rate",
    "Vertical orientation (zenith)": "orientation_theta",
    "Lateral orientation (azimuth)": "orientation_phi",
    "Mass": "mass",
    "Motor mass": "motor_mass",
    "Propellant mass": "motor_mass",
    "Longitudinal moment of inertia": "longitudinal_inertia",
    "Rotational moment of inertia": "rotational_inertia",
    "Gravitational acceleration": "gravity",
    "Gravity": "gravity",
    "CP location": "cp_location",
    "CG location": "cg_location",
    "Stability margin calibers": "stability",
    "Thrust": "thrust_force",
    "Thrust-to-weight ratio": "thrust_weight_ratio",
    "Drag force": "drag_force",
    "Drag coefficient": "drag_coeff",
    "Friction drag coefficient": "friction_drag_coeff",
    "Pressure drag coefficient": "pressure_drag_coeff",
    "Base drag coefficient": "base_drag_coeff",
    "Axial drag coefficient": "axial_drag_coeff",
    "Normal force coefficient": "normal_force_coeff",
    "Pitch moment coefficient": "pitch_moment_coeff",
    "Yaw moment coefficient": "yaw_moment_coeff",
    "Side force coefficient": "side_force_coeff",
    "Roll moment coefficient": "roll_moment_coeff",
    "Roll forcing coefficient": "roll_forcing_coeff",
    "Roll damping coefficient": "roll_damping_coeff",
    "Pitch damping coefficient": "pitch_damping_moment_coeff",
    "Yaw damping coefficient": "yaw_damping_moment_coeff",
    "Coriolis acceleration": "coriolis_acceleration",
    "Reference length": "reference_length",
    "Reference area": "reference_area",
    "Wind velocity": "wind_velocity",
    "Wind speed": "wind_velocity",
    "Wind direction": "wind_direction",
    "Air temperature": "air_temperature",
    "Air pressure": "air_pressure",
    "Air density": "air_density",
    "Speed of sound": "speed_of_sound",
    "Mach number": "mach_number",
    "Reynolds number": "reynolds_number",
    "Simulation time step": "time_step",
    "Computation time": "computation_time",
    "Position upwind": "position_upwind",
    "Position parallel to wind": "position_parallel",
    # 26.xx symbol-suffixed display names
    "Drag coefficient (CD)": "drag_coeff",
    "Friction drag coefficient (CD_friction)": "friction_drag_coeff",
    "Pressure drag coefficient (CD_pressure)": "pressure_drag_coeff",
    "Base drag coefficient (CD_base)": "base_drag_coeff",
    "Axial drag coefficient (CA)": "axial_drag_coeff",
    "Normal force coefficient (CN)": "normal_force_coeff",
    "Normal force coefficient derivative (CNα)": "cna",
    "Pitch moment coefficient (Cm)": "pitch_moment_coeff",
    "Damping ratio": "damping_ratio",
    "Natural frequency": "natural_frequency",
    "Damping moment coefficient": "damping_moment_coeff",
    "Damping moment coefficient (aerodynamic)": "damping_moment_coeff_aerodynamic",
    "Damping moment coefficient (propulsive)": "damping_moment_coeff_propulsive",
    "Corrective moment coefficient": "corrective_moment_coeff",
}
SAVE_KEYS = frozenset(_DISPLAY_TO_KEY.values()) | {
    "acceleration_x",
    "acceleration_y",
    "acceleration_bodyx",
    "acceleration_bodyy",
    "acceleration_bodyz",
    "thrust_correction",
}


def column_key(name: str) -> str | None:
    """Canonical save key for a stored column name, or None if unknown."""
    if name in SAVE_KEYS:
        return name
    return _DISPLAY_TO_KEY.get(name)


@dataclass
class DataBranch:
    name: str
    columns: dict[str, np.ndarray]
    events: list[tuple[float, str]]


@dataclass
class StoredSimulation:
    name: str
    config_id: str | None
    conditions: dict[str, Any]
    summary: dict[str, float]
    branches: list[DataBranch]
    warnings: list[str] = field(default_factory=list)
    provenance: Provenance = field(
        default_factory=lambda: Provenance(
            Tier.OR_STORED,
            "openrocket.stored_simulation",
            warnings=("Rounded to 3 decimals; random turbulence seed; instantaneous parachute opening",),
        )
    )


def _multiplicity(c: Component) -> int:
    n = c.instance_count if c.kind is Kind.INNERTUBE else 1
    for a in c.ancestors():
        if a.kind in (Kind.PODSET, Kind.PARALLELSTAGE, Kind.BOOSTERSET):
            n *= a.instance_count
    return n


def parse_configurations(doc: ParsedDocument) -> list[FlightConfiguration]:
    rocket = doc.rocket
    comps = list(rocket.root.walk())
    mounts = [c for c in comps if c.motor_mount is not None]
    recovery = [c for c in comps if c.kind in RECOVERY]
    entries = list(rocket.flight_config_entries)
    if not entries:  # very old files: configurations implied by motor ids
        ids = []
        for m in mounts:
            ids += [i for i in m.motor_mount["motors"] if i not in ids]
        entries = [{"id": i, "default": n == 0, "name": None, "stages": {}} for n, i in enumerate(ids)]
    configs = []
    for fc in entries:
        fid = fc["id"]
        stages = fc.get("stages") or {}
        if stages:
            active = frozenset(n for n, on in stages.items() if on) or frozenset({0})
        else:
            active = frozenset(range(rocket.stage_count))
        motors = []
        for m in mounts:
            mm = m.motor_mount
            d = mm["motors"].get(fid)
            if d is None:
                continue
            ig = mm["ignition_overrides"].get(fid, {})
            delay_raw = d.get("delay")
            motors.append(
                MotorAssignment(
                    mount_id=m.id,
                    manufacturer=d.get("manufacturer", ""),
                    designation=d.get("designation", ""),
                    digest=d.get("digest") or None,
                    diameter=fnum(d.get("diameter"), 0.0),
                    length=fnum(d.get("length"), 0.0),
                    delay=None if delay_raw in (None, "", "none") else fnum(delay_raw),
                    ignition_event=ig.get("ignitionevent") or mm["ignitionevent"],
                    ignition_delay=fnum(ig.get("ignitiondelay"), mm["ignitiondelay"]),
                    overhang=mm["overhang"],
                    count=_multiplicity(m),
                    motor_type=d.get("type") or "single",
                )
            )
        deployments = []
        for r in recovery:
            event = r.values.get("deployevent") or "ejection"
            alt = r.num("deployaltitude", 200.0)
            delay = r.num("deploydelay", 0.0)
            o = r.deploy_overrides.get(fid)
            if o:
                event = o.get("deployevent", event) or event
                alt = fnum(o.get("deployaltitude"), alt)
                delay = fnum(o.get("deploydelay"), delay)
            deployments.append(Deployment(device_id=r.id, event=event, altitude=alt, delay=delay))
        configs.append(
            FlightConfiguration(
                id=fid,
                name=fc.get("name"),
                is_default=bool(fc.get("default")),
                active_stages=active,
                motors=motors,
                deployments=deployments,
            )
        )
    if configs and not any(c.is_default for c in configs):
        configs[0].is_default = True
    return configs


_COND_NUM = (
    "launchrodlength",
    "windaverage",
    "windturbulence",
    "winddirection",
    "launchaltitude",
    "launchlatitude",
    "launchlongitude",
    "timestep",
    "maxtime",
)


def _conditions(el) -> dict[str, Any]:
    c: dict[str, Any] = {}
    if el is None:
        return c
    for ch in el:
        if ch.tag == "wind":
            model = ch.get("model")
            if model == "average":
                c["wind_average"] = {k.tag: fnum(k.text) for k in ch}
            elif model == "multilevel":
                c["wind_multilevel"] = {
                    "altituderef": ch.get("altituderef"),
                    "levels": [{k: fnum(v) for k, v in lv.attrib.items()} for lv in ch.findall("windlevel")],
                }
        elif ch.tag == "atmosphere":
            c["atmosphere"] = {"model": ch.get("model"), **{k.tag: fnum(k.text) for k in ch}}
        else:
            c[ch.tag] = (ch.text or "").strip()
    for k in _COND_NUM:
        if k in c:
            c[k] = fnum(c[k])
    for k in ("launchrodangle", "launchroddirection"):
        if k in c:
            c[k] = fnum(c[k], 0.0) * DEG
    if "configid" in c and not c["configid"]:
        c["configid"] = None
    return c


def parse_simulations(doc: ParsedDocument, issues: list[Issue]) -> list[StoredSimulation]:
    sims = []
    unknown: Counter[str] = Counter()
    for el in doc.root_element.findall("simulations/simulation"):
        cond = _conditions(el.find("conditions"))
        fd = el.find("flightdata")
        summary: dict[str, float] = {}
        branches: list[DataBranch] = []
        warnings: list[str] = []
        if fd is not None:
            summary = {k: fnum(v) for k, v in fd.attrib.items()}
            for w in fd.findall("warning"):
                warnings.append((w.findtext("description") if len(w) else w.text or "").strip())
            for b in fd.findall("databranch"):
                types = (b.get("types") or "").split(",")
                rows = []
                for dp in b.findall("datapoint"):
                    parts = (dp.text or "").split(",")
                    if len(parts) == len(types):
                        rows.append([fnum(x, math.nan) for x in parts])
                data = np.array(rows, dtype=float).reshape(-1, len(types))
                cols: dict[str, np.ndarray] = {}
                for i, tname in enumerate(types):
                    key = column_key(tname)
                    if key is None:
                        unknown[tname] += 1
                        key = tname
                    cols.setdefault(key, data[:, i])
                events = [(fnum(e.get("time"), math.nan), e.get("type", "")) for e in b.findall("event")]
                branches.append(DataBranch(b.get("name", ""), cols, events))
        sims.append(
            StoredSimulation(
                name=el.findtext("name") or "",
                config_id=cond.get("configid"),
                conditions=cond,
                summary=summary,
                branches=branches,
                warnings=warnings,
            )
        )
    for name in unknown:
        issues.append(
            Issue(
                Severity.INFO,
                "ORK_UNKNOWN_COLUMN",
                f"Stored simulation column {name!r} is not a known OpenRocket data type; kept as-is",
            )
        )
    return sims
