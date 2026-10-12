from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from builders import an_event

from agent_actions.engine import ProcessRecord
from agent_actions.model import Hook
from agent_actions.session import (
    SessionStore,
    format_timestamp,
    free_name,
    latest_states,
    short_id,
    slug,
)
from agent_actions.storage import read_json

MOMENT = datetime(2026, 9, 15, 23, 24, 55, 123456, tzinfo=UTC)


def test_timestamp_is_utc_with_milliseconds() -> None:
    assert format_timestamp(MOMENT) == "20260915T232455123"


def test_timestamp_in_another_timezone_is_converted_to_utc() -> None:
    local = datetime(2026, 9, 16, 1, 24, 55, 123000, tzinfo=timezone(timedelta(hours=2)))

    assert format_timestamp(local) == "20260915T232455123"


def test_timestamps_sort_in_time_order() -> None:
    moments = [MOMENT + timedelta(milliseconds=offset) for offset in (999, 1, 1000, 0)]

    stamps = [format_timestamp(moment) for moment in moments]

    assert sorted(stamps) == [format_timestamp(moment) for moment in sorted(moments)]


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    [("3f1c9a2e-77b0-4c1d", "3f1c9a2e"), ("ab_c/d", "abcd"), ("", "unknown")],
    ids=["uuid", "unsafe_characters", "empty"],
)
def test_short_id_keeps_eight_safe_characters(raw_id: str, expected: str) -> None:
    assert short_id(raw_id) == expected


@pytest.mark.parametrize(
    ("agent_type", "expected"),
    [
        ("Explore", "Explore"),
        ("security reviewer!", "security-reviewer"),
        ("plugin:agent", "plugin-agent"),
        (None, "subagent"),
    ],
    ids=["plain", "spaces", "plugin_scoped", "missing"],
)
def test_slug_makes_agent_type_folder_safe(agent_type: str | None, expected: str) -> None:
    assert slug(agent_type) == expected


def test_collision_adds_one_millisecond_per_taken_name() -> None:
    taken = {"20260915T232455123_abc", "20260915T232455124_abc"}

    assert free_name(taken, MOMENT, lambda stamp: f"{stamp}_abc") == "20260915T232455125_abc"


def test_latest_state_of_each_process_wins() -> None:
    document = {
        "20260915T000000002": {"A": {"state": {"n": 2}}},
        "20260915T000000001": {"A": {"state": {"n": 1}}, "B": {"state": {"m": 1}}},
    }

    assert latest_states(document) == {"A": {"n": 2}, "B": {"m": 1}}


def test_same_session_reuses_its_folder_and_a_subagent_gets_its_own(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session_dir = tmp_path / ".hooks" / "20260915T232455123_abc12345"

    main = store.agent_dir(an_event(Hook.PRE_TOOL, session_id="abc12345-x"), MOMENT)
    again = store.agent_dir(
        an_event(Hook.STOP, session_id="abc12345-x"), MOMENT + timedelta(minutes=5)
    )
    subagent = store.agent_dir(
        an_event(Hook.SUBAGENT_STOP, session_id="abc12345-x", agent_id="ag", agent_type="Explore"),
        MOMENT + timedelta(minutes=6),
    )

    assert main == again == session_dir / "main-agent"
    assert subagent == session_dir / "Explore_20260915T233055123"
    assert read_json(subagent / "agent.json") == {"agent_id": "ag", "agent_type": "Explore"}


def test_record_appends_state_io_and_log(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    record = ProcessRecord("A", {"n": 1}, {"hook": "stop"}, {"verdict": "allow"})

    first = store.record(tmp_path, MOMENT, [record], {"exit_code": 0}, ["[A] allow"])
    second = store.record(tmp_path, MOMENT, [], {"exit_code": 1}, [])

    assert (first, second) == ("20260915T232455123", "20260915T232455124")
    assert read_json(tmp_path / "state.json") == {
        first: {
            "A": {"state": {"n": 1}, "inputs": {"hook": "stop"}, "outputs": {"verdict": "allow"}}
        }
    }
    assert list(read_json(tmp_path / "io.json")) == [first, second]
    assert (tmp_path / "log.txt").read_text(encoding="utf-8") == f"{first} [A] allow\n"
    assert store.saved_states(tmp_path) == {"A": {"n": 1}}


def test_sessions_are_listed_newest_first(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.agent_dir(an_event(session_id="older"), MOMENT)
    store.agent_dir(an_event(session_id="newer"), MOMENT + timedelta(hours=1))

    assert [summary.session_id for summary in store.sessions()] == ["newer", "older"]
