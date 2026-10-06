"""Layering guard: lower layers must not import GUI / rendering stacks (spec §4 dependency rule)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "stressaero"

FORBIDDEN = {
    "core": {"PySide6", "pyvista", "pyvistaqt", "vtk", "vtkmodules", "pyqtgraph"},
    "geometry": {"PySide6", "pyvistaqt", "pyqtgraph"},
    "physics": {"PySide6", "pyvista", "pyvistaqt", "vtk", "vtkmodules", "pyqtgraph"},
    "io": {"PySide6", "pyvista", "pyvistaqt", "vtk", "vtkmodules", "pyqtgraph"},
    "viz": {"PySide6", "pyvistaqt", "pyqtgraph"},
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_layering():
    violations = []
    for layer, forbidden in FORBIDDEN.items():
        layer_dir = SRC / layer
        assert layer_dir.is_dir(), f"missing layer package {layer}"
        for py in layer_dir.rglob("*.py"):
            bad = _imported_roots(py) & forbidden
            if bad:
                violations.append(f"{py.relative_to(SRC)} imports {sorted(bad)}")
    assert violations == []
