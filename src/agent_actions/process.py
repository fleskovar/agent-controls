"""Process base classes. A process runs on hooks and returns a ProcessResult.

A process family fixes the hooks that a process can attach to and the verdicts
that it can return. `Context.add` checks both against the harness, so a process
on the wrong hook fails at install time instead of failing silently in the agent.

State: the attributes that `__state__` creates are the state variables. The
framework restores their last recorded values before `run` and records them after.

Condition: `Context.add(process, when=...)` sets `when`. The framework calls it
with the hook event before `run`, and skips the process when the answer is false.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Final

from agent_actions.errors import StateError
from agent_actions.model import Hook, HookInput, ProcessResult, Verdict

ALLOW_ONLY: Final = frozenset({Verdict.ALLOW})
ALLOW_OR_BLOCK: Final = frozenset({Verdict.ALLOW, Verdict.BLOCK})
ANY_VERDICT: Final = frozenset(Verdict)

Condition = Callable[[HookInput], object]

_STATE_NAMES_ATTRIBUTE: Final = "_state_names"


class Process(ABC):
    """Base of all processes. Extend a family class, not this one."""

    family: ClassVar[tuple[Hook, ...]] = tuple(Hook)
    verdicts: ClassVar[frozenset[Verdict]] = ANY_VERDICT
    uses_context: ClassVar[bool] = False

    name: str = ""
    on: tuple[Hook, ...] = ()
    when: Condition | None = None

    @abstractmethod
    def run(self, event: HookInput) -> ProcessResult:
        """Decide on one hook call."""

    def __state__(self) -> None:  # noqa: B027 - optional by design, most guardrails hold no state
        """Create the state attributes with their initial values. The default has no state."""

    @property
    def label(self) -> str:
        """The process name in state.json, logs and reasons. Set `name` to change it."""
        return self.name or type(self).__name__

    @property
    def hooks(self) -> tuple[Hook, ...]:
        """The hooks this process runs on: `on`, or the first hook of the family."""
        return tuple(self.on) or self.family[:1]

    def state_names(self) -> tuple[str, ...]:
        names: tuple[str, ...] | None = self.__dict__.get(_STATE_NAMES_ATTRIBUTE)
        if names is None:
            before = set(vars(self))
            self.__state__()
            names = tuple(key for key in vars(self) if key not in before)
            vars(self)[_STATE_NAMES_ATTRIBUTE] = names
        return names

    def load_state(self, saved: Mapping[str, Any]) -> None:
        """Reset the state to its initial values, then apply the saved values it knows."""
        names = self.state_names()
        self.__state__()
        for key in names:
            if key in saved:
                setattr(self, key, saved[key])

    def dump_state(self) -> dict[str, Any]:
        """The current state values, checked to be JSON-serializable."""
        state = {key: getattr(self, key) for key in self.state_names()}
        for key, value in state.items():
            try:
                json.dumps(value)
            except (TypeError, ValueError) as error:
                raise StateError(
                    f"State variable '{key}' of process '{self.label}' is not "
                    f"JSON-serializable: {error}"
                ) from error
        return state


class PreToolProcess(Process):
    """Runs before a tool call. It can allow, ask the user, or block the call."""

    family = (Hook.PRE_TOOL,)


class PostToolProcess(Process):
    """Runs after a tool call. It can give feedback with block or with context."""

    family = (Hook.POST_TOOL,)
    verdicts = ALLOW_OR_BLOCK


class PromptProcess(Process):
    """Runs when the user submits a prompt. It can block the prompt."""

    family = (Hook.USER_PROMPT,)
    verdicts = ALLOW_OR_BLOCK


class StopProcess(Process):
    """Runs when the agent or a subagent wants to stop.

    Block keeps the agent working. The reasons tell the agent what is missing.
    """

    family = (Hook.STOP, Hook.SUBAGENT_STOP)
    verdicts = ALLOW_OR_BLOCK


class StartProcess(Process):
    """Runs when a session or a subagent starts. It can only allow and add context."""

    family = (Hook.SESSION_START, Hook.SUBAGENT_START)
    verdicts = ALLOW_ONLY


class EventProcess(Process):
    """Runs on any hook, to observe or to add context. It can only allow."""

    verdicts = ALLOW_ONLY
