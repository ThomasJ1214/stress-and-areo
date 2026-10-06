"""Component tree dock: mirrors the OpenRocket component hierarchy."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from stressaero.core.rocket import Component, Rocket

_KIND_LABELS = {
    "rocket": "Rocket",
    "stage": "Stage",
    "parallelstage": "Booster stage",
    "boosterset": "Booster stage",
    "podset": "Pod set",
    "nosecone": "Nose cone",
    "bodytube": "Body tube",
    "transition": "Transition",
    "trapezoidfinset": "Trapezoidal fins",
    "ellipticalfinset": "Elliptical fins",
    "freeformfinset": "Freeform fins",
    "tubefinset": "Tube fins",
    "launchlug": "Launch lug",
    "railbutton": "Rail button",
    "innertube": "Inner tube",
    "tubecoupler": "Coupler",
    "engineblock": "Engine block",
    "centeringring": "Centering ring",
    "bulkhead": "Bulkhead",
    "masscomponent": "Mass component",
    "shockcord": "Shock cord",
    "parachute": "Parachute",
    "streamer": "Streamer",
}


def kind_label(kind: str) -> str:
    return _KIND_LABELS.get(kind, kind)


class ComponentTree(QTreeWidget):
    """Emits ``componentSelected(id)`` when the user selects a component."""

    componentSelected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Component", "Type"])
        self.setColumnWidth(0, 220)
        self._items: dict[str, QTreeWidgetItem] = {}
        self._updating = False
        self.itemSelectionChanged.connect(self._on_selection)

    def populate(self, rocket: Rocket | None) -> None:
        self._updating = True
        try:
            self.clear()
            self._items.clear()
            if rocket is not None:
                self._add(rocket.root, None)
                self.expandAll()
        finally:
            self._updating = False

    def _add(self, c: Component, parent_item: QTreeWidgetItem | None) -> None:
        item = QTreeWidgetItem([c.name, kind_label(c.kind.value)])
        item.setData(0, Qt.ItemDataRole.UserRole, c.id)
        if parent_item is None:
            self.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        self._items[c.id] = item
        for ch in c.children:
            self._add(ch, item)

    def component_count(self) -> int:
        return len(self._items)

    def select(self, component_id: str | None) -> None:
        """Select (and emit) a component programmatically; ``None`` clears the selection."""
        if component_id is None:
            self.clearSelection()
            return
        item = self._items.get(component_id)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item)

    def select_silently(self, component_id: str | None) -> None:
        self._updating = True
        try:
            self.select(component_id)
        finally:
            self._updating = False

    def selected_id(self) -> str | None:
        items = self.selectedItems()
        return items[0].data(0, Qt.ItemDataRole.UserRole) if items else None

    def _on_selection(self) -> None:
        if self._updating:
            return
        cid = self.selected_id()
        if cid is not None:
            self.componentSelected.emit(cid)
