"""Flags: set one on a hook, and compare the git work tree with a snapshot in a flag.

A flag is a named JSON value in `Context.flags` (all sessions of the project) or in
`Context.session_flags` (one session). Give one of these dicts to the functions
below. A test gives a plain dict.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from agent_controls.model import Hook, HookInput, ProcessResult, allow
from agent_controls.process import EventProcess
from agent_controls.processes.commands import (
    Command,
    CommandOutcome,
    CommandRunner,
    run_subprocess,
    with_paths,
)
from agent_controls.processes.paths import matching_pattern, relative_path

if TYPE_CHECKING:
    import git

Flags = MutableMapping[str, Any]

BASELINE_FLAG: Final = "baseline"
_AS_COMMITTED: Final = ""  # the "digest" of a path that equals the commit of the snapshot


class SetFlag(EventProcess):
    """Sets a flag when it runs. To select the moment, use `on`, and `when` in `Context.add`.

    `value` can be a function of the hook event, for example `git_snapshot`. With
    `keep`, a flag that has a value keeps it. Use `keep` for a baseline: a harness
    can fire `session-start` again in one session, for example after a compaction.
    """

    def __init__(
        self,
        flags: Flags,
        flag: str,
        value: Any = True,
        *,
        on: Sequence[Hook] = (Hook.SESSION_START,),
        keep: bool = False,
        name: str = "",
    ) -> None:
        self.flags = flags
        self.flag = flag
        self.value = value
        self.on = tuple(on)
        self.keep = keep
        self.name = name or f"SetFlag({flag})"

    def run(self, event: HookInput) -> ProcessResult:
        if self.keep and self.flag in self.flags:
            result = allow(f"Kept the flag '{self.flag}'.")
        else:
            self.flags[self.flag] = self.value(event) if callable(self.value) else self.value
            result = allow(f"Set the flag '{self.flag}'.")
        return result


def git_snapshot(event: HookInput) -> dict[str, Any]:
    """The state of the git work tree now, as the value of a flag.

    It holds the last commit, and a digest of each file that differs from it. It
    needs a git repository with one commit or more, at the project root or above it.
    """
    repo = _repo(event.root)
    commit = repo.head.commit.hexsha
    return {"commit": commit, "files": _differing_files(repo, commit)}


def changed_paths(
    root: str | Path, snapshot: Mapping[str, Any] | None, patterns: Sequence[str] = ()
) -> list[str]:
    """The paths whose content changed after a snapshot, relative to the project root.

    A file that was edited, created, deleted, committed with new content, or put back
    to its committed content is in the list. A file that had uncommitted changes at
    the snapshot, and that did not change after it, is not. Without a snapshot, each
    uncommitted change is in the list. With `patterns`, only matching paths are.
    """
    repo = _repo(root)
    before = snapshot or {"commit": repo.head.commit.hexsha, "files": {}}
    then: Mapping[str, str | None] = before["files"]
    now = _differing_files(repo, before["commit"])
    relative = sorted(
        relative_path(str(Path(repo.working_dir, path)), str(root), str(root))
        for path in then.keys() | now.keys()
        if then.get(path, _AS_COMMITTED) != now.get(path, _AS_COMMITTED)
    )
    return [
        path
        for path in relative
        if not path.startswith("..") and (not patterns or matching_pattern(path, patterns))
    ]


def on_changed_paths(
    flags: Flags,
    patterns: Sequence[str] = (),
    *,
    flag: str = BASELINE_FLAG,
    command_runner: CommandRunner = run_subprocess,
) -> CommandRunner:
    """A command runner that replaces `{paths}` with the files that changed after a snapshot.

    The snapshot is the value of `flag`. Deleted files are not in `{paths}`. When no
    file changed, the command does not run, and the result is a pass.
    """

    def run(command: Command, cwd: Path, timeout: float, stdin: str = "") -> CommandOutcome:
        paths = [
            path for path in changed_paths(cwd, flags.get(flag), patterns) if (cwd / path).is_file()
        ]
        return (
            command_runner(with_paths(command, paths), cwd, timeout, stdin)
            if paths
            else CommandOutcome(0, "")
        )

    return run


def clear_on_pass(
    flags: Flags, flag: str, *, command_runner: CommandRunner = run_subprocess
) -> CommandRunner:
    """A command runner that deletes a flag when the command passes."""

    def run(command: Command, cwd: Path, timeout: float, stdin: str = "") -> CommandOutcome:
        outcome = command_runner(command, cwd, timeout, stdin)
        if outcome.exit_code == 0:
            flags.pop(flag, None)
        return outcome

    return run


def _repo(root: str | Path) -> git.Repo:
    # Imported here: the import takes about 200 ms, and it fails when git is not
    # installed. A hook call that reads no snapshot must not pay for it.
    import git

    return git.Repo(root, search_parent_directories=True)


def _differing_files(repo: git.Repo, commit: str) -> dict[str, str | None]:
    """The digest of each file that differs from a commit, or None for a deleted file.

    ponytail: two git scans of the whole work tree, and one read of each changed
    file, on each call. Compare the size and the modification time first if a work
    tree holds large uncommitted files.
    """
    tracked = str(repo.git.diff("--name-only", "--no-renames", "-z", commit)).split("\0")
    return {
        path: _digest(Path(repo.working_dir, path))
        for path in sorted({*tracked, *repo.untracked_files})
        if path
    }


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
