"""Regenerate OpenRocket reference values by running OpenRocket itself headless.

Requires Java 21 (``java`` and ``javac`` on PATH). Downloads the official OpenRocket jar (GPL-3.0) into a
cache directory (never committed), compiles ``ORProbe.java`` against it, runs it on the given ``.ork``
files and writes JSON fixtures via :mod:`probe_to_json`.

Example::

    python tools/oracle/run_oracle.py tests/data/openrocket/v2412/*.ork --out tests/data/openrocket/expected
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe_to_json  # noqa: E402

JAR_URL = "https://github.com/openrocket/openrocket/releases/download/release-{v}/OpenRocket-{v}.jar"
CACHE = Path(os.environ.get("STRESSAERO_CACHE", Path.home() / ".cache" / "stressaero"))


def ensure_jar(version: str) -> Path:
    jar = CACHE / f"OpenRocket-{version}.jar"
    if not jar.exists():
        jar.parent.mkdir(parents=True, exist_ok=True)
        tmp = jar.with_suffix(".part")
        with urllib.request.urlopen(JAR_URL.format(v=version)) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(jar)
    return jar


def run_probe(jar: Path, files: list[Path]) -> str:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["javac", "-cp", str(jar), "-d", td, str(HERE / "ORProbe.java")], check=True)
        listing = Path(td) / "files.txt"
        listing.write_text("\n".join(str(f) for f in files), encoding="utf-8")
        res = subprocess.run(
            ["java", "-Djava.awt.headless=true", "-cp", os.pathsep.join([str(jar), td]),
             "ORProbe", f"@{listing}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate OpenRocket oracle fixtures")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--or-version", default="24.12")
    args = ap.parse_args(argv)
    jar = ensure_jar(args.or_version)
    text = run_probe(jar, [f.resolve() for f in args.files])
    written = probe_to_json.write_fixtures(probe_to_json.parse_probe(text), args.out)
    print(f"wrote {len(written)} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
