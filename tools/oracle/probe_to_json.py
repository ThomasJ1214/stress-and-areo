"""Convert ORProbe text output into per-file JSON expected-value fixtures.

Usage: python tools/oracle/probe_to_json.py PROBE_OUTPUT.txt [...] --out tests/data/openrocket/expected

ORProbe prints, per file::

    FILE <path>
    COMP <index> <class> <name> <x_abs> <length> <instances> [key=value ...]
    SIM  <index> <name> key=value ...

Log lines and anything else are ignored. The fixture is keyed by the .ork's parent directory (sample set)
and file stem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SIM_KEYS = {"CP(M0.3)": "cp_m03", "CNa": "cna_m03"}


def _num(s: str) -> float:
    return float(s)


def parse_probe(text: str) -> dict[Path, dict]:
    out: dict[Path, dict] = {}
    current: dict | None = None
    for raw in text.splitlines():
        parts = raw.split("\t")
        tag = parts[0]
        if tag == "FILE":
            current = {"components": [], "sims": [], "or_version": "24.12"}
            out[Path(parts[1])] = current
        elif tag == "COMP" and current is not None:
            comp = {
                "index": int(parts[1]),
                "cls": parts[2],
                "name": parts[3],
                "x": _num(parts[4]),
                "length": _num(parts[5]),
                "instances": int(parts[6]),
            }
            for kv in parts[7:]:
                k, v = kv.split("=", 1)
                comp[k] = _num(v)
            current["components"].append(comp)
        elif tag == "SIM" and current is not None:
            sim = {"index": int(parts[1]), "name": parts[2]}
            for kv in parts[3:]:
                k, v = kv.split("=", 1)
                sim[SIM_KEYS.get(k, k)] = _num(v)
            current["sims"].append(sim)
    return out


def write_fixtures(parsed: dict[Path, dict], out_dir: Path) -> list[Path]:
    written = []
    for ork_path, data in parsed.items():
        target = out_dir / ork_path.parent.name / (ork_path.stem + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("probe_files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    parsed: dict[Path, dict] = {}
    for f in args.probe_files:
        parsed.update(parse_probe(f.read_text(encoding="utf-8")))
    written = write_fixtures(parsed, args.out)
    print(f"wrote {len(written)} fixture files to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
