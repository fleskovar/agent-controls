"""What every harness adapter provides, and the helpers that the adapters share."""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Final, Protocol, cast

from agent_actions.model import (
    Capability,
    Harness,
    Hook,
    HookInput,
    ProcessResult,
    ToolCall,
    ToolKind,
)

AGENT_ACTIONS_RUN: Final = "agent_actions run"


class HarnessAdapter(Protocol):
    """All knowledge about one harness. Add a harness by implementing this protocol."""

    @property
    def harness(self) -> Harness: ...

    @property
    def tools(self) -> ToolCatalog: ...

    @property
    def capabilities(self) -> Mapping[Hook, Capability]: ...

    @property
    def config_path(self) -> PurePosixPath: ...

    def parse(self, hook: Hook, payload: Mapping[str, Any]) -> HookInput:
        """The harness payload as a neutral HookInput."""
        ...

    def render(self, hook: Hook, result: ProcessResult) -> Mapping[str, Any] | None:
        """The stdout JSON for a result that the capability check accepted. None: no output."""
        ...

    def merge_config(
        self,
        existing: Mapping[str, Any],
        commands: Mapping[Hook, Sequence[str]],
        runner: str,
        timeout: int,
    ) -> dict[str, Any]:
        """The configuration document with the entries of `runner` replaced by `commands`."""
        ...


@dataclass(frozen=True, slots=True)
class ToolCatalog:
    """The tool names of one harness, grouped by what the tool does.

    Use it in a process to recognize tools, for example
    `event.tool.name in tools_for(event.harness).write`. Most processes only need
    `event.tool.kind`, which the adapter sets from this catalog.
    """

    read: frozenset[str]
    write: frozenset[str]
    search: frozenset[str]
    shell: frozenset[str]
    path_keys: frozenset[str]
    command_keys: frozenset[str] = frozenset({"command"})

    def kind_of(self, tool_name: str) -> ToolKind:
        groups = (
            (self.write, ToolKind.WRITE),
            (self.read, ToolKind.READ),
            (self.search, ToolKind.SEARCH),
            (self.shell, ToolKind.SHELL),
        )
        return next((kind for names, kind in groups if tool_name in names), ToolKind.OTHER)

    def call(
        self,
        name: str,
        arguments: Mapping[str, Any],
        output: str | None = None,
        extra_paths: Sequence[str] = (),
    ) -> ToolCall:
        kind = self.kind_of(name)
        command = (
            next(
                (
                    value
                    for key, value in arguments.items()
                    if key in self.command_keys and isinstance(value, str)
                ),
                None,
            )
            if kind is ToolKind.SHELL
            else None
        )
        paths = tuple(dict.fromkeys((*find_paths(arguments, self.path_keys), *extra_paths)))
        return ToolCall(name, kind, dict(arguments), paths, command, output)


def find_paths(value: Any, keys: frozenset[str]) -> tuple[str, ...]:
    """Every string under a path key, at any depth, in order, without duplicates.

    Nested search covers tools that edit several files in one call, such as
    `MultiEdit` or `multi_replace_string_in_file`.
    """
    found: list[str] = []
    _collect_paths(value, keys, found)
    return tuple(dict.fromkeys(found))


def _collect_paths(value: Any, keys: frozenset[str], found: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in cast("Mapping[object, object]", value).items():
            if key in keys and isinstance(item, str):
                found.append(item)
            elif key in keys and isinstance(item, list):
                found.extend(path for path in cast("list[object]", item) if isinstance(path, str))
            else:
                _collect_paths(item, keys, found)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            _collect_paths(item, keys, found)


def as_mapping(value: Any) -> Mapping[str, Any]:
    """Tool arguments as a mapping. A JSON object string is decoded."""
    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = {"value": value}
    return (
        cast("Mapping[str, Any]", decoded) if isinstance(decoded, Mapping) else {"value": decoded}
    )


def as_text(value: Any) -> str | None:
    """A payload value as text: strings stay, other JSON values are encoded."""
    return value if value is None or isinstance(value, str) else json.dumps(value)


def optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def reason_text(result: ProcessResult) -> str:
    return "\n".join(result.reasons)


def context_text(result: ProcessResult) -> str:
    return "\n\n".join(result.context)


class Shell(StrEnum):
    POSIX = "posix"
    POWERSHELL = "powershell"


_SHELL_SAFE: Final = re.compile(r"[\w./:+-]+")


def command_line(argv: Sequence[str], shell: Shell) -> str:
    """One command string for the shell that the harness uses.

    Arguments without special characters stay unquoted, which works in bash, cmd
    and PowerShell alike. Other arguments are quoted for the given shell.
    """
    line = " ".join(argv)
    if not all(_SHELL_SAFE.fullmatch(argument) for argument in argv):
        line = (
            shlex.join(argv)
            if shell is Shell.POSIX
            else "& " + " ".join("'" + argument.replace("'", "''") + "'" for argument in argv)
        )
    return line


def is_own_command(command: Any, runner: str) -> bool:
    """True for a command that `install` wrote for this runner file."""
    return isinstance(command, str) and AGENT_ACTIONS_RUN in command and runner in command
