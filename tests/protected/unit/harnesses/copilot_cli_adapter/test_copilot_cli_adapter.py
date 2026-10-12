from collections.abc import Mapping
from typing import Any

import pytest

from agent_actions.harnesses.copilot_cli import CopilotCliAdapter
from agent_actions.model import Hook, ProcessResult, ToolKind, allow, ask, block

ADAPTER = CopilotCliAdapter()


def test_string_tool_args_are_decoded() -> None:
    payload = {
        "sessionId": "s-1",
        "timestamp": 1704614400000,
        "cwd": "/repo",
        "toolName": "view",
        "toolArgs": '{"path": ".env"}',
    }

    event = ADAPTER.parse(Hook.PRE_TOOL, payload)

    assert event.tool is not None
    assert (event.session_id, event.tool.kind, event.tool.paths) == (
        "s-1",
        ToolKind.READ,
        (".env",),
    )


def test_post_tool_result_text_is_the_tool_output() -> None:
    payload = {
        "toolName": "bash",
        "toolArgs": {"command": "make test"},
        "toolResult": {"resultType": "success", "textResultForLlm": "12 passed"},
    }

    tool = ADAPTER.parse(Hook.POST_TOOL, payload).tool

    assert tool is not None
    assert (tool.command, tool.output) == ("make test", "12 passed")


def test_subagent_stop_uses_the_agent_name_when_the_type_is_missing() -> None:
    payload = {
        "sessionId": "s",
        "agentId": "a1",
        "agentName": "reviewer",
        "response": "Looks good.",
    }

    event = ADAPTER.parse(Hook.SUBAGENT_STOP, payload)

    assert (event.agent_id, event.agent_type, event.last_message) == (
        "a1",
        "reviewer",
        "Looks good.",
    )


def test_snake_case_payload_from_a_claude_format_configuration_is_read() -> None:
    payload = {"session_id": "s-2", "tool_name": "edit", "tool_input": {"path": "a.py"}}

    event = ADAPTER.parse(Hook.PRE_TOOL, payload)

    assert event.tool is not None
    assert (event.session_id, event.tool.kind) == ("s-2", ToolKind.WRITE)


@pytest.mark.parametrize(
    ("hook", "result", "expected"),
    [
        (
            Hook.PRE_TOOL,
            block("no"),
            {"permissionDecision": "deny", "permissionDecisionReason": "no"},
        ),
        (
            Hook.PRE_TOOL,
            ask("sure?"),
            {"permissionDecision": "ask", "permissionDecisionReason": "sure?"},
        ),
        (Hook.PRE_TOOL, allow("fine"), None),
        (Hook.STOP, block("tests fail"), {"decision": "block", "reason": "tests fail"}),
        (Hook.POST_TOOL, allow(context="lint errors"), {"additionalContext": "lint errors"}),
    ],
    ids=[
        "pre_tool_deny",
        "pre_tool_ask",
        "pre_tool_allow",
        "agent_stop_block",
        "post_tool_context",
    ],
)
def test_result_is_rendered_as_top_level_fields(
    hook: Hook, result: ProcessResult, expected: Mapping[str, Any] | None
) -> None:
    assert ADAPTER.render(hook, result) == expected


def test_install_writes_a_versioned_file_with_bash_and_powershell() -> None:
    argv = (
        "py",
        "-m",
        "agent_actions",
        "run",
        "checks.py",
        "--harness",
        "copilot-cli",
        "--hook",
        "stop",
    )

    merged = ADAPTER.merge_config({}, {Hook.STOP: argv}, "checks.py", 45)

    command = "py -m agent_actions run checks.py --harness copilot-cli --hook stop"
    assert merged == {
        "version": 1,
        "hooks": {
            "agentStop": [
                {
                    "type": "command",
                    "bash": command,
                    "powershell": command,
                    "cwd": ".",
                    "timeoutSec": 45,
                }
            ]
        },
    }
