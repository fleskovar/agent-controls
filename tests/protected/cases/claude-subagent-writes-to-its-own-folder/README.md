# claude-subagent-writes-to-its-own-folder

**Behaviour:** A hook that a subagent fires is recorded in a folder of that
subagent, not in `main-agent`.

**Why this case exists:** State is per agent. A loop counter of a subagent must
not consume the budget of the main agent, and a reader must see which agent did
what. The case also shows a process that attaches to `subagent-stop` instead of
the default `stop`.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `agent_id: "agent-7f3e"` | The payload comes from a subagent. |
| `agent_type: "Explore"` | The folder name starts with the agent type. |
| `on=[aa.Hook.SUBAGENT_STOP]` | A stop process on the second hook of its family. |
| `passing_pytest` | The command passes, so the subagent may stop. |

## Walkthrough

1. The short id of the session is `d4e5f6a7`, so the session folder is
   `20260915T100000000_d4e5f6a7`.
2. The payload carries an `agent_id`, so the framework does not use `main-agent`.
   It looks for a folder `Explore_*` whose agent.json holds `agent-7f3e`.
3. No such folder exists, so it creates `Explore_20260915T100000000` from the
   agent type and the clock, with an agent.json that holds the id and the type.
4. The runner attaches `RequireTests` to `subagent-stop`, so the process is
   active for this hook. On `stop` it would not run.
5. The command runner answers exit code 0, so the result is `allow` with the
   reason `` `pytest -q` passed. ``
6. Reasons of an allow go to log.txt only, and `stop` hooks have no context
   channel, so the agent receives no output. The subagent stops.
7. `folders.json` has no `main-agent` entry: the main agent fired no hook in this
   case.

## Baseline

Computed by hand from docs/requirements.md (R7, R13, R22, R26) and the folder
layout in README.md.

## Run and debug

    make test-case CASE=claude-subagent-writes-to-its-own-folder
    make debug-case CASE=claude-subagent-writes-to-its-own-folder
