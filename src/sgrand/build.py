"""Cross-platform SoulGold build adapters and dependency diagnostics."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import RandomizerError
from .process import CommandSpec
from .source import validate_source


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    detail: str
    remedy: str = ""


class BuildAdapter:
    name = "unknown"

    def command(self, checkout: Path, jobs: int) -> CommandSpec:
        raise NotImplementedError

    def diagnose(self) -> list[DependencyStatus]:
        raise NotImplementedError


def _native_tool(name: str, remedy: str) -> DependencyStatus:
    resolved = shutil.which(name)
    return DependencyStatus(name, resolved is not None, resolved or "not found", remedy)


def _probe(argv: tuple[str, ...], name: str, remedy: str) -> DependencyStatus:
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DependencyStatus(name, False, str(exc), remedy)
    detail = (result.stdout or result.stderr).strip() or f"exit {result.returncode}"
    return DependencyStatus(name, result.returncode == 0, detail, remedy)


class LinuxBuildAdapter(BuildAdapter):
    name = "Linux native"

    def command(self, checkout: Path, jobs: int) -> CommandSpec:
        return CommandSpec(("make", f"-j{max(1, jobs)}"), cwd=checkout)

    def diagnose(self) -> list[DependencyStatus]:
        return [
            _native_tool("git", "Install git with the system package manager."),
            _native_tool("make", "Install build-essential or the equivalent."),
            _native_tool("python3", "Install Python 3."),
            _native_tool(
                "arm-none-eabi-gcc",
                "Install binutils-arm-none-eabi, gcc-arm-none-eabi and libnewlib-arm-none-eabi.",
            ),
            _native_tool("pkg-config", "Install pkg-config and libpng development headers."),
            _probe(
                ("pkg-config", "--exists", "libpng"),
                "libpng",
                "Install libpng development headers.",
            )
            if shutil.which("pkg-config")
            else DependencyStatus(
                "libpng", False, "pkg-config unavailable", "Install pkg-config and libpng."
            ),
        ]


class MacOSBuildAdapter(BuildAdapter):
    name = "macOS native"

    def command(self, checkout: Path, jobs: int) -> CommandSpec:
        devkitpro = os.environ.get("DEVKITPRO", "/opt/devkitpro")
        environment = {
            "DEVKITPRO": devkitpro,
            "DEVKITARM": os.environ.get("DEVKITARM", f"{devkitpro}/devkitARM"),
        }
        return CommandSpec(("make", f"-j{max(1, jobs)}"), cwd=checkout, environment=environment)

    def diagnose(self) -> list[DependencyStatus]:
        return [
            _native_tool("git", "Install Xcode Command Line Tools."),
            _native_tool("make", "Install Xcode Command Line Tools."),
            _native_tool("python3", "Install Python 3."),
            _native_tool("pkg-config", "Run: brew install pkg-config libpng"),
            _probe(
                ("pkg-config", "--exists", "libpng"),
                "libpng",
                "Run: brew install libpng",
            )
            if shutil.which("pkg-config")
            else DependencyStatus(
                "libpng", False, "pkg-config unavailable", "Run: brew install pkg-config libpng"
            ),
            _native_tool(
                "arm-none-eabi-gcc",
                "Install devkitPro pacman, gba-dev and devkitarm-rules.",
            ),
            _probe(
                ("xcode-select", "-p"),
                "Xcode Command Line Tools",
                "Run: xcode-select --install",
            ),
        ]


class Wsl2BuildAdapter(BuildAdapter):
    name = "Windows WSL2"

    def __init__(self, distribution: str | None = None) -> None:
        self.distribution = distribution

    def _prefix(self) -> tuple[str, ...]:
        return (
            ("wsl.exe", "--distribution", self.distribution) if self.distribution else ("wsl.exe",)
        )

    def command(self, checkout: Path, jobs: int) -> CommandSpec:
        parallel = max(1, jobs)
        build_script = (
            f"setsid make -j{parallel} & pid=$!; "
            'echo "$pid" > .sgrand-build.pid; '
            "trap 'kill -TERM -- -$pid 2>/dev/null || true; "
            "rm -f .sgrand-build.pid' INT TERM EXIT; "
            'wait "$pid"'
        )
        cancel_script = (
            "if test -f .sgrand-build.pid; then "
            "pid=$(cat .sgrand-build.pid); kill -TERM -- -$pid 2>/dev/null || true; fi"
        )
        return CommandSpec(
            (*self._prefix(), "--cd", str(checkout), "sh", "-lc", build_script),
            cancel_argv=(
                *self._prefix(),
                "--cd",
                str(checkout),
                "sh",
                "-lc",
                cancel_script,
            ),
        )

    def diagnose(self) -> list[DependencyStatus]:
        statuses = [
            _native_tool("git", "Install Git for Windows for checkout downloads."),
            _native_tool("wsl.exe", "Install WSL2 and an Ubuntu distribution."),
        ]
        if not shutil.which("wsl.exe"):
            return statuses
        statuses.append(
            _probe(
                ("wsl.exe", "--status"),
                "WSL status",
                "Run wsl --install, then ensure the default version is 2.",
            )
        )
        statuses.append(self._diagnose_version())
        statuses.append(
            _probe(
                (
                    *self._prefix(),
                    "sh",
                    "-lc",
                    "command -v make git python3 arm-none-eabi-gcc pkg-config >/dev/null "
                    "&& pkg-config --exists libpng",
                ),
                "SoulGold toolchain in WSL",
                "Install SoulGold's documented Ubuntu dependencies inside WSL2.",
            )
        )
        return statuses

    def _diagnose_version(self) -> DependencyStatus:
        try:
            result = subprocess.run(
                ("wsl.exe", "--list", "--verbose"),
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return DependencyStatus(
                "WSL2 distribution",
                False,
                str(exc),
                "Install a distribution and convert it with wsl --set-version <name> 2.",
            )
        output = (result.stdout or result.stderr).replace("\x00", "")
        rows = [line for line in output.splitlines() if line.strip()]
        if self.distribution:
            rows = [line for line in rows if self.distribution.casefold() in line.casefold()]
        else:
            default_rows = [line for line in rows if line.lstrip().startswith("*")]
            rows = default_rows or rows[1:]
        available = result.returncode == 0 and any(line.rstrip().endswith("2") for line in rows)
        detail = " | ".join(line.strip() for line in rows) or f"exit {result.returncode}"
        return DependencyStatus(
            "WSL2 distribution",
            available,
            detail,
            "Set the selected/default distribution to WSL2 with wsl --set-version <name> 2.",
        )


def build_adapter(system_name: str | None = None) -> BuildAdapter:
    selected = system_name or platform.system()
    if selected == "Linux":
        return LinuxBuildAdapter()
    if selected == "Darwin":
        return MacOSBuildAdapter()
    if selected == "Windows":
        return Wsl2BuildAdapter()
    raise RandomizerError(f"Unsupported build platform: {selected}")


def diagnose(
    checkout: Path | None = None, system_name: str | None = None
) -> list[DependencyStatus]:
    statuses = build_adapter(system_name).diagnose()
    if checkout is not None:
        try:
            validate_source(checkout)
        except RandomizerError as exc:
            statuses.append(
                DependencyStatus(
                    "SoulGold checkout v.1.1.4", False, str(exc), "Select or download v.1.1.4."
                )
            )
        else:
            statuses.append(
                DependencyStatus("SoulGold checkout v.1.1.4", True, str(checkout.resolve()))
            )
    return statuses


def format_diagnostics(statuses: list[DependencyStatus]) -> str:
    lines = []
    for status in statuses:
        marker = "OK" if status.available else "MISSING"
        line = f"[{marker}] {status.name}: {status.detail}"
        if not status.available and status.remedy:
            line += f"\n    {status.remedy}"
        lines.append(line)
    return "\n".join(lines)
