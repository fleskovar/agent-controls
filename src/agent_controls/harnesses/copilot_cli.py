"""GitHub Copilot CLI adapter.

References (read on 2026-09-15):
- https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks
- https://docs.github.com/en/copilot/reference/hooks-reference

Payloads are camelCase and carry no event name, which is why the hook command
passes `--hook`. `toolArgs` can arrive as a JSON string. Decisions are top-level
fields. Configuration: `.github/hooks/agent-controls-copilot-cli.json`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any, Final, cast

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

CONFIG_VERSION: Final = 1

EVENT_NAMES: Final[Mapping[Hook, str]] = {
    Hook.SESSION_START: "sessionStart",
    Hook.USER_PROMPT: "userPromptSubmitted",
    Hook.PRE_TOOL: "preToolUse",
    Hook.POST_TOOL: "postToolUse",
    Hook.STOP: "agentStop",
    Hook.SUBAGENT_STOP: "subagentStop",
    Hook.SESSION_END: "sessionEnd",
}

_ALLOW: Final = frozenset({Verdict.ALLOW})
_ALLOW_BLOCK: Final = frozenset({Verdict.ALLOW, Verdict.BLOCK})

CAPABILITIES: Final[Mapping[Hook, Capability]] = {
    Hook.SESSION_START: Capability(_ALLOW, context=False),
    Hook.USER_PROMPT: Capability(_ALLOW, context=False),
    Hook.PRE_TOOL: Capability(frozenset(Verdict), context=False),
    Hook.POST_TOOL: Capability(_ALLOW, context=True),
    Hook.STOP: Capability(_ALLOW_BLOCK, context=False),
    Hook.SUBAGENT_STOP: Capability(_ALLOW_BLOCK, context=False),
    Hook.SESSION_END: Capability(_ALLOW, context=False),
}

TOOLS: Final = ToolCatalog(
    read=frozenset({"view"}),
    write=frozenset({"create", "edit"}),
    search=frozenset({"grep", "glob"}),
    shell=frozenset({"bash", "powershell"}),
    path_keys=frozenset({"path", "file_path"}),
)


def _field(payload: Mapping[str, Any], camel: str, snake: str) -> Any:
    """camelCase first; snake_case when Copilot CLI runs a Claude-format configuration."""
    value = payload.get(camel)
    return payload.get(snake) if value is None else value


def _tool_output(result: Any) -> str | None:
    return (
        as_text(cast("Mapping[str, Any]", result).get("textResultForLlm"))
        if isinstance(result, Mapping)
        else as_text(result)
    )


class CopilotCliAdapter:
    harness = Harness.COPILOT_CLI
    tools = TOOLS
    capabilities = CAPABILITIES
    config_path = PurePosixPath(".github/hooks/agent-controls-copilot-cli.json")

    def parse(self, hook: Hook, payload: Mapping[str, Any]) -> HookInput:
        tool = (
            self.tools.call(
                str(_field(payload, "toolName", "tool_name") or ""),
                as_mapping(_field(payload, "toolArgs", "tool_input")),
                _tool_output(_field(payload, "toolResult", "tool_response")),
            )
            if hook in TOOL_HOOKS
            else None
        )
        return HookInput(
            harness=self.harness,
            hook=hook,
            session_id=str(_field(payload, "sessionId", "session_id") or ""),
            cwd=str(payload.get("cwd") or ""),
            agent_id=optional_text(_field(payload, "agentId", "agent_id")),
            agent_type=optional_text(
                _field(payload, "agentType", "agent_type") or payload.get("agentName")
            ),
            tool=tool,
            prompt=optional_text(payload.get("prompt")),
            last_message=optional_text(payload.get("response")),
            stop_hook_active=_field(payload, "stopHookActive", "stop_hook_active") is True,
            raw=dict(payload),
        )

    def render(self, hook: Hook, result: ProcessResult) -> Mapping[str, Any] | None:
        output: dict[str, Any] = {}
        if hook is Hook.PRE_TOOL and result.verdict is not Verdict.ALLOW:
            output = {
                "permissionDecision": "deny" if result.verdict is Verdict.BLOCK else "ask",
                "permissionDecisionReason": reason_text(result),
            }
        elif result.verdict is Verdict.BLOCK:
            output = {"decision": "block", "reason": reason_text(result)}
        if result.context:
            output["additionalContext"] = context_text(result)
        return output or None

    def merge_config(
        self,
        existing: Mapping[str, Any],
        commands: Mapping[Hook, Sequence[str]],
        runner: str,
        timeout: int,
    ) -> dict[str, Any]:
        hooks: dict[str, list[dict[str, Any]]] = {
            event: [
                handler for handler in handlers if not is_own_command(handler.get("bash"), runner)
            ]
            for event, handlers in dict(existing.get("hooks", {})).items()
        }
        for hook, argv in commands.items():
            hooks.setdefault(EVENT_NAMES[hook], []).append(
                {
                    "type": "command",
                    "bash": command_line(argv, Shell.POSIX),
                    "powershell": command_line(argv, Shell.POWERSHELL),
                    "cwd": ".",
                    "timeoutSec": timeout,
                }
            )
        return {
            **existing,
            "version": CONFIG_VERSION,
            "hooks": {event: handlers for event, handlers in hooks.items() if handlers},
        }
