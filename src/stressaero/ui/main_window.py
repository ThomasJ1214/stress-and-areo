"""Main application window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QWidget,
)

import stressaero
from stressaero.core.configuration import FlightConfiguration
from stressaero.core.provenance import Severity
from stressaero.core.units import SYSTEMS, Dim, UnitSystem, format_quantity
from stressaero.io.ork import OrkImport, load_ork
from stressaero.io.project import Project, load_project, save_project
from stressaero.physics.massmodel import component_mass_cg, reference_length, rocket_length, structure_mass
from stressaero.ui.component_tree import ComponentTree
from stressaero.ui.inspector import Inspector
from stressaero.ui.viewport import Viewport
from stressaero.viz.rocket_mesh import rocket_meshes

APP_NAME = "Stress & Aero"
FILE_FILTER = "Rocket files (*.ork *.saproj);;OpenRocket (*.ork);;Stress & Aero project (*.saproj);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)
        self.ork: OrkImport | None = None
        self.project = Project()
        self.project_path: Path | None = None
        self.unit_system_name = "metric"
        self._selected: str | None = None

        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)
        self.tree = ComponentTree(self)
        self.inspector = Inspector(self)
        self.issues = QListWidget(self)
        self._dock("Components", self.tree, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock("Properties", self.inspector, Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock("Import messages", self.issues, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.resizeDocks([self.findChild(QDockWidget, "Import messages")], [120], Qt.Orientation.Vertical)
        self.resizeDocks(
            [self.findChild(QDockWidget, "Components"), self.findChild(QDockWidget, "Properties")],
            [300, 360],
            Qt.Orientation.Horizontal,
        )

        self.config_combo = QComboBox(self)
        self.config_combo.setMinimumWidth(260)
        self.config_combo.currentIndexChanged.connect(self._on_config_changed)
        self.summary = QLabel(self)
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("main-toolbar")
        toolbar.addWidget(QLabel(" Flight configuration: "))
        toolbar.addWidget(self.config_combo)
        toolbar.addSeparator()
        toolbar.addWidget(self.summary)
        self.addToolBar(toolbar)

        self.tree.componentSelected.connect(self.select_component)
        self.viewport.componentPicked.connect(self._on_picked)
        self._build_menus()
        self.statusBar().showMessage("Open an OpenRocket .ork file or a Stress & Aero project to begin.")

    # ------------------------------------------------------------------ construction helpers
    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> None:
        dock = QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "&Open…", self._open_dialog, QKeySequence.StandardKey.Open)
        self.recent_menu = file_menu.addMenu("Open &recent")
        self._refresh_recent()
        self._action(file_menu, "&Save project", self._save, QKeySequence.StandardKey.Save)
        self._action(file_menu, "Save project &as…", self._save_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        self._action(file_menu, "E&xit", self.close, QKeySequence.StandardKey.Quit)

        view = self.menuBar().addMenu("&View")
        units = view.addMenu("&Units")
        group = QActionGroup(self)
        self.unit_actions: dict[str, QAction] = {}
        for key, label in (("metric", "Metric (SI)"), ("us", "US customary")):
            act = QAction(label, self, checkable=True)
            act.triggered.connect(lambda _checked=False, k=key: self.set_unit_system(k))
            group.addAction(act)
            units.addAction(act)
            self.unit_actions[key] = act
        self.unit_actions["metric"].setChecked(True)
        self._action(
            view,
            "&Reset camera",
            lambda: (self.viewport.plotter.view_isometric(), self.viewport.plotter.reset_camera()),
        )

        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "&About", self._about)

    def _action(self, menu, text, slot, shortcut=None) -> QAction:
        act = QAction(text, self)
        if shortcut is not None:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    # ------------------------------------------------------------------ public API
    @property
    def unit_system(self) -> UnitSystem:
        return SYSTEMS[self.unit_system_name]

    def open_path(self, path: Path | str) -> None:
        path = Path(path)
        try:
            if path.suffix.lower() == ".saproj":
                project = load_project(path)
                ork = project.load_rocket()
                self.project, self.project_path = project, path
            else:
                ork = load_ork(path)
                self.project = Project(ork_name=path.name, ork_bytes=path.read_bytes())
                self.project_path = None
        except Exception as e:  # noqa: BLE001 - any load failure is reported to the user
            QMessageBox.critical(self, APP_NAME, f"Could not open {path.name}:\n\n{e}")
            return
        self.ork = ork
        self._remember_recent(path)
        self.tree.populate(ork.rocket)
        self._populate_issues()
        self._populate_configs(self.project.selected_config_id)
        self.set_unit_system(self.project.unit_system if path.suffix.lower() == ".saproj" else self.unit_system_name)
        self.setWindowTitle(f"{ork.rocket.root.name} — {APP_NAME}")
        self.statusBar().showMessage(
            f"Loaded {path.name} (OpenRocket format {ork.format_version}, {len(ork.configurations)} configurations, "
            f"{len(ork.issues)} import messages)"
        )

    def save_project(self, path: Path | str) -> None:
        path = Path(path)
        self.project.selected_config_id = self.current_config_id()
        self.project.unit_system = self.unit_system_name
        try:
            save_project(self.project, path)
        except OSError as e:
            QMessageBox.critical(self, APP_NAME, f"Could not save {path.name}:\n\n{e}")
            return
        self.project_path = path
        self.statusBar().showMessage(f"Saved {path}")

    def set_unit_system(self, name: str) -> None:
        if name not in SYSTEMS:
            raise ValueError(name)
        self.unit_system_name = name
        self.unit_actions[name].setChecked(True)
        self.project.unit_system = name
        self._refresh_summary()
        self._refresh_inspector()

    def current_config(self) -> FlightConfiguration | None:
        if self.ork is None or not self.ork.configurations:
            return None
        idx = self.config_combo.currentIndex()
        return self.ork.configurations[idx] if 0 <= idx < len(self.ork.configurations) else None

    def current_config_id(self) -> str | None:
        cfg = self.current_config()
        return cfg.id if cfg is not None else None

    def set_configuration(self, config_id: str) -> None:
        if self.ork is None:
            return
        for i, c in enumerate(self.ork.configurations):
            if c.id == config_id:
                self.config_combo.setCurrentIndex(i)
                return
        raise KeyError(config_id)

    def select_component(self, component_id: str | None) -> None:
        self._selected = component_id
        self.viewport.highlight(component_id)
        self.tree.select_silently(component_id)
        self._refresh_inspector()

    # ------------------------------------------------------------------ internals
    def _on_picked(self, component_id: str) -> None:
        self.select_component(component_id)

    def _populate_configs(self, preferred: str | None) -> None:
        self.config_combo.blockSignals(True)
        self.config_combo.clear()
        index = 0
        for i, c in enumerate(self.ork.configurations):
            self.config_combo.addItem(c.display_name(), c.id)
            if (preferred is not None and c.id == preferred) or (preferred is None and c.is_default):
                index = i
        self.config_combo.setCurrentIndex(index)
        self.config_combo.blockSignals(False)
        self._on_config_changed()

    def _on_config_changed(self, *_args) -> None:
        if self.ork is None:
            return
        cfg = self.current_config()
        self.project.selected_config_id = cfg.id if cfg else None
        mass = structure_mass(self.ork.rocket, cfg)
        self.viewport.show_rocket(
            rocket_meshes(self.ork.rocket, cfg), mass.cg_x, body_radius=reference_length(self.ork.rocket, cfg) / 2
        )
        if self._selected is not None:
            self.viewport.highlight(self._selected)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        if self.ork is None:
            self.summary.setText("")
            return
        cfg = self.current_config()
        s = self.unit_system
        mass = structure_mass(self.ork.rocket, cfg)
        text = (
            f"  Structure mass {format_quantity(mass.mass, Dim.MASS, s)} (no motors) · "
            f"CG {format_quantity(mass.cg_x, Dim.LENGTH, s)} from nose · "
            f"length {format_quantity(rocket_length(self.ork.rocket, cfg), Dim.LENGTH, s)} · "
            f"reference diameter {format_quantity(reference_length(self.ork.rocket, cfg), Dim.LENGTH, s)}"
        )
        self.summary.setText(text)
        self.summary.setToolTip(f"Method: {mass.provenance.label()} ({mass.provenance.method_id})")

    def _refresh_inspector(self) -> None:
        c = self.ork.rocket.by_id.get(self._selected) if (self.ork and self._selected) else None
        self.inspector.show_component(c, self.unit_system, component_mass_cg(c) if c is not None else None)

    def _populate_issues(self) -> None:
        self.issues.clear()
        icons = {Severity.INFO: "ℹ", Severity.WARNING: "⚠", Severity.ERROR: "✖"}
        for issue in self.ork.issues:
            self.issues.addItem(f"{icons[issue.severity]} {issue.message}")

    # ------------------------------------------------------------------ dialogs
    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open rocket", "", FILE_FILTER)
        if path:
            self.open_path(path)

    def _save(self) -> None:
        if self.project_path is None:
            self._save_as()
        else:
            self.save_project(self.project_path)

    def _save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "", "Stress & Aero project (*.saproj)")
        if path:
            if not path.lower().endswith(".saproj"):
                path += ".saproj"
            self.save_project(path)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {stressaero.__version__}<br>Rocket aerodynamic, flight and structural analysis.<br>"
            "Third-party licences: see THIRD_PARTY_NOTICES.md.",
        )

    # ------------------------------------------------------------------ recent files
    def _remember_recent(self, path: Path) -> None:
        settings = QSettings("StressAero", "StressAero")
        recent = [p for p in (settings.value("recent", []) or []) if p != str(path)]
        settings.setValue("recent", [str(path)] + recent[:7])
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        self.recent_menu.clear()
        settings = QSettings("StressAero", "StressAero")
        for p in settings.value("recent", []) or []:
            act = self.recent_menu.addAction(p)
            act.triggered.connect(lambda _checked=False, path=p: self.open_path(path))
