# Third-party notices

Runtime dependencies (installed from PyPI, bundled in the Windows build):

| Component | Licence |
|---|---|
| Python 3.12 | PSF |
| NumPy, SciPy | BSD-3-Clause |
| defusedxml | PSF |
| Qt 6 / PySide6 | LGPL-3.0 (dynamically linked) |
| VTK, PyVista, pyvistaqt | BSD-3-Clause / MIT |
| pyqtgraph | MIT |

Test-only / tooling material:

| Component | Licence | Use |
|---|---|---|
| OpenRocket example `.ork` files (`tests/data/openrocket/`) | GPL-3.0 | regression fixtures, not shipped |
| OpenRocket 24.12 jar (downloaded by `tools/oracle/run_oracle.py`, never committed) | GPL-3.0 | run as a separate process to regenerate reference values |

External solvers bundled in later milestones (SU2, CalculiX, gmsh) run as separate
executables and keep their own licences (LGPL-2.1 / GPL-2.0+).
