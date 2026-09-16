"""Background operations used by the Qt window."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..build import build_adapter, diagnose, format_diagnostics
from ..checkout import download_checkout
from ..engine import Randomizer, RunMode
from ..gui_config import GuiConfig, materialize_gui_config
from ..process import ProcessCancelled, run_command
from ..reporting import publish_rom, write_technical_report


@dataclass(frozen=True)
class EngineRequest:
    source: Path
    output: Path
    seed: str
    config: GuiConfig
    mode: RunMode


class Worker(QObject):
    failed = Signal(str)
    cancelled = Signal(str)
    log = Signal(str)
    progress = Signal(int)
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = threading.Event()

    @Slot()
    def cancel(self) -> None:
        self._cancelled.set()


class EngineWorker(Worker):
    completed = Signal(object)

    def __init__(self, request: EngineRequest) -> None:
        super().__init__()
        self.request = request

    @Slot()
    def run(self) -> None:
        try:
            self.log.emit("Validando checkout y configuración…")
            self.progress.emit(5)
            with materialize_gui_config(self.request.config) as paths:
                report = Randomizer().run(
                    self.request.source,
                    self.request.seed,
                    self.request.mode,
                    move_config_path=paths.moves,
                    ability_config_path=paths.abilities,
                    ability_profile=paths.ability_profile,
                    trainer_config_path=paths.trainers,
                    trainer_profile=paths.trainer_profile,
                    include_spoilers=not self.request.config.spoiler_free,
                )
            self.progress.emit(90)
            if self.request.mode is RunMode.APPLY:
                try:
                    report_path = write_technical_report(
                        report,
                        self.request.output,
                        self.request.config.preset,
                        self.request.seed,
                    )
                except OSError as exc:
                    self.log.emit(
                        "ADVERTENCIA: la transacción terminó correctamente, "
                        f"pero no se pudo copiar el reporte: {exc}"
                    )
                else:
                    self.log.emit(f"Reporte técnico: {report_path}")
            self.progress.emit(100)
            self.completed.emit(report)
        except ProcessCancelled as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:  # Qt worker boundary
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class BuildWorker(Worker):
    completed = Signal(str)

    def __init__(
        self,
        source: Path,
        output: Path,
        profile: str,
        seed: str,
        report: dict[str, Any],
    ) -> None:
        super().__init__()
        self.source = source
        self.output = output
        self.profile = profile
        self.seed = seed
        self.report = report

    @Slot()
    def run(self) -> None:
        try:
            adapter = build_adapter()
            command = adapter.command(self.source, os.cpu_count() or 2)
            self.log.emit(f"Adaptador: {adapter.name}")
            self.log.emit(f"Ejecutando: {command.display}")
            run_command(
                command,
                cancelled=self._cancelled.is_set,
                on_line=self.log.emit,
                on_progress=self.progress.emit,
            )
            target = publish_rom(self.source, self.output, self.profile, self.seed, overwrite=False)
            try:
                write_technical_report(self.report, self.output, self.profile, self.seed)
            except OSError as exc:
                self.log.emit(f"ADVERTENCIA: no se pudo actualizar el reporte: {exc}")
            self.completed.emit(str(target))
        except ProcessCancelled as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:  # Qt worker boundary
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class DownloadWorker(Worker):
    completed = Signal(str)

    def __init__(self, destination: Path) -> None:
        super().__init__()
        self.destination = destination

    @Slot()
    def run(self) -> None:
        try:
            self.log.emit("Descargando SoulGold v.1.1.4 desde el repositorio oficial…")
            download_checkout(
                self.destination,
                cancelled=self._cancelled.is_set,
                on_line=self.log.emit,
                on_progress=self.progress.emit,
            )
            self.completed.emit(str(self.destination))
        except ProcessCancelled as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:  # Qt worker boundary
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class DiagnosticWorker(Worker):
    completed = Signal(str)

    def __init__(self, source: Path | None) -> None:
        super().__init__()
        self.source = source

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(10)
            result = format_diagnostics(diagnose(self.source))
            self.progress.emit(100)
            self.completed.emit(result)
        except Exception as exc:  # Qt worker boundary
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
