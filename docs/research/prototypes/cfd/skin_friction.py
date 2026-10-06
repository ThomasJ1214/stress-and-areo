"""Engineering skin-friction and wall-spacing helpers (independent estimates used to judge RANS results).

* van Driest II compressible turbulent flat-plate mean skin friction (adiabatic wall) applied to the
  Karman-Schoenherr incompressible law 0.242/sqrt(Cf) = log10(Re Cf)  (Hopkins & Inouye, AIAA J 9(6) 1971).
* first-cell height for a target y+ (flat-plate estimate at x = L).
"""
import math

G, RG = 1.4, 287.058


def mu_suth(T):
    return 1.716e-5 * (T / 273.15) ** 1.5 * (273.15 + 110.4) / (T + 110.4)


def cf_inc_ks(Re):
    """Karman-Schoenherr mean (plate-averaged) turbulent skin friction: 0.242/sqrt(Cf) = log10(Re*Cf)."""
    cf = 0.455 / math.log10(Re) ** 2.58          # Prandtl-Schlichting start value
    for _ in range(100):
        cf = (0.242 / math.log10(Re * cf)) ** 2
    return cf


def cf_van_driest2(M, Re_x, Te=288.15, r=0.89):
    m = r * 0.5 * (G - 1) * M * M
    Tw_Te = 1.0 + m                      # adiabatic wall
    A = math.sqrt(m / Tw_Te)
    B = (1.0 + m) / Tw_Te - 1.0
    den = math.sqrt(B * B + 4 * A * A)
    C1 = (2 * A * A - B) / den
    C2 = B / den
    Fc = m / (math.asin(C1) + math.asin(C2)) ** 2 if M > 1e-3 else 1.0
    F_rtheta = mu_suth(Te) / mu_suth(Te * Tw_Te)
    F_rx = F_rtheta / Fc
    return cf_inc_ks(Re_x * F_rx) / Fc, Fc, Tw_Te


def first_cell(M, L, yplus, p=101325.0, T=288.15):
    a = math.sqrt(G * RG * T)
    U = M * a
    rho = p / (RG * T)
    Re = rho * U * L / mu_suth(T)
    cf, Fc, Tw_Te = cf_van_driest2(M, Re, T)
    # local Cf ~ 0.8 * mean Cf near x = L (turbulent); wall properties at adiabatic wall temperature
    tau = 0.8 * cf * 0.5 * rho * U * U
    Tw = T * Tw_Te
    rho_w = p / (RG * Tw)
    utau = math.sqrt(tau / rho_w)
    nu_w = mu_suth(Tw) / rho_w
    return yplus * nu_w / utau, Re, cf


if __name__ == "__main__":
    print("M     Re_L(L=1m)   Cf_mean(vD2)  Cf_inc   y(y+=1)     y(y+=30)")
    for M in [0.1, 0.3, 0.8, 1.2, 2.0, 3.0]:
        y1, Re, cf = first_cell(M, 1.0, 1.0)
        y30, _, _ = first_cell(M, 1.0, 30.0)
        print(f"{M:4.1f}  {Re:10.3e}   {cf:.5f}      {cf_inc_ks(Re):.5f}  {y1:.2e}   {y30:.2e}")
    # friction drag estimate for the test rocket at M=2, sea level, AoA 0 (turbulent from the nose tip)
    R, LN, L = 0.05, 0.30, 1.0
    Aref = math.pi * R * R
    S_nose = math.pi * R * math.hypot(LN, R)
    S_body = 2 * math.pi * R * (L - LN)
    S_fins = 4 * 2 * 0.5 * (0.12 + 0.06) * 0.08
    M = 2.0
    a = math.sqrt(G * RG * 288.15)
    rho = 101325 / (RG * 288.15)
    Re_L = rho * M * a * L / mu_suth(288.15)
    cf_body, _, _ = cf_van_driest2(M, Re_L)
    mac = 2 / 3 * (0.12 + 0.06 - 0.12 * 0.06 / 0.18)
    cf_fin, _, _ = cf_van_driest2(M, rho * M * a * mac / mu_suth(288.15))
    CDf = (cf_body * (S_nose + S_body) + cf_fin * S_fins) / Aref
    print(f"\nTest rocket M=2: Re_L={Re_L:.3e}, Cf_body={cf_body:.5f}, Cf_fin(MAC={mac:.4f} m)={cf_fin:.5f}")
    print(f"  wetted areas: nose {S_nose:.4f}, body {S_body:.4f}, fins {S_fins:.4f} m^2; Aref {Aref:.6f} m^2")
    print(f"  friction drag CD_f (body+nose) = {cf_body*(S_nose+S_body)/Aref:.4f}, fins = {cf_fin*S_fins/Aref:.4f}, total = {CDf:.4f}")
