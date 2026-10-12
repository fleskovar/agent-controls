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
| [`SetFlag`](#setflag) | any hook | nothing; it sets a flag |

Each process can have a `when` condition. A condition can read a flag from an
earlier session. Refer to [Flags and conditions](#flags-and-conditions).

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

## Flags and conditions

The state of a process belongs to one process and one agent. A **flag** is state
that processes share. A flag is a named JSON value in a file under `.hooks/`. One
process sets it on one hook call. A different process, or a condition, reads it on
a later call.

| Dict | File | Lifetime |
| --- | --- | --- |
| `context.flags` | `.hooks/flags.json` | all sessions of the project |
| `context.session_flags` | `.hooks/<session>/flags.json` | one session; the main agent and its subagents share it |

The two are plain dicts. Read and change them in a process or in a condition. The
framework loads them before the runner file, and writes each changed flag after
the hook call.

### when

```python
context.add(process, when=condition)
```

`condition` is a function of the hook event. The process runs only when the
condition returns a true value.

```python
flags = context.flags
context.add(RequireTests(), when=lambda _: flags.get("tests-due"))
context.add(AddContext(RULES), when=lambda event: event.agent_type == "Explore")
```

- Use `when`, not an `if` around `context.add`. `install` loads the runner file
  with empty flags to find the hooks. A process that is not added gets no hook.
- The framework calls the condition immediately before the process. Thus the
  condition sees a flag that an earlier process set in the same hook call.
- A process that does not run gets no record in `state.json`, and keeps its
  state. `log.txt` gets a line that tells that the process was skipped.
- A condition that raises an exception is a failure of the process. The result
  is a block where the hook can block (fail closed).

### SetFlag

```python
SetFlag(flags, flag, value=True, *, on=(Hook.SESSION_START,), keep=False, name="")
```

Sets a flag when it runs. It never blocks, and it adds no context. Thus it works
on each hook of each harness.

```python
context.add(SetFlag(context.flags, "tests-due", on=[Hook.POST_TOOL]),
            when=lambda event: event.tool.kind is ToolKind.WRITE)
```

- `flags` is `context.flags` or `context.session_flags`.
- `value` can be a function of the hook event. The flag gets the result.
- With `keep=True`, a flag that has a value keeps it. Use it for a baseline: a
  harness can fire `session-start` again in one session, for example after a
  compaction.
- The default name is `SetFlag(<flag>)`.

To delete a flag, use `flags.pop(flag, None)` in your process, or
[`clear_on_pass`](#on_changed_paths-and-clear_on_pass).

### git_snapshot and changed_paths

```python
git_snapshot(event) -> dict
changed_paths(root, snapshot, patterns=()) -> list[str]
```

`git_snapshot` is a value for `SetFlag`. It records the last commit, and a digest
of each file that differs from it. `changed_paths` compares the work tree with a
snapshot, and returns the changed paths relative to the project root.

```python
session = context.session_flags
context.add(SetFlag(session, "baseline", git_snapshot, keep=True))
context.add(RequireTests(),
            when=lambda event: changed_paths(event.root, session.get("baseline"), ["src/**"]))
```

- A file is in the list when its content differs from its content at the
  snapshot: edited, created, deleted, committed with new content, or put back to
  the committed content.
- A file that had uncommitted changes at the snapshot, and that did not change
  after it, is not in the list. Your work from before the session is not the
  work of the agent.
- The comparison reads git, not the tool calls. Thus it also finds a change that
  a shell command made. Files that git ignores are not compared.
- Without a snapshot (`None`), each uncommitted change is in the list. A hook
  that has no baseline thus checks more files, not fewer.
- With `patterns`, only the paths that match are in the list.
- The two functions need a git repository with one commit or more, at the
  project root or above it.

### on_changed_paths and clear_on_pass

```python
on_changed_paths(flags, patterns=(), *, flag="baseline", command_runner=run_subprocess)
clear_on_pass(flags, flag, *, command_runner=run_subprocess)
```

The two functions make a `command_runner` for `RequireCommand`, `RequireTests`
and `RunCommand`.

- `on_changed_paths` replaces `{paths}` in the command with the files that
  changed after the snapshot in `flags[flag]`. Deleted files are not in
  `{paths}`. When no file changed, the command does not run, and the process
  passes.
- `clear_on_pass` deletes a flag when the command exits with code 0.

### Example: checks that follow the changes

```python
import agent_actions as aa
from agent_actions.processes import (
    LoopGuard, RequireCommand, RequireTests, SetFlag,
    changed_paths, clear_on_pass, git_snapshot, on_changed_paths,
)

SOURCES = ["src/**", "tests/**"]

context = aa.get_current_context()
flags, session = context.flags, context.session_flags

# Session start: keep the state of the work tree as the baseline of this session.
context.add(SetFlag(session, "baseline", git_snapshot, keep=True))

# Stop: lint only the Python files that changed after the baseline.
context.add(RequireCommand(["ruff", "check", "{paths}"], name="lint",
                           command_runner=on_changed_paths(session, ["*.py"])))

# Stop: a source file changed in this session, thus the tests are due. The flag
# stays for the later sessions, until the tests pass.
context.add(SetFlag(flags, "tests-due", on=[aa.Hook.STOP]),
            when=lambda event: changed_paths(event.root, session.get("baseline"), SOURCES))
context.add(LoopGuard(RequireTests(command_runner=clear_on_pass(flags, "tests-due"))),
            when=lambda _: flags.get("tests-due"))

aa.run(context)
```

A session that changes only documentation runs no tests. A session that ends
while the tests fail leaves `tests-due` in `.hooks/flags.json`. The next session
cannot stop until the tests pass, also when it changes no source file.

In one session, `tests-due` is set again at each stop while a source file
differs from the baseline. To set the flag when the session ends without a stop,
add `aa.Hook.POST_TOOL` to `on`. Git then scans the work tree after each tool
call.

### Limits

- A flag is a file. An agent that can write in `.hooks/` can change a flag. Add
  `BlockWrites([".hooks/**"])`.
- Two parallel hook calls can change two different flags. When they change the
  same flag, the last call wins.
- The framework does not delete flags. Delete `.hooks/flags.json` to start again.

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
