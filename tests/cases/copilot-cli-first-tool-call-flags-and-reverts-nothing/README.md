# copilot-cli-first-tool-call-flags-and-reverts-nothing

**Behaviour:** When no start hook ran for an agent, the first `post-tool` call of
`RevertWrites` does the start check: it flags the changed protected files and
reverts nothing.

**Why this case exists:** Copilot CLI has no context channel on `sessionStart` and no
`subagentStart` hook, so the process runs on `post-tool` only. Without this
rule, the first tool call discards the work that the user did before the session.
The price is stated here: a change that the first tool call itself made to a
protected file is flagged, not reverted.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/commit/` | The last commit of the project. `.gitignore` excludes `.hooks/`, as in a real project. |
| `on=[aa.Hook.POST_TOOL]` | The only hook that works for this process on Copilot CLI. |
| No `.hooks/` folder in `inputs/project/` | No state exists for this agent: this is its first call. |
| `inputs/project/tests/PricingTests.cs` | A protected file that the user changed before the session. |
| `toolName: "bash"` | A tool call that did not touch the tests. |

## Walkthrough

1. No session folder exists, so the framework creates one. The process starts
   with its initial state: `unresolved` is `null`.
2. Git reports one changed path, `tests/PricingTests.cs`, and `tests/**`
   covers it.
3. The hook is `post-tool`, but `unresolved` is `null`. That means that no
   call recorded the start of this agent, so this call records it: the list
   becomes `[tests/PricingTests.cs]`. Nothing is reverted.
4. The context is the start warning, not the revert warning.
5. Copilot CLI reads context on `postToolUse` from a top-level
   `additionalContext` field.
6. `worktree.json` still shows the change of the user.

## Baseline

Computed by hand from docs/requirements.md (R44) and the RevertWrites rules in
docs/processes.md.

## Run and debug

    make test-case CASE=copilot-cli-first-tool-call-flags-and-reverts-nothing
    make debug-case CASE=copilot-cli-first-tool-call-flags-and-reverts-nothing
