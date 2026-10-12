# claude-shell-change-to-a-protected-test-is-reverted

**Behaviour:** After a shell command changed a protected test and created a file in the
protected folder, `RevertWrites` reverts both with git and tells the agent.

**Why this case exists:** `BlockWrites` reads the paths of a write tool. It cannot see
a change that `sed` makes. This process reads git after the call, so the tool
that made the change does not matter. This is the main guardrail of the process.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/commit/` | The last commit of the project. `.gitignore` excludes `.hooks/`, as in a real project. |
| Recorded `unresolved: []` | The session started on a clean work tree, so no path is exempt. |
| `tool_name: "Bash"` | A shell tool. Its payload has no file path. |
| `inputs/project/tests/PricingTests.cs` | A tracked protected file with a weakened assertion: `100m` in place of `90m`. |
| `inputs/project/tests/Shortcut.cs` | A new, untracked file in the protected folder. |
| `inputs/project/src/Pricing.cs` | The real work of the agent, outside the patterns. It must stay. |

## Walkthrough

1. The folder `20260915T093000000_2b3c4d5e` holds the session of this payload,
   so the framework restores the recorded state: `unresolved` is `[]`.
2. Git reports three changed paths. `tests/**` covers two of them:
   `tests/PricingTests.cs` and `tests/Shortcut.cs`.
3. The hook is `post-tool` and a state exists, so this is the revert branch.
   No path is in `unresolved`, so both protected paths are reverted.
4. `tests/PricingTests.cs` is tracked. `git restore --source=HEAD` puts back
   the text of the last commit, with `90m`.
5. `tests/Shortcut.cs` is untracked. `git clean` deletes it.
6. The result is an `allow` with the revert warning as context. It names the
   two paths in sorted order.
7. `worktree.json` has one line left: `src/Pricing.cs` is still modified.

## Baseline

Computed by hand from docs/requirements.md (R44) and the RevertWrites rules in
docs/processes.md.

## Run and debug

    make test-case CASE=claude-shell-change-to-a-protected-test-is-reverted
    make debug-case CASE=claude-shell-change-to-a-protected-test-is-reverted
