# PyInstaller spec for Stress & Aero (onedir build).  Build with:  pyinstaller packaging/stressaero.spec
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is provided by PyInstaller
ICON = str(ROOT / "packaging" / "assets" / "stressaero.ico")

datas = collect_data_files("stressaero") + collect_data_files("pyvista")
hiddenimports = (
    collect_submodules("stressaero")
    + collect_submodules("pyvistaqt")
    + ["vtkmodules.util.numpy_support", "vtkmodules.qt.QVTKRenderWindowInteractor"]
)

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib.tests", "numpy.tests", "scipy.tests", "IPython", "jupyter", "trame"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StressAero",
    console=False,
    icon=ICON if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="StressAero")  # noqa: F821
