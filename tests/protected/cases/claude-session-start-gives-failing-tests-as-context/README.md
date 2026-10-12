# claude-session-start-gives-failing-tests-as-context

**Behaviour:** When a session starts, `RunCommand` runs the test command of a C# project.
The command fails, so its output reaches the agent as context.

**Why this case exists:** The framework is in Python, but the project that it guards
does not have to be. A command, an exit code and text are the whole contract,
so `dotnet test` works as `pytest` does. At the start, the agent learns which
tests fail already, before it changes a file.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `RunCommand("dotnet test --nologo")` | The default hook of the process is `session-start`. |
| `failing_dotnet_test` | Exit code 1 and two lines of output, in place of a real test run. |
| `hook_event_name: "SessionStart"` | A hook that cannot block. It has a context channel. |

## Walkthrough

1. `RunCommand` is attached to `session-start`, so it is active on this call.
2. The command runner returns exit code 1. An exit code other than 0 is a
   failure.
3. `RunCommand` never blocks. The result is an `allow` that carries one
   context text.
4. The text has three parts: the command and its exit code, the default
   reason `Read the output before you continue.`, and after a line break the
   command output. The output has 105 characters, which is below
   `max_output_chars` (3000), so nothing is cut.
5. Claude Code reads context on `SessionStart` from
   `hookSpecificOutput.additionalContext`.
6. `RunCommand` declares no state, so its recorded state is `{}`.

## Baseline

Computed by hand from docs/requirements.md (R45) and the RunCommand rules in
docs/processes.md.

## Run and debug

    make test-case CASE=claude-session-start-gives-failing-tests-as-context
    make debug-case CASE=claude-session-start-gives-failing-tests-as-context
