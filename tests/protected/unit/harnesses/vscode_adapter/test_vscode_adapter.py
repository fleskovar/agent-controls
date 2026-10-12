from agent_actions.harnesses.vscode import VSCodeAdapter
from agent_actions.model import Hook, ToolKind, allow, block

ADAPTER = VSCodeAdapter()


def test_camel_case_file_path_is_a_write_path() -> None:
    payload = {
        "timestamp": "2026-09-15T10:00:00.000Z",
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "replace_string_in_file",
        "tool_input": {"filePath": "src/app.py", "oldString": "a", "newString": "b"},
    }

    tool = ADAPTER.parse(Hook.PRE_TOOL, payload).tool

    assert tool is not None
    assert (tool.kind, tool.paths) == (ToolKind.WRITE, ("src/app.py",))


def test_apply_patch_file_headers_are_paths() -> None:
    patch = (
        "*** Begin Patch\n"
        "*** Update File: /repo/tests/test_a.py\n@@\n-a\n+b\n"
        "*** Add File: /repo/new.py\n+x\n"
        "*** End Patch"
    )
    payload = {"tool_name": "apply_patch", "tool_input": {"input": patch, "explanation": "fix"}}

    tool = ADAPTER.parse(Hook.PRE_TOOL, payload).tool

    assert tool is not None
    assert tool.paths == ("/repo/tests/test_a.py", "/repo/new.py")


def test_blocked_prompt_uses_the_common_output_format() -> None:
    assert ADAPTER.render(Hook.USER_PROMPT, block("no secrets in prompts")) == {
        "continue": False,
        "stopReason": "no secrets in prompts",
    }


def test_blocked_stop_uses_the_claude_code_format() -> None:
    assert ADAPTER.render(Hook.STOP, block("tests fail")) == {
        "decision": "block",
        "reason": "tests fail",
    }


def test_vscode_has_no_session_end_hook_and_no_prompt_context() -> None:
    assert Hook.SESSION_END not in ADAPTER.capabilities
    assert ADAPTER.capabilities[Hook.USER_PROMPT].context is False


def test_allow_on_pre_tool_gives_no_output() -> None:
    assert ADAPTER.render(Hook.PRE_TOOL, allow("fine")) is None


def test_install_writes_command_and_windows_variants() -> None:
    argv = (
        "C:/Program Files/py.exe",
        "-m",
        "agent_actions",
        "run",
        "checks.py",
        "--harness",
        "vscode",
        "--hook",
        "stop",
    )

    merged = ADAPTER.merge_config({}, {Hook.STOP: argv}, "checks.py", 30)

    assert merged == {
        "hooks": {
            "Stop": [
                {
                    "type": "command",
                    "command": "'C:/Program Files/py.exe' -m agent_actions run checks.py --harness vscode --hook stop",
                    "windows": "& 'C:/Program Files/py.exe' '-m' 'agent_actions' 'run' 'checks.py' '--harness' 'vscode' '--hook' 'stop'",
                    "timeout": 30,
                }
            ]
        }
    }
