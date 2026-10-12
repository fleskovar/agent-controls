from pathlib import Path

import pytest

from agent_actions.errors import IncompatibleProcessError, RunnerFileError
from agent_actions.harnesses import make_adapter
from agent_actions.model import Harness, Hook, HookInput, ProcessResult, allow, ask
from agent_actions.process import PreToolProcess, PromptProcess, StartProcess, StopProcess
from agent_actions.processes import AddContext
from agent_actions.runtime import Context, get_current_context, load_runner, log


class StopCheck(StopProcess):
    def run(self, event: HookInput) -> ProcessResult:
        return allow()


class AskingGuard(PreToolProcess):
    def run(self, event: HookInput) -> ProcessResult:
        return ask("Are you sure?")


class Greeting(StartProcess):
    on = (Hook.SUBAGENT_START,)

    def run(self, event: HookInput) -> ProcessResult:
        return allow()


class PromptFilter(PromptProcess):
    def run(self, event: HookInput) -> ProcessResult:
        return allow()


def context_for(harness: Harness, hook: Hook | None = None) -> Context:
    return Context(make_adapter(harness), hook, None)


def test_process_on_a_hook_outside_its_family_is_rejected() -> None:
    process = StopCheck()
    process.on = (Hook.PRE_TOOL,)

    with pytest.raises(IncompatibleProcessError, match="'pre-tool' is not a hook of StopCheck"):
        context_for(Harness.CLAUDE).add(process)


def test_process_on_a_hook_the_harness_lacks_is_rejected() -> None:
    with pytest.raises(
        IncompatibleProcessError, match="harness 'copilot-cli' has no 'subagent-start' hook"
    ):
        context_for(Harness.COPILOT_CLI).add(Greeting())


def test_declared_verdict_the_hook_cannot_deliver_is_rejected() -> None:
    with pytest.raises(
        IncompatibleProcessError, match="'user-prompt' cannot deliver the verdicts block"
    ):
        context_for(Harness.COPILOT_CLI).add(PromptFilter())


def test_context_process_on_a_hook_without_context_channel_is_rejected() -> None:
    with pytest.raises(IncompatibleProcessError, match="'stop' has no channel for context"):
        context_for(Harness.CLAUDE).add(AddContext("rules", on=[Hook.STOP]))


def test_two_processes_with_the_same_name_are_rejected() -> None:
    context = context_for(Harness.CLAUDE).add(StopCheck())

    with pytest.raises(IncompatibleProcessError, match="another process is named 'StopCheck'"):
        context.add(StopCheck())


def test_active_processes_are_those_attached_to_the_current_hook() -> None:
    stop_check = StopCheck()
    context = context_for(Harness.CLAUDE, Hook.STOP).add(AskingGuard()).add(stop_check)

    assert context.active() == (stop_check,)


def test_hooks_are_listed_in_lifecycle_order() -> None:
    context = context_for(Harness.CLAUDE).add(StopCheck()).add(AskingGuard())

    assert context.hooks() == (Hook.PRE_TOOL, Hook.STOP)


def test_context_outside_a_hook_call_explains_how_to_start() -> None:
    with pytest.raises(RunnerFileError, match="agent_actions run"):
        get_current_context()


def test_log_outside_a_run_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    log("hello")

    assert capsys.readouterr().err == "[runner] hello\n"


def test_runner_file_that_does_not_call_run_is_an_error(tmp_path: Path) -> None:
    runner = tmp_path / "checks.py"
    runner.write_text("import agent_actions as aa\naa.get_current_context()\n")

    with pytest.raises(RunnerFileError, match=r"did not call agent_actions\.run\(context\)"):
        load_runner(runner, make_adapter(Harness.CLAUDE), Hook.STOP, None)


def test_runner_file_exception_is_reported_with_its_type(tmp_path: Path) -> None:
    runner = tmp_path / "checks.py"
    runner.write_text("raise KeyError('threshold')\n")

    with pytest.raises(RunnerFileError, match="failed: KeyError"):
        load_runner(runner, make_adapter(Harness.CLAUDE), Hook.STOP, None)


def test_missing_runner_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RunnerFileError, match="does not exist"):
        load_runner(tmp_path / "missing.py", make_adapter(Harness.CLAUDE), Hook.STOP, None)


def test_runner_file_imports_modules_next_to_it(tmp_path: Path) -> None:
    (tmp_path / "local_rules_module.py").write_text(
        "from agent_actions import StopProcess, allow\n\n"
        "class LocalCheck(StopProcess):\n"
        "    def run(self, event):\n"
        "        return allow()\n"
    )
    runner = tmp_path / "checks.py"
    runner.write_text(
        "import agent_actions as aa\n"
        "from local_rules_module import LocalCheck\n"
        "context = aa.get_current_context()\n"
        "context.add(LocalCheck())\n"
        "aa.run(context)\n"
    )

    context = load_runner(runner, make_adapter(Harness.CLAUDE), Hook.STOP, None)

    assert [process.label for process in context.processes] == ["LocalCheck"]
