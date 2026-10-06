import math

import numpy as np
import pytest

from stressaero.geometry.shapes import CLIPPABLE, DEFAULT_PARAM, Shape, profile, profile_radius

L, R = 0.24, 0.04


def test_cone_midpoint():
    assert profile_radius(Shape.CONICAL, L / 2, L, 0.0, R, 0.0, False) == pytest.approx(R / 2)


def test_tangent_ogive_matches_closed_form():
    x = L / 2
    rho = (R**2 + L**2) / (2 * R)
    expected = math.sqrt(rho**2 - (L - x) ** 2) + R - rho
    assert profile_radius(Shape.OGIVE, x, L, 0.0, R, 1.0, False) == pytest.approx(expected, rel=1e-12)


def test_von_karman_midpoint():
    assert profile_radius(Shape.HAACK, L / 2, L, 0.0, R, 0.0, False) == pytest.approx(R * math.sqrt(0.5), rel=1e-12)


@pytest.mark.parametrize("shape", list(Shape))
def test_endpoints(shape):
    p = DEFAULT_PARAM.get(shape, 0.0)
    assert profile_radius(shape, 0.0, L, 0.0, R, p, False) == pytest.approx(0.0, abs=1e-12)
    assert profile_radius(shape, L, L, 0.0, R, p, False) == pytest.approx(R, rel=1e-9)
    # transition between two non-zero radii, unclipped
    assert profile_radius(shape, 0.0, L, 0.01, R, p, False) == pytest.approx(0.01, abs=1e-12)
    assert profile_radius(shape, L, L, 0.01, R, p, False) == pytest.approx(R, rel=1e-9)


def test_clipped_power_transition_starts_at_fore_radius():
    r = profile_radius(Shape.POWER, 0.0, 0.1, 0.01, R, 0.5, True)
    assert abs(r - 0.01) <= 1e-3 * R
    assert profile_radius(Shape.POWER, 0.1, 0.1, 0.01, R, 0.5, True) == pytest.approx(R, rel=1e-9)


def test_clipping_ignored_for_non_clippable_shapes():
    assert Shape.OGIVE not in CLIPPABLE
    a = profile_radius(Shape.OGIVE, 0.05, 0.1, 0.01, R, 1.0, True)
    b = profile_radius(Shape.OGIVE, 0.05, 0.1, 0.01, R, 1.0, False)
    assert a == b


def test_reversed_transition_mirrors():
    x = np.linspace(0, 0.1, 11)
    fwd = profile_radius(Shape.ELLIPSOID, x, 0.1, 0.01, R, 0.0, False)
    rev = profile_radius(Shape.ELLIPSOID, 0.1 - x, 0.1, R, 0.01, 0.0, False)
    np.testing.assert_allclose(fwd, rev, rtol=1e-12)


def test_vectorised_matches_scalar_and_profile():
    xs, rs = profile(Shape.PARABOLIC, L, 0.0, R, 0.5, False, n=33)
    assert xs.shape == rs.shape == (33,)
    assert rs[16] == pytest.approx(profile_radius(Shape.PARABOLIC, xs[16], L, 0.0, R, 0.5, False))
    assert np.all(np.diff(rs) >= -1e-15)


def test_out_of_range_x_clamps():
    assert profile_radius(Shape.CONICAL, -1.0, L, 0.0, R, 0.0, False) == 0.0
    assert profile_radius(Shape.CONICAL, 5.0, L, 0.0, R, 0.0, False) == R
