from collections.abc import Mapping
from typing import Any

import pytest

from agent_actions.harnesses.claude import ClaudeAdapter
from agent_actions.model import Hook, ProcessResult, ToolCall, ToolKind, allow, ask, block

ADAPTER = ClaudeAdapter()


def test_pre_tool_payload_becomes_a_neutral_input() -> None:
    tool_input = {
        "file_path": "/repo/tests/test_a.py",
        "edits": [{"old_string": "1", "new_string": "2"}],
    }
    payload = {
        "session_id": "abc123",
        "cwd": "/repo",
        "hook_event_name": "PreToolUse",
        "tool_name": "MultiEdit",
        "tool_input": tool_input,
        "agent_id": "agent-1",
        "agent_type": "Explore",
    }

    event = ADAPTER.parse(Hook.PRE_TOOL, payload)

    assert event.tool == ToolCall(
        "MultiEdit", ToolKind.WRITE, tool_input, ("/repo/tests/test_a.py",)
    )
    assert (event.session_id, event.cwd, event.agent_id, event.agent_type) == (
        "abc123",
        "/repo",
        "agent-1",
        "Explore",
    )


def test_stop_payload_carries_stop_hook_active_and_the_last_message() -> None:
    payload = {"session_id": "s", "stop_hook_active": True, "last_assistant_message": "Done."}

    event = ADAPTER.parse(Hook.STOP, payload)

    assert (event.tool, event.stop_hook_active, event.last_message) == (None, True, "Done.")


@pytest.mark.parametrize(
    ("hook", "result", "expected"),
    [
        (Hook.PRE_TOOL, allow("not protected"), None),
        (
            Hook.PRE_TOOL,
            block("protected"),
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "protected",
                }
            },
        ),
        (
            Hook.PRE_TOOL,
            ask("sure?"),
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "sure?",
                }
            },
        ),
        (
            Hook.PRE_TOOL,
            allow(context="hint"),
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "hint"}},
        ),
        (
            Hook.STOP,
            block("tests fail", "fix them"),
            {"decision": "block", "reason": "tests fail\nfix them"},
        ),
        (Hook.STOP, allow("tests pass"), None),
        (Hook.SUBAGENT_STOP, block("incomplete"), {"decision": "block", "reason": "incomplete"}),
        (Hook.POST_TOOL, block("lint errors"), {"decision": "block", "reason": "lint errors"}),
        (Hook.USER_PROMPT, block("secret"), {"decision": "block", "reason": "secret"}),
        (
            Hook.SESSION_START,
            allow(context=["rule a", "rule b"]),
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "rule a\n\nrule b",
                }
            },
        ),
    ],
    ids=[
        "pre_tool_allow_gives_no_decision",
        "pre_tool_block_is_deny",
        "pre_tool_ask",
        "pre_tool_context",
        "stop_block",
        "stop_allow",
        "subagent_stop_block",
        "post_tool_block",
        "prompt_block",
        "session_start_context",
    ],
)
def test_result_is_rendered_in_claude_code_format(
    hook: Hook, result: ProcessResult, expected: Mapping[str, Any] | None
) -> None:
    assert ADAPTER.render(hook, result) == expected


def test_install_keeps_foreign_settings_and_replaces_its_own_entries() -> None:
    existing = {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "lint.sh"}]},
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "old/python -m agent_actions run checks.py --hook pre-tool",
                        }
                    ],
                },
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "py -m agent_actions run checks.py --hook stop",
                        }
                    ]
                }
            ],
        },
    }
    argv = (
        "py",
        "-m",
        "agent_actions",
        "run",
        "checks.py",
        "--harness",
        "claude",
        "--hook",
        "pre-tool",
    )

    merged = ADAPTER.merge_config(existing, {Hook.PRE_TOOL: argv}, "checks.py", 60)

    assert merged == {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "lint.sh"}]},
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "timeout": 60,
                            "command": "py -m agent_actions run checks.py --harness claude --hook pre-tool",
                        }
                    ],
                },
            ],
        },
    }


def test_install_keeps_entries_of_another_runner_file() -> None:
    other = {
        "hooks": [{"type": "command", "command": "py -m agent_actions run other.py --hook stop"}]
    }
    existing = {"hooks": {"Stop": [other]}}

    merged = ADAPTER.merge_config(existing, {}, "checks.py", 60)

    assert merged == existing
