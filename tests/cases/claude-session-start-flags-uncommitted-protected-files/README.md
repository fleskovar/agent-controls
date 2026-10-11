# claude-session-start-flags-uncommitted-protected-files

**Behaviour:** When a session starts, `RevertWrites` tells the agent which protected files
already have uncommitted changes, records them, and reverts nothing.

**Why this case exists:** Git cannot tell who changed a file. Without this check, the first
tool call reverts the work that the user did before the session. The warning
tells the agent to ask the user, and the recorded list keeps the files safe.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/commit/` | The last commit of the project. `.gitignore` excludes `.hooks/`, as in a real project. |
| `inputs/project/tests/PricingTests.cs` | A protected file that the user changed before the session. |
| `inputs/project/tests/TaxTests.cs` | A new, untracked file in a protected folder. It is a change too. |
| `inputs/project/src/Pricing.cs` | A changed file outside the patterns. It is not protected. |
| `RevertWrites(["tests/**"])` | The pattern, and the default hooks, which include `session-start`. |

## Walkthrough

1. The case runner commits `inputs/commit/` and `runner.py`, then copies
   `inputs/project/` on top. Git now reports three paths: `src/Pricing.cs` and
   `tests/PricingTests.cs` are modified, and `tests/TaxTests.cs` is untracked.
2. `tests/**` covers `tests/PricingTests.cs` and `tests/TaxTests.cs`. It does not
   cover `src/Pricing.cs`. The protected paths with changes, sorted, are
   `tests/PricingTests.cs` and `tests/TaxTests.cs`.
3. The hook is `session-start`, not `post-tool`. The process records the two
   paths in the state variable `unresolved` and reverts nothing.
4. The two paths are not empty, so the result is an `allow` with the start
   warning as context. The warning names both paths, joined with `, `.
5. Claude Code reads context on `SessionStart` from
   `hookSpecificOutput.additionalContext`.
6. `worktree.json` is the same as before the call: three lines, with the
   untracked file last, as `git status --short` prints them.

## Baseline

Computed by hand from docs/requirements.md (R44) and the RevertWrites rules in
docs/processes.md.

## Run and debug

    make test-case CASE=claude-session-start-flags-uncommitted-protected-files
    make debug-case CASE=claude-session-start-flags-uncommitted-protected-files
