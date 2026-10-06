# Developer guide

## Prerequisites
- Python **3.12** (64-bit). Windows: install from python.org; Linux/macOS: system package or `uv python install 3.12`.
- Git.
- Linux only, for GUI tests: `xvfb` and the Qt/OpenGL system libraries listed in `.github/workflows/ci.yml`.

## Set up
```bash
git clone https://github.com/ThomasJ1214/stress-and-areo.git
cd stress-and-areo
python -m venv .venv            # Windows: py -3.12 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Run the app
```bash
python -m stressaero                     # empty window
python -m stressaero path/to/rocket.ork  # open a rocket
```

## Run the tests
```bash
pytest                       # Windows / any machine with a display
xvfb-run -a pytest           # headless Linux (GUI tests need a virtual display)
pytest -m "not gui"          # skip GUI tests
ruff check src tests tools   # lint
```
Tests marked `oracle` compare against committed reference values produced by OpenRocket itself;
regenerating those values needs Java 21 (see `tools/oracle/`).

## Project layout
```
src/stressaero/
  core/        units, provenance (fidelity tiers), rocket + configuration model   (no I/O, no GUI)
  geometry/    nose/transition shapes, resolved-component geometry queries
  io/          ork/ (container, parse, resolve, configs), project files
  physics/     mass model (OpenRocket-compatible)
  viz/         component meshes for the 3-D view
  ui/          PySide6 main window, tree, inspector, viewport, app entry point
tests/         mirrors src/; tests/data/openrocket holds OpenRocket sample files + expected values
tools/oracle/  regenerate expected values by running OpenRocket itself
packaging/     PyInstaller spec, Inno Setup script, Windows build script, icon
docs/          user guide, developer guide, design spec and plans, research notes
```
Layering is enforced by `tests/test_layering.py`: nothing outside `ui/` imports Qt, and `core/`, `io/`, `physics/`
never import the rendering stack.

## Regenerating OpenRocket reference values
The importer and mass model are tested against numbers produced by OpenRocket 24.12 itself
(`tests/data/openrocket/expected/`). To regenerate them (needs Java 21 with `java` and `javac` on PATH):
```bash
python tools/oracle/run_oracle.py tests/data/openrocket/v2412/*.ork --out tests/data/openrocket/expected
```
The script downloads the official OpenRocket jar (GPL-3.0) to `~/.cache/stressaero/` and runs it as a separate
program; it is never committed or bundled.

## Building the Windows installer
On Windows with Python 3.12 and the project installed (`pip install -e ".[dev]"`):
```powershell
./packaging/build_windows.ps1
```
This runs PyInstaller (`packaging/stressaero.spec`), executes the frozen app's self-test
(`StressAero.exe --selftest --selftest-out result.txt`) and compiles `packaging/installer.iss` with Inno Setup 6
(installed through Chocolatey if missing). Output: `dist/StressAero-Setup-<version>.exe`.
CI does the same on every push (job `windows`, artifact `StressAero-Setup`).

On Linux you can check that the PyInstaller spec still collects everything:
```bash
pyinstaller --noconfirm packaging/stressaero.spec && xvfb-run -a dist/StressAero/StressAero --selftest
```

## Conventions
- SI units internally (angles in radians); conversion only in `ui/`/reports via `core.units`.
- Every computed engineering result carries a `core.provenance.Provenance` (fidelity tier + method id).
- Tests first; `ruff check` and `ruff format` must pass (`ruff format src tests tools`).
