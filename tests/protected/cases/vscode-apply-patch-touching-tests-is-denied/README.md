# vscode-apply-patch-touching-tests-is-denied

**Behaviour:** The files of an `apply_patch` call come from the patch text, so a
patch that changes a protected file is denied.

**Why this case exists:** `apply_patch` carries no path argument at all. The
whole change is one string. Without the patch header rule, every path guard is
blind to the one VS Code tool that can rewrite a repository in a single call.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `tool_input.input` | A patch with two `*** Update File:` headers and no path key. |
| First header | An allowed file, `src/app.py`. |
| Second header | A protected file, `tests/test_app.py`. |

## Walkthrough

1. `apply_patch` is a VS Code write tool, so the kind is `write`.
2. The normal path search finds nothing: the arguments hold `explanation` and
   `input`, and neither is a path key.
3. The VS Code adapter then reads the patch headers. The expression
   `*** (Add|Update|Delete) File: <path>` gives `src/app.py` and
   `tests/test_app.py`, in the order of the patch.
4. `BlockWrites` finds no match for the first path, and matches `tests/**` on the
   second.
5. The verdict is `block`. The reason names the file inside the patch, which is
   what the agent has to act on.

## Baseline

Computed by hand from docs/requirements.md (R35) and the VS Code adapter rule for
patch headers in docs/data-model.md, section 6.

## Run and debug

    make test-case CASE=vscode-apply-patch-touching-tests-is-denied
    make debug-case CASE=vscode-apply-patch-touching-tests-is-denied
