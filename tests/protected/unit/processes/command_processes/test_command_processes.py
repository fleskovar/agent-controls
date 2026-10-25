import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from builders import a_tool_event, an_event

from agent_controls.harnesses import make_adapter
from agent_controls.model import Harness, Hook, ToolKind, allow, block
from agent_controls.processes import (
    CheckAfterEdit,
    CommandOutcome,
    RequireCommand,
    RequireTests,
    RunCommand,
    run_subprocess,
)
from agent_controls.processes.commands import (
    NOT_FOUND_EXIT_CODE,
    PYTEST_COMMAND,
    RUN_REASON,
    STOP_REASON,
    TESTS_REASON,
    Command,
    event_json,
    with_paths,
)
from agent_controls.runtime import compatibility_problems

STOP = an_event(Hook.STOP, cwd="/repo/src", root="/repo")


class FakeCommandRunner:
    """Returns prepared outcomes in order, and records each call and the last stdin text."""

    def __init__(self, *outcomes: CommandOutcome) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[Command, Path, float]] = []
        self.stdin = ""

    def __call__(self, command: Command, cwd: Path, timeout: float, stdin: str) -> CommandOutcome:
        self.calls.append((command, cwd, timeout))
        self.stdin = stdin
        return self.outcomes.pop(0)


def test_passing_command_allows_the_stop_and_runs_in_the_project_root() -> None:
    runner = FakeCommandRunner(CommandOutcome(0, "ok"))

    result = RequireCommand("ruff check .", command_runner=runner).run(STOP)

    assert result == allow("`ruff check .` passed.")
    assert runner.calls == [("ruff check .", Path("/repo"), 240.0)]


def test_failing_command_blocks_with_the_output_tail() -> None:
    runner = FakeCommandRunner(CommandOutcome(1, "xxxxxxxxxx2 errors"))

    result = RequireCommand(["ruff", "check"], max_output_chars=8, command_runner=runner).run(STOP)

    assert result == block(
        f"`ruff check` failed with exit code 1. {STOP_REASON}", "Output:\n...2 errors"
    )


def test_require_tests_runs_pytest_with_its_own_reason() -> None:
    runner = FakeCommandRunner(CommandOutcome(1, "1 failed"))
    process = RequireTests(command_runner=runner)

    result = process.run(STOP)

    assert runner.calls[0][0] == PYTEST_COMMAND
    assert TESTS_REASON in result.reasons[0]
    assert process.label == "RequireTests"


@pytest.mark.parametrize(
    ("command", "paths", "expected"),
    [
        ("ruff check {paths}", ["a b.py", "c.py"], "ruff check 'a b.py' c.py"),
        (["ruff", "check", "{paths}"], ["a.py", "c.py"], ["ruff", "check", "a.py", "c.py"]),
    ],
    ids=["string_is_quoted", "sequence_is_expanded"],
)
def test_paths_placeholder_is_replaced(
    command: Command, paths: Sequence[str], expected: Command
) -> None:
    assert with_paths(command, paths) == expected


def test_failed_check_after_an_edit_becomes_context() -> None:
    runner = FakeCommandRunner(CommandOutcome(1, "E501 line too long"))
    event = a_tool_event("Write", ToolKind.WRITE, paths=["src/a.py"], hook=Hook.POST_TOOL)

    result = CheckAfterEdit("ruff check {paths}", command_runner=runner).run(event)

    assert result == allow(
        context="`ruff check src/a.py` failed with exit code 1 after your edit. Fix these problems.\nE501 line too long"
    )


def test_edit_outside_the_patterns_runs_no_command() -> None:
    runner = FakeCommandRunner()
    event = a_tool_event("Write", ToolKind.WRITE, paths=["README.md"], hook=Hook.POST_TOOL)

    CheckAfterEdit("ruff check {paths}", patterns=["*.py"], command_runner=runner).run(event)

    assert runner.calls == []


def test_read_tool_runs_no_check() -> None:
    runner = FakeCommandRunner()
    event = a_tool_event("Read", ToolKind.READ, paths=["src/a.py"], hook=Hook.POST_TOOL)

    assert CheckAfterEdit("ruff check .", command_runner=runner).run(event) == allow()
    assert runner.calls == []


def test_command_gets_the_hook_event_as_json_on_stdin() -> None:
    runner = FakeCommandRunner(CommandOutcome(0, "ok"))

    RequireCommand("dotnet test", command_runner=runner).run(STOP)

    assert json.loads(runner.stdin) == STOP.to_record()


def test_failed_command_on_a_start_hook_becomes_context() -> None:
    runner = FakeCommandRunner(CommandOutcome(1, "Failed!  - Failed: 2, Passed: 7"))

    result = RunCommand("dotnet test", command_runner=runner).run(an_event(Hook.SESSION_START))

    assert result == allow(
        context=f"`dotnet test` failed with exit code 1. {RUN_REASON}\nFailed!  - Failed: 2, Passed: 7"
    )


def test_passed_command_on_a_start_hook_adds_no_context() -> None:
    runner = FakeCommandRunner(CommandOutcome(0, "Passed!"))

    result = RunCommand("dotnet test", command_runner=runner).run(an_event(Hook.SESSION_START))

    assert result == allow("`dotnet test` passed.")


def test_real_command_reads_the_event_on_stdin_and_answers_on_stdout(tmp_path: Path) -> None:
    script = "import json, sys; print('hook: ' + json.load(sys.stdin)['hook']); raise SystemExit(1)"
    event = an_event(Hook.SUBAGENT_START, cwd=str(tmp_path), root=str(tmp_path))

    result = RunCommand([sys.executable, "-c", script], reason="Note.").run(event)

    assert result.context[0].endswith("failed with exit code 1. Note.\nhook: subagent-start\n")


def test_check_after_an_edit_sends_the_tool_call_on_stdin() -> None:
    runner = FakeCommandRunner(CommandOutcome(0, "ok"))
    event = a_tool_event("Write", ToolKind.WRITE, paths=["src/Pricing.cs"], hook=Hook.POST_TOOL)

    CheckAfterEdit("dotnet test", command_runner=runner).run(event)

    sent = json.loads(runner.stdin)
    assert sent["hook"] == "post-tool"
    assert sent["tool"] == {
        "name": "Write",
        "kind": "write",
        "arguments": {},
        "paths": ["src/Pricing.cs"],
        "command": None,
        "output": None,
    }


def test_event_json_has_the_fields_of_the_event_without_the_raw_payload() -> None:
    event = an_event(Hook.STOP, agent_id="agent-1", last_message="Done.", raw={"hook": "Stop"})

    sent = json.loads(event_json(event))

    assert sent == {
        "harness": "claude",
        "hook": "stop",
        "session_id": "session-1",
        "cwd": "/repo",
        "root": "/repo",
        "agent_id": "agent-1",
        "agent_type": None,
        "tool": None,
        "prompt": None,
        "last_message": "Done.",
        "stop_hook_active": False,
    }


def test_run_command_runs_in_the_project_root_and_sends_the_event() -> None:
    runner = FakeCommandRunner(CommandOutcome(0, "ok"))
    event = an_event(Hook.SESSION_START, cwd="/repo/src", root="/repo")

    RunCommand(["dotnet", "test"], timeout=30.0, command_runner=runner).run(event)

    assert runner.calls == [(["dotnet", "test"], Path("/repo"), 30.0)]
    assert json.loads(runner.stdin) == event.to_record()


def test_run_command_gives_only_the_output_tail_with_its_own_reason() -> None:
    runner = FakeCommandRunner(CommandOutcome(2, "xxxxxxxxxx2 failed"))
    process = RunCommand(
        ["dotnet", "test"], reason="Fix them first.", max_output_chars=8, command_runner=runner
    )

    result = process.run(an_event(Hook.SUBAGENT_START))

    assert result == allow(
        context="`dotnet test` failed with exit code 2. Fix them first.\n...2 failed"
    )


def test_run_command_default_hook_is_session_start_and_on_replaces_it() -> None:
    assert RunCommand("dotnet test").hooks == (Hook.SESSION_START,)
    assert RunCommand("dotnet test", on=[Hook.SUBAGENT_START, Hook.POST_TOOL]).hooks == (
        Hook.SUBAGENT_START,
        Hook.POST_TOOL,
    )


@pytest.mark.parametrize(
    ("harness", "hook", "accepted"),
    [
        (Harness.CLAUDE, Hook.SESSION_START, True),
        (Harness.CLAUDE, Hook.SUBAGENT_START, True),
        (Harness.CLAUDE, Hook.USER_PROMPT, True),
        (Harness.CLAUDE, Hook.POST_TOOL, True),
        (Harness.CLAUDE, Hook.STOP, False),
        (Harness.CLAUDE, Hook.SUBAGENT_STOP, False),
        (Harness.VSCODE, Hook.SESSION_START, True),
        (Harness.COPILOT_CLI, Hook.POST_TOOL, True),
        (Harness.COPILOT_CLI, Hook.SESSION_START, False),
    ],
)
def test_run_command_is_accepted_only_on_hooks_with_a_context_channel(
    harness: Harness, hook: Hook, accepted: bool
) -> None:
    process = RunCommand("dotnet test", on=[hook])

    assert (compatibility_problems(process, make_adapter(harness)) == []) is accepted


def test_real_subprocess_gets_the_stdin_text(tmp_path: Path) -> None:
    script = "import sys; print(sys.stdin.read().upper())"

    outcome = run_subprocess([sys.executable, "-c", script], tmp_path, 60, "event")

    assert outcome == CommandOutcome(0, "EVENT\n")


def test_real_shell_command_gets_the_stdin_text(tmp_path: Path) -> None:
    command = f'"{sys.executable}" -c "import sys; print(sys.stdin.read().upper())"'

    outcome = run_subprocess(command, tmp_path, 60, "event")

    assert outcome == CommandOutcome(0, "EVENT\n")


def test_real_subprocess_without_stdin_text_reads_the_end_of_the_input(tmp_path: Path) -> None:
    """The command must not wait for input, and must not read the stdin of the hook."""
    script = "import sys; print(repr(sys.stdin.read()))"

    outcome = run_subprocess([sys.executable, "-c", script], tmp_path, 60)

    assert outcome == CommandOutcome(0, "''\n")


def test_real_subprocess_that_does_not_read_a_large_stdin_still_finishes(tmp_path: Path) -> None:
    """A test framework ignores stdin. A text above the pipe buffer must not block or fail."""
    outcome = run_subprocess([sys.executable, "-c", "print('done')"], tmp_path, 60, "x" * 1_000_000)

    assert outcome == CommandOutcome(0, "done\n")


def test_real_subprocess_reports_exit_code_and_output(tmp_path: Path) -> None:
    outcome = run_subprocess(
        [sys.executable, "-c", "print('hi'); raise SystemExit(3)"], tmp_path, 60
    )

    assert outcome == CommandOutcome(3, "hi\n")


def test_missing_program_reports_not_found(tmp_path: Path) -> None:
    outcome = run_subprocess(["agent-controls-no-such-program"], tmp_path, 60)

    assert outcome.exit_code == NOT_FOUND_EXIT_CODE
