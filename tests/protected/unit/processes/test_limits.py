import pytest
from builders import a_tool_event, an_event

from agent_actions.model import Hook, HookInput, ProcessResult, ToolKind, Verdict, allow, block
from agent_actions.process import StopProcess
from agent_actions.processes import LoopGuard, ToolCallBudget
from agent_actions.processes.limits import BUDGET_REASON, LOOP_ADVICE

STOP = an_event(Hook.STOP)


class ScriptedCheck(StopProcess):
    """Returns the scripted verdicts in order."""

    def __init__(self, *script: Verdict) -> None:
        self.script = script

    def __state__(self) -> None:
        self.calls = 0

    def run(self, event: HookInput) -> ProcessResult:
        verdict = self.script[self.calls]
        self.calls += 1
        return block("tests fail") if verdict is Verdict.BLOCK else allow("tests pass")


def guard_for(*script: Verdict, max_blocks: int = 2) -> LoopGuard:
    guard = LoopGuard(ScriptedCheck(*script), max_blocks=max_blocks)
    guard.load_state({})
    return guard


def test_blocks_pass_through_with_attempt_numbers_up_to_the_limit() -> None:
    guard = guard_for(Verdict.BLOCK, Verdict.BLOCK)

    first, second = guard.run(STOP), guard.run(STOP)

    assert first.reasons == ("tests fail", "Blocked stop 1 of 2.")
    assert second.reasons == ("tests fail", f"Blocked stop 2 of 2. {LOOP_ADVICE}")


def test_block_after_the_limit_allows_the_stop_and_resets_the_count() -> None:
    guard = guard_for(Verdict.BLOCK, Verdict.BLOCK, Verdict.BLOCK)

    results = [guard.run(STOP) for _ in range(3)]

    assert results[2] == allow("Allowed the stop after 2 blocked stops in a row.", "tests fail")
    assert guard.consecutive_blocks == 0


def test_an_allowed_stop_resets_the_count() -> None:
    guard = guard_for(Verdict.BLOCK, Verdict.ALLOW, Verdict.BLOCK)

    results = [guard.run(STOP) for _ in range(3)]

    assert results[2].reasons[-1] == "Blocked stop 1 of 2."


def test_state_includes_the_state_of_the_wrapped_process() -> None:
    guard = LoopGuard(ScriptedCheck(Verdict.BLOCK), max_blocks=2)
    guard.load_state({"consecutive_blocks": 1, "inner": {"calls": 0}})

    guard.run(STOP)

    assert guard.dump_state() == {"consecutive_blocks": 2, "inner": {"calls": 1}}


def test_guard_takes_hooks_and_name_from_the_wrapped_process() -> None:
    inner = ScriptedCheck(Verdict.ALLOW)
    inner.on = (Hook.SUBAGENT_STOP,)

    guard = LoopGuard(inner)

    assert (guard.hooks, guard.label) == ((Hook.SUBAGENT_STOP,), "LoopGuard(ScriptedCheck)")


def test_max_blocks_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_blocks must be 1 or more"):
        LoopGuard(ScriptedCheck(), max_blocks=0)


def test_budget_blocks_calls_after_the_maximum() -> None:
    budget = ToolCallBudget(2)
    budget.load_state({})
    event = a_tool_event("Read", ToolKind.READ, paths=["a.py"])

    results = [budget.run(event) for _ in range(3)]

    assert [result.verdict for result in results] == [Verdict.ALLOW, Verdict.ALLOW, Verdict.BLOCK]
    assert results[2].reasons == (f"The budget of 2 tool calls is used up. {BUDGET_REASON}",)


def test_budget_counts_only_the_selected_kinds() -> None:
    budget = ToolCallBudget(1, kinds=[ToolKind.SHELL])
    budget.load_state({})
    event = a_tool_event("Read", ToolKind.READ, paths=["a.py"])

    results = [budget.run(event) for _ in range(2)]

    assert [result.verdict for result in results] == [Verdict.ALLOW, Verdict.ALLOW]
    assert budget.calls == 0
