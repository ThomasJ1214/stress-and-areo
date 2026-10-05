import pytest

from tests.oracle_data import all_ork_files, expected_path, find, iter_cases


def test_every_sample_has_expected_values():
    files = all_ork_files()
    assert len(files) >= 70
    missing = [str(p) for p in files if not expected_path(p).exists()]
    assert missing == []


def test_dual_parachute_reference_values():
    case = next(c for c in iter_cases() if c.ork_path == find("Dual parachute"))
    assert case.sims[0]["structMass"] == pytest.approx(1.36077711, rel=1e-8)
    assert case.sims[0]["refLen"] == pytest.approx(0.056642, abs=1e-12)
    fins = case.components[13]
    assert fins["cls"] == "TrapezoidFinSet"
    assert fins["instances"] == 3
    assert fins["bodyr"] == pytest.approx(0.028321)
