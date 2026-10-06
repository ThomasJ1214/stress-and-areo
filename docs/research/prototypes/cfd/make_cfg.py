"""Write an SU2 v8.5 config for the finned cone-cylinder test case.

python make_cfg.py <case_dir> <mesh.su2> --mach 2.0 --aoa 4.0 [--solver EULER|RANS|INC_EULER] [--iter 3000]
       [--scheme ROE|AUSMPLUSUP2|SLAU2|JST|LMROE] [--lowmach] [--cfl 5] [--cflmax 50]
"""
import argparse
import math
import os

ap = argparse.ArgumentParser()
ap.add_argument("case_dir")
ap.add_argument("mesh")
ap.add_argument("--mach", type=float, default=2.0)
ap.add_argument("--aoa", type=float, default=4.0)
ap.add_argument("--solver", default="EULER")
ap.add_argument("--turb", default="SST")
ap.add_argument("--iter", type=int, default=3000)
ap.add_argument("--scheme", default="ROE")
ap.add_argument("--lowmach", action="store_true")
ap.add_argument("--cfl", type=float, default=5.0)
ap.add_argument("--cflmax", type=float, default=50.0)
ap.add_argument("--mg", type=int, default=0)
ap.add_argument("--nk", action="store_true", help="Newton-Krylov")
ap.add_argument("--wallfunc", action="store_true")
ap.add_argument("--restart", action="store_true")
ap.add_argument("--resmin", type=float, default=-8.0)
ap.add_argument("--venkat", type=float, default=0.03)
ap.add_argument("--limiter", default="VENKATAKRISHNAN_WANG")
a = ap.parse_args()

R = 0.05
ref_area = math.pi * R * R
walls = "nose, body, fins, base"
T_inf, p_inf = 288.15, 101325.0
gamma, Rgas = 1.4, 287.058
a_inf = math.sqrt(gamma * Rgas * T_inf)
U_inf = a.mach * a_inf

lines = []
add = lines.append
inc = a.solver.startswith("INC")
add(f"SOLVER= {a.solver}")
if a.solver in ("RANS", "INC_RANS"):
    add(f"KIND_TURB_MODEL= {a.turb}")
    if a.turb == "SST":
        add("SST_OPTIONS= V2003m")
add("MATH_PROBLEM= DIRECT")
add(f"RESTART_SOL= {'YES' if a.restart else 'NO'}")
add(f"AOA= {a.aoa}")
add("SIDESLIP_ANGLE= 0.0")
if not inc:
    add(f"MACH_NUMBER= {a.mach}")
    add("FREESTREAM_OPTION= TEMPERATURE_FS")
    add(f"FREESTREAM_PRESSURE= {p_inf}")
    add(f"FREESTREAM_TEMPERATURE= {T_inf}")
    add("REF_DIMENSIONALIZATION= FREESTREAM_VEL_EQ_ONE")
    add("FLUID_MODEL= STANDARD_AIR")
    add(f"GAMMA_VALUE= {gamma}")
    add(f"GAS_CONSTANT= {Rgas}")
    if a.solver == "RANS":
        rho = p_inf / (Rgas * T_inf)
        mu = 1.716e-5 * (T_inf / 273.15) ** 1.5 * (273.15 + 110.4) / (T_inf + 110.4)
        Re_per_m = rho * U_inf / mu
        add(f"REYNOLDS_NUMBER= {Re_per_m * 1.0:.6e}")
        add("REYNOLDS_LENGTH= 1.0")
        add("VISCOSITY_MODEL= SUTHERLAND")
        add("MU_CONSTANT= 1.716E-5\nMU_REF= 1.716E-5\nMU_T_REF= 273.15\nSUTHERLAND_CONSTANT= 110.4")
        add("FREESTREAM_TURBULENCEINTENSITY= 0.001\nFREESTREAM_TURB2LAMVISCRATIO= 1.0")
else:
    # incompressible (variable-density capable) pressure-based-like solver, constant density here
    rho = p_inf / (Rgas * T_inf)
    al = math.radians(a.aoa)
    add("INC_DENSITY_MODEL= CONSTANT")
    add("INC_ENERGY_EQUATION= NO")
    add(f"INC_DENSITY_INIT= {rho:.6f}")
    add(f"INC_VELOCITY_INIT= ( {U_inf*math.cos(al):.6f}, 0.0, {U_inf*math.sin(al):.6f} )")
    add("INC_NONDIM= INITIAL_VALUES")
    add("FLUID_MODEL= CONSTANT_DENSITY")
    if a.solver == "INC_RANS":
        add("VISCOSITY_MODEL= CONSTANT_VISCOSITY\nMU_CONSTANT= 1.789E-5")

add("REF_ORIGIN_MOMENT_X= 0.0\nREF_ORIGIN_MOMENT_Y= 0.0\nREF_ORIGIN_MOMENT_Z= 0.0")
add("REF_LENGTH= 0.1")
add(f"REF_AREA= {ref_area:.10f}")

if a.solver in ("EULER", "INC_EULER"):
    add(f"MARKER_EULER= ( {walls} )")
else:
    add(f"MARKER_HEATFLUX= ( nose, 0.0, body, 0.0, fins, 0.0, base, 0.0 )")
    if a.wallfunc:
        add("MARKER_WALL_FUNCTIONS= ( nose, STANDARD_WALL_FUNCTION, body, STANDARD_WALL_FUNCTION, fins, STANDARD_WALL_FUNCTION, base, STANDARD_WALL_FUNCTION )")
add("MARKER_FAR= ( farfield )")
add(f"MARKER_PLOTTING= ( {walls} )")
add(f"MARKER_MONITORING= ( {walls} )")

add("NUM_METHOD_GRAD= GREEN_GAUSS")
add("NUM_METHOD_GRAD_RECON= LEAST_SQUARES")
add(f"CFL_NUMBER= {a.cfl}")
add("CFL_ADAPT= YES")
add(f"CFL_ADAPT_PARAM= ( 0.5, 1.05, {min(a.cfl, 1.0)}, {a.cflmax}, 0.1, 0 )")
add(f"CONV_NUM_METHOD_FLOW= {a.scheme if not inc else 'FDS'}")
add("MUSCL_FLOW= YES")
add(f"SLOPE_LIMITER_FLOW= {a.limiter}")
add(f"VENKAT_LIMITER_COEFF= {a.venkat}")
if a.lowmach and not inc:
    add("LOW_MACH_CORR= YES")
if a.solver in ("RANS", "INC_RANS"):
    add("CONV_NUM_METHOD_TURB= SCALAR_UPWIND\nMUSCL_TURB= NO\nTIME_DISCRE_TURB= EULER_IMPLICIT")
add("TIME_DISCRE_FLOW= EULER_IMPLICIT")
add("LINEAR_SOLVER= FGMRES\nLINEAR_SOLVER_PREC= ILU\nLINEAR_SOLVER_ERROR= 0.05\nLINEAR_SOLVER_ITER= 15")
add(f"MGLEVEL= {a.mg}")
if a.mg:
    add("MGCYCLE= V_CYCLE\nMG_PRE_SMOOTH= ( 1, 2, 3, 3 )\nMG_POST_SMOOTH= ( 0, 0, 0, 0 )\nMG_CORRECTION_SMOOTH= ( 0, 0, 0, 0 )\nMG_DAMP_RESTRICTION= 0.75\nMG_DAMP_PROLONGATION= 0.75")
if a.nk:
    add("NEWTON_KRYLOV= YES\nNEWTON_KRYLOV_IPARAM= (200, 0, 1)\nNEWTON_KRYLOV_DPARAM= (0, 0, 0, 1e-5, -1)")

add(f"ITER= {a.iter}")
add("CONV_FIELD= REL_RMS_DENSITY" if not inc else "CONV_FIELD= REL_RMS_PRESSURE")
add(f"CONV_RESIDUAL_MINVAL= {a.resmin}")
add("CONV_STARTITER= 10")

add(f"MESH_FILENAME= {os.path.relpath(a.mesh, a.case_dir)}")
add("MESH_FORMAT= SU2")
add("SOLUTION_FILENAME= restart_flow.dat\nRESTART_FILENAME= restart_flow.dat")
add("TABULAR_FORMAT= CSV\nCONV_FILENAME= history")
add("VOLUME_FILENAME= flow\nSURFACE_FILENAME= surface_flow")
add("OUTPUT_FILES= (RESTART, PARAVIEW, SURFACE_PARAVIEW, SURFACE_CSV)")
add("VOLUME_OUTPUT= (COORDINATES, SOLUTION, PRIMITIVE)")
sc = "(INNER_ITER, WALL_TIME, RMS_DENSITY, RMS_ENERGY, DRAG, LIFT, MOMENT_Y, AVG_CFL, LINSOL_ITER)" if not inc else \
     "(INNER_ITER, WALL_TIME, RMS_PRESSURE, DRAG, LIFT, MOMENT_Y, AVG_CFL, LINSOL_ITER)"
add(f"SCREEN_OUTPUT= {sc}")
add("HISTORY_OUTPUT= (ITER, WALL_TIME, RMS_RES, REL_RMS_RES, AERO_COEFF, AERO_COEFF_SURF, CFL_NUMBER, LINSOL)")
add("OUTPUT_WRT_FREQ= 500")
add("WRT_FORCES_BREAKDOWN= YES\nBREAKDOWN_FILENAME= forces_breakdown.dat")
add("SCREEN_WRT_FREQ_INNER= 20")

os.makedirs(a.case_dir, exist_ok=True)
with open(os.path.join(a.case_dir, "case.cfg"), "w") as fh:
    fh.write("% generated by make_cfg.py\n" + "\n".join(lines) + "\n")
print(f"U_inf = {U_inf:.3f} m/s, a_inf = {a_inf:.3f} m/s, ref_area = {ref_area:.6e} m^2")
print("wrote", os.path.join(a.case_dir, "case.cfg"))
