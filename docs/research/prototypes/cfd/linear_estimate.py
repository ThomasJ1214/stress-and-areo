"""Simplified (tier-2) supersonic linear-theory estimate of CN and x_cp for the test rocket at M=2, AoA=4 deg.
Used only as a sanity check of the CFD normal force / CP (NOT a reference solution).

nose : slender-body theory CN_alpha = 2/rad (ref = base area), CP at 2/3 of cone length
fins : Ackeret 2D lift slope 4/sqrt(M^2-1) per rad on exposed planform (2 panels per lifting pair),
       body interference K_W(B) = 1 + R/(R+s) (Barrowman form), CP at mid-MAC (supersonic)
body : linear theory gives no lift on the cylinder (afterbody carry-over ignored)
"""
import math

M, aoa = 2.0, math.radians(4.0)
R, LN = 0.05, 0.30
Aref = math.pi * R * R
cr, ct, s = 0.12, 0.06, 0.08
x_le_root = 0.88
sweep_dx = 0.06                     # tip LE is 0.06 m aft of root LE
S_panel = 0.5 * (cr + ct) * s
beta = math.sqrt(M * M - 1)
cna_nose = 2.0
x_nose = 2.0 / 3.0 * LN
cna_fin2d = 4.0 / beta
K = 1 + R / (R + s)
cna_fins = cna_fin2d * (2 * S_panel) / Aref * K       # cruciform: 2 effective panels in the pitch plane
mac = 2.0 / 3.0 * (cr + ct - cr * ct / (cr + ct))
y_mac = s / 3.0 * (cr + 2 * ct) / (cr + ct)
x_mac_le = x_le_root + sweep_dx * y_mac / s
x_fins = x_mac_le + 0.5 * mac
CN_nose = cna_nose * math.sin(aoa) * math.cos(aoa)
CN_fins = cna_fins * aoa
CN = CN_nose + CN_fins
x_cp = (CN_nose * x_nose + CN_fins * x_fins) / CN
print(f"CN_nose={CN_nose:.4f} (x={x_nose:.3f} m)  CN_fins+interf={CN_fins:.4f} (K={K:.3f}, x={x_fins:.4f} m)")
print(f"CN_total={CN:.4f}  x_cp={x_cp:.4f} m  ({x_cp/0.1:.2f} D from nose tip)")
print("note: no tip-Mach-cone loss on fins (reduces fin lift ~5-15%) and no afterbody carry-over lift")
