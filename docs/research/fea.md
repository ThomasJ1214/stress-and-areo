# Research: fea

_Written up on 2026-10-06 from the files left on disk by a hands-on research agent that was cut off before it wrote its report. The scripts, decks, logs and result JSON are committed in `docs/research/prototypes/fea/`. Binaries, `.frd`/`.vtu` results, the wine prefix, benchmark outputs and images exist only in the session scratchpad (`…/scratchpad/research/fea/`). Every run used a 4-vCPU VM (Intel Xeon @ 2.8 GHz, 15 GB RAM) with 2 threads. "Linux ccx" means the conda-forge `calculix 2.23` linux-64 build 8. Windows executables were run only under wine 9.0, never on Windows. Units are mm, N, MPa, t/mm³ and s. Numbers come from the artifacts unless marked [RECALL] (from memory or literature, not checked here) or "(interpretation)" (an inference from the artifacts, not separately tested). A few short checks were run during the write-up (PE imports, memory, solver availability, `.frd` node mapping, manual searches); they are marked "(write-up check)" and used under 2 CPU-minutes in total._

## Recommendation

**Build the FEA tier on CalculiX 2.23 from conda-forge (win-64, build 8), run as a separate process with its multithreaded SPOOLES solver.**

- **Why this build.** It passed every analytic benchmark it was given: static, linear buckling, modal, an orthotropic solid, modal dynamics and free-free load mapping. It is the smallest and most heavily patched Windows build. The same package family runs Linux CI, so the two platforms can be compared number for number.
- **What is not yet shown.** Three Windows builds gave identical answers under wine. No Windows executable has been run on real Windows. A Windows CI smoke test should be the first task of M7.

**What to bundle**

- **Package:** `calculix-2.23-pl5321h7abefab_8.conda` from `conda.anaconda.org/conda-forge/win-64` (2,625,351 B, SHA-256 `a6c1e75c092893d73d0bb3902cba9db7e14ba3fe4d2f8cd74cdfbc1bc041d1d1`), plus its runtime DLLs, copied app-local into `{app}/tools/calculix/`.
- **Bundle contents:** 12 files, 55.5 MB (15.8 MB zipped):
  - `ccx.exe`;
  - `openblas.dll`, `libblas.dll`, `liblapack.dll`, `libarpack.dll`;
  - `libgfortran-5.dll`, `libgomp-1.dll`, `libgcc_s_seh-1.dll`, `libquadmath-0.dll`, `libwinpthread-1.dll`;
  - `vcruntime140.dll`.
- **Licences:** ship ccx's GPL-2.0-or-later text and a source pointer: the Dhondt tarball plus the feedstock patches.

**How to run it**

- **Command:** `ccx.exe -i <job>`, run in the job directory.
- **Threads:** set `OMP_NUM_THREADS` and `CCX_NPROC_EQUATION_SOLVER` to physical cores − 1. CalculiX defaults to **1 thread**. Also pin `OPENBLAS_NUM_THREADS` [RECALL].
- **Failure detection:** treat any of these as a failure: a non-zero exit code (conda-forge exits with 201 on `*ERROR`), any `*ERROR` line, or an empty `.sta` file.

**Element choices**

- **Tubes, couplers, fins and bulkhead plates:** S8R (gmsh quad8, with a few S6 where gmsh cannot make quads).
  - Laminates use `*SHELL SECTION, COMPOSITE`, with one `*ORIENTATION` per part: local 1 = tube axis or fin root chord.
- **CAD and 3-D-printed parts:** C3D10 (gmsh tet10) with `*ELASTIC, TYPE=ENGINEERING CONSTANTS` and `*ORIENTATION` for the print axes.

**Analysis rules**

- **Linear static under inertia relief done by hand.** CalculiX 2.23 has no inertia-relief keyword (write-up check of the manual).
  - Apply the rigid-body acceleration with `*DLOAD … GRAV`.
  - Apply the angular acceleration as consistent nodal forces.
  - Support the model with a 3-2-1 statically determinate constraint.
  - Reject the run if the support reactions exceed 0.1% of the applied load.
- **`*BUCKLE` must request at least 10 modes.** One requested mode gave a lowest factor **19% too high**.
  - The FE buckling load is never a design value on its own. Always report γ·P with the NASA SP-8007 knockdown.
- **`*FREQUENCY`** with 8–10 modes for fins; this is the flutter input.
- **Recovery shock:** static analysis × dynamic load factor.
  - `*MODAL DYNAMIC` is for verification only, and only with hinged shell edges. Clamped shells crash ccx 2.23.
- **`NLGEOM` collapse of an imperfect tube:** expert or manual study only. It took 15 minutes for an 8.9k-node bay and stops at the limit point.
- **Never use `SOLVER=ITERATIVE CHOLESKY`.** It "converged" with a 27% displacement error.

**Results, loads and optional solvers**

- **Results:** read the ASCII `.frd` with our own reader (the prototype's `fea_common.read_frd`) and convert it to a pyvista VTU.
  - Keep the default 3-D expanded shell output for stresses and map it back to the mid-surface with the node rule verified in §3.
  - Use `OUTPUT=2D` only for displacements and mode shapes.
  - Do **not** import ccx2paraview (GPL-3.0) into the core.
- **Loads:** CFD loads use the conservative force mapping from `cfd.md`. Engineering-tier loads become pressure distributions. Thrust and recovery loads go on their attachment faces.
- **Optional fast solver:** Dhondt's self-contained `ccx_static.exe` (PaStiX) as a setting, enabled only if Windows-native benchmarks at 8–16 threads show a real gain.
- **Not in v1:** the MKL/PARDISO build. It adds about 330 MB, and redistributing GPL code with a proprietary library is an open question [RECALL].

**Spec changes this implies**

- §3: "CalculiX ccx (Windows build, PARDISO/SPOOLES)" becomes "conda-forge build, SPOOLES; PaStiX optional".
- §7.2: "constraints via inertia relief" is implemented by hand.
- §7.2: "ply failure indices" are not yet demonstrated.

### Milestone-7 pipeline (proposed)

1. **Geometry → mesh (gmsh worker process, as in the CFD tier)**
   - Shell parts are meshed on their mid-surfaces:
     - `Mesh.Algorithm=8`, `RecombineAll=1`, `RecombinationAlgorithm=1`, `SecondOrderIncomplete=1`;
     - tubes use a transfinite structured mesh (circle × extrude, `recombine=True`).
   - Solid parts are meshed with tet10, with `MeshSizeMin` always set.
   - One physical group per part and per load or support face. These become `*ELSET`/`*NSET` and face lists.
   - Sizing rules from the benchmarks:
     - at least 6 S8R per buckle half-wave (h = 4 mm on R = 49 mm was mesh-converged to 0.02%);
     - fins at h ≈ chord/30 (modes within 0.4% of a 4× finer mesh);
     - bulkheads at h ≈ R/16.
2. **Deck writer** (mm–N–MPa–t/mm³)
   - **Node order:** gmsh → ccx is the identity for quad8 and tri6. For tet10, swap the last two nodes: `[0..7, 9, 8]`.
   - **Line length:** at most 16 entries per line, with continuation lines.
   - **Composites:** each ply line reads `thickness,,MATERIAL[,ORIENTATION]`. The verified variant uses one `*ELASTIC, TYPE=ANISO` material per ply angle, pre-rotated by the deck writer.
   - **Orthotropic solids:** `ENGINEERING CONSTANTS` plus `*ORIENTATION, SYSTEM=RECTANGULAR` given by the a and b axes.
   - Elastic constants and densities come from the material database, with their source.
3. **Loads**
   - Each case comes from a selected flight instant (engineering tier or CFD), a recovery case or a user case.
   - CFD surface forces are mapped conservatively. Thrust and recovery loads are applied as face pressure or distributed nodal forces.
   - Inertia relief is applied as above, followed by the reaction gate.
   - Spin and pitch-rate (ω²) terms are added with `CENTRIF` when they matter (not tested).
4. **Solve**
   - One case per process, in its own directory, with the environment variables above. A per-case timeout is set and Cancel kills the process.
   - The solver is SPOOLES. Request `SOLVER=PASTIX` only with the optional build, and never request a solver that the shipped build does not contain. The conda-forge build exits with 201 and "PARDISO library is not linked" (write-up check).
5. **Post-process**
   - Eigen and buckling tables and reaction totals come from `.dat`; fields come from `.frd`.
   - VTU files are written per case: `DISP_k`, `STRESS_k` and `VONMISES_k`.
   - Shells: top, bottom and mid-surface values plus membrane and bending split. Composites: per-ply stresses rotated into ply axes, then failure indices (still to be built).
   - The deformed shape is shown with a scale factor (`warp_by_vector`, verified offscreen).
6. **Verify:** the CI suite below.
7. **Progress:** read ccx stdout stage lines:
   - "Determining the structure of the matrix";
   - "Factoring the system of equations using the symmetric spooles solver";
   - "Calculating the buckling factors…" (one stress-calculation line per mode follows);
   - "U^T*M*U=1.000000 for eigenmode k" during `*FREQUENCY`;
   - for `NLGEOM`, the `.sta` file's TOT TIME / step period and the `.cvg` residuals.

**Verification benchmarks for CI** (coarse meshes, all measured on the VM with 2 threads):

| ID | Case | Mesh | Reference | Measured | CI tolerance | ccx time |
|---|---|---|---|---|---|---|
| B1 | Wide clamped plate strip, 10 kPa | S8R, h = 10 mm (1,301 nodes) | w = ps⁴/8D, σ = 3ps²/t² | w −1.33%, σ +0.35% | w ±2%, σ ±1% | 0.4 s |
| B2 | Swept trapezoidal fin, 10 kPa | S8R, h = 5 mm (1,408 nodes) | Statics: F = pA, M = F·ȳ | M from root σ −0.085% | M ±0.2%; peak/average root stress 1.45–1.55 (regression) | 0.5 s |
| C1 | Square CFFF plate, modes 1–5 | S8R, h = 5 mm (1,281 nodes) | Leissa NASA SP-160 | −0.20 … −1.42% | ±2% | 1.1 s |
| C2 | Swept fin, modes 1–5 | S8R, h = 5 mm | Stored h = 1.25 mm values | ≤ +0.4% | ±1% | 1.1 s |
| D1 | Tension, print axes tilted | C3D10, LC 3 (7,667 nodes) | Exact rotated compliance | ≤1e-4% (print precision) | ±0.01% | 1.5 s |
| D2 | Orthotropic cantilever | C3D10, LC 3 | Timoshenko beam; σ at L/4 | w −1.6%, σ −0.05% | w −3…0%, σ ±0.5% | 1.5 s |
| E | Free-free mapped load, closed tube | C3D10, LC 4 (60k nodes; make coarser for CI, untested) | ΣF, ΣM; support reactions → 0 | F +0.012%, M +0.008%, reactions ≤0.028% | 0.1% | 18 s (+33 s Python) |
| F1 | Clamped circular plate | S8R, h = 3 mm (2,597 nodes) | Roark/Timoshenko w₀, σ_edge, σ_centre | +0.26 / +0.56 / −0.09% | ±1% | 0.9 s |
| F2 | Simply supported plate, step load | S8R, 20 modes | f₁ exact; DLF = 2 | f₁ −0.25%, DLF 2.035 | f ±1%, DLF 1.95–2.10 | 11.4 s |
| A0 | Aluminium tube buckling | S8R, h = 4 mm, 10 modes | E t /(R√(3(1−ν²))) | ratio 0.959 | 0.94–0.98 | 16.5 s |
| A1 | Quasi-isotropic laminate tube buckling | as A0 | Orthotropic Donnell | ratio 0.939 | 0.92–0.96 | 25.9 s |
| A-ev | Eigensolver guard | 10 vs 20 modes | — | 0.000% | ≤0.1% | +12 s |
| G | Imperfect `NLGEOM` collapse | S8R, h = 4 mm | SP-8007 | 0.735 × linear | manual suite only | 926 s |

- **Windows smoke test:** run `winrun/d1_tension.inp` (scratchpad) and check node 6 against the Linux values U = (0.3863623, 0.03186421, 0.07594857) mm.
- **Tolerance floor:** `.dat`/`.frd` print 6–7 significant digits, so no tolerance should be tighter than about 1e-5 relative.

**Expected cost.** The measured column uses 2 threads on the VM. The projection assumes desktop cores as fast as one vCPU and a 2–3× gain going to 8 threads. That gain is an assumption: SPOOLES gained only 1.36× from 1 to 2 threads, and nothing above 2 threads was measured.

| Job | Size | Measured | Projected on 8 cores | Memory |
|---|---|---|---|---|
| Fin modes | 1.4k S8R nodes | 1.1 s | <1 s | ~0.15 GB |
| Bay buckling, 10 modes | 8.9k / 15.7k shell nodes (≈61k / 107k equations) | 16–26 s / 29–45 s | 8–20 s | ≈1–1.5 GB (estimate) |
| Static, 140k equations (fin or C3D10 part) | 20.7k S8R / 45k C3D10 nodes | 14.7 / 23.9 s | 6–12 s | 1.3 / 1.5 GB (write-up check) |
| Static of a mapped CFD load | 60k C3D10 nodes | 18 s ccx + 33 s Python mapping | 8 s + vectorised mapping | ~2 GB (estimate) |
| Whole airframe shell model at h = 4 mm (1.2 m × 98 mm) | ~70k shell nodes, ~0.5M equations [projection] | — | 1–5 min | 5–15 GB [projection, from the manual's "32 GB → ~1M equations"] |
| `NLGEOM` imperfect bay | 61k equations | 926 s | 6–10 min | not measured |

## Key findings

### 1. Which ccx build to ship for Windows

**Candidates found on disk:**

| Candidate | Source | Size | Solvers built in | DLL imports (write-up check, pefile) |
|---|---|---|---|---|
| **conda-forge `calculix 2.23 pl5321h7abefab_8` (win-64)** | `conda.anaconda.org/conda-forge/win-64/calculix-2.23-pl5321h7abefab_8.conda`. Installed with `micromamba create --platform win-64 -c conda-forge calculix libblas=*=*openblas` (`ccxwin/conda-meta/history`) and collected into `winbundle_cf/` | `ccx.exe` 7,649,366 B (SHA-256 `2e9c75bb…8ee`); bundle 12 files, 55,466,668 B; `winbundle_cf.zip` 15,803,778 B (SHA-256 `8be1aa3e…69e1`) | SPOOLES 2.2 multithreaded (static) + ARPACK, plus the iterative solvers. Built with `-DSPOOLES -DARPACK -DMATRIXSTORAGE -DUSE_MT=1` (`recipe/Makefile_MT`). **No PARDISO, no PaStiX, no TAUCS**: `SOLVER=PARDISO` → "*ERROR in linstatic: the PARDISO library is not linked", rc 201 (write-up check on the Linux twin) | `libgcc_s_seh-1`, `KERNEL32`, `api-ms-win-crt-*` (UCRT), `libwinpthread-1`, `libblas`, `liblapack`, `libgfortran-5`, `libgomp-1`, `libarpack`. `libblas.dll`/`liblapack.dll` forward all 151/1,949 exports to `openblas.dll`, which imports `VCRUNTIME140` + UCRT |
| Dhondt / Brzegowy `calculix_2.23_4win.zip` → **`ccx_static.exe`** | Linked from dhondt.de (page saved as `web/dhondt.html`); built 2025-10-24 | zip 61,675,985 B (SHA-256 `87fc4e17…72e8`); exe 41,861,637 B (SHA-256 `e18360eb…c1f`) | SPOOLES + **PaStiX 6.4.0** (+ TAUCS per the README). Default solver is PaStiX: the manual's default order is SGI, PaStiX, PARDISO, SPOOLES, TAUCS | `KERNEL32` + UCRT only; fully self-contained |
| same zip → `ccx_dynamic.exe` + Intel oneAPI MKL 2025.2.1 | MKL DLLs in `winrun_pardiso/`; source not recorded (`mklwin/` no longer exists) | exe 41,877,727 B (SHA-256 `dc894b9c…669`) + about 332 MB of MKL DLLs (`mkl_rt.2`, `mkl_core.2`, `mkl_intel_thread.2`, `mkl_sequential.2`, `mkl_def/mc3/avx2/avx512.2`, `libiomp5md`) | SPOOLES + PaStiX + **PARDISO** (requires an explicit `SOLVER=PARDISO`) | + `mkl_rt.2.dll` |

- The zip also holds `ccx_i4.exe` (42.3 MB, needs MKL), `ccx_dynamic_i8.exe` (38.1 MB), cgx, tetgen and CAD converters. None of these were used.
- **Provenance of the conda-forge build.** Feedstock commit `9d06fb57` (2026-09-28); the banner reads "executable made on Mon Sep 28 09:17:36 2026". It carries about 45 patches:
  - upstream fixes up to `e9e57ed` (2026-09-17);
  - malformed-input hardening that ends in `*ERROR` with exit code 201 instead of a crash;
  - a Windows locale fix;
  - a requirement for SPOOLES build ≥1006, which fixes multithreaded-SPOOLES data races.

  Dhondt's binaries are plain upstream 2.23.
- **Threading.**
  - Per the manual (write-up check):
    - `OMP_NUM_THREADS` sets stiffness assembly, SPOOLES-MT and stress recovery, **default 1**;
    - `CCX_NPROC_STIFFNESS`, `CCX_NPROC_EQUATION_SOLVER` and `CCX_NPROC_RESULTS` override it per stage;
    - `NUMBER_OF_CPUS` caps the detected core count;
    - PARDISO follows `OMP_NUM_THREADS`, and MKL also reads `MKL_NUM_THREADS`.
  - The prototype's `run_ccx` set both `OMP_NUM_THREADS` and `CCX_NPROC_EQUATION_SOLVER`. Logs then show "Using up to 2 cpu(s)" for structure, stiffness, SPOOLES and stresses.
  - The one wine run without these variables used 1 CPU (`winrun/cf.log`).
  - Under wine, PaStiX reported "Number of threads per process: 2".
  - OpenBLAS is the pthreads build. Pinning `OPENBLAS_NUM_THREADS` to avoid oversubscription is [RECALL].
- **Windows binaries were executed, under wine only.** The runtime was wine64 9.0 (`Ubuntu 9.0~repack-4build3`, reporting itself as Windows 10), `WINEPREFIX=fea/wineprefix`. All three builds agree with each other and with Linux ccx to every printed digit:

  | Deck | conda-forge `ccx.exe` | `ccx_static.exe` (PaStiX) | `ccx_dynamic.exe` (PARDISO) | Linux ccx |
  |---|---|---|---|---|
  | d1 tension, LC 3 (22,839 equations): node 6 U (mm) | 0.3863623 / 0.03186421 / 0.07594857 (`winrun/`) | same (`winrun_static/`), 2.00 s | same (`winrun_pardiso/d1p`), 1.99 s | same, 1.50 s |
  | Composite tube, hinged, h = 3 mm, 3 modes (108,150 equations): λ₁ | 61.15484 (`winrun_buckle/a1cf.dat`) | 61.15484, 33.5 s | 61.15484, 32.5 s | — |

  Windows behaviour that wine cannot show is still unproven: file locking while tailing logs, killing the process tree, paths with spaces, antivirus scanning and native thread scaling.
- **Licences** (conda metadata unless marked):
  - CalculiX: GPL-2.0-or-later.
  - ARPACK 3.9.1, OpenBLAS 0.3.34 and the BLAS/LAPACK forwarders 3.11.0: BSD-3-Clause.
  - libgcc, libgfortran, libgomp and libquadmath 16.2.0: GPL-3.0-only WITH GCC-exception-3.1 (the runtime exception allows redistribution).
  - libwinpthread: MIT AND BSD-3-Clause-Clear.
  - `vcruntime140.dll`: Microsoft Visual C++ 2015–2022 Runtime licence.
  - UCRT: Microsoft Windows SDK licence. It ships with Windows 10/11, so it need not be bundled [RECALL].
  - SPOOLES: public domain [RECALL].
  - PaStiX and Scotch: CeCILL-C [RECALL]; hwloc: BSD [RECALL].
  - MKL: Intel Simplified Software License [RECALL]. Shipping it alongside a GPL binary is a legal question [RECALL].
  - Distributing GPL binaries obliges us to make the source available [RECALL]. Ship the source URL with its SHA-256 (`9c88385c…d6e7`, recipe) and the feedstock patches.
- **Decision.** Use conda-forge as the default:
  - it is small, patched and reproducible;
  - it is identical to the Linux CI build;
  - MT SPOOLES was confirmed under wine.

  Dhondt's `ccx_static.exe` is the optional PaStiX build. MKL/PARDISO is deferred.

### 2. Test cases (a)–(g)

**Summary**

| Case | Model | Reference | FE vs reference | ccx time (2 threads) |
|---|---|---|---|---|
| (a) Tube buckling | S8R, R 49, t 1, L 150, h 4/3/2 mm | Classical cylinder formula + NASA SP-8007 | Aluminium 0.959×; quasi-isotropic 0.939×; cross-ply 0.973× classical; mesh-converged | 16–127 s |
| (b) Fin root stress | S8R plate, t 3 mm, 10 kPa | Plate-strip theory; statics | Strip w +0.27%, σ +0.51%; fin root M −0.004%; peak σ **1.51× the beam average** | 0.4–15 s |
| (c) Fin modes | S8R plate | Leissa CFFF; strip estimates | Leissa −0.2…−1.7%; strip estimates +23% / +90% (unusable) | 1–31 s |
| (d) Orthotropic solid | C3D10 + `*ORIENTATION` | Exact rotated compliance; Timoshenko | ≤1e-4%; −1.5% | 1.5–24 s |
| (e) Load mapping | C3D10 cup, free-free | Force/moment integrals; reactions → 0 | +0.012% / +0.008%; reactions ≤0.028% | 18 s |
| (f) Bulkhead | S8R disk | Roark plate formulas; exact f₁; DLF 2 | ≤0.56%; f₁ −0.25%; DLF 2.035 | 0.9–11 s |
| (g) Imperfect cylinder | S8R composite, `NLGEOM` | SP-8007; linear `*BUCKLE` | Collapse 0.735× linear = SP-8007 design +0.5% | 926 s |

#### (a) Thin-tube buckling under axial compression: S8R, `*BUCKLE` (`test_a_tube_buckle.py`, `case_a/results_*.json`, `logs/a_*.txt`)

**Model**

- Geometry: R = 49 mm, t = 1 mm, L = 150 mm (R/t = 49).
- Mesh: gmsh transfinite circle extruded with `recombine=True`, giving structured S8R:

  | h | Grid | Nodes | S8R |
  |---|---|---|---|
  | 4 mm | 77 × 38 | 8,932 | 2,926 |
  | 3 mm | 103 × 50 | 15,656 | 5,150 |
  | 2 mm | 154 × 75 | 34,958 | 11,550 |

- Boundary conditions:
  - clamped: bottom DOF 1–6; top DOF 1, 2, 4–6, leaving axial motion free;
  - hinged: bottom 1–3; top 1, 2.
- Load: a 1,000 N reference load as consistent edge forces (1/6, 2/3, 1/6) on the top ring; `*BUCKLE` with 10 modes.

**Materials**

- Aluminium: E 70 GPa, ν 0.3.
- E-glass/epoxy unidirectional ply (illustrative values): E1 39, E2 8.6 GPa; G12 3.8 GPa; ν12 0.28; 8 plies × 0.125 mm.
- Laminate stiffness from CLT (script, quasi-isotropic layup):
  - A11 = A22 = 20,677 N/mm, A12 = 5,992 N/mm, A66 = 7,342 N/mm;
  - D11 = 2,307 N·mm, D22 = 1,582 N·mm, D16 = D26 = 60.4 N·mm;
  - B ≈ 2e-13 (symmetric layup).

**References**

- Isotropic: σ_cl = E t /(R√(3(1−ν²))), which gives P_cl = 266,193 N.
- Laminate: Donnell orthotropic cylinder, simply supported, with B = 0 and A16, A26, D16, D26 neglected. The script minimises over (m, n).
- NASA SP-8007 knockdown, γ = 1 − 0.901(1 − e^(−φ)):
  - isotropic: φ = √(R/t)/16;
  - orthotropic: φ = (1/29.8)·√(R/(D11 D22/(A11 A22))^¼).

**Results**

| Case | h (mm) | Classical P (N) | FE P_cr (N) | FE/classical | γ | γ·P_cl (N) | Time (s) |
|---|---|---|---|---|---|---|---|
| Aluminium, clamped | 4 / 3 / 2 | 266,193 | 255,326 / 255,250 / 255,221 | 0.959 | 0.681 | 181,205 | 16.5 / 29.2 / 88.5 |
| Aluminium, hinged | 3 | 266,193 | 253,915 | 0.954 | 0.681 | 181,205 | 29.3 |
| [0/90/45/−45]s, clamped | 4 / 3 / 2 | 65,540 (m 4, n 6) | 61,558 / 61,548 / 61,549 | 0.939 | 0.687 (φ 0.426) | 45,054 | 25.9 / 45.0 / 126.5 |
| [0/90/45/−45]s, hinged | 3 | 65,540 | 61,116 | 0.933 | 0.687 | 45,054 | 44.3 |
| [0/90/0/90]s, clamped | 3 | 50,853 (m 5, n 6) | 49,462 | 0.973 | 0.679 | 34,530 | 44.4 |

- **Mesh convergence.** h = 4 mm is already converged to 0.02%. That is about 6 S8R per circumferential half-wave, since n = 6 gives a 25.7 mm half-wave.
- **The 4% isotropic gap is independent of the mesh** and grows with hinged ends. It comes from end constraints in the linear pre-buckling state (interpretation). FE results 0.9–1.0 × classical are typical for constrained-end cylinders [RECALL].
- **The quasi-isotropic laminate loses another 2%.** That matches its bending–twisting coupling (D16 = D26 = 60.4 N·mm), which the classical formula ignores. The FE mode is helical (`img/a1_tube_mode1.png`). The cross-ply laminate, with D16 = D26 = 0, is only 2.7% low (interpretation).
- **Design values.** Report both γ·P_cl and γ·P_FE; for this laminate γ·P_FE = 42,316 N. Use the lower (interpretation).
- **Eigensolver pitfall** (`case_g/chk*.{dat,log}`, h = 4 mm laminate). Changing only the number of requested modes, n_ev:

  | n_ev | λ₁ | Error | Time |
  |---|---|---|---|
  | 1 | 73.479 | **+19.4%** | 12.5 s |
  | 3 | 61.680 | +0.20% | 15.0 s |
  | 5 | 61.630 | +0.12% | 18.1 s |
  | 10 | 61.558 | converged | 22.7 s |
  | 20 / 30 | 61.558 | the repeated pair now appears | 35.1 / 57.0 s |
  | 5, accuracy 1e-5, 40 Lanczos vectors | 61.558 | converged | 36.5 s |

  - The manual's defaults are accuracy 0.01 and 4 × n_ev Lanczos vectors, and its example uses 1 mode ("usually 1"). For cylinders, whose modes come in closely spaced pairs, those defaults are non-conservative.
  - The first imperfect-cylinder attempt used n_ev = 1 and P_cr = 73,479 N (`case_g_run_XI0.1.txt`), and had to be redone.
- **Expanded model size.** With 8 plies the expanded model is 41,200 C3D20R elements and 292,520 nodes. The 10-mode `.frd` is 185 MB and the VTU 65 MB (see §3).

#### (b) Fin root stress: S8R static (`test_bc_fin.py`, `case_bc/results_NSEG{1,2,4}.json`)

- **Common model:** aluminium plate (E 70 GPa, ν 0.3), t = 3 mm, uniform 10 kPa, root fully clamped. gmsh quad8 meshes at h = 10/5/2.5 mm (b1) and h = 5/2.5/1.25 mm (b2).

**b1: wide strip** (chord 400, span 100)

- Reference: cylindrical bending of a clamped–free strip, with w = p s⁴/(8D), D = E t³/(12(1−ν²)), and σ_root = 3 p s²/t². This gives 0.7222 mm and 33.33 MPa.
- FE at mid-chord, by mesh level:

  | Nodes | Time | w error | σ error |
  |---|---|---|---|
  | 1,301 | 0.40 s | −1.33% | +0.35% |
  | 5,001 | 1.74 s | −0.27% | +0.48% |
  | 19,601 | 14.2 s | +0.27% | +0.51% |

- A beam formula with EI in place of D overestimates w by 9.9%. Wide fins need the plate stiffness.

**b2: realistic swept fin**

- Geometry: root 150 mm, tip 60 mm, span 100 mm, leading-edge sweep 90 mm, unswept trailing edge.
- Exact statics: F = 105 N; M_root = F·ȳ = 4,500 N·mm with ȳ = 42.86 mm; the beam-average root stress is 6M/(c_r t²) = **20.0 MPa**.
- FE results (1,408 / 5,246 / 20,685 nodes; 0.47 / 2.06 / 14.7 s):
  - Root moment from the integrated FE σ_y is within 0.085% at h = 5 mm and 0.004% at h = 1.25 mm.
  - **Peak root σ_y is 30.31 / 30.29 / 30.26 MPa, which is 1.51× the beam average.** It sits at about 0.9 c_r from the leading edge (x ≈ 134 of 150 mm), near the trailing edge. The root stress rises almost linearly from the leading edge (`root_profile` in the JSON).
  - Peak von Mises is 28.6 MPa.
  - The root reaction is 104.69 N rather than 105 N. The 0.31 N difference equals the pressure lumped directly onto the constrained root nodes, which ccx's RF total excludes (h·c_r·p/6 = 0.31 N; interpretation).
- **Consequence for the engineering tier.** A root-moment/beam model gets the moment exactly right but under-predicts the peak root stress of a swept fin by about 34%. It needs a chordwise distribution factor or an FE check (interpretation).

#### (c) Fin modes: S8R `*FREQUENCY` (same script)

**c1: square CFFF plate**

- Plate: 100 × 100 × 3 mm aluminium, ρ = 2.70e-9 t/mm³.
- Reference: Leissa, *Vibration of Plates* (NASA SP-160, 1969), Table 4.53 for ν = 0.3: λ = ωa²√(ρh/D) = 3.4917, 8.5246, 21.429, 27.331, 31.111. This gives 256.9, 627.1, 1,576.5, 2,010.7 and 2,288.8 Hz.
- FE errors on modes 1–5:
  - h = 5 mm (1,281 nodes, 1.08 s): −0.20, −0.87, −0.76, −1.21, −1.42%;
  - h = 1.25 mm (19,521 nodes, 28.3 s): −0.60, −1.12, −1.13, −1.30, −1.71%.
- With refinement the FE converges to slightly *below* thin-plate theory, and the gap grows with mode number. That is consistent with the shear-deformable shell at a/t = 33 (interpretation).

**c2: the b2 fin**

- Modes 1–5 at h = 5 mm (1.10 s): 304.1, 860.6, 1,627.6, 2,179.6, 3,158.6 Hz.
- At h = 1.25 mm (31.5 s): 303.0, 858.2, 1,621.5, 2,173.2, 3,150.5 Hz. The change is ≤0.4%.
- The classifier labels the modes bending, torsion, bending, torsion, torsion.
- Uniform-strip estimates use the mean chord and no taper:
  - first bending: (1.8751²/2πs²)√(E t²/12ρ) = 246.8 Hz, so FE is +23%;
  - first torsion (St Venant strip): 450.9 Hz, so FE is +90%.
- Simple beam and strip estimates are unusable for low-aspect-ratio fins. This is the case for FE modal input to flutter in §6.3.

#### (d) Orthotropic solid: C3D10 with `*ORIENTATION` (`test_d_ortho_solid.py`, `case_d/results_LC{3.0,1.5}.json`)

**Model**

- Bar 100 × 20 × 10 mm.
- gmsh tet10 meshes:
  - LC 3: 7,667 nodes, 4,352 C3D10, 23k DOF;
  - LC 1.5: 45,400 nodes, 28,949 C3D10, 136k DOF.
- Transversely isotropic "PLA-like" material: E1 = E2 = 3,200, E3 = 2,400 MPa; ν12 0.35, ν13 = ν23 0.30; G12 1,185, G13 = G23 900 MPa.
- Deck: `*ELASTIC, TYPE=ENGINEERING CONSTANTS` (9 constants), `*ORIENTATION, NAME=OR1, SYSTEM=RECTANGULAR` given by the first two columns of R, and `*SOLID SECTION … ORIENTATION=OR1`.
- Pressure on tet faces uses ccx face numbers {1: (0,1,2), 2: (0,3,1), 3: (1,3,2), 4: (2,3,0)}.

**d1: 10 MPa tension with the print axes rotated** (40° about y, then 30° about z)

- Exact homogeneous solution from the rotated compliance: u_x(L) = 0.3863623, u_y = 0.0318642, u_z = 0.0759486 mm; E_x,eff = 2,588.24 MPa.
- ccx matches to every printed digit (≤1e-4%). σ_xx is uniformly 10.000 MPa, and the other components are ≤6e-9 MPa.
- scikit-fem (P2 tets) matches the exact values to ≤1.4e-8%.

**d2: cantilever, 50 N tip shear, axes aligned**

- Timoshenko: w = PL³/(3E1 I) + PL/(κ G13 A) = 3.1250 + 0.0333 = 3.1583 mm.
- ccx gives 3.1074 mm (LC 3) and 3.1098 mm (LC 1.5), i.e. −1.6 / −1.5%. FE is stiffer because the whole root face is clamped and B/H = 2 adds plate action (interpretation).
- scikit-fem equals ccx to within 1e-4%.
- σ_x at L/4 (top fibre): 11.240 MPa against 11.25 (−0.09%).

**Cost**

- ccx: 1.5 s (LC 3) and 22.6–23.9 s (LC 1.5).
- Memory at LC 1.5 (135,694 equations, SPOOLES, 2 threads): 1,529 MB peak RSS (write-up check).

#### (e) Load mapping and free-free equilibrium (`test_e_loadmap.py`, `case_e/results.json`, `e_loadmap.dat`)

**Model**

- Closed-end tube ("cup"): R_o 49, R_i 47, L 200 mm, with a 6 mm aft bulkhead.
- Isotropic glass-fibre-like material: E 20 GPa, ν 0.15, ρ 1.85e-9 t/mm³.
- Mesh: C3D10 at LC 4 (max) / 2 (min): 60,289 nodes, 30,781 elements.

**Loads**

- A CFD surrogate: a separate, finer linear-triangle skin with 18,009 vertices and 35,710 triangles, carrying p = 0.02 + 0.03 cos θ (1 − z/L) MPa.
- Thrust: 2,000 N as uniform pressure on the aft face.
- Inertia relief by hand (details in §6).

**Results**

- Mapped force and moment against the surrogate's own integral:
  - F_x −461.774 N against −461.718 N (**+0.012%**);
  - M_y −30,784.9 N·mm against −30,782.4 N·mm (**+0.008%**);
  - maximum projection distance 0.0125 mm.

  The residual reflects faceted versus curved geometry, not the mapping (interpretation).
- Rigid-body state: mass 0.300 kg; a = (−156.8 g, 0, +679.3 g); α_y = 2,469 rad/s². These are unphysically large because only a 0.3 kg shell carries the loads, but that is fine for the test.
- **Support reactions** at the 3-2-1 nodes: (−0.089, −0.0001, +0.580) N against |F_ext| = 2,052.6 N, i.e. **≤0.028%**. The loads are balanced.
- Peak von Mises: 21.6 MPa.
- Cost: ccx 18.0 s; the whole script 50.9 s. The remaining 33 s is pure-Python closest-point mapping and mass quadrature, which must be vectorised in production.

#### (f) Bulkhead: circular plate (`test_f_bulkhead.py`, `case_f/run.txt`, `results.json`)

**Model**

- Plate: radius 47 mm, t = 3 mm, plywood-like isotropic (E 8,000 MPa, ν 0.3, ρ 0.68e-9 t/mm³).
- Load: 50 kPa (347 N total).
- Mesh: S8R at h = 3 mm, 2,597 nodes / 832 S8R; 0.88 s and 137 MB (write-up check).

**Results against Roark/Timoshenko**

| Quantity | Reference | FE | Error |
|---|---|---|---|
| Clamped: w₀ = pa⁴/(64D) | 0.19273 mm | 0.19323 | +0.26% |
| Clamped: σ_r at edge = 3pa²/(4t²) | 9.204 MPa | 9.256 | +0.56% |
| Clamped: σ at centre = 3(1+ν)pa²/(8t²) | 5.983 MPa | 5.977 | −0.09% |
| Simply supported: w₀ = (5+ν)/(1+ν)·pa⁴/(64D) | 0.78575 mm | 0.78749 | +0.22% |
| Simply supported: σ_centre = 3(3+ν)pa²/(8t²) | 15.187 MPa | 15.197 | +0.07% |
| Simply supported: f₁ (λ² = 4.935, root of J1/J0 + I1/I0 = 2λ/(1−ν)) | 1,107.2 Hz | 1,104.4 | −0.25% |
| Step load, undamped: peak/static centre deflection | 2.0 (single-degree-of-freedom DLF) | 2.035 | +1.7% |

**Dynamic run**

- `*FREQUENCY, STORAGE=YES` with 20 modes, then `*MODAL DYNAMIC` with Δt = T₁/200 over 3 T₁ (600 points). It took 11.4 s.

**Two ccx defects**

1. **Clamped shells (edge DOF 1–6) crash in `*MODAL DYNAMIC`.**
   - Linux conda-forge: the output stops after the eigenmodes and the `.sta` file is empty (`dbg.log`, `dbg3.log`, `f2w.*`, `f2_inc.*`).
   - Dhondt's `ccx_static.exe` under wine: "Unhandled page fault on write access to 0x0" in `ccx_static+0x3a9a93` (`w.log`).
   - Hinged edges (DOF 1–3) work.
2. **The default `*STEP` increment limit of 100 ends the dynamic step** with "*ERROR in dyna: max. # of increments reached" (`dbg2.log`). Use `*STEP, INC=10000`.
   - ccx also warns that point loads on shell nodes in `*MODAL DYNAMIC` must be pre-applied with zero magnitude in the `*FREQUENCY` step.

#### (g) Imperfect laminate cylinder, `NLGEOM` (`test_g_imperfect.py`, `case_g/results_XI0.1.json`, `g1_nlgeom.{sta,cvg,dat}`)

**Model**

- The (a) laminate tube, clamped, at h = 4 mm (8,932 nodes, 61,249 equations).
- Imperfection: 0.1 t × the first buckling mode. The mode came from `*BUCKLE 10` with `*NODE FILE, OUTPUT=2D`, so it is available on the original shell node IDs.
- Solution: `*STEP, NLGEOM, INC=400`; `*STATIC 0.05, 1.0, 1e-5, 0.05`; prescribed end shortening up to 1.4 × the linear critical shortening (2.03 mm).

**Result**

- The load is nearly linear up to 43.1 kN at 1.22 mm. It peaks at **45,275 N** at 1.286 mm (step time 0.633).
- Newton then failed repeatedly, and the run stopped at "increment size smaller than minimum".
- 24 converged increments with 13 cutbacks took **926 s**.
- The peak is 0.735 × the linear FE load (61,558 N) and 0.691 × classical. The SP-8007 design value γ·P_cl = 45,054 N is 0.5% below the FE peak.
- Only one imperfection amplitude was run.
- The CalculiX manual mentions no Riks or arc-length method (write-up check), so the post-buckling path cannot be traced.
- SP-8007 is not over-conservative relative to a 0.1 t eigen-imperfection here. Real paper, phenolic and glass tubes have larger imperfections and material non-linearity [RECALL]. Keep SP-8007 as the design rule and offer the non-linear analysis as a study.

### 3. Results I/O

**Readers**

- **Our own reader** (`fea_common.py`):
  - `read_frd` parses the ASCII `.frd` by fixed columns. Node blocks are `2C`, element blocks `3C`, and each result block starts with a `100C` line holding its step value (buckling factor or frequency), then `-4` (name) and `-5` (components) lines.
  - `read_dat_eigen` reads the `B U C K L I N G   F A C T O R` and `E I G E N V A L U E` tables from `.dat` (the CYCLES/TIME column).
  - Regular expressions read the reaction totals (`*NODE PRINT … TOTALS=ONLY|YES`) and the `*NODE PRINT, FREQUENCY=1` time series.
- **pyccx** was not installed or used.
- **ccx2paraview 3.2.0** (GPL-3.0 per its metadata) was used once as a cross-check on `b2_fin.frd`, in `c2p/`. Its output and ours agree exactly (write-up check):
  - 48,324 points and 6,778 cells: 6,772 `VTK_QUADRATIC_HEXAHEDRON` + 6 `VTK_WEDGE`;
  - von Mises maximum 28.603 MPa in both files;
  - array names are `U/S/S_Mises/S_Principal/ERROR` versus our `DISP_0/STRESS_0/VONMISES_0/ERROR_0`.

  Because of the GPL-3.0 licence, use it only as a test oracle, never as an import in the core.

**Conversion to VTU** (`frd_to_vtu`)

- `.frd` element types map to pyvista cells:
  - he20 → quadratic hexahedron, node permutation `[0..11, 16..19, 12..15]`;
  - te10 → quadratic tetra, same node order;
  - pe15 → linear wedge `[0,2,1,3,5,4]`, dropping the mid-side nodes;
  - qu8, tr6, he8 and te4 map directly.
- The k-th result block of each name becomes the point array `<NAME>_k`, and `VONMISES_k` is computed from STRESS.
- `render_test.py` used `extract_surface(nonlinear_subdivision=…)` and `warp_by_vector("DISP_0", factor)` and rendered offscreen PNGs: `img/b2_fin_vonmises.png`, `a1_tube_mode1.png`, `d2_cantilever.png`.

**Shell expansion pitfalls** (S8R → C3D20R, S6 → C3D15)

1. **The default output is the expanded 3-D mesh, with new node numbers.**
   - Expanded node IDs start after the highest input node ID; in `f1`, 2,597 input nodes are followed by expanded nodes from 2,598.
   - For single-material shells the **element IDs are kept** (832 elements, IDs 102–933).
   - For `COMPOSITE` shells, **each ply becomes its own layer of C3D20R with new element IDs**: 5,150 input elements (IDs 259–5,408) became 41,200 elements (IDs 5,409–46,608).
   - The plies do not share nodes. The node count is n_plies × (3 n_corner + 2 n_midside) = 8 × (3·5,253 + 2·10,403) = 292,520, which matches the file exactly (write-up check). The plies are presumably tied by MPCs: the log shows 618,001 MPCs (interpretation).
2. **Mapping back to the mid-surface** (verified for all 832 elements of `f1`, write-up check). In `.frd` he20 order:
   - shell corner k = expanded node `ex[12+k]` = mean of `ex[k]` (−t/2) and `ex[k+4]` (+t/2);
   - shell mid-side j = mean of `ex[8+j]` (bottom) and `ex[16+j]` (top).

   So the bottom face is `ex[0..3, 8..11]` and the top face `ex[4..7, 16..19]`. Membrane stress is the mean of the two faces and bending stress is half their difference. For composites the per-ply element ordering was **not** verified, so map plies by geometry or establish the order first.
3. **`*NODE FILE, OUTPUT=2D`** also writes results on the original shell node IDs. The `g0_buckle.frd` blocks hold 175,868 nodes: 166,936 expanded plus 8,932 original.
   - Per the manual, OUTPUT=2D averages through the thickness and so removes bending stresses.
   - Use it only for displacements and mode shapes, as case (g) did.
4. **File size.** ASCII `.frd` is large: 185 MB for 10 modes of the 15.7k-node composite tube, and the VTU is 65 MB. The manual offers binary `.frd` via `*NODE OUTPUT`/`*ELEMENT OUTPUT` (not tested). The reader currently loads the whole file into memory.
5. **Fixed-width fields.** A negative value can run into the node ID, as in `56864-2.45164E-03`. Parse by column, never with `split()`.
6. **The first DISP block of a `*BUCKLE` `.frd`** is the static base state (value 0); the modes follow, each with its buckling factor.
7. **Reaction totals** exclude loads applied directly to constrained nodes. See (b): 104.69 N against 105 N.
8. **Static `.frd` files contain an `ERROR` field** (the error estimator) by default. It reached 88% at the b2 root corners. Hide it or explain it.
9. **Logs over-report sizes.** The ccx log's "estimated upper bounds", e.g. 1,169,256 nodes for the composite tube, are not the real model size.

### 4. Meshing and section cards

**How the prototypes meshed**

- gmsh 4.15.2 ran through its Python API **in-process** in the prototypes. Production must run it in the worker process, for GPL isolation.
- Settings:
  - **Shells:** `SecondOrderIncomplete=1` then `setOrder(2)`, giving 8-node serendipity quads (gmsh type 16 → S8R, same node order) and a few tri6 (type 9 → S6). The b2 fin had 6 S6 among 6,778 elements.
    - Plates and disks: `Algorithm=8` (Frontal-Delaunay for quads), `RecombineAll=1`, `RecombinationAlgorithm=1`, with `MeshSizeMin = MeshSizeMax`.
    - Tubes: transfinite circle (round(2πR/h) + 1 points), then `extrude(numElements=[round(L/h)], recombine=True)`, giving a fully structured mesh.
  - **Solids:** the default 3-D algorithm with `MeshSizeMin/Max`, then `setOrder(2)`, giving tet10 (type 11 → C3D10 with permutation `[0..7, 9, 8]`).
- `write_elements` wraps lines at 16 entries, which ccx requires for more than 15 nodes per element.

**Physical groups were not used.** Every model wrote a single `ELSET=EALL`. Node sets and load faces came from geometric predicates:

- `np.isclose` on z, x or the radius;
- tet faces whose three corner nodes satisfy a predicate;
- outer faces found as faces that occur only once.

The production path is gmsh physical groups per part and per load or support surface, written as `*ELSET`/`*NSET` and face lists (`getPhysicalGroups` / `getEntitiesForPhysicalGroup` / `getElements(dim, tag)` [RECALL]). This is untested.

**Composite section as written in the prototype**

```
*ORIENTATION, NAME=OAX, SYSTEM=RECTANGULAR
0.,0.,1.,1.,0.,0.                 ** local 1 = tube axis (global z)
*MATERIAL, NAME=PLY145
*ELASTIC, TYPE=ANISO              ** 21 constants: ply stiffness rotated +45° about local 3 (aniso_card)
*SHELL SECTION, ELSET=EALL, COMPOSITE, ORIENTATION=OAX
0.125,,PLY100                     ** one line per ply: thickness,,material[,orientation]
…
```

- The manual (write-up check) states:
  - `COMPOSITE` works only with S8R and S6;
  - each ply line may name its own orientation as a fourth field, which is cleaner than pre-rotated ANISO materials;
  - `OFFSET` can move the reference surface, e.g. onto the outer mould line.

  Neither option was tested.
- ccx creates one orientation per expanded layer element: "orientations: 41201" in the log.
- Laminate symmetry was checked: B ≈ 1e-13. The CLT A and D matrices are in the result JSON.

### 5. Alternatives to CalculiX

| Option | Run here? | Evidence / notes | Verdict |
|---|---|---|---|
| **scikit-fem 12.0.2** (BSD-3, in-process) | **Yes**, case (d) | `ElementVector(ElementTetP2)` with a full anisotropic C_ijkl through `einsum`. Matches the exact d1 solution to ≤1.4e-8% and ccx on d2 to 1e-4%. **8.5× slower** at 23k DOF (12.9 s against 1.5 s) and **12.7× slower** at 136k DOF (304 s against 23.9 s), using scipy's default direct solver. No shell or composite elements and no buckling procedure were exercised. It has Kirchhoff plate elements but no general layered shells [RECALL]. | An in-process engineering-tier helper and an independent CI oracle for solids. Not the FEA tier. |
| FEniCSx | No | [RECALL] LGPL; needs PETSc/MPI; Windows support only through conda and recent; no ready-made layered shell with `COMPOSITE`-style input. | No. |
| Code_Aster | No | [RECALL] GPL; strong shells and composites (DKT, COQUE_3D, `DEFI_COMPOSITE`), buckling and modal analysis; Windows builds lag and the install is large; Python `.comm` decks with MED I/O. | No for v1 (packaging and size). |
| Elmer | No | [RECALL] GPL solver; Windows installers exist; Reissner–Mindlin shell solver; limited layered-composite support. | No. |

**Recommendation:** use CalculiX for the FEA tier. Keep scikit-fem for in-process cross-checks and small engineering helpers, such as plate modes, if needed.

### 6. Mapping loads and inertia relief

- **From CFD.** The CFD research (`cfd.md` §5, `prototypes/cfd/map_loads.py`) compared two mappings:
  - **Pressure interpolation** onto an independent structural surface lost **11–42% of the axial force** on a real vehicle with nose, fins and base.
  - **Conservative force mapping** (each CFD face force goes to the structural face under its centroid, split by barycentric weights) kept force within 1e-4% and moment within 2e-4%.

  Case (e) shows that pressure quadrature onto quadratic tet faces works for a *smooth* field on a cylinder (+0.012% / +0.008%), but that test has no inclined surfaces, no thin fins and no shocks. **Use the conservative mapping.**
  - For S8R and C3D10 faces, split each CFD face force with the quadratic shape functions at the projected point. This keeps the force exact (interpretation; not yet run end-to-end CFD → ccx).
  - For shells, project onto the mid-surface, or set `OFFSET` so the outer mould line is the reference surface (untested).
- **From the engineering tier.** Spread the per-station normal force as a cos θ circumferential pressure, as case (e) did with p₀ + p₁ cos θ. Apply drag as skin and base loads, and thrust on the thrust-ring face (interpretation).
- **Inertia relief, as done in case (e):**
  1. Integrate the mass, CG and inertia tensor over the FE mesh (4th-order tet quadrature, 10-node shape functions).
  2. Compute a = F_ext/m and α = I_cg⁻¹·M_cg.
  3. Apply the translational part as `*DLOAD, EALL, GRAV, |a|, −â` (a d'Alembert body force).
  4. Apply the rotational part as consistent nodal forces f_i = −∫N_i ρ α × (x − x_cg) dV.
  5. Support the model with a 3-2-1 constraint on three rim nodes 120° apart (DOF 1–3, 2–3, 3).

  The reactions then measure the imbalance: ≤0.028% of the applied load.

  Production issues:
  - The FE structure will not carry the motor, payload and electronics mass. Add them as point or distributed masses (`*MASS` [RECALL]), or the FE-derived a and α will disagree with the flight simulation (interpretation).
  - Centripetal ω² terms from spin and pitch rate are missing. `*DLOAD … CENTRIF` is available per the manual but was not tested.
- **Recovery shock.**
  - **Bulkhead:** the clamped static result × a DLF (2.0 for an undamped step) is accurate (f1 within 0.6%). Modal dynamics reproduced DLF 2.035 for the hinged plate.
  - **Shock-cord and eyebolt load paths, and couplers:** not modelled.

### 7. Performance, memory and threading

**Memory and time for single decks** (write-up check, conda-forge Linux build, SPOOLES, 2 threads)

| Deck | Type | Equations | Wall | CPU | Peak RSS |
|---|---|---|---|---|---|
| `f1_static` (bulkhead) | S8R, 2,597 nodes | 16,931 | 0.96 s | 1.46 s | 137 MB |
| d1, LC 3 | C3D10, 7,667 nodes | 22,839 | 1.50 s | 2.18 s | 148 MB |
| b2 fin, h = 1.25 mm | S8R, 20,685 nodes | 143,404 | 16.8 s | 23.9 s | 1,325 MB |
| d1, LC 1.5 | C3D10, 45,400 nodes | 135,694 | 24.7 s | 39.6 s | 1,529 MB |

**Solver benchmark** on the d1 LC 1.5 deck (135,694 equations; `bench/bench.sh`; ccx's "Total CalculiX Time" from the scratchpad `bench/*.out`):

| Run | Build / solver | Threads | Time | Answer |
|---|---|---|---|---|
| sp1 | Linux, SPOOLES | 1 | 32.2 s | reference |
| sp2 | Linux, SPOOLES | 2 | 23.6 s (1.36×) | same |
| px2 | `ccx_static.exe` under wine, PaStiX | 2 | 22.1 s; factorisation 4.68 s at 45 GFlop/s; 787 MB factor storage; general LU with fill 8.5 | same |
| pd | `ccx_dynamic.exe` under wine, PARDISO (`MKL_THREADING_LAYER=SEQUENTIAL`, so MKL probably ran 1 thread; interpretation) | 2 | **17.5 s** | same |
| it2 | Linux, `ITERATIVE CHOLESKY` | 2 | 30.4 s; 417 iterations to the 1.1e-4 limit | **wrong**: node 6 u_y +15%, u_z −27.5% |

- PaStiX and the non-solver parts each take about half the time. "CCX without PaStiX" was 0.86 of 1.71 s on d1 LC 3 and 6.0 of 13.6 s for the first buckling factorisation. Assembly, stress recovery and ASCII output therefore matter as much as the solver.
- Run times for the analyses are given per case in §2.
- **Scaling beyond 2 threads was not measured.** SPOOLES-MT gained only 1.36× from 1 to 2 threads. PaStiX and PARDISO scale better [RECALL]. That is the reason to keep PaStiX as an option to benchmark.
- The manual says "with 32 GB of RAM you can solve up to 1,000,000 equations" with SPOOLES, which has no out-of-core mode. That caps the size of whole-vehicle shell models on 16–32 GB desktops.

## Verified by running

All paths are relative to `docs/research/prototypes/fea/` unless marked (scratchpad).

- **Linux ccx 2.23** (conda-forge linux-64 build 8, banner "made on Mon Sep 28 09:16:29 2026") ran every case. Its logs are `case_*/*.log`.
- **Windows builds under wine 9.0** (`wine_install.log`):
  - `winrun/cf.log`: conda-forge exe, d1 LC 3, 1 thread;
  - `winrun_buckle/{cf.log, st.log, a1cf.dat, a1_comp.dat}`: conda-forge and `ccx_static` on the composite buckle;
  - `winrun_static/st.log`: PaStiX, d1 LC 3;
  - `winrun_pardiso/{a1p, d1p}.{log,dat}`: PARDISO;
  - `case_f/w.log`: `ccx_static` crash in clamped `*MODAL DYNAMIC`;
  - result equality across builds: `.dat` node 6 and λ₁ (write-up check).
- **Binary inspection (write-up check):** pefile imports and export forwarders; `strings` scans for PaStiX, PARDISO, SPOOLES and MKL; MKL version resources (oneAPI 2025.2.1); SHA-256 of the zips and exes (scratchpad).
- **Build provenance:** conda metadata in `ccxwin/conda-meta/*.json` and `history`; recipe and Makefile in `calculix-feedstock/recipe/`; `dhondtwin/calculix_2.23_4win/README_Install` (all scratchpad).
- **Case (a):** `test_a_tube_buckle.py`, `rerun_a_g.sh`, `case_a/results_h*.json`, `logs/a_*.txt`, `case_a/a{0,1}_*.{dat,log}`.
- **Eigensolver sensitivity:** `case_g/chk{1,3,5,10,20,30,5_1e-5_40}.{dat,log}`.
- **Cases (b) and (c):** `test_bc_fin.py`, `case_bc/results_NSEG{1,2,4}.json`, `case_bc/*.{dat,log}`.
- **Case (d):** `test_d_ortho_solid.py`, `case_d/results_LC{3.0,1.5}.json`, including the scikit-fem results and timings.
- **Case (e):** `test_e_loadmap.py`, `case_e/results.json`, `case_e/e_loadmap.dat` (reactions).
- **Case (f):** `test_f_bulkhead.py`, `case_f/{run.txt, results.json, *.inp, *.log, dbg*.log, w.log}`.
- **Case (g):** `test_g_imperfect.py`, `case_g/{g0_buckle, g1_nlgeom}.*`, `results_XI0.1.json`, `logs/g_XI0.1.txt`, `case_g_run_XI0.1.txt` (the earlier one-mode attempt).
- **Solver benchmark:** `bench/bench.sh`, `bench/*.sta`; timings and answers in `bench/*.{out,dat}` (scratchpad).
- **Results I/O:**
  - `fea_common.py`, `render_test.py`; PNGs in `img/` (scratchpad);
  - ccx2paraview cross-check in `c2p/b2_fin.vtu` (scratchpad), compared with `case_bc/b2_fin.vtu` (write-up check);
  - the expanded-node mapping rule and composite element IDs (write-up check on `case_f/f1_static.frd` and `case_a/a1_comp.frd`).
- **Memory and solver availability (write-up check):** peak RSS for four decks; `SOLVER=PARDISO` → rc 201 (scratchpad `writeup_check/`).
- **Manual facts (write-up check** on `docs/CalculiX/ccx_2.23/doc/ccx/*.html`):
  - solver default order;
  - `*BUCKLE` defaults (accuracy 0.01, 4 × n_ev Lanczos vectors);
  - OUTPUT=2D averaging;
  - `COMPOSITE` limited to S8R/S6 with per-ply orientation;
  - thread environment variables;
  - binary `*NODE OUTPUT`;
  - no inertia-relief keyword and no Riks/arc-length method.

### Scratchpad-only files worth preserving

Copy these into `docs/research/prototypes/fea/` before the scratchpad is lost:

- `bench/{sp1,sp2,px2,pd,it2}.out`, plus the node-6 lines of `bench/*.dat`. These hold the only record of the solver timings, the PaStiX details and the wrong iterative answer.
- `img/{a1_tube_mode1,b2_fin_vonmises,d2_cantilever}.png`.
- `ccxwin/conda-meta/*.json` and `history`, which give the package URLs, SHA-256 and licences (about 130 kB). Alternatively, generate `tools/manifest.json` from them now.
- `calculix-feedstock/recipe/{recipe.yaml, Makefile_MT, build.bat}`, which document how the shipped binary was built.
- `dhondtwin/calculix_2.23_4win/README_Install` and `web/{dhondt,calculix_de}.html`.
- `winrun/d1_tension.inp` (0.5 MB), as the Windows smoke-test deck.
- `writeup_check/{mem.py, *.out}`.
- A text file of the SHA-256 values for `winbundle_cf.zip`, `ccx.exe`, the Dhondt zip and exes, and the MKL DLLs.

Consider pruning the committed `docs/CalculiX/` HTML manual (about 14 MB, thousands of PNGs; link to dhondt.de instead) and the stray `wineprefix/drive_c/…/winevulkan.json`.

## Risks

- **Windows execution is unproven.** All Windows evidence comes from wine. Untested so far:
  - DLL loading from the app directory;
  - thread counts and CPU dispatch;
  - killing the process to cancel;
  - paths with spaces or long paths;
  - antivirus delays;
  - file locking while the job system tails `.sta` and stdout.
- **Scaling to 8–16 threads is unmeasured,** and SPOOLES-MT scaled poorly (1.36× from 1 to 2 threads). All desktop runtimes above are projections.
- **The SPOOLES memory ceiling** (in-core only, about 1M equations in 32 GB) limits whole-vehicle shell models. Use bay-level or coarser global models and submodels.
- **`*BUCKLE` is fragile with few modes.** One mode was 19% non-conservative. Linear FE buckling is also 0.93–0.97 × classical, still far above test reality for imperfect shells, so the SP-8007 knockdown must always be applied and labelled.
- **Engineering-tier fin stress is non-conservative for swept fins.** The beam average missed the peak root stress by 34%. The fin flutter screen also needs FE modes: strip estimates were 23–90% off.
- **ccx defects:**
  - clamped shells crash in `*MODAL DYNAMIC` in both builds;
  - `ITERATIVE CHOLESKY` reports convergence with up to 27% error;
  - the default `INC` ends modal-dynamic steps early;
  - `.frd` precision is 6–7 digits.
- **Composite post-processing is unbuilt.** Plies expand into separate C3D20R layers with new IDs; the ply-to-element ordering, ply-axis stress rotation and failure indices were not demonstrated. `.frd` and VTU sizes reach hundreds of MB for one modal or buckling run.
- **Load mapping has not been run end to end** (SU2 surface → conservative map → ccx). The FE-side test used a smooth analytic field on a cylinder only.
- **Model features with no test at all:**
  - shell-to-solid and fin-to-tube connections (`*TIE`, shared nodes);
  - contact;
  - fin-can fillets;
  - couplers;
  - bolted joints;
  - spiral-wound paper or phenolic tubes;
  - print infill models.

  The material values used were illustrative.
- **`NLGEOM` collapse is slow and incomplete:** 15 minutes for 61k equations, it stops at the limit point, there is no arc-length method, and only one imperfection amplitude was run.
- **Licensing:**
  - GPL-2 ccx is fine as a separate process but obliges us to make the source available;
  - ccx2paraview is GPL-3.0 and must not enter the core;
  - MKL/PARDISO redistribution with GPL code is unresolved [RECALL].
- **Supply chain:** the Dhondt binaries come from a third-party builder with no build recipe. The conda-forge build depends on the feedstock staying maintained, so pin the URL and SHA-256 in `tools/manifest.json`.

## Open questions

- How do ccx (conda-forge SPOOLES), `ccx_static` (PaStiX) and `ccx_dynamic` (PARDISO) perform natively on Windows at 4, 8 and 16 threads, for 100k–1M-equation shell models? What is the right thread count, and is PaStiX worth shipping?
- How should fins, couplers and bulkheads connect to the airframe shell: shared nodes, `*TIE` or `*EQUATION`? How do we model fin-can fillets and through-the-wall fin tabs, and validate them?
- How do we get ply stresses and failure indices? Options: rotate the expanded per-ply C3D20R stresses ourselves, use `*EL FILE, GLOBAL=NO`, or switch to per-layer orientations in the composite section. What is the expanded-element ordering for `COMPOSITE` shells?
- Should we switch to binary `.frd` (`*NODE OUTPUT`/`*ELEMENT OUTPUT`) to cut file size and parse time? Which output sets should a 3-D view request by default?
- Should the imperfect `NLGEOM` analysis be in v1 at all? If so, with what imperfection amplitudes (0.1–0.5 t?), what increment controls, and how should the limit point be reported without an arc-length method?
- Is there a workaround for clamped-shell `*MODAL DYNAMIC`: solid bulkheads, `*DYNAMIC` direct integration, or an upstream fix? Or is static × DLF enough for recovery loads?
- How do we reconcile the FE structural mass with the flight-simulation mass model (point masses for the motor, payload and electronics) so that inertia relief balances? When do spin and pitch-rate ω² terms (`CENTRIF`) matter?
- Does SP-8007 apply to spiral-wound paper and phenolic tubes, and where do their orthotropic properties and knockdowns come from?
- What size does a vectorised conservative mapping onto quadratic faces need for production? The case (e) Python loop took 33 s for 60k nodes.
- Does the gmsh worker produce clean quad8 shells from real STEP mid-surfaces? The prototypes meshed only primitives.
