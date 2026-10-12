"""Flags and `when` conditions: state that outlives a hook call and a session."""

import json
from pathlib import Path
from typing import Any

import git
import pytest
from builders import an_event

from agent_actions.app import install_hooks, run_hook
from agent_actions.engine import execute
from agent_actions.errors import StateError
from agent_actions.harnesses import make_adapter
from agent_actions.model import Harness, Hook, HookInput, ProcessResult, Verdict, allow, block
from agent_actions.process import StopProcess
from agent_actions.processes import (
    CommandOutcome,
    SetFlag,
    changed_paths,
    clear_on_pass,
    git_snapshot,
    on_changed_paths,
)
from agent_actions.processes.commands import Command
from agent_actions.runtime import Context
from agent_actions.session import FlagFile

CLAUDE = make_adapter(Harness.CLAUDE)
STOP = an_event(Hook.STOP)


class Refuse(StopProcess):
    def __state__(self) -> None:
        self.runs = 0

    def run(self, event: HookInput) -> ProcessResult:
        self.runs += 1
        return block("not yet")


# --- when: a condition on a process ---------------------------------------------------


def test_process_with_a_false_condition_does_not_run_and_gets_no_record() -> None:
    process = Refuse()
    process.when = lambda event: False

    step = execute([process], STOP, CLAUDE.capabilities[Hook.STOP], {})

    assert step.result.verdict is Verdict.ALLOW
    assert step.records == ()
    assert step.log_lines == ("[Refuse] skipped: its `when` condition is false",)


def test_condition_gets_the_event_and_a_true_answer_runs_the_process() -> None:
    process = Refuse()
    process.when = lambda event: event.hook is Hook.STOP

    step = execute([process], STOP, CLAUDE.capabilities[Hook.STOP], {})

    assert step.result.reasons == ("[Refuse] not yet",)
    assert step.records[0].state == {"runs": 1}


def test_condition_sees_a_flag_that_an_earlier_process_set_in_the_same_call() -> None:
    flags: dict[str, Any] = {}
    setter = SetFlag(flags, "tests-due", on=[Hook.STOP])
    gated = Refuse()
    gated.when = lambda event: flags.get("tests-due")

    step = execute([setter, gated], STOP, CLAUDE.capabilities[Hook.STOP], {})

    assert step.result.verdict is Verdict.BLOCK


def test_condition_that_raises_blocks_where_block_is_possible() -> None:
    flags: dict[str, Any] = {}
    process = Refuse()
    process.when = lambda event: flags["missing"]

    step = execute([process], STOP, CLAUDE.capabilities[Hook.STOP], {})

    assert step.result.verdict is Verdict.BLOCK
    assert "KeyError" in step.result.reasons[0]


def test_add_with_a_condition_keeps_the_hook_of_the_process() -> None:
    context = Context(CLAUDE, None, None)

    context.add(Refuse(), when=lambda event: False)

    assert context.hooks() == (Hook.STOP,)
    assert context.processes[0].when is not None
    assert context.flags == {} and context.session_flags == {}


# --- FlagFile: one flags.json ---------------------------------------------------------


def test_only_the_changed_flags_are_written_so_a_parallel_change_survives(tmp_path: Path) -> None:
    path = tmp_path / "flags.json"
    path.write_text('{"a": 1, "b": 2, "c": 3}', encoding="utf-8")
    file = FlagFile(path, tmp_path / ".lock")
    path.write_text('{"a": 1, "b": 20, "c": 3, "d": 4}', encoding="utf-8")  # another hook call

    file.flags["a"] = [1]
    del file.flags["c"]
    file.flags["e"] = {"nested": True}

    assert file.save() == ["a", "c", "e"]
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "a": [1],
        "b": 20,
        "d": 4,
        "e": {"nested": True},
    }


def test_change_inside_a_flag_value_is_saved(tmp_path: Path) -> None:
    path = tmp_path / "flags.json"
    path.write_text('{"seen": ["a.py"]}', encoding="utf-8")
    file = FlagFile(path, tmp_path / ".lock")

    file.flags["seen"].append("b.py")

    assert file.save() == ["seen"]
    assert json.loads(path.read_text(encoding="utf-8")) == {"seen": ["a.py", "b.py"]}


def test_no_change_writes_no_file(tmp_path: Path) -> None:
    file = FlagFile(tmp_path / "flags.json", tmp_path / ".lock")

    assert file.save() == []
    assert not (tmp_path / "flags.json").exists()


def test_flag_that_is_not_json_is_an_error_and_keeps_the_file(tmp_path: Path) -> None:
    path = tmp_path / "flags.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    file = FlagFile(path, tmp_path / ".lock")
    file.flags["bad"] = {1, 2}

    with pytest.raises(StateError, match=r"A flag of bad in .* is not JSON-serializable"):
        file.save()

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


# --- SetFlag --------------------------------------------------------------------------


def test_set_flag_sets_true_by_default_and_names_itself_after_the_flag() -> None:
    flags: dict[str, Any] = {}
    process = SetFlag(flags, "tests-due")

    assert process.run(an_event(Hook.SESSION_START)) == allow("Set the flag 'tests-due'.")
    assert flags == {"tests-due": True}
    assert process.label == "SetFlag(tests-due)"
    assert process.hooks == (Hook.SESSION_START,)


def test_set_flag_calls_a_function_value_with_the_event() -> None:
    flags: dict[str, Any] = {}

    SetFlag(flags, "hook", lambda event: event.hook.value).run(an_event(Hook.USER_PROMPT))

    assert flags == {"hook": "user-prompt"}


def test_set_flag_with_keep_does_not_replace_a_value() -> None:
    flags: dict[str, Any] = {"baseline": "first"}

    result = SetFlag(flags, "baseline", "second", keep=True).run(an_event(Hook.SESSION_START))

    assert result == allow("Kept the flag 'baseline'.")
    assert flags == {"baseline": "first"}


# --- git snapshot: what changed after a baseline --------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> git.Repo:
    """A repository with one commit of five source files."""
    repo = git.Repo.init(tmp_path)
    (tmp_path / "src").mkdir()
    names = [f"src/{name}.py" for name in ("kept", "edited", "deleted", "dirty", "restored")]
    for name in names:
        (tmp_path / name).write_text("original\n")
    repo.index.add(names)
    repo.index.commit("first")
    return repo


def event_in(root: Path) -> HookInput:
    return an_event(Hook.SESSION_START, cwd=str(root), root=str(root))


def test_changed_paths_lists_only_the_content_that_changed_after_the_snapshot(
    repo: git.Repo, tmp_path: Path
) -> None:
    # Before the snapshot: the work of the user, which is not committed.
    (tmp_path / "src/dirty.py").write_text("work of the user\n")
    (tmp_path / "src/restored.py").write_text("work of the user\n")
    (tmp_path / "notes.txt").write_text("untracked\n")
    snapshot = json.loads(json.dumps(git_snapshot(event_in(tmp_path))))  # as flags.json keeps it

    (tmp_path / "src/edited.py").write_text("changed\n")
    (tmp_path / "src/deleted.py").unlink()
    (tmp_path / "src/restored.py").write_text("original\n")
    (tmp_path / "src/new.py").write_text("new\n")
    (tmp_path / "README.md").write_text("new\n")
    repo.index.add(["src/dirty.py"])
    repo.index.commit("the user commits unchanged work")

    assert changed_paths(tmp_path, snapshot) == [
        "README.md",
        "src/deleted.py",
        "src/edited.py",
        "src/new.py",
        "src/restored.py",
    ]
    assert changed_paths(tmp_path, snapshot, ["*.md", "src/new.py"]) == ["README.md", "src/new.py"]


def test_change_that_is_committed_after_the_snapshot_is_in_the_list(
    repo: git.Repo, tmp_path: Path
) -> None:
    snapshot = git_snapshot(event_in(tmp_path))
    (tmp_path / "src/edited.py").write_text("changed\n")
    repo.index.add(["src/edited.py"])
    repo.index.commit("second")

    assert changed_paths(tmp_path, snapshot) == ["src/edited.py"]


def test_without_a_snapshot_each_uncommitted_change_is_in_the_list(
    repo: git.Repo, tmp_path: Path
) -> None:
    (tmp_path / "src/edited.py").write_text("changed\n")
    (tmp_path / "src/new.py").write_text("new\n")

    assert changed_paths(tmp_path, None) == ["src/edited.py", "src/new.py"]


def test_paths_are_relative_to_a_project_root_below_the_repository(
    repo: git.Repo, tmp_path: Path
) -> None:
    (tmp_path / "src/edited.py").write_text("changed\n")
    (tmp_path / "outside.txt").write_text("new\n")

    assert changed_paths(tmp_path / "src", None) == ["edited.py"]


def recorder(calls: list[Command], exit_code: int = 0) -> Any:
    def run(command: Command, cwd: Path, timeout: float, stdin: str) -> CommandOutcome:
        calls.append(command)
        return CommandOutcome(exit_code, "output")

    return run


def test_command_runs_on_the_changed_files_that_exist(repo: git.Repo, tmp_path: Path) -> None:
    flags = {"baseline": git_snapshot(event_in(tmp_path))}
    (tmp_path / "src/edited.py").write_text("changed\n")
    (tmp_path / "src/deleted.py").unlink()
    (tmp_path / "README.md").write_text("new\n")
    calls: list[Command] = []
    runner = on_changed_paths(flags, ["*.py"], command_runner=recorder(calls, exit_code=1))

    outcome = runner(["ruff", "check", "{paths}"], tmp_path, 10.0, "")

    assert calls == [["ruff", "check", "src/edited.py"]]
    assert outcome == CommandOutcome(1, "output")


def test_command_does_not_run_and_passes_when_no_file_changed(
    repo: git.Repo, tmp_path: Path
) -> None:
    flags = {"baseline": git_snapshot(event_in(tmp_path))}
    calls: list[Command] = []

    outcome = on_changed_paths(flags, command_runner=recorder(calls))("ruff {paths}", tmp_path, 1.0)

    assert calls == []
    assert outcome.exit_code == 0


# --- clear_on_pass --------------------------------------------------------------------


def test_pass_deletes_the_flag_and_a_failure_keeps_it(tmp_path: Path) -> None:
    flags: dict[str, Any] = {"tests-due": True}

    failed = clear_on_pass(flags, "tests-due", command_runner=recorder([], 1))("t", tmp_path, 1.0)
    assert failed.exit_code == 1
    assert flags == {"tests-due": True}

    passed = clear_on_pass(flags, "tests-due", command_runner=recorder([]))("t", tmp_path, 1.0)
    assert passed.exit_code == 0
    assert flags == {}


# --- end to end: a flag from one session starts a guardrail in the next ---------------

RUNNER = """\
import agent_actions as aa
from agent_actions.processes import CommandOutcome, RequireCommand, SetFlag, clear_on_pass

context = aa.get_current_context()
flags, session = context.flags, context.session_flags


def tests(command, cwd, timeout, stdin):
    return CommandOutcome(0 if (cwd / "fixed").exists() else 1, "1 failed")


context.add(SetFlag(session, "first-hook", lambda event: event.hook.value, keep=True,
                    on=[aa.Hook.POST_TOOL, aa.Hook.STOP]))
context.add(SetFlag(flags, "tests-due", on=[aa.Hook.POST_TOOL]),
            when=lambda event: event.tool.kind is aa.ToolKind.WRITE)
context.add(
    RequireCommand("run-tests", name="tests",
                   command_runner=clear_on_pass(flags, "tests-due", command_runner=tests)),
    when=lambda event: flags.get("tests-due"),
)
aa.run(context)
"""
EDIT = '{"session_id": "%s", "tool_name": "Edit", "tool_input": {"file_path": "src/a.py"}}'
READ = '{"session_id": "%s", "tool_name": "Read", "tool_input": {"file_path": "src/a.py"}}'


def call(root: Path, hook: Hook, payload: str) -> dict[str, Any] | None:
    response = run_hook(root, Path("checks.py"), Harness.CLAUDE, hook, payload)
    assert response.exit_code == 0, response.stderr
    return None if response.stdout is None else dict(response.stdout)


def flag_file(root: Path, pattern: str) -> dict[str, Any]:
    [path] = root.glob(pattern)
    return json.loads(path.read_text(encoding="utf-8"))


def test_flag_from_one_session_starts_the_guardrail_in_the_next_session(tmp_path: Path) -> None:
    (tmp_path / "checks.py").write_text(RUNNER, encoding="utf-8")

    # Session 1: a read sets no flag, and the stop is free. Then an edit sets the flag.
    assert call(tmp_path, Hook.POST_TOOL, READ % "one") is None
    assert call(tmp_path, Hook.STOP, '{"session_id": "one"}') is None
    assert call(tmp_path, Hook.POST_TOOL, EDIT % "one") is None
    assert flag_file(tmp_path, ".hooks/flags.json") == {"tests-due": True}

    # Session 2 changes nothing, and its stop is blocked: the flag is from session 1.
    blocked = call(tmp_path, Hook.STOP, '{"session_id": "two"}')
    assert blocked is not None and blocked["decision"] == "block"
    assert "`run-tests` failed" in blocked["reason"]

    # The tests pass: the stop is free, and the flag is gone for all sessions.
    (tmp_path / "fixed").touch()
    assert call(tmp_path, Hook.STOP, '{"session_id": "two"}') is None
    assert flag_file(tmp_path, ".hooks/flags.json") == {}
    assert call(tmp_path, Hook.STOP, '{"session_id": "three"}') is None

    # Each session has its own session flags.
    assert flag_file(tmp_path, ".hooks/*_one/flags.json") == {"first-hook": "post-tool"}
    assert flag_file(tmp_path, ".hooks/*_two/flags.json") == {"first-hook": "stop"}
    # The log tells why a guardrail ran or did not run.
    [log_two] = tmp_path.glob(".hooks/*_two/main-agent/log.txt")
    [log_three] = tmp_path.glob(".hooks/*_three/main-agent/log.txt")
    assert "[agent_actions] changed project flags: tests-due" in log_two.read_text("utf-8")
    assert "[tests] skipped: its `when` condition is false" in log_three.read_text("utf-8")


def test_install_registers_the_hook_of_a_process_that_has_a_condition(tmp_path: Path) -> None:
    (tmp_path / "checks.py").write_text(RUNNER, encoding="utf-8")

    report = install_hooks(tmp_path, Path("checks.py"), Harness.CLAUDE, "python")

    assert report.hooks == (Hook.POST_TOOL, Hook.STOP)


def test_flag_that_is_not_json_fails_the_hook_call_loudly(tmp_path: Path) -> None:
    (tmp_path / "checks.py").write_text(
        "import agent_actions as aa\n"
        "from agent_actions.processes import SetFlag\n"
        "context = aa.get_current_context()\n"
        "context.add(SetFlag(context.flags, 'bad', {1, 2}, on=[aa.Hook.STOP]))\n"
        "aa.run(context)\n",
        encoding="utf-8",
    )

    response = run_hook(tmp_path, Path("checks.py"), Harness.CLAUDE, Hook.STOP, "{}")

    assert response.exit_code == 1
    assert "is not JSON-serializable" in response.stderr
    assert not (tmp_path / ".hooks/flags.json").exists()
