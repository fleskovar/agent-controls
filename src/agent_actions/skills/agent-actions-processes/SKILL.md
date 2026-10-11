---
name: agent-actions-processes
description: Write, test and install Agent Actions processes - the Python guardrails that run on AI agent lifecycle hooks (Claude Code, VS Code, Copilot CLI). Use when a project asks to block edits of protected files, block reads of secrets, force tests or linters before the agent stops, limit retries or tool calls, add context at session start, or when a runner file, a hook configuration or a `.hooks/` session record needs a change.
---

# Author an Agent Actions process

Agent Actions runs Python classes on agent lifecycle hooks. This skill tells you
how to add one to a project without reading the framework source.

## 1. Check first whether an included process is enough

Do not write a class before you check the catalog. Most requests need
composition, not new code.

| Request | Use |
| --- | --- |
| "Never let the agent change the tests" | `BlockWrites(["tests/**"])` |
| "Undo each change to the tests, also from a shell command" | `RevertWrites(["tests/**"])` |
| "Never let the agent read the secrets" | `BlockReads([".env", "secrets/**"])` |
| "No force pushes, no rm -rf" | `BlockShellCommands([r"git\s+push\s+.*--force", r"\brm\s+-rf\b"])` |
| "Tests must pass before it stops" | `RequireTests()` |
| "The linter must pass before it stops" | `RequireCommand("ruff check .")` |
| "Do not let it retry for ever" | `LoopGuard(RequireTests(), max_blocks=3)` |
| "Lint each file it edits" | `CheckAfterEdit("ruff check {paths}", patterns=["*.py"])` |
| "Show it the failed tests at the start" | `RunCommand("dotnet test", on=[Hook.SESSION_START])` |
| "Tell it the project rules at the start" | `AddContext("...")` |
| "Cap the number of tool calls" | `ToolCallBudget(200)` |

All of them come from `agent_actions.processes`. The parameters are in
`docs/processes.md` of the framework.

## 2. The runner file

One file per project lists the processes. It is harness-agnostic.

```python
import agent_actions as aa
from agent_actions.processes import BlockWrites, LoopGuard, RequireTests

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
context.add(LoopGuard(RequireTests(), max_blocks=3))
aa.run(context)
```

Rules for the runner file:

- Call `aa.run(context)` once, at the end. Without it the run fails.
- Do not read stdin, and do not print. The CLI does both.
- Do not branch on the harness. If you need harness-specific tool names, use
  `aa.tools_for(context.harness)`.
- Give each process a different `name=` when you add two of the same class.

Install the hooks after each change of the process list:

```bash
agent_actions install agent_checks.py --target claude
```

## 3. Write a new process

Pick the family of the hook. The family fixes the hooks and the verdicts.

| Family | Hooks it may attach to | Verdicts | Typical use |
| --- | --- | --- | --- |
| `PreToolProcess` | `pre-tool` | allow, ask, block | Block a tool call before it runs |
| `PostToolProcess` | `post-tool` | allow, block | Give feedback about a finished call |
| `PromptProcess` | `user-prompt` | allow, block | Reject a prompt |
| `StopProcess` | `stop`, `subagent-stop` | allow, block | Keep the agent working |
| `StartProcess` | `session-start`, `subagent-start` | allow | Add context |
| `EventProcess` | any hook | allow | Observe, or add context |

```python
import agent_actions as aa


class BlockLargeWrites(aa.PreToolProcess):
    """Blocks a write of more than `max_bytes` characters, and counts the blocks."""

    verdicts = aa.process.ALLOW_OR_BLOCK  # narrow the declaration when you never ask

    def __init__(self, max_bytes: int = 20_000, *, name: str = "") -> None:
        self.max_bytes = max_bytes
        self.name = name

    def __state__(self) -> None:
        self.blocked = 0

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        tool = event.tool
        content = "" if tool is None else str(tool.arguments.get("content", ""))
        if tool is None or tool.kind is not aa.ToolKind.WRITE or len(content) <= self.max_bytes:
            return aa.allow()
        self.blocked += 1
        aa.log(f"blocked write number {self.blocked}")
        return aa.block(
            f"The write is {len(content)} characters, over the limit of {self.max_bytes}. "
            "Split the change into smaller edits."
        )
```

Hard rules:

- **A `block` or an `ask` needs a reason.** The reason is the only thing the
  agent reads. Write what to do next, not only what went wrong.
- **State lives in `__state__`.** The attributes that `__state__` creates are the
  state. The framework restores them before `run` and records them after. Values
  must be JSON types. Attributes from `__init__` are configuration, not state.
- **Do not read the clock, the environment or files at import time.** Take them
  as parameters. The case tests then stay deterministic.
- **Inject anything that runs a command.** Take a `command_runner` parameter with
  `run_subprocess` as the default, as `RequireCommand` does.
- **Return a result. Do not print.** Use `aa.log(...)` for the session log.

Useful fields of `event` (`HookInput`): `harness`, `hook`, `session_id`, `cwd`,
`root`, `agent_id`, `agent_type`, `prompt`, `last_message`, `stop_hook_active`,
`raw`, and `tool` with `name`, `kind`, `arguments`, `paths`, `command`, `output`.

## 4. Know what the harness can deliver

`context.add` rejects a process when its hook, its verdicts or its context do not
fit the target harness. The error names the reason. Three traps:

- `stop` and `subagent-stop` have **no context channel**. Put the message in the
  reasons of a block.
- Copilot CLI cannot block a `user-prompt`, and has no `subagent-start` hook.
- VS Code has no `session-end` hook, and no context on `user-prompt`.

An `allow` on `pre-tool` never approves the call. It only states no objection, so
the permission rules of the harness still apply.

## 5. Test the process

Unit test first, with a plain object. No files and no harness:

```python
def test_write_over_the_limit_is_blocked() -> None:
    process = BlockLargeWrites(max_bytes=10)
    process.load_state({})
    event = HookInput(
        harness=Harness.CLAUDE,
        hook=Hook.PRE_TOOL,
        tool=ToolCall("Write", ToolKind.WRITE, {"content": "x" * 11}),
    )

    result = process.run(event)

    assert result.verdict is Verdict.BLOCK
    assert process.dump_state() == {"blocked": 1}
```

Then add one case folder under `tests/cases/` for the behaviour that matters:
`inputs/case.json`, `inputs/runner.py`, `inputs/stdin.json`, the expected
`outputs/*.json`, and a `README.md` that walks a reader from the input to the
output. Copy the closest existing case folder. Adding a case is adding a folder.

Prove the test can fail: break the rule on purpose, watch the test go red, then
restore it.

## 6. Check the recorded session when a hook behaves oddly

```text
.hooks/<timestamp>_<short-session-id>/main-agent/
    state.json   state, inputs and outputs per step and process
    io.json      raw stdin, stdout and exit code per step
    log.txt      the aa.log lines and one summary line per result
```

Replay a recorded call, with no agent:

```bash
agent_actions run agent_checks.py --harness claude --hook pre-tool --input payload.json
```

Take the payload from an `io.json` entry. This is also how you build a new case
folder from a real session.
