# Included processes

Import them from `agent_actions.processes`. Every process works in every
supported harness, unless the table says otherwise. Patterns are relative to the
project root, match case-insensitively, and `*` also matches `/`. A pattern
without a wildcard also covers everything inside the folder it names, and
`tests/**` also covers the folder `tests` itself.

A relative tool path resolves against the working folder of the agent. If that
folder lies outside the project root, the root is the base instead, so a guard
stays closed when a harness reports a path style the framework cannot map.

| Process | Hook | Blocks |
| --- | --- | --- |
| [`BlockWrites`](#blockwrites) | `pre-tool` | write tools on protected paths |
| [`BlockReads`](#blockreads) | `pre-tool` | read, search and write tools on secret paths |
| [`PathGuard`](#pathguard) | `pre-tool` | the tool kinds you choose |
| [`BlockShellCommands`](#blockshellcommands) | `pre-tool` | shell commands that match a regular expression |
| [`RequireCommand`](#requirecommand) | `stop`, `subagent-stop` | the stop while a command fails |
| [`RequireTests`](#requiretests) | `stop`, `subagent-stop` | the stop while pytest fails |
| [`LoopGuard`](#loopguard) | the hooks of the process it wraps | nothing; it releases a blocked stop |
| [`CheckAfterEdit`](#checkafteredit) | `post-tool` | nothing; it adds the failure output as context |
| [`RunCommand`](#runcommand) | any hook with a context channel | nothing; it adds the failure output as context |
| [`RevertWrites`](#revertwrites) | `session-start`, `subagent-start`, `post-tool` | nothing; it reverts changes to protected paths with git |
| [`AddContext`](#addcontext) | any hook with a context channel | nothing |
| [`ToolCallBudget`](#toolcallbudget) | `pre-tool` | tool calls after a maximum |

## BlockWrites

```python
BlockWrites(patterns, *, reason=..., check_shell=False, name="")
```

Blocks write tools on matching paths. Use it for tests, generated code,
migrations, or any file that only a person changes.

```python
context.add(BlockWrites(["tests/**", "migrations/**", "pyproject.toml"]))
```

- `reason` replaces the default sentence that the agent reads. Say what to do
  instead.
- `check_shell=True` also blocks shell commands that mention a protected path.
  It is off by default, because `pytest tests` mentions `tests` and is harmless.

## BlockReads

```python
BlockReads(patterns, *, reason=..., check_shell=True, name="")
```

Blocks read, search **and** write tools on matching paths, and by default also
shell commands that mention one. Use it for credentials.

```python
context.add(BlockReads([".env", "secrets/**", "*.pem", "~/.aws/**"]))
```

A search tool that names no path is not blocked. A repository-wide search can
still reach a secret file that no ignore file excludes.

## PathGuard

```python
PathGuard(patterns, *, kinds, reason, check_shell=False, name="")
```

The base of the two guards above. Use it for a combination they do not cover, for
example only search tools:

```python
context.add(PathGuard(["archive/**"], kinds={ToolKind.SEARCH}, reason="The archive is noise."))
```

## BlockShellCommands

```python
BlockShellCommands(patterns, *, reason=..., name="")
```

Blocks a shell command when a regular expression matches it. Matching ignores
case.

```python
context.add(BlockShellCommands([
    r"\brm\s+-rf\b",
    r"git\s+push\s+.*--force",
    r"\bcurl\b.*\|\s*(ba)?sh",
]))
```

## RequireCommand

```python
RequireCommand(command, *, reason=..., timeout=240.0, max_output_chars=3000,
               on=(Hook.STOP,), name="", command_runner=run_subprocess)
```

Runs a command when the agent wants to stop. Exit code 0 allows the stop.
Anything else blocks it and gives the agent the command output.

```python
context.add(RequireCommand("ruff check .", name="lint"))
context.add(RequireCommand(["mypy", "src"], name="types", on=[Hook.STOP, Hook.SUBAGENT_STOP]))
```

- A string command runs in the shell. A sequence runs without one.
- The command runs in the project root.
- Only the last `max_output_chars` characters reach the agent, which is where
  test runners and linters print their summary.
- `command_runner` is the injection point. Tests pass a function that returns a
  `CommandOutcome` and start no process.
- Give each instance a `name`. Two instances of the same class need two names.

## RequireTests

```python
RequireTests(command=(sys.executable, "-m", "pytest", "-q"), *, reason=..., **options)
```

`RequireCommand` with pytest and a reason that also forbids the obvious cheat:

> Make all tests pass before you finish. Do not change or delete tests to make
> them pass.

Pair it with `BlockWrites(["tests/**"])`, which enforces the second sentence.

## LoopGuard

```python
LoopGuard(process, max_blocks=3, *, name="")
```

Wraps a stop process. It passes blocks through and counts them. After
`max_blocks` blocks in a row it allows the stop instead, and resets the counter.
An allowed stop from the wrapped process also resets it.

```python
context.add(LoopGuard(RequireTests(), max_blocks=3))
```

The last block before the release carries an extra sentence that tells the agent
to report at its next stop that the approach needs a review. Without the guard,
`RequireTests` blocks for ever and the agent repeats a strategy that does not
work.

## CheckAfterEdit

```python
CheckAfterEdit(command, *, patterns=(), reason=..., timeout=120.0,
               max_output_chars=3000, name="", command_runner=run_subprocess)
```

Runs a command after a write tool, and gives the failure output to the agent as
context. It never blocks, so it works on every harness.

```python
context.add(CheckAfterEdit("ruff check {paths}", patterns=["*.py"]))
```

- `{paths}` becomes the edited paths. In a string command they are quoted.
- With `patterns`, the command runs only when an edited path matches.

## RunCommand

```python
RunCommand(command, *, on=(Hook.SESSION_START,), reason=..., timeout=240.0,
           max_output_chars=3000, name="", command_runner=run_subprocess)
```

Runs a command on the hooks that you choose. Exit code 0 adds nothing. Anything
else gives the command output to the agent as context. It never blocks.

```python
context.add(RunCommand("dotnet test", on=[Hook.SESSION_START, Hook.SUBAGENT_START]))
```

- `Context.add` rejects a hook that has no context channel, for example `stop`.
  Use `RequireCommand` there.
- On `post-tool` it runs after each tool call, also after a read. To run a
  command only after an edit, use `CheckAfterEdit`.
- `reason` replaces the default sentence that follows the exit code. Say what
  the agent must do with the output.
- The other parameters work as in `RequireCommand`.

## RevertWrites

```python
RevertWrites(patterns, *, on=(Hook.SESSION_START, Hook.SUBAGENT_START, Hook.POST_TOOL), name="")
```

Uses git to keep matching paths equal to the last commit. It needs a git
repository at the project root or above it. It never blocks.

```python
context.add(RevertWrites(["tests/**", "pyproject.toml"]))
```

**After each tool call**, it finds the changes to matching paths, reverts them
with `git restore` and `git clean`, and tells the agent:

> The changes made to the files tests/test_a.py were reverted, because these are
> protected files that cannot be changed.

- The check reads git, not the tool call. It also finds a change that a shell
  command made, which `BlockWrites` cannot see.
- A changed, staged, deleted or new file that matches a pattern is reverted.
  Files that git ignores are not checked.
- The revert discards the changes. They cannot be restored.

**When a session or a subagent starts**, it finds the matching paths that
already have uncommitted changes, and tells the agent:

> The protected files tests/test_a.py have uncommitted changes. Protected files
> cannot be changed. Stop and ask the user to commit or discard these changes
> before you continue.

- Git cannot tell who made a change. Thus these paths are recorded in the state,
  and the process does not revert them. Your work is not lost.
- A recorded path is protected again after you commit or discard its changes.
- Do not change a protected file while the agent works. The next tool call
  reverts a change that was not there at the start.

Copilot CLI has no context channel on `session-start`, and no `subagent-start`
hook. Use `on=[Hook.POST_TOOL]` there. The first tool call of each agent then
does the start check: it gives the warning and reverts nothing.

Pair it with `BlockWrites` for the same patterns. `BlockWrites` stops a write
tool before the change. `RevertWrites` removes the changes that get past it.

## AddContext

```python
AddContext(text, *, on=(Hook.SESSION_START,), name="")
```

Adds text to the agent context.

```python
context.add(AddContext(Path("docs/agent-rules.md").read_text(), name="rules"))
```

`Context.add` rejects a hook that has no context channel, for example `stop`.

## ToolCallBudget

```python
ToolCallBudget(max_calls, *, kinds=tuple(ToolKind), reason=..., name="")
```

Counts tool calls of one agent in one session and blocks them after the maximum.
Blocked calls are not counted. Use `kinds` to count only some tools:

```python
context.add(ToolCallBudget(50, kinds=[ToolKind.SHELL], name="shell-budget"))
```

The counter is per agent folder, so a subagent has its own budget.

## The command runner

```python
@dataclass(frozen=True, slots=True)
class CommandOutcome:
    exit_code: int
    output: str

CommandRunner = Callable[[Command, Path, float, str], CommandOutcome]
```

The arguments are the command, the working folder, the timeout in seconds, and
the text for the standard input of the command.

`run_subprocess` is the default. It joins stdout and stderr, and it reports a
timeout as exit code 124 and a missing program as 127, so a guardrail never
crashes because a tool is absent.

## Commands in other languages

`RequireCommand`, `CheckAfterEdit` and `RunCommand` run any program, so they
also run the test framework of a project that is not in Python. The contract is
the same for the three processes:

- **stdin:** the hook event as one JSON object. The keys are the fields of
  `HookInput` in [data-model.md](data-model.md), without `raw`, and they are the
  same for every harness. A command that does not read stdin still works.
- **Exit code:** 0 means that the command passed. Any other value means that it
  failed.
- **stdout and stderr:** on a failure, the end of the joined output goes to the
  agent. On a pass, the output is discarded.

A C# project with a test run at each point of the agent lifecycle:

```python
import agent_actions as aa
from agent_actions.processes import CheckAfterEdit, LoopGuard, RequireCommand, RunCommand

TESTS = "dotnet test --nologo"

context = aa.get_current_context()
# Start of a session or of a subagent: show the tests that fail already.
context.add(RunCommand(TESTS, on=[aa.Hook.SESSION_START, aa.Hook.SUBAGENT_START]))
# After an edit of a C# file: give the failures as feedback.
context.add(CheckAfterEdit(TESTS, patterns=["*.cs"]))
# End of the task of the agent or of a subagent: block the stop while a test fails.
context.add(
    LoopGuard(RequireCommand(TESTS, on=[aa.Hook.STOP, aa.Hook.SUBAGENT_STOP], name="tests"))
)
aa.run(context)
```

To decide in your own program, read the event from stdin, print the message for
the agent, and exit with 0 or 1.
