"""Processes that run a command: on stop until it passes, after an edit, or on any hook.

Each command gets the hook event as JSON on its standard input. The exit code and
the output are its answer.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agent_actions.model import Hook, HookInput, ProcessResult, ToolKind, allow, block
from agent_actions.process import ALLOW_ONLY, EventProcess, PostToolProcess, StopProcess
from agent_actions.processes.paths import matching_pattern, relative_path

Command = str | Sequence[str]

TIMEOUT_EXIT_CODE: Final = 124
NOT_FOUND_EXIT_CODE: Final = 127
DEFAULT_MAX_OUTPUT_CHARS: Final = 3000
PATHS_PLACEHOLDER: Final = "{paths}"
PYTEST_COMMAND: Final = (sys.executable, "-m", "pytest", "-q")
STOP_REASON: Final = "Fix the problems, then finish your work."
TESTS_REASON: Final = (
    "Make all tests pass before you finish. Do not change or delete tests to make them pass."
)
EDIT_REASON: Final = "Fix these problems."
RUN_REASON: Final = "Read the output before you continue."


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    exit_code: int
    output: str


CommandRunner = Callable[[Command, Path, float, str], CommandOutcome]


def run_subprocess(command: Command, cwd: Path, timeout: float, stdin: str = "") -> CommandOutcome:
    """Run a command, and write `stdin` to its standard input.

    A string runs in the shell; a sequence runs without a shell.
    """
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=isinstance(command, str),
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        outcome = CommandOutcome(completed.returncode, completed.stdout + completed.stderr)
    except subprocess.TimeoutExpired:
        outcome = CommandOutcome(
            TIMEOUT_EXIT_CODE, f"The command did not finish in {timeout:.0f} s."
        )
    except FileNotFoundError as error:
        outcome = CommandOutcome(NOT_FOUND_EXIT_CODE, str(error))
    return outcome


def display(command: Command) -> str:
    return command if isinstance(command, str) else shlex.join(command)


def tail(text: str, max_chars: int) -> str:
    """The end of the output, where test runners and linters print their summary."""
    return text if len(text) <= max_chars else "..." + text[-max_chars:]


def with_paths(command: Command, paths: Sequence[str]) -> Command:
    """The command with `{paths}` replaced by the given paths."""
    return (
        command.replace(PATHS_PLACEHOLDER, " ".join(shlex.quote(path) for path in paths))
        if isinstance(command, str)
        else [
            item for part in command for item in (paths if part == PATHS_PLACEHOLDER else (part,))
        ]
    )


def working_dir(event: HookInput) -> Path:
    return Path(event.root or event.cwd or ".")


def event_json(event: HookInput) -> str:
    """The hook event as JSON, in the same shape for every harness. Commands read it on stdin."""
    return json.dumps(event.to_record())


class RequireCommand(StopProcess):
    """Blocks the stop while a command fails, and gives the command output to the agent.

    Use it for linters, type checkers or builds. Wrap it in LoopGuard to limit retries.
    """

    def __init__(
        self,
        command: Command,
        *,
        reason: str = STOP_REASON,
        timeout: float = 240.0,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        on: Sequence[Hook] = (Hook.STOP,),
        name: str = "",
        command_runner: CommandRunner = run_subprocess,
    ) -> None:
        self.command = command
        self.reason = reason
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.on = tuple(on)
        self.name = name
        self.command_runner = command_runner

    def run(self, event: HookInput) -> ProcessResult:
        outcome = self.command_runner(
            self.command, working_dir(event), self.timeout, event_json(event)
        )
        shown = display(self.command)
        return (
            allow(f"`{shown}` passed.")
            if outcome.exit_code == 0
            else block(
                f"`{shown}` failed with exit code {outcome.exit_code}. {self.reason}",
                f"Output:\n{tail(outcome.output, self.max_output_chars)}",
            )
        )


class RequireTests(RequireCommand):
    """RequireCommand with pytest, run by the Python interpreter that runs the hook."""

    def __init__(
        self, command: Command = PYTEST_COMMAND, *, reason: str = TESTS_REASON, **options: Any
    ) -> None:
        super().__init__(command, reason=reason, **options)


class CheckAfterEdit(PostToolProcess):
    """After a write tool, runs a command and gives its failure output to the agent as context.

    Put `{paths}` in the command to pass the edited paths. With `patterns`, only
    edits of matching paths run the command, for example `patterns=["*.py"]`.
    """

    verdicts = ALLOW_ONLY
    uses_context = True

    def __init__(
        self,
        command: Command,
        *,
        patterns: Sequence[str] = (),
        reason: str = EDIT_REASON,
        timeout: float = 120.0,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        name: str = "",
        command_runner: CommandRunner = run_subprocess,
    ) -> None:
        self.command = command
        self.patterns = tuple(patterns)
        self.reason = reason
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.name = name
        self.command_runner = command_runner

    def run(self, event: HookInput) -> ProcessResult:
        paths = self._checked_paths(event)
        result = allow()
        if paths is not None:
            command = with_paths(self.command, paths)
            outcome = self.command_runner(
                command, working_dir(event), self.timeout, event_json(event)
            )
            shown = display(command)
            result = (
                allow(f"`{shown}` passed.")
                if outcome.exit_code == 0
                else allow(
                    context=f"`{shown}` failed with exit code {outcome.exit_code} after your edit. "
                    f"{self.reason}\n{tail(outcome.output, self.max_output_chars)}"
                )
            )
        return result

    def _checked_paths(self, event: HookInput) -> tuple[str, ...] | None:
        """The edited paths to check, or None when this call needs no check."""
        tool = event.tool
        checked: tuple[str, ...] | None = None
        if tool is not None and tool.kind is ToolKind.WRITE:
            checked = tuple(
                path
                for path in tool.paths
                if not self.patterns
                or matching_pattern(relative_path(path, event.cwd, event.root), self.patterns)
            )
            if self.patterns and not checked:
                checked = None
        return checked


class RunCommand(EventProcess):
    """Runs a command on any hook with a context channel, and gives its failure output as context.

    Use it on the start hooks, to tell the agent what is broken before it works.
    It never blocks. To keep the agent working until a command passes, use
    RequireCommand on the stop hooks. To run a command only after an edit, use
    CheckAfterEdit.
    """

    uses_context = True

    def __init__(
        self,
        command: Command,
        *,
        on: Sequence[Hook] = (Hook.SESSION_START,),
        reason: str = RUN_REASON,
        timeout: float = 240.0,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        name: str = "",
        command_runner: CommandRunner = run_subprocess,
    ) -> None:
        self.command = command
        self.on = tuple(on)
        self.reason = reason
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.name = name
        self.command_runner = command_runner

    def run(self, event: HookInput) -> ProcessResult:
        outcome = self.command_runner(
            self.command, working_dir(event), self.timeout, event_json(event)
        )
        shown = display(self.command)
        return (
            allow(f"`{shown}` passed.")
            if outcome.exit_code == 0
            else allow(
                context=f"`{shown}` failed with exit code {outcome.exit_code}. {self.reason}\n"
                f"{tail(outcome.output, self.max_output_chars)}"
            )
        )
