---
name: agent-actions-guardrails
description: Choose and configure the checks of an Agent Actions runner file - run the tests automatically, keep the coverage from a decrease or above a floor, lint and format the code, and stop the agent from changing or reading files. Also make a check depend on the context - run it only on the files that the session changed, only after an event, or because of a flag from an earlier session or from a person. Has runner templates for C#, Odin, Julia and Python, and a method for each other language. Use when the user asks for tests, coverage, a linter, a formatter or protected files as agent guardrails, asks to add a check to the runner file, or asks for a check that runs only in some conditions or that remembers something between sessions.
---

# Configure the checks of a project

A runner file lists processes. Each process runs on a lifecycle hook of the
agent. The included processes run the tools of the project, in any language. You
write Python only to list them.

To install the package and to register the hooks, use the `agent-actions-setup`
skill. To write a new process class, use the `agent-actions-processes` skill. Its
reference page has each parameter of each included process.

## The four moments

| Moment | Hooks | Processes | Effect on the agent |
| --- | --- | --- | --- |
| A session or a subagent starts | `session-start`, `subagent-start` | `RunCommand`, `AddContext`, `RevertWrites` | Reads the output as context. Never blocked. |
| Before a tool call | `pre-tool` | `BlockWrites`, `BlockReads`, `PathGuard`, `BlockShellCommands`, `ToolCallBudget` | The call is denied, with a reason. |
| After a tool call | `post-tool` | `CheckAfterEdit`, `RevertWrites` | Reads the failure output as context. Never blocked. |
| The agent or a subagent wants to stop | `stop`, `subagent-stop` | `RequireCommand`, `RequireTests`, `RequireCoverage`, `LoopGuard` | Continues to work until the command passes. |

A check after an edit runs many times in one task. Keep it below 10 seconds:
a formatter, a type check, the tests that the edit affects. A check on the stop
runs a small number of times. Put the full test run, the coverage and the build there.

## From a goal to a process

| Goal | Process | Moment |
| --- | --- | --- |
| Show the failing tests before work starts | `RunCommand(TESTS, on=[Hook.SESSION_START])` | start |
| Run the tests after each edit | `CheckAfterEdit(TESTS, patterns=["*.cs"])` | after a tool call |
| No stop while a test fails | `LoopGuard(RequireCommand(TESTS, name="tests"))` | stop |
| No decrease of the coverage in a session | `PytestCoverage`, `DotnetCoverage`, `TypeScriptCoverage` or `RequireCoverage`, and its `baseline()` | start and stop |
| Keep a fixed coverage floor | The same process with `minimum=80` | stop |
| Format each edited file | `CheckAfterEdit([FORMATTER, "{paths}"], patterns=[...])` | after a tool call |
| No stop with lint, type or build errors | `LoopGuard(RequireCommand(LINT, name="lint"))` | stop |
| Stop edits of files | `BlockWrites(patterns)` and `RevertWrites(patterns)` | before and after a tool call |
| Stop reads of secrets | `BlockReads([".env", "secrets/**"])` | before a tool call |
| Stop dangerous commands | `BlockShellCommands([r"git\s+push\s+.*--force"])` | before a tool call |
| Limit the retries | `LoopGuard(process, max_blocks=3)` | stop |
| Limit the tool calls | `ToolCallBudget(200)` | before a tool call |
| Give the project rules | `AddContext(text)` | start |
| Run a check only in some conditions | `context.add(process, when=...)` | each |
| Lint only the files that the session changed | `SetFlag` with `git_snapshot`, and `on_changed_paths` | start and stop |
| Run the tests only after a change of the source code | `SetFlag` with `git_snapshot`, and `when` with `changed_paths` | start and stop |
| Make the next session pay a debt, for example tests that fail | `SetFlag(context.flags, ...)` and `clear_on_pass` | after a tool call, stop, start |
| Let a person switch a guardrail on or off | A flag in `.hooks/flags.json`, and `when` | each |

`RequireTests()` is `RequireCommand` with pytest. Use it only in a Python project.

The last five rows are on the page [Checks that depend on the context](./flags-and-conditions.md).

## Procedure

1. Find the language and the tools of the project. Read its build script, its CI
   file and its README. Use the commands that the project already uses.
2. Copy the template of the language to `.hooks/agent_checks.py`:

   | Language | Page | Template |
   | --- | --- | --- |
   | C# | [C#](./csharp.md) | `./assets/csharp_checks.py` |
   | Odin | [Odin](./odin.md) | `./assets/odin_checks.py` |
   | Julia | [Julia](./julia.md) | `./assets/julia_checks.py` |
   | Python | [Python](./python.md) | `./assets/python_checks.py` |
   | Other | [Other languages](./other-languages.md) | Start from the closest template. |

3. If the template uses it, copy `./assets/coverage_floor.py` to `.hooks/coverage_floor.py`.
4. Change the constants at the top of the runner file to the commands and the
   folders of the project. Delete each process that the project does not need.
5. Run each command by hand in the project root. Fix the project, or tell the
   user, until each command passes.
6. Keep the coverage baseline of the session start, the default of the templates.
   If the user asks for a fixed floor, measure the coverage. Set `COVERAGE_MINIMUM`
   to the measured value, rounded down. Ask the user before you set a higher floor.
7. Ask the user which paths the agent must not change. Put them in `PROTECTED`,
   with a reason for each group. See [Protect files](#protect-files).
8. Register the hooks, and run one hook by hand. The `agent-actions-setup` skill
   gives the commands.

## Rules for commands

`RequireCommand`, `CheckAfterEdit` and `RunCommand` have the same contract:

- The command runs in the project root.
- Exit code 0 is a pass. Each other exit code is a failure.
- On a failure, the agent reads the last 3000 characters of the output. Use the
  quiet option of the tool, so that the summary is in those characters.
- The command gets the hook event as one JSON object on its standard input. A
  command that does not read it works too.

Write each command as a list, not as a string:

```python
CheckAfterEdit(["dotnet", "format", "whitespace", "--folder", "--include", "{paths}"])
```

- A list runs without a shell. Its behavior is the same on Windows, Linux and macOS.
- `{paths}` becomes the edited paths, as the harness gave them. They are usually
  absolute. Make sure that the tool accepts absolute paths.
- Use a string only for a program that needs a shell. On Windows, `npm` and `npx`
  are `.cmd` files and need one. Do not put `{paths}` in a string command on
  Windows: the paths get POSIX quotes, which `cmd.exe` does not remove.
- Use `sys.executable` for a Python tool. It is the interpreter that runs the hook.

Set the timeouts:

- Each process has a `timeout` in seconds: 240 by default, 120 for `CheckAfterEdit`.
- The harness has one timeout for each hook call: 300 seconds by default. Give
  `--timeout` to `agent_actions install`. Make it longer than the sum of the
  process timeouts on the stop hook.

Give each process a `name`. The name starts the reason that the agent reads, and
two processes of one class need two names.

Write each `reason` as an instruction: what the agent must do next, and which
shortcut it must not use. Example: "Fix the type errors. Do not suppress a warning."

## Checks that depend on the context

The templates run each check on each hook call. Start with them. Add a condition
when a check is too slow, too strict, or needs a memory.

| Symptom | Pattern |
| --- | --- |
| The stop is slow, and most sessions change only some files. | Check only the files that the session changed. |
| The project has old lint problems that are not the task of the agent. | Check only the files that the session changed. |
| A session ends while a check fails, and the next session does not know. | A debt for the next session. |
| The agent must read or run something before it changes some files. | A gate that an event opens. |
| A small request becomes a change of many files. | A limit for one prompt. |
| A change of one file needs a change of a different file. | Files that must change together. |
| A person must stop or steer the agents without a new install. | Switches that a person sets. |

Each pattern is a complete runner file on the page
[Checks that depend on the context](./flags-and-conditions.md). Three rules apply
to all of them:

- A flag is a named JSON value. `context.flags` is for all sessions of the
  project, and `context.session_flags` is for one session.
- Use `context.add(process, when=...)`, not an `if` around `context.add`. With an
  `if`, `install` does not register the hook of the process.
- Add `.hooks/flags.json` to `.gitignore`, and protect the flag files from the agent.

## Tests

Use the three moments together. Each one has a different job.

- **Start.** `RunCommand` shows the failures that exist before the work. The
  agent then knows which failures are its own.
- **After an edit.** `CheckAfterEdit` gives feedback early. Use it only when the
  test run is fast, or when a tool selects the affected tests.
- **Stop.** `RequireCommand` in a `LoopGuard` is the gate. This one is mandatory.

After 3 blocked stops in a row, `LoopGuard` allows the stop and tells the agent
to report that the approach needs a review. Without it, an agent that cannot fix
a test loops until the user stops it.

Protect the tests that define the behavior. If the agent can change a test, it
can make a failing test pass without a fix.

## Coverage

The coverage gate blocks the stop when the coverage is below a baseline. Thus new
code needs tests, or it must be on a path that the tests run already.

- **Baseline at the session start.** The default. `baseline()` measures the
  coverage when the session starts. The gate compares with that value.
- **Fixed baseline.** Give `minimum=80`. The gate measures nothing at the start.

```python
gate = PytestCoverage(context.session_flags, source="my_package", name="tests-and-coverage")
context.add(gate.baseline())
context.add(LoopGuard(gate))
```

| Language | Process | Needs |
| --- | --- | --- |
| Python | `PytestCoverage(flags, source="my_package")` | pytest-cov |
| C# | `DotnetCoverage(flags)` | coverlet.collector in each test project |
| TypeScript | `TypeScriptCoverage(flags)`. For Jest, give `command=`. | `@vitest/coverage-v8` |
| Other | `RequireCoverage(command, flags, pattern=...)`, or `reports="**/lcov.info"` | A command that prints the percentage, or writes Cobertura or LCOV |

The baseline runs all tests when the session starts. Give `agent_actions install`
a `--timeout` that is longer than the test run.

A fixed floor also works without the gate:

1. If the test tool has a threshold option, use it. Examples: `pytest
   --cov-fail-under=80`, `cargo llvm-cov --fail-under-lines 80`.
2. If it has none, let the tool write a Cobertura XML or an LCOV report, and use
   `coverage_floor.py`:

   ```python
   RequireCommand(
       [sys.executable, ".hooks/coverage_floor.py", "80", "coverage/**/*.xml", "--", *TESTS],
       name="tests-and-coverage",
   )
   ```

   The script deletes the old reports, runs the test command, and fails when the
   tests fail or when the line coverage is below the floor. It prints the lines
   without coverage, so the agent knows where to add tests.

Do not decrease the floor to make a stop pass. Tell the user when the floor
cannot be met.

## Lint and format

- Format after each edit, on the edited files only. A formatter that changes the
  file is not a failure.
- Check the format, the lint rules, the types and the build on the stop.
- Use the configuration files of the project. Do not put rule options in the runner file.
- Add the configuration files of the linter to `PROTECTED`. An agent that can
  change the rules can pass each check.

## Protect files

The templates have a `PROTECTED` table: one reason for the agent, and the
patterns that it covers.

```python
PROTECTED: dict[str, list[str]] = {
    "Only a person changes these tests. Fix the code, not the test.": ["tests/protected/**"],
    "These files set the checks. Ask the user to change them.": [".hooks/*.py", ".editorconfig"],
}
```

For each group, the template adds two processes:

- `BlockWrites` denies a write tool before the change.
- `RevertWrites` uses git to revert a change that got past it, for example from
  a shell command. It discards the change.

Pattern rules:

- A pattern is relative to the project root. Matching ignores case.
- `*` also matches `/`. Thus `*.pem` matches at each depth.
- A pattern without a wildcard also covers the content of that folder. `tests`
  covers `tests/unit/a_test.cs`.
- A name without a folder matches only in the project root. For each depth, add
  a second pattern: `.env` and `**/.env`.

Before you use `RevertWrites`:

- The project must be a git repository with one commit or more.
- `.gitignore` must contain `.hooks/*/` and `.hooks/flags.json`. If it does not,
  a pattern that covers `.hooks` deletes the session records and the flags.
- Commit the protected files. A protected file with changes at the session start
  is not reverted. The agent gets a message to ask the user about it.
- git cannot revert a file that it ignores, for example `.env`. For such a file,
  only `BlockWrites` works.

To protect secrets from reads, use `BlockReads`. It also blocks a shell command
that mentions the path. That check is a substring match, so use a specific pattern.
