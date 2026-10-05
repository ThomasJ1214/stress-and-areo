"""Access to OpenRocket-oracle expected values committed under tests/data/openrocket/expected/."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "openrocket"
SETS = ("v2412", "v2309", "master", "synthetic")


@dataclass
class OracleCase:
    ork_path: Path
    components: list[dict]
    sims: list[dict]

    @property
    def id(self) -> str:
        return f"{self.ork_path.parent.name}/{self.ork_path.stem}"


def expected_path(ork_path: Path) -> Path:
    return DATA / "expected" / ork_path.parent.name / (ork_path.stem + ".json")


def all_ork_files() -> list[Path]:
    return sorted(p for s in SETS for p in (DATA / s).glob("*.ork"))


def iter_cases() -> Iterator[OracleCase]:
    for ork in all_ork_files():
        data = json.loads(expected_path(ork).read_text(encoding="utf-8"))
        yield OracleCase(ork, data["components"], data["sims"])


def find(name_fragment: str, set_name: str = "v2412") -> Path:
    matches = [p for p in (DATA / set_name).glob("*.ork") if name_fragment in p.name]
    assert len(matches) == 1, (name_fragment, matches)
    return matches[0]
