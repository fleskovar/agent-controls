import pytest
from builders import an_event

from agent_actions.engine import execute
from agent_actions.errors import IncompatibleResultError, ProcessFailedError
from agent_actions.harnesses import make_adapter
from agent_actions.model import Harness, Hook, HookInput, ProcessResult, Verdict, allow, ask, block
from agent_actions.process import ANY_VERDICT, StartProcess, StopProcess
from agent_actions.runtime import log

CLAUDE = make_adapter(Harness.CLAUDE).capabilities
STOP = an_event(Hook.STOP)


class Counter(StopProcess):
    def __state__(self) -> None:
        self.runs = 0

    def run(self, event: HookInput) -> ProcessResult:
        self.runs += 1
        log(f"run {self.runs}")
        return block("again") if self.runs < 3 else allow("done")


class Broken(StopProcess):
    def run(self, event: HookInput) -> ProcessResult:
        raise RuntimeError("disk full")


class BrokenStart(StartProcess):
    def run(self, event: HookInput) -> ProcessResult:
        raise RuntimeError("no rules file")


class AskOnStop(StopProcess):
    verdicts = ANY_VERDICT

    def run(self, event: HookInput) -> ProcessResult:
        return ask("Stop now?")


class LyingAskOnStop(StopProcess):
    def run(self, event: HookInput) -> ProcessResult:
        return ask("Stop now?")


class ContextOnStop(StopProcess):
    def run(self, event: HookInput) -> ProcessResult:
        return allow(context="hint")


def test_state_is_restored_before_the_run_and_recorded_after() -> None:
    step = execute([Counter()], STOP, CLAUDE[Hook.STOP], {"Counter": {"runs": 1}})

    assert step.records[0].state == {"runs": 2}
    assert step.result.reasons == ("[Counter] again",)


def test_log_lines_carry_the_process_name_and_a_result_summary() -> None:
    step = execute([Counter()], STOP, CLAUDE[Hook.STOP], {})

    assert step.log_lines == ("[Counter] run 1", "[Counter] block: again")


def test_record_holds_the_inputs_and_the_outputs() -> None:
    step = execute([Counter()], STOP, CLAUDE[Hook.STOP], {"Counter": {"runs": 2}})

    record = step.records[0]
    assert record.inputs["hook"] == "stop"
    assert record.outputs == {"verdict": Verdict.ALLOW, "reasons": ("done",), "context": ()}


def test_exception_blocks_where_block_is_possible() -> None:
    step = execute([Broken()], STOP, CLAUDE[Hook.STOP], {})

    assert step.result.verdict is Verdict.BLOCK
    assert "RuntimeError: disk full" in step.result.reasons[0]
    assert "Traceback" in step.log_lines[0]


def test_exception_on_a_hook_that_cannot_block_fails_the_run() -> None:
    event = an_event(Hook.SESSION_START)

    with pytest.raises(ProcessFailedError, match="Process 'BrokenStart' failed on 'session-start'"):
        execute([BrokenStart()], event, CLAUDE[Hook.SESSION_START], {})


@pytest.mark.parametrize("process", [AskOnStop(), LyingAskOnStop()], ids=["declared", "undeclared"])
def test_verdict_the_hook_cannot_deliver_fails_the_run(process: StopProcess) -> None:
    with pytest.raises(
        IncompatibleResultError,
        match="returned 'ask' on 'stop' for harness 'claude', but only allow, block",
    ):
        execute([process], STOP, CLAUDE[Hook.STOP], {})


def test_context_on_a_hook_without_channel_fails_the_run() -> None:
    with pytest.raises(IncompatibleResultError, match="returned context on 'stop'"):
        execute([ContextOnStop()], STOP, CLAUDE[Hook.STOP], {})


def test_no_active_processes_allow() -> None:
    step = execute([], STOP, CLAUDE[Hook.STOP], {})

    assert (step.result, step.records) == (allow(), ())
