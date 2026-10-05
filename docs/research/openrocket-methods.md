# Research: openrocket-methods

> **Topic:** openrocket-methods: OpenRocket 23.09/24.12 aero, mass and flight-simulation methods (equation level), reproducing them in Python, driving OR from Python, and model gaps up to Mach 3

_Generated from a hands-on feasibility research agent (2026-10). Items marked VERIFIED were run/read by the agent; others are from recall and must be re-checked before relying on them._

## Recommendation

Build the fast tier with two switchable modes in one code base.

**1) OR-compatible mode.** A faithful port of OR 23.09/24.12, including its quirks, so the app can reproduce OR results for validation and user trust.
- Port the equations in the key findings: Barrowman/Galejs body terms, Diederich/Busemann fins, roughness-limited friction, nose drag tables, 0.25/M base drag, OR's mass integration, RK4 6-DOF with OR's time-step rules, Euler recovery and the event semantics.
- Also port OR's numeric details: linear a(T)=165.77+0.606T, linear viscosity, 500 m ISA table, 293.15 K default for component analysis, radius-based fineness in the friction correction, joint-angle sinphi for ogive noses, single-surface supersonic fin CNa, instantaneous chute opening, rail clearance after the full rod length.
- I verified this is achievable: my Python port matches OR 24.12's BarrowmanCalculator to ~1e-14 (worst 9e-5) for CD, its friction/pressure/base split, CNa and CP. The test covered M 0.05-3, six nose shapes, three fin profiles and two finishes.

**2) Extended (accuracy-first, Mach 3) mode.** Replace the gaps OR documents or exhibits:
- Fin CNa and CP: use two-surface supersonic linear theory with tip/root Mach-cone losses (Ackeret/Evvard, or Barrowman's FIN strip method with tip terms). Use NACA 1307 K_W(B)/K_B(W) for fin-body interference.
- Nose wave drag: second-order shock-expansion (NACA TR-1328) for ogives and arbitrary noses, Taylor-Maccoll for cones. Calibrate the transonic region with Stoney TR-R-100 data or CFD.
- Body normal force: supersonic nose CNa/CP, plus viscous crossflow with Cd_c(M_c).
- Base drag: power-on/off correlations.
- Fins: thickness wave drag.
- Damping: proper Cmq/Cma-dot and supersonic roll damping.
- Thermo: exact ISA/US76 sqrt(gamma*R*T) and Sutherland viscosity.
- Rigid-body dynamics: full Euler equations with gyroscopic terms and a time-varying inertia tensor (jet damping optional).
- Rail exit: compute from rail-button geometry.
- Recovery: a parachute inflation / opening-shock model (Knacke/Pflanz, or two-body with an elastic shock cord). This is required for the user's deployment-load analysis because OR's instantaneous-opening peaks (722-1004 m/s² in the examples) are artifacts.

Every output should carry its fidelity tier and Mach/AoA validity band. The transonic band (0.8-1.2) should be flagged as interpolated unless CFD tables are supplied. Accept user or CFD aero tables vs (Mach, AoA), as OR master's CsvMachAoALookup now does.

**Cross-validation.** Do not depend on orhelper: it works for 23.09 but breaks on 24.12 because of the net.sf to info.openrocket package rename. Instead:
- Ship a small adapter like run_or.py (JPype or a Java CLI subprocess). Run OR as a separate GPL process with the user's OR jar/JRE. The OR Windows installer bundles a JRE.
- Before comparing, zero the wind turbulence and call setRandomSeed. The wind seed is not stored in .ork, so plain runs are not repeatable.
- Compare time series and events, and use BarrowmanCalculator.getForceAnalysis for per-component CD/CNa/CP sweeps.
- Use the downloaded Arcas Robin wind-tunnel reports (TN D-4013 for M 0.6-1.2, TN D-4014 for M 1.5-4.63) as validation data for the supersonic tier. Their data are in plots and must be digitised.

## Key findings

- Pipeline (24.12, read in source).
  - BasicEventSimulationEngine runs an event queue and switches between four steppers: RK4SimulationStepper for powered/coast flight (6-DOF), BasicLandingStepper under a chute (3-DOF Euler), BasicTumbleStepper (3-DOF Euler) and GroundStepper.
  - Aerodynamics come from BarrowmanCalculator. It finds a per-component calculator class by reflection (<Component>Calc in aerodynamics/barrowman) and simply adds the components' contributions.
  - Paths are relative to core/src/main/java/info/openrocket/core/ (24.12). In 23.09 the same sub-paths sit under core/src/net/sf/openrocket/.
- Atmosphere (models/atmosphere/ExtendedISAModel, InterpolatingAtmosphericModel, AtmosphericConditions).
  - ISA layer breakpoints at 0/11/20/32/47/51/71/84.852 km. Pressure:
    p = p_b*(1+(h-h_b)L/T_b)^(-g0/(L R)), or p_b*exp(-g0(h-h_b)/(R T_b)) in isothermal layers. R = 287.053, g0 = 9.80665.
  - Values are tabulated every 500 m and linearly interpolated; altitude is clamped to 0..84.852 km.
  - rho = p/(R T).
  - Speed of sound is a linear fit: a = 165.77 + 0.606 T. This is about 0.7% high at 217 K versus sqrt(gamma R T).
  - Dynamic viscosity is also linear: mu = 3.7291e-6 + 4.9944e-8 T. This is about 2.3% above Sutherland at 217 K.
  - A custom launch-site temperature/pressure inserts an extra layer at the site altitude.
  - The default AtmosphericConditions() is 293.15 K / 101325 Pa. FlightConditions and Component Analysis use this default; the ISA model is only used in simulations.
- Gravity (WGSGravityModel): Somigliana formula with inverse-square altitude scaling.
    g0 = 9.7803267714*(1+0.00193185138639 sin²φ)/sqrt(1-0.00669437999013 sin²φ)
    g = g0*(6371000/(6371000+h))²
- Geodesy and Coriolis (util/GeodeticComputationStrategy).
  - FLAT: 111325 m per degree of latitude, 111050·cos φ m per degree of longitude, no Coriolis.
  - SPHERICAL (default): great-circle propagation with R = 6371 km.
  - WGS84: Vincenty direct formula.
  - Coriolis: a = 2Ω(v_n sinφ - v_u cosφ, -v_e sinφ, v_e cosφ) with Ω = 7.292115e-5 and v_e := -v_x. Because x = East, the y and z components appear to have the wrong sign. The effect is tiny (<0.015 m/s² at 100 m/s). [derived]
- Wind (PinkNoiseWindModel; MultiLevelPinkNoiseWindModel is 24.12 only).
  - Vector: w = (U + σ n(t)/2.252)·(sin ψ, cos ψ, 0), where ψ is the direction the wind blows from (0 = North, π/2 = East).
  - Air velocity relative to the rocket is computed as v_rocket + w.
  - n(t) is Kasdin IIR 1/f^α noise with α = 5/3 and 2 poles: a_i = (i-1-α/2)a_{i-1}/i, x_k = g_k - Σ a_i x_{k-i}. It is sampled every 0.05 s and linearly interpolated.
  - Defaults are U = 2 m/s and turbulence intensity σ/U = 0.1. Wind has no altitude dependence in the single-level model.
  - Multi-level wind linearly interpolates between levels' vectors and can be imported from CSV.
  - The random seed is random per document load and is NOT stored in the .ork, so plain OR runs are not repeatable.
- Flight conditions (AbstractSimulationStepper.calculateFlightConditions, FlightConditions).
  - The air velocity is rotated into body axes.
  - Angle of attack α = acos(v_z/V); θ = atan2(v_y, v_x) is the direction of the lateral flow.
  - Body rates are rotated by -θ.
  - M = V/a.
  - β = sqrt|1-M²|. 24.12 clamps β ≥ 0.25; 23.09 does not.
  - Re = V·L_aero/ν, where L_aero is the aerodynamic length of the whole rocket.
  - Reference length is the maximum body diameter; A_ref = π d²/4.
- Body normal force and CP (SymmetricComponentCalc, read in source and verified by running).
  - Barrowman term (only when the radius changes): CNa_B = 2(A1-A0)/A_ref, with x_cp = (L·A1 - V_full)/(A1-A0).
  - Galejs body lift on every symmetric part: CN_L = 1.1·(A_plan/A_ref)·sin²α, acting at the planform centroid. Below M < 0.05 with α > 45°, it is multiplied by (M/0.05)².
  - Component CN = [CNa_B·sinc α + 1.1·(A_plan/A_ref)·sin α·sinc α]·α, where sinc α = sin α/α.
  - Cm about the nose tip = CN·x_cp/L_ref.
  - The code states that supersonic body CNa and CP are the same as subsonic. Nose CNa is 2 at all Mach numbers.
- Fin geometry and single-fin CNa (FinSetCalc, read in source and verified by running).
  - Geometry uses 48 span strips to get MAC length, MAC span and MAC leading-edge position, mid-chord cos Γc, leading-edge cos ΓL, AR = 2s²/A_fin, and rollSum = Σ c_i (r + y_i)² Δy.
  - Subsonic (M ≤ 0.9), Diederich: CNa1 = 2π s²/A_ref / (1 + sqrt(1 + (1-M²)(s²/(A_fin cos Γc))²)).
  - Supersonic (M ≥ 1.5): CNa1 = (A_fin/A_ref)(K1 + K2 α + K3 α²) with
    K1 = 2/β
    K2 = ((γ+1)M⁴ - 4β²)/(4β⁴)
    K3 = ((γ+1)M⁸ + (2γ²-7γ-5)M⁶ + 10(γ+1)M⁴ + 8)/(6β⁷)
    The table runs to M 4.9 and is held constant beyond.
  - Transonic (0.9 < M < 1.5): a quartic fitted to the subsonic value and slope at 0.9, the supersonic value and slope at 1.5, and zero second derivative at 0.9.
- Fin set CNa, CP and roll (FinSetCalc, read in source and verified by running).
  - Each fin instance gets cna = CNa1·sin²(θ - φ_fin). For three or more equally spaced fins the sum is N/2.
  - Fin-fin factors for more than 4 overlapping fins: 5 → 0.948, 6 → 0.913, 7 → 0.854, 8 → 0.81, more → 0.75.
  - Body-fin interference: multiply by (1 + τ) with τ = r/(s + r).
  - CN = cna·min(α, 20°).
  - Fin CP: x = MAC_lead + f·MAC_length, where
    f = 0.25 for M ≤ 0.5
    f = (AR β - 0.67)/(2 AR β - 1) for M ≥ 2
    a 5th-order polynomial (coefficients rational in AR) in between.
  - Roll forcing per fin: (MAC_span + r)·CNa1·(1 + τ)·δ_cant/L_ref, faded out between α = 20° and 30°.
  - Roll damping, subsonic: 2π p·rollSum/(A_ref L_ref V β).
  - Roll damping, supersonic: Σ (K1 η + K2 η² + K3 η³) c_i (r + y_i) Δy/(A_ref L_ref) with η = p(r + y)/V. Transonic is a linear blend.
  - Fin side force and yaw moment are disabled (Cside = Cyaw = 0; TODO in the source).
- Small components (read in source).
  - Tube fins: CNa = 2(AR'/(1+AR'))π² r_in c/A_ref with AR = 2r_in/c and AR' = 2AR/π.
    Bug: calculatePoly() is never called in 23.09 or 24.12, so the tube-fin CP sits at the leading edge for 0.5 < M < 2.
  - Launch lugs: no normal force. Drag = Darcy-Weisbach internal flow with the Swamee-Jain friction factor, plus 0.7(CD_stag + CD_base)·A_frontal.
  - Rail buttons: drag only, from the Gowen-Perkins cylinder Cd at a boundary-layer-reduced Mach. The result is multiplied again by CD_stag, which looks like double counting.
- Rocket totals and pitch damping (BarrowmanCalculator).
  - CNa = ΣCNa_i; Xcp = Σ(CNa_i x_i)/ΣCNa_i; stability margin in calibers = (Xcp - Xcg)/d_ref.
  - Stall margin = 17.5° - α. A TUMBLE event fires when the margin is negative and the CG is aft of the CP.
  - Pitch/yaw damping is ad hoc:
    mul = 0.275·d̄/(A_ref L_ref)·(x_cg⁴ + (L - x_cg)⁴) + Σ 0.6·min(N,4)·A_fin·|x_midchord - x_cg|³/(A_ref L_ref)
    then multiplied by 3 (source comment: 'TODO: Higher damping yields much more realistic apogee turn').
    C_damp = sign(q)·min(mul·(q/V)², Cm), subtracted from Cm and Cyaw.
  - The simulator adds random ±0.0005 noise to Cm and Cyaw at every evaluation.
- Skin friction (BarrowmanCalculator, read in source and verified by running).
  - Fully turbulent (default): Cf = 1/(1.5 ln Re - 5.6)², or 0.0148 for Re < 1e4.
  - Perfect finish: 1.328/sqrt(Re) for Re < 5.39e5; otherwise 1/(1.5 ln Re - 5.6)² - 1700/Re.
  - Compressibility, blended linearly for 0.9 ≤ M ≤ 1.1:
    turbulent: (1 - 0.1M²) subsonic, (1 + 0.15M²)^-0.58 supersonic
    perfect finish: (1 - 0.1M²) subsonic, (1 + 0.045M²)^-0.25 supersonic, only for Re > 1e6 and ramped in between 1e6 and 3e6
  - Roughness limit: Cf_r = 0.032 (k/L_aero)^0.2 · r(M), with r = 1 - 0.1M² subsonic, 1/(1+0.18M²) supersonic, blended in between. k = 500/250/150/60/20/5/2/0.5 µm for rough / rough-unfinished / unfinished / normal / smooth / optimum / polished / finish-polished.
  - Cf_c = max(Cf, Cf_r). For perfect finish, Cf_r is used only if Re > 1e6 and Cf_r > Cf.
  - Bodies: Cf_c·A_wet/A_ref. Fins: Cf_c(1 + 2t/MAC)·2A_fin/A_ref per fin.
  - Total = fins + (1 + 1/(2 f_B))·bodies, with f_B = L/r_max. The code uses the radius where the techdoc says diameter, so the body correction is half the documented one.
- Body pressure, base and fin drag (read in source and verified by running).
  - Stagnation: CD_stag = 0.85·q_stag/q, with q_stag/q = 1 + M²/4 + M⁴/40 for M ≤ 1, and 1.84 - 0.76/M² + 0.166/M⁴ + 0.035/M⁶ above.
  - Every forward-facing step adds CD_stag·ΔA/A_ref.
  - Boattails: CD_base·A_frontal·{1 for γ ≤ 1; (3-γ)/2 for 1 < γ < 3; 0 for γ ≥ 3}, with γ = L/(d1-d2).
  - Cone and ogive noses: Hermite fit on M 1-1.3 with CD(1) = sin φ, CD(1.3) = 2.1 sin²φ + 0.6019 sin φ, slopes 4/(γ+1)(1 - 0.5 sin φ) at M 1 and -1.1341 sin φ at M 1.3. For M ≥ 1.32, CD = 2.1 sin²φ + 0.5 sin φ/sqrt(M²-1). Ogives are multiplied by 0.72(ψ-0.5)² + 0.82.
  - Other noses use Stoney TR-R-100 fineness-3 tables (ellipsoid, x^1/4, x^1/2, x^3/4, parabolic 1/2, 3/4, 1, von Kármán, LV-Haack), interpolated across the shape parameter. They are scaled to the actual fineness by CD_stag·(CD3/CD_stag)^(log(f+1)/log 4). Below the table, CD = a·M^b + 0.8 sin²φ.
  - Base drag: CD_base = 0.12 + 0.13M² for M ≤ 1, 0.25/M above, times the aft-facing area/A_ref. There is no power-on correction in 23.09 or 24.12; master adds one.
  - Fin pressure drag:
    square leading edge: CD_stag·cos²ΓL + CD_base
    rounded or airfoil leading edge: [(1-M²)^-0.417 - 1, or 1 - 1.785(M-0.9), or 1.214 - 0.502/M² + 0.1095/M⁴]·cos²ΓL, plus CD_base/2 for rounded and 0 for airfoil
    all multiplied by span·t/A_ref per fin.
  - Axial drag at angle of attack: CD_axial = CD·m(α), where m is a Hermite fit with m(0) = 1, m(17°) = 1.3, m(90°) = 0.
- Mass properties (masscalc/MassCalculation, SymmetricComponent.calculateProperties, FinSet, motor/*; read in source).
  - Symmetric parts are integrated as 128 conical frustums. Wall thickness is measured normal to the surface; the 'filled' flag is honoured.
  - Fin inertia uses an equal-area rectangle. Fillets and tabs are included.
  - Mass and CG overrides are supported, with flags that also override subcomponents.
  - The assembly is combined with the parallel-axis theorem. Only Ixx and Iyy = Izz are kept; there are no products of inertia.
  - Motors: propellant mass is proportional to cumulative impulse (trapezoidal). In RASP .eng files the CG is fixed at L/2; RSE files can give CG(t).
  - Motor inertia is a solid cylinder: Ixx = m r²/2, Iyy = m(3r² + L²)/12. Clustered motors add m d² to Ixx only.
  - No jet damping, no ṁ term, no thrust misalignment.
- 6-DOF RK4 (RK4SimulationStepper, read in source).
  - Body force vector, rotated by θ about z: F = R_z(θ)(-CN q A, -Cside q A, T - CD_axial q A).
  - a = q⊗F/m⊗q⁻¹ - g ẑ + a_coriolis.
  - Cm_cg = Cm - CN x_cg/L_ref.
  - ω̇_body = (-Cyaw_cg qAL/I_long, Cm_cg qAL/I_long, C_roll qAL/I_rot). There are no ω×Iω or İ terms.
  - Classical RK4 on position, velocity, orientation quaternion (updated by Rot(h·ω_avg)) and angular velocity. Mass is re-evaluated at every stage.
  - Time step h = min of:
    user dt (default 0.05 s; divided by 5 while on the rod)
    time to the next event
    3° / lateral pitch rate
    56.64° / roll rate
    2° / roll acceleration
    4° / pitch acceleration
    L_rod/(10 v) while on the rod
    1.5 × the previous step
    The floor is dt/20.
  - On the rod, acceleration is projected onto the rod direction and angular acceleration is zero.
- Events (BasicEventSimulationEngine, DeploymentConfiguration; read in source).
  - LIFTOFF when the rocket has risen more than 0.02 m.
  - LAUNCHROD (rail exit) when |r - r0| exceeds the full rod length. The lug-based effective length is computed but unused; rail buttons are ignored.
  - BURNOUT at ignition + burn time; EJECTION_CHARGE follows after the motor delay.
  - APOGEE at the first step where z < z_max - 0.01 m, time-stamped at the previous step.
  - Recovery deployment triggers on LAUNCH, EJECTION, APOGEE, ALTITUDE (descending crossing), LOWER_STAGE_SEPARATION or NEVER, plus a delay of at least 1 ms. Deployment under thrust aborts the simulation; speeds above 20 m/s produce a warning.
  - Staging spawns a separate data branch.
  - TUMBLE aborts if thrust is still above 0.01 N.
  - Optimum ejection delay comes from a coast-only re-simulation.
  - Maximum simulation time defaults to 1200 s.
- Recovery and tumble (AbstractEulerStepper, BasicLandingStepper, BasicTumbleStepper; read in source and verified by running).
  - 3-DOF explicit Euler: v += a h, x += v h + a h²/2, with h = min(0.5 s, 1/|a|), shortened for ground hit, apogee and oscillation.
  - a = -(0.5 ρ|v_air|²·ΣN·CD·A/m)·v̂ - g ẑ + a_coriolis. Only the parachute/streamer drag area counts; airframe drag is ignored under canopy.
  - Parachute area A = π(D/2)², default CD 0.8.
  - Streamer CD = 0.034((ρ_A + 0.025)/0.105)(AR+1)/AR.
  - Deployment is instantaneous: the full CdA acts on the first step, with no inflation or snatch model.
  - Tumble CdA = 1.42·Σ A_fin·k_eff(N)/N + 0.56·Σ A_plan, with k_eff = [0, 0.5, 1, 1.41, 1.81, 1.73, 1.90, 1.85].
- Bug confirmed by running: OR under-predicts supersonic wave drag for ogive noses. The code feeds the joint angle at 0.99 L (sin φ ≈ 0 for a tangent ogive) into the cone correlation, while the techdoc says ogives should follow the cone of the same fineness.
  - Test geometry: 0.30 m nose, 80 mm diameter, fineness 3.75.
  - Tangent-ogive nose pressure CD in OR 24.12: 0.0004 at M 2 and 0.0002 at M 3. The cone of the same fineness gives 0.0748 and 0.0600. The deficit is about 14% of total rocket CD.
  - There is also an unphysical bump of 0.038 at M ≈ 1.2.
  - The same code is still on master (2026-10), which even hard-codes sin φ = 0 for the tangent ogive.
- OR's supersonic fin CNa is about half of linear theory. It uses only the windward-surface Busemann pressure (CNa1 = (A_fin/A_ref)·K1 with K1 = 2/β). A flat plate gives Cp_lower - Cp_upper, i.e. CNa = 4/β (Ackeret), and the K2 term cancels. OR's subsonic branch already uses the full two-surface 2π.
  - OR's own techdoc wind-tunnel comparison (Arcas Robin) reports that CNa is 'notably lower than the experimental values … reason unknown', the CP estimate is pessimistic above M 1.5, and drag is too high at high supersonic Mach.
  - Estimate on the test rocket, against two-sided Ackeret with a rectangular tip-loss factor (derived, not validated):
    OR / estimate = 0.73 at M 1.5, 0.63 at M 2, 0.57 at M 3.
    At M 2 the rocket CNa would be 10.8 instead of OR's 7.51 and the CP would be 88 mm (+1.1 cal) further aft; at M 3 the CP shift is +1.6 cal.
  - OR's figure is therefore conservative for static margin, but it under-predicts fin loads, restoring moment and roll forcing.
  - Unchanged on master.
- Other limitations up to Mach 3 (read in source).
  - Body CNa and CP do not vary with Mach (nose CNa = 2). The body-lift crossflow K = 1.1 has no Mach dependence.
  - Transonic behaviour is polynomial bridging only: fin CNa between M 0.9 and 1.5, fin CP between M 0.5 and 2. There is no body transonic wave drag beyond the nose tables.
  - No fin thickness wave drag.
  - Base drag 0.25/M applies even during motor burn.
  - Pitch damping is quadratic and ad hoc. Roll damping and forcing use the same single-surface supersonic K terms.
  - Atmosphere uses linear fits for speed of sound and viscosity.
  - No gyroscopic coupling and no products of inertia.
  - Rail exit uses the full rod length.
  - Recovery deployment is instantaneous. OR's deployment peak accelerations (722 m/s² and 1004 m/s² in the 24.12 dual-deploy example) are artifacts, so OR cannot feed deployment shock-load analysis.
  - Valid as coded: subsonic M < 0.8 good; transonic 0.8-1.2 interpolated; supersonic partial.
- Driving OR from Python (verified by running).
  - Jar URLs follow the pattern https://github.com/openrocket/openrocket/releases/download/release-<v>/OpenRocket-<v>.jar. 23.09 is 71.8 MB with package net.sf.openrocket. 24.12 is 83.1 MB with packages info.openrocket.core / info.openrocket.swing (GuiModule is in info.openrocket.swing.startup).
  - JPype 1.7.1 with Java 21 runs headless.
  - Start-up is about 4 s (23.09) or 7 s (24.12) for Guice plus the motor/preset database. Each simulation then takes 0.05-1.5 s.
  - orhelper 0.1.3 (upstream last commit 2022-08) works with 23.09: the simple-model-rocket example reached 50.65 m with all events. With 24.12 it fails with "Java package 'net' has no attribute 'sf'".
  - My run_or.py handles both versions: Guice + PluginModule + Application.setInjector + startLoader, then waits on the preset and motor loaders, which are private fields.
- Measured OR results with no wind and seed 42 (24.12 / 23.09).
  - Single-stage apogees agree within 0.1%:
    simple rocket S4: 319.14 / 319.37 m
    dual-deploy S1: 593.15 / 593.51 m
    dual-deploy S3: 2224.74 / 2225.00 m, Mach 1.15
    ARC payload: 452.19 / 452.19 m
    tube fin: 282.82 / 282.89 m
  - The two-stage example differs by 1.8% (678.4 / 666.7 m).
  - Descent times differ by up to 3 s because 24.12 rewrote the Euler recovery stepper.
  - Deployment peak acceleration differs (721.9 / 579.4 m/s²).
  - With default wind, 24.12's ground-hit velocity (about 4.6 m/s) includes horizontal drift; both versions give about 4.17 m/s with no wind.
  - Time-step study, dual-deploy S3: apogee 2224.56 / 2224.74 / 2224.70 / 2224.70 m at dt = 0.1 / 0.05 / 0.01 / 0.002 s, so the ascent is converged to about 0.01%. Flight time varies by about 2 s.
  - Values stored in the .ork match a 24.12 re-run closely, but not exactly, because of the random seed.
- Exact reproduction is feasible (verified by running).
  - or_aero_probe.py builds a nose / body / 4-trapezoid-fin rocket inside OR 24.12 and calls BarrowmanCalculator.getAerodynamicForces and getForceAnalysis.
  - or_aero_py.py is an independent port written from the source.
  - They match at 18 Mach numbers from 0.05 to 3 across: tangent ogive, ogive 0.5, ogive 0, conical, Haack 0 and 1/3, power 1/2, ellipsoid and parabolic noses; square, rounded and airfoil fins; normal and polished/perfect finishes.
  - Agreement covers CD, its friction/pressure/base split, CNa and Xcp. Relative error is typically 1e-14; the worst is 9.3e-5, at table edges where OR accumulates x-points by repeated m += 0.05.
  - Reference row (tangent ogive, square fins, NORMAL finish):
    M 0.3: CD 0.5921, CNa 11.595, Xcp 1.0218 m
    M 1.0: CD 0.7192, CNa 12.641
    M 2.0: CD 0.5140, CNa 7.513, Xcp 0.9396 m
    M 3.0: CD 0.4083, CNa 5.376, Xcp 0.8255 m
- Version differences relevant to validation (read in source).
  - 24.12 renamed packages and moved the .ork format from 1.9 to 1.10; 23.09 loaded the 1.10 example files fine.
  - 24.12 also added: the β ≥ 0.25 clamp, multi-level/CSV wind, stall-margin tumble detection, the rewritten Euler recovery stepper, the Component Analysis sweep tool and warning fixes.
  - 24.12 removed TubeCalc's supersonic f/β correction.
  - Master (unreleased 26.xx) adds:
    RK6SimulationStepper and a stepper selector
    Monte-Carlo
    CsvMachAoALookup / LookupTable drag and stability calculators (user aero tables vs Mach and AoA)
    NACA 1307 fin-body interference
    powered base-drag correction
    Neither the ogive nose drag nor the supersonic fin CNa behaviour is fixed on master.
- Other confirmed or likely defects (read in source).
  - TubeFinSetCalc CP polynomial is never initialised.
  - The body-friction fineness ratio uses radius instead of diameter.
  - The Coriolis east-velocity sign looks inverted (tiny effect).
  - Rail-button drag is multiplied by CD_stag twice.
  - At ignition, motor curve time points are queued as absolute times, which is wrong for air-starts.
  - OR's Component Analysis uses 20 °C, not ISA, unless the user changes it.
- Validation references were downloaded from NASA NTRS (reachable through the proxy):
  - NASA TN D-4013 (Ferris; Arcas Robin; M 0.60-1.20): NTRS 19670020050.
  - NASA TN D-4014 (Babb & Fuller; M 1.50-4.63, L/D 18.20 and 23.77, fins canted 0° and 2°, Re 9.84e6/m; data in plots, needs digitising): NTRS 19670020031.
  - Stoney NASA TR-R-100 (source of OR's nose drag tables): NTRS 19630004995.
  - NACA Report 1307 (Pitts-Nielsen-Kaattari interference): NTRS 19930091008.
  - The Niskanen thesis (2009) and the techdoc PDF are in the OR repository under doc/.

## Verified by running

- Cloned OR master (b4eb02a4), release-24.12 (133b558d) and release-23.09 (6c89a3c6) from GitHub with --depth 1. All three succeeded.
- Downloaded both release jars from GitHub releases with curl -L. Both returned HTTP 200: OpenRocket-23.09.jar is 71,758,139 bytes and OpenRocket-24.12.jar is 83,149,098 bytes. The manifests confirm the main classes net.sf.openrocket.startup.OpenRocket (23.09) and info.openrocket.swing.startup.OpenRocket (24.12).
- Installed JPype1 1.7.1, orhelper 0.1.3 and numpy 2.4.6 in a venv.
- Tested stock orhelper with headless mode added through JAVA_TOOL_OPTIONS. On 23.09 it ran 'A simple model rocket': max altitude 50.65 m, 187 points, all events (rail exit at 0.2496 s, apogee at 3.49 s, ground hit at 15.92 s). On 24.12 it fails with AttributeError: Java package 'net' has no attribute 'sf'.
- Ran my JPype driver run_or.py on 20 simulations from 6 example .ork files with OR 24.12, and the same files with OR 23.09 (23.09 loaded the 24.12-saved files). Default wind (2 m/s, 10% turbulence). Examples: 24.12 dual-deploy Sim 3 reached 2223.9 m at Mach 1.147; the stored .ork values were 2223.846 m and Mach 1.147.
- Deterministic runs (no wind, seed 42) in both versions:
  - Apogees agree within about 0.1% for single-stage rockets.
  - The two-stage example differs by 1.8% (678.42 vs 666.66 m).
  - Deployment peak acceleration differs (721.91 vs 579.38 m/s²).
  - Ground-hit velocity is 4.18 vs 4.17 m/s. This confirmed that the 10% gap in the default-wind runs comes from 24.12 reporting total velocity including horizontal drift.
- Time-step sweep on OR 24.12 (dt = 0.1, 0.05, 0.02, 0.01, 0.005, 0.002 s) for dual-deploy Sim 3:
  - Apogee: 2224.564 / 2224.738 / 2224.703 / 2224.695 / 2224.694 / 2224.695 m. The ascent is converged to about 0.01% at the default step.
  - Flight time ranges from 130.1 to 132.1 s.
  - Wall time ranges from about 0.9 to 13 s per simulation.
- Probed OR 24.12's BarrowmanCalculator directly on a rocket built in code: 12 configurations × 18 Mach numbers (0.05-3.0), saved to runs/aero_probe_24.12.json. The tangent-ogive nose pressure CD is 0.0004 at M 2 and 0.0002 at M 3, versus 0.0748 and 0.0600 for the conical nose of the same fineness. The tangent-ogive value peaks at 0.038 at M 1.2.
- Compared my Python port (or_aero_py.py) with OR 24.12 for CD, friction CD, pressure CD, base CD, CNa and Xcp. Maximum relative error over all cases is 9.27e-5 and typically about 1e-14 (runs/aero_compare.txt). This required matching OR's 293.15 K default in AtmosphericConditions; with 288.15 K the perfect-finish friction was off by 0.3%.
- Ran supersonic_gaps.py: the ratio of OR's fin CNa1 to two-sided Ackeret with tip loss is 0.73 / 0.66 / 0.63 / 0.59 / 0.57 at M 1.5 / 1.75 / 2 / 2.5 / 3. With the corrected fins the CP moves +88 mm (+1.10 cal) at M 2 and +130 mm (+1.63 cal) at M 3. This is a derived estimate, not experimental validation.
- Queried the NASA NTRS API and downloaded the public PDFs: TN D-4014 (12.5 MB, 79 pages), TN D-4013 (2.6 MB, 64 pages), TR-R-100 (7.8 MB) and NACA Report 1307 (33 MB). pdftotext on TN D-4014 confirms the test conditions, but the aerodynamic data are only in plots.
- Extracted the text of thesis.pdf and techdoc.pdf with pypdf: thesis is 126 pages (Niskanen, HUT, 20.5.2009), techdoc is 131 pages (v13.05).

## Risks

- GPL-3 licensing. Bundling OR jars or ported code is fine for private and team use, but OR should run as a separate process. A Python port of OR equations written from GPL source arguably makes a derivative work, so keep OR-compat code isolated, or re-derive it from the thesis/techdoc and the papers if the licence matters later.
- The harness blocked REPORT.md, so this structured output is the report. Scripts and data artifacts do exist under the scratch directory.
- My supersonic correction estimates (fin CNa ratio, CP shift, cone-equivalent ogive wave drag) are linear-theory estimates, not validation. Real fin-body and tip effects need NACA 1307/DATCOM-class methods or CFD, and should be checked against the digitised Arcas Robin data.
- OR behaviour will keep changing (master has RK6, lookup tables, NACA 1307 interference and powered base drag). An 'OR-compatible' mode must be pinned to specific versions (23.09, 24.12) and regression-tested against the actual jars.
- OR results are non-deterministic unless wind turbulence is zeroed and the seed is fixed. Comparisons against users' saved .ork results will differ by roughly 0.1-1% because the seed is not stored.
- The two-stage and descent-phase differences between 23.09 and 24.12 (1.8% apogee, about 3 s descent, peak deployment acceleration) mean 'match OR' is version-dependent. The app must say which OR version it is comparing against.
- OR's reported max acceleration and deployment loads are artifacts of instantaneous chute opening. Users must not compare our physically modelled deployment loads with OR's numbers without an explanation.
- The Arcas Robin wind-tunnel data exist only as plots in scanned PDFs. Digitising them takes effort and adds uncertainty of about 2-3%.

## Open questions

- Should OR-compat mode reproduce known OR defects exactly (ogive sinφ, single-surface supersonic fins, radius-based f_B, tube-fin CP, Coriolis sign), with a 'differs from OR because…' report in extended mode? I recommend yes.
- Which OR version is the user's reference: 23.09, 24.12, or both? Should we also track master features (CSV aero lookup tables, RK6, Monte Carlo, NACA 1307) as compatibility targets?
- Is it acceptable to require the user's own Java/OR install for cross-validation, or should the Windows installer bundle a JRE plus the OR 24.12 jar as a separate GPL component?
- Which supersonic fin method should the extended tier use: Barrowman FIN strip theory with tip terms, DATCOM-style charts, or NACA 1307 with linear theory? This depends on how much time we can spend digitising charts.
- Do we digitise the Arcas Robin data (TN D-4013/D-4014) now as the primary Mach 1.5-4.6 validation case, or rely on our own CFD tier for supersonic validation?
- Parachute opening-shock model choice for the deployment-load analysis (Knacke/Pflanz opening-shock factor vs an elastic shock-cord two-body model) and the user's canopy data available (D0, porosity, reefing, line length).

## Artifact notes

NOT WRITTEN. The harness refused to create REPORT.md ("Subagents should return findings as text, not write report files"), so the full report content is in these structured fields instead. Intended path: /tmp/claude-0/-home-user-stress-and-areo/045926a7-bc8f-54ef-a52e-f5484ae3b45a/scratchpad/research/openrocket-methods/REPORT.md. Supporting artifacts are under the same directory, with D=/tmp/claude-0/-home-user-stress-and-areo/045926a7-bc8f-54ef-a52e-f5484ae3b45a/scratchpad/research/openrocket-methods.

Scripts:
- run_or.py: JPype driver for OR 23.09 and 24.12. Env options: NOWIND, TIMESTEP, TAGSUFFIX, OUTDIR.
- or_aero_probe.py: builds a known rocket inside OR and dumps CD/CNa/CP vs Mach per component.
- or_aero_py.py: independent Python port of OR's static aero, plus a comparison main.
- supersonic_gaps.py: estimates of OR's supersonic gaps.
- orhelper_test.py: test of stock orhelper.

Run outputs:
- runs/or24_batch.json, runs/or23_batch.json: default-wind batches.
- runs/nowind_24.12.json, runs/nowind_23.09.json: deterministic runs.
- runs/dt_*.json: time-step study.
- runs/*.csv: time series.
- runs/aero_probe_24.12.json, runs/aero_compare.txt, runs/supersonic_gaps.txt.

Downloads:
- jars/OpenRocket-23.09.jar, jars/OpenRocket-24.12.jar.
- refs/19670020031.pdf: NASA TN D-4014.
- refs/19670020050.pdf: TN D-4013.
- refs/19630004995.pdf: TR-R-100.
- refs/19930091008.pdf: NACA Report 1307.

Source trees:
- or-24.12/ (tag release-24.12, commit 133b558d)
- or-23.09/ (tag release-23.09, commit 6c89a3c6)
- openrocket/ (master b4eb02a4, 2026-10-03). It contains doc/thesis.pdf (Niskanen 2009, 126 pp.) and doc/techdoc/techdoc.pdf plus the .tex sources.
