import os
from pathlib import Path

import pytest

from agent_actions.errors import StateError
from agent_actions.storage import file_lock, read_json, write_json


def test_missing_file_reads_as_an_empty_object(tmp_path: Path) -> None:
    assert read_json(tmp_path / "state.json") == {}


def test_corrupt_file_is_an_error_and_stays_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{oops", encoding="utf-8")

    with pytest.raises(StateError, match="is not valid JSON"):
        read_json(path)

    assert path.read_text(encoding="utf-8") == "{oops"


def test_json_that_is_not_an_object_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(StateError, match="must contain a JSON object"):
        read_json(path)


def test_written_json_reads_back_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "io.json"

    write_json(path, {"step": {"exit_code": 0, "text": "é"}})

    assert read_json(path) == {"step": {"exit_code": 0, "text": "é"}}
    assert [child.name for child in tmp_path.iterdir()] == ["io.json"]


def test_lock_file_exists_only_inside_the_block(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"

    with file_lock(lock):
        inside = lock.exists()

    assert (inside, lock.exists()) == (True, False)


def test_stale_lock_is_taken_over(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    lock.touch()
    os.utime(lock, (0, 0))

    with file_lock(lock, wait_seconds=1, stale_seconds=10):
        pass

    assert not lock.exists()


def test_held_lock_times_out(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    lock.touch()

    with (
        pytest.raises(StateError, match="Timed out"),
        file_lock(lock, wait_seconds=0.1, stale_seconds=3600),
    ):
        pass
