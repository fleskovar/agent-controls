"""VS Code (GitHub Copilot agent) adapter.

References (read on 2026-09-15):
- https://code.visualstudio.com/docs/agents/reference/hooks-reference
- https://code.visualstudio.com/docs/copilot/customization/hooks

The payload and output follow the Claude Code format, with camelCase tool
arguments (`filePath`). Configuration: `.github/hooks/agent-controls-vscode.json`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, Final

from agent_controls.harnesses.base import (
    Shell,
    ToolCatalog,
    command_line,
    is_own_command,
    reason_text,
)
from agent_controls.harnesses.claude import (
    CAPABILITIES as CLAUDE_CAPABILITIES,
)
from agent_controls.harnesses.claude import (
    EVENT_NAMES as CLAUDE_EVENT_NAMES,
)
from agent_controls.harnesses.claude import (
    parse_snake_case,
    render_claude_style,
)
from agent_controls.model import Capability, Harness, Hook, HookInput, ProcessResult, Verdict

_VSCODE_HOOKS: Final = (
    Hook.SESSION_START,
    Hook.USER_PROMPT,
    Hook.PRE_TOOL,
    Hook.POST_TOOL,
    Hook.STOP,
    Hook.SUBAGENT_START,
    Hook.SUBAGENT_STOP,
    Hook.PRE_COMPACT,
)

EVENT_NAMES: Final[Mapping[Hook, str]] = {hook: CLAUDE_EVENT_NAMES[hook] for hook in _VSCODE_HOOKS}

CAPABILITIES: Final[Mapping[Hook, Capability]] = {
    **{hook: CLAUDE_CAPABILITIES[hook] for hook in _VSCODE_HOOKS},
    # UserPromptSubmit uses the common output format only: no additionalContext.
    Hook.USER_PROMPT: Capability(frozenset({Verdict.ALLOW, Verdict.BLOCK}), context=False),
}

PATCH_TOOLS: Final = frozenset({"apply_patch", "applyPatch"})
_PATCH_FILE_HEADER: Final = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.MULTILINE
)

TOOLS: Final = ToolCatalog(
    read=frozenset({"read_file", "readFile", "view_image", "read_notebook_cell_output"}),
    write=frozenset(
        {
            "create_file",
            "createFile",
            "replace_string_in_file",
            "replaceStringInFile",
            "multi_replace_string_in_file",
            "multiReplaceStringInFile",
            "insert_edit_into_file",
            "insertEditIntoFile",
            "apply_patch",
            "applyPatch",
            "edit_notebook_file",
            "editNotebookFile",
            "create_directory",
            "createDirectory",
            "editFiles",
        }
    ),
    search=frozenset(
        {
            "file_search",
            "fileSearch",
            "grep_search",
            "grepSearch",
            "list_dir",
            "listDirectory",
            "semantic_search",
            "codebase",
            "textSearch",
            "findTextInFiles",
            "findFiles",
        }
    ),
    shell=frozenset({"run_in_terminal", "runInTerminal", "runCommands"}),
    path_keys=frozenset({"filePath", "file_path", "path", "dirPath", "files", "filePaths"}),
)


def patch_paths(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    """The files named in the headers of an `apply_patch` patch."""
    patch = arguments.get("input", arguments.get("patch", ""))
    return tuple(_PATCH_FILE_HEADER.findall(patch)) if isinstance(patch, str) else ()


class VSCodeAdapter:
    harness = Harness.VSCODE
    tools = TOOLS
    capabilities = CAPABILITIES
    config_path = PurePosixPath(".github/hooks/agent-controls-vscode.json")

    def parse(self, hook: Hook, payload: Mapping[str, Any]) -> HookInput:
        event = parse_snake_case(self.harness, hook, payload, self.tools)
        tool = event.tool
        if tool is not None and tool.name in PATCH_TOOLS:
            paths = tuple(dict.fromkeys((*tool.paths, *patch_paths(tool.arguments))))
            event = replace(event, tool=replace(tool, paths=paths))
        return event

    def render(self, hook: Hook, result: ProcessResult) -> Mapping[str, Any] | None:
        return (
            {"continue": False, "stopReason": reason_text(result)}
            if hook is Hook.USER_PROMPT and result.verdict is Verdict.BLOCK
            else render_claude_style(hook, result, EVENT_NAMES)
        )

    def merge_config(
        self,
        existing: Mapping[str, Any],
        commands: Mapping[Hook, Sequence[str]],
        runner: str,
        timeout: int,
    ) -> dict[str, Any]:
        hooks: dict[str, list[dict[str, Any]]] = {
            event: [
                handler
                for handler in handlers
                if not is_own_command(handler.get("command"), runner)
            ]
            for event, handlers in dict(existing.get("hooks", {})).items()
        }
        for hook, argv in commands.items():
            hooks.setdefault(EVENT_NAMES[hook], []).append(
                {
                    "type": "command",
                    "command": command_line(argv, Shell.POSIX),
                    "windows": command_line(argv, Shell.POWERSHELL),
                    "timeout": timeout,
                }
            )
        return {
            **existing,
            "hooks": {event: handlers for event, handlers in hooks.items() if handlers},
        }
