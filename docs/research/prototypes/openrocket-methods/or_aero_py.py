"""
Independent Python re-implementation of OpenRocket 24.12's Barrowman-family aerodynamics
(BarrowmanCalculator + SymmetricComponentCalc + FinSetCalc) for a nose + body tube + trapezoidal fin set,
written from reading the Java source.  Purpose: prove we can reproduce OR's numbers (validation tier),
then extend/replace for Mach 0.8-3.

Only zero-AoA axial drag + linear CNa/CP are reproduced here (that is what the probe compares).
"""
import json
import math
import sys

import numpy as np

GAMMA = 1.4
R_AIR = 287.053

# ----------------------------------------------------------------------------------- interpolators

def lin_interp(xs, ys, x):
    """OpenRocket LinearInterpolator: linear inside, constant extrapolation outside."""
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    if x <= xs[0]:
        return float(ys[0])
    if x >= xs[-1]:
        return float(ys[-1])
    return float(np.interp(x, xs, ys))


def poly_interpolator(*points):
    """OpenRocket PolyInterpolator.  points[0] = x positions with value constraints, points[1] = x with
    1st-derivative constraints, points[2] = x with 2nd-derivative constraints ...
    Returns a function(values...) -> coefficient array (highest power first)."""
    n = sum(len(p) for p in points)
    rows = []
    for d, pts in enumerate(points):
        for x0 in pts:
            row = []
            for k in range(n - 1, -1, -1):  # power k, highest first
                if k < d:
                    row.append(0.0)
                else:
                    c = math.factorial(k) / math.factorial(k - d)
                    row.append(c * x0 ** (k - d))
            rows.append(row)
    A = np.array(rows)

    def solve(*values):
        return np.linalg.solve(A, np.array(values, float))
    return solve


def poly_eval(x, coeffs):
    r = 0.0
    for c in coeffs:
        r = r * x + c
    return r

# ----------------------------------------------------------------------------------- atmosphere

def atmosphere_sea_level():
    T, p = 293.15, 101325.0   # OR AtmosphericConditions() default (STANDARD_TEMPERATURE=293.15 K!)
    rho = p / (R_AIR * T)
    a = 165.77 + 0.606 * T                      # OR linear speed-of-sound approximation
    mu = 3.7291e-06 + 4.9944e-08 * T            # OR linear viscosity approximation
    return dict(T=T, p=p, rho=rho, a=a, nu=mu / rho)

# ----------------------------------------------------------------------------------- nose shapes

def shape_radius(shape, x, R, L, param):
    if shape == "CONICAL":
        return R * x / L
    if shape == "OGIVE":
        if L < R:
            x = x * R / L
            L = R
        if param < 1e-6:  # MINFEATURE
            return R * x / L
        Rc = math.sqrt((L ** 2 + R ** 2) * (((2 - param) * L) ** 2 + (param * R) ** 2) / (4 * (param * R) ** 2))
        Lp = L / param
        y0 = math.sqrt(max(Rc * Rc - Lp * Lp, 0))
        return math.sqrt(max(Rc * Rc - (Lp - x) ** 2, 0)) - y0
    if shape == "ELLIPSOID":
        x = x * R / L
        return math.sqrt(max(2 * R * x - x * x, 0))
    if shape == "POWER":
        if param <= 1e-5:
            return 0.0 if x <= 1e-5 else R
        return R * (x / L) ** param
    if shape == "PARABOLIC":
        return R * ((2 * x / L - param * (x / L) ** 2) / (2 - param))
    if shape == "HAACK":
        th = math.acos(1 - 2 * x / L)
        return R * math.sqrt(max((th - math.sin(2 * th) / 2 + param * math.sin(th) ** 3) / math.pi, 0))
    raise ValueError(shape)


def symmetric_properties(rfun, L, n=128):
    """SymmetricComponent.calculateProperties(): wet area, planform area & center, full volume."""
    wet = plan = planc = fullV = 0.0
    for i in range(n):
        x1, x2 = i * L / n, (i + 1) * L / n
        l = x2 - x1
        r1, r2 = rfun(x1), rfun(x2)
        wet += (r1 + r2) * math.sqrt((r1 - r2) ** 2 + l ** 2)
        dA = l * (r1 + r2)
        plan += dA
        planc += dA * x1 + 2.0 * l ** 2 * (r1 / 6.0 + r2 / 3.0)
        fullV += l * (r1 * r1 + r1 * r2 + r2 * r2)  # 3/pi * frustum volume
    return dict(wet=wet * math.pi, plan=plan, planCenter=planc / plan if plan > 0 else 0,
                fullVolume=fullV * math.pi / 3.0)

# ----------------------------------------------------------------------------------- drag pieces

def stagnation_cd(M):
    if M <= 1:
        q = 1 + M ** 2 / 4 + M ** 4 / 40
    else:
        q = 1.84 - 0.76 / M ** 2 + 0.166 / M ** 4 + 0.035 / M ** 6
    return 0.85 * q


def base_cd(M):
    return 0.12 + 0.13 * M * M if M <= 1 else 0.25 / M


def friction_coefficient(M, Re, perfect):
    c1 = c2 = 1.0
    if perfect:
        if Re < 1e4:
            Cf = 1.33e-2
        elif Re < 5.39e5:
            Cf = 1.328 / math.sqrt(Re)
        else:
            Cf = 1.0 / (1.50 * math.log(Re) - 5.6) ** 2 - 1700 / Re
        if M < 1.1 and Re > 1e6:
            c1 = 1 - 0.1 * M * M * ((Re - 1e6) / 2e6 if Re < 3e6 else 1)
        if M > 0.9 and Re > 1e6:
            f = 1.0 / (1 + 0.045 * M * M) ** 0.25
            c2 = 1 + (f - 1) * (Re - 1e6) / 2e6 if Re < 3e6 else f
    else:
        Cf = 1.48e-2 if Re < 1e4 else 1.0 / (1.50 * math.log(Re) - 5.6) ** 2
        if M < 1.1:
            c1 = 1 - 0.1 * M * M
        if M > 0.9:
            c2 = 1 / (1 + 0.15 * M * M) ** 0.58
    if M < 0.9:
        return Cf * c1
    if M < 1.1:
        return Cf * (c2 * (M - 0.9) / 0.2 + c1 * (1.1 - M) / 0.2)
    return Cf * c2


def roughness_correction(M):
    if M < 0.9:
        return 1 - 0.1 * M * M
    if M > 1.1:
        return 1 / (1 + 0.18 * M * M)
    c1 = 1 - 0.1 * 0.9 ** 2
    c2 = 1.0 / (1 + 0.18 * 1.1 ** 2)
    return c2 * (M - 0.9) / 0.2 + c1 * (1.1 - M) / 0.2

# nose cone experimental tables (Stoney, NASA TR-R-100, fineness 3) as in SymmetricComponentCalc
TABLES = {
    "ellipsoid": ([1.2, 1.25, 1.3, 1.4, 1.6, 2.0, 2.4], [0.110, 0.128, 0.140, 0.148, 0.152, 0.159, 0.162]),
    "x14": ([1.2, 1.3, 1.4, 1.6, 1.8, 2.2, 2.6, 3.0, 3.6], [0.140, 0.156, 0.169, 0.192, 0.206, 0.227, 0.241, 0.249, 0.252]),
    "x12": ([0.925, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.7, 2.0], [0, 0.014, 0.050, 0.060, 0.059, 0.081, 0.084, 0.085, 0.078]),
    "x34": ([0.8, 0.9, 1.0, 1.06, 1.2, 1.4, 1.6, 2.0, 2.8, 3.4], [0, 0.015, 0.078, 0.121, 0.110, 0.098, 0.090, 0.084, 0.078, 0.074]),
    "vonKarman": ([0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.4, 1.6, 2.0, 3.0], [0, 0.010, 0.027, 0.055, 0.070, 0.081, 0.095, 0.097, 0.091, 0.083]),
    "lvHaack": ([0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.4, 1.6, 2.0], [0, 0.010, 0.024, 0.066, 0.084, 0.100, 0.114, 0.117, 0.113]),
    "parabolic": ([0.95, 0.975, 1.0, 1.05, 1.1, 1.2, 1.4, 1.7], [0, 0.016, 0.041, 0.092, 0.109, 0.119, 0.113, 0.108]),
    "parabolic12": ([0.8, 0.9, 0.95, 1.0, 1.05, 1.1, 1.3, 1.5, 1.8], [0, 0.016, 0.042, 0.100, 0.126, 0.125, 0.100, 0.090, 0.088]),
    "parabolic34": ([0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.4, 1.7], [0, 0.023, 0.073, 0.098, 0.107, 0.106, 0.089, 0.082]),
}
_blunt_x = [round(m, 10) for m in np.arange(0, 3, 0.05)]
TABLES["blunt"] = (_blunt_x, [stagnation_cd(m) for m in _blunt_x])
_conical_poly = poly_interpolator([1.0, 1.3], [1.0, 1.3])


def ogive_table(param, sinphi):
    """calculateOgiveNoseInterpolator(param, sinphi) -> (xs, ys)."""
    cd1 = sinphi
    cd13 = 2.1 * sinphi ** 2 + 0.6019 * sinphi
    coef = _conical_poly(cd1, cd13, 4 / (GAMMA + 1) * (1 - 0.5 * cd1), -1.1341 * sinphi)
    mul = 0.72 * (param - 0.5) ** 2 + 0.82
    xs, ys = [], []
    m = 1.0
    while m < 1.3001:
        xs.append(m)
        ys.append(mul * poly_eval(m, coef))
        m += 0.02
    m = 1.32
    while m < 4:
        xs.append(m)
        ys.append(mul * (2.1 * sinphi ** 2 + 0.5 * sinphi / math.sqrt(m * m - 1)))
        m += 0.02
    return xs, ys


def nose_pressure_table(shape, param, fineness, sinphi):
    """SymmetricComponentCalc.calculateNoseInterpolator()."""
    cone_sin = 1 / math.sqrt(1 + 4 * fineness ** 2)
    int1 = int2 = None
    p = 0
    if shape == "CONICAL":
        xs, ys = ogive_table(0, sinphi)
    elif shape == "OGIVE":
        xs, ys = ogive_table(param, sinphi)       # NOTE: sinphi = joint angle, not cone half-angle
    else:
        if shape == "ELLIPSOID":
            int1 = TABLES["ellipsoid"]
        elif shape == "POWER":
            if param <= 0.25:
                int1, int2, p = TABLES["blunt"], TABLES["x14"], param * 4
            elif param <= 0.5:
                int1, int2, p = TABLES["x14"], TABLES["x12"], (param - 0.25) * 4
            elif param <= 0.75:
                int1, int2, p = TABLES["x12"], TABLES["x34"], (param - 0.5) * 4
            else:
                int1, int2, p = TABLES["x34"], ogive_table(0, cone_sin), (param - 0.75) * 4
        elif shape == "PARABOLIC":
            if param <= 0.5:
                int1, int2, p = ogive_table(0, cone_sin), TABLES["parabolic12"], param * 2
            elif param <= 0.75:
                int1, int2, p = TABLES["parabolic12"], TABLES["parabolic34"], (param - 0.5) * 4
            else:
                int1, int2, p = TABLES["parabolic34"], TABLES["parabolic"], (param - 0.75) * 4
        elif shape == "HAACK":
            int1, int2, p = TABLES["vonKarman"], TABLES["lvHaack"], param * 3
        if int2 is not None:
            pts = sorted(set(list(int1[0]) + list(int2[0])))
            ys3 = [p * lin_interp(*int2, m) + (1 - p) * lin_interp(*int1, m) for m in pts]
            int1 = (pts, ys3)
        log4 = math.log(fineness + 1) / math.log(4)
        xs, ys = [], []
        for m in int1[0]:
            stag = lin_interp(*TABLES["blunt"], m)
            xs.append(m)
            ys.append(stag * (lin_interp(*int1, m) / stag) ** log4)
    # subsonic fill-in: Cd = a*M^b + cd(M=0)
    order = np.argsort(xs)
    xs = list(np.asarray(xs)[order])
    ys = list(np.asarray(ys)[order])
    mmin, vmin = xs[0], ys[0]
    if vmin >= 0.001:
        cd0 = 0.8 * sinphi ** 2
        deriv = (lin_interp(xs, ys, mmin + 0.01) - vmin) / 0.01
        if not (cd0 >= vmin - 0.01 or deriv <= 0.01):
            b = mmin * deriv / (vmin - cd0)
            a = (vmin - cd0) / mmin ** b
            m = 0.0
            while m < mmin:
                xs.append(m)
                ys.append(a * m ** b + cd0)
                m += 0.05
    return xs, ys

# ----------------------------------------------------------------------------------- fins

K_MACH = [1.5 + i * 0.1 for i in range(int((5.0 - 1.5) * 10))]


def K123(M):
    k1, k2, k3 = [], [], []
    for m in K_MACH:
        b = math.sqrt(m * m - 1)
        k1.append(2.0 / b)
        k2.append(((GAMMA + 1) * m ** 4 - 4 * b ** 2) / (4 * b ** 4))
        k3.append(((GAMMA + 1) * m ** 8 + (2 * GAMMA ** 2 - 7 * GAMMA - 5) * m ** 6 + 10 * (GAMMA + 1) * m ** 4 + 8)
                  / (6 * b ** 7))
    return lin_interp(K_MACH, k1, M), lin_interp(K_MACH, k2, M), lin_interp(K_MACH, k3, M)


_cna_poly = poly_interpolator([0.9, 1.5], [0.9, 1.5], [0.9])


def trapezoid_fin_geometry(root, tip, sweep, span, divisions=48):
    """FinSetCalc.calculateFinGeometry() strip method for a trapezoid fin (body radius const)."""
    pts = [(0.0, 0.0), (sweep, span), (sweep + tip, span), (root, 0.0)]
    lead = [math.inf] * divisions
    trail = [-math.inf] * divisions
    clen = [0.0] * divisions
    for k in range(1, len(pts)):
        x1, y1 = pts[k - 1]
        x2, y2 = pts[k]
        if abs(y1 - y2) < 0.001:
            continue
        i1 = int(y1 * 1.0001 / span * (divisions - 1))
        i2 = int(y2 * 1.0001 / span * (divisions - 1))
        i1, i2 = max(0, min(i1, divisions - 1)), max(0, min(i2, divisions - 1))
        if i1 > i2:
            i1, i2 = i2, i1
        for i in range(i1, i2 + 1):
            y = i * span / (divisions - 1)
            x = (y - y2) / (y1 - y2) * x1 + (y1 - y) / (y1 - y2) * x2
            x = min(max(x, min(x1, x2)), max(x1, x2))
            lead[i] = min(lead[i], x)
            trail[i] = max(trail[i], x)
            clen[i] += -x if y1 < y2 else x
    for i in range(divisions):
        if math.isinf(lead[i]) or math.isinf(trail[i]):
            lead[i] = trail[i] = 0
        if clen[i] < 0:
            clen[i] = 0
        clen[i] = min(clen[i], trail[i] - lead[i])
    dy = span / (divisions - 1)
    macL = macS = macLead = area = cosG = cosGL = 0.0
    for i in range(divisions):
        length = trail[i] - lead[i]
        y = i * dy
        macL += length * length
        macS += y * length
        macLead += lead[i] * length
        area += length
        if i > 0:
            dx = (trail[i] + lead[i]) / 2 - (trail[i - 1] + lead[i - 1]) / 2
            cosG += dy / math.hypot(dx, dy)
            dx = lead[i] - lead[i - 1]
            cosGL += dy / math.hypot(dx, dy)
    macL *= dy; macS *= dy; macLead *= dy; area *= dy
    return dict(macLength=macL / area, macSpan=macS / area, macLead=macLead / area,
                cosGamma=cosG / (divisions - 1), cosGammaLead=cosGL / (divisions - 1),
                area=0.5 * (root + tip) * span, ar=2 * span ** 2 / (0.5 * (root + tip) * span), span=span)


def cp_poly(ar):
    d = (1 - 3.4641 * ar) ** 2
    return [9.16049 * (-0.588838 + ar) * (-0.20624 + ar) / d,
            -31.6049 * (-0.705375 + ar) * (-0.198476 + ar) / d,
            55.3086 * (-0.711482 + ar) * (-0.196772 + ar) / d,
            -39.5062 * (-0.72074 + ar) * (-0.194245 + ar) / d,
            12.8395 * (-0.725688 + ar) * (-0.19292 + ar) / d,
            -1.58025 * (-0.728769 + ar) * (-0.192105 + ar) / d]  # poly[0..5], ascending powers


def fin_cp_frac(M, ar):
    if M <= 0.5:
        return 0.25
    beta = max(0.25, math.sqrt(abs(M * M - 1)))
    if M >= 2:
        return (ar * beta - 0.67) / (2 * ar * beta - 1)
    p = cp_poly(ar)
    return sum(c * M ** i for i, c in enumerate(p))


def fin_cna1(M, g, Aref, alpha=0.0):
    s, A, cg = g["span"], g["area"], g["cosGamma"]
    if M <= 0.9:
        return 2 * math.pi * s ** 2 / (1 + math.sqrt(1 + (1 - M * M) * (s ** 2 / (A * cg)) ** 2)) / Aref
    if M >= 1.5:
        k1, k2, k3 = K123(M)
        return A * (k1 + k2 * alpha + k3 * alpha ** 2) / Aref
    sq = math.sqrt(1 + (1 - 0.9 ** 2) * (s * s / (A * cg)) ** 2)
    subV = 2 * math.pi * s ** 2 / Aref / (1 + sq)
    subD = 2 * M * math.pi * s ** 6 / ((A * cg) ** 2 * Aref * sq * (1 + sq) ** 2)
    k1, k2, k3 = K123(1.5)
    superV = A * (k1 + k2 * alpha + k3 * alpha ** 2) / Aref
    superD = -A / Aref * 2 * 1.5 / (1.5 ** 2 - 1) ** 1.5
    return poly_eval(M, _cna_poly(subV, superV, subD, superD, 0.0))

# ----------------------------------------------------------------------------------- whole rocket

def rocket_aero(geom, nose_shape, nose_param, M, cross="SQUARE", roughness=60e-6, perfect=False):
    atm = atmosphere_sea_level()
    R, Ln, Lb = geom["R"], geom["nose_len"], geom["body_len"]
    Aref = math.pi * R * R
    Laero = Ln + Lb
    V = M * atm["a"]
    Re = V * Laero / atm["nu"]
    # --- geometry
    rnose = lambda x: shape_radius(nose_shape, x, R, Ln, nose_param)
    nprop = symmetric_properties(rnose, Ln)
    bprop = dict(wet=2 * math.pi * R * Lb, plan=2 * R * Lb, planCenter=Lb / 2)
    fg = trapezoid_fin_geometry(geom["root"], geom["tip"], geom["sweep"], geom["span"])
    N, t = geom["fin_n"], geom["fin_t"]
    # --- friction
    Cf = friction_coefficient(M, Re, perfect)
    rl = 0.032 * (roughness / Laero) ** 0.2 * roughness_correction(M)
    if perfect:
        Cc = rl if (Re > 1e6 and rl > Cf) else Cf
    else:
        Cc = max(Cf, rl)
    body_fric = Cc * nprop["wet"] / Aref + Cc * bprop["wet"] / Aref
    fB = (Laero + 0.0001) / R
    fin_fric = N * Cc * (1 + 2 * t / fg["macLength"]) * 2 * fg["area"] / Aref
    fric = fin_fric + body_fric * (1 + 1.0 / (2 * fB))
    # --- pressure
    r99 = rnose(0.99 * Ln)
    sinphi = (R - r99) / math.hypot(R - r99, 0.01 * Ln)
    fineness = Ln / (2 * R)
    xs, ys = nose_pressure_table(nose_shape, nose_param, fineness, sinphi)
    nose_press = lin_interp(xs, ys, M) * (math.pi * R * R) / Aref
    stag, base = stagnation_cd(M), base_cd(M)
    if cross == "SQUARE":
        cdf = stag
    else:
        if M < 0.9:
            cdf = (1 - M * M) ** -0.417 - 1
        elif M < 1:
            cdf = 1 - 1.785 * (M - 0.9)
        else:
            cdf = 1.214 - 0.502 / M ** 2 + 0.1095 / M ** 4
    cdf *= fg["cosGammaLead"] ** 2
    if cross == "SQUARE":
        cdf += base
    elif cross == "ROUNDED":
        cdf += base / 2
    fin_press = N * cdf * fg["span"] * t / Aref
    press = nose_press + fin_press
    base_total = base * math.pi * R * R / Aref
    CD = fric + press + base_total
    # --- normal force (alpha -> 0)
    cna_nose = 2.0  # 2*(A1-A0)/Aref
    cp_nose = (Ln * math.pi * R * R - nprop["fullVolume"]) / (math.pi * R * R)
    tau = R / (fg["span"] + R)
    cna_fins = fin_cna1(M, fg, Aref) * (N / 2.0) * (1 + tau)  # sum sin^2 over N>=3 evenly spaced = N/2
    fin_front_x = Ln + Lb - geom["root"]
    cp_fins = fin_front_x + fg["macLead"] + fin_cp_frac(M, fg["ar"]) * fg["macLength"]
    CNa = cna_nose + cna_fins
    CPx = (cna_nose * cp_nose + cna_fins * cp_fins) / CNa
    return dict(M=M, CD=CD, fric=fric, press=press, base=base_total, CNa=CNa, CPx=CPx, Re=Re, nosePr=nose_press,
                finPr=fin_press, sinphi=sinphi, nose_wet=nprop["wet"], fin=fg)


if __name__ == "__main__":
    probe = json.load(open(sys.argv[1]))
    geom = probe["geom"]
    maxerr = {}
    lines = []
    for case, rows in probe["cases"].items():
        if "aoa" in case:
            continue
        parts = case.split("_")
        shape, param, cross = parts[0], float(parts[1]), parts[2]
        perfect = case.endswith("PERFECT")
        rough = 2e-6 if "POLISHED" in case else 60e-6
        for r in rows:
            m = rocket_aero(geom, shape, param, r["M"], cross=cross, roughness=rough, perfect=perfect)
            for k in ("CD", "fric", "press", "base", "CNa", "CPx"):
                rel = abs(m[k] - r[k]) / max(abs(r[k]), 1e-9)
                if rel > maxerr.get((case, k), (0, None))[0]:
                    maxerr[(case, k)] = (rel, r["M"], r[k], m[k])
            lines.append(f"{case:38s} M={r['M']:4.2f}  CD OR={r['CD']:.4f} py={m['CD']:.4f} | "
                         f"CNa OR={r['CNa']:.3f} py={m['CNa']:.3f} | CPx OR={r['CPx']:.4f} py={m['CPx']:.4f}")
    print("\n".join(lines))
    print("\nMax relative error per (case, quantity):")
    worst = 0
    for (case, k), (e, M, a, b) in sorted(maxerr.items()):
        worst = max(worst, e)
        print(f"  {case:38s} {k:5s} maxrel={e:.2e} at M={M} (OR={a:.5f}, py={b:.5f})")
    print("WORST", worst)
