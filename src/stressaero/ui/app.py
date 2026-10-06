"""Application entry point: ``stressaero`` / ``python -m stressaero`` / ``StressAero.exe``."""

from __future__ import annotations

import argparse
import os
import sys
from importlib import resources
from pathlib import Path

DEMO_ROCKET = "demo_rocket.ork"


def _demo_path() -> Path:
    return Path(str(resources.files("stressaero.data.samples").joinpath(DEMO_ROCKET)))


def selftest(out_path: str | None = None) -> int:
    """Headless smoke test used by CI on the frozen executable (no window is shown)."""
    import pyvista  # noqa: F401  - ensure the rendering stack imports in the frozen app

    from stressaero.io.ork import load_ork
    from stressaero.physics.massmodel import structure_mass
    from stressaero.viz.rocket_mesh import rocket_meshes

    imp = load_ork(_demo_path())
    cfg = next((c for c in imp.configurations if c.is_default), None)
    mass = structure_mass(imp.rocket, cfg)
    meshes = rocket_meshes(imp.rocket, cfg)
    n = sum(1 for _ in imp.rocket.root.walk())
    line = f"SELFTEST OK {n} components {len(meshes)} meshes {mass.mass * 1000:.1f} g"
    print(line)  # no-op in the windowed Windows build (no console)
    if out_path:
        Path(out_path).write_text(line + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stressaero", description="Stress & Aero rocket analysis")
    parser.add_argument("path", nargs="?", help=".ork or .saproj file to open")
    parser.add_argument("--selftest", action="store_true", help="run a headless smoke test and exit")
    parser.add_argument("--selftest-out", help="also write the self-test result to this file")
    parser.add_argument("--demo", action="store_true", help="open the bundled demo rocket")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.selftest_out)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from stressaero.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Stress & Aero")
    app.setOrganizationName("StressAero")
    window = MainWindow()
    window.show()
    if args.path:
        window.open_path(args.path)
    elif args.demo:
        window.open_path(_demo_path())
    autoquit = os.environ.get("STRESSAERO_AUTOQUIT_MS")
    if autoquit:
        shot = os.environ.get("STRESSAERO_SCREENSHOT")

        def _finish() -> None:
            if shot:
                window.grab().save(shot)
            app.quit()

        QTimer.singleShot(int(autoquit), _finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
