import dataclasses
import math

import pytest

from stressaero.core.provenance import Issue, Provenance, Severity, Tier, ValidityBand


def test_label_interpolated():
    assert Provenance(Tier.CFD, "cfd.su2", interpolated=True).label() == "CFD (SU2) · interpolated"


def test_label_plain():
    p = Provenance(Tier.ENGINEERING_OR, "mass.or_compat.24_12")
    assert p.label() == "Engineering (OpenRocket method)"


@pytest.mark.parametrize("tier", list(Tier))
def test_every_tier_has_badge(tier):
    assert tier.badge and isinstance(tier.badge, str)


def test_validity_contains():
    band = ValidityBand(mach=(0.0, 0.8))
    assert band.contains(mach=0.9) is False
    assert band.contains(mach=0.5) is True
    assert band.contains() is True
    aoa = ValidityBand(aoa_rad=(0.0, math.radians(10)))
    assert aoa.contains(aoa_rad=math.radians(12)) is False
    assert aoa.contains(mach=5.0) is True  # unconstrained axis


def test_frozen_and_hashable():
    p = Provenance(Tier.FEA, "fea.ccx", references=("ref",), warnings=("w",))
    i = Issue(Severity.WARNING, "ORK_STALE_AUTO", "stale", component_id="abc")
    assert hash(p) and hash(i)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.tier = Tier.CFD  # type: ignore[misc]


def test_severity_ordering():
    assert Severity.ERROR > Severity.WARNING > Severity.INFO
