from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal, Slot, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from sgrand.engine import RunMode
from sgrand.gui.window import MainWindow
from sgrand.gui.workers import Worker


class BurstWorker(Worker):
    @Slot()
    def run(self) -> None:
        for index in range(500):
            self.log.emit(f"line {index}")
            self.progress.emit(index % 101)
        self.finished.emit()


class FailingWorker(Worker):
    @Slot()
    def run(self) -> None:
        self.log.emit("before failure")
        self.failed.emit("synthetic worker failure")
        self.finished.emit()


class CancellableWorker(Worker):
    @Slot()
    def run(self) -> None:
        while not self._cancelled.wait(0.002):
            self.progress.emit(25)
        self.cancelled.emit("synthetic worker cancelled")
        self.finished.emit()


class RecoveryBuildWorker(Worker):
    completed = Signal(str)
    selected_profile = ""

    def __init__(
        self,
        _source: Path,
        output: Path,
        profile: str,
        seed: str,
        _report: dict[str, object],
    ) -> None:
        super().__init__()
        self.output = output
        self.profile = profile
        self.seed = seed
        type(self).selected_profile = profile

    @Slot()
    def run(self) -> None:
        self.completed.emit(str(self.output / f"SGRand-{self.profile}-{self.seed}.gba"))
        self.finished.emit()


class ThreadCheckingWindow(MainWindow):
    def __init__(self) -> None:
        self.callbacks_on_gui_thread: list[bool] = []
        self.errors: list[str] = []
        self.build_target = ""
        super().__init__()

    def _record_thread(self) -> None:
        self.callbacks_on_gui_thread.append(self.thread().isCurrentThread())

    @Slot(object)
    def _engine_completed(self, result_object: object) -> None:
        self._record_thread()
        super()._engine_completed(result_object)

    @Slot(str)
    def _append_log(self, line: str) -> None:
        self._record_thread()
        super()._append_log(line)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self._record_thread()
        super()._operation_failed(message)

    @Slot(str)
    def _diagnostics_completed(self, result: str) -> None:
        self._record_thread()
        super()._diagnostics_completed(result)

    @Slot(str)
    def _build_completed(self, target: str) -> None:
        self._record_thread()
        self.build_target = target
        self.statusBar().showMessage(f"Compilación completada: {target}")

    def _show_error(self, message: str) -> None:
        self.errors.append(message)


def _wait_for_worker(window: MainWindow, timeout: float = 15.0) -> None:
    application = QApplication.instance()
    assert application is not None
    deadline = time.monotonic() + timeout
    while window._thread is not None and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.002)
    application.processEvents()
    assert window._thread is None, "background worker did not finish before timeout"


@pytest.fixture
def thread_window() -> ThreadCheckingWindow:
    application = QApplication.instance() or QApplication([])
    window = ThreadCheckingWindow()
    yield window
    window.close()
    application.processEvents()


def test_preview_and_apply_callbacks_stay_on_gui_thread(
    thread_window: ThreadCheckingWindow,
    synthetic_source: Path,
    tmp_path: Path,
) -> None:
    qt_messages: list[str] = []

    def message_handler(_kind: object, _context: object, message: str) -> None:
        qt_messages.append(message)

    previous_handler = qInstallMessageHandler(message_handler)
    try:
        thread_window.source_edit.setText(str(synthetic_source))
        thread_window.output_edit.setText(str(tmp_path / "output"))
        thread_window.seed_edit.setText("thread-regression")

        thread_window._run_engine(RunMode.PREVIEW)
        _wait_for_worker(thread_window)
        assert thread_window.preview_text.toPlainText()
        assert thread_window.report_text.toPlainText()

        thread_window._run_engine(RunMode.APPLY)
        _wait_for_worker(thread_window)
        assert thread_window._last_applied_seed == "thread-regression"
    finally:
        qInstallMessageHandler(previous_handler)

    assert not thread_window.errors
    assert thread_window.callbacks_on_gui_thread
    assert all(thread_window.callbacks_on_gui_thread)
    assert not any("different thread" in message for message in qt_messages)
    assert not any("Cannot create children" in message for message in qt_messages)


def test_diagnostic_completion_stays_on_gui_thread(
    thread_window: ThreadCheckingWindow, synthetic_source: Path
) -> None:
    thread_window.source_edit.setText(str(synthetic_source))
    thread_window._diagnose()
    _wait_for_worker(thread_window)

    assert thread_window.log_text.toPlainText()
    assert not thread_window.errors
    assert thread_window.callbacks_on_gui_thread
    assert all(thread_window.callbacks_on_gui_thread)


def test_worker_event_queue_handles_bursts_and_failure(
    thread_window: ThreadCheckingWindow,
) -> None:
    thread_window._start_worker(BurstWorker(), "burst", cancellable=False)
    _wait_for_worker(thread_window)
    assert "line 0" in thread_window.log_text.toPlainText()
    assert "line 499" in thread_window.log_text.toPlainText()
    assert all(thread_window.callbacks_on_gui_thread)

    thread_window.callbacks_on_gui_thread.clear()
    thread_window._start_worker(FailingWorker(), "failure", cancellable=False)
    _wait_for_worker(thread_window)
    assert thread_window.errors == ["synthetic worker failure"]
    assert "ERROR: synthetic worker failure" in thread_window.log_text.toPlainText()
    assert all(thread_window.callbacks_on_gui_thread)


def test_cancellable_worker_finishes_cleanly_on_gui_thread(
    thread_window: ThreadCheckingWindow,
) -> None:
    application = QApplication.instance()
    assert application is not None
    thread_window._start_worker(CancellableWorker(), "cancel", cancellable=True)
    deadline = time.monotonic() + 2
    while not thread_window.cancel_button.isEnabled() and time.monotonic() < deadline:
        application.processEvents()
    thread_window._cancel_operation()
    _wait_for_worker(thread_window)

    assert "synthetic worker cancelled" in thread_window.log_text.toPlainText()
    assert not thread_window.errors
    assert all(thread_window.callbacks_on_gui_thread)


def test_build_recovers_previous_randomization_session(
    thread_window: ThreadCheckingWindow,
    synthetic_source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    seed = "recovered-seed"
    report = {
        "tool": "SGRand",
        "schema_version": 1,
        "supported_tag": "v.1.1.4",
        "seed_input": seed,
        "seed_numeric": 1,
        "applied": True,
        "spoilers_included": False,
        "counts": {
            "files_changed": 1,
            "wild_slots_changed": 1,
            "static_and_gift_commands_changed": 1,
            "map_items_changed": 1,
            "scripted_items_changed": 1,
            "level_up_slots_changed": 1,
            "compatibility_species_changed": 1,
            "normal_abilities_species_changed": 1,
            "innates_species_changed": 1,
            "trainers_changed": 1,
        },
        "writes": [],
    }
    report_path = output / f"SGRand-Custom-{seed}-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr("sgrand.gui.window.BuildWorker", RecoveryBuildWorker)

    thread_window.source_edit.setText(str(synthetic_source))
    thread_window.output_edit.setText(str(output))
    thread_window.seed_edit.setText(seed)
    thread_window._build()
    _wait_for_worker(thread_window)

    assert not thread_window.errors
    assert RecoveryBuildWorker.selected_profile == "Custom"
    assert thread_window.build_target.endswith(f"SGRand-Custom-{seed}.gba")
    assert (
        f"Sesión de randomización recuperada: {report_path}" in thread_window.log_text.toPlainText()
    )
    assert all(thread_window.callbacks_on_gui_thread)


def test_build_uses_current_session_without_disk_report(
    thread_window: ThreadCheckingWindow,
    synthetic_source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    seed = "same-session-seed"
    thread_window.source_edit.setText(str(synthetic_source))
    thread_window.output_edit.setText(str(output))
    thread_window.seed_edit.setText(seed)
    thread_window._run_engine(RunMode.APPLY)
    _wait_for_worker(thread_window)
    assert not thread_window.errors

    for report_path in output.glob("*-report.json"):
        report_path.unlink()
    (synthetic_source / "soulgold-randomizer-manifest.json").unlink()
    monkeypatch.setattr("sgrand.gui.window.BuildWorker", RecoveryBuildWorker)

    thread_window._build()
    _wait_for_worker(thread_window)
    assert not thread_window.errors
    assert RecoveryBuildWorker.selected_profile == "Balanced"
    assert thread_window.build_target.endswith(f"SGRand-Balanced-{seed}.gba")
    assert all(thread_window.callbacks_on_gui_thread)
