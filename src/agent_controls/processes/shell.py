"""Shell command guard."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from agent_controls.model import HookInput, ProcessResult, ToolKind, allow, block
from agent_controls.process import ALLOW_OR_BLOCK, PreToolProcess

SHELL_REASON: Final = "Use a safer command, or ask the user to run this one."


class BlockShellCommands(PreToolProcess):
    """Blocks shell commands that match a regular expression (case-insensitive).

    Example: `BlockShellCommands([r"\\brm\\s+-rf\\b", r"git\\s+push\\s+.*--force"])`.
    """

    verdicts = ALLOW_OR_BLOCK

    def __init__(
        self, patterns: str | Sequence[str], *, reason: str = SHELL_REASON, name: str = ""
    ) -> None:
        texts = (patterns,) if isinstance(patterns, str) else tuple(patterns)
        self.patterns = tuple(re.compile(text, re.IGNORECASE) for text in texts)
        self.reason = reason
        self.name = name

    def run(self, event: HookInput) -> ProcessResult:
        tool = event.tool
        command = tool.command if tool is not None and tool.kind is ToolKind.SHELL else None
        match = next(
            (pattern for pattern in self.patterns if command and pattern.search(command)), None
        )
        return (
            allow()
            if match is None
            else block(
                f"The shell command matches the blocked pattern '{match.pattern}'. {self.reason}"
            )
        )
