# vscode-edit-outside-protected-paths-gets-no-decision

**Behaviour:** In VS Code, an edit outside the protected paths produces no output
at all, so the permission rules of the harness still apply.

**Why this case exists:** Two rules meet here. The VS Code adapter must read the
camelCase argument `filePath`, and an `allow` must never become an explicit
approval (R14). An explicit `permissionDecision: "allow"` switches off the
permission prompt of the user for every edit, which no guardrail intends.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `tool_name: "replace_string_in_file"` | A VS Code write tool, with another name than in Claude Code. |
| `tool_input.filePath` | The camelCase path key of VS Code. |
| Pattern `tests/**` | A pattern that must not match `src/pricing.py`. |

## Walkthrough

1. `replace_string_in_file` is in the VS Code write tools, so the kind is
   `write`.
2. `filePath` is a VS Code path key, so the path is `{{root}}/src/pricing.py`.
3. Relative to the project root the path is `src/pricing.py`.
4. Pattern `tests/**`: the path is not equal to `tests`, it does not start with
   `tests/`, and the glob does not match. There is no match.
5. `BlockWrites` returns `allow` with no reason.
6. The combined verdict is `allow`. On `pre-tool` an allow gives no decision, and
   there is no context, so the output document is empty and the CLI prints
   nothing.
7. The step is still recorded. state.json shows that the guardrail ran and
   allowed the edit.

## Baseline

Computed by hand from docs/requirements.md (R14, R19, R35) and from the VS Code
hooks reference (tool names and PreToolUse output).

## Run and debug

    make test-case CASE=vscode-edit-outside-protected-paths-gets-no-decision
    make debug-case CASE=vscode-edit-outside-protected-paths-gets-no-decision
