# claude-edit-of-protected-test-is-denied

**Behaviour:** In Claude Code, `BlockWrites` denies an `Edit` of a file under a
protected folder, and the reason tells the agent what to do instead.

**Why this case exists:** This is the main guardrail of the framework. If path
normalization or the PreToolUse output format breaks, the agent changes test
files and nobody sees an error.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `tool_name: "Edit"` | A write tool of Claude Code. |
| `tool_input.file_path` | An absolute path inside the project root. |
| Patterns `tests/**` and `pyproject.toml` | The first matching pattern wins. |

`{{root}}` is the temporary project folder. The case runner replaces it in the
inputs, and puts it back in the outputs.

## Walkthrough

1. The adapter reads `tool_name` `Edit`. `Edit` is in the Claude Code write
   tools, so the tool kind is `write`.
2. The adapter reads `tool_input.file_path`, the only value under a path key.
   The paths are therefore `("{{root}}/tests/test_pricing.py",)`.
3. `BlockWrites` guards write tools, so it checks the path.
4. Relative to the project root the path is `tests/test_pricing.py`.
5. Pattern `tests/**` matches, because `*` also matches `/`. The search stops,
   so `pyproject.toml` is never compared.
6. The result is `block` with one reason. It is the only verdict, so it wins the
   combination, and the reason gets the prefix `[BlockWrites]`.
7. On `pre-tool`, Claude Code takes a block as `permissionDecision: "deny"`
   inside `hookSpecificOutput`, with `hookEventName: "PreToolUse"`.
8. The session id starts with `3f1c9a2e`, and the clock reads
   `20260915T100000000`. The session folder is `20260915T100000000_3f1c9a2e`.
   The payload has no `agent_id`, so the agent folder is `main-agent`.
9. `BlockWrites` declares no state, so its recorded state is `{}`.

## Baseline

Computed by hand from docs/requirements.md (R13, R22 to R24, R35) and from the
Claude Code hooks reference (PreToolUse decision control).

## Run and debug

    make test-case CASE=claude-edit-of-protected-test-is-denied
    make debug-case CASE=claude-edit-of-protected-test-is-denied
