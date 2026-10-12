# loop-guard-allows-the-stop-after-two-blocks

**Behaviour:** After two blocked stops in a row, `LoopGuard` allows the third
stop, even though the test command still fails.

**Why this case exists:** Without this limit, `RequireTests` blocks for ever and
the agent burns a whole budget on a strategy that does not work. The case also
shows state that survives between hook calls: the counter comes from the
recorded state of the session, not from memory.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/project/.hooks/.../session.json` | A session that started at 09:30 and is found again by its short id `5c6d7e8f`. |
| Recorded `consecutive_blocks: 2` | The two earlier blocked stops. |
| `max_blocks=2` | The limit that this call reaches. |
| `failing_pytest` | The tests still fail, so the inner process still blocks. |

## Walkthrough

1. The short id of the session is `5c6d7e8f`. The folder
   `20260915T093000000_5c6d7e8f` holds a session.json with the same full id, so
   the framework reuses it. No new folder is created.
2. `latest_states` reads the newest step of state.json, which gives
   `LoopGuard(RequireTests)` the state `{"consecutive_blocks": 2, "inner": {}}`.
3. `LoopGuard` restores its own counter and passes `inner` to `RequireTests`,
   which declares no state.
4. The inner process runs the command runner. It fails again, so the inner result
   is `block`.
5. The counter is 2, and `max_blocks` is 2, so the condition
   `consecutive_blocks >= max_blocks` holds. The guard does not pass the block
   on.
6. The guard resets the counter to 0 and returns `allow`. The first reason states
   the release, and the reasons of the inner block follow, so the log keeps the
   cause.
7. The combined verdict is `allow`. On `stop`, Claude Code needs no output for an
   allow, so stdout is empty and the agent stops.
8. The recorded state shows `consecutive_blocks: 0`. The next failure starts a
   new series of two.

## Baseline

Computed by hand from docs/requirements.md (R18, R40) and the LoopGuard rules in
docs/processes.md.

## Run and debug

    make test-case CASE=loop-guard-allows-the-stop-after-two-blocks
    make debug-case CASE=loop-guard-allows-the-stop-after-two-blocks
