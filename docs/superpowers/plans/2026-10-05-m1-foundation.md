# M1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable Stress & Aero desktop app that opens any OpenRocket `.ork` (formats 1.0–1.10/1.11), reproduces
OpenRocket 24.12's geometry/mass/CG exactly, shows the rocket as an interactive 3-D model with picking + inspector +
flight-configuration selector + metric/US units, saves/loads projects, and is built into a Windows installer by CI.

**Architecture:** `src/stressaero` package with strict layering (`core` ← `geometry`/`physics`/`io` ← `viz` ← `ui`).
The `.ork` importer is a production port of the research prototype `docs/research/prototypes/ork-format/proto_parser.py`
(verified against OpenRocket 24.12 on 71 samples), split into container → parse → resolve → mass modules. Expected
values come from OpenRocket's own headless output (`orprobe/probe_all.txt`) converted to JSON fixtures.

**Tech Stack:** Python 3.12, numpy, PySide6 6.11, pyvista 0.49 / VTK 9.7, pyvistaqt, pyqtgraph, defusedxml, pytest,
pytest-qt, PyInstaller, Inno Setup 6, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-05-rocket-analysis-app-design.md` (§3 stack, §4 architecture, §4.2 provenance,
§5 data model, §8.1 UI, §14 testing, §15 packaging, §16 M1 row).

## Global Constraints

- Python `>=3.12,<3.14`; package `stressaero` in `src/` layout; console entry `stressaero = stressaero.ui.app:main`; `python -m stressaero` launches the GUI.
- Internal units SI, angles in radians; degree values from `.ork` (angleoffset, rotation, radialdirection, cant, clusterrotation, launchrodangle, launchroddirection) converted at parse; `winddirection` and `<wind><direction>` are already radians; lat/lon stay degrees.
- Nothing outside `stressaero.ui` imports `PySide6`/`pyvistaqt`; nothing in `core`/`geometry`/`physics`/`io` imports `pyvista` (enforced by `tests/test_layering.py`).
- Every computed engineering quantity returned to the UI carries a `Provenance`; mass/CG from the OR-style model use `Tier.ENGINEERING_OR`, method id `"mass.or_compat.24_12"`.
- Stale `auto` values are never used; both file value and recomputed value are kept and an `Issue(code="ORK_STALE_AUTO")` is raised when they differ by > 1e-9 m.
- XML parsed with `defusedxml.ElementTree`; ZIP reading rejects uncompressed entries > 64 MiB (`OrkFormatError`) and never extracts to disk.
- Oracle tolerances (vs OpenRocket 24.12): positions ≤ 1e-4 m (canted fins) else ≤ 1e-7 m; lengths/radii ≤ 1e-7 m; component mass ≤ 1e-5 relative (+1e-9 kg abs); structure mass ≤ 1e-5 relative; CG ≤ 1e-5 m; reference length ≤ 1e-9 m.
- GPL artefacts (OpenRocket sample files, OR jar) stay in `tests/data/openrocket/` and `tools/oracle/` with `ATTRIBUTION.md`; the jar is downloaded, never committed.
- Commit messages end with the session's `Co-Authored-By`/`Claude-Session` trailer lines.

## Review Focus

1. Pre-1.9 files (no `<id>`), GZIP (format 1.2) and plain-XML (1.4/1.6) `.ork` → must load; component ids fall back to stable tree paths (`path:0/1/3`) identical across two loads — test in Task 7.
2. ZIP oddities: entries with a leading `/` (Parallel booster staging), `rocket.ork` not first, oversized entry → leading-slash file loads; oversized raises `OrkFormatError` with a readable message — tests in Task 6.
3. Non-ASCII component names and localized/unknown stored-simulation column names (e.g. `Höhe`) → name preserved exactly; unknown columns kept under their raw name plus an `Issue(code="ORK_UNKNOWN_COLUMN")` — tests in Tasks 7 and 9.
4. Multi-stage / pod / parallel-stage rockets (out of v1 simulation scope) → still import, resolve and render every instance at the right place; inactive stages hidden for the selected configuration — tests in Tasks 10 and 11.
5. Project files with a corrupt embedded `.ork` or newer schema version → `load_project` raises `ProjectFormatError`; the GUI shows an error dialog instead of crashing — tests in Tasks 12 and 13.

---

## File structure (M1)

```
pyproject.toml, README.md, LICENSE, THIRD_PARTY_NOTICES.md, .gitignore
.github/workflows/ci.yml                 Linux: lint + tests (xvfb); Windows: tests (non-render) + installer build
src/stressaero/__init__.py               __version__ = "0.1.0"
src/stressaero/__main__.py               -> ui.app.main()
src/stressaero/core/units.py             dimensions, units, unit systems, formatting
src/stressaero/core/provenance.py        Tier, ValidityBand, Provenance, Severity, Issue
src/stressaero/core/rocket.py            resolved rocket model dataclasses
src/stressaero/geometry/shapes.py        transition/nose profile functions r(x)
src/stressaero/io/ork/__init__.py        load_ork() facade, OrkImport, OrkFormatError
src/stressaero/io/ork/container.py       ZIP/GZIP/plain detection + guards
src/stressaero/io/ork/parse.py           XML -> component tree with file values
src/stressaero/io/ork/resolve.py         lengths, axial positions, auto dimensions, instances
src/stressaero/io/ork/configs.py         flight configurations, motors, recovery, stored simulations
src/stressaero/physics/massmodel.py      OR-compatible component/structure mass + CG, reference length
src/stressaero/io/project.py             .saproj save/load
src/stressaero/viz/rocket_mesh.py        component -> pyvista PolyData (world coords, ids)
src/stressaero/ui/app.py                 QApplication bootstrap, --selftest
src/stressaero/ui/main_window.py         window, menus, toolbar (config + units), docks
src/stressaero/ui/component_tree.py      tree dock
src/stressaero/ui/inspector.py           property table with units + provenance badges
src/stressaero/ui/viewport.py            pyvistaqt viewport, picking, highlight, CG marker
tools/oracle/ORProbe.java, run_oracle.py, probe_to_json.py, ATTRIBUTION.md
tests/data/openrocket/{v2412,v2309,master,synthetic}/*.ork, expected/**/*.json, ATTRIBUTION.md
tests/...                                mirrors src
packaging/stressaero.spec, packaging/installer.iss, packaging/build_windows.ps1
docs/user/INSTALL.md, docs/dev/DEVELOPING.md
```

---

### Task 1: Project scaffold, layering guard, Linux CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, `README.md`, `src/stressaero/__init__.py`, `src/stressaero/__main__.py`, `src/stressaero/{core,geometry,physics,io,io/ork,viz,ui}/__init__.py`, `.github/workflows/ci.yml`, `docs/dev/DEVELOPING.md`
- Test: `tests/test_package.py`, `tests/test_layering.py`

**Interfaces:**
- Produces: importable `stressaero` with `__version__: str`; pytest config (`testpaths=["tests"]`, markers `gui`, `oracle`, `slow`); extras `[dev]` = pytest, pytest-qt, ruff, hypothesis, pyinstaller.

- [ ] **Step 1: Write failing tests**

```python
def test_version():
    import stressaero
    assert stressaero.__version__ == "0.1.0"

FORBIDDEN = {"core": {"PySide6", "pyvista", "pyvistaqt", "vtk"}, "geometry": {"PySide6", "pyvistaqt"},
             "physics": {"PySide6", "pyvista", "pyvistaqt", "vtk"}, "io": {"PySide6", "pyvista", "pyvistaqt", "vtk"},
             "viz": {"PySide6", "pyvistaqt"}}
def test_layering():  # AST-scan every module under src/stressaero/<layer>/ for forbidden top-level imports
    ...
    assert violations == []
```

- [ ] **Step 2: Run** `uv run --python 3.12 pytest tests/test_package.py tests/test_layering.py -v` → FAIL (package missing).
- [ ] **Step 3: Create scaffold.** `pyproject.toml` (hatchling, deps: numpy>=2.2, scipy>=1.14, defusedxml, PySide6>=6.8, pyvista>=0.45, pyvistaqt>=0.11, pyqtgraph>=0.13; ruff line-length 110). `LICENSE`: "Copyright (c) 2026 the Stress & Aero authors. All rights reserved. Private/team use." `THIRD_PARTY_NOTICES.md` lists runtime deps + licences (OpenRocket GPL-3 test data/oracle only). CI job `linux`: setup-python 3.12, `pip install -e .[dev]`, `apt-get install xvfb libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0`, `ruff check`, `xvfb-run -a pytest -m "not oracle"`. `DEVELOPING.md`: clone, `py -3.12 -m venv .venv`, `pip install -e .[dev]`, `python -m stressaero`, `pytest`, Linux GUI tests via `xvfb-run`.
- [ ] **Step 4: Run tests** → PASS; `ruff check src tests` clean.
- [ ] **Step 5: Commit** `chore: project scaffold, layering guard, CI`.

---

### Task 2: Units

**Files:** Create `src/stressaero/core/units.py`; Test `tests/core/test_units.py`

**Interfaces:**
- Produces:
  - `class Dim(str, Enum)`: `LENGTH, DISTANCE, MASS, TIME, ANGLE, VELOCITY, ACCELERATION, FORCE, PRESSURE, DENSITY, AREA, VOLUME, TEMPERATURE, INERTIA, MOMENT, AREAL_DENSITY, LINEAR_DENSITY, ANGULAR_RATE, IMPULSE, FREQUENCY, DIMENSIONLESS`
  - `@dataclass(frozen=True) class Unit: symbol: str; dim: Dim; scale: float; offset: float = 0.0` (SI = scale·v + offset)
  - `UNITS: dict[str, Unit]`; `to_si(value: float, unit: str) -> float`; `from_si(value_si: float, unit: str) -> float`
  - `@dataclass(frozen=True) class UnitSystem: name: str; preferred: Mapping[Dim, str]`; `METRIC`, `US_CUSTOMARY`; `UnitSystem.unit(dim) -> Unit`; `UnitSystem.with_override(dim, symbol) -> UnitSystem`
  - `format_quantity(value_si: float, dim: Dim, system: UnitSystem, sig: int = 4) -> str` (e.g. `"25.40 mm"`)
  - Preferred units: METRIC = LENGTH mm, DISTANCE m, MASS g, VELOCITY m/s, ACCELERATION m/s², FORCE N, PRESSURE kPa, DENSITY kg/m³, TEMPERATURE °C, INERTIA kg·m², MOMENT N·m, ANGLE °; US = LENGTH in, DISTANCE ft, MASS oz, VELOCITY ft/s, ACCELERATION ft/s², FORCE lbf, PRESSURE psi, DENSITY lb/ft³, TEMPERATURE °F, INERTIA lb·in², MOMENT lbf·ft, ANGLE °.

- [ ] **Step 1: Failing tests** — exact constants and round trips:

```python
@pytest.mark.parametrize("sym,si", [("in", 0.0254), ("ft", 0.3048), ("lb", 0.45359237), ("oz", 0.028349523125),
    ("lbf", 4.4482216152605), ("psi", 6894.757293168361), ("mph", 0.44704), ("kn", 1852/3600),
    ("lb/ft³", 16.018463373960138), ("lb·in²", 0.45359237*0.0254**2), ("deg", math.pi/180), ("g", 1e-3)])
def test_scale(sym, si): assert to_si(1.0, sym) == pytest.approx(si, rel=1e-15)
def test_temperature(): assert to_si(32.0, "°F") == pytest.approx(273.15); assert from_si(373.15, "°C") == pytest.approx(100.0)
def test_roundtrip_all_units(): for each unit u: from_si(to_si(1.2345, u), u) ≈ 1.2345 (rel 1e-12)
def test_format(): assert format_quantity(0.0254, Dim.LENGTH, US_CUSTOMARY) == "1.000 in"; assert format_quantity(0.0254, Dim.LENGTH, METRIC) == "25.40 mm"
def test_override(): s = METRIC.with_override(Dim.LENGTH, "cm"); assert s.unit(Dim.LENGTH).symbol == "cm"
def test_dim_mismatch(): with pytest.raises(ValueError): METRIC.with_override(Dim.LENGTH, "kg")
```

- [ ] **Step 2:** `pytest tests/core/test_units.py -v` → FAIL.
- [ ] **Step 3:** Implement; ASCII aliases accepted (`"deg"`, `"degF"`, `"kg/m^3"`) mapping to the same `Unit`.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(core): unit system with metric/US customary`.

---

### Task 3: Provenance and issues

**Files:** Create `src/stressaero/core/provenance.py`; Test `tests/core/test_provenance.py`

**Interfaces:**
- Produces:
  - `class Tier(str, Enum)`: `ESTIMATE, OR_STORED, ENGINEERING_OR, ENGINEERING, GEOMETRIC, CFD, FEA`; property `badge: str` ("Estimate", "OpenRocket stored result", "Engineering (OpenRocket method)", "Engineering", "Geometry-based", "CFD (SU2)", "FEA (CalculiX)").
  - `@dataclass(frozen=True) class ValidityBand: mach: tuple[float, float] | None = None; aoa_rad: tuple[float, float] | None = None; note: str = ""`; `contains(mach: float | None = None, aoa_rad: float | None = None) -> bool`.
  - `@dataclass(frozen=True) class Provenance: tier: Tier; method_id: str; method_version: str = "1"; references: tuple[str, ...] = (); warnings: tuple[str, ...] = (); validity: ValidityBand | None = None; interpolated: bool = False`; `label() -> str` (badge + " · interpolated" when set).
  - `class Severity(IntEnum): INFO=0, WARNING=1, ERROR=2`; `@dataclass(frozen=True) class Issue: severity: Severity; code: str; message: str; component_id: str | None = None`.

- [ ] **Step 1: Failing tests:** `Provenance(Tier.CFD, "cfd.su2", interpolated=True).label() == "CFD (SU2) · interpolated"`; `ValidityBand(mach=(0, 0.8)).contains(mach=0.9) is False`; `contains()` with no args is True; dataclasses are hashable/frozen.
- [ ] **Steps 2–4:** fail → implement → pass. **Step 5:** Commit `feat(core): provenance tiers and issues`.

---

### Task 4: OpenRocket fixtures and oracle expected data

**Files:**
- Create: `tests/data/openrocket/{v2412,v2309,master,synthetic}/*.ork` (copied from research `samples/`; synthetic from `docs/research/prototypes/ork-format/samples_synthetic/`), `tests/data/openrocket/ATTRIBUTION.md`, `tools/oracle/ORProbe.java` (from research), `tools/oracle/run_oracle.py`, `tools/oracle/probe_to_json.py`, `tools/oracle/ATTRIBUTION.md`, `tests/data/openrocket/expected/<set>/<file-stem>.json`, `tests/oracle_data.py`
- Test: `tests/test_oracle_fixtures.py`

**Interfaces:**
- Produces: `tests/oracle_data.py::iter_cases() -> Iterator[OracleCase]` with `OracleCase(ork_path: Path, components: list[dict], sims: list[dict])`; component dict keys `index, cls, name, x, length, instances, fore, aft, ro, ri, bodyr, compmass, compcgx` (missing → absent); sim keys `index, name, structMass, structCG, launchMass, launchCG, cp_m03, cna_m03, refLen, length`.
- `run_oracle.py --or-version 24.12 [--files ...] --out expected/`: downloads `https://github.com/openrocket/openrocket/releases/download/release-24.12/OpenRocket-24.12.jar` to `~/.cache/stressaero/`, compiles ORProbe against it, runs headless (`-Djava.awt.headless=true`), pipes to `probe_to_json.py`.

- [ ] **Step 1: Failing test:** every `.ork` in `tests/data/openrocket/{v2412,v2309,master,synthetic}` has an expected JSON; Dual parachute (v2412) expected `sims[0]["structMass"] == pytest.approx(1.36077711, rel=1e-8)` and `refLen == 0.056642`; component 13 cls `"TrapezoidFinSet"` with `instances == 3`.
- [ ] **Step 2:** FAIL. **Step 3:** copy fixtures; write `probe_to_json.py` (parse `FILE/COMP/SIM` lines, ignore log lines, map `../samples/<set>/<name>` → `expected/<set>/<stem>.json`); generate expected JSON from `docs/research/prototypes/ork-format/orprobe/probe_all.txt` + `probe_synth.txt`; write `run_oracle.py` (regeneration path, marked `oracle` in CI and run manually/nightly).
- [ ] **Step 4:** PASS (+ `python tools/oracle/run_oracle.py --files tests/data/openrocket/v2412/*Dual*.ork` reproduces the committed JSON within 1e-9 when Java 21 is available).
- [ ] **Step 5:** Commit `test: vendor OpenRocket samples and oracle expected values`.

---

### Task 5: Nose/transition profile shapes

**Files:** Create `src/stressaero/geometry/shapes.py`; Test `tests/geometry/test_shapes.py`

**Interfaces:**
- Produces: `class Shape(str, Enum): CONICAL, OGIVE, ELLIPSOID, POWER, PARABOLIC, HAACK`; `DEFAULT_PARAM: dict[Shape, float]` (ogive 1, power 0.5, parabolic 1, haack 0); `CLIPPABLE = {ELLIPSOID, POWER, HAACK}`; `profile_radius(shape: Shape, x: float | np.ndarray, length: float, r_fore: float, r_aft: float, param: float, clipped: bool) -> float | np.ndarray` (x from fore end; handles r_fore > r_aft by mirroring; clipped bisection tol 1e-4 per OR); `profile(shape, length, r_fore, r_aft, param, clipped, n=128) -> tuple[np.ndarray, np.ndarray]`.
- Formulas: port `_shape_radius` + clipping from `docs/research/prototypes/ork-format/proto_parser.py:147-180` (cone R x/L; ogive ρ/Λ/y0 form with conical fallback k<0.001; ellipsoid √(2Rx'−x'²), x'=xR/L; power R(x/L)^k; parabolic R(2x/L − k(x/L)²)/(2−k); Haack θ=acos(1−2x/L), R√((θ − sin2θ/2 + k sin³θ)/π)).

- [ ] **Step 1: Failing tests:** cone midpoint = R/2; tangent ogive (k=1, L=0.24, R=0.04) at x=L/2 equals `sqrt(ρ²−(L−x)²)+R−ρ` with ρ=(R²+L²)/(2R); Haack k=0 at x=L/2 equals `R*sqrt((π/2)/π)`; all shapes r(0)=r_fore, r(L)=r_aft; clipped power(0.5) transition with r_fore=0.01 satisfies r(0)=0.01 within 1e-4·R; reversed transition r_fore>r_aft mirrors.
- [ ] **Steps 2–4.** **Step 5:** Commit `feat(geometry): OpenRocket nose/transition profile shapes`.

---

### Task 6: `.ork` container reader

**Files:** Create `src/stressaero/io/ork/container.py`, `src/stressaero/io/ork/errors.py`; Test `tests/io/ork/test_container.py`

**Interfaces:**
- Produces: `class OrkFormatError(ValueError)`; `@dataclass(frozen=True) class Container: kind: Literal["zip", "gzip", "xml"]; xml: bytes; entries: tuple[str, ...]`; `read_container(source: Path | bytes, *, max_bytes: int = 64 * 2**20) -> Container`.
- Rules: magic `PK` → ZIP, use the first entry whose name (leading `/` stripped) ends with `.ork`/`.rkt`/`.cdx1`; `1f 8b` → gzip; else plain XML must contain `<openrocket` in the first 300 bytes; read with size cap (stream, abort > max_bytes).

- [ ] **Step 1: Failing tests:** v2412 Dual parachute → `kind == "zip"`, entries[0] == "rocket.ork"; `simplerocket.ork` → "gzip"; `asimple.ork` → "xml"; Parallel booster staging loads (leading-slash entries listed); a zip whose `rocket.ork` inflates to 65 MiB (build in tmp with zeros) → `OrkFormatError` matching "too large"; random bytes → `OrkFormatError` matching "not an OpenRocket file".
- [ ] **Steps 2–4.** **Step 5:** Commit `feat(io): ork container detection with size and path guards`.

---

### Task 7: Parse XML into the component tree

**Files:** Create `src/stressaero/core/rocket.py`, `src/stressaero/io/ork/parse.py`; Test `tests/io/ork/test_parse.py`

**Interfaces:**
- Produces (core/rocket.py):
  - `class Kind(str, Enum)` with values = OR tag names: `rocket, stage, parallelstage, boosterset, podset, nosecone, bodytube, transition, trapezoidfinset, ellipticalfinset, freeformfinset, tubefinset, launchlug, railbutton, innertube, tubecoupler, engineblock, centeringring, bulkhead, masscomponent, shockcord, parachute, streamer`; helper sets `SYMMETRIC, FINS, RINGS, MASS_OBJECTS, RECOVERY, ASSEMBLIES, STAGES`.
  - `@dataclass class Material: name: str; kind: Literal["bulk","surface","line"]; density: float; group: str = "Custom"`.
  - `@dataclass class MassOverride: mass: float | None = None; cg: float | None = None; cd: float | None = None; mass_sub: bool = False; cg_sub: bool = False; cd_sub: bool = False`.
  - `@dataclass class AxialPlacement: method: Literal["after","top","middle","bottom","absolute"]; offset: float`.
  - `@dataclass(eq=False) class Component: id: str; kind: Kind; name: str; parent: "Component | None"; children: list["Component"]; placement: AxialPlacement; values: dict[str, Any]` (SI-normalised file values; auto fields stored as `AutoValue(cached: float | None)`), `material: Material | None`, `override: MassOverride`, `finish_roughness: float | None`, `instance_count: int = 1`, and resolved fields filled by Task 8: `length: float = 0.0; x_rel: float = 0.0; x_abs: float = 0.0; stage_index: int | None = None; resolved: dict[str, float]` (e.g. `fore_radius`, `aft_radius`, `outer_radius`, `inner_radius`, `body_radius`, `packed_length`, `packed_radius`); `walk() -> Iterator[Component]`; `path: str`.
  - `@dataclass(frozen=True) class AutoValue: cached: float | None`.
  - `@dataclass class Rocket: root: Component; by_id: dict[str, Component]; issues: list[Issue]`.
- Produces (io/ork/parse.py): `parse_document(xml: bytes) -> ParsedDocument` with `ParsedDocument(version: str, creator: str, rocket: Rocket, root_element: Element)`; ids = `<id>` text or `f"path:{'/'.join(child indices)}"`.

- [ ] **Step 1: Failing tests:** v2412 Dual parachute: 20 components in pre-order, kinds match oracle `cls` mapping (`NoseCone→nosecone`, `AxialStage→stage`…); `bodytube` radius stored as `AutoValue(0.025)` (stale cache kept); trapezoid fin `cant` in radians; `simplerocket.ork` ids start with `"path:"` and are identical across two parses; a synthetic XML with name `"Nasenkegel ü"` round-trips exactly; unknown element `<foo/>` → `Issue(code="ORK_UNKNOWN_ELEMENT")`, not an exception.
- [ ] **Step 2:** FAIL. **Step 3:** Port `parse_component`, value parsing (`fnum`, `auto_num`, `fbool`), legacy tag aliases (`fincount`/`position`/`rotation`) and `COMPONENT_TAGS` from the prototype (`proto_parser.py:60-120, 183-300, 658-765`), using `defusedxml.ElementTree.fromstring`.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat(io): parse ork XML into component tree`.

---

### Task 8: Resolve lengths, positions and auto dimensions

**Files:** Create `src/stressaero/io/ork/resolve.py`, `src/stressaero/io/ork/__init__.py`; Test `tests/io/ork/test_resolve.py`, `tests/io/ork/test_oracle_geometry.py`

**Interfaces:**
- Consumes: `Rocket`, `Component` (Task 7); `profile_radius` (Task 5).
- Produces: `resolve(rocket: Rocket, *, emulate_or_stale_positions: bool = True) -> None` (fills `length, x_rel, x_abs, stage_index, resolved`, adds `ORK_STALE_AUTO` issues); `load_ork(source: Path | bytes, *, name: str | None = None) -> OrkImport` with `OrkImport(rocket: Rocket, configurations: list[FlightConfiguration], simulations: list[StoredSimulation], format_version: str, creator: str, container: Container, issues: list[Issue])` (configs/sims filled in Task 9; until then empty lists).
- Rules (verbatim from research `docs/research/ork-format.md` §AXIAL POSITIONING / AUTO DIMENSIONS): AFTER/TOP/MIDDLE/BOTTOM/ABSOLUTE formulas; assembly length = Σ AFTER children; `getLength` per kind (fins = rootchord, freeform = x_last − x_first, rail button = 0, mass objects = packed length); auto radius chain (`front_auto`/`rear_auto`/`uses_next`/`uses_prev`/`bt_auto`, default 0.025); ring outer auto = min parent inner radius at ring front/back; centering-ring inner auto = max overlapping sibling inner-tube outer radius; tube-fin auto radius; mass-object volume-preserving auto length + OR stale-position quirk; stage numbering pre-order.

- [ ] **Step 1: Failing tests:** `test_oracle_geometry.py` parametrized over all oracle cases: for each component (pre-order index aligned with oracle `index`, skipping `Rocket`/assemblies for radii) assert `x_abs`, `length`, `fore/aft/ro/ri/bodyr` within the Global Constraints tolerances; Dual parachute body tube `resolved["fore_radius"] == pytest.approx(0.028321, abs=1e-9)` and an `ORK_STALE_AUTO` issue on it; drogue parachute `x_abs == pytest.approx(0.842975869, abs=1e-7)`.
- [ ] **Step 2:** FAIL. **Step 3:** Port `_inline_sequence`…`bt_auto` and position/length logic from `proto_parser.py:300-655` into pure functions; no global mutable state (pass a guard set).
- [ ] **Step 4:** PASS for all 75 fixture files. **Step 5:** Commit `feat(io): resolve ork positions and auto dimensions (matches OpenRocket 24.12)`.

---

### Task 9: Flight configurations, motors, recovery, stored simulations

**Files:** Create `src/stressaero/io/ork/configs.py`; Modify `src/stressaero/io/ork/__init__.py`; Test `tests/io/ork/test_configs.py`

**Interfaces:**
- Produces:
  - `@dataclass class MotorAssignment: mount_id: str; manufacturer: str; designation: str; digest: str | None; diameter: float; length: float; delay: float | None` (None = plugged)`; ignition_event: str; ignition_delay: float; overhang: float; count: int; motor_type: str`
  - `@dataclass class Deployment: device_id: str; event: str; altitude: float; delay: float`
  - `@dataclass class FlightConfiguration: id: str; name: str; is_default: bool; active_stages: frozenset[int]; motors: list[MotorAssignment]; deployments: list[Deployment]`; `display_name() -> str` (OR-style `"[J570W-14]"` when unnamed)
  - `@dataclass class DataBranch: name: str; columns: dict[str, np.ndarray]; events: list[tuple[float, str]]`; `@dataclass class StoredSimulation: name: str; config_id: str; conditions: dict[str, Any]; summary: dict[str, float]; branches: list[DataBranch]; provenance: Provenance` (Tier.OR_STORED)
  - `parse_configurations(doc: ParsedDocument) -> list[FlightConfiguration]`; `parse_simulations(doc: ParsedDocument, issues: list[Issue]) -> list[StoredSimulation]`
- Column keys: canonical save keys (`time, altitude, velocity_total, acceleration_total, mach, cg_location, cp_location, …`) mapped from English display names, 26.xx keys and symbol-suffixed names (port `TYPE_KEYS`, `proto_parser.py:768-830`).

- [ ] **Step 1: Failing tests:** Dual parachute v2412 → 6 configurations; default config motor designation `"J570W"`, manufacturer `"AeroTech"`; drogue deployment event `"apogee"`, main `"altitude"` with `altitude == pytest.approx(152.4)`; stored sim 3 `summary["maxaltitude"] == pytest.approx(2223.846, abs=1e-3)` and `"altitude" in branches[0].columns`; `launchrodangle` converted to radians; a sim XML with column `Höhe` keeps `columns["Höhe"]` and emits `ORK_UNKNOWN_COLUMN`.
- [ ] **Steps 2–4.** **Step 5:** Commit `feat(io): flight configurations, motors, recovery and stored simulations`.

---

### Task 10: OR-compatible mass model

**Files:** Create `src/stressaero/physics/massmodel.py`; Test `tests/physics/test_massmodel.py`, `tests/physics/test_oracle_mass.py`

**Interfaces:**
- Consumes: resolved `Rocket`, `FlightConfiguration`.
- Produces: `@dataclass(frozen=True) class MassProps: mass: float; cg_x: float; provenance: Provenance`; `component_mass_cg(c: Component) -> tuple[float, float]` (mass of all instances, CG x relative to the component front — matches oracle `compmass`/`compcgx`); `structure_mass(rocket: Rocket, config: FlightConfiguration) -> MassProps` (active stages only, overrides incl. subcomponent flags); `reference_length(rocket: Rocket, config: FlightConfiguration) -> float`; `rocket_length(rocket, config) -> float`.
- Method (port `proto_parser.py:1018-1280`): 128-frustum symmetric shells with normal wall thickness and shoulders/caps; fin planform strip integration incl. tabs and fillets, cross-section volume factors; rings, tubes, lugs, rail buttons, mass objects; parachute = canopy area·ρ_s + lines; overrides per `MassCalculation.calculateStructure` semantics. Provenance `Tier.ENGINEERING_OR`, `"mass.or_compat.24_12"`.

- [ ] **Step 1: Failing tests:** oracle-parametrized `compmass`/`compcgx` for every component and `structMass`/`structCG`/`refLen` for every stored sim's configuration (tolerances per Global Constraints; the logo-rocket freeform fin that extends past its parent is `xfail` with reason "fin beyond parent end: known gap"); unit test: a 1 m aluminium tube r=0.05, t=0.002, ρ=2700 → mass = ρπ(r²−(r−t)²)L exactly, cg = 0.5.
- [ ] **Steps 2–4.** **Step 5:** Commit `feat(physics): OpenRocket-compatible mass and CG model`.

---

### Task 11: Rocket display meshes

**Files:** Create `src/stressaero/viz/rocket_mesh.py`; Test `tests/viz/test_rocket_mesh.py`

**Interfaces:**
- Consumes: resolved `Rocket`, `FlightConfiguration`, `profile` (Task 5).
- Produces: `component_mesh(c: Component, *, segments: int = 72) -> pv.PolyData | None` (world frame: +x aft from nose tip, metres; all instances; `cell_data["component_index"]`); `rocket_meshes(rocket: Rocket, config: FlightConfiguration | None) -> dict[str, pv.PolyData]` (keyed by component id; inactive stages excluded; internal components flagged via `field_data["internal"]`).
- Geometry: symmetric components = closed revolved shells (outer + inner surface + end annuli; shoulders included); fins = planform polygon extruded by thickness, rotated about x by instance angle, canted about the fin's mid-root-chord radial axis; tube fins/lugs/rings/inner tubes = closed annular cylinders at instance offsets; rail buttons = stacked cylinders; mass objects/recovery = closed cylinders with packed size; pod/parallel-stage children offset by instance positions.

- [ ] **Step 1: Failing tests:** closed-shell volume of a body tube mesh within 1e-3 relative of π(r²−(r−t)²)L at 72 segments; nose cone mesh bounds x∈[0, L]; Dual parachute: fin set mesh has 3 connected bodies (`connectivity().n_regions == 3`) and max radial extent = body radius + fin height; Pods--airframes: meshes exist for every pod instance at radial offsets (bounds checks); inactive stage of Two stage high power excluded for a sustainer-only config.
- [ ] **Steps 2–4.** **Step 5:** Commit `feat(viz): rocket component meshes`.

---

### Task 12: Project files (`.saproj`)

**Files:** Create `src/stressaero/io/project.py`; Test `tests/io/test_project.py`

**Interfaces:**
- Produces: `PROJECT_SCHEMA_VERSION = 1`; `class ProjectFormatError(ValueError)`; `@dataclass class Project: ork_name: str | None = None; ork_bytes: bytes | None = None; selected_config_id: str | None = None; unit_system: str = "metric"; unit_overrides: dict[str, str] = field(default_factory=dict); settings: dict[str, Any] = field(default_factory=dict)`; `save_project(project: Project, path: Path) -> None` (ZIP: `project.json` + `assets/<ork_name>`; atomic write via temp file + replace); `load_project(path: Path) -> Project`; `Project.load_rocket() -> OrkImport`.

- [ ] **Step 1: Failing tests:** round trip preserves every field and ork bytes; `project.json` has `"schema_version": 1`; schema_version 99 → `ProjectFormatError` matching "newer version"; corrupt ork bytes → `load_project` succeeds but `project.load_rocket()` raises `OrkFormatError`; save over an existing file is atomic (original intact if writing fails — simulate by monkeypatching `zipfile.ZipFile.writestr` to raise).
- [ ] **Steps 2–4.** **Step 5:** Commit `feat(io): project save/load`.

---

### Task 13: Desktop UI shell

**Files:** Create `src/stressaero/ui/app.py`, `main_window.py`, `component_tree.py`, `inspector.py`, `viewport.py`; Test `tests/gui/test_main_window.py` (marker `gui`, run under xvfb)

**Interfaces:**
- Consumes: `load_ork`, `structure_mass`, `reference_length`, `rocket_meshes`, `Project` APIs, `units`.
- Produces:
  - `ui/app.py`: `main(argv: list[str] | None = None) -> int` (flags: `--selftest` loads bundled sample without showing a window and prints `SELFTEST OK <components> <mass>`; positional path opens `.ork`/`.saproj`).
  - `MainWindow(QMainWindow)`: `open_path(path: Path) -> None`, `save_project(path: Path) -> None`, `set_unit_system(name: Literal["metric", "us"]) -> None`, `set_configuration(config_id: str) -> None`, `select_component(component_id: str | None) -> None`; attributes `tree: ComponentTree`, `inspector: Inspector`, `viewport: Viewport`, `config_combo: QComboBox`, `summary: QLabel`.
  - `ComponentTree(QTreeWidget)`: `populate(rocket: Rocket) -> None`, `select(component_id: str | None) -> None`, signal `componentSelected(str)`.
  - `Inspector(QTableWidget)`: `show_component(c: Component | None, system: UnitSystem, mass: tuple[float, float] | None) -> None` — rows: Name, Type, Position, Length, radii/fin dims as applicable, Material (+density), Mass, CG, each value via `format_quantity`; mass row shows provenance badge text.
  - `Viewport(QWidget)`: `show_rocket(meshes: dict[str, pv.PolyData], cg_x: float | None, cp_x: float | None = None) -> None`, `highlight(component_id: str | None) -> None`, signal `componentPicked(str)`; uses `QtInteractor`, left-click cell picking → component id; internal parts 30 % opacity; CG marker (black/white disc icon + label).
  - Menus: File (Open… Ctrl+O, Save Project Ctrl+S, Save Project As…, Recent, Exit), View (Units: Metric / US customary, Reset camera), Help (About with version + licences). Status bar shows import issues count; Issues dock lists `Issue`s.
- Errors: any exception from loading shows `QMessageBox.critical` with the message; app stays usable.

- [ ] **Step 1: Failing tests (pytest-qt):** open Dual parachute → tree has 20 items and config combo 6 entries; selecting the nose cone in the tree highlights it in the viewport (`viewport.highlighted == id`) and inspector shows `"283.2 mm"` length in metric and `"11.15 in"` after `set_unit_system("us")`; programmatic viewport pick at a fin's projected centre emits `componentPicked` with the fin set id; summary label contains `"1361"` (g, structure mass) for the default config; save → reopen project restores unit system and selected config; opening a corrupt `.saproj` shows a critical message box (monkeypatched) and leaves the window open; `main(["--selftest"]) == 0`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement; keep logic thin (all computations come from lower layers).
- [ ] **Step 4:** `xvfb-run -a pytest tests/gui -v` → PASS. Also launch `xvfb-run -a python -m stressaero tests/data/openrocket/v2412/<Dual parachute>.ork` with a 5 s auto-quit env var `STRESSAERO_AUTOQUIT_MS=5000` and save a screenshot to `docs/images/m1-main-window.png`.
- [ ] **Step 5:** Commit `feat(ui): main window with component tree, inspector, 3-D viewport, units and configurations`.

---

### Task 14: Windows packaging and installer CI

**Files:** Create `packaging/stressaero.spec`, `packaging/installer.iss`, `packaging/build_windows.ps1`, `packaging/assets/stressaero.ico`, `docs/user/INSTALL.md`; Modify `.github/workflows/ci.yml` (add `windows` job), `README.md`

**Interfaces:**
- Produces: `dist/StressAero/StressAero.exe` (PyInstaller onedir, windowed, `collect_all` for `vtkmodules`, `pyvista`, `pyvistaqt`, `PySide6` plugins `platforms`, `styles`, `imageformats`; bundles one sample `.ork` for `--selftest`); `StressAero-Setup-<version>.exe` (Inno Setup: per-user `{localappdata}\Programs\StressAero`, `PrivilegesRequired=lowest`, Start-menu + optional desktop shortcut, `.saproj` association, uninstaller).
- CI `windows` job (`windows-latest`, Python 3.12): `pip install -e .[dev]`; `pytest -m "not gui and not oracle"`; `packaging/build_windows.ps1` (PyInstaller → `dist\StressAero\StressAero.exe --selftest` must print `SELFTEST OK` → `iscc packaging\installer.iss`, installing Inno Setup via `choco install innosetup -y` if `iscc` is missing); upload installer as artifact `StressAero-Setup`.

- [ ] **Step 1:** Add CI assertion step: frozen `--selftest` output contains `SELFTEST OK`. Locally on Linux: `pyinstaller packaging/stressaero.spec` then `xvfb-run -a dist/StressAero/StressAero --selftest` prints `SELFTEST OK` (validates the spec's collection rules).
- [ ] **Step 2:** Push; verify the GitHub Actions `windows` job is green and the artifact exists (check via GitHub MCP `actions_list`/`get_job_logs`).
- [ ] **Step 3:** `INSTALL.md`: download artifact/release → run installer → SmartScreen "More info → Run anyway" → launch → open a `.ork`; system requirements (Windows 10/11 64-bit, OpenGL 3.2+ GPU driver).
- [ ] **Step 4:** Commit `build: Windows PyInstaller + Inno Setup installer via CI`.

---

### Task 15: Milestone wrap-up

**Files:** Modify `README.md` (features in M1, screenshot, quick start), `docs/dev/DEVELOPING.md` (oracle regeneration, packaging), `docs/superpowers/specs/...` only if a decision changed.

- [ ] **Step 1:** Full suite: `xvfb-run -a pytest -v` (Linux) → all pass (oracle-marked tests pass using committed JSON); CI green on both OSes.
- [ ] **Step 2:** Request a whole-branch review (superpowers:requesting-code-review) and fix findings.
- [ ] **Step 3:** Commit `docs: M1 readme and developer guide`; push.
