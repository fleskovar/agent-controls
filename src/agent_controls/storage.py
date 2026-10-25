"""JSON files and lock files, written so that a crash or a parallel call loses no data."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final, cast

from agent_controls.errors import StateError

LOCK_WAIT_SECONDS: Final = 600.0
STALE_LOCK_SECONDS: Final = 900.0
LOCK_POLL_SECONDS: Final = 0.05


def read_json(path: Path) -> dict[str, Any]:
    """The JSON object in a file, or {} when the file does not exist.

    A corrupt file is an error, so that no caller overwrites data it could not read.
    """
    document: Any = {}
    if path.exists():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise StateError(
                f"'{path}' is not valid JSON ({error}). Fix or delete the file; "
                "agent_controls does not overwrite it."
            ) from error
    if not isinstance(document, dict):
        raise StateError(f"'{path}' must contain a JSON object.")
    return cast("dict[str, Any]", document)


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    """Write through a temporary file and a rename, so that readers never see half a file."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


@contextmanager
def file_lock(
    path: Path,
    wait_seconds: float = LOCK_WAIT_SECONDS,
    stale_seconds: float = STALE_LOCK_SECONDS,
) -> Generator[None, None, None]:
    """Hold an exclusive lock file for the duration of the block.

    ponytail: a polling lock file with a stale-age cutoff. A holder that runs longer
    than `stale_seconds` can lose the lock; switch to OS locks (fcntl/msvcrt) if needed.
    """
    deadline = time.monotonic() + wait_seconds
    while not _try_create(path):
        if _age_seconds(path) > stale_seconds:
            path.unlink(missing_ok=True)
        elif time.monotonic() > deadline:
            raise StateError(f"Timed out after {wait_seconds:.0f} s waiting for the lock '{path}'.")
        else:
            time.sleep(LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _try_create(path: Path) -> bool:
    created = True
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except (FileExistsError, PermissionError):
        created = False
    return created


def _age_seconds(path: Path) -> float:
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        age = 0.0
    return age
