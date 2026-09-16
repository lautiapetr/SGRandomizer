"""Main Qt Widgets window."""

from __future__ import annotations

import json
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QSettings, QThread
from PySide6.QtGui import QCloseEvent, QFontDatabase
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
from ..reporting import format_readable_report
from .workers import (
    BuildWorker,
    DiagnosticWorker,
    DownloadWorker,
    EngineRequest,
    EngineWorker,
    Worker,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SGRand — SoulGold v.1.1.4 Randomizer")
        self.resize(1120, 780)
        self.settings = QSettings()
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._operation_cancellable = False
        self._loading_config = False
        self._ability_profile = "Balanced"
        self._trainer_profile = "Balanced"
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
        root.addWidget(self._paths_group())
        root.addLayout(self._configuration_bar())

        self.tabs = QTabWidget()
        self.move_editor = self._json_editor()
        self.ability_editor = self._json_editor()
        self.trainer_editor = self._json_editor()
        for editor in (self.move_editor, self.ability_editor, self.trainer_editor):
            editor.textChanged.connect(self._mark_custom)
        self.preview_text = self._readonly_editor()
        self.report_text = self._readonly_editor()
        self.log_text = self._readonly_editor()
        self.tabs.addTab(self.move_editor, "Movimientos")
        self.tabs.addTab(self.ability_editor, "Habilidades e innatas")
        self.tabs.addTab(self.trainer_editor, "Entrenadores")
        self.tabs.addTab(self.preview_text, "Preview")
        self.tabs.addTab(self.report_text, "Reporte técnico")
        self.tabs.addTab(self.log_text, "Logs")
        root.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        self.diagnose_button = QPushButton("Diagnosticar")
        self.preview_button = QPushButton("Preview")
        self.apply_button = QPushButton("Randomizar")
        self.build_button = QPushButton("Compilar")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
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
        actions.addWidget(self.progress, 1)
        root.addLayout(actions)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Listo")

    def _paths_group(self) -> QGroupBox:
        group = QGroupBox("Checkout y salida")
        layout = QGridLayout(group)
        self.source_edit = QLineEdit()
        self.output_edit = QLineEdit()
        browse_source = QPushButton("Seleccionar…")
        download = QPushButton("Descargar v.1.1.4…")
        browse_output = QPushButton("Salida…")
        browse_source.clicked.connect(self._select_source)
        browse_output.clicked.connect(self._select_output)
        download.clicked.connect(self._download)
        layout.addWidget(QLabel("SoulGold:"), 0, 0)
        layout.addWidget(self.source_edit, 0, 1)
        layout.addWidget(browse_source, 0, 2)
        layout.addWidget(download, 0, 3)
        layout.addWidget(QLabel("Salida:"), 1, 0)
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
        random_seed.clicked.connect(lambda: self.seed_edit.setText(secrets.token_hex(8)))
        self.spoiler_checkbox = QCheckBox("Sin spoilers")
        import_button = QPushButton("Importar JSON…")
        export_button = QPushButton("Exportar JSON…")
        import_button.clicked.connect(self._import_config)
        export_button.clicked.connect(self._export_config)
        layout.addWidget(QLabel("Preset:"))
        layout.addWidget(self.preset_combo)
        layout.addWidget(QLabel("Semilla:"))
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
            self, "Seleccionar checkout SoulGold v.1.1.4", self.source_edit.text()
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
        worker.completed.connect(self._download_completed)
        self._start_worker(worker, "Descargando checkout…", cancellable=True)

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
            self._ability_profile = config.ability_profile
            self._trainer_profile = config.trainer_profile
            self.move_editor.setPlainText(json.dumps(config.moves, ensure_ascii=False, indent=2))
            self.ability_editor.setPlainText(json.dumps(abilities, ensure_ascii=False, indent=2))
            self.trainer_editor.setPlainText(json.dumps(trainers, ensure_ascii=False, indent=2))
        finally:
            self._loading_config = False

    def _mark_custom(self) -> None:
        if not self._loading_config:
            self._loading_config = True
            self.preset_combo.setCurrentText("Custom")
            self._loading_config = False

    def _config(self) -> GuiConfig:
        try:
            abilities = json.loads(self.ability_editor.toPlainText())
            trainers = json.loads(self.trainer_editor.toPlainText())
            document = {
                "schema_version": GUI_CONFIG_SCHEMA_VERSION,
                "preset": self.preset_combo.currentText(),
                "spoiler_free": self.spoiler_checkbox.isChecked(),
                "ability_profile": abilities.get("default_profile", self._ability_profile),
                "trainer_profile": trainers.get("default_profile", self._trainer_profile),
                "moves": json.loads(self.move_editor.toPlainText()),
                "abilities": abilities,
                "trainers": trainers,
            }
        except json.JSONDecodeError as exc:
            raise RandomizerError(f"JSON inválido: {exc}") from exc
        return gui_config_from_dict(document)

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
            required = "checkout, salida y semilla" if require_output else "checkout y semilla"
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
            lambda report: self._engine_completed(report, mode, seed, source, config)
        )
        label = "Calculando preview…" if mode is RunMode.PREVIEW else "Randomizando…"
        self._start_worker(worker, label, cancellable=False)

    def _engine_completed(
        self,
        report_object: object,
        mode: RunMode,
        seed: str,
        source: Path,
        config: GuiConfig,
    ) -> None:
        if not isinstance(report_object, dict):
            self._show_error("El motor devolvió un reporte inválido.")
            return
        report = cast(dict[str, Any], report_object)
        self._last_report = report
        self.preview_text.setPlainText(format_readable_report(report))
        self.report_text.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        self.tabs.setCurrentWidget(self.preview_text)
        if mode is RunMode.APPLY:
            self._last_applied_seed = seed
            self._last_applied_source = source.resolve()
            self._last_applied_config = json.dumps(
                config.as_dict(), sort_keys=True, separators=(",", ":")
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
        if (
            self._last_report is None
            or self._last_applied_seed != seed
            or self._last_applied_source != source.resolve()
            or self._last_applied_config != fingerprint
        ):
            self._show_error("Randomiza este checkout, semilla y configuración antes de compilar.")
            return
        profile = config.preset
        worker = BuildWorker(source, output, profile, seed, self._last_report)
        worker.completed.connect(self._build_completed)
        self._start_worker(worker, "Compilando SoulGold…", cancellable=True)

    def _build_completed(self, target: str) -> None:
        self.statusBar().showMessage(f"Compilación completada: {target}")
        QMessageBox.information(self, "Compilación completada", f"Salida:\n{target}")

    def _diagnose(self) -> None:
        source = Path(self.source_edit.text()) if self.source_edit.text().strip() else None
        worker = DiagnosticWorker(source)
        worker.completed.connect(self._diagnostics_completed)
        self._start_worker(worker, "Diagnosticando dependencias…", cancellable=False)

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
        worker.log.connect(self._append_log)
        worker.progress.connect(self.progress.setValue)
        worker.failed.connect(self._operation_failed)
        worker.cancelled.connect(self._operation_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._worker_finished)
        self._thread = thread
        self._worker = worker
        self._operation_cancellable = cancellable
        self._set_busy(True, cancellable)
        self.progress.setValue(0)
        self.statusBar().showMessage(status)
        thread.start()

    def _append_log(self, line: str) -> None:
        self.log_text.appendPlainText(line)

    def _operation_failed(self, message: str) -> None:
        self.log_text.appendPlainText(f"ERROR: {message}")
        self.tabs.setCurrentWidget(self.log_text)
        self.statusBar().showMessage("La operación falló")
        self._show_error(message)

    def _operation_cancelled(self, message: str) -> None:
        self.log_text.appendPlainText(message)
        self.tabs.setCurrentWidget(self.log_text)
        self.statusBar().showMessage("Operación cancelada")

    def _worker_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._operation_cancellable = False
        self._set_busy(False, False)

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
