"""Off-screen pyvista rendering of ccx results (verifies the viewer pipeline: frd -> vtu -> 3D)."""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyvista as pv
from fea_common import read_frd, frd_to_vtu
pv.OFF_SCREEN = True
os.makedirs("img", exist_ok=True)
# 1) fin root stress map (von Mises) with deformation x50
g = frd_to_vtu(read_frd("case_bc/b2_fin.frd"), "case_bc/b2_fin.vtu")
surf = g.extract_surface(nonlinear_subdivision=2)
warped = surf.warp_by_vector("DISP_0", factor=50)
p = pv.Plotter(window_size=(1000, 700))
p.add_mesh(warped, scalars="VONMISES_0", cmap="turbo", show_edges=False,
           scalar_bar_args=dict(title="von Mises [MPa]"))
p.add_mesh(surf, style="wireframe", opacity=0.15, color="gray")
p.view_isometric(); p.screenshot("img/b2_fin_vonmises.png"); p.close()
# 2) first buckling mode of the composite tube
fr = read_frd("case_a/a1_comp.frd")
g = frd_to_vtu(fr, "case_a/a1_comp_render.vtu")
s = g.extract_surface(nonlinear_subdivision=1)
d = s["DISP_1"]; s["|U|"] = np.linalg.norm(d, axis=1)
w = s.warp_by_vector("DISP_1", factor=5.0 / np.abs(d).max())
p = pv.Plotter(window_size=(800, 900))
p.add_mesh(w, scalars="|U|", cmap="viridis", scalar_bar_args=dict(title="buckling mode 1 |U| (normalised)"))
p.view_xz(); p.camera.elevation = 20; p.screenshot("img/a1_tube_mode1.png"); p.close()
# 3) solid orthotropic bar (C3D10) displacement
g = pv.read("case_d/d2_cantilever.vtu") if os.path.exists("case_d/d2_cantilever.vtu") else None
g = frd_to_vtu(read_frd("case_d/d2_cantilever.frd"), "case_d/d2_cantilever.vtu")
s = g.extract_surface(nonlinear_subdivision=1)
p = pv.Plotter(window_size=(1000, 500))
p.add_mesh(s.warp_by_vector("DISP_0", factor=3), scalars="VONMISES_0", cmap="turbo",
           scalar_bar_args=dict(title="von Mises [MPa]"))
p.view_isometric(); p.screenshot("img/d2_cantilever.png"); p.close()
print("ok", [f for f in os.listdir("img")])
