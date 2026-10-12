# vscode-multi-file-edit-with-one-protected-path-is-denied

**Behaviour:** A tool that edits several files in one call is denied when **one**
of its paths is protected, even when the protected path is not the first.

**Why this case exists:** A guard that reads only the first path key leaves an
easy way around itself: edit one allowed file and one protected file in the same
call. Path search is therefore recursive over the whole tool input.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `replacements[0].filePath` | An allowed file, `src/pricing.py`. |
| `replacements[1].filePath` | A protected file, in a nested list of objects. |
| Pattern `tests/**` | Matches the second path only. |

## Walkthrough

1. `multi_replace_string_in_file` is a VS Code write tool, so the kind is `write`.
2. The path search walks the whole tool input. `replacements` is not a path key,
   so it descends into the list, and finds `filePath` in each object. The paths
   are `src/pricing.py` and `tests/test_pricing.py`, in that order.
3. `BlockWrites` compares the paths in order. `src/pricing.py` does not match.
4. `tests/test_pricing.py` matches `tests/**`. The search stops at the first hit,
   and the reason names that path, not the first one.
5. The verdict is `block`, which VS Code takes as `permissionDecision: "deny"`.

## Baseline

Computed by hand from docs/requirements.md (R35) and the path search rule in
docs/data-model.md, section 6.

## Run and debug

    make test-case CASE=vscode-multi-file-edit-with-one-protected-path-is-denied
    make debug-case CASE=vscode-multi-file-edit-with-one-protected-path-is-denied
