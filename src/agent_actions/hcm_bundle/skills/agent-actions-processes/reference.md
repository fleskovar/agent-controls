# Process reference

Import the included processes from `agent_actions.processes`. Each process works
in each supported harness, unless its section tells you a limit.

| Process | Default hook | Effect |
| --- | --- | --- |
| [`BlockWrites`](#blockwrites) | `pre-tool` | Blocks write tools on protected paths. |
| [`BlockReads`](#blockreads) | `pre-tool` | Blocks read, search and write tools on secret paths. |
| [`PathGuard`](#pathguard) | `pre-tool` | Blocks the tool kinds that you select on protected paths. |
| [`BlockShellCommands`](#blockshellcommands) | `pre-tool` | Blocks shell commands that match a regular expression. |
| [`ToolCallBudget`](#toolcallbudget) | `pre-tool` | Blocks tool calls after a maximum. |
| [`CheckAfterEdit`](#checkafteredit) | `post-tool` | Runs a command after a write tool. Adds the failure output as context. |
| [`RevertWrites`](#revertwrites) | start hooks, `post-tool` | Reverts changes to protected paths with git. |
| [`RunCommand`](#runcommand) | `session-start` | Runs a command. Adds the failure output as context. |
| [`AddContext`](#addcontext) | `session-start` | Adds text to the context of the agent. |
| [`RequireCommand`](#requirecommand) | `stop` | Blocks the stop while a command fails. |
| [`RequireTests`](#requiretests) | `stop` | `RequireCommand` with pytest. |
| [`RequireCoverage`](#requirecoverage) | `stop` | Blocks the stop when the coverage is below the session start or a minimum. |
| [`PytestCoverage`](#pytestcoverage), [`DotnetCoverage`](#dotnetcoverage), [`TypeScriptCoverage`](#typescriptcoverage) | `stop` | `RequireCoverage` for pytest, .NET and Vitest. |
| [`Limit`](#limit) | The hooks of its process | After a maximum of blocks, allows, asks the user, or blocks with a new message. |
| [`LoopGuard`](#loopguard) | The hooks of its process | Deprecated. Use `Limit`. |
| [`SetFlag`](#setflag) | `session-start` | Sets a flag for a later hook call or a later session. |

Each process accepts `name=""`. Two processes of one class in one runner file
need two names.

`context.add(process, when=condition)` runs a process only when the condition is
true. Refer to [Flags and conditions](#flags-and-conditions).

## Path patterns

`BlockWrites`, `BlockReads`, `PathGuard`, `RevertWrites` and the `patterns` of
`CheckAfterEdit` use the same rules:

- A pattern is relative to the project root. Matching ignores case.
- `*` also matches `/`. `?` matches one character.
- A pattern without a wildcard also covers the content of the folder that it
  names. `tests/**` also covers the folder `tests`.
- A name without a folder matches only in the project root. Add `**/name` for
  each depth.
- A relative tool path resolves against the working folder of the agent. If that
  folder is outside the project root, the root is the base.

## BlockWrites

```python
BlockWrites(patterns, *, reason=..., check_shell=False, name="")
```

Blocks write tools on matching paths.

```python
context.add(BlockWrites(["tests/**", "migrations/**", "pyproject.toml"]))
```

- `reason` replaces the default sentence that the agent reads. Tell the agent
  what to do instead.
- `check_shell=True` also blocks a shell command that mentions a protected path.
  It is off by default, because a test command mentions `tests`.

## BlockReads

```python
BlockReads(patterns, *, reason=..., check_shell=True, name="")
```

Blocks read, search and write tools on matching paths. By default, it also
blocks a shell command that mentions one.

```python
context.add(BlockReads([".env", "**/.env", "secrets/**", "*.pem"]))
```

- The shell check is a substring match on the part of the pattern that has no
  wildcard. It does not find a path that a command builds when it runs. It can
  match other text: `.env` also matches `.environment`.
- A search tool that names no path is not blocked.

## PathGuard

```python
PathGuard(patterns, *, kinds, reason, check_shell=False, name="")
```

The base of the two guards above. `kinds` is a set of `ToolKind` values: `READ`,
`WRITE`, `SEARCH`, `SHELL`, `OTHER`.

```python
context.add(
    PathGuard(["archive/**"], kinds={aa.ToolKind.SEARCH}, reason="Do not search the archive.")
)
```

## BlockShellCommands

```python
BlockShellCommands(patterns, *, reason=..., name="")
```

Blocks a shell command when a regular expression finds a match in it. Matching
ignores case.

```python
context.add(
    BlockShellCommands(
        [r"\brm\s+-rf\b", r"git\s+push\s+.*--force", r"git\s+commit\s+.*--no-verify"]
    )
)
```

## ToolCallBudget

```python
ToolCallBudget(max_calls, *, kinds=tuple(ToolKind), reason=..., name="")
```

Counts the tool calls of one agent in one session, and blocks them after the
maximum. A blocked call is not counted. A subagent has its own count.

```python
context.add(ToolCallBudget(50, kinds=[aa.ToolKind.SHELL], name="shell-budget"))
```

## CheckAfterEdit

```python
CheckAfterEdit(command, *, patterns=(), reason=..., timeout=120.0,
               max_output_chars=3000, name="", command_runner=run_subprocess)
```

Runs a command after a write tool. On a failure, the agent gets the output as
context. It never blocks.

```python
context.add(CheckAfterEdit([sys.executable, "-m", "ruff", "format", "{paths}"], patterns=["*.py"]))
```

- `{paths}` becomes the edited paths that match, as the harness gave them. In a
  list command, each path is one argument.
- With `patterns`, the command runs only when an edited path matches.
- A shell command that changes a file does not start this process. Only a write
  tool does.

## RevertWrites

```python
RevertWrites(patterns, *, on=(Hook.SESSION_START, Hook.SUBAGENT_START, Hook.POST_TOOL), name="")
```

Keeps matching paths equal to the last git commit. It needs a git repository
with one commit or more, at the project root or above it. It never blocks.

- **After each tool call**, it reverts the changed, staged, deleted and new files
  that match, and tells the agent. The check reads git, not the tool call. Thus
  it also finds a change from a shell command. The revert discards the change.
- **When a session or a subagent starts**, it records the matching paths that
  have changes already, and tells the agent to ask the user about them. It does
  not revert a recorded path until that path is clean.
- It does not check a file that git ignores.
- Copilot CLI has no context on `session-start` and no `subagent-start` hook.
  Use `on=[Hook.POST_TOOL]` there. The first tool call then does the start check.

Use it together with `BlockWrites` for the same patterns.

## RunCommand

```python
RunCommand(command, *, on=(Hook.SESSION_START,), reason=..., timeout=240.0,
           max_output_chars=3000, name="", command_runner=run_subprocess)
```

Runs a command on the hooks in `on`. On a failure, the agent gets the output as
context. It never blocks.

```python
context.add(RunCommand(["dotnet", "test", "--nologo"], on=[aa.Hook.SESSION_START]))
```

- Each hook in `on` must have a context channel in the harness. `stop` has none.
  Use `RequireCommand` there.
- On `post-tool`, it runs after each tool call, also after a read. To run a
  command only after an edit, use `CheckAfterEdit`.

## AddContext

```python
AddContext(text, *, on=(Hook.SESSION_START,), name="")
```

Adds fixed text to the context of the agent.

```python
context.add(AddContext("Run the build script, not the compiler.", name="rules"))
```

## RequireCommand

```python
RequireCommand(command, *, reason=..., timeout=240.0, max_output_chars=3000,
               on=(Hook.STOP,), name="", command_runner=run_subprocess)
```

Runs a command when the agent wants to stop. Exit code 0 allows the stop. Each
other exit code blocks the stop, and the agent reads the reason and the output.

```python
context.add(RequireCommand(["cargo", "clippy", "--", "-D", "warnings"], name="lint"))
context.add(RequireCommand(["mypy", "src"], name="types", on=[aa.Hook.STOP, aa.Hook.SUBAGENT_STOP]))
```

- `reason` follows the exit code in the message. Tell the agent what to do.
- With `on=[Hook.STOP, Hook.SUBAGENT_STOP]`, a subagent cannot stop while the
  command fails.

## RequireTests

```python
RequireTests(command=(sys.executable, "-m", "pytest", "-q"), *, reason=..., **options)
```

`RequireCommand` with pytest as the default command, and a reason that forbids
changes to the tests. For a different test tool, use `RequireCommand`.

## RequireCoverage

```python
RequireCoverage(command, flags=None, *, minimum=None, pattern=r"(\d+(?:\.\d+)?)\s*%",
                reports="", tolerance=0.0, reason=..., timeout=600.0, max_output_chars=3000,
                on=(Hook.STOP,), name="", command_runner=run_subprocess)
```

Blocks the stop when the coverage is below a baseline. Thus new code needs tests,
or it must be on a path that the tests run already. Give one of the two baselines:

- `flags`: compare with the coverage at the session start. Give
  `context.session_flags`, and also add `gate.baseline()`. That process measures
  the coverage on `session-start`, and keeps the first value of the session.
- `minimum`: compare with a fixed value in percent, for example `90`.

```python
gate = RequireCoverage(["make", "coverage"], context.session_flags, name="coverage")
context.add(gate.baseline())
context.add(Limit(gate, max_in_a_row=3))

coverage = RequireCoverage(["make", "coverage"], minimum=90, name="coverage")
context.add(Limit(coverage, max_in_a_row=3))
```

- The coverage is the last match of `pattern` in the command output. The pattern
  has one group, the number.
- With `reports`, a glob relative to the project root, the gate reads the line
  coverage of the Cobertura or LCOV reports that match, and not the output. It
  deletes these reports before each run. Reports of one file merge.
- A failed command blocks the stop. Output without a coverage number also blocks it.
- `tolerance` is the decrease in percentage points that the gate accepts.
- A baseline measurement that fails stores None. The gate then allows the stop.
- The baseline runs the full command at the session start. Make the hook timeout
  of `install` longer than the command.

## PytestCoverage

```python
PytestCoverage(flags=None, *, source="", **options)
```

`RequireCoverage` with pytest-cov, run by the interpreter of the hook. `source` is
the package to measure, for example `source="my_package"`. It reads the `TOTAL`
line, with two decimals.

## DotnetCoverage

```python
DotnetCoverage(flags=None, *, results=".hooks/coverage", **options)
```

`RequireCoverage` with `dotnet test --collect:"XPlat Code Coverage"`. The
coverlet.collector package of the .NET test templates writes the Cobertura reports
into `results`. The gate merges the reports of all test projects.

## TypeScriptCoverage

```python
TypeScriptCoverage(flags=None, **options)
```

`RequireCoverage` with `npx vitest run --coverage --coverage.reporter=text-summary`.
It reads the `Lines` line of the summary. For Jest, give
`command="npx jest --coverage --coverageReporters=text-summary"`. Vitest needs the
`@vitest/coverage-v8` package.

## Limit

```python
Limit(process, *, max_in_a_row=None, max_total=None, window=None,
      then=Verdict.ALLOW, message=..., counts=is_block, problem=None, reset_on=(),
      store=None, flags=None, flag="", name="", clock=time.time)
```

Wraps a process of any family, and counts its blocks. After a maximum, it
changes the verdict. Give `max_in_a_row`, `max_total` or both.

```python
context.add(Limit(RequireCommand(["dotnet", "test"], name="tests"), max_in_a_row=5, max_total=10))
context.add(Limit(BlockWrites(["migrations/**"]), max_in_a_row=2, then=aa.Verdict.ASK))
```

- `max_in_a_row`: a result that is not a block resets this count. A release
  also resets it.
- `max_total`: this count never resets. It is per agent and per session.
- The block that reaches a maximum gets `message`. On `stop`, it is the last
  text that the agent reads before the release.
- `then` is the verdict after a maximum. `ALLOW` releases the check. `ASK` lets
  the user decide, on `pre-tool` only. `BLOCK` never releases, and gives
  `message` instead.
- `counts` selects the results to count. Example: `counts=lambda result: bool(result.context)`.
- With `flags` and `flag`, each release sets the flag.
- `reset_on=[Hook.USER_PROMPT]`: a new prompt resets the count in a row.
- `problem=problem_text`: a different failure resets the count in a row. The
  function `problem_text` ignores numbers, for example durations.
- `window=600`: `max_total` counts only the results of the last 600 seconds.
- `store=context.session_flags`: the main agent and its subagents share the
  counts. `store=context.flags`: the sessions share them. A person resets the
  counts when they delete the flag with the name of the guard.
- `Context.add` rejects a `then` verdict that the hooks cannot deliver.
- The name of the guard is `Limit(<name of the process>)`.

## LoopGuard

```python
LoopGuard(process, max_blocks=3, *, name="")
```

Deprecated. Use `Limit(process, max_in_a_row=3)`. Do not add `LoopGuard` to a
new runner file.

Wraps a stop process. It passes each block and counts it. After `max_blocks`
blocks in a row, it allows the next stop and resets the count. A stop that the
wrapped process allows also resets the count.

```python
context.add(LoopGuard(RequireCommand(["dotnet", "test"], name="tests"), max_blocks=3))
```

The last block tells the agent to report, at its next stop, that the approach
needs a review. The name of the guard is `LoopGuard(<name of the process>)`.

## Flags and conditions

A flag is a named JSON value that processes share. The framework keeps it in a
file, loads it before the runner file, and writes each change after the hook call.

| Dict | File | Lifetime |
| --- | --- | --- |
| `context.flags` | `.hooks/flags.json` | All sessions of the project. |
| `context.session_flags` | `.hooks/<session>/flags.json` | One session. The main agent and its subagents share it. |

The two are plain dicts. Read and change them in a process or in a condition.

```python
context.add(process, when=condition)
```

`condition` is a function of the hook event. The process runs only when the
condition returns a true value.

```python
flags = context.flags
context.add(RequireTests(), when=lambda _: flags.get("tests-due"))
```

- Use `when`, not an `if` around `context.add`. `install` loads the runner file
  with empty flags. A process that is not added there gets no hook.
- The framework calls the condition immediately before the process. Thus the
  condition sees a flag that an earlier process set in the same hook call.
- A process that does not run gets no record in `state.json`. `log.txt` tells
  that it was skipped.
- A condition that raises an exception blocks where the hook can block.
- A flag is a file. Protect it: `BlockWrites([".hooks/**"])`.
- When two parallel hook calls change the same flag, the last call wins.

## SetFlag

```python
SetFlag(flags, flag, value=True, *, on=(Hook.SESSION_START,), keep=False, name="")
```

Sets a flag when it runs. It never blocks, and it adds no context. Thus it works
on each hook of each harness.

```python
context.add(
    SetFlag(context.flags, "tests-due", on=[aa.Hook.POST_TOOL]),
    when=lambda event: event.tool.kind is aa.ToolKind.WRITE,
)
```

- `flags` is `context.flags` or `context.session_flags`.
- `value` can be a function of the hook event. The flag gets the result.
- With `keep=True`, a flag that has a value keeps it. Use it for a baseline: a
  harness can fire `session-start` again in one session.
- The default name is `SetFlag(<flag>)`.
- To delete a flag, use `flags.pop(flag, None)` in a process, or `clear_on_pass`.

## Snapshots of the work tree

```python
git_snapshot(event) -> dict
changed_paths(root, snapshot, patterns=()) -> list[str]
on_changed_paths(flags, patterns=(), *, flag="baseline", command_runner=run_subprocess)
clear_on_pass(flags, flag, *, command_runner=run_subprocess)
```

Import the four functions from `agent_actions.processes`. They need a git
repository with one commit or more, at the project root or above it.

- `git_snapshot` is a value for `SetFlag`. It records the last commit, and a
  digest of each file that differs from it.
- `changed_paths` returns the paths whose content changed after a snapshot,
  relative to the project root. An edited, created, deleted, committed or
  reverted file is in the list. A file that had uncommitted changes at the
  snapshot, and that did not change after it, is not.
- `changed_paths` reads git, not the tool calls. Thus it also finds a change from
  a shell command. It does not compare a file that git ignores.
- Without a snapshot (`None`), each uncommitted change is in the list.
- `on_changed_paths` makes a `command_runner`. It replaces `{paths}` with the
  changed files that exist. When no file changed, the command does not run, and
  the process passes.
- `clear_on_pass` makes a `command_runner` that deletes a flag when the command
  exits with code 0.

Lint only the files that changed in this session. Run the tests only after a
change of a source file, also when that change is from an earlier session:

```python
import agent_actions as aa
from agent_actions.processes import (
    Limit,
    RequireCommand,
    RequireTests,
    SetFlag,
    changed_paths,
    clear_on_pass,
    git_snapshot,
    on_changed_paths,
)

SOURCES = ["src/**", "tests/**"]

context = aa.get_current_context()
flags, session = context.flags, context.session_flags

# Session start: keep the state of the work tree as the baseline of this session.
context.add(SetFlag(session, "baseline", git_snapshot, keep=True))

# Stop: lint only the Python files that changed after the baseline.
context.add(
    RequireCommand(
        ["ruff", "check", "{paths}"],
        name="lint",
        command_runner=on_changed_paths(session, ["*.py"]),
    )
)

# Stop: a source file changed in this session, thus the tests are due. The flag
# stays for the later sessions, until the tests pass.
context.add(
    SetFlag(flags, "tests-due", on=[aa.Hook.STOP]),
    when=lambda event: changed_paths(event.root, session.get("baseline"), SOURCES),
)
context.add(
    Limit(RequireTests(command_runner=clear_on_pass(flags, "tests-due")), max_in_a_row=3),
    when=lambda _: flags.get("tests-due"),
)

aa.run(context)
```

In one session, `tests-due` is set again at each stop while a source file differs
from the baseline. To set the flag when the session ends without a stop, add
`aa.Hook.POST_TOOL` to `on`. Git then scans the work tree after each tool call.

## Commands

The `command` of `RequireCommand`, `CheckAfterEdit` and `RunCommand`:

- A list runs without a shell. A string runs in the shell. Prefer a list.
- The command runs in the project root.
- The standard input is the hook event as one JSON object. Its keys are the
  fields of `HookInput` below, without `raw`.
- Exit code 0 is a pass. On a failure, the last `max_output_chars` characters of
  the standard output and the standard error go to the agent.
- A timeout gives exit code 124. A program that does not exist gives exit code 127.
- `command_runner` replaces the function that starts the process. A test gives a
  function that returns `CommandOutcome(exit_code, output)`:

  ```python
  from agent_actions.processes import CommandOutcome, RequireCommand


  def failing(command, cwd, timeout, stdin):
      return CommandOutcome(exit_code=1, output="1 failed, 4 passed")


  process = RequireCommand(["dotnet", "test"], command_runner=failing)
  ```

## The hook event

```python
class HookInput:
    harness: Harness  # CLAUDE, VSCODE, COPILOT_CLI
    hook: Hook  # SESSION_START, USER_PROMPT, PRE_TOOL, POST_TOOL, STOP,
    # SUBAGENT_START, SUBAGENT_STOP, PRE_COMPACT, SESSION_END
    session_id: str
    cwd: str  # the working folder of the agent
    root: str  # the project root, which holds .hooks/
    agent_id: str | None  # None for the main agent
    agent_type: str | None
    tool: ToolCall | None  # pre-tool and post-tool only
    prompt: str | None  # user-prompt only
    last_message: str | None  # stop and subagent-stop only
    stop_hook_active: bool
    raw: Mapping[str, Any]  # the payload of the harness, unchanged


class ToolCall:
    name: str  # the tool name of the harness, for example "Edit"
    kind: ToolKind  # READ, WRITE, SEARCH, SHELL, OTHER
    arguments: Mapping[str, Any]
    paths: tuple[str, ...]  # each path in the arguments, at each depth
    command: str | None  # shell tools only
    output: str | None  # post-tool only
```

Use `tool.kind` in a process, not the tool name. The kind is the same in each harness.

## Results

```python
aa.allow(*reasons, context=())  # no objection; the reasons go to log.txt
aa.ask(reason, *more, context=())  # pre-tool only: the user decides
aa.block(reason, *more, context=())  # block the tool call, the prompt or the stop
```

- `ask` and `block` need a reason. The agent reads it.
- `context` is text for the agent. The hook must have a context channel.
- When more than one process runs on a hook, the most restrictive verdict wins:
  `block`, then `ask`, then `allow`. The agent reads the reasons of the processes
  that gave that verdict, each with the process name in front.
