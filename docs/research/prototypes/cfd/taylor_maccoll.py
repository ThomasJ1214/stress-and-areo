"""Taylor-Maccoll exact inviscid solution for supersonic flow over a sharp cone at zero incidence.

Independent reference for the CFD feasibility test (forebody wave drag).

Nondimensional velocity V' = V / V_max, V_max = sqrt(2 h0).
ODE (theta = polar angle measured from cone axis, Vr = V'_r, Vt = dVr/dtheta = V'_theta):
    (g-1)/2 * [1 - Vr^2 - Vr'^2] * [2 Vr + Vr' cot(theta) + Vr''] - Vr'^2 * [Vr + Vr''] = 0
Solved for Vr'' and integrated from the shock (theta = beta) inward until V'_theta = 0 (cone surface).
Shooting on beta gives the shock angle for a prescribed cone half-angle.
"""
import math
import sys
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq


def oblique_shock(M1, beta, g=1.4):
    Mn1 = M1 * math.sin(beta)
    p21 = 1.0 + 2.0 * g / (g + 1.0) * (Mn1 ** 2 - 1.0)
    Mn2 = math.sqrt((1.0 + 0.5 * (g - 1.0) * Mn1 ** 2) / (g * Mn1 ** 2 - 0.5 * (g - 1.0)))
    tan_d = 2.0 / math.tan(beta) * (M1 ** 2 * math.sin(beta) ** 2 - 1.0) / (M1 ** 2 * (g + math.cos(2 * beta)) + 2.0)
    delta = math.atan(tan_d)
    M2 = Mn2 / math.sin(beta - delta)
    return delta, M2, p21


def rhs(theta, y, g):
    Vr, Vt = y
    a = 0.5 * (g - 1.0) * (1.0 - Vr ** 2 - Vt ** 2)
    num = Vt ** 2 * Vr - a * (2.0 * Vr + Vt / math.tan(theta))
    den = a - Vt ** 2
    return [Vt, num / den]


def cone_from_beta(M1, beta, g=1.4):
    delta, M2, p21 = oblique_shock(M1, beta, g)
    V2 = (2.0 / ((g - 1.0) * M2 ** 2) + 1.0) ** -0.5
    Vr0 = V2 * math.cos(beta - delta)
    Vt0 = -V2 * math.sin(beta - delta)

    def ev(theta, y, g):
        return y[1]
    ev.terminal = True
    ev.direction = 1  # Vt goes from negative to zero
    sol = solve_ivp(rhs, [beta, 1e-4], [Vr0, Vt0], args=(g,), events=ev, rtol=1e-12, atol=1e-14, max_step=1e-3)
    if sol.t_events[0].size == 0:
        return None
    th_c = sol.t_events[0][0]
    Vr_c = sol.y_events[0][0][0]
    Mc = math.sqrt(2.0 / (g - 1.0) * Vr_c ** 2 / (1.0 - Vr_c ** 2))
    # isentropic from just behind shock (M2, p2) to surface (Mc, pc)
    pc_p2 = ((1.0 + 0.5 * (g - 1.0) * M2 ** 2) / (1.0 + 0.5 * (g - 1.0) * Mc ** 2)) ** (g / (g - 1.0))
    pc_p1 = pc_p2 * p21
    Cp = (pc_p1 - 1.0) / (0.5 * g * M1 ** 2)
    return dict(theta_c=th_c, beta=beta, Mc=Mc, pc_p1=pc_p1, Cp=Cp, M2=M2, delta=delta)


def solve_cone(M1, theta_c_deg, g=1.4):
    tc = math.radians(theta_c_deg)
    mu = math.asin(1.0 / M1)

    def f(beta):
        r = cone_from_beta(M1, beta, g)
        return (r["theta_c"] if r else 0.0) - tc
    # weak-shock branch: beta between Mach angle and ~ the detachment angle
    b_lo = mu + 1e-6
    b_hi = b_lo
    while f(b_hi) < 0 and b_hi < math.radians(89):
        b_hi += math.radians(0.5)
    beta = brentq(f, b_lo, b_hi, xtol=1e-12)
    return cone_from_beta(M1, beta, g)


def modified_newtonian_cp(M1, theta_c, g=1.4):
    """Modified-Newtonian estimate Cp = Cp_max sin^2(theta), Cp_max from the Rayleigh pitot formula.
    Shown only to illustrate that impact methods are poor at low supersonic Mach (not a reference)."""
    th = math.radians(theta_c)
    # Modified Newtonian: Cp = Cp_max sin^2(theta) with Cp_max from Rayleigh pitot
    p02_pinf = ((g + 1) ** 2 * M1 ** 2 / (4 * g * M1 ** 2 - 2 * (g - 1))) ** (g / (g - 1)) * (1 - g + 2 * g * M1 ** 2) / (g + 1)
    cpmax = (p02_pinf - 1) / (0.5 * g * M1 ** 2)
    return cpmax * math.sin(th) ** 2


if __name__ == "__main__":
    g = 1.4
    cases = [(2.0, math.degrees(math.atan(0.05 / 0.30)))]
    if len(sys.argv) == 3:
        cases = [(float(sys.argv[1]), float(sys.argv[2]))]
    # sanity check against NACA 1135 / classical charts: M=2, 10 deg cone -> beta ~ 31.2 deg, Cp ~ 0.105 (approx.)
    for M, th in [(2.0, 10.0)] + cases + [(3.0, math.degrees(math.atan(0.05 / 0.30))), (1.5, math.degrees(math.atan(0.05 / 0.30)))]:
        r = solve_cone(M, th, g)
        print(f"M={M:.3f} theta_c={th:.4f} deg -> beta={math.degrees(r['beta']):.4f} deg, Mc={r['Mc']:.4f}, "
              f"pc/pinf={r['pc_p1']:.5f}, Cp_cone={r['Cp']:.5f}, modNewtonian Cp={modified_newtonian_cp(M, th):.5f}")
