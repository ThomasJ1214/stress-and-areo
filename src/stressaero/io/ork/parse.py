"""Parse OpenRocket XML into the :mod:`stressaero.core.rocket` component tree (file values only).

Positions, lengths and ``auto`` dimensions are *not* resolved here (see :mod:`resolve`); values are typed
and converted to SI with angles in radians. Element semantics follow OpenRocket 23.09/24.12
(``DocumentConfig``, ``*Handler``/``*Saver`` classes); legacy names (``fincount``, ``position``,
``rotation``) are accepted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

from stressaero.core.provenance import Issue, Severity
from stressaero.core.rocket import (
    FILLED,
    FINS,
    STAGES,
    AutoValue,
    AxialPlacement,
    Component,
    Kind,
    MassOverride,
    Material,
    Rocket,
)
from stressaero.io.ork.errors import OrkFormatError

DEG = math.pi / 180.0

COMPONENT_TAGS = frozenset(k.value for k in Kind) - {Kind.ROCKET.value}

FINISH_ROUGHNESS = {  # ExternalComponent.Finish (m)
    "rough": 500e-6,
    "roughunfinished": 250e-6,
    "unfinished": 150e-6,
    "normal": 60e-6,
    "smooth": 20e-6,
    "optimum": 5e-6,
    "polished": 2e-6,
    "finishpolished": 0.5e-6,
    "mirror": 0.0,
}

# ClusterConfiguration.java unit-spacing points (scaled by 2*outerRadius*clusterScale)
_R5 = 1.0 / (2 * math.sin(2 * math.pi / 10))
_S2, _S3 = math.sqrt(2), math.sqrt(3)
CLUSTERS: dict[str, list[float]] = {
    "single": [0, 0],
    "double": [-0.5, 0, 0.5, 0],
    "3-row": [-1, 0, 0, 0, 1, 0],
    "4-row": [-1.5, 0, -0.5, 0, 0.5, 0, 1.5, 0],
    "3-ring": [-0.5, -1 / (2 * _S3), 0.5, -1 / (2 * _S3), 0, 1 / _S3],
    "4-ring": [-0.5, 0.5, 0.5, 0.5, 0.5, -0.5, -0.5, -0.5],
    "5-ring": [0, _R5]
    + [c for i in range(1, 5) for c in (_R5 * math.sin(2 * math.pi * i / 5), _R5 * math.cos(2 * math.pi * i / 5))],
    "6-ring": [0, 1, _S3 / 2, 0.5, _S3 / 2, -0.5, 0, -1, -_S3 / 2, -0.5, -_S3 / 2, 0.5],
    "3-star": [0, 0, 0, 1, _S3 / 2, -0.5, -_S3 / 2, -0.5],
    "4-star": [0, 0, -1 / _S2, 1 / _S2, 1 / _S2, 1 / _S2, 1 / _S2, -1 / _S2, -1 / _S2, -1 / _S2],
    "5-star": [0, 0, 0, 1]
    + [c for i in range(1, 5) for c in (math.sin(2 * math.pi * i / 5), math.cos(2 * math.pi * i / 5))],
    "6-star": [0, 0, 0, 1, _S3 / 2, 0.5, _S3 / 2, -0.5, 0, -1, -_S3 / 2, -0.5, -_S3 / 2, 0.5],
    "9-grid": [-1.4, 1.4, 0, 1.4, 1.4, 1.4, -1.4, 0, 0, 0, 1.4, 0, -1.4, -1.4, 0, -1.4, 1.4, -1.4],
    "9-star": [
        0,
        0,
        1.4,
        0,
        1.4 / _S2,
        -1.4 / _S2,
        0,
        -1.4,
        -1.4 / _S2,
        -1.4 / _S2,
        -1.4,
        0,
        -1.4 / _S2,
        1.4 / _S2,
        0,
        1.4,
        1.4 / _S2,
        1.4 / _S2,
    ],
}

_DEG_FIELDS = frozenset({"angleoffset", "rotation", "radialdirection", "cant", "clusterrotation"})
_AUTO_FIELDS = frozenset(
    {"radius", "aftradius", "foreradius", "outerradius", "innerradius", "packedradius", "cd", "linelength"}
)
_BOOL_FIELDS = frozenset(
    {
        "isflipped",
        "shapeclipped",
        "aftshouldercapped",
        "foreshouldercapped",
        "motormount",
        "overridesubcomponents",
        "overridesubcomponentsmass",
        "overridesubcomponentscg",
        "overridesubcomponentscd",
        "isdrogue",
    }
)
_STR_FIELDS = frozenset(
    {
        "name",
        "id",
        "shape",
        "crosssection",
        "clusterconfiguration",
        "masscomponenttype",
        "deployevent",
        "separationevent",
        "finish",
        "comment",
        "color",
        "linestyle",
        "designer",
        "revision",
        "referencetype",
        "designtype",
        "kitname",
        "material",
        "filletmaterial",
        "linematerial",
        "preset",
        "radiusoffset",
        "tabposition",
    }
)
_STRUCTURED = frozenset(
    {
        "subcomponents",
        "motormount",
        "appearance",
        "insideappearance",
        "inside-appearance",
        "finpoints",
        "deploymentconfiguration",
        "separationconfiguration",
        "motorconfiguration",
        "flightconfiguration",
        "preset",
    }
)
KNOWN_ELEMENTS = frozenset(
    """
aftradius aftshouldercapped aftshoulderlength aftshoulderradius aftshoulderthickness angleoffset appearance
axialoffset baseheight cant cd clusterconfiguration clusterrotation clusterscale color comment cordlength
crosssection deployaltitude deploydelay deployevent deploymentconfiguration designer designtype diameter
filletmaterial filletradius fincount finish finpoints flangeheight foreradius foreshouldercapped
foreshoulderlength foreshoulderradius foreshoulderthickness height id innerdiameter innerradius
insideappearance inside-appearance instancecount instanceseparation isflipped length linecount linelength
linematerial linestyle mass masscomponenttype material motorconfiguration flightconfiguration motormount name
outerdiameter outerradius overridecd overridecg overridemass overridesubcomponents overridesubcomponentscd
overridesubcomponentscg overridesubcomponentsmass packedlength packedradius position preset radialdirection
radialposition radius radiusoffset referencetype revision rootchord rotation screwheight separationaltitude
separationconfiguration separationdelay separationevent shape shapeclipped shapeparameter striplength
stripwidth subcomponents sweeplength tabheight tablength tabposition thickness tipchord kitname
customreference isdrogue
""".split()
)


def fnum(s: str | None, default: float | None = None) -> float | None:
    if s is None:
        return default
    s = s.strip()
    if not s:
        return default
    low = s.lower()
    if low == "nan":
        return math.nan
    if low in ("inf", "infinity"):
        return math.inf
    if low in ("-inf", "-infinity"):
        return -math.inf
    return float(s)


def _typed(tag: str, text: str) -> Any:
    t = text.strip()
    if tag in _BOOL_FIELDS:
        return t.lower() == "true"
    if tag in _STR_FIELDS:
        return t
    if tag in _AUTO_FIELDS and t.startswith("auto"):
        rest = t[4:].strip()
        return AutoValue(fnum(rest) if rest else None)
    if tag == "thickness" and t == FILLED:
        return FILLED
    try:
        v = fnum(t)
    except ValueError:
        return t
    if v is not None and tag in _DEG_FIELDS:
        v *= DEG
    return v


def _material(el: Element) -> Material:
    return Material(
        name=(el.text or "").strip(),
        kind=el.get("type", "bulk"),
        density=float(el.get("density", "0") or 0.0),
        group=el.get("group", "Custom"),
    )


@dataclass
class ParsedDocument:
    version: str
    creator: str
    rocket: Rocket
    root_element: Element


class _Ctx:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self._unknown_seen: set[tuple[str, str]] = set()
        self.stage_counter = 0

    def unknown(self, parent_tag: str, tag: str, cid: str | None) -> None:
        key = (parent_tag, tag)
        if key not in self._unknown_seen:
            self._unknown_seen.add(key)
            self.issues.append(
                Issue(
                    Severity.WARNING,
                    "ORK_UNKNOWN_ELEMENT",
                    f"Unknown element <{tag}> in <{parent_tag}> was ignored",
                    cid,
                )
            )


def _instance_count(c: Component) -> int:
    k = c.kind
    if k in FINS or k is Kind.TUBEFINSET:
        return int(c.values.get("instancecount", c.values.get("fincount", 1)) or 1)
    if k in (
        Kind.LAUNCHLUG,
        Kind.RAILBUTTON,
        Kind.BULKHEAD,
        Kind.CENTERINGRING,
        Kind.PODSET,
        Kind.PARALLELSTAGE,
        Kind.BOOSTERSET,
    ):
        return int(c.values.get("instancecount", 1) or 1)
    if k is Kind.INNERTUBE:
        cfg = c.values.get("clusterconfiguration", "single") or "single"
        return len(CLUSTERS.get(cfg, [0, 0])) // 2
    return 1


def _placement(c: Component) -> AxialPlacement:
    if "axialoffset" in c.attrs:
        method = c.attrs["axialoffset"].get("method")
        off = c.values.get("axialoffset")
    elif "position" in c.attrs:
        method = c.attrs["position"].get("type")
        off = c.values.get("position")
    else:
        return AxialPlacement("after", 0.0)
    method = (method or "after").strip().lower()
    return AxialPlacement(method, float(off) if isinstance(off, int | float) else 0.0)


def _parse_motormount(el: Element) -> dict[str, Any]:
    mm: dict[str, Any] = {
        "ignitionevent": "automatic",
        "ignitiondelay": 0.0,
        "overhang": 0.0,
        "motors": {},
        "ignition_overrides": {},
    }
    for ch in el:
        if ch.tag == "ignitionevent":
            mm["ignitionevent"] = (ch.text or "").strip()
        elif ch.tag == "ignitiondelay":
            mm["ignitiondelay"] = fnum(ch.text, 0.0)
        elif ch.tag == "overhang":
            mm["overhang"] = fnum(ch.text, 0.0)
        elif ch.tag == "motor":
            d = {k.tag: (k.text or "").strip() for k in ch}
            mm["motors"][ch.get("configid")] = d
        elif ch.tag == "ignitionconfiguration":
            d = {k.tag: (k.text or "").strip() for k in ch}
            mm["ignition_overrides"][ch.get("configid")] = d
    return mm


def _parse_component(el: Element, parent: Component | None, path: str, ctx: _Ctx) -> Component:
    kind = Kind(el.tag)
    c = Component(id="", kind=kind, name="", parent=parent, path=path)
    sub_index = 0
    for ch in el:
        tag = ch.tag
        if tag == "subcomponents":
            for sub in ch:
                if sub.tag in COMPONENT_TAGS:
                    c.children.append(_parse_component(sub, c, f"{path}/{sub_index}", ctx))
                    sub_index += 1
                else:
                    ctx.unknown(el.tag, sub.tag, None)
        elif tag == "motormount":
            c.motor_mount = _parse_motormount(ch)
        elif tag == "finpoints":
            c.fin_points = [(float(p.get("x", "0")), float(p.get("y", "0"))) for p in ch.findall("point")]
        elif tag == "deploymentconfiguration":
            c.deploy_overrides[ch.get("configid", "")] = {k.tag: (k.text or "").strip() for k in ch}
        elif tag == "separationconfiguration":
            c.separation_overrides[ch.get("configid", "")] = {k.tag: (k.text or "").strip() for k in ch}
        elif tag in ("motorconfiguration", "flightconfiguration"):
            c.values.setdefault("_flightconfigs", []).append(
                {
                    "id": ch.get("configid"),
                    "default": ch.get("default") == "true",
                    "name": ch.findtext("name"),
                    "stages": {int(s.get("number", "0")): s.get("active") == "true" for s in ch.findall("stage")},
                }
            )
        elif tag in ("appearance", "insideappearance", "inside-appearance"):
            d: dict[str, Any] = {}
            paint = ch.find("paint")
            if paint is not None:
                d["paint"] = dict(paint.attrib)
            decal = ch.find("decal")
            if decal is not None:
                d["decal"] = decal.get("name")
            if tag == "appearance":
                c.appearance = d
        elif tag == "preset":
            c.preset = dict(ch.attrib)
        else:
            if tag not in KNOWN_ELEMENTS:
                ctx.unknown(el.tag, tag, None)
            text = ch.text or ""
            c.attrs[tag] = dict(ch.attrib)
            c.multi.setdefault(tag, []).append((dict(ch.attrib), text))
            if tag == "material":
                c.material = _material(ch)
            elif tag == "filletmaterial":
                c.fillet_material = _material(ch)
            elif tag == "linematerial":
                c.line_material = _material(ch)
            c.values[tag] = _typed(tag, text)

    c.name = c.values.get("name") or kind.value
    c.id = c.values.get("id") or f"path:{path}"
    finish = c.values.get("finish")
    if isinstance(finish, str) and finish:
        c.finish_roughness = FINISH_ROUGHNESS.get(finish.lower().replace("_", ""))
    c.override = _override(c)
    c.instance_count = _instance_count(c)
    c.placement = _placement(c)
    if kind in STAGES:
        c.stage_index = ctx.stage_counter
        ctx.stage_counter += 1
    return c


def _override(c: Component) -> MassOverride:
    v = c.values
    legacy = bool(v.get("overridesubcomponents", False))
    return MassOverride(
        mass=v.get("overridemass") if isinstance(v.get("overridemass"), float) else None,
        cg=v.get("overridecg") if isinstance(v.get("overridecg"), float) else None,
        cd=v.get("overridecd") if isinstance(v.get("overridecd"), float) else None,
        mass_sub=bool(v.get("overridesubcomponentsmass", legacy)),
        cg_sub=bool(v.get("overridesubcomponentscg", legacy)),
        cd_sub=bool(v.get("overridesubcomponentscd", legacy)),
    )


def _assign_stage_indices(root: Component) -> None:
    """Every component's stage is its nearest stage ancestor (stage numbers are pre-order)."""
    for c in root.walk():
        if c.kind in STAGES:
            continue
        for a in c.ancestors():
            if a.kind in STAGES:
                c.stage_index = a.stage_index
                break


def parse_document(xml: bytes) -> ParsedDocument:
    try:
        root_el = SafeET.fromstring(xml)
    except (ParseError, DefusedXmlException) as e:
        raise OrkFormatError(f"malformed or unsafe OpenRocket XML: {e}") from e
    if root_el.tag != "openrocket":
        raise OrkFormatError(f"not an OpenRocket document (root element <{root_el.tag}>)")
    rocket_el = root_el.find("rocket")
    if rocket_el is None:
        raise OrkFormatError("OpenRocket document has no <rocket> element")
    ctx = _Ctx()
    root = _parse_component(rocket_el, None, "0", ctx)
    _assign_stage_indices(root)
    by_id: dict[str, Component] = {}
    for c in root.walk():
        if c.id in by_id:
            c.id = f"{c.id}#{c.path}"
            ctx.issues.append(Issue(Severity.WARNING, "ORK_DUPLICATE_ID", f"duplicate component id in {c.name}", c.id))
        by_id[c.id] = c
    rocket = Rocket(
        root=root,
        by_id=by_id,
        issues=ctx.issues,
        stage_count=max(ctx.stage_counter, 1),
        flight_config_entries=root.values.pop("_flightconfigs", []),
    )
    return ParsedDocument(
        version=root_el.get("version", ""), creator=root_el.get("creator", ""), rocket=rocket, root_element=root_el
    )
