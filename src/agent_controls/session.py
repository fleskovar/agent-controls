"""Session folders under `.hooks/`: naming, lookup, step records and flags.

.hooks/flags.json
.hooks/<timestamp>_<short-session-id>/{session.json, flags.json}
.hooks/<timestamp>_<short-session-id>/main-agent/{state.json, io.json, log.txt}
.hooks/<timestamp>_<short-session-id>/<agent-type>_<timestamp>/{agent.json, ...}
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from agent_controls.engine import ProcessRecord
from agent_controls.errors import StateError
from agent_controls.model import HookInput
from agent_controls.storage import file_lock, read_json, write_json

HOOKS_DIR: Final = ".hooks"
MAIN_AGENT_DIR: Final = "main-agent"
SESSION_FILE: Final = "session.json"
AGENT_FILE: Final = "agent.json"
STATE_FILE: Final = "state.json"
IO_FILE: Final = "io.json"
LOG_FILE: Final = "log.txt"
FLAGS_FILE: Final = "flags.json"
LOCK_FILE: Final = ".lock"
SHORT_ID_LENGTH: Final = 8
UNKNOWN_SESSION: Final = "unknown"
DEFAULT_AGENT_TYPE: Final = "subagent"
COLLISION_STEP: Final = timedelta(milliseconds=1)


def format_timestamp(moment: datetime) -> str:
    """UTC as `YYYYMMDDTHHMMSSmmm`. The string order is the time order."""
    utc = moment.astimezone(UTC)
    return f"{utc:%Y%m%dT%H%M%S}{utc.microsecond // 1000:03d}"


def short_id(raw_id: str) -> str:
    """The first 8 letters, digits or '-' of an id."""
    return re.sub(r"[^A-Za-z0-9-]", "", raw_id)[:SHORT_ID_LENGTH] or UNKNOWN_SESSION


def slug(text: str | None) -> str:
    """A folder-safe agent type."""
    return re.sub(r"[^A-Za-z0-9-]+", "-", text or "").strip("-") or DEFAULT_AGENT_TYPE


def free_name(taken: Collection[str], moment: datetime, name_for: Callable[[str], str]) -> str:
    """The first name that is not taken. Each collision adds 1 ms to the timestamp."""
    name = name_for(format_timestamp(moment))
    while name in taken:
        moment += COLLISION_STEP
        name = name_for(format_timestamp(moment))
    return name


def latest_states(
    document: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Mapping[str, Any]]:
    """The most recent recorded state of each process in a state.json document."""
    return {
        name: record.get("state", {})
        for stamp in sorted(document)
        for name, record in document[stamp].items()
    }


_NO_FLAG: Final = object()


class FlagFile:
    """One `flags.json`: named JSON values that processes share between hook calls.

    `flags` is a plain dict. A hook call changes it, then `save` writes the changes.
    """

    def __init__(self, path: Path, lock: Path) -> None:
        self._path = path
        self._lock = lock
        self._loaded = read_json(path)
        self.flags: dict[str, Any] = copy.deepcopy(self._loaded)

    def save(self) -> list[str]:
        """Write the flags that changed after the load, and return their names.

        Only these flags are written, into the file as it is now. Thus a parallel
        hook call that changed a different flag loses nothing.

        ponytail: the last writer of one flag wins. Hold the lock for the whole hook
        call if two agents must count in one flag.
        """
        names = sorted(
            name
            for name in self._loaded.keys() | self.flags.keys()
            if self._loaded.get(name, _NO_FLAG) != self.flags.get(name, _NO_FLAG)
        )
        if names:
            with file_lock(self._lock):
                document = read_json(self._path)
                for name in names:
                    document.pop(name, None)
                document.update({name: self.flags[name] for name in names if name in self.flags})
                try:
                    write_json(self._path, document)
                except (TypeError, ValueError) as error:
                    raise StateError(
                        f"A flag of {', '.join(names)} in '{self._path}' is not "
                        f"JSON-serializable: {error}"
                    ) from error
        return names


@dataclass(frozen=True, slots=True)
class SessionSummary:
    folder: str
    session_id: str
    agents: tuple[str, ...]


class SessionStore:
    """Reads and writes the session files under `<root>/.hooks`."""

    def __init__(self, root: Path) -> None:
        self.hooks_dir = root / HOOKS_DIR

    def agent_dir(self, event: HookInput, now: datetime) -> Path:
        """The folder of the agent that fired the hook. Missing folders are created."""
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        session_short_id = short_id(event.session_id)
        with file_lock(self.hooks_dir / LOCK_FILE):
            session = _find_or_create(
                self.hooks_dir,
                f"*_{session_short_id}",
                SESSION_FILE,
                {"session_id": event.session_id},
                now,
                lambda stamp: f"{stamp}_{session_short_id}",
            )
            if event.agent_id is None:
                folder = session / MAIN_AGENT_DIR
                folder.mkdir(exist_ok=True)
            else:
                agent_type = slug(event.agent_type)
                folder = _find_or_create(
                    session,
                    f"{agent_type}_*",
                    AGENT_FILE,
                    {"agent_id": event.agent_id, "agent_type": event.agent_type},
                    now,
                    lambda stamp: f"{agent_type}_{stamp}",
                )
        return folder

    def flag_files(self, agent_dir: Path) -> tuple[FlagFile, FlagFile]:
        """The flags of the project, and the flags of the session of an agent folder."""
        lock = self.hooks_dir / LOCK_FILE
        return (
            FlagFile(self.hooks_dir / FLAGS_FILE, lock),
            FlagFile(agent_dir.parent / FLAGS_FILE, lock),
        )

    def saved_states(self, agent_dir: Path) -> dict[str, Mapping[str, Any]]:
        return latest_states(read_json(agent_dir / STATE_FILE))

    def record(
        self,
        agent_dir: Path,
        now: datetime,
        records: Sequence[ProcessRecord],
        io_record: Mapping[str, Any],
        log_lines: Sequence[str],
    ) -> str:
        """Append one step to state.json, io.json and log.txt. Returns the step timestamp.

        ponytail: each step rewrites the whole JSON files, O(steps) per call. Move to
        JSON Lines if sessions grow to thousands of hook calls.
        """
        states = read_json(agent_dir / STATE_FILE)
        ios = read_json(agent_dir / IO_FILE)
        stamp = free_name(states.keys() | ios.keys(), now, str)
        if records:
            states[stamp] = {record.name: record.to_record() for record in records}
            write_json(agent_dir / STATE_FILE, states)
        ios[stamp] = dict(io_record)
        write_json(agent_dir / IO_FILE, ios)
        with (agent_dir / LOG_FILE).open("a", encoding="utf-8") as log_file:
            log_file.writelines(f"{stamp} {line}\n" for line in log_lines)
        return stamp

    def sessions(self) -> list[SessionSummary]:
        """Recorded sessions, newest first."""
        folders = (
            sorted(
                (p for p in self.hooks_dir.iterdir() if (p / SESSION_FILE).is_file()), reverse=True
            )
            if self.hooks_dir.is_dir()
            else []
        )
        return [
            SessionSummary(
                folder.name,
                str(read_json(folder / SESSION_FILE).get("session_id", "")),
                tuple(sorted(child.name for child in folder.iterdir() if child.is_dir())),
            )
            for folder in folders
        ]


def _find_or_create(
    parent: Path,
    pattern: str,
    identity_file: str,
    identity: Mapping[str, Any],
    now: datetime,
    name_for: Callable[[str], str],
) -> Path:
    """The child folder whose identity file matches the first identity field, or a new one."""
    key = next(iter(identity))
    folder = next(
        (
            candidate
            for candidate in sorted(parent.glob(pattern))
            if candidate.is_dir() and read_json(candidate / identity_file).get(key) == identity[key]
        ),
        None,
    )
    if folder is None:
        folder = parent / free_name({child.name for child in parent.iterdir()}, now, name_for)
        folder.mkdir()
        write_json(folder / identity_file, identity)
    return folder
