"""Main Qt Widgets window."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from queue import SimpleQueue
from typing import Any, cast

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..engine import RunMode
from ..errors import RandomizerError
from ..gui_config import (
    GUI_CONFIG_SCHEMA_VERSION,
    PRESET_NAMES,
    GuiConfig,
    gui_config_from_dict,
    load_gui_config,
    preset_config,
    save_gui_config,
)
from ..reporting import format_readable_report, recover_build_report
from .editors import (
    AbilityConfigEditor,
    AdvancedJsonDialog,
    MoveConfigEditor,
    TrainerConfigEditor,
)
from .theme import icon
from .tutorial import TutorialWizard
from .workers import (
    BuildWorker,
    DiagnosticWorker,
    DownloadWorker,
    EngineRequest,
    EngineResult,
    EngineWorker,
    Worker,
)


def _describe(widget: QWidget, text: str, *, name: str = "") -> None:
    """Expose contextual help consistently to mouse and assistive technology users."""
    widget.setToolTip(text)
    widget.setStatusTip(text)
    widget.setAccessibleDescription(text)
    if name:
        widget.setAccessibleName(name)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SGRand — SoulGold v.1.1.4 Randomizer")
        self.setWindowIcon(icon("app"))
        self.resize(1120, 780)
        self.settings = QSettings()
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._ui_events: SimpleQueue[tuple[Callable[..., None], tuple[object, ...]]] = SimpleQueue()
        self._ui_event_timer = QTimer(self)
        self._ui_event_timer.setInterval(10)
        self._ui_event_timer.timeout.connect(self._drain_ui_events)
        self._ui_event_timer.start()
        self._operation_cancellable = False
        self._loading_config = False
        self._tutorial: TutorialWizard | None = None
        self._last_report: dict[str, Any] | None = None
        self._last_applied_seed: str | None = None
        self._last_applied_source: Path | None = None
        self._last_applied_config: str | None = None
        self._build_ui()
        self._load_preset("Balanced")
        self.source_edit.setText(cast(str, self.settings.value("source", "", str)))
        self.output_edit.setText(cast(str, self.settings.value("output", "", str)))

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        welcome = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(icon("app").pixmap(48, 48))
        brand_icon.setAccessibleName("Icono de SGRand")
        title_column = QVBoxLayout()
        title_column.setSpacing(0)
        title = QLabel("SGRand")
        title.setObjectName("heroTitle")
        subtitle = QLabel("Tu aventura, tus reglas — configura, revisa y crea tu partida.")
        subtitle.setObjectName("heroSubtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        tutorial_button = QPushButton("Abrir tutorial")
        tutorial_button.setIcon(icon("tutorial"))
        _describe(
            tutorial_button,
            "Abre una guía paso a paso para preparar el checkout, elegir ajustes, probarlos "
            "y compilar.",
        )
        tutorial_button.clicked.connect(self._show_tutorial)
        welcome.addWidget(brand_icon)
        welcome.addLayout(title_column, 1)
        welcome.addWidget(tutorial_button)
        root.addLayout(welcome)
        root.addWidget(self._paths_group())
        root.addLayout(self._configuration_bar())

        self.tabs = QTabWidget()
        self.move_editor = MoveConfigEditor()
        self.ability_editor = AbilityConfigEditor()
        self.trainer_editor = TrainerConfigEditor()
        for editor in (self.move_editor, self.ability_editor, self.trainer_editor):
            editor.changed.connect(self._mark_custom)
        self.move_editor.advanced_requested.connect(lambda: self._edit_advanced("moves"))
        self.ability_editor.advanced_requested.connect(lambda: self._edit_advanced("abilities"))
        self.trainer_editor.advanced_requested.connect(lambda: self._edit_advanced("trainers"))
        self.preview_text = self._readonly_editor()
        self.report_text = self._readonly_editor()
        self.log_text = self._readonly_editor()
        tab_definitions = (
            (
                self.move_editor,
                "Movimientos",
                "Movimientos por nivel, compatibilidad con MT/tutores y sus datos básicos.",
            ),
            (
                self.ability_editor,
                "Habilidades",
                "Habilidades principales, innatas y protecciones especiales de las especies.",
            ),
            (
                self.trainer_editor,
                "Entrenadores",
                "Equipos, niveles, temas, movimientos y objetos de cada grupo de entrenadores.",
            ),
            (
                self.preview_text,
                "Vista previa",
                "Vista previa legible de los cambios calculados sin modificar el checkout.",
            ),
            (
                self.report_text,
                "Informe",
                "Reporte JSON detallado para diagnóstico, reproducción o soporte.",
            ),
            (
                self.log_text,
                "Actividad",
                "Mensajes de progreso, herramientas de compilación y errores.",
            ),
        )
        tab_icons = ("moves", "abilities", "trainers", "preview", "report", "logs")
        self.tabs.setIconSize(QSize(20, 20))
        for (widget, label, help_text), icon_name in zip(tab_definitions, tab_icons, strict=True):
            index = self.tabs.addTab(widget, icon(icon_name), label)
            self.tabs.setTabToolTip(index, help_text)
            _describe(widget, help_text)
        root.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        self.diagnose_button = QPushButton("Comprobar")
        self.preview_button = QPushButton("Ver cambios")
        self.apply_button = QPushButton("Randomizar")
        self.build_button = QPushButton("Compilar juego")
        self.cancel_button = QPushButton("Cancelar")
        self.diagnose_button.setIcon(icon("diagnose"))
        self.preview_button.setIcon(icon("preview"))
        self.apply_button.setIcon(icon("randomize"))
        self.build_button.setIcon(icon("build"))
        self.apply_button.setProperty("kind", "primary")
        self.build_button.setProperty("kind", "gold")
        self.cancel_button.setEnabled(False)
        _describe(
            self.diagnose_button,
            "Comprueba el checkout y las herramientas necesarias antes de randomizar o compilar.",
        )
        _describe(
            self.preview_button,
            "Calcula y muestra qué cambiaría con esta semilla sin modificar ningún archivo.",
        )
        _describe(
            self.apply_button,
            "Aplica la configuración de forma transaccional: ante un error, no deja cambios "
            "parciales.",
        )
        _describe(
            self.build_button,
            "Compila el checkout ya randomizado y guarda la salida con el perfil y la semilla.",
        )
        _describe(self.cancel_button, "Cancela una descarga o compilación que esté en curso.")
        self.diagnose_button.clicked.connect(self._diagnose)
        self.preview_button.clicked.connect(lambda: self._run_engine(RunMode.PREVIEW))
        self.apply_button.clicked.connect(lambda: self._run_engine(RunMode.APPLY))
        self.build_button.clicked.connect(self._build)
        self.cancel_button.clicked.connect(self._cancel_operation)
        for button in (
            self.diagnose_button,
            self.preview_button,
            self.apply_button,
            self.build_button,
            self.cancel_button,
        ):
            actions.addWidget(button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        _describe(self.progress, "Muestra el avance de la operación en curso.")
        actions.addWidget(self.progress, 1)
        root.addLayout(actions)
        self.setCentralWidget(central)
        help_menu = self.menuBar().addMenu("Ayuda")
        tutorial_action = QAction("Tutorial de uso…", self)
        tutorial_action.setIcon(icon("tutorial"))
        tutorial_action.setShortcut("F1")
        tutorial_action.setToolTip("Abrir la guía de uso paso a paso")
        tutorial_action.setStatusTip("Abrir la guía de uso paso a paso")
        tutorial_action.triggered.connect(self._show_tutorial)
        help_menu.addAction(tutorial_action)
        self.statusBar().showMessage("Listo")

    def _paths_group(self) -> QGroupBox:
        group = QGroupBox("Proyecto y resultados")
        layout = QGridLayout(group)
        self.source_edit = QLineEdit()
        self.output_edit = QLineEdit()
        browse_source = QPushButton("Buscar…")
        download = QPushButton("Descargar proyecto…")
        browse_output = QPushButton("Buscar…")
        browse_source.setIcon(icon("folder"))
        browse_output.setIcon(icon("folder"))
        download.setIcon(icon("download"))
        source_help = (
            "Carpeta del checkout compatible de Pokémon SoulGold v.1.1.4. Debe contener el "
            "código fuente preparado por el proyecto; no selecciones una ROM."
        )
        output_help = (
            "Carpeta externa donde se guardarán el checkout randomizado, el reporte y la "
            "compilación. No debe ser la misma carpeta que el checkout de origen."
        )
        _describe(self.source_edit, source_help, name="Checkout de SoulGold")
        _describe(self.output_edit, output_help, name="Carpeta de salida")
        _describe(browse_source, "Busca en tu equipo un checkout SoulGold v.1.1.4 ya existente.")
        _describe(
            download,
            "Descarga el checkout público compatible en una carpeta elegida por ti; no "
            "descarga ninguna ROM.",
        )
        _describe(browse_output, "Elige la carpeta donde SGRand guardará sus resultados.")
        browse_source.clicked.connect(self._select_source)
        browse_output.clicked.connect(self._select_output)
        download.clicked.connect(self._download)
        source_label = QLabel("Proyecto SoulGold:")
        source_label.setBuddy(self.source_edit)
        _describe(source_label, source_help)
        layout.addWidget(source_label, 0, 0)
        layout.addWidget(self.source_edit, 0, 1)
        layout.addWidget(browse_source, 0, 2)
        layout.addWidget(download, 0, 3)
        output_label = QLabel("Guardar en:")
        output_label.setBuddy(self.output_edit)
        _describe(output_label, output_help)
        layout.addWidget(output_label, 1, 0)
        layout.addWidget(self.output_edit, 1, 1)
        layout.addWidget(browse_output, 1, 2)
        return group

    def _configuration_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESET_NAMES)
        self.preset_combo.currentTextChanged.connect(self._preset_selected)
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("Texto o número")
        random_seed = QPushButton("Aleatoria")
        random_seed.setIcon(icon("dice"))
        random_seed.clicked.connect(lambda: self.seed_edit.setText(secrets.token_hex(8)))
        self.spoiler_checkbox = QCheckBox("Sin spoilers")
        preset_help = (
            "Carga un punto de partida completo: Vanilla+ cambia poco, Balanced busca variedad "
            "jugable, Chaos prioriza sorpresas y Custom indica que editaste alguna regla. Cambiar "
            "de preset reemplaza los ajustes actuales."
        )
        seed_help = (
            "Texto o número que hace reproducible la partida. La misma semilla y configuración "
            "generan los mismos resultados; cambia la semilla para obtener otra partida."
        )
        _describe(self.preset_combo, preset_help, name="Preset")
        _describe(self.seed_edit, seed_help, name="Semilla")
        _describe(random_seed, "Genera una semilla nueva y difícil de repetir por accidente.")
        _describe(
            self.spoiler_checkbox,
            "Oculta especies, movimientos y otros resultados concretos en la vista previa, el "
            "manifiesto y el reporte. No cambia la partida generada.",
        )
        self.spoiler_checkbox.toggled.connect(self._mark_custom)
        import_button = QPushButton("Importar JSON…")
        export_button = QPushButton("Exportar JSON…")
        import_button.clicked.connect(self._import_config)
        export_button.clicked.connect(self._export_config)
        _describe(import_button, "Carga un archivo JSON de configuración versionado y lo valida.")
        _describe(export_button, "Guarda todos los ajustes actuales en un JSON reutilizable.")
        preset_label = QLabel("Estilo:")
        preset_label.setBuddy(self.preset_combo)
        _describe(preset_label, preset_help)
        layout.addWidget(preset_label)
        layout.addWidget(self.preset_combo)
        seed_label = QLabel("Semilla:")
        seed_label.setBuddy(self.seed_edit)
        _describe(seed_label, seed_help)
        layout.addWidget(seed_label)
        layout.addWidget(self.seed_edit, 1)
        layout.addWidget(random_seed)
        layout.addWidget(self.spoiler_checkbox)
        layout.addWidget(import_button)
        layout.addWidget(export_button)
        return layout

    @staticmethod
    def _json_editor() -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        return editor

    @classmethod
    def _readonly_editor(cls) -> QPlainTextEdit:
        editor = cls._json_editor()
        editor.setReadOnly(True)
        return editor

    def _select_source(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Seleccionar proyecto SoulGold v.1.1.4", self.source_edit.text()
        )
        if selected:
            self.source_edit.setText(selected)

    def _select_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de salida", self.output_edit.text()
        )
        if selected:
            self.output_edit.setText(selected)

    def _download(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, "Carpeta donde descargar SoulGold")
        if not parent:
            return
        name, accepted = QInputDialog.getText(
            self, "Nombre de carpeta", "Carpeta:", text="soulgold-v1.1.4"
        )
        if not accepted or not name.strip():
            return
        destination = Path(parent) / name.strip()
        worker = DownloadWorker(destination)
        worker.completed.connect(
            lambda source: self._enqueue_ui(self._download_completed, source),
            Qt.ConnectionType.DirectConnection,
        )
        self._start_worker(worker, "Descargando proyecto…", cancellable=True)

    @Slot(str)
    def _download_completed(self, source: str) -> None:
        self.source_edit.setText(source)
        self.statusBar().showMessage("Checkout v.1.1.4 descargado y validado")

    def _preset_selected(self, name: str) -> None:
        if self._loading_config or name == "Custom":
            return
        self._load_preset(name)

    def _load_preset(self, name: str) -> None:
        config = preset_config(name, spoiler_free=self.spoiler_checkbox.isChecked())
        self._set_config(config)

    def _set_config(self, config: GuiConfig) -> None:
        abilities = deepcopy(config.abilities)
        trainers = deepcopy(config.trainers)
        abilities["default_profile"] = config.ability_profile
        trainers["default_profile"] = config.trainer_profile
        self._loading_config = True
        try:
            self.preset_combo.setCurrentText(config.preset)
            self.spoiler_checkbox.setChecked(config.spoiler_free)
            self.move_editor.set_document(config.moves)
            self.ability_editor.set_document(abilities, config.ability_profile)
            self.trainer_editor.set_document(trainers, config.trainer_profile)
        finally:
            self._loading_config = False

    def _mark_custom(self) -> None:
        if not self._loading_config:
            self._loading_config = True
            self.preset_combo.setCurrentText("Custom")
            self._loading_config = False

    def _config(self) -> GuiConfig:
        document = {
            "schema_version": GUI_CONFIG_SCHEMA_VERSION,
            "preset": self.preset_combo.currentText(),
            "spoiler_free": self.spoiler_checkbox.isChecked(),
            "ability_profile": self.ability_editor.profile_name,
            "trainer_profile": self.trainer_editor.profile_name,
            "moves": self.move_editor.document(),
            "abilities": self.ability_editor.document(),
            "trainers": self.trainer_editor.document(),
        }
        return gui_config_from_dict(document)

    def _edit_advanced(self, section: str) -> None:
        try:
            current = self._config()
        except RandomizerError as exc:
            self._show_error(str(exc))
            return
        documents = {
            "moves": current.moves,
            "abilities": current.abilities,
            "trainers": current.trainers,
        }
        labels = {
            "moves": "Movimientos",
            "abilities": "Habilidades e innatas",
            "trainers": "Entrenadores",
        }

        def validate(candidate: dict[str, Any]) -> None:
            aggregate = current.as_dict()
            aggregate[section] = candidate
            if section == "abilities":
                aggregate["ability_profile"] = candidate.get("default_profile", "")
            elif section == "trainers":
                aggregate["trainer_profile"] = candidate.get("default_profile", "")
            gui_config_from_dict(aggregate)

        dialog = AdvancedJsonDialog(self, labels[section], documents[section], validate)
        if dialog.exec() != AdvancedJsonDialog.DialogCode.Accepted:
            return
        candidate = dialog.result_document
        if candidate is None:  # pragma: no cover - guarded by dialog acceptance
            return
        if section == "moves":
            self.move_editor.set_document(candidate)
        elif section == "abilities":
            self.ability_editor.set_document(candidate, str(candidate["default_profile"]))
        else:
            self.trainer_editor.set_document(candidate, str(candidate["default_profile"]))
        self._mark_custom()

    def _show_tutorial(self) -> None:
        if self._tutorial is None:
            self._tutorial = TutorialWizard(self)
            self._tutorial.finished.connect(self._tutorial_finished)
        self._tutorial.show()
        self._tutorial.raise_()
        self._tutorial.activateWindow()

    def _tutorial_finished(self) -> None:
        self._tutorial = None

    def _import_config(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Importar configuración", filter="JSON (*.json)"
        )
        if not selected:
            return
        try:
            self._set_config(load_gui_config(Path(selected)))
        except RandomizerError as exc:
            self._show_error(str(exc))

    def _export_config(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self, "Exportar configuración", "sgrand-config.json", "JSON (*.json)"
        )
        if not selected:
            return
        try:
            save_gui_config(self._config(), Path(selected))
        except RandomizerError as exc:
            self._show_error(str(exc))

    def _paths_and_seed(self, *, require_output: bool = True) -> tuple[Path, Path, str]:
        source_text = self.source_edit.text().strip()
        output_text = self.output_edit.text().strip()
        seed = self.seed_edit.text().strip()
        if not source_text or not seed or (require_output and not output_text):
            required = "proyecto, salida y semilla" if require_output else "proyecto y semilla"
            raise RandomizerError(f"Selecciona {required}.")
        source = Path(source_text)
        output = Path(output_text) if output_text else source.parent
        self.settings.setValue("source", str(source))
        if output_text:
            self.settings.setValue("output", str(output))
        return source, output, seed

    def _run_engine(self, mode: RunMode) -> None:
        try:
            source, output, seed = self._paths_and_seed(require_output=mode is RunMode.APPLY)
            config = self._config()
        except RandomizerError as exc:
            self._show_error(str(exc))
            return
        worker = EngineWorker(EngineRequest(source, output, seed, config, mode))
        worker.completed.connect(
            lambda result: self._enqueue_ui(self._engine_completed, result),
            Qt.ConnectionType.DirectConnection,
        )
        label = "Calculando preview…" if mode is RunMode.PREVIEW else "Randomizando…"
        self._start_worker(worker, label, cancellable=False)

    @Slot(object)
    def _engine_completed(self, result_object: object) -> None:
        if not isinstance(result_object, EngineResult):
            self._show_error("El motor devolvió un reporte inválido.")
            return
        request = result_object.request
        report = result_object.report
        self._last_report = report
        self.preview_text.setPlainText(format_readable_report(report))
        self.report_text.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        self.tabs.setCurrentWidget(self.preview_text)
        if request.mode is RunMode.APPLY:
            self._last_applied_seed = request.seed
            self._last_applied_source = request.source.resolve()
            self._last_applied_config = json.dumps(
                request.config.as_dict(), sort_keys=True, separators=(",", ":")
            )
            self.statusBar().showMessage("Randomización transaccional completada")
        else:
            self.statusBar().showMessage("Preview completado; no se escribió ningún archivo")

    def _build(self) -> None:
        try:
            source, output, seed = self._paths_and_seed()
            config = self._config()
        except RandomizerError as exc:
            self._show_error(str(exc))
            return
        fingerprint = json.dumps(config.as_dict(), sort_keys=True, separators=(",", ":"))
        same_session = (
            self._last_report is not None
            and self._last_applied_seed == seed
            and self._last_applied_source == source.resolve()
            and self._last_applied_config == fingerprint
        )
        if same_session:
            report = cast(dict[str, Any], self._last_report)
            profile = config.preset
        else:
            try:
                report, profile, recovered_from = recover_build_report(
                    source, output, seed, config.preset
                )
            except RandomizerError as exc:
                self._show_error(str(exc))
                return
            self._last_report = report
            self.preview_text.setPlainText(format_readable_report(report))
            self.report_text.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
            self.log_text.appendPlainText(f"Sesión de randomización recuperada: {recovered_from}")
        worker = BuildWorker(source, output, profile, seed, report)
        worker.completed.connect(
            lambda target: self._enqueue_ui(self._build_completed, target),
            Qt.ConnectionType.DirectConnection,
        )
        self._start_worker(worker, "Compilando SoulGold…", cancellable=True)

    @Slot(str)
    def _build_completed(self, target: str) -> None:
        self.statusBar().showMessage(f"Compilación completada: {target}")
        QMessageBox.information(self, "Compilación completada", f"Salida:\n{target}")

    def _diagnose(self) -> None:
        source = Path(self.source_edit.text()) if self.source_edit.text().strip() else None
        worker = DiagnosticWorker(source)
        worker.completed.connect(
            lambda result: self._enqueue_ui(self._diagnostics_completed, result),
            Qt.ConnectionType.DirectConnection,
        )
        self._start_worker(worker, "Diagnosticando dependencias…", cancellable=False)

    @Slot(str)
    def _diagnostics_completed(self, result: str) -> None:
        self.log_text.appendPlainText(result)
        self.tabs.setCurrentWidget(self.log_text)
        self.statusBar().showMessage("Diagnóstico completado")

    def _start_worker(self, worker: Worker, status: str, *, cancellable: bool) -> None:
        if self._thread is not None:
            self._show_error("Ya hay una operación en curso.")
            return
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)  # type: ignore[attr-defined]
        worker.log.connect(
            lambda line: self._enqueue_ui(self._append_log, line),
            Qt.ConnectionType.DirectConnection,
        )
        worker.progress.connect(
            lambda value: self._enqueue_ui(self.progress.setValue, value),
            Qt.ConnectionType.DirectConnection,
        )
        worker.failed.connect(
            lambda message: self._enqueue_ui(self._operation_failed, message),
            Qt.ConnectionType.DirectConnection,
        )
        worker.cancelled.connect(
            lambda message: self._enqueue_ui(self._operation_cancelled, message),
            Qt.ConnectionType.DirectConnection,
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(
            lambda: self._enqueue_ui(self._worker_finished),
            Qt.ConnectionType.DirectConnection,
        )
        self._thread = thread
        self._worker = worker
        self._operation_cancellable = cancellable
        self._set_busy(True, cancellable)
        self.progress.setValue(0)
        self.statusBar().showMessage(status)
        thread.start()

    def _enqueue_ui(self, callback: Callable[..., None], *args: object) -> None:
        """Transfer a worker event without invoking any Qt API from that worker."""
        self._ui_events.put((callback, args))

    @Slot()
    def _drain_ui_events(self) -> None:
        """Run a bounded batch of worker callbacks from the GUI event loop."""
        for _ in range(200):
            if self._ui_events.empty():
                return
            callback, args = self._ui_events.get()
            callback(*args)

    @Slot(str)
    def _append_log(self, line: str) -> None:
        self.log_text.appendPlainText(line)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self.log_text.appendPlainText(f"ERROR: {message}")
        self.tabs.setCurrentWidget(self.log_text)
        self.statusBar().showMessage("La operación falló")
        self._show_error(message)

    @Slot(str)
    def _operation_cancelled(self, message: str) -> None:
        self.log_text.appendPlainText(message)
        self.tabs.setCurrentWidget(self.log_text)
        self.statusBar().showMessage("Operación cancelada")

    @Slot()
    def _worker_finished(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        self._operation_cancellable = False
        self._set_busy(False, False)
        if thread is not None:
            thread.deleteLater()

    def _set_busy(self, busy: bool, cancellable: bool) -> None:
        for button in (
            self.diagnose_button,
            self.preview_button,
            self.apply_button,
            self.build_button,
        ):
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and cancellable)

    def _cancel_operation(self) -> None:
        if self._worker is not None and self._operation_cancellable:
            # Worker.cancel only sets a threading.Event and is safe to call directly;
            # a queued Qt slot cannot run while the worker thread is inside Popen.
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Cancelando proceso…")

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "SGRand", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None:
            if not self._operation_cancellable:
                QMessageBox.information(
                    self,
                    "Operación en curso",
                    "Espera a que finalice la planificación transaccional antes de salir.",
                )
                event.ignore()
                return
            answer = QMessageBox.question(
                self,
                "Operación en curso",
                "¿Cancelar la operación y salir?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._cancel_operation()
            self._thread.quit()
            if not self._thread.wait(5000):
                event.ignore()
                return
        event.accept()
