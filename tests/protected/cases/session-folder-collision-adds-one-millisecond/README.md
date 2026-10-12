# session-folder-collision-adds-one-millisecond

**Behaviour:** Two sessions whose ids share the first 8 characters, and that
start in the same millisecond, get two folders. The second name carries a
timestamp that is 1 ms later.

**Why this case exists:** The folder name is a trimmed id, so it is not unique by
itself. Without the collision rule, the second session writes its state into the
folder of the first one, and both state histories become wrong. The case also
shows `AddContext` on a start hook.

## Inputs

| Row | Demonstrates |
| --- | --- |
| Existing folder `20260915T100000000_a1b2c3d4` | A session of another agent run, with a different full id. |
| New session id `a1b2c3d4-9999-...` | The same first 8 characters, a different session. |
| Clock `10:00:00.000` | Exactly the timestamp of the existing folder. |

## Walkthrough

1. The short id of the new session is `a1b2c3d4`, which is the first 8 characters
   that are letters, digits or `-`.
2. The framework looks for a folder that matches `*_a1b2c3d4` and whose
   session.json holds the same **full** id. The one folder present holds
   `a1b2c3d4-0000-4old-...`, so it does not match.
3. The framework builds the name from the clock: `20260915T100000000_a1b2c3d4`.
   That name exists, so it adds 1 ms: `20260915T100000001_a1b2c3d4`. That name is
   free.
4. The new folder gets a session.json with the full id, so the next hook call of
   this session finds it again.
5. The agent folder is `main-agent`, because the payload has no `agent_id`.
6. `AddContext` returns `allow` with context. On `session-start`, Claude Code
   accepts context as `hookSpecificOutput.additionalContext`.
7. `folders.json` lists three folders: the old session, the new session, and the
   main-agent folder inside the new session. The old session has no agent folder,
   because this case never ran a hook for it.

## Baseline

Computed by hand from docs/requirements.md (R23 to R26, R42).

## Run and debug

    make test-case CASE=session-folder-collision-adds-one-millisecond
    make debug-case CASE=session-folder-collision-adds-one-millisecond
