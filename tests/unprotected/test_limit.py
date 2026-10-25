"""Limit: a wrapper that changes the verdict of any process after a maximum of results."""

import pytest
from builders import a_tool_event, an_event

from agent_controls.errors import IncompatibleProcessError
from agent_controls.harnesses import make_adapter
from agent_controls.model import (
    Harness,
    Hook,
    HookInput,
    ProcessResult,
    ToolKind,
    Verdict,
    allow,
    block,
)
from agent_controls.process import StopProcess
from agent_controls.processes import BlockWrites, Limit
from agent_controls.processes.limits import LIMIT_ADVICE, RESET_REASON, problem_text
from agent_controls.runtime import Context

STOP = an_event(Hook.STOP)
PROMPT = an_event(Hook.USER_PROMPT, prompt="try X")
FAIL, PASS = Verdict.BLOCK, Verdict.ALLOW


class Scripted(StopProcess):
    """Returns the scripted verdicts in order."""

    def __init__(self, *script: Verdict) -> None:
        self.script = script

    def __state__(self) -> None:
        self.calls = 0

    def run(self, event: HookInput) -> ProcessResult:
        verdict = self.script[self.calls]
        self.calls += 1
        return block("tests fail") if verdict is FAIL else allow("tests pass")


def results(limit: Limit, calls: int, event: HookInput = STOP) -> list[ProcessResult]:
    limit.load_state({})
    return [limit.run(event) for _ in range(calls)]


def test_in_a_row_warns_at_the_maximum_releases_after_it_and_starts_again() -> None:
    limit = Limit(Scripted(FAIL, FAIL, FAIL, FAIL), max_in_a_row=2)

    first, second, third, fourth = results(limit, 4)

    assert first == block("tests fail", "Count: 1 of 2 in a row.")
    assert second == block("tests fail", "Count: 2 of 2 in a row.", LIMIT_ADVICE[Verdict.ALLOW])
    assert third == allow(
        "The limit of 2 in a row is used up.", LIMIT_ADVICE[Verdict.ALLOW], "tests fail"
    )
    assert fourth.reasons[-1] == "Count: 1 of 2 in a row."


def test_a_pass_resets_the_count_in_a_row_but_not_the_total() -> None:
    limit = Limit(Scripted(FAIL, PASS, FAIL, FAIL), max_in_a_row=2, max_total=2)

    outcomes = results(limit, 4)

    assert [result.verdict for result in outcomes] == [FAIL, PASS, FAIL, PASS]
    assert outcomes[3].reasons[0] == "The limit of 2 in total is used up."
    assert (limit.in_a_row, limit.total) == (0, 3)


def test_after_the_total_each_counted_result_gets_the_exit_verdict() -> None:
    limit = Limit(Scripted(FAIL, FAIL, PASS, FAIL), max_total=1)

    verdicts = [result.verdict for result in results(limit, 4)]

    assert verdicts == [FAIL, PASS, PASS, PASS]


def test_block_as_exit_never_releases_and_gives_the_new_message() -> None:
    limit = Limit(Scripted(FAIL, FAIL), max_in_a_row=1, then=Verdict.BLOCK, message="Ask the user.")

    _, second = results(limit, 2)

    assert second == block("The limit of 1 in a row is used up.", "Ask the user.", "tests fail")


def test_ask_as_exit_on_pre_tool_lets_the_user_decide() -> None:
    limit = Limit(BlockWrites(["migrations/**"]), max_in_a_row=1, then=Verdict.ASK)
    edit = a_tool_event("Edit", ToolKind.WRITE, paths=["migrations/0001.sql"])

    verdicts = [result.verdict for result in results(limit, 4, edit)]

    assert verdicts == [Verdict.BLOCK, Verdict.ASK, Verdict.BLOCK, Verdict.ASK]


def test_counts_selects_the_results_to_count() -> None:
    limit = Limit(Scripted(PASS, PASS), max_in_a_row=1, counts=lambda result: True)

    first, second = results(limit, 2)

    assert first.reasons[1:] == ("Count: 1 of 1 in a row.", LIMIT_ADVICE[Verdict.ALLOW])
    assert second.reasons[0] == "The limit of 1 in a row is used up."


def test_a_release_sets_the_flag() -> None:
    flags: dict[str, object] = {}
    limit = Limit(Scripted(FAIL, FAIL), max_in_a_row=1, flags=flags, flag="needs-review")

    results(limit, 2)

    assert flags == {"needs-review": True}


def test_state_includes_the_state_of_the_wrapped_process() -> None:
    limit = Limit(Scripted(FAIL), max_in_a_row=3, max_total=9)
    limit.load_state({"in_a_row": 1, "total": 4, "inner": {"calls": 0}})

    limit.run(STOP)

    assert limit.dump_state() == {
        "in_a_row": 2,
        "total": 5,
        "problem_id": "",
        "times": [],
        "inner": {"calls": 1},
    }


def test_limit_takes_hooks_name_and_verdicts_from_the_wrapped_process() -> None:
    inner = Scripted()
    inner.on = (Hook.SUBAGENT_STOP,)

    limit = Limit(inner, max_in_a_row=1)

    assert (limit.hooks, limit.label) == ((Hook.SUBAGENT_STOP,), "Limit(Scripted)")
    assert limit.family == inner.family
    assert limit.needs(Hook.SUBAGENT_STOP) == inner.needs(Hook.SUBAGENT_STOP)


def test_context_rejects_an_exit_verdict_that_the_hook_cannot_deliver() -> None:
    context = Context(make_adapter(Harness.CLAUDE), None, None)

    context.add(Limit(BlockWrites(["a"]), max_in_a_row=1, then=Verdict.ASK))
    with pytest.raises(IncompatibleProcessError, match="cannot deliver the verdicts ask"):
        context.add(Limit(Scripted(), max_in_a_row=1, then=Verdict.ASK))


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "Give max_in_a_row, max_total or both"),
        ({"max_in_a_row": 0}, "each 1 or more"),
        ({"max_total": 1, "flag": "x"}, "Give `flags` and `flag` together"),
        ({"max_in_a_row": 1, "window": 60}, "`window` needs `max_total`"),
        ({"max_total": 1, "window": 0}, "more than 0 seconds"),
    ],
)
def test_bad_options_are_rejected(options: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Limit(Scripted(), **options)


# --- reset_on: a new prompt is a new problem ------------------------------------------


def test_a_reset_hook_resets_the_count_in_a_row_and_only_allows() -> None:
    limit = Limit(Scripted(FAIL, FAIL), max_in_a_row=2, max_total=9, reset_on=[Hook.USER_PROMPT])
    limit.load_state({})

    limit.run(STOP)
    reset = limit.run(PROMPT)
    second = limit.run(STOP)

    assert reset == allow(RESET_REASON)
    assert second.reasons[-1] == "Count: 1 of 2 in a row, 2 of 9 in total."
    assert limit.hooks == (Hook.STOP, Hook.USER_PROMPT)
    assert limit.needs(Hook.USER_PROMPT).verdicts == {Verdict.ALLOW}


def test_a_reset_hook_accepts_an_exit_that_only_the_wrapped_hook_delivers() -> None:
    claude = Context(make_adapter(Harness.CLAUDE), None, None)
    copilot = Context(make_adapter(Harness.COPILOT_CLI), None, None)
    guard = BlockWrites(["a"])

    claude.add(Limit(guard, max_in_a_row=1, then=Verdict.ASK, reset_on=[Hook.USER_PROMPT]))
    copilot.add(Limit(Scripted(), max_in_a_row=1, reset_on=[Hook.USER_PROMPT]))

    assert claude.hooks() == (Hook.USER_PROMPT, Hook.PRE_TOOL)


# --- problem: count only the same problem in a row -------------------------------------


class Failing(StopProcess):
    """Blocks with the scripted reasons in order."""

    def __init__(self, *reasons: str) -> None:
        self.reasons = reasons

    def __state__(self) -> None:
        self.calls = 0

    def run(self, event: HookInput) -> ProcessResult:
        self.calls += 1
        return block(self.reasons[self.calls - 1])


def test_a_new_problem_starts_the_count_in_a_row_again() -> None:
    outputs = ("FAILED test_a in 0.51s", "FAILED test_a in 0.73s", "FAILED test_b in 0.70s")
    limit = Limit(Failing(*outputs), max_in_a_row=3, max_total=9, problem=problem_text)

    counts = [result.reasons[-1] for result in results(limit, 3)]

    assert counts == [
        "Count: 1 of 3 in a row, 1 of 9 in total.",
        "Count: 2 of 3 in a row, 2 of 9 in total.",
        "Count: 1 of 3 in a row, 3 of 9 in total.",
    ]


def test_problem_text_ignores_numbers_and_addresses() -> None:
    first = block("2 failed in 0.51s", "<Mock at 0x7f3a2b>")
    second = block("3 failed in 1.20s", "<Mock at 0x9c1d00>")

    assert problem_text(first) == problem_text(second) == "# failed in #.#s\n<Mock at #>"


# --- window: a maximum per period -------------------------------------------------------


def test_window_counts_only_the_recent_results() -> None:
    now = [0.0]
    limit = Limit(Scripted(*[FAIL] * 4), max_total=2, window=60, clock=lambda: now[0])
    limit.load_state({})

    verdicts = []
    for moment in (0.0, 30.0, 100.0, 110.0):
        now[0] = moment
        verdicts.append(limit.run(STOP).verdict)

    assert verdicts == [FAIL, FAIL, FAIL, FAIL]
    assert limit.times == [100.0, 110.0]
    now[0] = 120.0
    limit.process = Scripted(FAIL)
    limit.process.load_state({})
    assert limit.run(STOP).reasons[0] == "The limit of 2 in the last 60 s is used up."


# --- store: counts that agents and sessions share --------------------------------------


def test_a_store_shares_the_counts_and_a_deleted_flag_resets_them() -> None:
    store: dict[str, object] = {}
    main, subagent = (
        Limit(Scripted(FAIL), max_total=1, store=store, name="tests") for _ in range(2)
    )
    for limit in (main, subagent):
        limit.load_state({})

    main.run(STOP)
    released = subagent.run(STOP)

    assert released.verdict is PASS
    assert store["tests"] == {"in_a_row": 0, "total": 2, "problem_id": "", "times": []}

    del store["tests"]
    subagent.process = Scripted(FAIL)
    subagent.process.load_state({})
    assert subagent.run(STOP).reasons[-2] == "Count: 1 of 1 in total."
