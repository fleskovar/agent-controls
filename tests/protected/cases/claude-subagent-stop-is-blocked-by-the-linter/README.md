# claude-subagent-stop-is-blocked-by-the-linter

**Behaviour:** A subagent that wants to stop while the linter fails is kept
working, and the step is recorded in the folder of that subagent.

**Why this case exists:** Three details that only appear together on this hook: a
stop process attached to `subagent-stop` instead of the default `stop`, a process
under a custom name, and a blocked **subagent** stop. The sibling case
`claude-subagent-writes-to-its-own-folder` covers the allowed direction.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `on=[aa.Hook.SUBAGENT_STOP]` | The second hook of the stop family. |
| `name="lint"` | A custom process name, which appears in the reason and in state.json. |
| `agent_type: "code-reviewer"` | The name of the subagent folder. |
| `failing_ruff` | An injected command runner: exit code 1 and one finding. |

## Walkthrough

1. The payload carries an `agent_id`, so the framework uses a subagent folder. It
   creates `code-reviewer_20260915T100000000` from the agent type and the clock.
2. The process is attached to `subagent-stop`, so it is active for this hook. On
   the `stop` hook of the main agent it would not run.
3. The command runner answers exit code 1, so the verdict is `block`, with two
   reasons: the failure and the output.
4. Both reasons carry the prefix `[lint]`, the custom name, not the class name
   `RequireCommand`. A project with three required commands therefore gets three
   readable prefixes.
5. Claude Code takes a `SubagentStop` block as `{"decision": "block", "reason":
   ...}`, exactly as for the main agent. The subagent continues to work.
6. state.json records the step under the key `lint`, inside the subagent folder,
   so the main agent record stays clean.

## Baseline

Computed by hand from docs/requirements.md (R7, R10, R22, R39).

## Run and debug

    make test-case CASE=claude-subagent-stop-is-blocked-by-the-linter
    make debug-case CASE=claude-subagent-stop-is-blocked-by-the-linter
