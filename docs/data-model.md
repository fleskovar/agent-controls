# Data model per harness

This document maps the neutral model to each harness. The adapters are the only
code that holds these names. Sources, read on 2026-09-15:

- Claude Code: <https://code.claude.com/docs/en/hooks>
- VS Code: <https://code.visualstudio.com/docs/agents/reference/hooks-reference>
  and <https://code.visualstudio.com/docs/copilot/customization/hooks>
- Copilot CLI: <https://docs.github.com/en/copilot/reference/hooks-reference>

Harness documentation changes. If a field moves, change the adapter and its unit
test, and nothing else.

## 1. The neutral types

```python
class Hook(StrEnum):        # the lifecycle point
    SESSION_START; USER_PROMPT; PRE_TOOL; POST_TOOL; STOP
    SUBAGENT_START; SUBAGENT_STOP; PRE_COMPACT; SESSION_END

class Verdict(StrEnum):     # what a process decides
    ALLOW; ASK; BLOCK

class ToolKind(StrEnum):    # what a tool does
    READ; WRITE; SEARCH; SHELL; OTHER
```

```python
@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str                     # the harness tool name, for example "Edit"
    kind: ToolKind                # from the tool catalog of the adapter
    arguments: Mapping[str, Any]  # the tool input, as the harness sent it
    paths: tuple[str, ...]        # every value under a path key, any depth
    command: str | None           # the command text, shell tools only
    output: str | None            # the tool result, post-tool only

@dataclass(frozen=True, slots=True)
class HookInput:
    harness: Harness;  hook: Hook
    session_id: str;   cwd: str;  root: str
    agent_id: str | None;  agent_type: str | None
    tool: ToolCall | None
    prompt: str | None          # user-prompt
    last_message: str | None    # stop and subagent-stop
    stop_hook_active: bool
    raw: Mapping[str, Any]      # the payload, unchanged

@dataclass(frozen=True, slots=True)
class ProcessResult:
    verdict: Verdict
    reasons: tuple[str, ...]    # to the agent on block and ask; to log.txt on allow
    context: tuple[str, ...]    # to the agent context, where the hook has a channel
```

`cwd` is the working folder of the agent, from the payload. `root` is the project
root that holds `.hooks/`. Tool paths can be relative: resolve them against `cwd`,
as `processes.paths.relative_path` does.

## 2. Hook names

| Neutral hook | Claude Code | VS Code | Copilot CLI |
| --- | --- | --- | --- |
| `session-start` | `SessionStart` | `SessionStart` | `sessionStart` |
| `user-prompt` | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmitted` |
| `pre-tool` | `PreToolUse` | `PreToolUse` | `preToolUse` |
| `post-tool` | `PostToolUse` | `PostToolUse` | `postToolUse` |
| `stop` | `Stop` | `Stop` | `agentStop` |
| `subagent-start` | `SubagentStart` | `SubagentStart` | not available |
| `subagent-stop` | `SubagentStop` | `SubagentStop` | `subagentStop` |
| `pre-compact` | `PreCompact` | `PreCompact` | not available |
| `session-end` | `SessionEnd` | not available | `sessionEnd` |

## 3. What each hook can deliver

`Context.add` reads this table. "Verdicts" are the decisions that reach the
agent. "Context" says whether the hook has a channel for added text.

| Hook | Claude Code | VS Code | Copilot CLI |
| --- | --- | --- | --- |
| `session-start` | allow, context | allow, context | allow |
| `user-prompt` | allow, block, context | allow, block | allow |
| `pre-tool` | allow, ask, block, context | allow, ask, block, context | allow, ask, block |
| `post-tool` | allow, block, context | allow, block, context | allow, context |
| `stop` | allow, block | allow, block | allow, block |
| `subagent-start` | allow, context | allow, context | — |
| `subagent-stop` | allow, block | allow, block | allow, block |
| `pre-compact` | allow | allow | — |
| `session-end` | allow | — | allow |

Two consequences you feel while writing processes:

- **`stop` has no context channel.** Put the message in the reasons of a block.
- **Copilot CLI cannot block a prompt**, so a `PromptProcess` is rejected for that
  harness at install time.

## 4. Input fields

### Claude Code and VS Code (snake_case)

| Neutral field | Payload field |
| --- | --- |
| `session_id` | `session_id` |
| `cwd` | `cwd` |
| `agent_id`, `agent_type` | `agent_id`, `agent_type` |
| `tool.name`, `tool.arguments` | `tool_name`, `tool_input` |
| `tool.output` | `tool_response` |
| `prompt` | `prompt` |
| `last_message` | `last_assistant_message` |
| `stop_hook_active` | `stop_hook_active` |

### Copilot CLI (camelCase)

| Neutral field | Payload field |
| --- | --- |
| `session_id` | `sessionId` |
| `cwd` | `cwd` |
| `agent_id`, `agent_type` | `agentId`, `agentType` or `agentName` |
| `tool.name`, `tool.arguments` | `toolName`, `toolArgs` (an object **or** a JSON string) |
| `tool.output` | `toolResult.textResultForLlm` |
| `prompt` | `prompt` |
| `last_message` | `response` |

The Copilot CLI adapter also accepts the snake_case names, because that harness
can read a Claude-format configuration.

## 5. Output rendering

| Hook and verdict | Claude Code and VS Code | Copilot CLI |
| --- | --- | --- |
| `pre-tool` allow | no output | no output |
| `pre-tool` block | `hookSpecificOutput.permissionDecision = "deny"` with `permissionDecisionReason` | `permissionDecision = "deny"` with `permissionDecisionReason` |
| `pre-tool` ask | the same, with `"ask"` | the same, with `"ask"` |
| `stop`, `subagent-stop`, `post-tool` block | `{"decision": "block", "reason": ...}` | `{"decision": "block", "reason": ...}` |
| `user-prompt` block | Claude Code: `{"decision": "block", "reason": ...}`. VS Code: `{"continue": false, "stopReason": ...}` | not available |
| any hook with context | `hookSpecificOutput.additionalContext` | `additionalContext` (post-tool) |
| allow with no context | no output at all | no output at all |

Several reasons join with a newline. Each reason carries the process name as
`[Name] reason`. Several context entries join with a blank line.

## 6. Tool catalogs

`tools_for(harness)` returns these sets. Use `tool.kind` in a process; use the
sets only when you need a specific tool name.

| Kind | Claude Code | VS Code | Copilot CLI |
| --- | --- | --- | --- |
| write | `Write`, `Edit`, `MultiEdit`, `NotebookEdit` | `create_file`, `replace_string_in_file`, `multi_replace_string_in_file`, `insert_edit_into_file`, `apply_patch`, `edit_notebook_file`, `create_directory`, `editFiles` (and camelCase forms) | `create`, `edit` |
| read | `Read`, `NotebookRead` | `read_file`, `view_image`, `read_notebook_cell_output` | `view` |
| search | `Glob`, `Grep`, `LS` | `file_search`, `grep_search`, `list_dir`, `semantic_search`, `codebase`, `findFiles`, `findTextInFiles` | `grep`, `glob` |
| shell | `Bash`, `PowerShell` | `run_in_terminal`, `runCommands` | `bash`, `powershell` |
| path keys | `file_path`, `notebook_path`, `path` | `filePath`, `file_path`, `path`, `dirPath`, `files`, `filePaths` | `path`, `file_path` |

Path search is recursive, so a tool that edits several files in one call, such as
`MultiEdit` or `multi_replace_string_in_file`, yields every path. For VS Code
`apply_patch`, the adapter also reads the `*** Update File:` headers of the patch.

## 7. Configuration files

| Harness | File | Shape |
| --- | --- | --- |
| `claude` | `.claude/settings.json` | `hooks.<Event>[] = {matcher?, hooks: [{type, command, timeout}]}`; `matcher: "*"` on tool events |
| `vscode` | `.github/hooks/agent-controls-vscode.json` | `hooks.<Event>[] = {type, command, windows, timeout}` |
| `copilot-cli` | `.github/hooks/agent-controls-copilot-cli.json` | `version: 1`, `hooks.<event>[] = {type, bash, powershell, cwd, timeoutSec}` |

`install` writes one entry per hook that the runner file uses, replaces the
entries of the same runner file, and keeps every other key of the file.
