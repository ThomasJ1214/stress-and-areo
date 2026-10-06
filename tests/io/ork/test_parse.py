import math

import pytest

from stressaero.core.provenance import Severity
from stressaero.core.rocket import AutoValue, Kind
from stressaero.io.ork.container import read_container
from stressaero.io.ork.parse import parse_document
from tests.oracle_data import find, iter_cases

OR_CLASS_TO_KIND = {
    "Rocket": {Kind.ROCKET},
    "AxialStage": {Kind.STAGE},
    "ParallelStage": {Kind.PARALLELSTAGE, Kind.BOOSTERSET},
    "PodSet": {Kind.PODSET},
    "NoseCone": {Kind.NOSECONE},
    "BodyTube": {Kind.BODYTUBE},
    "Transition": {Kind.TRANSITION},
    "TrapezoidFinSet": {Kind.TRAPEZOIDFINSET},
    "EllipticalFinSet": {Kind.ELLIPTICALFINSET},
    "FreeformFinSet": {Kind.FREEFORMFINSET},
    "TubeFinSet": {Kind.TUBEFINSET},
    "LaunchLug": {Kind.LAUNCHLUG},
    "RailButton": {Kind.RAILBUTTON},
    "InnerTube": {Kind.INNERTUBE},
    "TubeCoupler": {Kind.TUBECOUPLER},
    "EngineBlock": {Kind.ENGINEBLOCK},
    "CenteringRing": {Kind.CENTERINGRING},
    "Bulkhead": {Kind.BULKHEAD},
    "MassComponent": {Kind.MASSCOMPONENT},
    "ShockCord": {Kind.SHOCKCORD},
    "Parachute": {Kind.PARACHUTE},
    "Streamer": {Kind.STREAMER},
}


def _parse(path):
    return parse_document(read_container(path).xml)


@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c.id)
def test_component_kinds_match_openrocket_preorder(case):
    comps = list(_parse(case.ork_path).rocket.root.walk())
    assert len(comps) == len(case.components)
    for ours, theirs in zip(comps, case.components, strict=True):
        assert ours.kind in OR_CLASS_TO_KIND[theirs["cls"]], (theirs["index"], theirs["name"])
        assert ours.name == theirs["name"]
        assert ours.instance_count == theirs["instances"] or theirs["cls"] in ("Rocket", "AxialStage")


def test_dual_parachute_details():
    doc = _parse(find("Dual parachute"))
    comps = list(doc.rocket.root.walk())
    assert len(comps) == 20
    assert doc.version == "1.10"
    tube = comps[5]
    assert tube.kind is Kind.BODYTUBE
    assert tube.values["radius"] == AutoValue(0.025)  # stale cache preserved as-is
    fins = comps[13]
    assert fins.kind is Kind.TRAPEZOIDFINSET
    assert isinstance(fins.values["cant"], float)
    assert fins.material is not None and fins.material.density > 0
    assert doc.rocket.by_id[tube.id] is tube


def test_cant_converted_to_radians():
    doc = _parse(find("Simulation scripting"))
    canted = [
        c
        for c in doc.rocket.root.walk()
        if c.kind in {Kind.TRAPEZOIDFINSET, Kind.FREEFORMFINSET} and c.values.get("cant")
    ]
    assert canted, "expected a canted fin set"
    assert all(abs(c.values["cant"]) < math.radians(30) for c in canted)


def test_old_files_get_stable_path_ids():
    path = find("simplerocket", "v2412")
    ids1 = [c.id for c in _parse(path).rocket.root.walk()]
    ids2 = [c.id for c in _parse(path).rocket.root.walk()]
    assert ids1 == ids2
    assert ids1[0] == "path:0"
    assert all(i.startswith("path:") for i in ids1)
    assert len(set(ids1)) == len(ids1)


XML = """<?xml version="1.0" encoding="utf-8"?>
<openrocket version="1.10" creator="test"><rocket><name>R</name><subcomponents>
<stage><name>S</name><subcomponents>
<nosecone><name>Nasenkegel ü</name><length>0.2</length><thickness>0.002</thickness><shape>ogive</shape>
<aftradius>0.03</aftradius><foo>1</foo></nosecone>
</subcomponents></stage></subcomponents></rocket></openrocket>""".encode()


def test_non_ascii_name_and_unknown_element():
    doc = parse_document(XML)
    nose = [c for c in doc.rocket.root.walk() if c.kind is Kind.NOSECONE][0]
    assert nose.name == "Nasenkegel ü"
    codes = [(i.code, i.severity) for i in doc.rocket.issues]
    assert ("ORK_UNKNOWN_ELEMENT", Severity.WARNING) in codes


def test_rejects_non_openrocket_xml():
    from stressaero.io.ork.errors import OrkFormatError

    with pytest.raises(OrkFormatError):
        parse_document(b"<other/>")
    with pytest.raises(OrkFormatError):
        parse_document(b"<openrocket><rocket>")  # malformed
