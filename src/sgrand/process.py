"""Cancelable subprocess execution shared by checkout and build workers."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .errors import RandomizerError


@dataclass(frozen=True)
class CommandSpec:
    argv: tuple[str, ...]
    cwd: Path | None = None
    environment: Mapping[str, str] | None = None
    cancel_argv: tuple[str, ...] | None = None

    @property
    def display(self) -> str:
        return " ".join(self.argv)


class ProcessCancelled(RandomizerError):
    """Raised when a user cancels an external process."""


def _terminate_process_tree(
    process: subprocess.Popen[str], cancel_argv: tuple[str, ...] | None
) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        if cancel_argv is not None:
            with suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run(
                    cancel_argv,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            check=False,
            capture_output=True,
            text=True,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)


def run_command(
    command: CommandSpec,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    on_line: Callable[[str], None] = lambda _line: None,
    on_progress: Callable[[int], None] = lambda _value: None,
) -> None:
    """Run a command without a shell, stream logs, and cancel its process tree."""
    environment = os.environ.copy()
    if command.environment:
        environment.update(command.environment)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command.argv,
            cwd=command.cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            start_new_session=os.name != "nt",
            creationflags=flags,
        )
    except OSError as exc:
        raise RandomizerError(f"Cannot start {command.display}: {exc}") from exc
    output: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output.put(line.rstrip("\r\n"))
        output.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    lines = 0
    stream_closed = False
    on_progress(1)
    while process.poll() is None or not stream_closed:
        if cancelled():
            _terminate_process_tree(process, command.cancel_argv)
            raise ProcessCancelled(f"Cancelled: {command.display}")
        try:
            line = output.get(timeout=0.1)
        except queue.Empty:
            continue
        if line is None:
            stream_closed = True
            continue
        on_line(line)
        lines += 1
        lower = line.lower()
        if "objcopy" in lower or "gbafix" in lower:
            progress = 97
        elif "arm-none-eabi-ld" in lower or "memory region" in lower:
            progress = 92
        elif "trainerproc" in lower:
            progress = 15
        else:
            progress = min(88, 3 + lines // 35)
        on_progress(progress)
    reader.join(timeout=1)
    return_code = process.wait()
    if return_code:
        raise RandomizerError(f"Command failed with exit code {return_code}: {command.display}")
    on_progress(100)
