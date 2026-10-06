# Research: cfd

> **Topic:** cfd: a high-fidelity CFD tier using SU2 v8.5 and gmsh 4.15 for finned rockets (Mach 0.1–3, AoA 0–15°) on a Windows desktop with 8–16 cores. Covers which binaries to ship, the meshing pipeline, accuracy against reference solutions, run cost, post-processing, mapping loads to the structure, and convergence and progress reporting.

_Written up on 2026-10-06 from the on-disk artifacts of a hands-on research agent that was cut off before it wrote its report. The small files (scripts, configs, logs, result tables) are in `docs/research/prototypes/cfd/`. Meshes, VTU fields, binaries, mesh logs and download records are only in the session scratchpad (`…/scratchpad/research/cfd/`). Numbers come from those artifacts unless marked [RECALL]. A few short checks were re-run during the write-up and are marked "(write-up check)"._

**Test vehicle used in every run.** A cone–cylinder 1.0 m long with D = 0.1 m. The conical nose is L_N = 0.30 m long (half-angle 9.46°). It has four trapezoidal fins in an "x" layout: flat plates 4 mm thick with square edges, root chord 0.12 m, tip chord 0.06 m, span 0.08 m, leading-edge sweep 0.06 m, trailing edge flush with the base. Freestream is sea level (101 325 Pa, 288.15 K). A_ref = πD²/4, L_ref = D, and moments are taken about the nose tip, so x_cp/D = −C_My/C_N. "CA" and "CN" are body-axis C_Fx and C_Fz.

## Recommendation

**Build the CFD tier on SU2 8.5.0 Euler. Use engineering skin-friction and base-drag corrections, and label them as such. Keep RANS out of v1, or mark it "experimental".** In supersonic flow, Euler with multigrid converges in 1–15 minutes per case at mesh sizes that give C_N within about 3% and x_cp within 0.02 D of the grid-converged value. RANS did not work: the boundary-layer meshing is fragile, wall functions produced NaN, and the low-Re SST model neither converged nor predicted friction correctly.

- **What to bundle:** `SU2-v8.5.0-win64-omp.zip` (28,043,921 B, SHA-256 `4466fe21aedb5e0bad57afd45f829acbdec6ec79fe8c3f8954ddea06a4b4bc11`, hashed locally). Ship only `bin/SU2_CFD.exe` (23.5 MB) plus the LGPL-2.1 licence text.
  - The exe imports only `KERNEL32`, `USER32` and `msvcrt`, with libgomp linked statically. It needs no MS-MPI and no VC++ runtime.
  - Run it as `SU2_CFD.exe -t <threads> case.cfg` from the case directory.
  - Do **not** ship `win64-mpi`. It needs `msmpi.dll` (an MS-MPI install) and was no faster than OpenMP at 2 workers.
  - 8.5.0 is the first release with an OpenMP Windows asset; the 8.4.0 `win64` exe is serial.
  - **Not yet shown:** the Windows exe has never been run. Only its imports were inspected. Running a Windows CI smoke test should be the first task in M6.
- **Mesher:** gmsh 4.15.2 with the OCC kernel, in a separate worker process. Unstructured tetrahedra: 2-D Frontal-Delaunay (alg 6), 3-D HXT (alg 10), curvature sizing (12) and distance-based sizing fields combined with a `Min` field. Replace the sharp nose apex with a 0.25 mm meplat (flat tip). Add a conical refinement zone over the nose shock and refine fin edges and the near wake.
  - Make two meshes per vehicle: a short supersonic domain and a large subsonic domain. Change AoA through the freestream direction only; never remesh for it.
- **Solver settings by regime:**
  - **M ≥ ~1.2:** compressible Euler, Roe, MUSCL with the Venkatakrishnan–Wang limiter (K = 0.03), 3 multigrid levels, CFL adapting from 5 to 100. Forces settle within 0.1% in 22–55 iterations. Residuals drop 5.5–8 orders in 71–126 iterations.
  - **M ≤ ~0.3:** the incompressible solver (`INC_EULER`). It converged 7 orders in 102 iterations. The compressible Roe scheme is biased at M = 0.1. Roe with `LOW_MACH_CORR` was unstable.
  - **0.3 < M < 1.2: untested.** This is the biggest gap.
- **Mesh presets (sizes scale with D and fin thickness):**

  | Preset | Mesh level | Nodes for the 1 m test rocket | Peak memory | What it gives |
  |---|---|---|---|---|
  | Preview | u2.8 | 58k | 0.8 GB | quick look |
  | Medium | u2.0 | 148k | 2 GB | x_cp within 0.05 D |
  | Accurate (default) | u1.4 | 408k | 5.7 GB | C_N −3.1% / GCI 4%; x_cp GCI 0.24%; CA about −7% |

  - Measured memory is about 14 kB per node. A finer level (about 1.1M nodes) would need about 15 GB, so offer it only on machines with at least 32 GB.
  - Run the 3-level grid-convergence study (GCI) once per vehicle on a reference case, and report its uncertainty band.
- **Drag:** Euler gives the forebody wave drag (nose and fins). Add van Driest II turbulent friction and an empirical base drag. Never report Euler base pressure as base drag: it is not grid-converged (GCI 27%) and has no physical basis in an inviscid solver.
- **Loads for the FEA tier:** map loads conservatively, sending each CFD wall-face force to structural nodes with barycentric weights. That conserved force and moment to ≤2e-4%. Interpolating pressure node to node lost 11–42% of the axial force.
- **Progress bar:** tail `history.csv`, which has one row per iteration. Parse it by column position, because the header contains `Time(sec)` twice. For gmsh, use its `[ xx%]` log lines for 1-D and 2-D meshing. Show 3-D meshing as an indeterminate sub-stage; it takes 70–86% of mesh time.
- **Expected cost on an 8-core desktop** at the default preset (projection; see Key findings §4):
  - about 4–6 minutes per supersonic case;
  - about 4–8 hours (overnight) for a 12 Mach × 4 AoA flight database;
  - under 1 hour for "key moments" mode (about 5 cases).

### Milestone-6 pipeline (proposed)

1. **Geometry.**
   - Build the B-rep OML (outer mould line) and replace sharp apexes with a meplat of about 0.5% of the local radius.
   - Turn component faces into gmsh physical groups. These become SU2 markers such as `nose`, `body`, `fins`, `base`, and `<cad part>`.
   - Export STEP for the mesher worker.
2. **Mesh.** Use the gmsh worker with the `make_mesh.py` settings, but scale lengths by D and fin thickness t.
   - Wall sizes: body 0.06·D·s, fins 0.03·D·s, fin edges ≤ min(0.015·D·s, t/4).
   - Grow at 0.06·s per metre of distance from the wall.
   - Refine a cone over the nose (0.008·D·s at the tip to 0.066·D·s at the shoulder).
   - Refine a box over the wake (0.2·D·s for 5 D behind the base).
   - Far-field size 3·D·s; s = 2.8 / 2.0 / 1.4 for the three presets.
   - Supersonic domain: x from −3 D to +8 D past the base, radius 9 D. Subsonic domain: about ±60 D.
   - Always set `MeshSizeMin`. Add a watchdog timeout. If HXT fails, retry with a slightly perturbed size factor.
3. **Solve.** Generate the config as `make_cfg.py` does. For each Mach regime, use one mesh with a sequence of AoA values. Run cases one after another using all physical cores minus one; memory, not cores, is the binding limit.
   - Restart each case from the neighbouring AoA's solution. Expected savings are [RECALL]; this was not measured.
   - Write a restart file every 50 iterations so that pause and cancel lose little.
4. **Converge.** A case counts as converged only if one of these holds:
   - the residual target (relrms ≤ −5.5) is met **and** a Cauchy window on C_D, C_N and C_My over the last 50 iterations is within 1e-4 relative; or
   - the residual has dropped at least 3 orders **and** the Cauchy window passes.

   Anything else is flagged and never used silently.
5. **Post-process.**
   - Per-marker coefficients come from `history.csv` (`AERO_COEFF_SURF`) and `forces_breakdown.dat`.
   - Cp fields come from `surface_flow.vtu`; volume fields from `flow.vtu` (pyvista).
   - Add van Driest II friction per component wetted area, plus empirical base drag.
   - Build aero tables over Mach × AoA. Cancel mesh-asymmetry bias by subtracting the AoA = 0 result or by running ±AoA.
6. **Verify.**
   - CI: Taylor–Maccoll cone at Mach 2 on the u2.8-equivalent mesh (about 1–2 min on 2 threads), nose CA within −20%…0%.
   - Manual validation suite: fine mesh within −6%; Richardson-extrapolated value within ±3%. These thresholds come from the measured −17.2 / −5.5 / +1.9%.
   - Grid-convergence study on one reference case per vehicle.

## Key findings

### 1. SU2 binaries and how the runs were launched

- **Release assets** (`downloads/asset_probe.txt`, probed 2026-10-05):
  - 8.0.0–8.4.0 publish `win64`, `win64-mpi`, `linux64`, `linux64-mpi`, `macos64` and `macos64-mpi` (`linux64-omp` is 404).
  - 8.5.0 publishes **`win64-omp`, `win64-mpi`, `linux64-omp`, `linux64-mpi`**; plain `win64`/`linux64` are 404 and `macos64-omp` is 404.
  - 8.5.1, 8.6.0 and 9.0.0 did not exist yet.
  - The naming change at 8.5.0 means the tool fetcher must pin exact asset names.
- **Downloaded zip sizes and SHA-256** (`downloads/SHA256SUMS.txt`):

  | Asset | Size (B) | SHA-256 prefix |
  |---|---|---|
  | win64-omp | 28,043,921 | 4466fe21… |
  | win64-mpi | 28,925,770 | 7da985f9… |
  | linux64-omp | 30,226,528 | aadc800c… |
  | linux64-mpi | 37,550,641 | ff4381fd… |
  | 8.4.0 win64 | 26,588,077 | — |

- **PE import inspection with pefile (write-up check):**
  - 8.5.0 `win64-omp` `SU2_CFD.exe` imports `KERNEL32`, `USER32` and `msvcrt`. It contains libgomp strings (MinGW, statically linked) and the option text "Number of OpenMP threads per MPI rank."
  - 8.5.0 `win64-mpi` imports `KERNEL32`, `msmpi.dll` and `msvcrt`, and contains no libgomp, so it is pure MPI. Needing the MS-MPI redistributable means an admin install [RECALL], which is wrong for a beginner per-user installer.
  - 8.4.0 `win64` contains no libgomp, so it is serial.
  - The Linux 8.5.0 omp and mpi binaries are static ("not a dynamic executable").
- **Version:** run logs show `Release 8.5.0 "Harrier"` under LGPL-2.1. The `bin/*.py` helper scripts need Python and are not required; the app drives `SU2_CFD` directly.
- **How runs were launched** (`queue1..7.sh`):
  - Each case got a directory and a `case.cfg` written by `make_cfg.py`. The mesh path was relative.
  - Command: `cd case && SU2_CFD -t 2 case.cfg > run.log` with the Linux OpenMP build.
  - MPI comparison: `mpiexec -n 2` (MPICH 5.0.2 from pip) with the `linux64-mpi` build.
  - Wall time was measured with `date`. Peak memory came from sampling `/proc/<pid>/status` VmHWM every 2 s.
  - Host: a VM with 4 vCPUs (Xeon @ 2.8 GHz) and 15 GB RAM (observed in the write-up session). Runs used 2 threads so they could share the VM.

### 2. Meshing pipeline

**What worked: `make_mesh.py` (gmsh 4.15.2 Python API, OCC kernel)**

- **Geometry:**
  - OCC cone with a **meplat of R_tip = 0.25 mm**, fused with a cylinder.
  - Four fins: each planform is extruded to 4 mm, rotated into place, with the root sunk 0.1 R into the body. All are fused.
  - The fused body is cut out of a far-field cylinder.
  - Large domain: x ∈ [−6, 12] m, R = 6 m. `--small-domain` (supersonic): x ∈ [−0.3, 1.8] m, R = 0.9 m.
- **Markers:** bounding-box classification produces `nose`, `body`, `fins` (16 faces), `base` and `farfield`. gmsh writes the `.su2` file directly from physical groups. SU2 read every file, reported "All volume elements are correctly oriented", and silently re-oriented the far-field triangles, which is harmless.
- **Sizing:** Distance + MathEval fields, combined with `Min`:
  - body 6 mm·sf, fins 3 mm·sf, fin edges 1.5 mm·sf, nose-tip curve 0.5 mm·sf, each plus `growth`·distance;
  - a nose `Frustum` from 0.8 mm·sf (r ≤ 20 mm at the tip) to 6.6 mm·sf (r ≤ 220 mm at the shoulder);
  - a wake `Box` of 20 mm·sf for 0.5 m behind the base;
  - a constant far-field size.
- **Two refinement families:**
  - The `sf` family scales wall sizes only (growth 0.12, far size 0.6 m).
  - The `--uniform` family scales all lengths (growth 0.06·sf, far size 0.3·sf). This is the one to use for refinement studies.
  - `sf2` and `u2.0` have identical sizing and differ only in domain size.
- **Options:** `MeshSizeExtendFromBoundary=0`, `MeshSizeFromPoints=0`, `MeshSizeFromCurvature=12`, `Algorithm=6`, `Algorithm3D=10` (HXT), `Optimize=1`, `NumThreads=2`.

**Failures found and their fixes**

- **True cone apex.** The `sf1.4` mesh with a sharp apex failed in 3-D with "Found two duplicated facets … HXT 3D mesh failed" (`meshes/rocket_sf1.4.log`). The `make_mesh.py` comment records duplicated or non-manifold apex triangles with every 2-D algorithm.
  - Write-up re-check: `dbg_apex.py` (sharp-apex sweep) did not finish within 90 s; per-combination output was lost to buffering, which is consistent with the apex hang reported in `cad-geometry.md`.
  - `dbg_apex2.py` (meplat, r_tip = 0.25 and 0.5 mm, h = 4–12 mm): **8/8 surface meshes were clean**, with 0 duplicate, 0 non-manifold and 0 open edges, in 8.5 s total.
  - Curvature sizing is also required at the tip (code comment).
- **`MathEval "Min(F1, c)"` hangs gmsh 4.15** (`dbg_fields.py`; code note "verified"). The fix is to put a constant MathEval field inside a `Min` field.
- **Boundary layer in gmsh:**
  - The `BoundaryLayer` *field* is 2-D only in 4.15.2: there is no `SurfacesList` (`bl_mesh.py` docstring, "verified"). The `--bl` path in `make_mesh.py` therefore does not make 3-D prisms.
  - `gmsh.model.geo.extrudeBoundaryLayer` on the reloaded discrete wall mesh **failed at patch junctions when the wall was split into several patches** (`split_markers.py` docstring; the `REPORT.md` it cites was never written).
  - It **worked on a single merged wall patch** (`--single`). Component markers were then recovered by centroid classification (`split_markers.py`): nose 2,982 / body 2,167 / fins 1,936 / base 301 triangles.
  - Result `rocket_bl_sf3_split.su2`:
    - 10 layers, h1 = 40 µm, ratio 1.2, total thickness 1.04 mm;
    - **73,860 prisms + 55,187 tets, 48,095 nodes**;
    - 3-D meshing took 2.4 s in a box domain of x −0.6…2.5 m, ±1.2 m.
- **netgen 6.2.2608 (pip) boundary layer straight from STEP** (`ng_bl.py`): box minus rocket, `maxh` 0.15, 10 layers with h1 = 40 µm and ratio 1.2. It **succeeded**: 39,720 prisms + 72,464 tets, 34,168 points. Generation time was not recorded. It was never exported to SU2 or solved.

**Mesh-quality re-check (write-up, `meshqual.py`, scaled Jacobian)**

| Mesh | Prisms | Tets | Inverted |
|---|---|---|---|
| gmsh boundary-layer mesh | min 0.149, median 0.895 | min 0.020, p1 0.116 | 0 |
| netgen boundary-layer mesh | min 0.052, median 0.638 | min 0.066 | 0 |

**Tet meshes (gmsh logs; 2 threads, times include 1-D + 2-D + 3-D)**

| Mesh | Domain | Wall triangles | Nodes | Tets | gmsh wall time (3-D part) | minSICN min / p1 / mean (0 negative) |
|---|---|---|---|---|---|---|
| u2.8 | small | 11,756 | 58,003 | 299,270 | 21.3 s (14.5 s) | 0.084 / 0.399 / 0.788 |
| u2.0 | small | 20,908 | 147,946 | 808,728 | 36.3 s (28.4 s) | 0.119 / 0.407 / 0.796 |
| u1.4 | small | 39,910 | 408,469 | 2,328,130 | 78.3 s (67.2 s) | 0.177 / 0.410 / 0.800 |
| sf3 | large | 10,864 | 160,210 | 852,820 | 41.4 s (31.0 s) | 0.124 / 0.410 / 0.797 |
| sf2 | large | 20,102 | 210,920 | 1,142,193 | 48.8 s (37.2 s) | 0.175 / 0.410 / 0.797 |

- **Domain size is cheap to get right in supersonic flow.** sf2 (large) and u2.0 (small) use identical sizing. The small domain cut the node count by 30% and run time by about 50%. It changed CA by +0.8%, C_N by +1.1% and x_cp by +0.01 D.
- **Fin edges are under-resolved.** At u1.4 the fin-edge size (2.1 mm) puts only about 2 cells across the 4 mm blunt fin edge. This matches the poor grid convergence of the fin loads in §3. Presets must tie the edge size to fin thickness.

### 3. Results and accuracy

**Mach 2, Euler, multigrid 3** (`results_table.txt`, `results_gci.txt`)

| Mesh | Nodes | AoA | Iterations | Wall s | Peak memory GB | CA | CN | C_My | x_cp/D | CA nose / fins / base | CN nose / body / fins |
|---|---|---|---|---|---|---|---|---|---|---|---|
| u2.8 | 58k | 0 | 150* | 117 | 0.79 | 0.1807 | −0.0096 | 0.098 | – | 0.0791 / 0.0866 / 0.0150 | – |
| u2.8 | 58k | 4 | 71 | 78 | 0.81 | 0.1799 | 0.5219 | −3.664 | 7.020 | 0.0788 / 0.0850 / 0.0162 | 0.108 / 0.142 / 0.272 |
| u2.0 | 148k | 0 | 75 | 166 | 2.04 | 0.2626 | 0.0050 | −0.050 | – | 0.0859 / 0.1129 / 0.0637 | – |
| u2.0 | 148k | 4 | 80 | 181 | 2.04 | 0.2622 | 0.5512 | −3.957 | 7.179 | 0.0853 / 0.1118 / 0.0651 | 0.115 / 0.128 / 0.308 |
| u1.4 | 408k | 0 | 150* | 940 | 5.67 | 0.2934 | 0.0045 | −0.038 | – | 0.0902 / 0.1193 / 0.0838 | – |
| u1.4 | 408k | 4 | 125 | 793 | 5.67 | 0.2951 | 0.5669 | −4.093 | 7.219 | 0.0896 / 0.1180 / 0.0875 | 0.122 / 0.112 / 0.333 |
| **Richardson extrapolation** | – | 4 | – | – | – | 0.3170 | **0.5853** | – | **7.233** | base 0.106 | fins 0.383 |
| sf3 (large domain) | 160k | 0 / 4 | 83 / 80 | 200 / 183 | 2.12 / 2.19 | 0.1869 / 0.1873 | 0.5196 | −3.728 | 7.176 | | |
| sf2 (large domain) | 211k | 0 / 4 | 126 / 112 | 394 / 336 | 2.82 / 2.92 | 0.2605 / 0.2604 | 0.5451 | −3.908 | 7.169 | | |

\* Stopped at the 150-iteration cap with the residual stalled (relrms −3.4 and −4.5) while forces had already settled within 0.1% by iterations 34 and 55.

**Grid convergence** (u2.8 → u2.0 → u1.4; refinement ratios r = 1.366 and 1.403 by node count; Roache GCI)

| Quantity | GCI on finest mesh | Observed order p | Notes |
|---|---|---|---|
| CN at AoA 4 | **4.05%** | 1.90 | u1.4 is 3.1% low; u2.0 is 5.8% low |
| x_cp at AoA 4 | **0.24%** | 4.2 | converged by u2.0 to within 0.05 D |
| CA at AoA 0 | 7.9% | – | u1.4 is 6% low |
| CA at AoA 4 | 9.3% | – | u1.4 is 7% low |
| Base CA | 27% | – | |
| Fin CN | 18.9% | – | |
| Nose CN | – | 0.06 | not in the asymptotic range |

So the "accurate" preset (u1.4-class, about 0.4M nodes for this vehicle) is adequate for C_N, x_cp and static margin. Euler axial force is not grid-converged at any affordable level and should be used only for its nose and fin wave-drag parts.

**Mesh-asymmetry noise.** At AoA 0, C_N reached 0.0045–0.0096 and C_My −0.04 to +0.10, which is 1–2.4% of the AoA 4 values. Subtract the AoA 0 result or use ±AoA.

**Limiter sensitivity.** Venkatakrishnan K = 0.3 instead of 0.03 on sf2 raised CA from 0.2605 to 0.2641 (+1.4%). That run did not converge in 150 iterations (relrms −1.46), so keep K = 0.03.

**Comparison with reference methods**

- **Taylor–Maccoll** (`taylor_maccoll.py`, `results_taylor_maccoll.txt`). Exact for the 9.4623° cone at M = 2: β = 31.006°, cone-surface Mach 1.847, Cp = **0.09553**. Modified Newtonian gives 0.0448 and is useless here. Nose CA at AoA 0 should equal the cone Cp:

  | Mesh | Nose CA | Error vs 0.09553 |
  |---|---|---|
  | u2.8 | 0.0791 | −17.2% |
  | u2.0 | 0.0859 | −10.0% |
  | u1.4 | 0.0902 | −5.5% |
  | Extrapolated | 0.0974 | +1.9% (GCI 9.9%) |

  Area-averaged Cp for x > 0.2 L_N was −4.8% on u1.4 and +1.0% extrapolated. **The Mach 2 cone verification passes at the extrapolated level.**
- **Linear supersonic estimate** (`linear_estimate.py`: slender-body nose, Ackeret fins, Barrowman-style interference K = 1.385). C_N = 0.5485 (−6.3% vs CFD extrapolated) and x_cp = 7.62 D (+0.39 D aft). The estimate ignores afterbody carry-over lift, but the CFD body marker carries C_N 0.112. The CFD nose C_N of 0.122 is 12% below the slender-body value of 0.139.
- **Barrowman (subsonic formula).** There is no script; it was computed inline, and the arithmetic was re-checked during the write-up. CNα = 7.96/rad, of which fins give 5.96. C_N at 4° = 0.5557, x_cp = 7.466 D.
  - At M = 0.1 with `INC_EULER`: CFD C_N is **−2.9%** and x_cp is **+0.29 D** (aft).
  - At M = 2 the formula is not applicable. CFD gives CNα = 8.38/rad (extrapolated) against 7.96.
  - `openrocket-methods.md` records that OpenRocket's supersonic fin CNα is about half of linear theory, so this tier matters most above Mach 1.
- **Skin-friction correction** (`skin_friction.py`: van Driest II with adiabatic wall, applied to Kármán–Schoenherr):
  - M = 2, sea level: Re_L = 4.66e7, Cf of body 0.00179, Cf of fins 0.00266 (mean aerodynamic chord 0.0933 m).
  - **Friction CA = 0.0610 (nose + body) + 0.0195 (fins) = 0.0805.** This is about 27% of the Euler CA, so the correction is not optional.
  - Illustrative build-up at M = 2, AoA 0 (arithmetic only, not validated against test data): Euler forebody wave drag 0.2096 (u1.4: nose 0.0902 + fins 0.1193) + friction 0.0805 + base 0.25/M = 0.125 (the OpenRocket base-drag formula from `openrocket-methods.md`) ≈ 0.415. The Euler base value of 0.084 is replaced.
  - First-cell heights: for y⁺ = 1 they run from 11 µm (M 0.1) to 1.6–1.9 µm (M 1.2–3); for y⁺ = 30 they are 47–333 µm.

**Low Mach: M = 0.1, AoA 4°, large-domain sf3 mesh (160k nodes)**

| Solver | Converged? | Iterations | Wall s | CA | CN | x_cp/D | Base CA |
|---|---|---|---|---|---|---|---|
| `INC_EULER` (FDS, constant density) | **yes**, 7.1 orders; forces settled by iteration 53–58 | 102 | 291 | 0.327 | **0.539** | **7.76** | 0.345 |
| Compressible Roe | yes, 7.0 orders; forces settled by iteration 92 | 495 | 1166 | 0.456 | 0.511 (−5%) | 8.27 (+0.5 D) | 0.554 |
| Roe + `LOW_MACH_CORR=YES` | **no**: relrms −1.4; CN swings 0.30–0.73 at CFL 100 | 250 (cap) | 787 | (0.252) | (0.598) | (8.40) | – |

- Use the incompressible solver for low Mach.
- Euler CA at M = 0.1 is base-flow numerical artefact and must not be used.
- Preconditioning (`ROE_TURKEL_PREC` / `LOW_MACH_PREC`), the `LMROE`, SLAU2 and AUSM+up2 schemes, and lower CFL with `LOW_MACH_CORR` were **not tried**. `make_cfg.py` accepts some of these options, but none were run.

**RANS attempt: Mach 2, AoA 0, SST V2003m, gmsh boundary-layer mesh with 48k nodes**

1. Wall functions starting from freestream: `rc=1` after 5.7 s (the log was overwritten).
2. Stage 1, low-Re SST: 300 iterations, 125 s, 0.49 GB. relrms only −1.7; the CFL kept collapsing between 0.5 and 20.
3. Stage 2, restart with `STANDARD_WALL_FUNCTION`: log shows "y+ < 5 in 3930 points" and "Warning: T_Wall < 0", then **NaN at iteration 1**.
4. Stage 3, low-Re SST restart: 900 more iterations, 386 s, 0.50 GB. **Did not converge**:
   - relrms oscillated between −0.5 and −2.3;
   - CA drifted from 0.514 to 0.503;
   - spurious C_N −0.0085 and C_My +0.052 at AoA 0.
5. Why it failed:
   - y⁺ achieved: median 14.8, p5 8.9, p95 22.9 (write-up check on `surface_flow.vtu`). That is the buffer layer, which neither wall-resolved nor wall-function modelling handles.
   - Friction CA was **0.0199 against the 0.0805 estimate** (4× low; median Cf 5.1e-4).
   - Base CA was 0.267.
   - Pressure was 96% of drag.

**The RANS route is not production-ready.** Making it work needs:

- y⁺ ≤ 1 layers, about 1.5 µm at Mach 2, which means roughly 25–30 layers;
- a robust 3-D boundary-layer mesher;
- a much larger mesh.

### 4. Performance, memory and parallel mode

**Cost per iteration.** Euler with multigrid 3 and ILU on 2 OpenMP threads costs **≈13–14 µs per node per iteration** across every mesh:

| Mesh | Nodes | s per iteration |
|---|---|---|
| u2.8 | 58k | 0.75–0.91 |
| u2.0 | 148k | 1.96–2.03 |
| sf3 | 160k | 2.07–2.15 |
| sf2 | 211k | 2.76–2.87 |
| u1.4 | 408k | 5.68–5.79 |

- Incompressible and Roe runs at M = 0.1: 14.6–16.3 µs.
- RANS without multigrid: 9.1 µs.
- Setup and output add 13–89 s per run (wall time minus iterations × s/iteration), which is 9–17% of a run.

**Parallel mode, run alone** (`queue7.log`, `runs_mem/par_*`; 148k nodes, no multigrid, 25 iterations):

| Mode | s per iteration |
|---|---|
| OpenMP, 1 thread | **2.30** (15.6 µs/node) |
| OpenMP, 2 threads | **1.27** (1.82× speed-up) |
| MPI, 2 ranks | **1.26** |

Forces were identical to 4 digits. OpenMP and MPI performed the same at 2 workers. **Scaling beyond 2 threads was not measured** because of the 4-vCPU VM. Run logs show OpenMP edge-colouring efficiency of 0.77–0.84 on the coarse multigrid levels; `EDGE_COLORING_GROUP_SIZE` is the tuning knob.

**Multigrid.** One multigrid-3 cycle costs 1.6–2× a no-multigrid iteration, but reaches converged forces in 22–55 iterations. The only no-multigrid Euler run (`old/smoke_40it`) reached relrms −1.2 after 40 iterations with forces still moving.

**Peak memory**

- Euler, multigrid 3, ILU: **13.2–13.9 kB per node** (0.79 GB at 58k, 2.04 GB at 148k, 2.82 GB at 211k, 5.67 GB at 408k nodes).
- Write-up check (58k nodes, 3 iterations, 2 threads):

  | Settings | Peak memory | kB per node | s per iteration |
  |---|---|---|---|
  | No multigrid + ILU | 628 MB | 10.8 | 0.59 |
  | No multigrid + LU-SGS | 474 MB | 8.2 | 0.54 |
  | Multigrid 3 + ILU | 768 MB | 13.2 | 1.15 |

- Only the OpenMP process was measured; MPI memory was not measured.

**Projections for a Windows desktop**

Assumptions:

- single-core cost of a multigrid-3 iteration ≈ 25 µs per node (2 × 13.9 µs at the measured 91% two-thread efficiency);
- desktop cores about as fast as this VM's vCPU (likely conservative [RECALL]);
- parallel efficiency 75% at 8 threads and 60% at 16 threads [RECALL / assumption, unmeasured];
- 150 iterations per supersonic case;
- add about 1 minute of setup and output per case.

| Preset | Nodes | 8 cores | 16 cores | Memory |
|---|---|---|---|---|
| Preview (u2.8) | 60k | ~0.5 min | ~0.4 min | 0.8 GB |
| Medium (u2.0) | 150k | ~2 min | ~1.5 min | 2.1 GB |
| Accurate (u1.4) | 410k | **~5 min** | **~4 min** | 5.7 GB |
| Extra-fine (one more refinement level) | ~1.1M | ~13 min | ~8 min | **~15 GB** (multigrid 3 + ILU); ~9 GB with LU-SGS and no multigrid, but more iterations |

- **Flight database, 12 Mach × 4 AoA = 48 cases, at the Accurate preset:**
  - about 4 hours on 8 cores if every case behaved like the supersonic runs;
  - realistically **5–8 hours on 8 cores and 3.5–5.5 hours on 16 cores**, assuming transonic and subsonic cases need 2–3× the iterations [RECALL; untested];
  - about 2.7× longer at Extra-fine, which is also memory-bound.
  - A half-model with a pitch-plane symmetry plane would roughly halve the cost. That plane exists geometrically for this "x" fin layout, but it was **untested**.
- **Key-moments mode (about 5 cases):** about 30–45 minutes on 8 cores.
- **Meshing:** happens once per regime per vehicle and took 21–78 s for 58k–408k nodes on 2 threads.

### 5. Post-processing and mapping loads to the structure

- **Per-component forces.**
  - Each component is its own wall marker, listed in `MARKER_MONITORING` and `MARKER_PLOTTING`.
  - `HISTORY_OUTPUT` includes `AERO_COEFF_SURF`, which gives `CD(nose)`, `CFx(fins)`, `CMy(base)` and similar per iteration in `history.csv`.
  - `WRT_FORCES_BREAKDOWN=YES` writes `forces_breakdown.dat` with the pressure and friction split per marker.
- **Independent check of the force integration.** `postprocess.py` re-integrates −Cp·n·A from `surface_flow.vtu` with pyvista, after classifying components geometrically and checking outward normals with the divergence theorem (enclosed volume 6.36e-3 m³). It **reproduces SU2's marker forces to 4 decimals** (for example, m2_a4_sf2 C_N 0.5451 / 0.5451 and CA 0.2604 / 0.2604). Offscreen PNG rendering also worked (`runs/m2_a4_sf2/surface_cp.png`, `symplane_mach.png`).
- **VTU fields** (pyvista 0.49 / VTK 9.7):
  - Surface and volume: `Density`, `Momentum`, `Energy`, `Pressure`, `Temperature`, `Mach`, `Pressure_Coefficient`, `Velocity`.
  - RANS adds `Turb_Kin_Energy`, `Omega`, `Laminar_Viscosity`, `Skin_Friction_Coefficient`, `Heat_Flux`, `Y_Plus`, `Eddy_Viscosity`.
- **Two output pitfalls:**
  - With `REF_DIMENSIONALIZATION=FREESTREAM_VEL_EQ_ONE`, `Pressure` and `Density` are non-dimensional. Compute loads from Cp·q∞ (as was done) or switch to dimensional output.
  - The merged `surface_flow.vtu` has **no marker ID array**. Map points to components using the `.su2` marker lists, since `surface_flow.csv` carries a `PointID` [RECALL that it is the mesh node index], or by geometry.
- **Mapping to the structure** (`map_loads.py` on m2_a4_sf2, q∞ = 283.7 kPa; CFD total F_z = 1214.6 N, F_x = 580.3 N, M_y = −870.8 N·m):
  - The structural surface mesh was re-meshed from `rocket.step` with gmsh at h = 0.02 m and h = 0.008 m.
  - **Pressure interpolation** (closest-point projection, barycentric interpolation, consistent nodal forces): errors at h = 0.02 / 0.008 m were **normal force −3.1% / −1.8%, axial force −42.5% / −11.4%, pitch moment −4.0% / −2.5%**.
  - **Conservative force mapping** (each CFD face force goes to the structural triangle under its centroid, split by barycentric weights): force error ≤ 1e-4% and moment error +0.0002% at both resolutions.
  - Kernel interpolation is flagged in the code as wrong because it mixes the two sides of thin fins.
  - Output `struct_loads.vtp` holds `force_N`, `p_minus_pinf_Pa` and `force_conservative_N`.

### 6. Convergence criteria and the progress bar

- **Criteria used:** `CONV_FIELD=REL_RMS_DENSITY` (`REL_RMS_PRESSURE` for the incompressible solver), with `CONV_RESIDUAL_MINVAL` of −5.5 to −8 and `CONV_STARTITER=10`. SU2 listed Cauchy defaults (ε 1e-10, 100 elements), but no Cauchy field was active.
- **What the runs showed:**
  - At Mach 2, forces settled within 0.1% after 22–55 iterations, while relrms reached −5.5 after 71–125 iterations.
  - Two AoA 0 runs stalled on the residual (−3.4 and −4.5) with forces already settled. A residual-only rule would wrongly fail them.
  - Two runs oscillated without converging (`LOW_MACH_CORR` and RANS). A residual drop alone would not flag "flat but wrong".
  - Hence the combined rule in the Recommendation.
- **What `history.csv` provides** (written every inner iteration; the screen updates only every 20):
  - `Inner_Iter`;
  - **two columns both named `Time(sec)`**: the first is the current iteration time and the second the average per iteration;
  - `rms[*]` and `relrms[*]`, which are 0 at the first iteration and **reset to 0 on every restart**, so use absolute `rms` targets when resuming;
  - CFL and linear-solver iterations;
  - total and per-marker coefficients.
- **Rows are written as the run goes:** the NaN run left its iteration-0 row on disk. Whether a reader can tail the file while SU2 holds it open on Windows is [RECALL] and untested.
- **Proposed progress maths for "Solve case k of N":**
  - Fraction done = max(it / ITER, progress in log residual), where log-residual progress = relrms / target, used only once the last 20 iterations show a negative slope. The first 20–40 iterations are non-monotonic while the CFL ramps.
  - ETA = average s/iteration × min(ITER − it, (target − relrms) / slope).
  - Also show the Cauchy window status.
- **Mesh stage:** gmsh prints `[ xx%] Meshing curve/surface …` for 1-D and 2-D (79 lines in the u1.4 log). The 3-D HXT stage prints only its phases.
- **Pause and resume:** restart from `restart_flow.dat` worked on Linux, including switching turbulence settings between stages.

## Verified by running

All paths are relative to `docs/research/prototypes/cfd/` unless marked (scratchpad).

- **SU2 binaries:**
  - 8.5.0 assets probed and downloaded (scratchpad `downloads/asset_probe.txt`, `SHA256SUMS.txt`).
  - Linux 8.5.0 omp and mpi builds run on all cases. Version banner "8.5.0 Harrier" appears in every `runs/*/run.log`.
  - Windows exe DLL imports inspected with pefile, plus libgomp string checks (write-up check).
  - **The Windows exes were never executed.**
- **gmsh tet meshes:**
  - u2.8, u2.0, u1.4, sf3 and sf2 generated, with sizes, times and quality as in §2 (scratchpad `meshes/*.log`).
  - The sharp-apex HXT failure is in scratchpad `meshes/rocket_sf1.4.log`.
  - The meplat fix was re-confirmed with `dbg_apex2.py` (write-up check: 8/8 clean).
  - `MathEval Min` hang: `dbg_fields.py` and the code comment; its output was not retained.
- **Boundary-layer meshes:**
  - gmsh single-patch extrusion (scratchpad `meshes/rocket_bl_sf3.log`, `bl_mesh.py`, `split_markers.py`).
  - netgen boundary layer from STEP (`ng_bl.py`, scratchpad `meshes/ng_bl.vtu`).
  - Quality re-checked with `meshqual.py` (write-up check).
- **Euler at Mach 2**, AoA 0 and 4, 5 meshes: `runs/m2_*/{case.cfg,run.log,history.csv,post.json,forces_breakdown.dat,walltime.txt,peak_rss.txt}`, collected in `results_table.txt` by `collect.py`.
- **Grid convergence and Richardson extrapolation:** `gci.py` → `results_gci.txt`.
- **Reference solutions:**
  - Taylor–Maccoll: `taylor_maccoll.py` → `results_taylor_maccoll.txt`.
  - Linear supersonic estimate: `linear_estimate.py` → `results_linear_estimate.txt`.
  - Barrowman: `results_barrowman.txt` (no script; arithmetic re-derived in the write-up).
  - Friction and y⁺: `skin_friction.py` → `results_skin_friction.txt`.
- **Low Mach:** `runs/m01_a4_sf3_{inc,roe,roe_lmcorr}`.
- **RANS:**
  - `runs/rans_m2_a0_bl_sf3/` (final stage), `stage1/`, `stage2_wf_failed/` (wall-function NaN and the T_Wall < 0 warning).
  - The final 900-iteration `history.csv` and `surface_flow.vtu` (y⁺ and Cf) exist only in the scratchpad.
- **Timing, parallel mode and memory:**
  - `queue1..7.{sh,log}` and `runs_mem/par_{omp1,omp2,mpi2}`.
  - `runs_mem/{mg0_ilu,mg0_lusgs,mg3_ilu,omp2,mpi2}` were timed while other runs were active, so treat those timings as noisy.
  - Memory for the multigrid and preconditioner variants was re-measured in the write-up (3-iteration runs).
- **Post-processing:** pyvista re-integration matches SU2 (`post.json` → `pyvista_integration`). Offscreen PNGs are in `runs/m2_a4_sf2/`.
- **Load mapping:** `map_loads.py` → `results_load_mapping.txt`; `struct_loads.vtp` is in the scratchpad.
- **Windows wheels downloaded** (scratchpad `downloads/wheels/`):
  - gmsh 4.15.2 `win_amd64`: contains `gmsh-4.15.dll` and `gmsh.py` but **no `gmsh.exe`**.
  - netgen-mesher 6.2.2608 cp311: LGPL-2.1-only; depends on netgen-occt 7.8.1, a second copy of OCCT.
  - vtk 9.7.1 cp311, pyvista 0.49.0, tetgen 0.8.4 cp311.
  - These are **cp311 wheels; cp312 was not checked here.**
- **Caveats on the result files:**
  - In `results_table.txt` the `rans_m2_a0_bl_sf3` row is stale: iterations = 1 and CA 0.5213 come from the failed stage-2 restart. The final values are CA 0.5026 after 900 iterations, still unconverged.
  - The `m01_a4_sf3_roe_lmcorr` row is a snapshot of an oscillating run.
  - The `m2_a0_sf2_K0.3` row is not converged.
  - The scratchpad-only mesh logs, `asset_probe.txt`, `SHA256SUMS.txt` and the final RANS `history.csv` should be copied into the repo before the scratchpad is lost.

## Risks

- **Windows execution is unproven.** The `-t` option, file locking while tailing `history.csv`, killing the process to cancel, and long paths or spaces in case directories all need a Windows CI smoke test early in M6.
- **Memory, not CPU, limits accuracy.** At about 14 kB per node, a 16 GB desktop caps out near 0.8–1M nodes with multigrid 3 and ILU. Real CAD OMLs (rail buttons, launch lugs, boat-tails, more fins) will push node counts up at the same resolution.
- **Transonic flow (M 0.8–1.2) is entirely untested,** and 0.3 < M < 0.8 is untested too. These usually converge slowest and are the most sensitive to mesh and domain size [RECALL]. The flight database needs them.
- **AoA above 4° is untested** (the spec range is 0–15°). Euler cannot capture crossflow separation from a smooth body, so it will under-predict non-linear body lift at high AoA [RECALL].
- **Euler axial force is not grid-converged** (GCI 8–9%; base 27%). The empirical friction and base-drag terms (power-off, turbulent from the tip) will dominate drag error. This is not yet validated against wind-tunnel data (Arcas Robin and the like).
- **The RANS route failed**: wall functions gave NaN, low-Re SST was non-convergent, the gmsh 3-D boundary layer only works on a single patch, and the y⁺ target was wrong. Promising RANS in v1 would be over-promising.
- **gmsh fragility:** the apex singularity, the `MathEval Min` hang, HXT failures from duplicate facets, and multi-patch boundary-layer extrusion. gmsh must run in a separate process with a watchdog, fallbacks and clear errors (it is GPL, which the spec already requires to be isolated).
- **Geometry path gap.** The CFD meshes were built from gmsh OCC primitives in-script. The **STEP → gmsh → SU2 volume-mesh path was never exercised**; STEP import was used only for the structural re-mesh and for netgen.
- **Performance projections rest on unmeasured assumptions:** scaling beyond 2 threads and desktop per-core speed. Run timings came from a shared 4-vCPU VM.
- **Unstructured-mesh asymmetry** gives 1–2.4% bias in C_N and C_My at small AoA unless it is cancelled.
- **Parser traps:** duplicate `Time(sec)` headers, non-dimensional VTU fields, relrms resetting on restart, and no marker IDs in the surface VTU.
- **The 4 mm square-edged fin** made fin wave drag (CA_fins about 0.12) and fin C_N converge poorly. Real fins with sharp or rounded edges will behave differently.

## Open questions

- Which compressible settings converge reliably for M 0.3–1.2? Candidates include Roe with lower CFL, `LOW_MACH_PREC`/`ROE_TURKEL_PREC`, SLAU2, AUSM+up2, Newton–Krylov (`NEWTON_KRYLOV` is present in `make_cfg.py` but unused), multigrid behaviour, and the domain size needed. What do they cost?
- How well does the Windows OpenMP build scale at 8 and 16 threads? Is the default "physical cores − 1" right, or are 2 concurrent cases × 4 threads better? Memory argues against concurrent cases. What gain does `EDGE_COLORING_GROUP_SIZE` tuning give?
- How much does restarting from the neighbouring AoA or Mach solution save in a sweep? Does a half-model with a symmetry plane give the same forces as the full model, and which roll orientations allow it for 3-fin and 4-fin layouts?
- Should RANS be pursued at all for v1? If so, choose between netgen (boundary layers straight from STEP, LGPL, its own OCCT 7.8 copy) and gmsh single-patch extrusion with marker splitting. It would also need a y⁺ ≤ 1 layer design (h1 1.5–11 µm across the envelope), SA vs SST, and a convergence recipe. None of this is validated.
- How accurate is Euler + van Driest + empirical base drag against wind-tunnel data, and up to what AoA can the Euler normal force be trusted?
- Does gmsh meshing of real STEP OMLs (CAD protuberances, tangent ogives, boat-tails) stay robust with the same sizing fields? Is a meplat or tip blunting acceptable to users, and how should it be disclosed?
- What is the best per-marker surface output for mapping components? Options are separate surface files per marker, or a PointID → marker map built from the `.su2` file.
- Is the surface of a frozen gmsh worker (DLL plus the Python API) the right approach, rather than the SDK `gmsh.exe`, given the wheel has no exe? Do cp312 wheels exist for netgen and the pinned VTK?
- What restart-write frequency (`OUTPUT_WRT_FREQ`) gives an acceptable pause/cancel granularity, and how much I/O cost does it add on large meshes?
