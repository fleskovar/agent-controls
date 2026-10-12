from builders import an_event

from agent_actions.model import Hook, allow
from agent_actions.processes import AddContext


def test_text_is_added_as_context() -> None:
    assert AddContext("Use make test.").run(an_event(Hook.SESSION_START)) == allow(
        context="Use make test."
    )


def test_default_hook_is_session_start() -> None:
    assert AddContext("rules").hooks == (Hook.SESSION_START,)
