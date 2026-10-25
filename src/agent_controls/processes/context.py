"""Context injection."""

from __future__ import annotations

from collections.abc import Sequence

from agent_controls.model import Hook, HookInput, ProcessResult, allow
from agent_controls.process import EventProcess


class AddContext(EventProcess):
    """Adds fixed text to the agent context, for example the project rules.

    Typical hooks: session-start, subagent-start, user-prompt. `Context.add`
    rejects a hook that has no context channel in the harness.
    """

    uses_context = True

    def __init__(
        self, text: str, *, on: Sequence[Hook] = (Hook.SESSION_START,), name: str = ""
    ) -> None:
        self.text = text
        self.on = tuple(on)
        self.name = name

    def run(self, event: HookInput) -> ProcessResult:
        return allow(context=self.text)
