---
name: agent-actions-processes
description: Write and test a new Agent Actions process - a Python class that runs on an AI agent lifecycle hook in Claude Code, VS Code or Copilot CLI - and look up the parameters of the included processes. Use when the included processes cannot do what a project needs, when a custom guardrail needs state or its own decision logic, when a process must share state with a different process or a later session, or when you need the exact signature of an included process.
---

# Author an Agent Actions process

Agent Actions runs Python classes on agent lifecycle hooks. This skill tells you
how to add one to a project without reading the framework source.

To install the package and to register the hooks, use the `agent-actions-setup`
skill. To set up tests, coverage, a linter or protected files in a project of any
language, use the `agent-actions-guardrails` skill.

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
| "Do not let it retry for ever" | `Limit(RequireTests(), max_in_a_row=3)` |
| "After 5 failures in a row, or 10 in total, let it stop and ask for help" | `Limit(RequireTests(), max_in_a_row=5, max_total=10)` |
| "After 2 denied attempts, let me decide" | `Limit(BlockWrites([...]), max_in_a_row=2, then=aa.Verdict.ASK)` |
| "Lint each file it edits" | `CheckAfterEdit("ruff check {paths}", patterns=["*.py"])` |
| "Show it the failed tests at the start" | `RunCommand("dotnet test", on=[Hook.SESSION_START])` |
| "Tell it the project rules at the start" | `AddContext("...")` |
| "Cap the number of tool calls" | `ToolCallBudget(200)` |
| "Run the check only when X" | `context.add(process, when=lambda event: ...)` |
| "Remember X for a later session" | `SetFlag(context.flags, "x")`, then `when=lambda _: context.flags.get("x")` |
| "Lint only the files that changed in this session" | `SetFlag(context.session_flags, "baseline", git_snapshot, keep=True)` and `on_changed_paths(...)` |

All of them come from `agent_actions.processes`. The parameters of each one are
in [the process reference](./reference.md).

The last three rows make a check depend on the context. The
`agent-actions-guardrails` skill has a complete runner file for each such
pattern, on its page about flags and conditions. Read that page before you write
a class for one of them.

## 2. The runner file

One file per project lists the processes. It is harness-agnostic.

```python
import agent_actions as aa
from agent_actions.processes import BlockWrites, Limit, RequireTests

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
context.add(Limit(RequireTests(), max_in_a_row=3))
aa.run(context)
```

Rules for the runner file:

- Call `aa.run(context)` once, at the end. Without it the run fails.
- Do not read stdin, and do not print. The CLI does both.
- Do not branch on the harness. If you need harness-specific tool names, use
  `aa.tools_for(context.harness)`.
- Give each process a different `name=` when you add two of the same class.
- Do not put an `if` around `context.add`. Use `context.add(process, when=...)`,
  so that `install` finds the hook of the process.

Install the hooks after each change of the process list:

```bash
python -m agent_actions install .hooks/agent_checks.py --target claude
```

The runner file imports the modules that are beside it. Thus put a new process
class in a file beside the runner file, and import it there.

## 3. Write a new process

Pick the family of the hook. The family fixes the hooks and the verdicts.

| Family | Hooks it can attach to | Verdicts | Typical use |
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
- **Shared state lives in a flag.** The state belongs to one process and one
  agent. For a value that a different process or a later session reads, take
  `context.flags` or `context.session_flags` as a parameter, and change that
  dict in `run`. A test gives a plain dict.
- **Do not read the clock, the environment or files at import time.** Take them
  as parameters. The case tests then stay deterministic.
- **Inject anything that runs a command.** Take a `command_runner` parameter with
  `run_subprocess` as the default, as `RequireCommand` does.
- **Return a result. Do not print.** Use `aa.log(...)` for the session log.

Useful fields of `event` (`HookInput`): `harness`, `hook`, `session_id`, `cwd`,
`root`, `agent_id`, `agent_type`, `prompt`, `last_message`, `stop_hook_active`,
`raw`, and `tool` with `name`, `kind`, `arguments`, `paths`, `command`, `output`.

## 4. Share state between processes and sessions

`__state__` belongs to one process in one agent. For each other need, use a flag
or a condition.

| Need | Use |
| --- | --- |
| A count or a memory of one process | `__state__` |
| A value that a different process reads in the same session | `context.session_flags` |
| A value that a later session reads | `context.flags` |
| Run an included process only in some conditions | `context.add(process, when=...)`, and no new class |
| The files that changed after a moment | `git_snapshot` in a flag, then `changed_paths` |

Rules for a process that uses flags:

- **Take the flag dict as a parameter.** The runner file gives `context.flags` or
  `context.session_flags`. A test gives a plain dict.
- **Read a flag with `.get`.** A flag is missing before its first write.
- **Change the dict in `run`.** The framework saves each changed flag after the
  hook call. Values must be JSON types.
- **Do not write a class only to skip a process.** That is the job of `when`.
- **Write a condition as a function of the event, with a name.** Then a test can
  call it.

This stop process reads a snapshot from a flag. It blocks the stop when one
group of files changed after the snapshot, and its paired group did not:

```python
from collections.abc import Mapping, Sequence
from typing import Any

import agent_actions as aa
from agent_actions.processes import Limit, SetFlag, changed_paths, git_snapshot


class RequirePairedChange(aa.StopProcess):
    """Blocks the stop when `changed` files changed after the baseline and no `paired` file did."""

    def __init__(
        self,
        flags: Mapping[str, Any],
        changed: Sequence[str],
        paired: Sequence[str],
        reason: str,
        *,
        name: str,
    ) -> None:
        self.flags = flags
        self.changed = changed
        self.paired = paired
        self.reason = reason
        self.name = name

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        baseline = self.flags.get("baseline")
        trigger = changed_paths(event.root, baseline, self.changed)
        if not trigger or changed_paths(event.root, baseline, self.paired):
            return aa.allow()
        return aa.block(
            f"You changed {', '.join(trigger)}, but no file in {', '.join(self.paired)}. "
            f"{self.reason}"
        )


context = aa.get_current_context()
session = context.session_flags

context.add(SetFlag(session, "baseline", git_snapshot, keep=True))
context.add(
    Limit(
        RequirePairedChange(
            session,
            ["pyproject.toml", "requirements*.txt"],
            ["CHANGELOG.md"],
            "Add the dependency change to the changelog.",
            name="dependencies-need-changelog",
        ),
        max_in_a_row=3,
    )
)
aa.run(context)
```

- The process does not save the snapshot. `SetFlag` does that on `session-start`,
  so a different process can use the same baseline.
- `changed_paths` with `None` gives each uncommitted change. Thus the process is
  strict, not open, when the baseline is missing.
- The test of a process that reads git uses a real repository in a temporary
  folder. Section 6 shows it.

## 5. Know what the harness can deliver

`context.add` rejects a process when its hook, its verdicts or its context do not
fit the target harness. The error names the reason. Three traps:

- `stop` and `subagent-stop` have **no context channel**. Put the message in the
  reasons of a block.
- Copilot CLI cannot block a `user-prompt`, and has no `subagent-start` hook.
- VS Code has no `session-end` hook, and no context on `user-prompt`.

An `allow` on `pre-tool` never approves the call. It only states no objection, so
the permission rules of the harness still apply.

## 6. Test the process

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

The imports of the test are `from agent_actions.model import Harness, Hook,
HookInput, ToolCall, ToolKind, Verdict`. Run the test with the interpreter that
has agent_actions.

A process that uses flags gets a plain dict. A process that reads a snapshot gets
a git repository in the temporary folder of the test:

```python
import git
from agent_actions.model import Harness, Hook, HookInput, Verdict
from agent_actions.processes import git_snapshot


def test_dependency_change_needs_a_changelog_entry(tmp_path) -> None:
    repo = git.Repo.init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("dependencies = []\n")
    repo.index.add(["pyproject.toml"])
    repo.index.commit("first")
    event = HookInput(Harness.CLAUDE, Hook.STOP, root=str(tmp_path))
    flags = {"baseline": git_snapshot(event)}
    process = RequirePairedChange(
        flags, ["pyproject.toml"], ["CHANGELOG.md"], "Add an entry.", name="changelog"
    )

    (tmp_path / "pyproject.toml").write_text("dependencies = ['requests']\n")
    assert process.run(event).verdict is Verdict.BLOCK

    (tmp_path / "CHANGELOG.md").write_text("- Added requests.\n")
    assert process.run(event).verdict is Verdict.ALLOW
```

A condition is a function. Call it with an event: `assert reads_the_guide(event)`.

Then run the process through the runner file, with a payload from a real
session. Section 7 shows the command. For a process with `when`, do two replays:
one with the flag in `.hooks/flags.json`, and one without it.

Prove the test can fail: break the rule on purpose, watch the test go red, then
restore it.

## 7. Check the recorded session when a hook behaves oddly

```text
.hooks/flags.json                                     the flags of the project
.hooks/<timestamp>_<short-session-id>/flags.json      the flags of one session
.hooks/<timestamp>_<short-session-id>/main-agent/
    state.json   state, inputs and outputs per step and process
    io.json      raw stdin, stdout and exit code per step
    log.txt      the aa.log lines, one summary line per result, each skipped
                 process, and each changed flag
```

Replay a recorded call, with no agent:

```bash
python -m agent_actions run .hooks/agent_checks.py --harness claude --hook pre-tool --input payload.json
```

Take the payload from the `stdin` of an `io.json` entry. The troubleshooting page
of the `agent-actions-setup` skill lists the common errors.
