"""The runner-file API: `get_current_context()`, `Context.add()`, `run()` and `log()`.

The CLI loads a runner file with `load_runner`. While the file runs, a context
variable holds the active hook call, so the functions below need no arguments.
"""

from __future__ import annotations

import runpy
import sys
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_actions.errors import AgentActionsError, IncompatibleProcessError, RunnerFileError
from agent_actions.harnesses.base import HarnessAdapter, ToolCatalog
from agent_actions.model import Harness, Hook, HookInput
from agent_actions.process import Condition, Process

DEFAULT_LOG_SOURCE = "runner"


class Context:
    """The processes of one runner file, and the hook call that they run for.

    During `agent_actions install`, `hook` and `event` are None.

    `flags` holds the flags of the project, and `session_flags` the flags of the
    current session. A flag is a named JSON value. A process or a `when` condition
    reads and changes these dicts, and the framework saves each change after the
    hook call. During `install`, the two dicts are empty.
    """

    def __init__(
        self,
        adapter: HarnessAdapter,
        hook: Hook | None,
        event: HookInput | None,
        flags: dict[str, Any] | None = None,
        session_flags: dict[str, Any] | None = None,
    ) -> None:
        self.adapter = adapter
        self.hook = hook
        self.event = event
        self.flags: dict[str, Any] = {} if flags is None else flags
        self.session_flags: dict[str, Any] = {} if session_flags is None else session_flags
        self._processes: list[Process] = []

    @property
    def harness(self) -> Harness:
        return self.adapter.harness

    @property
    def tools(self) -> ToolCatalog:
        return self.adapter.tools

    @property
    def processes(self) -> tuple[Process, ...]:
        return tuple(self._processes)

    def add(self, process: Process, *, when: Condition | None = None) -> Context:
        """Add a process. Raises IncompatibleProcessError when it cannot work in this harness.

        With `when`, the process runs only when `when(event)` is true. Use it, not an
        `if` around `add`: `install` must see the process to register its hook.
        """
        problems = compatibility_problems(process, self.adapter)
        if any(existing.label == process.label for existing in self._processes):
            problems.append(f"another process is named '{process.label}'; set a different `name`")
        if problems:
            raise IncompatibleProcessError(
                f"Cannot add process '{process.label}' for harness '{self.harness}': "
                + "; ".join(problems)
                + "."
            )
        if when is not None:
            process.when = when
        self._processes.append(process)
        return self

    def active(self) -> tuple[Process, ...]:
        """The processes that run on the current hook, in the order they were added."""
        return tuple(process for process in self._processes if self.hook in process.hooks)

    def hooks(self) -> tuple[Hook, ...]:
        """Every hook that at least one process uses, in lifecycle order."""
        used = {hook for process in self._processes for hook in process.hooks}
        return tuple(hook for hook in Hook if hook in used)


def compatibility_problems(process: Process, adapter: HarnessAdapter) -> list[str]:
    """Why a process cannot work in a harness. An empty list means that it can."""
    return [problem for hook in process.hooks for problem in _hook_problems(process, hook, adapter)]


def _hook_problems(process: Process, hook: Hook, adapter: HarnessAdapter) -> list[str]:
    capability = adapter.capabilities.get(hook)
    problems: list[str] = []
    if hook not in process.family:
        problems.append(
            f"'{hook}' is not a hook of {type(process).__name__} "
            f"(its hooks: {', '.join(process.family)})"
        )
    elif capability is None:
        problems.append(f"harness '{adapter.harness}' has no '{hook}' hook")
    else:
        missing = sorted(process.verdicts - capability.verdicts)
        if missing:
            problems.append(f"'{hook}' cannot deliver the verdicts {', '.join(missing)}")
        if process.uses_context and not capability.context:
            problems.append(f"'{hook}' has no channel for context")
    return problems


@dataclass(slots=True)
class _Invocation:
    adapter: HarnessAdapter
    hook: Hook | None
    event: HookInput | None
    flags: dict[str, Any] | None = None
    session_flags: dict[str, Any] | None = None
    context: Context | None = None
    submitted: bool = False


_INVOCATION: ContextVar[_Invocation | None] = ContextVar("agent_actions_invocation", default=None)
_LOG_LINES: ContextVar[list[str] | None] = ContextVar("agent_actions_log_lines", default=None)
_LOG_SOURCE: ContextVar[str] = ContextVar("agent_actions_log_source", default=DEFAULT_LOG_SOURCE)


def get_current_context() -> Context:
    """The context of the active hook call. The same object on every call."""
    invocation = _active_invocation()
    if invocation.context is None:
        invocation.context = Context(
            invocation.adapter,
            invocation.hook,
            invocation.event,
            invocation.flags,
            invocation.session_flags,
        )
    return invocation.context


def run(context: Context) -> None:
    """Hand the context to the CLI. The CLI runs the active processes when the runner file ends."""
    invocation = _active_invocation()
    invocation.context = context
    invocation.submitted = True


def log(message: str) -> None:
    """Append a line to log.txt of the current agent folder. Outside a run, print to stderr."""
    line = f"[{_LOG_SOURCE.get()}] {message}"
    lines = _LOG_LINES.get()
    if lines is None:
        print(line, file=sys.stderr)
    else:
        lines.append(line)


@contextmanager
def capture_log(lines: list[str]) -> Generator[None, None, None]:
    token = _LOG_LINES.set(lines)
    try:
        yield
    finally:
        _LOG_LINES.reset(token)


@contextmanager
def log_source(label: str) -> Generator[None, None, None]:
    token = _LOG_SOURCE.set(label)
    try:
        yield
    finally:
        _LOG_SOURCE.reset(token)


def _active_invocation() -> _Invocation:
    invocation = _INVOCATION.get()
    if invocation is None:
        raise RunnerFileError(
            "No hook call is active. Start the runner file with `agent_actions run` "
            "or `agent_actions install`."
        )
    return invocation


def load_runner(
    path: Path,
    adapter: HarnessAdapter,
    hook: Hook | None,
    event: HookInput | None,
    flags: dict[str, Any] | None = None,
    session_flags: dict[str, Any] | None = None,
) -> Context:
    """Execute a runner file and return the context that it handed to `run`."""
    if not path.is_file():
        raise RunnerFileError(f"The runner file '{path}' does not exist.")
    invocation = _Invocation(adapter, hook, event, flags, session_flags)
    folder = str(path.resolve().parent)
    token = _INVOCATION.set(invocation)
    sys.path.insert(0, folder)
    try:
        runpy.run_path(str(path), run_name="__main__")
    except AgentActionsError:
        raise
    except Exception as error:
        raise RunnerFileError(
            f"The runner file '{path}' failed: {type(error).__name__}: {error}"
        ) from error
    finally:
        sys.path.remove(folder)
        _INVOCATION.reset(token)
    if not invocation.submitted or invocation.context is None:
        raise RunnerFileError(f"The runner file '{path}' did not call agent_actions.run(context).")
    return invocation.context
