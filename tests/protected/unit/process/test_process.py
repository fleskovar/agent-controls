import pytest
from builders import an_event

from agent_actions.errors import StateError
from agent_actions.model import Hook, HookInput, ProcessResult, allow
from agent_actions.process import PreToolProcess, StopProcess


class Counter(StopProcess):
    def __init__(self, label_note: str = "not state") -> None:
        self.label_note = label_note

    def __state__(self) -> None:
        self.count = 0
        self.history: list[str] = []

    def run(self, event: HookInput) -> ProcessResult:
        self.count += 1
        return allow()


class Stateless(PreToolProcess):
    def run(self, event: HookInput) -> ProcessResult:
        return allow()


def test_state_names_are_the_attributes_created_by_state_method() -> None:
    assert Counter().state_names() == ("count", "history")


def test_load_state_restores_known_values_and_ignores_unknown_ones() -> None:
    process = Counter()

    process.load_state({"count": 4, "removed_variable": True})

    assert process.dump_state() == {"count": 4, "history": []}


def test_load_state_resets_values_that_are_not_saved() -> None:
    process = Counter()
    process.load_state({"count": 4})
    process.history.append("changed")

    process.load_state({})

    assert process.dump_state() == {"count": 0, "history": []}


def test_state_survives_a_run_and_is_dumped() -> None:
    process = Counter()
    process.load_state({"count": 1})

    process.run(an_event(Hook.STOP))

    assert process.dump_state()["count"] == 2


def test_non_json_state_names_the_process_and_the_variable() -> None:
    process = Counter()
    process.load_state({})
    process.history = {"a", "b"}  # type: ignore[assignment]  # the mistake under test

    with pytest.raises(StateError, match="State variable 'history' of process 'Counter'"):
        process.dump_state()


def test_process_without_state_method_has_no_state() -> None:
    assert Stateless().dump_state() == {}


def test_label_is_the_class_name_unless_a_name_is_set() -> None:
    named = Counter()
    named.name = "tests"

    assert (Counter().label, named.label) == ("Counter", "tests")


def test_hooks_default_to_the_first_family_hook() -> None:
    assert Counter().hooks == (Hook.STOP,)
