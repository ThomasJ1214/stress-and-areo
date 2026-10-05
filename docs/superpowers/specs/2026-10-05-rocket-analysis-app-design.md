# Stress & Aero — Rocket Aerodynamic, Flight and Structural Analysis Suite

**Design spec** · 2026-10-05 · status: approved in chat (pending written-spec review)

## 1. Purpose and success criteria

A Windows desktop application that lets a rocket designer take an OpenRocket `.ork` project and/or detailed
CAD files and answer, with transparent and traceable engineering:

- How does this rocket fly (6-DOF launch simulation with playback), and what are the aerodynamic loads,
  stability (CG/CP/margin), Mach, dynamic pressure, accelerations at every instant?
- What happens in wind, gusts and turbulence; how sensitive is it (sweeps, Monte Carlo)?
- Do the structures survive (airframe, fins, bulkheads, couplers, recovery shock), and with what margin?
- How do these answers change when an OpenRocket placeholder part is replaced by the real CAD geometry?

**Success** = a team member can install with one installer, open their `.ork`, pick a flight configuration,
simulate, watch the launch with aero/structural overlays, swap in a STEP payload, and get a comparison report —
where every number states which method produced it and its validity range, and the important methods are
regression-tested against OpenRocket and published/analytic references.

### 1.1 User constraints (from preliminary questions)

| Topic | Answer | Design consequence |
|---|---|---|
| Flight regime | up to ~Mach 3 | transonic + supersonic aero methods and CFD with shocks; aeroheating out of scope |
| Hardware | strong desktop (8+ cores, 32 GB+, dGPU) | local CFD/FEA at accuracy-oriented mesh sizes; GPU used for rendering only |
| Sharing | private / team use | GPL tools may be bundled; they still run as **separate processes** to keep the core licence-clean |
| Materials | cardboard/phenolic/wood, FG/CF composites, 3-D prints | orthotropic + laminate (CLT) analysis, anisotropic prints, material DB with sources |
| OpenRocket | 23.09 / 24.x | read formats 1.0–1.10 (+ tolerant 1.11); OR-compatible engine pinned to 23.09 and 24.12 |
| Configurations | single stage, dual deploy | simulation v1 = single stage incl. drogue + main; deployment shock loads modelled physically. Multi-stage / pods / parallel stages are imported and displayed, simulation warns "not supported in v1" |
| Runtime | accuracy first | long CFD/FEA runs are a normal workflow → background jobs, progress, cancel, resume, caching |
| Test data | public + generated; user adds own later | analytic fixtures + OpenRocket examples + OR headless oracle; `tests/data/user/` slot for team files |

### 1.2 Priorities (from the request, in order)
1 correct & transparent calculations · 2 OpenRocket integration · 3 CAD replacement · 4 reliable simulations ·
5 interactive 3-D viewer · 6 easy Windows install · 7 performance · 8 polished UI.

### 1.3 Non-goals (v1)
Aeroheating/ablation; multi-stage, clustered-booster and pod *simulation* (import/display only); active control /
airbrakes; real-gas effects; aeroelastic time-domain coupling (flutter is a stability check, not a coupled sim);
editing rocket geometry beyond what is needed for CAD replacement (OpenRocket remains the design tool).

## 2. Feasibility evidence (research summary)

Full notes and prototypes: `docs/research/`. Highlights that drive this design:

- **.ork import** — ZIP/GZIP/plain-XML container; 23 component types; positions/auto-dimensions must be
  *re-derived* (155/252 stored `auto` values in official samples are stale). A stdlib prototype matched
  OpenRocket 24.12 on all 71 official samples: positions ≤6e-5 m, radii ≤8e-15 m, structure mass ≤6.4e-6
  relative, CG ≤4.8e-6 m. Motor curves are *not* in the file; OR's MD5 motor digest was ported and matches
  ThrustCurve.org files.
- **OpenRocket methods** — a Python port of OR 24.12's Barrowman calculator matched OR to ~1e-14 (worst 9e-5)
  over Mach 0.05–3. OR has documented/verified gaps at our Mach range: supersonic fin CNα ≈ ½ of linear theory
  (single-surface Busemann), tangent-ogive wave drag ≈ 0 (bug), base drag 0.25/M with no power-on correction,
  ad-hoc ×3 pitch damping, instantaneous parachute opening (deployment "shock" spikes of 700–1000 m/s² are
  artefacts). OR 23.09/24.12 jars run headless via JPype/Java 21 and serve as a regression oracle.
- **CAD** — OpenCASCADE 8.0.1 via `cadquery-ocp-novtk` gives exact B-rep mass properties (1e-13), assembly names
  and transforms, exact sections, B-rep outer-skin (OML) extraction, glTF/STL export. OCCT can silently
  corrupt a STEP round-trip → dual validation is mandatory. Alignment of random-pose meshes to OR components:
  axis ≤1.5e-6°, centring 0.02 mm, units inferred 4/4.
- **GUI** — PySide6 6.11 + pyvista 0.49/VTK 9.7 + pyqtgraph verified headless (Xvfb/Mesa): heatmaps, glyphs,
  cell picking → part name, timeline cursor driving the model.
- **CFD / FEA** — SU2 v8.5 (Linux/Windows binaries, OpenMP build) and CalculiX were exercised in research runs;
  their detailed findings are recorded in `docs/research/cfd.md` and `docs/research/fea.md` and are binding
  inputs to Milestones 6–7 (method details there take precedence over this summary).

## 3. Technology stack

| Concern | Choice | Notes |
|---|---|---|
| Language/runtime | Python 3.12 (64-bit) | ecosystem has dropped 3.11 (numpy 2.5, scipy 1.18) |
| UI | PySide6 (Qt 6) | docking workspaces, property inspector, model/view trees |
| 3-D | pyvista + pyvistaqt (VTK 9.7) | picking, scalar fields, glyphs, streamlines, animation, offscreen screenshots |
| 2-D plots | pyqtgraph (interactive), matplotlib (reports) | linked time cursors |
| Numerics | numpy, scipy | vectorised; `numba` only if profiling demands |
| CAD kernel | `cadquery-ocp-novtk==8.0.1.1.0` (OCCT 8.0.1) behind `geometry/occ_adapter.py` | pinned; all OCP calls isolated (OCP 8 broke 7.x APIs) |
| Mesh utilities | trimesh, manifold3d, shapely, meshio | mesh IO, repair, fast slicing, 2-D sections |
| Meshing | gmsh 4.15 **as separate process** (`gmsh.exe` from SDK / frozen mesher worker) | GPL isolation; MeshSizeMin always set; time-limited |
| CFD | SU2 v8.x (OpenMP Windows build) as subprocess | Euler + RANS (SA/SST); VTU output |
| FEA | CalculiX `ccx` (Windows build, PARDISO/SPOOLES) as subprocess | shells incl. composite layups, solids, `*BUCKLE`, `*FREQUENCY` |
| OR oracle (optional) | OpenRocket 24.12 jar + Temurin JRE 21, Java helper run as subprocess | cross-validation feature + CI regression |
| Motors | ThrustCurve.org snapshot (bundled) + `.eng`/`.rse` import + optional online refresh | digest matching |
| Reports | Jinja2 → self-contained HTML; PDF via reportlab; CSV/JSON/VTU exports | |
| Packaging | PyInstaller (onedir) + Inno Setup (per-user, no admin) | built by GitHub Actions `windows-latest` |
| Tests | pytest, pytest-qt (offscreen), hypothesis for invariants | Linux + Windows CI |

Package name: `stressaero` (repo `stress-and-areo`). Display name: **Stress & Aero**.

## 4. Architecture

```
src/stressaero/
  core/        units, quantities, provenance, data model (pure Python, no I/O, no GUI)
  io/          ork/ (reader, writer), motors/ (eng, rse, thrustcurve db, digest), cad/ (import facade),
               project/ (.saproj read/write), export/
  geometry/    occ_adapter (all OpenCASCADE calls), primitives (OR component → B-rep/mesh), oml, sections,
               alignment, massprops
  physics/     atmosphere (US76), gravity (WGS84), wind (profiles, Dryden/von Kármán, gusts), materials
  aero/        api (AeroModel protocol, AeroTable), or_compat/ (OR 23.09/24.12 port), extended/ (Mach 0–3
               engineering), geometric/ (equivalent body + local inclination on OML), cfd_tables/ (SU2-derived)
  flight/      6dof (state, EOM, integrator, events), rail, recovery (inflation/opening shock), motors (runtime
               mass/CG/inertia), simulation (orchestrator), results (time history)
  structures/  api, loads (distributed aero + inertial relief), beam, tubes, buckling, laminate (CLT, failure),
               fins (root stress, flutter), bulkheads, recovery_loads, margins
  solvers/     cfd/ (gmsh meshing driver, SU2 config/run/monitor/post), fea/ (model build, ccx run/parse), mesher
  jobs/        job model, worker process pool, progress protocol, cancel, cache (input-hash keyed)
  studies/     sweeps, Monte Carlo (LHS/Sobol), comparisons
  oracle/      OpenRocket subprocess driver + comparison
  viz/         scene builders (rocket, overlays, fields, flight scene), colormaps, legends — return pyvista objects
  ui/          main window, workspaces, panels, dialogs, timeline, theme
  report/      report model, HTML/PDF renderers
tools/         build scripts, solver fetchers, data snapshot scripts
tests/         unit/, validation/, regression/, gui/, data/ (fixtures; data/user/ for team files)
docs/          user guide, developer guide, methods/ (one document per method family), research/, superpowers/
packaging/     pyinstaller spec, inno setup script, icons
```

**Dependency rule:** `core` ← `physics`/`geometry`/`io` ← `aero`/`flight`/`structures`/`solvers` ← `jobs`/`studies`/
`oracle` ← `viz`/`report` ← `ui`. Lower layers never import upper ones; nothing below `ui` imports Qt.
Enforced by an import-linter test.

### 4.1 Swappable engines (plugin registry)

Each analysis family has a small protocol and a registry keyed by method id:

```python
class AeroModel(Protocol):
    id: str                    # e.g. "aero.or_compat.24_12", "aero.extended.v1", "aero.cfd_table"
    tier: Tier
    def coefficients(self, geom: AeroGeometry, cond: FlowCondition) -> AeroCoefficients: ...
    def validity(self) -> ValidityBand: ...
```

Likewise `StructuralModel`, `CFDSolver`, `FEASolver`, `CADImporter`, `RocketImporter`, `MotorSource`.
Results are plain dataclasses (numpy arrays inside), serialisable to the project file. Replacing a solver =
registering a new implementation; the UI lists registered methods per family.

### 4.2 Provenance (the honesty mechanism)

Every numeric result object carries `Provenance(tier, method_id, method_version, inputs_hash, validity,
warnings, references)`.

| Tier | Badge | Meaning |
|---|---|---|
| `ESTIMATE` | grey "Estimate" | heuristic or user-assumed values (e.g. 3-D-print effective density, default Cd) |
| `ENGINEERING_OR` | blue "Engineering (OpenRocket method)" | faithful port of OpenRocket 23.09/24.12 |
| `ENGINEERING` | blue "Engineering" | published semi-empirical / analytical methods (Barrowman+, linear supersonic theory, CLT, Roark…) |
| `GEOMETRIC` | teal "Geometry-based" | methods evaluated on the real OML (equivalent body, local inclination, exact sections) |
| `CFD` | green "CFD (SU2 Euler/RANS)" | numerical solution; shows mesh size, convergence level, turbulence model |
| `FEA` | green "FEA (CalculiX)" | numerical solution; shows element type/count, convergence check |
| `INTERPOLATED` | modifier "· interpolated" | value interpolated between solved points (tables, CFD database) |

Rules: (1) UI shows the badge next to every number, plot and overlay; (2) validity violations (e.g. Mach 0.8–1.2 for
engineering tiers, AoA beyond range) show an amber flag with the reason; (3) mixed-tier composites (e.g. flight using
CFD tables at some Mach and engineering elsewhere) report the tier per segment; (4) reports print the provenance table;
(5) no plot or overlay is drawn without a backing result (no decorative "flow lines").

## 5. Data model (core)

- **Project** — rocket source (`.ork` reference + embedded copy), CAD replacements, materials overrides,
  simulation setups, studies, results cache, UI state. Saved as `.saproj` (ZIP: `project.json` + `assets/` (ork, CAD)
  + `results/` (npz, vtu)). Versioned schema with migrations.
- **Rocket** — component tree mirroring OpenRocket's (id = OR UUID for format ≥1.9, tree path for older), with
  resolved absolute geometry (SI), per-component material, finish, overrides, and the *file value vs recomputed
  value* for auto dimensions (with warnings when they differ).
- **FlightConfiguration** — id, name, motor per mount (manufacturer, designation, digest, delay, ignition), recovery
  deployment per device (event, altitude, delay), resolved motor curve (with source and match quality).
- **Replacement** — target component id, CAD asset (file hash), selected leaves, unit, 4×4 transform, flip/roll,
  per-part materials and density, measured mass/CG overrides (with chosen model), superseded subcomponents,
  structural tags. Non-destructive: original OR component remains and can be toggled.
- **ResolvedVehicle** — what engines consume: OML (B-rep + tessellation, component-tagged faces), mass model
  (component masses, CG, full inertia tensor; motor time-dependence), aero geometry descriptors (body profile r(x),
  A_enc(x), fins, protuberances, non-axisymmetry flag), structural model descriptors (sections A_mat/I(x), joints, fins).
  Two variants can be resolved side-by-side: `original` (OR geometry) and `detailed` (with replacements).
- **Material** — isotropic / orthotropic (E1, E2, G12, ν12, strengths Xt/Xc/Yt/Yc/S, density) with `source`,
  `confidence`, `notes`; laminates as ply stacks; 3-D-print materials with raster/Z derates.

Internal units are SI everywhere; angles in radians internally. Display units come from a unit system
(Metric / US customary) with per-quantity overrides; conversion happens only in `ui`/`report`.

## 6. Engineering methods

Detailed equations, references and validation status live in `docs/methods/*.md` (one per family, written in the
milestone that implements it). This section fixes the method choices.

### 6.1 Aerodynamics

**Tier ENGINEERING_OR (OpenRocket-compatible).** Bit-for-bit port of OR 24.12 (and 23.09 switches) per the research
notes: Barrowman/Galejs body terms, Diederich subsonic fins, OR's supersonic fin K-terms and transonic quartic bridge,
fin-body τ factor, roughness-limited Cf with OR compressibility factors, OR nose-drag tables (Stoney TR-R-100),
stagnation/base drag, OR atmosphere approximations (a = 165.77 + 0.606T, linear μ), 293.15 K component-analysis
default. Purpose: reproduce OR to ≤1e-6 relative for validation and user trust. Known OR defects are reproduced and
listed in a "Differences from OpenRocket" panel.

**Tier ENGINEERING (extended, Mach 0–3).** Replaces OR where it is wrong or missing:
- normal force/CP: Barrowman (subsonic) body + Jorgensen viscous crossflow with Cd_c(M_c); supersonic body via
  second-order shock-expansion / Van Dyke hybrid for nose CNα and CP; fins via two-surface linear theory
  (Ackeret/Evvard) with Mach-cone tip and root corrections; fin–body interference K_W(B), K_B(W) per NACA Report 1307;
  transonic band 0.8–1.2 bridged by monotone interpolation and flagged `INTERPOLATED`.
- drag: compressible skin friction (Van Driest II) with transition and roughness; nose wave drag by second-order
  shock-expansion (ogives, arbitrary profiles) and Taylor–Maccoll (cones); fin thickness wave drag (supersonic
  thin-airfoil by leading-edge/airfoil type); base drag with power-on/off correlations; protuberances (lugs, rail
  buttons); transonic drag rise.
- damping: Cmq + Cmα̇ from slender-body/fin contributions, supersonic roll damping; cant-induced roll.
- exact ISA/US76 thermodynamics and Sutherland viscosity.

**Tier GEOMETRIC (real CAD shape).** For vehicles with CAD replacements: equivalent body of revolution from exact
A_enc(x) (slender-body CNα distribution dC_N/dx = (2/A_ref)(dA/dx)α, area-rule wave drag via von Kármán integral at
supersonic Mach), local-inclination surface methods (modified Newtonian + tangent-cone/tangent-wedge + Prandtl–Meyer)
on the triangulated OML for Mach ≥ ~1.5, wetted-area friction from the real surface, protuberance frontal-area drag.
A non-axisymmetry flag recommends CFD when the shape violates slender-body assumptions.

**Tier CFD (SU2).** See §7. Produces force/moment coefficients, surface Cp, and volume fields at chosen (Mach, AoA,
Re) points; converted into `AeroTable`s usable by the flight simulator and into field snapshots for visualisation.

**AeroTable.** All tiers can be sampled into a table over (Mach, α, [Re]) holding CN, CA, Cm, Cmq, Cl-roll terms,
CP, per-component breakdown and provenance per cell. Flight simulation consumes tables (fast, uniform); engineering
tiers can also be called directly.

### 6.2 Flight simulation

- 6-DOF rigid body, ECEF-free flat/spherical local frame (configurable), quaternion attitude, full inertia tensor
  with time-varying mass/CG/inertia from motor depletion, Euler's equations including ω×Iω (no OR simplifications);
  optional jet damping.
- Phases: on-rail (1-DOF along rail; rail exit from rail-button/lug geometry, not full rail length), free flight,
  recovery. Integrator: adaptive DOP853/RK45 (scipy) with event location for rail exit, burnout, apogee, ejection
  (motor delay), drogue/main deployment (event/altitude/delay per OR config), line stretch, full inflation, landing.
- Recovery: deployment sequence with snatch and canopy inflation (Knacke filling time t_f = n·D0/V, Cd·S(t) growth law,
  opening-load factor), optional two-body model with elastic shock cord (stiffness/damping from cord material);
  outputs shock-cord tension and airframe deceleration for structures.
- Environment: US Standard Atmosphere 1976 with site temperature/pressure offsets; WGS84 gravity; wind = constant /
  power-law / log / multi-level table + direction; turbulence = Dryden (MIL-HDBK-1797) or von Kármán with seed;
  1-cosine gusts; launch rail length/angle/azimuth, launch-into-wind option.
- Motors: thrust curve, propellant mass from impulse fraction, motor CG(t)/inertia; ThrustCurve snapshot + `.eng`/`.rse`;
  OR digest matching with fallback by designation (warning).
- Outputs: full time history (state, forces/moments per component, Mach, q, AoA, sideslip, CP/CG/margin, accelerations,
  loads inputs), events with exact times, summary (apogee, max velocity/Mach/accel/q, rail-exit velocity, descent
  rates, drift, landing point).
- Validation: OR-compatible mode reproduces OR trajectories (no-wind, fixed seed) within tolerance; extended mode
  validated by convergence studies, analytic cases (vacuum ballistic, constant-drag), and documented differences.

### 6.3 Structures (engineering tier)

- Loads at any flight instant: distributed aero normal force (from the aero model's per-station dCN/dx or CFD surface
  pressure), axial drag, thrust, inertial relief (d'Alembert, rigid-body accelerations incl. rotational) → axial
  force, shear and bending moment along x (beam with lumped/distributed masses), checked by global equilibrium.
- Airframe tubes: axial + bending stress, combined; orthotropic tubes via CLT; buckling — thin-cylinder classical with
  NASA SP-8007 knockdown, orthotropic cylinder buckling, Euler column of the whole airframe; couplers/joint bending.
- Laminates: CLT ABD, ply stresses, first-ply failure (Tsai-Wu, Hashin, max-stress), margins.
- Fins: root bending/shear as cantilever plate under aero pressure + inertia; fin-can/epoxy fillet shear;
  flutter — NACA TN 4197 (Martin form, reported as a screening estimate) and a typical-section / piston-theory flutter
  check using plate modal frequencies (analytic plate estimates in engineering tier, CalculiX modes in FEA tier);
  divergence.
- Bulkheads/centering rings: Roark plate formulas; shear pins/screws bearing and shear-out.
- Recovery: ejection-charge pressure (ideal gas, black powder sizing), opening-shock loads from §6.2, shock-cord and
  attachment loads, zipper risk indicator.
- 3-D prints: raster/Z-direction derates, infill/perimeter effective properties (ESTIMATE tier unless user supplies
  test data).
- Margins: MS = allowable / (FS · applied) − 1 with user factor of safety; worst-case over the flight timeline;
  heatmaps on the 3-D model.

### 6.4 Material database
Bundled JSON (`data/materials/*.json`) with values, ranges, `source` citation and `confidence` per property
(sources: CMH-17, FPL Wood Handbook, manufacturer TDS, etc.). User materials stored in the project and a user library.
No value is shown without its source/confidence on hover.

## 7. High-fidelity solvers

### 7.1 CFD (SU2)
- **Geometry**: whole-rocket OML (B-rep fuse of OR-generated solids + CAD OMLs) → STEP → gmsh worker.
- **Meshing**: farfield domain; surface sizing from curvature with MeshSizeMin; boundary-layer prisms for RANS where
  robust, else Euler + engineering skin-friction correction (labelled as such). Mesh presets (coarse/medium/fine) plus a
  mesh-independence study option (3 levels, Richardson extrapolation of CD/CNα).
- **Solver**: SU2 compressible Euler / RANS (SA, SST); low-Mach handling per research findings; AoA sweeps; Mach
  sweeps; "flight database" mode (Mach × AoA grid over the simulated envelope) and "key moments" mode (CFD at the
  exact Mach/AoA/altitude of rail exit, max-q, max Mach, burnout, apogee-approach).
- **Convergence**: residual drop target + Cauchy criterion on CD/CL/CMz; non-converged runs are flagged and never
  silently used.
- **Progress bar (required)**: multi-stage job progress — `Geometry → Mesh → Solve (case k of N) → Post-process`;
  during solve, live iteration count, residual history (log plot), coefficient history, iterations/s and ETA, mesh size;
  pause/cancel; resume from restart files. Implemented by the job system tailing SU2 `history.csv` and gmsh logs.
- **Outputs**: forces/moments per component (marker groups), surface Cp/Cf (mapped to component faces), volume VTU
  fields (Mach, pressure, density, velocity) for visualisation; aero tables; surface pressure fields for structural
  load mapping.

### 7.2 FEA (CalculiX)
- **Model building**: from the resolved vehicle: airframe tubes and fins as shells (S8R; composite `*SHELL SECTION,
  COMPOSITE` layups), CAD parts as solids (C3D10) with `*ORIENTATION` for orthotropic/printed materials; gmsh worker
  meshing with physical groups per part; tie/contact simplifications documented.
- **Loads**: mapped from a selected flight instant (engineering loads or CFD surface pressure + inertial body forces),
  recovery shock cases, user-defined cases; constraints via inertia relief (free-free with balanced loads).
- **Analyses**: linear static, linear buckling (`*BUCKLE`), modal (`*FREQUENCY`) feeding flutter; results parsed
  from `.frd/.dat` to VTU: von Mises, ply failure indices, displacement (deformation display with scale factor).
- **Verification**: analytic benchmarks in CI (plate, cantilever, cylinder buckling with knockdown commentary).
- Same job/progress system as CFD (stage progress, solver log tail, cancel).

## 8. Visualisation and UI

### 8.1 Main window
- **Left** project tree: rocket components (OR tree with replacement badges), flight configurations, CAD assets,
  simulations, studies, CFD/FEA runs, reports.
- **Centre** 3-D viewport (pyvista/VTK): orbit/pan/zoom, view presets, section view, transparency, part picking →
  inspector; overlay toggles (CG, CP with margin bar, force vectors per component, pressure heatmap, stress/margin
  heatmap, deformation with scale, CFD streamlines/slices, wind/velocity vectors, axes, dimensions).
- **Right** inspector: properties of the selected item, with units and provenance badges.
- **Bottom** timeline + linked plots (pyqtgraph): altitude, velocity, Mach, q, acceleration, AoA, stability margin,
  loads, worst margin; event markers (rail exit, max accel, max q, burnout, apogee, drogue, main, landing) — click to jump.
- **Workspaces**: Design (import, configs, replacements), Aero, Flight, Structures, CFD, FEA, Studies, Compare, Report.
- Global unit system toggle (Metric / US customary) + per-quantity overrides; all numeric inputs unit-aware.
- Long tasks never block the UI; a jobs panel lists running/queued jobs with progress bars and cancel.

### 8.2 Launch playback with aerodynamics ("watch the full launch")
- Flight scene: ground plane with launch rail, trajectory trail, rocket at the interpolated state for time t, camera
  modes (follow, chase, ground observer, free), playback speed (0.1×–50×), play/pause/scrub, jump-to-event.
- Per-frame aero overlays from the time history: relative-wind vector, AoA/sideslip arcs, Mach/q/altitude HUD,
  per-component aero force vectors and total force at CP, CG/CP markers with margin, thrust vector, drag.
- Surface pressure per frame:
  - engineering tiers: estimated Cp distribution from the tier's per-station model (labelled `ENGINEERING`/`GEOMETRIC`);
  - CFD database or key-moment CFD available: surface Cp and volume fields (streamlines, Mach slices) from the nearest
    solved (Mach, AoA) points, blended and labelled `CFD · interpolated` with the distance to the nearest solved point.
- Structural overlay per frame: margin heatmap from the engineering structures model evaluated at that instant
  (and FEA results at instants where FEA was run).
- Without CFD data the scene shows only quantities backed by results (forces, CP, estimated Cp) — never fake
  streamlines.

### 8.3 CAD replacement workflow (Design workspace)
Select OR component → "Replace with CAD…" → import (STEP/STP, IGES, STL, OBJ, PLY, 3MF, GLB) → validation report
(BRepCheck, B-rep vs mesh volume, watertightness, solids/surfaces) → part list with materials/densities (+ measured
mass/CG override; both override models shown) → automatic fit (units, axis, direction by profile, fore-face snap; roll
from user or feature snap) with ΔR/ΔL and interference report → superseded-subcomponent checklist → accept. The viewer
shows original vs detailed (toggle, ghost overlay, side-by-side). OML and mass properties update downstream; caches
invalidate by input hash.

### 8.4 Comparison
Any two (or more) resolved variants/configurations/runs: tables and overlaid plots for mass/CG/inertia, CNα/CP/margin vs
Mach, drag breakdown vs Mach, trajectory summaries, load and margin envelopes; a "what changed" summary with
provenance. Original-vs-detailed is a one-click comparison.

## 9. Studies
- Parameter sweeps (1-D/2-D) over any numeric input (wind speed/direction, launch angle, mass, CG shift, Cd multiplier,
  motor, rail length, deployment altitude…), wind sweeps preset.
- Monte Carlo: user-defined distributions (normal, uniform, triangular) for thrust scale/burn time, mass, CG, CD and CNα
  multipliers, wind speed/direction/turbulence seed, launch angle, fin misalignment; LHS/Sobol sampling; parallel
  worker processes (Windows spawn-safe); outputs: apogee/velocity/margin distributions with confidence intervals,
  landing ellipse (2σ/3σ), probability of exceeding load limits.
- All studies run as jobs with progress and are reproducible from a stored seed.

## 10. Reports and export
HTML (self-contained) and PDF reports: rocket summary, configuration, methods & provenance table, aero tables/plots,
flight summary and plots, events, structural margins (worst cases with locations), CAD replacement summary, comparisons,
warnings/validity flags. Exports: CSV/JSON time histories and tables, VTU/VTK fields, STL/STEP OML, `.ork` round-trip
with `overridemass`/`overridecg`/`overridecd` for replaced parts (explicitly notes OpenRocket's inertia limitation).

## 11. Jobs, performance and caching
- Job = typed request + inputs hash → worker process (multiprocessing spawn / external solver subprocess) → progress
  events (stage, fraction, message, metrics) over a queue → result stored in the project results cache.
- Cache invalidation by content hash of the resolved inputs; results reused across sessions.
- Fast tiers run synchronously when < ~100 ms, else as jobs. Aero tables are computed once per resolved vehicle.
- External solvers get thread counts from settings (default: physical cores − 1).

## 12. OpenRocket oracle (cross-validation)
Optional component: OpenRocket 24.12 jar (+23.09) with a bundled Temurin JRE 21, driven by a small Java helper run as a
subprocess (no in-process JVM). Uses: (a) "Compare with OpenRocket" in the app (mass/CG/CP/CNα/drag per component and
trajectory with zero turbulence, fixed seed), (b) CI regression of the importer and OR-compatible engine. Stored `.ork`
simulation data is shown as "OpenRocket stored result" (rounded, random seed) and is never used as ground truth.

## 13. Error handling
- Import: structured warnings (stale auto values, unknown elements, missing motors, unsupported features such as
  multi-stage simulation), never silent; zip-slip/zip-bomb guards; defusedxml.
- CAD: validation report blocks mass properties for open/invalid geometry ("display-only, enter mass").
- Solvers: non-zero exit, divergence, non-convergence → job marked failed/flagged with log excerpt; results never
  partially substituted.
- Physics guards: validity bands, NaN/Inf checks on every engine output, equilibrium checks for loads.

## 14. Testing and validation strategy
- **Unit** tests for every formula (with reference values and sources), units, data model, parsers.
- **Analytic fixtures**: CAD solids with exact mass properties (from research), exact sections, vacuum/constant-drag
  trajectories, plate/beam/cylinder structural cases, Taylor–Maccoll cones.
- **OpenRocket regression**: official example `.ork` files (GPL, vendored under `tests/data/openrocket/` with
  attribution) and synthetic files; expected values generated by the OR 24.12 headless oracle and committed as JSON;
  importer and OR-compatible engine must match (positions/radii ≤1e-6 m, mass ≤1e-5 rel, CNα/CD/CP ≤1e-6 rel).
- **Literature validation**: Arcas Robin wind-tunnel data (NASA TN D-4013/D-4014, digitised with uncertainty), NACA
  1307 interference examples, other cases documented in `docs/methods/validation.md`; tolerance bands justified per case.
- **Solver verification**: SU2 cone at Mach 2 vs Taylor–Maccoll; CalculiX cantilever/plate/cylinder buckling vs theory
  (CI runs coarse versions; full versions as a manual `validation` suite).
- **GUI**: pytest-qt offscreen smoke tests per workspace, screenshot regression for key scenes.
- **Property tests**: invariances (frame rotations, unit round-trips, mass composition).
- CI: Linux (fast suite + headless GUI) and Windows (full suite + installer build + smoke-run the frozen app).

## 15. Packaging and installation
- PyInstaller onedir build of `stressaero` (+ separate frozen worker entry points), Inno Setup installer
  `StressAero-Setup-<version>.exe`: per-user install (no admin), Start-menu/desktop shortcuts, `.saproj` and optional
  `.ork` file associations, uninstaller.
- Bundled tools under `{app}/tools/`: SU2 (Windows OpenMP build), CalculiX ccx (Windows build), gmsh (SDK exe),
  optional OpenRocket jar + Temurin JRE; versions pinned in `tools/manifest.json` with SHA-256; fetched by
  `tools/fetch_tools.py` in CI.
- GitHub Actions: on every push run tests; on `windows-latest` build the installer artifact; on tags publish a
  GitHub Release. Unsigned installer → documented SmartScreen "More info → Run anyway" step.
- Beginner docs: `docs/user/INSTALL.md` (screenshots, step-by-step), `docs/user/QUICKSTART.md`.
- Developer docs: `docs/dev/DEVELOPING.md` (clone, `py -3.12 -m venv`, `pip install -e .[dev]`, run, test, build
  installer locally).

## 16. Milestones (delivery order)

| # | Milestone | Done when |
|---|---|---|
| M1 | Foundation: repo scaffold, CI, units/provenance/data model, `.ork` reader (all versions), mass model, OR-generated geometry, 3-D viewer with picking and inspector, project save/load, unit toggle, Windows installer pipeline | official OR samples import and match OR oracle values; app opens a `.ork` and shows the rocket; installer artifact builds in CI |
| M2 | Aero engineering tiers (OR-compatible + extended) + AeroTables + Aero workspace (CNα/CP/CD vs Mach & AoA, drag breakdown, CG/CP/margin in 3-D, condition inputs: Mach/airspeed, altitude, AoA, wind) | OR-compatible matches OR ≤1e-6; extended validated against references; UI shows provenance |
| M3 | Flight: 6-DOF, environment, motors DB/digest, dual-deploy recovery with opening shock, timeline playback scene with aero overlays, events, plots, OR trajectory comparison | OR-compatible trajectories match OR oracle; playback works end-to-end |
| M4 | CAD replacement: import/validate/align/mass/OML, original-vs-detailed comparison, GEOMETRIC aero tier | analytic fixtures pass; replaced payload changes mass/CG/aero as expected |
| M5 | Structures engineering tier + materials DB + margins heatmaps over the flight timeline + recovery loads | analytic structural cases pass; margins displayed per instant |
| M6 | CFD tier: meshing worker, SU2 runner with progress bar, convergence, key-moments & flight-database modes, fields in playback, CFD aero tables in flight sim | Mach 2 cone verification passes; a full CFD-backed playback works |
| M7 | FEA tier: model build, CalculiX runner with progress, static/buckling/modal, load mapping (flight instant / CFD), deformation display, flutter with modal input | analytic benchmarks pass; FEA at max-q instant displays |
| M8 | Studies (sweeps, wind sweeps, Monte Carlo), comparisons, reports and exports | reproducible studies; HTML/PDF report generated |
| M9 | Polish: UX pass, theme, docs, installer hardening, performance profiling | beginner install walkthrough verified on Windows CI smoke test |

Each milestone ends with tests green on Linux + Windows CI, docs updated, and a pushed, reviewable state.
