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
