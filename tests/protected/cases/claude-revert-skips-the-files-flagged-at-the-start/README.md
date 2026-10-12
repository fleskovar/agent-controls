# claude-revert-skips-the-files-flagged-at-the-start

**Behaviour:** After a tool call, `RevertWrites` reverts only the protected files that were
clean when the session started. A file that was flagged at the start keeps its changes.

**Why this case exists:** This is the rule that keeps the work of the user. The start
warning alone is not enough: an agent can call a tool before the user answers.
The case also shows how a flagged file becomes protected again.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/commit/` | The last commit of the project. `.gitignore` excludes `.hooks/`, as in a real project. |
| Recorded `unresolved` | The start hook flagged `tests/PricingTests.cs` and `tests/TaxTests.cs` at 09:30. |
| `tests/PricingTests.cs` | Flagged, and still changed: the user did not decide yet. |
| `tests/TaxTests.cs` | Flagged, but equal to the last commit now: the user discarded the change. |
| `tests/DiscountTests.cs` | Not flagged, and changed by the `Edit` call of this payload. |

## Walkthrough

1. The folder `20260915T093000000_3c4d5e6f` holds the session of this payload.
   The restored state is `unresolved: [tests/PricingTests.cs, tests/TaxTests.cs]`.
2. Git reports two changed paths, both covered by `tests/**`:
   `tests/DiscountTests.cs` and `tests/PricingTests.cs`.
3. The process keeps in `unresolved` only the paths that still have changes.
   `tests/TaxTests.cs` is clean, so it leaves the list. From now on it is
   protected as any other file. The list is `[tests/PricingTests.cs]`.
4. The paths to revert are the changed paths that are not in the list. That is
   `tests/DiscountTests.cs` only.
5. `git restore` puts back the last commit of `tests/DiscountTests.cs`.
   `tests/PricingTests.cs` is not touched.
6. The revert warning names `tests/DiscountTests.cs` only.
7. `worktree.json` has one line: the change of the user in
   `tests/PricingTests.cs` is still there.

## Baseline

Computed by hand from docs/requirements.md (R44) and the RevertWrites rules in
docs/processes.md.

## Run and debug

    make test-case CASE=claude-revert-skips-the-files-flagged-at-the-start
    make debug-case CASE=claude-revert-skips-the-files-flagged-at-the-start
