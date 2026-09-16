"""Rollback-capable, multi-file source transactions."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from .errors import TransactionError
from .models import PlannedWrite

Replace = Callable[
    [
        str | bytes | os.PathLike[str] | os.PathLike[bytes],
        str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ],
    None,
]


def _stage(path: Path, content: bytes, mode: int | None) -> Path:
    if not path.parent.is_dir():
        raise TransactionError(f"Target directory does not exist: {path.parent}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.sgrand-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, stat.S_IMODE(mode))
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _current(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


class FileTransaction:
    """Preflight, stage, commit and roll back an entire set of file writes."""

    def __init__(self, replace: Replace = os.replace) -> None:
        self._replace = replace

    def apply(self, writes: Sequence[PlannedWrite]) -> None:
        if len({write.path for write in writes}) != len(writes):
            raise TransactionError("A transaction cannot write the same path twice")
        for write in writes:
            if _current(write.path) != write.original:
                raise TransactionError(
                    f"Source changed while planning; refusing to overwrite {write.path}"
                )

        staged: dict[Path, Path] = {}
        rollback_staged: dict[Path, Path] = {}
        committed: list[PlannedWrite] = []
        try:
            for write in writes:
                mode = write.path.stat().st_mode if write.path.exists() else None
                staged[write.path] = _stage(write.path, write.updated, mode)
                if write.original is not None:
                    rollback_staged[write.path] = _stage(write.path, write.original, mode)

            for write in writes:
                self._replace(staged[write.path], write.path)
                staged.pop(write.path, None)
                committed.append(write)
        except BaseException as exc:
            rollback_errors: list[str] = []
            for write in reversed(committed):
                try:
                    if write.original is None:
                        write.path.unlink(missing_ok=True)
                    else:
                        self._replace(rollback_staged[write.path], write.path)
                        rollback_staged.pop(write.path, None)
                except BaseException as rollback_exc:
                    rollback_errors.append(f"{write.path}: {rollback_exc}")
            detail = f"Transaction failed and was rolled back: {exc}"
            if rollback_errors:
                detail += "; rollback errors: " + "; ".join(rollback_errors)
            raise TransactionError(detail) from exc
        finally:
            for temporary in (*staged.values(), *rollback_staged.values()):
                temporary.unlink(missing_ok=True)
