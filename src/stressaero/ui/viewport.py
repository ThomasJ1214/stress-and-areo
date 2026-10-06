"""Interactive 3-D viewport (pyvista/VTK inside Qt) with component picking, highlight and CG/CP markers."""

from __future__ import annotations

import numpy as np
import pyvista as pv
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkCellPicker

EXTERNAL_COLOR = "lightsteelblue"
INTERNAL_COLOR = "burlywood"
HIGHLIGHT_COLOR = "gold"
_CLICK_TOLERANCE_PX = 4


class Viewport(QWidget):
    """Emits ``componentPicked(id)`` when the user clicks a component."""

    componentPicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("white", top="lightsteelblue")
        self.plotter.add_axes()
        self.meshes: dict[str, pv.PolyData] = {}
        self._actors: dict[str, object] = {}
        self._actor_to_id: dict[int, str] = {}
        self._base_colors: dict[str, object] = {}
        self._markers: list[object] = []
        self.highlighted: str | None = None
        self._picker = vtkCellPicker()
        self._picker.SetTolerance(0.0005)
        self._press: tuple[int, int] | None = None
        iren = self.plotter.iren.interactor
        iren.AddObserver("LeftButtonPressEvent", self._on_press, 1.0)
        iren.AddObserver("LeftButtonReleaseEvent", self._on_release, 1.0)

    # ------------------------------------------------------------------ scene
    def show_rocket(
        self,
        meshes: dict[str, pv.PolyData],
        cg_x: float | None,
        cp_x: float | None = None,
        *,
        body_radius: float | None = None,
        reset_camera: bool = True,
    ) -> None:
        self.plotter.clear_actors()
        self.meshes = dict(meshes)
        self._actors.clear()
        self._actor_to_id.clear()
        self._base_colors.clear()
        self._markers.clear()
        for cid, mesh in meshes.items():
            internal = bool(mesh.field_data["internal"][0]) if "internal" in mesh.field_data else False
            color = (
                tuple(mesh.field_data["color"])
                if "color" in mesh.field_data
                else (INTERNAL_COLOR if internal else EXTERNAL_COLOR)
            )
            actor = self.plotter.add_mesh(
                mesh,
                color=color,
                opacity=0.35 if internal else 1.0,
                smooth_shading=True,
                pickable=True,
                name=f"comp-{cid}",
            )
            self._actors[cid] = actor
            self._actor_to_id[id(actor)] = cid
            self._base_colors[cid] = color
        radius = body_radius if body_radius else self._reference_radius()
        for x, label, color in ((cg_x, "CG", "black"), (cp_x, "CP", "red")):
            if x is None:
                continue
            sphere = pv.Sphere(radius=radius * 1.15, center=(x, 0, 0))
            self._markers.append(self.plotter.add_mesh(sphere, color=color, pickable=False, name=f"marker-{label}"))
            self._markers.append(
                self.plotter.add_point_labels(
                    [(x, 0, radius * 3.0)],
                    [label],
                    font_size=14,
                    point_size=1,
                    shape_opacity=0.6,
                    name=f"label-{label}",
                )
            )
        self.highlighted = None
        if reset_camera:
            self.plotter.view_isometric()
            self.plotter.reset_camera()
        self.plotter.render()

    def _reference_radius(self) -> float:
        if not self.meshes:
            return 0.01
        b = np.array([m.bounds for m in self.meshes.values()])
        return max(float(np.max(np.abs(b[:, 2:6]))), 1e-3)

    def highlight(self, component_id: str | None) -> None:
        if self.highlighted in self._actors:
            self._actors[self.highlighted].prop.color = self._base_colors[self.highlighted]
        self.highlighted = component_id if component_id in self._actors else None
        if self.highlighted is not None:
            self._actors[self.highlighted].prop.color = HIGHLIGHT_COLOR
        self.plotter.render()

    # ------------------------------------------------------------------ picking
    def world_to_display(self, point) -> tuple[float, float]:
        ren = self.plotter.renderer
        ren.SetWorldPoint(float(point[0]), float(point[1]), float(point[2]), 1.0)
        ren.WorldToDisplay()
        x, y, _ = ren.GetDisplayPoint()
        return x, y

    def pick_at(self, x: float, y: float) -> str | None:
        """Pick the component under display coordinates (VTK convention, origin bottom-left)."""
        if not self._picker.Pick(x, y, 0, self.plotter.renderer):
            return None
        actor = self._picker.GetActor()
        cid = self._actor_to_id.get(id(actor)) if actor is not None else None
        if cid is not None:
            self.componentPicked.emit(cid)
        return cid

    def _on_press(self, obj, _event) -> None:
        self._press = obj.GetEventPosition()

    def _on_release(self, obj, _event) -> None:
        if self._press is None:
            return
        x, y = obj.GetEventPosition()
        if abs(x - self._press[0]) <= _CLICK_TOLERANCE_PX and abs(y - self._press[1]) <= _CLICK_TOLERANCE_PX:
            self.pick_at(x, y)
        self._press = None

    def screenshot(self, path: str) -> None:
        self.plotter.screenshot(path)

    def close(self) -> bool:
        self.plotter.close()
        return super().close()
