"""Test data builders: valid, boring defaults. Each test overrides only what it is about."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_actions.model import Harness, Hook, HookInput, ToolCall, ToolKind

ROOT = "/repo"


def an_event(hook: Hook = Hook.PRE_TOOL, **overrides: Any) -> HookInput:
    defaults: dict[str, Any] = {
        "harness": Harness.CLAUDE,
        "hook": hook,
        "session_id": "session-1",
        "cwd": ROOT,
        "root": ROOT,
    }
    return HookInput(**(defaults | overrides))


def a_tool_event(
    name: str,
    kind: ToolKind,
    *,
    paths: Sequence[str] = (),
    command: str | None = None,
    hook: Hook = Hook.PRE_TOOL,
) -> HookInput:
    return an_event(hook, tool=ToolCall(name, kind, paths=tuple(paths), command=command))
