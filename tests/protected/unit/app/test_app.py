from pathlib import Path

import pytest

from agent_actions.app import install_hooks, parse_payload, run_hook
from agent_actions.errors import PayloadError, RunnerFileError
from agent_actions.model import Harness, Hook


def test_invalid_payload_fails_without_creating_session_files(tmp_path: Path) -> None:
    response = run_hook(tmp_path, Path("checks.py"), Harness.CLAUDE, Hook.STOP, "{oops")

    assert response.exit_code == 1
    assert "not valid JSON" in response.stderr
    assert not (tmp_path / ".hooks").exists()


def test_hook_that_the_harness_lacks_is_reported(tmp_path: Path) -> None:
    response = run_hook(tmp_path, Path("checks.py"), Harness.COPILOT_CLI, Hook.SUBAGENT_START, "{}")

    assert response.stderr == "agent_actions: Harness 'copilot-cli' has no 'subagent-start' hook."


def test_payload_must_be_a_json_object() -> None:
    with pytest.raises(PayloadError, match="must be a JSON object"):
        parse_payload("[1]")


def test_empty_payload_is_an_empty_object() -> None:
    assert parse_payload("  \n") == {}


def test_missing_runner_file_is_recorded_as_a_failed_step(tmp_path: Path) -> None:
    response = run_hook(
        tmp_path, Path("missing.py"), Harness.CLAUDE, Hook.STOP, '{"session_id": "s1"}'
    )

    [io_file] = (tmp_path / ".hooks").glob("*/main-agent/io.json")
    assert response.exit_code == 1
    assert '"exit_code": 1' in io_file.read_text(encoding="utf-8")


def test_install_of_a_runner_file_without_processes_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "checks.py").write_text(
        "import agent_actions as aa\naa.run(aa.get_current_context())\n", encoding="utf-8"
    )

    with pytest.raises(RunnerFileError, match="adds no processes"):
        install_hooks(tmp_path, Path("checks.py"), Harness.CLAUDE, "python")
