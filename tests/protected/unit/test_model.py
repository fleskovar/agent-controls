import pytest

from agent_actions.model import (
    Harness,
    Hook,
    HookInput,
    NamedResult,
    ProcessResult,
    Verdict,
    allow,
    ask,
    block,
    combine,
)


@pytest.mark.parametrize("verdict", [Verdict.BLOCK, Verdict.ASK], ids=["block", "ask"])
def test_restrictive_result_without_reason_is_rejected(verdict: Verdict) -> None:
    with pytest.raises(ValueError, match="needs at least one reason for the agent"):
        ProcessResult(verdict)


def test_allow_without_reason_is_valid() -> None:
    assert allow() == ProcessResult(Verdict.ALLOW, (), ())


def test_context_given_as_one_string_stays_one_entry() -> None:
    assert block("protected", context="read CONTRIBUTING.md").context == ("read CONTRIBUTING.md",)


def _result(verdict: Verdict) -> ProcessResult:
    return ProcessResult(verdict, () if verdict is Verdict.ALLOW else ("because",))


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ((), Verdict.ALLOW),
        ((Verdict.ALLOW, Verdict.ASK), Verdict.ASK),
        ((Verdict.ASK, Verdict.BLOCK, Verdict.ALLOW), Verdict.BLOCK),
    ],
    ids=["no_processes", "ask_beats_allow", "block_beats_ask"],
)
def test_most_restrictive_verdict_wins(verdicts: tuple[Verdict, ...], expected: Verdict) -> None:
    results = [NamedResult(f"p{index}", _result(verdict)) for index, verdict in enumerate(verdicts)]

    assert combine(results).verdict is expected


def test_combined_reasons_come_from_winning_verdict_with_process_prefix() -> None:
    results = [
        NamedResult("Tests", block("tests fail")),
        NamedResult("Style", ask("style?")),
        NamedResult("Guard", block("protected", "ask the user")),
    ]

    assert combine(results).reasons == (
        "[Tests] tests fail",
        "[Guard] protected",
        "[Guard] ask the user",
    )


def test_context_of_all_processes_is_kept_in_order() -> None:
    results = [
        NamedResult("A", allow(context="one")),
        NamedResult("B", block("stop", context=["two", "three"])),
    ]

    assert combine(results).context == ("one", "two", "three")


def test_hook_input_record_leaves_out_the_raw_payload() -> None:
    event = HookInput(Harness.CLAUDE, Hook.STOP, raw={"transcript": "long"})

    record = event.to_record()

    assert "raw" not in record
    assert record["hook"] == "stop"
