"""Property inspector: shows the selected component's geometry, material and mass with units and provenance."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from stressaero.core.rocket import FINS, MASS_OBJECTS, RINGS, SYMMETRIC, Component, Kind
from stressaero.core.units import Dim, UnitSystem, format_quantity
from stressaero.physics.massmodel import PROVENANCE as MASS_PROVENANCE
from stressaero.ui.component_tree import kind_label

FROM_FILE = "From OpenRocket file"
RESOLVED = "Resolved (OpenRocket rules)"


class Inspector(QTableWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(["Property", "Value", "Source"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def show_component(self, c: Component | None, system: UnitSystem, mass: tuple[float, float] | None) -> None:
        rows: list[tuple[str, str, str]] = []
        if c is not None:

            def q(label: str, value: float, dim: Dim, source: str = FROM_FILE) -> None:
                rows.append((label, format_quantity(value, dim, system), source))

            rows.append(("Name", c.name, FROM_FILE))
            rows.append(("Type", kind_label(c.kind.value), FROM_FILE))
            if c.kind is not Kind.ROCKET:
                q("Position", c.x_abs, Dim.LENGTH, RESOLVED)
                q("Length", c.length, Dim.LENGTH, RESOLVED)
            if c.instance_count > 1:
                rows.append(("Instances", str(c.instance_count), FROM_FILE))
            r = c.resolved
            if c.kind in SYMMETRIC:
                q("Fore diameter", 2 * r["fore_radius"], Dim.LENGTH, RESOLVED)
                q("Aft diameter", 2 * r["aft_radius"], Dim.LENGTH, RESOLVED)
                t = c.values.get("thickness")
                rows.append(
                    (
                        "Wall",
                        "filled" if t == "filled" else format_quantity(c.num("thickness"), Dim.LENGTH, system),
                        FROM_FILE,
                    )
                )
                if c.kind is not Kind.BODYTUBE:
                    rows.append(("Shape", str(c.values.get("shape") or "conical"), FROM_FILE))
            elif c.kind in RINGS:
                q("Outer diameter", 2 * r["outer_radius"], Dim.LENGTH, RESOLVED)
                q("Inner diameter", 2 * r["inner_radius"], Dim.LENGTH, RESOLVED)
            elif c.kind in FINS:
                q("Root chord", c.length, Dim.LENGTH, RESOLVED)
                if c.kind is Kind.TRAPEZOIDFINSET:
                    q("Tip chord", c.num("tipchord"), Dim.LENGTH)
                    q("Sweep", c.num("sweeplength"), Dim.LENGTH)
                if c.kind is not Kind.FREEFORMFINSET:
                    q("Span", c.num("height"), Dim.LENGTH)
                q("Thickness", c.num("thickness"), Dim.LENGTH)
                q("Cant", c.values.get("cant") or 0.0, Dim.ANGLE)
                q("Body diameter at root", 2 * r.get("body_radius", 0.0), Dim.LENGTH, RESOLVED)
            elif c.kind is Kind.TUBEFINSET:
                q("Tube diameter", 2 * r["outer_radius"], Dim.LENGTH, RESOLVED)
            elif c.kind in MASS_OBJECTS:
                q("Packed diameter", 2 * r.get("packed_radius", 0.0), Dim.LENGTH, RESOLVED)
            if c.material is not None:
                dim = {"bulk": Dim.DENSITY, "surface": Dim.AREAL_DENSITY, "line": Dim.LINEAR_DENSITY}.get(
                    c.material.kind, Dim.DENSITY
                )
                rows.append(
                    ("Material", f"{c.material.name} ({format_quantity(c.material.density, dim, system)})", FROM_FILE)
                )
            if c.finish_roughness is not None:
                q("Surface roughness", c.finish_roughness, Dim.LENGTH)
            if c.override.mass is not None:
                q("Mass override", c.override.mass, Dim.MASS)
            if mass is not None and c.kind is not Kind.ROCKET:
                q("Mass", mass[0], Dim.MASS, MASS_PROVENANCE.label())
                q("CG (from nose)", c.x_abs + mass[1], Dim.LENGTH, MASS_PROVENANCE.label())
        self.setRowCount(len(rows))
        for i, (label, value, source) in enumerate(rows):
            for j, text in enumerate((label, value, source)):
                self.setItem(i, j, QTableWidgetItem(text))

    def row_values(self) -> dict[str, str]:
        return {self.item(i, 0).text(): self.item(i, 1).text() for i in range(self.rowCount())}

    def row_sources(self) -> dict[str, str]:
        return {self.item(i, 0).text(): self.item(i, 2).text() for i in range(self.rowCount())}
