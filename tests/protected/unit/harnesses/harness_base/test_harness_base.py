from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from agent_actions.harnesses.base import Shell, as_mapping, command_line, find_paths
from agent_actions.harnesses.claude import TOOLS
from agent_actions.model import ToolKind


def test_paths_are_found_at_any_depth_in_order_without_duplicates() -> None:
    arguments = {
        "file_path": "a.py",
        "edits": [{"file_path": "b.py"}, {"file_path": "a.py"}],
        "files": ["c.py"],
    }

    assert find_paths(arguments, frozenset({"file_path", "files"})) == ("a.py", "b.py", "c.py")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"path": ".env"}', {"path": ".env"}),
        ("not json", {"value": "not json"}),
        ({"path": "a"}, {"path": "a"}),
        (None, {"value": None}),
    ],
    ids=["json_string", "plain_string", "mapping", "missing"],
)
def test_tool_arguments_become_a_mapping(value: Any, expected: Mapping[str, Any]) -> None:
    assert as_mapping(value) == expected


@pytest.mark.parametrize(
    ("argv", "shell", "expected"),
    [
        (
            ("C:/venv/python.exe", "-m", "agent_actions"),
            Shell.POSIX,
            "C:/venv/python.exe -m agent_actions",
        ),
        (
            ("C:/venv/python.exe", "-m", "agent_actions"),
            Shell.POWERSHELL,
            "C:/venv/python.exe -m agent_actions",
        ),
        (("C:/My Tools/python.exe", "run"), Shell.POSIX, "'C:/My Tools/python.exe' run"),
        (("C:/My Tools/python.exe", "run"), Shell.POWERSHELL, "& 'C:/My Tools/python.exe' 'run'"),
        (("/home/o'neil/python", "run"), Shell.POWERSHELL, "& '/home/o''neil/python' 'run'"),
    ],
    ids=["safe_posix", "safe_powershell", "space_posix", "space_powershell", "quote_powershell"],
)
def test_command_line_quotes_only_when_needed(
    argv: Sequence[str], shell: Shell, expected: str
) -> None:
    assert command_line(argv, shell) == expected


def test_unknown_tool_is_of_kind_other() -> None:
    assert TOOLS.kind_of("WebFetch") is ToolKind.OTHER


def test_only_shell_tools_expose_a_command() -> None:
    shell_call = TOOLS.call("Bash", {"command": "ls"})
    write_call = TOOLS.call("Write", {"file_path": "a.py", "command": "not a shell command"})

    assert (shell_call.command, write_call.command) == ("ls", None)
