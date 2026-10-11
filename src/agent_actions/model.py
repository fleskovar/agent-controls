"""The neutral data model: hooks, verdicts, tool calls, hook inputs and process results.

Nothing in this module knows a harness. The adapters in `agent_actions.harnesses`
translate harness payloads into these types, and these types into harness output.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Final


class Harness(StrEnum):
    """The agent programs that fire hooks."""

    CLAUDE = "claude"
    VSCODE = "vscode"
    COPILOT_CLI = "copilot-cli"


class Hook(StrEnum):
    """Neutral lifecycle hooks. Each harness has its own name for each one."""

    SESSION_START = "session-start"
    USER_PROMPT = "user-prompt"
    PRE_TOOL = "pre-tool"
    POST_TOOL = "post-tool"
    STOP = "stop"
    SUBAGENT_START = "subagent-start"
    SUBAGENT_STOP = "subagent-stop"
    PRE_COMPACT = "pre-compact"
    SESSION_END = "session-end"


TOOL_HOOKS: Final = frozenset({Hook.PRE_TOOL, Hook.POST_TOOL})


class Verdict(StrEnum):
    """The decision of a process. Its meaning depends on the hook.

    - pre-tool: allow the call, ask the user, or block the call.
    - stop / subagent-stop: allow the stop, or block it so that the agent continues.
    - post-tool / user-prompt: allow, or block and give the reasons to the agent.
    """

    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


SEVERITY: Final[Mapping[Verdict, int]] = {Verdict.ALLOW: 0, Verdict.ASK: 1, Verdict.BLOCK: 2}


class ToolKind(StrEnum):
    """What a tool does, independent of its harness-specific name."""

    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    SHELL = "shell"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call, as a pre-tool or post-tool hook sees it."""

    name: str
    kind: ToolKind
    arguments: Mapping[str, Any] = field(default_factory=dict[str, Any])
    paths: tuple[str, ...] = ()
    command: str | None = None
    output: str | None = None


@dataclass(frozen=True, slots=True)
class HookInput:
    """The payload of one hook call, in the same shape for every harness.

    `cwd` is the agent working directory from the payload. `root` is the project
    root, where `.hooks/` lives. Tool paths are as the harness gave them; resolve
    relative paths against `cwd`.
    """

    harness: Harness
    hook: Hook
    session_id: str = ""
    cwd: str = ""
    root: str = ""
    agent_id: str | None = None
    agent_type: str | None = None
    tool: ToolCall | None = None
    prompt: str | None = None
    last_message: str | None = None
    stop_hook_active: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict[str, Any])

    def to_record(self) -> dict[str, Any]:
        """Plain JSON form for state.json. The raw payload goes to io.json instead."""
        record = asdict(self)
        del record["raw"]
        return record


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """What a process returns: a verdict, reasons for the agent, and extra context."""

    verdict: Verdict = Verdict.ALLOW
    reasons: tuple[str, ...] = ()
    context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict is not Verdict.ALLOW and not self.reasons:
            raise ValueError(f"A '{self.verdict}' result needs at least one reason for the agent.")

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


def allow(*reasons: str, context: str | Iterable[str] = ()) -> ProcessResult:
    """No objection. The reasons go to log.txt; the context goes to the agent."""
    return ProcessResult(Verdict.ALLOW, reasons, _texts(context))


def ask(reason: str, *more: str, context: str | Iterable[str] = ()) -> ProcessResult:
    """Let the user decide (pre-tool only). The reasons explain the question."""
    return ProcessResult(Verdict.ASK, (reason, *more), _texts(context))


def block(reason: str, *more: str, context: str | Iterable[str] = ()) -> ProcessResult:
    """Block the tool call, the prompt or the stop. The reasons tell the agent what to do."""
    return ProcessResult(Verdict.BLOCK, (reason, *more), _texts(context))


def _texts(value: str | Iterable[str]) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


@dataclass(frozen=True, slots=True)
class NamedResult:
    process: str
    result: ProcessResult


def combine(results: Sequence[NamedResult]) -> ProcessResult:
    """One result for the hook: the most restrictive verdict wins.

    The reasons of the processes that returned the winning verdict are kept, each
    prefixed with the process name. The context of all processes is kept.
    """
    verdict = max(
        (named.result.verdict for named in results),
        key=SEVERITY.__getitem__,
        default=Verdict.ALLOW,
    )
    reasons = tuple(
        f"[{named.process}] {reason}"
        for named in results
        if named.result.verdict is verdict
        for reason in named.result.reasons
    )
    context = tuple(text for named in results for text in named.result.context)
    return ProcessResult(verdict, reasons, context)


@dataclass(frozen=True, slots=True)
class Capability:
    """What one harness can deliver to the agent on one hook."""

    verdicts: frozenset[Verdict]
    context: bool


@dataclass(frozen=True, slots=True)
class Response:
    """What the CLI writes back to the harness."""

    stdout: Mapping[str, Any] | None = None
    exit_code: int = 0
    stderr: str = ""
