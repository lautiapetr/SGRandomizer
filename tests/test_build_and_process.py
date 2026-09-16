from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from sgrand.build import (
    LinuxBuildAdapter,
    MacOSBuildAdapter,
    Wsl2BuildAdapter,
    build_adapter,
)
from sgrand.checkout import SOULGOLD_REPOSITORY, SOULGOLD_TAG, checkout_clone_command
from sgrand.errors import RandomizerError
from sgrand.process import CommandSpec, ProcessCancelled, run_command


def test_platform_build_commands_are_argument_safe(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout with spaces"
    linux = LinuxBuildAdapter().command(checkout, 4)
    assert linux.argv == ("make", "-j4")
    assert linux.cwd == checkout

    mac = MacOSBuildAdapter().command(checkout, 0)
    assert mac.argv == ("make", "-j1")
    assert mac.environment is not None
    assert mac.environment["DEVKITARM"].endswith("/devkitARM")

    windows = Wsl2BuildAdapter("Ubuntu").command(checkout, 8)
    assert windows.argv[:6] == (
        "wsl.exe",
        "--distribution",
        "Ubuntu",
        "--cd",
        str(checkout),
        "sh",
    )
    assert "setsid make -j8" in windows.argv[-1]
    assert windows.cancel_argv is not None
    assert "kill -TERM" in windows.cancel_argv[-1]


def test_adapter_selection_and_unsupported_platform() -> None:
    assert isinstance(build_adapter("Linux"), LinuxBuildAdapter)
    assert isinstance(build_adapter("Darwin"), MacOSBuildAdapter)
    assert isinstance(build_adapter("Windows"), Wsl2BuildAdapter)
    with pytest.raises(RandomizerError, match="Unsupported build platform"):
        build_adapter("Plan9")


def test_checkout_clone_is_pinned_and_rejects_nonempty_target(tmp_path: Path) -> None:
    destination = tmp_path / "download"
    command = checkout_clone_command(destination)
    assert SOULGOLD_REPOSITORY in command.argv
    assert SOULGOLD_TAG in command.argv
    assert "--depth" in command.argv
    (destination / "existing.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(RandomizerError, match="must be empty"):
        checkout_clone_command(destination)


def test_process_streams_output_and_progress(tmp_path: Path) -> None:
    lines: list[str] = []
    progress: list[int] = []
    run_command(
        CommandSpec(
            (
                sys.executable,
                "-c",
                "print('trainerproc'); print('arm-none-eabi-ld'); print('objcopy')",
            ),
            cwd=tmp_path,
        ),
        on_line=lines.append,
        on_progress=progress.append,
    )
    assert lines == ["trainerproc", "arm-none-eabi-ld", "objcopy"]
    assert progress[-1] == 100
    assert max(progress) == 100


def test_process_can_be_cancelled() -> None:
    cancelled = threading.Event()
    timer = threading.Timer(0.15, cancelled.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ProcessCancelled):
            run_command(
                CommandSpec(
                    (
                        sys.executable,
                        "-c",
                        "import time; print('started', flush=True); time.sleep(10)",
                    )
                ),
                cancelled=cancelled.is_set,
            )
    finally:
        timer.cancel()
    assert time.monotonic() - started < 4
