"""Claude Code adapter.

Reference: https://code.claude.com/docs/en/hooks (read on 2026-09-15).
Configuration: `.claude/settings.json`, merged in place.

VS Code reads the same payload and output format, so `vscode.py` reuses
`parse_snake_case` and `render_claude_style` from this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any, Final

from agent_controls.harnesses.base import (
    Shell,
    ToolCatalog,
    as_mapping,
    as_text,
    command_line,
    context_text,
    is_own_command,
    optional_text,
    reason_text,
)
from agent_controls.model import (
    TOOL_HOOKS,
    Capability,
    Harness,
    Hook,
    HookInput,
    ProcessResult,
    Verdict,
)

_ALLOW: Final = frozenset({Verdict.ALLOW})
_ALLOW_BLOCK: Final = frozenset({Verdict.ALLOW, Verdict.BLOCK})
_ALL: Final = frozenset(Verdict)

EVENT_NAMES: Final[Mapping[Hook, str]] = {
    Hook.SESSION_START: "SessionStart",
    Hook.USER_PROMPT: "UserPromptSubmit",
    Hook.PRE_TOOL: "PreToolUse",
    Hook.POST_TOOL: "PostToolUse",
    Hook.STOP: "Stop",
    Hook.SUBAGENT_START: "SubagentStart",
    Hook.SUBAGENT_STOP: "SubagentStop",
    Hook.PRE_COMPACT: "PreCompact",
    Hook.SESSION_END: "SessionEnd",
}

CAPABILITIES: Final[Mapping[Hook, Capability]] = {
    Hook.SESSION_START: Capability(_ALLOW, context=True),
    Hook.USER_PROMPT: Capability(_ALLOW_BLOCK, context=True),
    Hook.PRE_TOOL: Capability(_ALL, context=True),
    Hook.POST_TOOL: Capability(_ALLOW_BLOCK, context=True),
    Hook.STOP: Capability(_ALLOW_BLOCK, context=False),
    Hook.SUBAGENT_START: Capability(_ALLOW, context=True),
    Hook.SUBAGENT_STOP: Capability(_ALLOW_BLOCK, context=False),
    Hook.PRE_COMPACT: Capability(_ALLOW, context=False),
    Hook.SESSION_END: Capability(_ALLOW, context=False),
}

TOOLS: Final = ToolCatalog(
    read=frozenset({"Read", "NotebookRead"}),
    write=frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"}),
    search=frozenset({"Glob", "Grep", "LS"}),
    shell=frozenset({"Bash", "PowerShell"}),
    path_keys=frozenset({"file_path", "notebook_path", "path"}),
)


def parse_snake_case(
    harness: Harness, hook: Hook, payload: Mapping[str, Any], tools: ToolCatalog
) -> HookInput:
    """Parse the snake_case payload that Claude Code and VS Code send."""
    tool = (
        tools.call(
            str(payload.get("tool_name", "")),
            as_mapping(payload.get("tool_input")),
            as_text(payload.get("tool_response")),
        )
        if hook in TOOL_HOOKS
        else None
    )
    return HookInput(
        harness=harness,
        hook=hook,
        session_id=str(payload.get("session_id") or ""),
        cwd=str(payload.get("cwd") or ""),
        agent_id=optional_text(payload.get("agent_id")),
        agent_type=optional_text(payload.get("agent_type")),
        tool=tool,
        prompt=optional_text(payload.get("prompt")),
        last_message=optional_text(payload.get("last_assistant_message")),
        stop_hook_active=payload.get("stop_hook_active") is True,
        raw=dict(payload),
    )


def render_claude_style(
    hook: Hook, result: ProcessResult, event_names: Mapping[Hook, str]
) -> dict[str, Any] | None:
    """Claude Code output. An `allow` on pre-tool gives no decision (R14)."""
    output: dict[str, Any] = {}
    specific: dict[str, Any] = {}
    if hook is Hook.PRE_TOOL and result.verdict is not Verdict.ALLOW:
        specific["permissionDecision"] = "deny" if result.verdict is Verdict.BLOCK else "ask"
        specific["permissionDecisionReason"] = reason_text(result)
    elif result.verdict is Verdict.BLOCK:
        output = {"decision": "block", "reason": reason_text(result)}
    if result.context:
        specific["additionalContext"] = context_text(result)
    if specific:
        output["hookSpecificOutput"] = {"hookEventName": event_names[hook], **specific}
    return output or None


class ClaudeAdapter:
    harness = Harness.CLAUDE
    tools = TOOLS
    capabilities = CAPABILITIES
    config_path = PurePosixPath(".claude/settings.json")

    def parse(self, hook: Hook, payload: Mapping[str, Any]) -> HookInput:
        return parse_snake_case(self.harness, hook, payload, self.tools)

    def render(self, hook: Hook, result: ProcessResult) -> Mapping[str, Any] | None:
        return render_claude_style(hook, result, EVENT_NAMES)

    def merge_config(
        self,
        existing: Mapping[str, Any],
        commands: Mapping[Hook, Sequence[str]],
        runner: str,
        timeout: int,
    ) -> dict[str, Any]:
        hooks = {
            event: _without_own_handlers(groups, runner)
            for event, groups in dict(existing.get("hooks", {})).items()
        }
        for hook, argv in commands.items():
            handler = {
                "type": "command",
                "command": command_line(argv, Shell.POSIX),
                "timeout": timeout,
            }
            matcher = {"matcher": "*"} if hook in TOOL_HOOKS else {}
            hooks.setdefault(EVENT_NAMES[hook], []).append({**matcher, "hooks": [handler]})
        return {**existing, "hooks": {event: groups for event, groups in hooks.items() if groups}}


def _without_own_handlers(groups: list[dict[str, Any]], runner: str) -> list[dict[str, Any]]:
    trimmed = (
        {
            **group,
            "hooks": [
                handler
                for handler in group.get("hooks", [])
                if not is_own_command(handler.get("command"), runner)
            ],
        }
        for group in groups
    )
    return [group for group in trimmed if group["hooks"]]
