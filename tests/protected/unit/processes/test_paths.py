import pytest
from builders import a_tool_event, an_event

from agent_actions.model import ToolKind, Verdict, allow, block
from agent_actions.processes import BlockReads, BlockWrites
from agent_actions.processes.paths import (
    READ_REASON,
    WRITE_REASON,
    matching_pattern,
    mentioned_pattern,
    relative_path,
)


@pytest.mark.parametrize(
    ("path", "cwd", "expected"),
    [
        ("tests/test_a.py", "/repo", "tests/test_a.py"),
        ("/repo/tests/test_a.py", "/repo/src", "tests/test_a.py"),
        ("test_a.py", "tests", "tests/test_a.py"),
        ("../other/x.py", "/repo", "../other/x.py"),
        ("./tests/../tests/a.py", "/repo", "tests/a.py"),
        ("tests/test_a.py", "/other/place", "tests/test_a.py"),
    ],
    ids=[
        "relative_to_cwd",
        "absolute",
        "relative_cwd",
        "outside_root",
        "dot_segments",
        "cwd_outside_root_falls_back_to_root",
    ],
)
def test_tool_path_is_made_relative_to_the_project_root(path: str, cwd: str, expected: str) -> None:
    assert relative_path(path, cwd, "/repo") == expected


@pytest.mark.parametrize(
    ("relative", "patterns", "expected"),
    [
        ("tests/unit/test_a.py", ["tests"], "tests"),
        ("tests/unit/test_a.py", ["tests/**"], "tests/**"),
        ("secrets", ["secrets/**"], "secrets/**"),
        ("src/tests.py", ["tests"], None),
        ("Config/.ENV", ["config/.env"], "config/.env"),
        ("certs/server.pem", ["*.pem"], "*.pem"),
        (".env", ["./.env/"], "./.env/"),
        ("README.md", ["tests", "*.pem"], None),
    ],
    ids=[
        "folder_covers_content",
        "double_star",
        "double_star_covers_the_folder_itself",
        "folder_name_is_not_a_file_prefix",
        "case_insensitive",
        "star_crosses_folders",
        "pattern_is_normalized",
        "no_match",
    ],
)
def test_first_covering_pattern_is_returned(
    relative: str, patterns: list[str], expected: str | None
) -> None:
    assert matching_pattern(relative, patterns) == expected


@pytest.mark.parametrize(
    ("command", "patterns", "expected"),
    [
        ("cat .env", [".env"], ".env"),
        ("type secrets\\prod.json", ["secrets/*.json"], "secrets/*.json"),
        ("pytest -q", [".env"], None),
    ],
    ids=["literal", "windows_separator", "unrelated"],
)
def test_shell_command_mentioning_a_pattern_is_found(
    command: str, patterns: list[str], expected: str | None
) -> None:
    assert mentioned_pattern(command, patterns) == expected


def test_write_to_a_protected_path_is_blocked_with_the_reason() -> None:
    event = a_tool_event("Edit", ToolKind.WRITE, paths=["/repo/tests/test_a.py"])

    result = BlockWrites(["tests/**"]).run(event)

    assert result == block(
        f"'Edit' on '/repo/tests/test_a.py' is blocked: 'tests/**' is protected. {WRITE_REASON}"
    )


def test_write_guard_ignores_reads_of_protected_paths() -> None:
    event = a_tool_event("Read", ToolKind.READ, paths=["/repo/tests/test_a.py"])

    assert BlockWrites("tests").run(event) == allow()


def test_read_guard_blocks_a_search_in_a_secret_folder() -> None:
    event = a_tool_event("Grep", ToolKind.SEARCH, paths=["secrets"])

    assert BlockReads("secrets").run(event).verdict is Verdict.BLOCK


def test_read_guard_checks_shell_commands_by_default() -> None:
    event = a_tool_event("Bash", ToolKind.SHELL, command="cat .env")

    result = BlockReads(".env").run(event)

    assert result == block(
        f"The shell command is blocked: it mentions '.env', which is protected. {READ_REASON}"
    )


def test_write_guard_ignores_shell_commands_by_default() -> None:
    event = a_tool_event("Bash", ToolKind.SHELL, command="pytest tests")

    assert BlockWrites("tests").run(event) == allow()


def test_event_without_a_tool_is_allowed() -> None:
    assert BlockWrites("tests").run(an_event()) == allow()
