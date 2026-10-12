# a-broken-guardrail-fails-closed

**Behaviour:** A process that raises an exception does not let the tool call
through. On a hook that can block, the exception becomes a block, with the error
in the reason and the traceback in the session log.

**Why this case exists:** A guardrail with a bug is the dangerous case, because a
crash that is treated as "no objection" removes the protection exactly when the
code is wrong. The choice here is fail closed: the agent is stopped, the user is
told, and the traceback is kept for the author.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `ModeGuard` | A process that reads `arguments["mode"]`, which no Claude Code tool sends. |
| A `Write` call | A normal, allowed edit. Only the bug stops it. |
| Hook `pre-tool` | A hook that can block, so the fail-closed rule applies. |

## Walkthrough

1. The process runs and raises `KeyError('mode')`.
2. The engine catches it. The traceback goes to log.txt, under the name of the
   process, so the author can read the failing line.
3. The hook can block, and the family of the process allows a block, so the
   engine turns the exception into a `block`.
4. The reason names the exception type and its message, and points at the log
   file. The agent can report that to the user, which is the only useful action.
5. The step is recorded like any other, so state.json shows the block. A reviewer
   sees that the guard fired, and the log shows why.

On a hook that cannot block, for example `session-start`, the run fails with exit
code 1 instead, because there is no way to be careful and quiet at the same time.

## Baseline

Computed by hand from docs/requirements.md (R16).

## Run and debug

    make test-case CASE=a-broken-guardrail-fails-closed
    make debug-case CASE=a-broken-guardrail-fails-closed
