from builders import a_tool_event

from agent_actions.model import ToolKind, Verdict, allow, block
from agent_actions.processes import BlockShellCommands
from agent_actions.processes.shell import SHELL_REASON


def test_matching_command_is_blocked_with_the_pattern() -> None:
    event = a_tool_event("Bash", ToolKind.SHELL, command="git push origin main --force")

    result = BlockShellCommands([r"git\s+push\s+.*--force"]).run(event)

    assert result == block(
        rf"The shell command matches the blocked pattern 'git\s+push\s+.*--force'. {SHELL_REASON}"
    )


def test_match_ignores_case() -> None:
    event = a_tool_event("PowerShell", ToolKind.SHELL, command="RM -RF build")

    assert BlockShellCommands("rm -rf").run(event).verdict is Verdict.BLOCK


def test_non_shell_tool_is_allowed() -> None:
    event = a_tool_event("Write", ToolKind.WRITE, paths=["notes.md"])

    assert BlockShellCommands("rm -rf").run(event) == allow()
