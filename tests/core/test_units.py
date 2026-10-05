import math

import pytest

from stressaero.core.units import METRIC, UNITS, US_CUSTOMARY, Dim, format_quantity, from_si, to_si


@pytest.mark.parametrize(
    "sym,si",
    [
        ("in", 0.0254),
        ("ft", 0.3048),
        ("lb", 0.45359237),
        ("oz", 0.028349523125),
        ("lbf", 4.4482216152605),
        ("psi", 6894.757293168361),
        ("mph", 0.44704),
        ("kn", 1852 / 3600),
        ("lb/ft³", 16.018463373960138),
        ("lb·in²", 0.45359237 * 0.0254**2),
        ("deg", math.pi / 180),
        ("g", 1e-3),
    ],
)
def test_scale(sym, si):
    assert to_si(1.0, sym) == pytest.approx(si, rel=1e-15)


def test_temperature():
    assert to_si(32.0, "°F") == pytest.approx(273.15)
    assert from_si(373.15, "°C") == pytest.approx(100.0)
    assert from_si(273.15, "°F") == pytest.approx(32.0)


def test_roundtrip_all_units():
    for symbol in UNITS:
        assert from_si(to_si(1.2345, symbol), symbol) == pytest.approx(1.2345, rel=1e-12), symbol


def test_format():
    assert format_quantity(0.0254, Dim.LENGTH, US_CUSTOMARY) == "1.000 in"
    assert format_quantity(0.0254, Dim.LENGTH, METRIC) == "25.40 mm"
    assert format_quantity(1.36077711, Dim.MASS, METRIC) == "1361 g"
    assert format_quantity(0.28321, Dim.LENGTH, US_CUSTOMARY) == "11.15 in"


def test_override():
    s = METRIC.with_override(Dim.LENGTH, "cm")
    assert s.unit(Dim.LENGTH).symbol == "cm"
    assert METRIC.unit(Dim.LENGTH).symbol == "mm"  # original untouched


def test_dim_mismatch():
    with pytest.raises(ValueError):
        METRIC.with_override(Dim.LENGTH, "kg")


def test_ascii_aliases():
    assert to_si(1.0, "degF") == to_si(1.0, "°F")
    assert to_si(1.0, "kg/m^3") == 1.0
    assert UNITS["deg"] is UNITS["°"]


def test_systems_cover_all_dims():
    for dim in Dim:
        assert METRIC.unit(dim).dim is dim
        assert US_CUSTOMARY.unit(dim).dim is dim
